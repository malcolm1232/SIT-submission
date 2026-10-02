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
                    # Disclosed on every skip, also when research already set the stop reason
                    # (a deadline that skips refine must not be hidden; INV-07, robustness LLM-05).
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


async def run_review(request: RunRequest, *, phases: Mapping[PhaseName, Phase] | None = None,
                     llm_factory: object = None, tools_factory: object = None, clock: object = None,
                     progress: object = None, stdin: object = None, stdout: object = None) -> RunOutcome:
    """Create the run directory and services (gateways per ``config.agent.transport``, ledger,
    registry, prompts, progress), write the initial manifest, start the background MCP warm-up,
    and run the :class:`Orchestrator` from ``INGEST``.

    Errors before the run directory exists (bad input, config, prompts) are raised as their typed
    :class:`AgentError`. Once it exists, every error is recorded (``failure.json``, ``state.json``,
    manifest outcome) and returned as ``RunOutcome.exit_code`` (``errors.ExitCode``).

    Keyword-only hooks (tests and ``selftest``): ``phases`` replaces the phase objects;
    ``llm_factory(run_dir, clock, progress)`` and ``tools_factory(run_dir, resume_offset, clock,
    progress)`` replace the gateway builders; ``clock``, ``progress``, ``stdin``/``stdout`` (plan
    approval and plan printing) replace the process defaults."""
    from sit_review_agent.clock import SystemClock
    from sit_review_agent.errors import InputError
    from sit_review_agent.models import ReviewMode
    from sit_review_agent.phases.ingest import placeholder_ref
    from sit_review_agent.prompts import PromptBundle
    from sit_review_agent.state.decision_registry import DecisionRegistry
    from sit_review_agent.state.evidence_ledger import EvidenceLedger
    from sit_review_agent.state.run_state import RunState
    from sit_review_agent.stop_rules import resolve

    clk = clock or SystemClock()
    cfg = request.config
    if not Path(request.pdf).is_file():
        raise InputError(f"input not found: {request.pdf}")
    if request.v1_pdf is not None and not Path(request.v1_pdf).is_file():
        raise InputError(f"previous version not found: {request.v1_pdf}")
    resolve(cfg.stop_rules.active)                                   # unknown stop rule = ConfigError (exit 2)
    prompts = PromptBundle.load()
    created = isoformat_z(clk.now_utc())                             # type: ignore[attr-defined]
    refs = [placeholder_ref(request.pdf, DocumentRole.UNDER_REVIEW)]
    prior_review_id: str | None = None
    if request.previous_run is not None:
        ref, prior_review_id = _run_previous_ref(Path(request.previous_run), {refs[0].doc_id})
        refs.append(ref)
    elif request.v1_pdf is not None:
        refs.append(placeholder_ref(request.v1_pdf, DocumentRole.PRIOR_VERSION, taken={refs[0].doc_id}))
        prior_review_id = f"none (prior version {Path(request.v1_pdf).name} supplied without a prior review)"
    sched = _run_fault_schedule(cfg)                                # a bad schedule is a ConfigError (exit 2)
    run_id = request.run_id or new_run_id(created)
    rd = open_run_dir(cfg, run_id)
    if rd.report_json.exists() or any(rd.checkpoints.iterdir()):
        from sit_review_agent.errors import ConfigError

        raise ConfigError(f"{rd.root} already holds a run; use `sit-review resume {rd.root}`")
    write_json_atomic(rd.effective_config, cfg.model_dump(mode="json"))
    prog = progress or _run_console_progress(clk, rd)
    state = RunState(run_id=run_id, mode=request.mode, created_utc=created,
                     review_mode=ReviewMode.DELTA if len(refs) > 1 else ReviewMode.FULL,
                     prior_review_id=prior_review_id,
                     previous_run_dir=str(request.previous_run) if request.previous_run is not None else None,
                     documents=refs)
    ctx: RunContext | None = None
    warm: asyncio.Task[None] | None = None
    try:
        llm = _run_build_llm(cfg, rd, clk, prog, sched, llm_factory)
        tools = _run_build_tools(cfg, rd, clk, prog, sched, None, tools_factory)
        ctx = RunContext(config=cfg, run_dir=rd, state=state, llm=llm, tools=tools,
                         ledger=EvidenceLedger(rd, clock=clk), registry=DecisionRegistry(), prompts=prompts,
                         clock=clk, progress=prog, plan_only=request.plan_only)  # type: ignore[arg-type]
        # Right after the tool stack exists, so cold starts overlap models.retrieve, the LLM
        # preflight, ingest and understand (robustness §10 item 2, runbook §7 drill 1).
        warm = _run_start_warmup(ctx)
        from sit_review_agent.manifest import start_manifest

        start_manifest(ctx, models_retrieve=await _run_models_retrieve(ctx))
        ctx.emit(f"run {run_id}: {rd.root}")
        failed = await _run_llm_preflight(ctx)
    except BaseException as exc:  # noqa: BLE001 - recorded in failure.json (INV-02), re-raised typed
        err = await _run_setup_failed(rd, run_id, ctx, warm, exc)
        if err is exc:
            raise
        raise err from exc
    if failed is not None:
        await _run_stop_warmup(warm)
        await _run_close_tools(ctx)
        return _run_fail(ctx, failed)
    return await _run_execute(ctx, phases, PhaseName.INGEST, stdin, stdout, warm)


