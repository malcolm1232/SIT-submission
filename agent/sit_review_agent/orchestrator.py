"""The explicit state machine (ADR-001, amended by the latency redesign, design section 4): runs
the stages in ``STAGE_ORDER`` (ingest, stage 1, refine, verify, report), honours phase flags and the
caps (deadline, token budget, ``stop_rules.stage_limits_s``), checkpoints after every ended phase
(ADR-009), and prints a progress line per step (runbook §5).

Stage 1 runs understand, plan and the assess shards concurrently (asyncio tasks on the run's event
loop: the gateways' ``claude -p`` calls are asyncio subprocesses and the MCP client is async, so a
task per member overlaps their waiting with no thread); research starts when understand and plan
have both ended (``states.STAGE_1_DEPENDS``). Each member runs on its own copy of the run state
(``phases._isolation``) and is merged back when it ends, so a checkpoint never holds a member's
half-written state. The stage ends when every member has ended, or at ``stage_1_end``: the runtime
cuts the model calls still open at the limit (``LLMDeadlineError``, the phases keep what they
salvaged), and members still running ``stage1_grace_s`` later are stopped here and disclosed. Then
the assess shards are merged in shard order (finding and evidence IDs never depend on which member
finished first) and the stage's last checkpoint (``assess``) is written.

Checkpoints and resume (ADR-009): every stage 1 member writes its checkpoint when it ends (the
checkpoint ordinal, not the file name, says which is latest); every finished assess shard is stored
in ``shards/<k>-<name>.json``; ``budget.elapsed_s`` is set at every checkpoint. Resume re-runs only
the members and shards that had not finished and restores the run clock from ``elapsed_s``. The
ledger offset a checkpoint records never covers half of research (the only member that writes the
ledger during stage 1): understand and plan end before research starts, and assess's checkpoint is
written when the stage closes, so no checkpoint is written while research runs.

Failure handling (exit codes in :mod:`sit_review_agent.errors`):

* ``LLMError`` raised by the gateway after its retry budget -> ``state.json`` written, re-raised
  (exit 3, resumable from the last checkpoint). In stage 1 the other members are stopped first. A
  failed assess shard is not a run failure while another shard assessed (``phases.assess``).
* ``KeyboardInterrupt`` / cancellation -> ``state.json`` written, :class:`RunInterrupted` (130).
* any other exception in a phase -> :class:`StageCrash` (exit 4) after ``state.json`` is written.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sit_review_agent.clock import isoformat_z
from sit_review_agent.config import EffectiveConfig
from sit_review_agent.context import RunContext
from sit_review_agent.errors import AgentError, RunInterrupted, StageCrash
from sit_review_agent.models import DegradationType, DocumentRole, StopReason, StopReasonCode
from sit_review_agent.phases.base import Phase
from sit_review_agent.progress import milestone
from sit_review_agent.rundir import RunDir, write_json_atomic
from sit_review_agent.state.checkpoint import Checkpoint, PinnedHashes, journal_offsets, write_checkpoint
from sit_review_agent.state.run_state import RunMode
from sit_review_agent.states import (
    PHASE_ORDER,
    STAGE_MEMBERS,
    STAGE_ON_CAP,
    STAGE_TRANSITIONS,
    MemberOutcome,
    PhaseName,
    Stage,
    stage1_close,
    stage1_ready,
    stage_of,
)
from sit_review_agent.stop_rules import check_caps

#: The concurrent members of stage 1, in launch order (shards are numbered after them).
STAGE_1 = STAGE_MEMBERS[Stage.STAGE_1]
#: Run-directory folder of the finished assess shards (resume re-runs only the others).
SHARDS_DIR = "shards"


def new_run_id(clock_iso: str) -> str:
    """``YYYYMMDDTHHMMSSZ-<8 hex>``: sortable, unique, safe as a directory name."""
    stamp = clock_iso.replace("-", "").replace(":", "")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def pinned_hashes(ctx: RunContext) -> PinnedHashes:
    under = [d for d in ctx.state.documents if d.role is DocumentRole.UNDER_REVIEW]
    text = under[0].sha256_text if under else ""
    return PinnedHashes(effective_config=ctx.config.sha256(), prompts_bundle=ctx.prompts.bundle_sha256,
                        canonical_text=text)


def resume_start(ckpt: Checkpoint) -> PhaseName | None:
    """Where a resume continues after ``ckpt`` (the latest checkpoint): stage 1 again (its ended
    members are not re-run) while the stage has not closed, which is written as the ``assess``
    checkpoint; else the phase after the checkpoint's."""
    if ckpt.phase in STAGE_1 and ckpt.phase is not PhaseName.ASSESS:
        return PhaseName.UNDERSTAND
    if ckpt.phase is PhaseName.INGEST:
        return PhaseName.UNDERSTAND
    nxt = STAGE_TRANSITIONS[stage_of(ckpt.phase)]
    return STAGE_MEMBERS[nxt][0] if nxt is not None else None


