"""The explicit state machine (ADR-001): runs phases in ``PHASE_ORDER``, honours phase flags and
the between-phase caps (deadline, token budget), checkpoints after every completed phase
(ADR-009), and prints a progress line per step (runbook §5).

Failure handling (exit codes in :mod:`sit_review_agent.errors`):

* ``LLMError`` raised by the gateway after its retry budget -> ``state.json`` written, re-raised
  (exit 3, resumable from the last checkpoint).
* ``KeyboardInterrupt`` / cancellation -> ``state.json`` written, :class:`RunInterrupted` (130).
* any other exception in a phase -> :class:`StageCrash` (exit 4) after ``state.json`` is written.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from sit_review_agent.clock import isoformat_z
from sit_review_agent.config import EffectiveConfig
from sit_review_agent.context import RunContext
from sit_review_agent.errors import AgentError, RunInterrupted, StageCrash
from sit_review_agent.models import DegradationType, DocumentRole
from sit_review_agent.phases.base import Phase
from sit_review_agent.rundir import RunDir, write_json_atomic
from sit_review_agent.state.checkpoint import Checkpoint, PinnedHashes, journal_offsets, write_checkpoint
from sit_review_agent.state.run_state import RunMode
from sit_review_agent.states import ON_CAP, PHASE_ORDER, TRANSITIONS, PhaseName
from sit_review_agent.stop_rules import check_caps


def new_run_id(clock_iso: str) -> str:
    """``YYYYMMDDTHHMMSSZ-<8 hex>``: sortable, unique, safe as a directory name."""
    stamp = clock_iso.replace("-", "").replace(":", "")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def pinned_hashes(ctx: RunContext) -> PinnedHashes:
    under = [d for d in ctx.state.documents if d.role is DocumentRole.UNDER_REVIEW]
    text = under[0].sha256_text if under else ""
    return PinnedHashes(effective_config=ctx.config.sha256(), prompts_bundle=ctx.prompts.bundle_sha256,
                        canonical_text=text)


class Orchestrator:
    def __init__(self, phases: Mapping[PhaseName, Phase] | None = None) -> None:
        if phases is None:
            from sit_review_agent.phases import default_phases

            phases = default_phases()
        missing = [p for p in PHASE_ORDER if p not in phases]
        if missing:
            raise ValueError(f"orchestrator needs every phase; missing {missing}")
        self.phases = dict(phases)

    def checkpoint(self, ctx: RunContext, phase: PhaseName) -> Path:
        ctx.sync_state()
        ckpt = Checkpoint(run_id=ctx.state.run_id, phase=phase, seq=PHASE_ORDER.index(phase) + 1,
                          created_utc=isoformat_z(ctx.clock.now_utc()), hashes=pinned_hashes(ctx),
                          offsets=journal_offsets(ctx.run_dir), state=ctx.state)
        return write_checkpoint(ctx.run_dir, ckpt)

    def _flush_state(self, ctx: RunContext) -> None:
        ctx.sync_state()
        write_json_atomic(ctx.run_dir.state, ctx.state.model_dump(mode="json"))

    async def run(self, ctx: RunContext, *, start_at: PhaseName = PhaseName.INGEST) -> RunContext:
        """Run from ``start_at`` (``INGEST`` for a new run, the phase after the last checkpoint on
        resume) to ``REPORT``, or to ``PLAN`` when ``ctx.plan_only``."""
        if not ctx.state.completed_phases and ctx.state.budget.started_monotonic == 0.0:
            ctx.state.budget.started_monotonic = ctx.clock.monotonic()
        phase: PhaseName | None = start_at
        while phase is not None:
            if not ctx.config.agent.phases.enabled(phase):
                ctx.progress.emit(phase.value, "skipped (disabled in config/agent.yaml)")
                phase = TRANSITIONS[phase]
                continue
            if phase in ON_CAP:
                cap = check_caps(ctx.state, ctx.config.stop_rules, ctx.elapsed_s())
                if cap is not None:
                    if ctx.state.stop_reason is None:
                        ctx.state.stop_reason = cap
                        ctx.state.add_degradation(DegradationType.BUDGET_OR_DEADLINE_HIT,
                                                  f"stop rule {cap.detail} ({cap.code}) before {phase.value}",
                                                  f"skipped to {ON_CAP[phase].value}; evidence may be partial")
                    ctx.progress.emit(phase.value, f"stop rule {cap.code} fired; skipping to {ON_CAP[phase].value}",
                                      "warn")
                    phase = ON_CAP[phase]
                    continue
            ctx.state.current_phase = phase
            ctx.progress.emit(phase.value, "started")
            t0 = ctx.clock.monotonic()
            try:
                ctx = await self.phases[phase].run(ctx)
            except (KeyboardInterrupt, asyncio.CancelledError) as exc:
                self._flush_state(ctx)
                ctx.progress.emit(phase.value, "interrupted; state flushed (resume continues from the last "
                                  "completed phase)", "warn")
                raise RunInterrupted(f"interrupted during {phase.value}") from exc
            except AgentError:
                self._flush_state(ctx)
                raise
            except Exception as exc:  # noqa: BLE001 - every unexpected error becomes a typed stage crash
                self._flush_state(ctx)
                raise StageCrash(phase.value, exc) from exc
            ctx.state.budget.phase_seconds[phase.value] = round(ctx.clock.monotonic() - t0, 3)
            ctx.state.completed_phases.append(phase)
            self.checkpoint(ctx, phase)
            ctx.progress.emit(phase.value, f"done in {ctx.state.budget.phase_seconds[phase.value]:.1f}s", "done")
            if ctx.plan_only and phase is PhaseName.PLAN:
                ctx.progress.emit(phase.value, "--plan-only: stopping after the plan (zero tool calls)")
                break
            phase = TRANSITIONS[phase]
        ctx.state.current_phase = None
        return ctx


@dataclass(frozen=True)
class RunRequest:
    """Everything ``sit-review run`` passes to :func:`run_review`."""

    pdf: Path
    config: EffectiveConfig
    v1_pdf: Path | None = None           # delta mode against a prior PDF (fresh_eyes --previous-pdf)
    previous_run: Path | None = None     # delta mode against a frozen prior run directory
    mode: RunMode = "dev"
    plan_only: bool = False
    run_id: str | None = None


@dataclass(frozen=True)
class RunOutcome:
    run_dir: Path
    exit_code: int
    report_md: Path | None


async def run_review(request: RunRequest) -> RunOutcome:
    """Create the run directory and services (gateways per ``config.agent.transport``, ledger,
    registry, prompts, progress), write the initial manifest, start the background MCP warm-up,
    and run the :class:`Orchestrator` from ``INGEST``."""
    raise NotImplementedError("phase 3: run_review (workstream C)")


async def resume_run(run_dir: Path, config: EffectiveConfig, *, accept_drift: bool = False) -> RunOutcome:
    """ADR-009 resume: latest checkpoint, drift check, ledger journal truncation, SelfReplayGateway,
    then :meth:`Orchestrator.run` from the next phase."""
    raise NotImplementedError("phase 3: resume_run (workstream C)")


def open_run_dir(config: EffectiveConfig, run_id: str) -> RunDir:
    return RunDir(config.resolve_repo_path(config.agent.run_root) / run_id).create()