async def resume_run(run_dir: Path, config: EffectiveConfig, *, accept_drift: bool = False,
                     phases: Mapping[PhaseName, Phase] | None = None, llm_factory: object = None,
                     tools_factory: object = None, clock: object = None, progress: object = None,
                     stdin: object = None, stdout: object = None) -> RunOutcome:
    """ADR-009 resume: latest checkpoint, drift check, ledger journal truncation, SelfReplayGateway,
    then :meth:`Orchestrator.run` from the next phase.

    Refuses with :class:`~sit_review_agent.errors.ResumeDriftError` (exit 5) when the effective
    config, prompt bundle or canonical text differs from the checkpoint, unless ``accept_drift``
    (recorded in the manifest's deviations; never in eval mode). Tool calls already in
    ``tools.jsonl`` are served from there, and new tool and LLM call IDs continue after the
    highest logged ones. Without any checkpoint the run restarts from ``ingest``. Hooks as in
    :func:`run_review`."""
    import json as _json

    from sit_review_agent.clock import SystemClock
    from sit_review_agent.errors import InputError, ResumeDriftError
    from sit_review_agent.hashing import sha256_text
    from sit_review_agent.prompts import PromptBundle
    from sit_review_agent.state.checkpoint import (
        check_drift,
        latest_checkpoint,
        next_phase_after,
        truncate_journal,
    )
    from sit_review_agent.state.decision_registry import DecisionRegistry
    from sit_review_agent.state.evidence_ledger import EvidenceLedger
    from sit_review_agent.state.run_state import RunState

    rd = RunDir(Path(run_dir))
    if not rd.root.is_dir():
        raise InputError(f"run directory not found: {rd.root}")
    clk = clock or SystemClock()
    prompts = PromptBundle.load()
    ckpt = latest_checkpoint(rd)
    deviations: list[str] = []
    if ckpt is None:
        if not rd.state.is_file():
            raise InputError(f"{rd.root} has neither a checkpoint nor state.json; start a new run")
        old = RunState.model_validate(_json.loads(rd.state.read_text(encoding="utf-8")))
        state = RunState(run_id=old.run_id, mode=old.mode, review_mode=old.review_mode, created_utc=old.created_utc,
                         prior_review_id=old.prior_review_id, previous_run_dir=old.previous_run_dir,
                         documents=old.documents)
        truncate_journal(rd.ledger_journal, 0)
        ledger_upto = 0
        start_at: PhaseName | None = PhaseName.INGEST
        deviations.append("resumed with no completed phase: restarted from ingest")
    else:
        if ckpt.phase is PhaseName.REPORT and rd.report_json.is_file():
            return RunOutcome(run_dir=rd.root, exit_code=0, report_md=rd.report_md)
        under = next((d for d in ckpt.state.documents if d.role is DocumentRole.UNDER_REVIEW), None)
        text_file = rd.doc_text(under.doc_id) if under is not None else None
        current_text = (sha256_text(text_file.read_text(encoding="utf-8"))
                        if text_file is not None and text_file.is_file() else "")
        if under is not None and not under.sha256_text:
            current_text = ""                                       # checkpoint before ingest finished
        current = PinnedHashes(effective_config=config.sha256(), prompts_bundle=prompts.bundle_sha256,
                               canonical_text=current_text)
        if ckpt.state.mode == "eval":
            drift = check_drift(ckpt, current, accept_drift=False)
        else:
            drift = check_drift(ckpt, current, accept_drift=accept_drift)
        if drift and not accept_drift:                               # pragma: no cover - check_drift raised
            raise ResumeDriftError(drift)
        deviations += [f"--accept-drift: {d}" for d in drift]
        truncate_journal(rd.ledger_journal, ckpt.offsets.ledger_jsonl)
        ledger_upto = ckpt.offsets.ledger_jsonl
        state = ckpt.state.model_copy(deep=True)
        start_at = next_phase_after(ckpt)
        deviations.append(f"resumed after phase {ckpt.phase.value} (checkpoint {ckpt.created_utc})")
    spent = sum(state.budget.phase_seconds.values())
    state.budget.started_monotonic = clk.monotonic() - spent        # type: ignore[attr-defined]
    state.current_phase = None
    prog = progress or _run_console_progress(clk, rd)
    sched = _run_fault_schedule(config)
    ctx: RunContext | None = None
    warm: asyncio.Task[None] | None = None
    try:
        from sit_review_agent.llm.gateway import prepare_resume

        llm = _run_build_llm(config, rd, clk, prog, sched, llm_factory)
        # New LLM call IDs continue after the logged ones; calls of the stage being re-run are
        # logged ``resumed: true`` (ADR-009 item 2).
        prepare_resume(llm, last_call_number=_run_max_id(rd.llm_log, "llm-"),
                       resumed_phase=_run_rerun_phase(rd, ckpt, start_at))
        tools_offset = rd.tools_log.stat().st_size if rd.tools_log.exists() else 0
        tools = _run_build_tools(config, rd, clk, prog, sched, tools_offset, tools_factory)
        registry = DecisionRegistry(state.registry, frozen=state.registry_frozen)
        registry._hashes = list(state.registry_hashes)             # restore the per-iteration hashes (INV-10)
        ctx = RunContext(config=config, run_dir=rd, state=state, llm=llm, tools=tools,
                         ledger=EvidenceLedger.load(rd, upto=ledger_upto, clock=clk), registry=registry,
                         prompts=prompts, clock=clk, progress=prog)    # type: ignore[arg-type]
        ctx.documents = _run_load_documents(rd, state)
        if start_at is not None:
            warm = _run_start_warmup(ctx)
        from sit_review_agent.manifest import start_manifest

        start_manifest(ctx, deviations=deviations)
        ctx.emit(f"resuming run {state.run_id} at {start_at.value if start_at else 'end'}"
                 + (f" (accepted drift: {'; '.join(d for d in deviations if d.startswith('--accept'))})"
                    if accept_drift and any(d.startswith("--accept") for d in deviations) else ""))
        if start_at is None:                                        # pragma: no cover - report checkpoint w/o file
            await _run_close_tools(ctx)
            return RunOutcome(run_dir=rd.root, exit_code=0,
                              report_md=rd.report_md if rd.report_md.exists() else None)
        failed = await _run_llm_preflight(ctx)
    except BaseException as exc:  # noqa: BLE001 - recorded in failure.json (INV-02), re-raised typed
        err = await _run_setup_failed(rd, state.run_id, ctx, warm, exc)
        if err is exc:
            raise
        raise err from exc
    if failed is not None:
        await _run_stop_warmup(warm)
        await _run_close_tools(ctx)
        return _run_fail(ctx, failed)
    return await _run_execute(ctx, phases, start_at, stdin, stdout, warm)