def _deadline_active(ctx: RunContext) -> bool:
    return "deadline" in ctx.config.stop_rules.active


class Orchestrator:
    #: Seconds past ``stage_limits_s.stage_1_end`` after which stage 1 members still running are
    #: stopped here. A backstop only: the runtime cuts their model calls at the limit itself, and a
    #: member then ends with what it salvaged; this catches what is not a model call (a hung tool).
    stage1_grace_s: float = 30.0
    #: How often (wall seconds) stage 1 checks the run clock against that limit while members run.
    stage1_poll_s: float = 1.0

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
        ctx.state.budget.elapsed_s = round(max(0.0, ctx.elapsed_s()), 3)
        ckpt = Checkpoint(run_id=ctx.state.run_id, phase=phase, seq=PHASE_ORDER.index(phase) + 1,
                          created_utc=isoformat_z(ctx.clock.now_utc()), hashes=pinned_hashes(ctx),
                          offsets=journal_offsets(ctx.run_dir), state=ctx.state)
        return write_checkpoint(ctx.run_dir, ckpt)

    def _flush_state(self, ctx: RunContext) -> None:
        ctx.sync_state()
        write_json_atomic(ctx.run_dir.state, ctx.state.model_dump(mode="json"))

    async def run(self, ctx: RunContext, *, start_at: PhaseName = PhaseName.INGEST) -> RunContext:
        """Run from ``start_at`` (``INGEST`` for a new run; on resume, :func:`resume_start`) to
        ``REPORT``, or to the end of ``PLAN`` when ``ctx.plan_only``."""
        if not ctx.state.completed_phases and ctx.state.budget.started_monotonic == 0.0:
            ctx.state.budget.started_monotonic = ctx.clock.monotonic()
        stage: Stage | None = stage_of(start_at)
        while stage is not None:
            if stage is Stage.STAGE_1:
                stage = await self._stage_1(ctx)
            else:
                stage = await self._single(ctx, STAGE_MEMBERS[stage][0])
        ctx.state.current_phase = None
        return ctx

    # ------------------------------------------------------------------ caps

    def _cap(self, ctx: RunContext, stage: Stage) -> StopReason | None:
        """A cap that stops ``stage`` from starting: the active between-phase caps, or (with the
        ``deadline`` rule active) the stage's own limit already passed."""
        cap = check_caps(ctx.state, ctx.config.stop_rules, ctx.elapsed_s())
        if cap is not None or not _deadline_active(ctx):
            return cap
        limits = ctx.config.stop_rules.stage_limits_s
        limit = {Stage.STAGE_1: ("stage_1_end", limits.stage_1_end),
                 Stage.REFINE: ("refine_end", limits.refine_end)}.get(stage)
        if limit is not None and ctx.elapsed_s() >= limit[1]:
            return StopReason.of(StopReasonCode.DEADLINE, f"stage_limits_s.{limit[0]}")
        return None

    def _skip_on_cap(self, ctx: RunContext, stage: Stage, cap: StopReason) -> Stage:
        if ctx.state.stop_reason is None:
            ctx.state.stop_reason = cap
        target = STAGE_ON_CAP[stage]
        name = "stage 1" if stage is Stage.STAGE_1 else stage.value
        # Disclosed on every skip, also when research already set the stop reason (a deadline that
        # skips refine must not be hidden; INV-07, robustness LLM-05).
        if stage is Stage.STAGE_1:
            from sit_review_agent.llm.runtime import OUT_OF_TIME_BEFORE_ASSESSMENT

            ctx.state.add_degradation(
                DegradationType.BUDGET_OR_DEADLINE_HIT,
                f"{OUT_OF_TIME_BEFORE_ASSESSMENT}: stop rule {cap.detail} ({cap.code}) fired before stage 1 (assess)",
                "the design was not assessed: the report has no findings and its verdict is not a judgement of the "
                "design; rerun with a longer deadline")
        else:
            from sit_review_agent.phases._model_calls import REFINE_FALLBACK_IMPACT

            ctx.state.add_degradation(DegradationType.BUDGET_OR_DEADLINE_HIT,
                                      f"stop rule {cap.detail} ({cap.code}) before {name}",
                                      f"skipped to {target.value}; {REFINE_FALLBACK_IMPACT}")
        ctx.progress.emit(STAGE_MEMBERS[stage][0].value, f"stop rule {cap.code} fired; skipping to {target.value}",
                          "warn")
        return target

    # ------------------------------------------------------------------ one-phase stages

    async def _single(self, ctx: RunContext, phase: PhaseName) -> Stage | None:
        stage = stage_of(phase)
        nxt = STAGE_TRANSITIONS[stage]
        if not ctx.config.agent.phases.enabled(phase):
            ctx.progress.emit(phase.value, "skipped (disabled in config/agent.yaml)")
            return nxt
        if stage in STAGE_ON_CAP:
            cap = self._cap(ctx, stage)
            if cap is not None:
                return self._skip_on_cap(ctx, stage, cap)
        ctx.state.current_phase = phase
        ctx.progress.emit(phase.value, "started")
        t0 = ctx.clock.monotonic()
        try:
            out = await self.phases[phase].run(ctx)
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
        if out is not ctx:                      # a phase may return another context object; keep its state
            ctx.state = out.state
        self._ended(ctx, phase, round(ctx.clock.monotonic() - t0, 3))
        return nxt

    def _ended(self, ctx: RunContext, phase: PhaseName, seconds: float, note: str = "") -> None:
        ctx.state.budget.phase_seconds[phase.value] = seconds
        if phase not in ctx.state.completed_phases:
            ctx.state.completed_phases.append(phase)
        self.checkpoint(ctx, phase)
        ctx.progress.emit(phase.value, f"done in {ctx.state.budget.phase_seconds[phase.value]:.1f}s{note}", "done")
        if not note:                            # a member stopped at the stage 1 limit reaches no milestone
            self._milestone(ctx, phase)

    @staticmethod
    def _milestone(ctx: RunContext, phase: PhaseName) -> None:
        """The stage milestones of ``progress.MILESTONES`` that end with ``phase`` (the merged list is
        announced by :meth:`_close`)."""
        if phase is PhaseName.UNDERSTAND:
            milestone(ctx.progress, "intent", phase.value, registry_entries=len(ctx.registry.entries()))
        elif phase is PhaseName.PLAN and ctx.state.plan is not None:
            milestone(ctx.progress, "plan", phase.value, questions=len(ctx.state.plan.questions))
        elif phase is PhaseName.REPORT and ctx.run_dir.report_json.is_file():
            milestone(ctx.progress, "verified", phase.value, findings=len(ctx.state.findings))

    # ------------------------------------------------------------------ stage 1

    def _member_phase(self, p: PhaseName) -> Phase:
        return self.phases[p]

    def _sharded(self) -> bool:
        a = self.phases[PhaseName.ASSESS]
        return callable(getattr(a, "run_shards", None)) and callable(getattr(a, "merge", None))

    async def _stage_1(self, ctx: RunContext) -> Stage | None:
        """Stage 1 (module docstring). Returns the next stage: refine, verify after a cap, or
        ``None`` when the run stops after the plan (``--plan-only`` or a plan not approved)."""
        from sit_review_agent.phases._isolation import Isolated, guarded, isolate, merge_member

        done_before = set(ctx.state.completed_phases)
        ended: dict[PhaseName, MemberOutcome] = {p: "done" for p in STAGE_1 if p in done_before}
        sharded = self._sharded()
        shard_results: dict[int, Any] = self._load_shards(ctx) if sharded else {}
        cap = self._cap(ctx, Stage.STAGE_1)
        if cap is not None:
            if not shard_results:
                return self._skip_on_cap(ctx, Stage.STAGE_1, cap)
            if ctx.state.stop_reason is None:           # resumed after the limit with finished shards:
                ctx.state.stop_reason = cap             # merge what finished, start nothing new
            ctx.progress.emit("stage_1", f"stop rule {cap.code} fired; merging the finished shards only", "warn")
            self._close(ctx, sharded, shard_results, ended, fired=True)
            return STAGE_ON_CAP[Stage.STAGE_1]
        for p in STAGE_1:
            if p not in ended and not ctx.config.agent.phases.enabled(p):
                ended[p] = "done"
                ctx.progress.emit(p.value, "skipped (disabled in config/agent.yaml)")

        running: dict[asyncio.Task[Any], PhaseName] = {}
        isos: dict[PhaseName, Isolated] = {}
        t0: dict[PhaseName, float] = {}
        t1: dict[PhaseName, float] = {}
        fired = False

        async def timed(p: PhaseName, coro: Any) -> Any:
            try:
                return await guarded(coro)
            finally:
                t1[p] = ctx.clock.monotonic()           # when the member ended, not when it is merged

        def store(result: Any) -> None:
            shard_results[result.index] = result
            self._store_shard(ctx, result)

        def start(p: PhaseName) -> None:
            iso = isolate(ctx, p)
            isos[p], t0[p] = iso, ctx.clock.monotonic()
            phase = self._member_phase(p)
            if p is PhaseName.ASSESS and sharded:
                coro = phase.run_shards(iso.ctx, done=dict(shard_results), on_end=store)  # type: ignore[attr-defined]
            else:
                coro = phase.run(iso.ctx)
            ctx.progress.emit(p.value, "started")
            running[asyncio.create_task(timed(p, coro), name=f"stage1-{p.value}")] = p

        def may_start(p: PhaseName) -> bool:
            return not (ctx.plan_only and p in (PhaseName.RESEARCH, PhaseName.ASSESS))

        try:
            while True:
                if not fired:
                    ready = stage1_ready(ended, running.values())
                    for p in STAGE_1:
                        if p in ready and may_start(p):
                            start(p)
                if not running:
                    break
                watch = not fired and _deadline_active(ctx)
                finished, _ = await asyncio.wait(set(running), timeout=self.stage1_poll_s if watch else None,
                                                 return_when=asyncio.FIRST_COMPLETED)
                if not finished:
                    limit = ctx.config.stop_rules.stage_limits_s.stage_1_end
                    if ctx.elapsed_s() < limit + self.stage1_grace_s:
                        continue
                    fired = True
                    names = ", ".join(sorted(p.value for p in running.values()))
                    ctx.progress.emit("stage_1", f"stage 1 limit passed by {self.stage1_grace_s:.0f} s; stopping "
                                      f"{names}", "warn")
                    for t in running:
                        t.cancel()
                    continue
                for task in sorted(finished, key=lambda t: STAGE_1.index(running[t])):
                    p = running.pop(task)
                    self._member_end(ctx, p, task, isos[p], t0[p], t1.get(p), ended, sharded, shard_results,
                                     merge_member)
        except BaseException as exc:
            for t in running:
                t.cancel()
            await asyncio.gather(*running, return_exceptions=True)
            if isinstance(exc, AgentError | _StageFailure):
                raise exc.error if isinstance(exc, _StageFailure) else exc from None
            self._flush_state(ctx)
            ctx.progress.emit("stage_1", "interrupted; state flushed (resume re-runs the unfinished members)", "warn")
            raise RunInterrupted("interrupted during stage 1") from exc
        if ctx.plan_only:
            if PhaseName.PLAN in ended:
                ctx.progress.emit(PhaseName.PLAN.value, "--plan-only: stopping after the plan (zero tool calls)")
            return None
        if fired:
            outcomes = stage1_close(ended, [])
            for p, how in outcomes.items():
                if how == "skipped" and p not in ended and ctx.config.agent.phases.enabled(p):
                    self._member_skipped(ctx, p)
        self._close(ctx, sharded, shard_results, ended, fired=fired)
        return STAGE_TRANSITIONS[Stage.STAGE_1]

    def _member_end(self, ctx: RunContext, p: PhaseName, task: asyncio.Task[Any], iso: Any, t0: float,
                    t1: float | None, ended: dict[PhaseName, MemberOutcome], sharded: bool,
                    shard_results: dict[int, Any], merge_member: Any) -> None:
        seconds = round((t1 if t1 is not None else ctx.clock.monotonic()) - t0, 3)
        if task.cancelled():                    # only the stage 1 backstop cancels a member
            self._member_cut(ctx, p, iso, merge_member)
            ended[p] = "cut"
            if p is not PhaseName.ASSESS:
                self._ended(ctx, p, seconds, " (stopped at the stage 1 limit)")
            return
        exc = task.exception()
        if exc is not None:
            ctx.state.current_phase = p
            self._flush_state(ctx)
            from sit_review_agent.phases._isolation import MemberInterrupted

            if isinstance(exc, MemberInterrupted):
                ctx.progress.emit(p.value, "interrupted; state flushed (resume re-runs the unfinished members)",
                                  "warn")
                raise _StageFailure(RunInterrupted(f"interrupted during {p.value}"))
            if isinstance(exc, asyncio.CancelledError):
                raise _StageFailure(RunInterrupted(f"interrupted during {p.value}"))
            if isinstance(exc, AgentError):
                raise _StageFailure(exc)
            raise _StageFailure(StageCrash(p.value, exc))
        ended[p] = "done"
        if p is PhaseName.ASSESS and sharded:
            for r in task.result():
                shard_results[r.index] = r
            ctx.state.budget.phase_seconds[p.value] = seconds
            ctx.progress.emit(p.value, f"{len(shard_results)} shard(s) ended in "
                              f"{ctx.state.budget.phase_seconds[p.value]:.1f}s; merged when stage 1 closes")
            return
        merge_member(ctx, iso)
        if p is PhaseName.ASSESS:               # a phase without shards: merged now, checkpointed at the close
            ctx.state.budget.phase_seconds[p.value] = seconds
            return
        self._ended(ctx, p, seconds)

    def _member_cut(self, ctx: RunContext, p: PhaseName, iso: Any, merge_member: Any) -> None:
        """A member the stage 1 backstop stopped: its code fallback, disclosed."""
        what = f"{p.value} was still running {self.stage1_grace_s:.0f} s after the stage 1 limit and was stopped"
        if p is PhaseName.UNDERSTAND:
            if not ctx.registry.frozen:
                ctx.registry.freeze()
            if not ctx.registry.hashes():
                ctx.registry.record_iteration(0)
            impact = "the review has no design-intent summary or decision registry from the model"
        elif p is PhaseName.PLAN:
            from sit_review_agent.phases.plan import build_plan

            ctx.state.plan = build_plan(ctx, None, missing="deadline")[0]
            impact = "the plan is one document-only question per criterion"
        elif p is PhaseName.RESEARCH:
            merge_member(ctx, iso)              # what research recorded before it was stopped
            if ctx.state.stop_reason is None:
                ctx.state.stop_reason = StopReason.of(StopReasonCode.DEADLINE, "stage_limits_s.stage_1_end")
            impact = "research ended early; the evidence register keeps what it had gathered"
        else:
            impact = "assess shards that had not ended were cut with nothing salvaged; their criteria are not assessed"
        ctx.state.add_degradation(DegradationType.BUDGET_OR_DEADLINE_HIT, what, impact)

    def _member_skipped(self, ctx: RunContext, p: PhaseName) -> None:
        if p is PhaseName.RESEARCH and ctx.state.stop_reason is None:
            ctx.state.stop_reason = StopReason.of(StopReasonCode.DEADLINE, "stage_limits_s.stage_1_end")
        ctx.state.add_degradation(DegradationType.BUDGET_OR_DEADLINE_HIT,
                                  f"{p.value} did not start before the stage 1 limit",
                                  "no external evidence was gathered; external claims stay unverified"
                                  if p is PhaseName.RESEARCH else f"the {p.value} step did not run")

    def _close(self, ctx: RunContext, sharded: bool, shard_results: dict[int, Any],
               ended: Mapping[PhaseName, MemberOutcome], *, fired: bool) -> None:
        """Merge the assess shards in shard order and write the stage's closing checkpoint."""
        p = PhaseName.ASSESS
        assess = self.phases[p]
        if sharded:
            if not shard_results and p not in ended:
                return
            plan = assess.shards(ctx)  # type: ignore[attr-defined]
            results = [shard_results.get(i) or _cut_shard(ctx, i, s, len(plan)) for i, s in enumerate(plan, start=1)]
            ctx.state.current_phase = p
            t0 = ctx.clock.monotonic()
            spent = ctx.state.budget.phase_seconds.get(p.value, 0.0)
            assess.merge(ctx, results)  # type: ignore[attr-defined]
            ctx.state.budget.phase_seconds[p.value] = spent
            if p not in ctx.state.completed_phases:
                ctx.state.completed_phases.append(p)
            self.checkpoint(ctx, p)
            # the member's done line (robustness OPS-10: every completed phase has started and done)
            ctx.progress.emit(p.value, f"done in {spent:.1f}s; stage 1 closed, merged in "
                              f"{ctx.clock.monotonic() - t0:.1f}s", "done")
            milestone(ctx.progress, "merged", PhaseName.REFINE.value, findings=len(ctx.state.finding_drafts),
                      shards=len(results))
        elif p in ended:
            if p not in ctx.state.completed_phases:
                ctx.state.completed_phases.append(p)
            self.checkpoint(ctx, p)
            ctx.progress.emit(p.value, f"done in {ctx.state.budget.phase_seconds.get(p.value, 0.0):.1f}s; stage 1 "
                              "closed", "done")

    # ------------------------------------------------------------------ finished shards on disk

    def _shard_dir(self, ctx: RunContext) -> Path:
        return ctx.run_dir.root / SHARDS_DIR

    def _store_shard(self, ctx: RunContext, result: Any) -> None:
        d = self._shard_dir(ctx)
        d.mkdir(parents=True, exist_ok=True)
        write_json_atomic(d / f"{result.index:02d}-{result.name}.json",
                          {"hashes": pinned_hashes(ctx).model_dump(mode="json"),
                           "result": result.model_dump(mode="json")})

    def _load_shards(self, ctx: RunContext) -> dict[int, Any]:
        """Finished shards of this run that resume may keep: same pinned hashes (config, prompts,
        text) and the same shard plan; anything else is re-run."""
        import json as _json

        from sit_review_agent.phases.assess import ShardResult

        d = self._shard_dir(ctx)
        if PhaseName.ASSESS in ctx.state.completed_phases or not d.is_dir():
            return {}
        plan = self.phases[PhaseName.ASSESS].shards(ctx)  # type: ignore[attr-defined]
        pinned = pinned_hashes(ctx).model_dump(mode="json")
        out: dict[int, Any] = {}
        for f in sorted(d.glob("*.json")):
            try:
                data = _json.loads(f.read_text(encoding="utf-8"))
                r = ShardResult.model_validate(data["result"])
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if data.get("hashes") != pinned or not 1 <= r.index <= len(plan):
                continue
            s = plan[r.index - 1]
            if s.name == r.name and list(s.criteria) == r.criteria:
                out[r.index] = r
        if out:
            ctx.progress.emit(PhaseName.ASSESS.value, f"{len(out)} finished shard(s) kept from before the "
                              "interruption: " + ", ".join(str(i) for i in sorted(out)))
        return out


class _StageFailure(Exception):
    """Carries the typed error of a failed stage 1 member out of the task loop (the other members
    are stopped first)."""

    def __init__(self, error: AgentError) -> None:
        super().__init__(str(error))
        self.error = error


def _cut_shard(ctx: RunContext, index: int, shard: Any, count: int) -> Any:
    """The result of a shard that had not ended when stage 1 closed: cut with nothing salvaged."""
    from sit_review_agent.phases._isolation import StateDelta
    from sit_review_agent.phases.assess import ShardResult, _not_assessed_impact
    from sit_review_agent.state.run_state import RunState

    probe = RunState(run_id="cut", created_utc=ctx.state.created_utc)
    d = probe.add_degradation(DegradationType.BUDGET_OR_DEADLINE_HIT,
                              f"assess shard {index}/{count} ({shard.name}) had not ended when stage 1 closed; "
                              "nothing was salvaged", _not_assessed_impact(shard.criteria))
    return ShardResult(index=index, name=shard.name, criteria=list(shard.criteria), outcome="cut",
                       iteration=ctx.state.budget.research_iterations, delta=StateDelta(degradations=[d]))


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
    k_index: int | None = None            # 1..k within a k-run group; recorded as manifest extra.k_index


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
    _run_check_tool_key(cfg)                                        # robustness INF-08: before any model call
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
                     k_index=request.k_index, documents=refs)
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

        # The no-retry preflight first (robustness NET-02: offline at start fails fast), then
        # models.retrieve (which retries) only when the backend answered.
        failed = await _run_llm_preflight(ctx)
        retrieved = (await _run_models_retrieve(ctx) if failed is None
                     else {"status": "not retrieved (LLM preflight failed)"})
        start_manifest(ctx, models_retrieve=retrieved)
        _run_attach_runtime(ctx, retrieved)
        ctx.emit(f"run {run_id}: {rd.root}")
    except BaseException as exc:  # noqa: BLE001 - recorded in failure.json (INV-02), re-raised typed
        err = await _run_setup_failed(rd, run_id, ctx, warm, exc)
        if err is exc:
            raise
        raise err from exc
    if failed is not None:
        await _run_stop_warmup(warm)
        await _run_close_tools(ctx)
        return _run_fail(ctx, failed)
    return await _run_execute(ctx, _run_process_faults(ctx, sched, phases), PhaseName.INGEST, stdin, stdout, warm)