# ------------------------------------------------------------------------- run_review helpers


def _run_console_progress(clock: object, rd: RunDir) -> object:
    from sit_review_agent.progress import ConsoleProgress

    return ConsoleProgress(clock=clock, log_path=rd.progress_log)  # type: ignore[arg-type]


def _run_previous_ref(previous: Path, taken: set[str]) -> tuple[object, str]:
    """The prior-version document of a frozen run directory and that run's review ID."""
    import json as _json

    from sit_review_agent.errors import InputError
    from sit_review_agent.phases.ingest import placeholder_ref

    report = previous / "report.json"
    if not report.is_file():
        raise InputError(f"--previous {previous}: no report.json (only completed runs can be compared against)")
    data = _json.loads(report.read_text(encoding="utf-8"))
    under = next((d for d in data["metadata"]["documents"] if d["role"] == "under_review"), None)
    if under is None:
        raise InputError(f"--previous {previous}: report.json lists no document under review")
    text = previous / under["text_path"]
    if not text.is_file():
        raise InputError(f"--previous {previous}: canonical text {under['text_path']} is missing")
    ref = placeholder_ref(text, DocumentRole.PRIOR_VERSION, taken=taken, version=under.get("version"))
    ref = ref.model_copy(update={"title": under.get("title") or ""})
    return ref, str(data["metadata"]["review_id"])