async def resume_run(run_dir: Path, config: EffectiveConfig, *, accept_drift: bool = False,
                     phases: Mapping[PhaseName, Phase] | None = None, llm_factory: object = None,
                     tools_factory: object = None, clock: object = None, progress: object = None,
                     stdin: object = None, stdout: object = None) -> RunOutcome:
    """ADR-009 resume: latest checkpoint, drift check, ledger journal truncation, SelfReplayGateway,
    then :meth:`Orchestrator.run` from :func:`resume_start` (inside stage 1, only the members and
    assess shards that had not finished run again), with the run clock restored from the
    checkpoint's ``budget.elapsed_s``.

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
    from sit_review_agent.state.checkpoint import check_drift, latest_checkpoint, truncate_journal
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
                         k_index=old.k_index, documents=old.documents)
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
        start_at = resume_start(ckpt)
        deviations.append(f"resumed after phase {ckpt.phase.value} (checkpoint {ckpt.created_utc})")
    # Stage 1 members overlap, so their seconds do not sum to the run's: the clock resumes from the
    # elapsed seconds recorded at the checkpoint (a state written before 2026-10-03: the sum).
    spent = state.budget.elapsed_for_resume()
    state.budget.started_monotonic = clk.monotonic() - spent        # type: ignore[attr-defined]
    state.current_phase = None
    prog = progress or _run_console_progress(clk, rd)
    sched = _run_fault_schedule(config)
    if start_at is not None:
        _run_check_tool_key(config)                                 # robustness INF-08
    ctx: RunContext | None = None
    warm: asyncio.Task[None] | None = None
    try:
        from sit_review_agent.llm.gateway import prepare_resume

        llm = _run_build_llm(config, rd, clk, prog, sched, llm_factory)
        # New LLM call IDs continue after the logged ones; calls of the stage being re-run are
        # logged ``resumed: true`` (ADR-009 item 2).
        reruns = _run_rerun_phases(rd, ckpt, start_at, state)
        for rerun in reruns or [None]:
            prepare_resume(llm, last_call_number=_run_max_id(rd.llm_log, "llm-"), resumed_phase=rerun)
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
        _run_attach_runtime(ctx, None)
        if sched is not None and getattr(sched, "process", None):
            ctx.emit("fault schedule: process faults are not re-applied on resume (the interruption is over)")
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


def _run_check_tool_key(cfg: EffectiveConfig) -> None:
    """Robustness INF-08: with live MCP servers enabled and their key unset, stop before any model
    call with a usage error (exit 2) that says what to do. Replayed or fake tool transports need no
    key, and a key revoked during the run keeps the doc-only degradation (runbook §6)."""
    import os

    from sit_review_agent.config import Transport
    from sit_review_agent.errors import ConfigError

    if cfg.agent.transport not in (Transport.LIVE, Transport.RECORD):
        return
    servers = [s.name for s in cfg.tools.enabled_servers()]
    if servers and not (os.environ.get(cfg.tools.auth_env) or "").strip():
        raise ConfigError(f"{cfg.tools.auth_env} is not set, and the enabled MCP tool servers ({', '.join(servers)}) "
                          f"need it. Set it (export {cfg.tools.auth_env}=<key>; the value is never logged), or pass "
                          "--no-tools for a document-only review. No model call was made")


def _run_attach_runtime(ctx: RunContext, retrieved: Mapping[str, object] | None) -> None:
    """One set of run limits for every layer of the LLM stack (``llm.runtime``): the deadline read
    from this run's clock (resume-adjusted ``budget.started_monotonic``), the pre-send size check
    against the model's context window (``models.retrieve`` when the backend gave one)."""
    from sit_review_agent.llm.runtime import attach_runtime, build_runtime, deadline_warnings

    state, clk = ctx.state, ctx.clock
    for warning in deadline_warnings(ctx.config.stop_rules):
        ctx.emit(warning, "warn")

    def elapsed() -> float:
        return clk.monotonic() - state.budget.started_monotonic

    def pages() -> int:
        return sum(d.page_count or 0 for d in state.documents)

    window = (retrieved or {}).get("max_input_tokens")
    attach_runtime(ctx.llm, build_runtime(ctx.config, elapsed, retrieved_window=window, pages=pages))


class _run_ProcessFault:  # private helper: `_run_` prefix by workstream rule
    """A ``process:`` entry of the run's fault schedule (research/robustness/README.md §5.3) around
    one phase: ``raise_in_stage`` (BEH-25: an exception, exit 4 with a partial report),
    ``sigint_in_stage`` (OPS-04: Ctrl-C, exit 130) and ``clock_jump`` (NET-03: the run clock jumps
    ``seconds`` forward before the phase). ``at: end`` (the default) fires after the phase's work and
    before its checkpoint, so a resume re-runs the stage (its tool calls served from
    ``tools.jsonl``); ``at: start`` fires before the phase does anything. Applied once, on a new
    run only: ``resume`` never re-applies it."""

    def __init__(self, inner: Phase, spec: object) -> None:
        self.inner = inner
        self.name = inner.name
        self.spec = spec
        if callable(getattr(inner, "run_shards", None)):            # assess: the fault wraps all its shards
            self.run_shards = self._run_shards
            self.merge = inner.merge  # type: ignore[attr-defined]
            self.shards = inner.shards  # type: ignore[attr-defined]

    async def run(self, ctx: RunContext) -> RunContext:
        return await self._around(ctx, lambda: self.inner.run(ctx))

    async def _run_shards(self, ctx: RunContext, **kw: Any) -> Any:
        return await self._around(ctx, lambda: self.inner.run_shards(ctx, **kw))  # type: ignore[attr-defined]

    async def _around(self, ctx: RunContext, work: Any) -> Any:
        from sit_review_agent.tools.faults import FaultType

        extra = getattr(self.spec, "model_extra", None) or {}
        kind = self.spec.type  # type: ignore[attr-defined]
        if kind is FaultType.CLOCK_JUMP:
            seconds = float(extra.get("seconds", 600))
            advance = getattr(ctx.clock, "advance", None)
            if callable(advance):
                advance(seconds)                                    # a virtual clock: everything sees the jump
            else:
                ctx.state.budget.started_monotonic -= seconds       # the run clock jumps forward
            ctx.emit(f"injected fault: clock jump of {seconds:g} s before {self.name.value}", "warn")
            return await work()
        out = None
        if str(extra.get("at", "end")) == "end":
            out = await work()
        ctx.emit(f"injected fault: {kind.value} in {self.name.value}", "warn")
        if kind is FaultType.SIGINT_IN_STAGE:
            raise KeyboardInterrupt
        del out
        raise RuntimeError(f"injected fault: raise_in_stage {self.name.value}")