def _run_fault_schedule(cfg: EffectiveConfig) -> object:
    if not cfg.agent.fault_schedule:
        return None
    from sit_review_agent.tools.faults import load_fault_schedule

    return load_fault_schedule(cfg.resolve_repo_path(cfg.agent.fault_schedule))


def _run_build_llm(cfg: EffectiveConfig, rd: RunDir, clock: object, progress: object, sched: object,
                   factory: object) -> object:
    """``FakeGateway`` with the selftest fixture script for ``transport: fake``; otherwise the
    backend named by ``llm.backend`` (ADR-010). Wrapped by the fault injector when a schedule is set."""
    from sit_review_agent.config import Transport
    from sit_review_agent.llm.backend import build_llm_gateway
    from sit_review_agent.llm.gateway import FaultInjectingLLMGateway

    if factory is not None:
        gw = factory(rd, clock, progress)  # type: ignore[operator]
    elif cfg.agent.transport is Transport.FAKE:
        from sit_review_agent.selftest import fixture_gateway

        gw = fixture_gateway(rd, clock=clock, model=cfg.agent.model)
    else:
        gw = build_llm_gateway(cfg, rd, clock=clock, progress=progress)  # type: ignore[arg-type]
    if sched is not None:
        gw = FaultInjectingLLMGateway(gw, sched, clock=clock, policy=cfg.agent.llm)  # type: ignore[arg-type]
        # The wrapper forwards ``native_pdf`` from the backend it wraps (llm.backend.supports_native_pdf).
    return gw


def _run_build_tools(cfg: EffectiveConfig, rd: RunDir, clock: object, progress: object, sched: object,
                     resume_offset: int | None, factory: object) -> object:
    """``None`` for a doc-only run (``--no-tools`` or no enabled server); else the layer stack of
    ``tools.gateway.build_tool_gateway``. ``transport: fake`` uses a strict ``ReplayGateway`` over
    ``replay.fixtures`` when given (selftest), else an empty fake. On resume, ``resume_offset``
    adds the ``SelfReplayGateway`` and new call IDs continue after the highest logged one."""
    from sit_review_agent.config import Transport
    from sit_review_agent.tools.gateway import CallIds, FakeToolGateway, ReplayGateway, build_tool_gateway

    if factory is not None:
        gw = factory(rd, resume_offset, clock, progress)  # type: ignore[operator]
    elif not cfg.tools.enabled_servers():
        return None
    else:
        base = None
        if cfg.agent.transport is Transport.FAKE:
            ids = CallIds()
            enabled = [s.name for s in cfg.tools.enabled_servers()]
            base = (ReplayGateway(cfg.resolve_repo_path(cfg.agent.replay.fixtures), strict=cfg.agent.replay.strict,
                                  servers=enabled, clock=clock, ids=ids,  # type: ignore[arg-type]
                                  capabilities=cfg.tools.capabilities)
                    if cfg.agent.replay.fixtures else FakeToolGateway([], {}, clock=clock, ids=ids))  # type: ignore[arg-type]
        gw = build_tool_gateway(cfg, rd, clock=clock, progress=progress, fault_schedule=sched,  # type: ignore[arg-type]
                                resume_offset=resume_offset, base=base)
    if gw is not None and resume_offset is not None:
        _run_advance_ids(gw, _run_max_id(rd.tools_log, "call-"))
    return gw