def _run_process_faults(ctx: RunContext, sched: object,
                        phases: Mapping[PhaseName, Phase] | None) -> Mapping[PhaseName, Phase] | None:
    """Wrap the phases named by the schedule's ``process:`` entries (so ``sit-review run --faults
    BEH-25`` / ``OPS-04`` drill the crash and Ctrl-C paths of runbook §7). An entry without a valid
    ``stage`` is a ConfigError at load time (``tools.faults``)."""
    specs = list(getattr(sched, "process", None) or [])
    if not specs:
        return phases
    from sit_review_agent.phases import default_phases

    out: dict[PhaseName, Phase] = dict(phases) if phases is not None else default_phases()
    for spec in specs:
        stage = PhaseName(str((spec.model_extra or {}).get("stage")))
        out[stage] = _run_ProcessFault(out[stage], spec)
        at = (spec.model_extra or {}).get("at", "end")
        ctx.emit(f"fault schedule {getattr(sched, 'id', '?')}: {spec.type.value} armed "
                 f"({'before' if spec.type.value == 'clock_jump' else f'at the {at} of'} {stage.value})", "warn")
    return out


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


def _run_rerun_phases(rd: RunDir, ckpt: object, start_at: PhaseName | None, state: object) -> list[PhaseName]:
    """The phases a resume re-runs that had already made model calls after the checkpoint (their
    re-issued calls are logged ``resumed: true``, ADR-009 item 2): ``start_at``, or in stage 1
    every member that had not ended."""
    from sit_review_agent.rundir import JsonlWriter

    if start_at is None:
        return []
    upto = ckpt.offsets.llm_jsonl if ckpt is not None else 0  # type: ignore[attr-defined]
    log = JsonlWriter(rd.llm_log)
    after = {e.get("phase") for e in log.read()[len(log.read(upto)):]}
    done = set(getattr(state, "completed_phases", []))
    candidates = [p for p in STAGE_1 if p not in done] if start_at in STAGE_1 else [start_at]
    return [p for p in candidates if p.value in after]


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
    if code is ExitCode.STAGE_CRASH:
        try:                                    # ADR-009 item 5, robustness BEH-25: a partial report
            record["partial_report"] = _run_partial_report(ctx, phase, cause).name
        except OSError:
            pass
    try:
        write_json_atomic(rd.failure, record)
    except OSError:
        pass
    outcome = Outcome.CRASHED if code is ExitCode.STAGE_CRASH else Outcome.ABORTED_GRACEFUL
    lower: str | None = None
    try:
        from sit_review_agent.llm.usage_budget import cost_lower_bound_line

        lower = cost_lower_bound_line(finalise_manifest(ctx, outcome).model_dump(mode="json"))
    except Exception:  # noqa: BLE001 - the failure record above is what matters
        pass
    if lower is not None:
        ctx.progress.emit(phase or "run", lower, "warn")
    ctx.progress.emit(phase or "run", f"error ({type(exc).__name__}, exit {int(code)}): {str(exc)[:300]}; "
                      f"state saved; resume with `sit-review resume {rd.root}`", "warn")
    return RunOutcome(run_dir=rd.root, exit_code=int(code), report_md=None)