def _run_chain(gw: object) -> list[object]:
    out: list[object] = []
    seen: set[int] = set()
    while gw is not None and id(gw) not in seen:
        seen.add(id(gw))
        out.append(gw)
        gw = getattr(gw, "inner", None)
    return out


def _run_advance_ids(gw: object, n: int) -> None:
    """Continue tool call numbering after ``call-<n>`` on every :class:`CallIds` of the stack
    (``ids`` on base layers, ``_ids`` captured by the policy and fault layers; usually one shared
    object), advanced in place so no layer keeps an older counter and resumed calls never reuse a
    logged ID."""
    from sit_review_agent.tools.gateway import CallIds

    if n <= 0:
        return
    for layer in _run_chain(gw):
        for attr in ("ids", "_ids"):
            cur = getattr(layer, attr, None)
            if isinstance(cur, CallIds):
                cur.advance_to(n)


def _run_rerun_phase(rd: RunDir, ckpt: object, start_at: PhaseName | None) -> PhaseName | None:
    """The stage a resume re-runs, if it had already made model calls after the checkpoint (its
    re-issued calls are logged ``resumed: true``, ADR-009 item 2); else ``None``."""
    from sit_review_agent.rundir import JsonlWriter

    if start_at is None:
        return None
    upto = ckpt.offsets.llm_jsonl if ckpt is not None else 0  # type: ignore[attr-defined]
    log = JsonlWriter(rd.llm_log)
    after = log.read()[len(log.read(upto)):]
    return start_at if any(e.get("phase") == start_at.value for e in after) else None


def _run_max_id(path: Path, prefix: str) -> int:
    from sit_review_agent.rundir import JsonlWriter

    best = 0
    for e in JsonlWriter(path).read():
        cid = str(e.get("call_id") or "")
        if cid.startswith(prefix) and cid[len(prefix):].isdigit():
            best = max(best, int(cid[len(prefix):]))
    return best


def _run_load_documents(rd: RunDir, state: object) -> dict[str, object]:
    """Rebuild the ingested documents from the run directory (resume)."""
    from sit_review_agent.ingest.pdf import Document

    docs: dict[str, object] = {}
    for ref in state.documents:  # type: ignore[attr-defined]
        if not ref.sha256_text or not rd.doc_text(ref.doc_id).is_file():
            continue
        pdf = Path(ref.pdf_path) if ref.pdf_path and ref.pdf_path.lower().endswith(".pdf") else None
        doc = Document.load(rd, ref.doc_id, pdf_path=pdf if pdf is not None and pdf.is_file() else None,
                            title=ref.title, role=ref.role)
        doc.version = ref.version
        if pdf is None:
            doc.extractor = doc.extractor.model_copy(update={"name": "text", "version": "n/a"})
        docs[ref.doc_id] = doc
    return docs


async def _run_models_retrieve(ctx: RunContext) -> dict[str, object]:
    """``models.retrieve`` once per run for the manifest (REPRODUCIBILITY §2), when the backend has it."""
    from sit_review_agent.config import Transport

    if ctx.config.agent.transport is Transport.FAKE:
        return {"status": "not retrieved (transport fake)"}
    for layer in _run_chain(ctx.llm):
        fn = getattr(layer, "models_retrieve", None)
        if fn is not None:
            try:
                return dict(await fn())
            except Exception as exc:  # noqa: BLE001 - recorded, never fatal
                return {"status": f"failed: {type(exc).__name__}"}
    return {"status": f"not available for backend {ctx.config.agent.llm.backend}"}


async def _run_llm_preflight(ctx: RunContext) -> AgentError | None:
    """Fail fast before ingest when the live backend is unusable (missing key or CLI; LLM-11):
    ``preflight()`` of the first gateway layer that has one. ``transport: fake`` skips it."""
    from sit_review_agent.config import Transport

    if ctx.config.agent.transport is Transport.FAKE:
        return None
    for layer in _run_chain(ctx.llm):
        fn = getattr(layer, "preflight", None)
        if fn is None:
            continue
        try:
            await fn()
        except AgentError as exc:
            return exc
        except NotImplementedError:
            ctx.emit("LLM preflight not implemented by this backend; skipped", "warn")
        except Exception as exc:  # noqa: BLE001 - an unusable backend is reported, never a traceback
            from sit_review_agent.errors import LLMUnavailableError

            return LLMUnavailableError(f"LLM preflight failed: {type(exc).__name__}: {str(exc)[:200]}")
        return None
    return None


def _run_start_warmup(ctx: RunContext) -> object:
    """Background MCP warm-up (overlaps ingest and understand; runbook §7 drill 1), when the tool
    gateway has one; otherwise says so."""
    if ctx.tools is None:
        return None
    for layer in _run_chain(ctx.tools):
        fn = getattr(layer, "warm_up", None)
        if fn is not None and asyncio.iscoroutinefunction(fn):
            async def _warm(fn: object = fn) -> None:
                try:
                    health = await fn()  # type: ignore[operator]
                    ctx.progress.emit("run", f"MCP warm-up done: {health}")
                except NotImplementedError:
                    ctx.progress.emit("run", "MCP warm-up not implemented by the tool gateway; skipped", "warn")
                except Exception as exc:  # noqa: BLE001 - warm-up is best effort
                    ctx.progress.emit("run", f"MCP warm-up failed ({type(exc).__name__}); servers start cold", "warn")

            return asyncio.create_task(_warm())
    ctx.progress.emit("run", "no MCP warm-up for this tool transport; skipped")
    return None


async def _run_stop_warmup(warm: object) -> None:
    """Cancel the background warm-up (if still running) and wait for it to finish, so no MCP
    connection task outlives the run (also on errors and Ctrl-C)."""
    if warm is None:
        return
    warm.cancel()  # type: ignore[attr-defined]
    try:
        await warm  # type: ignore[misc]
    except BaseException:  # noqa: BLE001 - a cancelled or failed warm-up is not the run's error
        pass