def _run_partial_report(ctx: RunContext, phase: str | None, cause: object) -> Path:
    """``report.partial.md`` after a stage crash (ADR-009 item 5, robustness BEH-25): the completed
    stages, what the run had gathered and how to resume. Never a review: no finding is printed, since
    none has passed verify (ADR-007), and the error is named by class only (details in failure.json)."""
    s, rd = ctx.state, ctx.run_dir
    done = ", ".join(p.value for p in s.completed_phases) or "none"
    lines = ["# Partial run record (not a review)", "",
             f"The run stopped because the `{phase or 'run'}` stage crashed "
             f"({type(cause).__name__ if cause is not None else 'StageCrash'}; exit 4). Nothing below is a "
             "finding: no draft has been verified against the document, so none is reported.", "",
             f"- Run: `{s.run_id}`",
             f"- Document: {(s.documents[0].title if s.documents else '') or 'unknown'}",
             f"- Completed stages: {done}",
             f"- Crashed stage: {phase or 'run'}",
             f"- Research questions planned: {len(s.plan.questions) if s.plan is not None else 0}",
             f"- Evidence register entries: {len(ctx.ledger)}",
             f"- Draft findings (unverified, not reported): {len(s.finding_drafts)}",
             f"- Resume: `sit-review resume {rd.root}` (continues after the last completed stage)",
             "- Details: `failure.json`, `state.json`, `checkpoints/`"]
    if s.degradations:
        lines += ["", "## Events before the crash", "", *[f"- {d.event}" for d in s.degradations]]
    path = rd.root / "report.partial.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def open_run_dir(config: EffectiveConfig, run_id: str) -> RunDir:
    return RunDir(config.resolve_repo_path(config.agent.run_root) / run_id).create()