async def _run_setup_failed(rd: RunDir, run_id: str, ctx: RunContext | None, warm: object,
                            exc: BaseException) -> AgentError:
    """A failure after the run directory exists but before the orchestrator starts (gateway
    construction, manifest, LLM preflight): stop the warm-up, close the tools, write
    ``failure.json`` (INV-02) and return the typed error to raise (an :class:`AgentError` as is,
    Ctrl-C as :class:`RunInterrupted`, anything else as :class:`StageCrash`, exit 4; INV-11)."""
    if isinstance(exc, AgentError):
        err: AgentError = exc
    elif isinstance(exc, KeyboardInterrupt | asyncio.CancelledError):
        err = RunInterrupted("interrupted while starting the run")
    else:
        err = StageCrash("run", exc)
    import json as _json

    await _run_stop_warmup(warm)
    if ctx is not None:
        await _run_close_tools(ctx)
    record: dict[str, object] = {}
    if rd.failure.is_file():                    # resume: keep what the earlier failure recorded
        try:
            record = dict(_json.loads(rd.failure.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            record = {}
    done = [p.value for p in ctx.state.completed_phases] if ctx is not None else record.get("completed_phases", [])
    record.update({"run_id": run_id, "exit_code": int(err.exit_code), "error": type(err).__name__,
                   "message": str(err)[:4000], "phase": None, "completed_phases": done, "stage": "setup",
                   "resumable": bool(done), "resume": f"sit-review resume {rd.root}"})
    record.pop("cause", None)
    if not isinstance(exc, AgentError):
        record["cause"] = f"{type(exc).__name__}: {str(exc)[:2000]}"
    try:
        write_json_atomic(rd.failure, record)
    except OSError:
        pass
    return err


async def _run_close_tools(ctx: RunContext) -> None:
    if ctx.tools is not None:
        try:
            await ctx.tools.aclose()
        except Exception:  # noqa: BLE001 - closing is best effort (stub layers may not implement it)
            pass


def _run_format_plan(plan: object) -> str:
    if plan is None:
        return "No research plan was produced."
    qs = plan.questions  # type: ignore[attr-defined]
    lines = [f"Research plan: {len(qs)} question(s)"]
    for q in qs:
        lines.append(f"  {q.id} [{q.criterion_id}] ({q.capability}; external: {'yes' if q.needs_external else 'no'}) "
                     f"{q.question}")
        if q.queries:
            lines.append(f"      queries: {'; '.join(q.queries)}")
        if q.section_refs:
            lines.append(f"      sections: {', '.join(q.section_refs)}")
    for s in plan.criteria_skipped:  # type: ignore[attr-defined]
        lines.append(f"  skipped {s.criterion_id}: {s.reason}")
    return "\n".join(lines)


class _run_SettledUnderstand:  # private helper: `_run_` prefix by workstream rule
    """``understand`` followed by the code-only registry anchor check (before research records
    registry hashes, so INV-10 and INV-04 can both hold; see ``phases.verify``)."""

    def __init__(self, inner: Phase) -> None:
        self.inner = inner
        self.name = inner.name

    async def run(self, ctx: RunContext) -> RunContext:
        from sit_review_agent.phases.verify import settle_registry_anchors

        ctx = await self.inner.run(ctx)
        settle_registry_anchors(ctx)
        return ctx


class _run_PlanGate:  # private helper: `_run_` prefix by workstream rule
    """``plan`` followed by printing the plan (``--plan-only`` / ``plan_approval``) and, with
    ``plan_approval``, a y/N confirmation on stdin. A non-interactive stdin (not a TTY) approves
    automatically and says so; a refusal stops the run after the plan (resumable)."""

    def __init__(self, inner: Phase, stdin: object, stdout: object) -> None:
        self.inner = inner
        self.name = inner.name
        self.stdin = stdin
        self.stdout = stdout

    async def run(self, ctx: RunContext) -> RunContext:
        import sys

        ctx = await self.inner.run(ctx)
        approval = ctx.config.agent.plan_approval and not ctx.plan_only
        if not (ctx.plan_only or approval):
            return ctx
        out = self.stdout or sys.stdout
        print(_run_format_plan(ctx.state.plan), file=out, flush=True)  # type: ignore[call-overload]
        if not approval:
            return ctx
        inp = self.stdin or sys.stdin
        interactive = bool(getattr(inp, "isatty", lambda: False)())
        if not interactive and self.stdin is None:
            ctx.emit("plan_approval: stdin is not a terminal; plan approved automatically (non-interactive)", "warn")
            return ctx
        print("Approve this plan and start research? [y/N] ", end="", file=out, flush=True)  # type: ignore[call-overload]
        answer = (inp.readline() or "").strip().lower()  # type: ignore[attr-defined]
        if answer in ("y", "yes"):
            ctx.emit("plan approved")
            return ctx
        if ctx.state.plan is not None:
            ctx.state.plan.approved = False
        ctx.plan_only = True
        ctx.emit("plan not approved: stopping after the plan (`sit-review resume` continues with research)", "warn")
        return ctx


def _run_wrap_phases(phases: Mapping[PhaseName, Phase] | None, stdin: object, stdout: object) -> dict[PhaseName, Phase]:
    from sit_review_agent.phases import default_phases

    out = dict(phases) if phases is not None else default_phases()
    out[PhaseName.UNDERSTAND] = _run_SettledUnderstand(out[PhaseName.UNDERSTAND])
    out[PhaseName.PLAN] = _run_PlanGate(out[PhaseName.PLAN], stdin, stdout)
    return out


async def _run_execute(ctx: RunContext, phases: Mapping[PhaseName, Phase] | None, start_at: PhaseName,
                       stdin: object, stdout: object, warm: object = None) -> RunOutcome:
    """Run the orchestrator, map errors to exit codes, record failures, close the gateways and
    stop the background warm-up (started by the caller right after the tool stack was built)."""
    from sit_review_agent.manifest import finalise_manifest
    from sit_review_agent.models import Outcome

    rd = ctx.run_dir
    try:
        ctx = await Orchestrator(_run_wrap_phases(phases, stdin, stdout)).run(ctx, start_at=start_at)
    except AgentError as exc:
        return _run_fail(ctx, exc)
    except Exception as exc:  # noqa: BLE001 - never a traceback (INV-11): a typed stage crash
        return _run_fail(ctx, StageCrash(ctx.state.current_phase.value if ctx.state.current_phase else "run", exc))
    finally:
        await _run_stop_warmup(warm)
        await _run_close_tools(ctx)
    if rd.report_json.is_file() and PhaseName.REPORT in ctx.state.completed_phases:
        ctx.emit(f"report: {rd.report_md}", "done")
        return RunOutcome(run_dir=rd.root, exit_code=0, report_md=rd.report_md)
    try:
        finalise_manifest(ctx, Outcome.ABORTED_GRACEFUL)
    except Exception:  # noqa: BLE001 - best effort; the run itself succeeded
        pass
    ctx.emit("stopped after the plan; no report written", "done")
    return RunOutcome(run_dir=rd.root, exit_code=0, report_md=None)


def _run_fail(ctx: RunContext, exc: AgentError) -> RunOutcome:
    """Record a failed run (``failure.json``, manifest outcome) and return its exit code."""
    import json as _json

    from sit_review_agent.errors import ExitCode
    from sit_review_agent.manifest import finalise_manifest
    from sit_review_agent.models import Outcome

    code = ExitCode(int(exc.exit_code))
    rd = ctx.run_dir
    record: dict[str, object] = {}
    if rd.failure.is_file():
        try:
            record = dict(_json.loads(rd.failure.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            record = {}
    phase = getattr(exc, "phase", None) or (ctx.state.current_phase.value if ctx.state.current_phase else None)
    record.update({"run_id": ctx.state.run_id, "exit_code": int(code), "error": type(exc).__name__,
                   "message": str(exc)[:4000], "phase": phase,
                   "completed_phases": [p.value for p in ctx.state.completed_phases],
                   "resumable": code in (ExitCode.LLM_UNAVAILABLE, ExitCode.SIGINT, ExitCode.STAGE_CRASH),
                   "resume": f"sit-review resume {rd.root}"})
    cause = getattr(exc, "cause", None)
    if cause is not None:
        record["cause"] = f"{type(cause).__name__}: {str(cause)[:2000]}"
    try:
        write_json_atomic(rd.failure, record)
    except OSError:
        pass
    outcome = Outcome.CRASHED if code is ExitCode.STAGE_CRASH else Outcome.ABORTED_GRACEFUL
    try:
        finalise_manifest(ctx, outcome)
    except Exception:  # noqa: BLE001 - the failure record above is what matters
        pass
    ctx.progress.emit(phase or "run", f"error ({type(exc).__name__}, exit {int(code)}): {str(exc)[:300]}; "
                      f"state saved; resume with `sit-review resume {rd.root}`", "warn")
    return RunOutcome(run_dir=rd.root, exit_code=int(code), report_md=None)


def open_run_dir(config: EffectiveConfig, run_id: str) -> RunDir:
    return RunDir(config.resolve_repo_path(config.agent.run_root) / run_id).create()
