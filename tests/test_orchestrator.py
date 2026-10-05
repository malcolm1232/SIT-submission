"""The state machine loop and stop rules, with fake phases (no model, no tools).

Stage 1 (latency redesign, design section 4): understand, plan and assess start together, research
waits for understand and plan, every member checkpoints when it ends, and the stage closes with the
assess checkpoint. Members here end in launch order unless a test gates them.
"""

from __future__ import annotations

import asyncio
import itertools
from pathlib import Path
from typing import Any

import pytest

from sit_review_agent import stop_rules
from sit_review_agent.clock import FakeClock, isoformat_z
from sit_review_agent.config import ConfigOverrides, load_config
from sit_review_agent.context import RunContext
from sit_review_agent.errors import StageCrash
from sit_review_agent.llm.gateway import FakeGateway
from sit_review_agent.models import DegradationType, StopReasonCode
from sit_review_agent.orchestrator import Orchestrator
from sit_review_agent.progress import NullProgress
from sit_review_agent.prompts import PromptBundle
from sit_review_agent.rundir import RunDir
from sit_review_agent.state.checkpoint import latest_checkpoint, load_checkpoint
from sit_review_agent.state.decision_registry import DecisionRegistry
from sit_review_agent.state.evidence_ledger import EvidenceLedger
from sit_review_agent.state.run_state import RunState
from sit_review_agent.states import PHASE_ORDER, PhaseName

#: The order a run without gates logs its phases: stage 1 launches understand, plan and assess
#: together; research starts once understand and plan have ended.
RUN_ORDER = ["ingest", "understand", "plan", "assess", "research", "refine", "verify", "report"]


class Recorder:
    def __init__(self, name: PhaseName, log: list[str], *, clock: FakeClock | None = None, advance: float = 0.0,
                 fail: bool = False) -> None:
        self.name, self.log, self.clock, self.advance, self.fail = name, log, clock, advance, fail

    async def run(self, ctx: RunContext) -> RunContext:
        self.log.append(self.name.value)
        if self.clock is not None:
            self.clock.advance(self.advance)
        if self.fail:
            raise RuntimeError("boom")
        return ctx


def make_ctx(tmp_path: Path, clock: FakeClock, **overrides: object) -> RunContext:
    cfg = load_config(overrides=ConfigOverrides(**overrides)) if overrides else load_config()
    rd = RunDir(tmp_path / "run-1").create()
    progress = NullProgress()
    return RunContext(config=cfg, run_dir=rd, state=RunState(run_id="run-1", created_utc=isoformat_z(clock.now_utc())),
                      llm=FakeGateway({}), tools=None, ledger=EvidenceLedger(rd, clock=clock),
                      registry=DecisionRegistry(), prompts=PromptBundle.load(), clock=clock, progress=progress)


def phases(log: list[str], **kw: Recorder) -> dict[PhaseName, Recorder]:
    out = {p: Recorder(p, log) for p in PHASE_ORDER}
    out.update({PhaseName(k): v for k, v in kw.items()})
    return out


async def test_runs_all_phases_in_order_and_checkpoints(tmp_path: Path) -> None:
    clock, log = FakeClock(), []
    ctx = await Orchestrator(phases(log)).run(make_ctx(tmp_path, clock))
    assert log == RUN_ORDER
    assert set(ctx.state.completed_phases) == set(PHASE_ORDER) and ctx.state.completed_phases[-1] is PhaseName.REPORT
    files = sorted(p.name for p in ctx.run_dir.checkpoints.iterdir())
    assert files == [f"{i + 1:02d}-{p.value}.json" for i, p in enumerate(PHASE_ORDER)]
    ckpt = latest_checkpoint(ctx.run_dir)
    assert ckpt is not None and ckpt.phase is PhaseName.REPORT and ckpt.hashes.effective_config == ctx.config.sha256()
    by_ordinal = sorted((load_checkpoint(f) for f in ctx.run_dir.checkpoints.iterdir()), key=lambda c: c.ordinal)
    # Stage 1 closes with the assess checkpoint, after research (the merge runs when the stage ends).
    assert [c.phase.value for c in by_ordinal] == ["ingest", "understand", "plan", "research", "assess", "refine",
                                                    "verify", "report"]
    assert ctx.run_dir.state.exists()
    assert any("started" in e.message for e in ctx.progress.events)        # progress line per step


async def test_plan_only_stops_after_plan(tmp_path: Path) -> None:
    clock, log = FakeClock(), []
    ctx = make_ctx(tmp_path, clock)
    ctx.plan_only = True
    await Orchestrator(phases(log)).run(ctx)
    assert log == ["ingest", "understand", "plan"]


async def test_deadline_cap_skips_to_verify_and_is_disclosed(tmp_path: Path) -> None:
    clock, log = FakeClock(), []
    ctx = make_ctx(tmp_path, clock, deadline_seconds=100)
    slow = Recorder(PhaseName.INGEST, log, clock=clock, advance=95)
    await Orchestrator(phases(log, ingest=slow)).run(ctx)
    assert log == ["ingest", "verify", "report"]
    assert ctx.state.stop_reason is not None and ctx.state.stop_reason.code is StopReasonCode.DEADLINE
    [d] = ctx.state.degradations
    assert d.type.value == "budget_or_deadline_hit" and d.event.startswith("out of time before assessment")


async def test_cap_before_refine_skips_it_and_is_disclosed(tmp_path: Path) -> None:
    clock, log = FakeClock(), []
    # --deadline 1000 scales the default's limits and reserves by 1000/3600 (USER_DECISIONS #48): refine ends by
    # 950 s and the deadline rule fires at 1000 - 50 s, so a research that runs to 960 s leaves refine no start.
    ctx = make_ctx(tmp_path, clock, deadline_seconds=1000)
    assert ctx.config.stop_rules.stage_limits_s.refine_end == 950 and ctx.config.stop_rules.report_reserve_seconds == 50
    slow = Recorder(PhaseName.RESEARCH, log, clock=clock, advance=960)
    await Orchestrator(phases(log, research=slow)).run(ctx)
    assert log == ["ingest", "understand", "plan", "assess", "research", "verify", "report"]
    [d] = ctx.state.degradations
    assert d.event.startswith("stop rule") and "before refine" in d.event and "severity and confidence" in d.impact


@pytest.mark.parametrize(("limit", "skipped"), [("stage_1_end", "stage 1"), ("refine_end", "refine")])
async def test_a_passed_stage_limit_skips_the_stage(tmp_path: Path, limit: str, skipped: str) -> None:
    """stop_rules.stage_limits_s: a stage whose limit has passed does not start (deadline rule active)."""
    from sit_review_agent.config import StageLimits

    clock, log = FakeClock(), []
    ctx = make_ctx(tmp_path, clock)
    # Rules at their own run length (planned = verdict_end + 1 = 5000 s, nothing scaled) whose deadline rule fires
    # at 5000 - 60 s, after both limits: only the stage limit can stop the stage. (The shipped profiles end refine
    # exactly a report reserve before the deadline, so there the deadline rule fires at the same second.)
    rules = ctx.config.stop_rules.model_copy(update={
        "deadline_seconds": 5000, "report_reserve_seconds": 60, "refine_reserve_seconds": 0,
        "stage_limits_s": StageLimits(stage_1_end=500, refine_end=1000, verdict_end=4999)})
    assert rules.effective() is rules
    ctx.config = ctx.config.model_copy(update={"stop_rules": rules})
    limits = ctx.config.stop_rules.stage_limits_s
    at = getattr(limits, limit)
    who = PhaseName.INGEST if limit == "stage_1_end" else PhaseName.RESEARCH
    await Orchestrator(phases(log, **{who.value: Recorder(who, log, clock=clock, advance=at)})).run(ctx)
    assert "refine" not in log and log[-2:] == ["verify", "report"]
    assert ctx.state.stop_reason is not None and ctx.state.stop_reason.detail == f"stage_limits_s.{limit}"
    assert any(skipped in d.event or "before stage 1" in d.event for d in ctx.state.degradations)


async def test_phase_crash_is_typed_and_state_flushed(tmp_path: Path) -> None:
    clock, log = FakeClock(), []
    ctx = make_ctx(tmp_path, clock)
    with pytest.raises(StageCrash) as info:
        await Orchestrator(phases(log, assess=Recorder(PhaseName.ASSESS, log, fail=True))).run(ctx)
    assert info.value.phase == "assess" and int(info.value.exit_code) == 4
    assert ctx.run_dir.state.exists()
    # understand and plan ended (and checkpointed) before the crash; research never started.
    assert latest_checkpoint(ctx.run_dir).phase is PhaseName.PLAN and "research" not in log


def test_stop_rule_evaluation_order() -> None:
    cfg = load_config()
    s = RunState(run_id="r", created_utc="2026-10-02T09:00:00Z")
    assert stop_rules.evaluate(s, cfg.stop_rules, 0.0) is None
    s.budget.new_sources_by_iteration = [3, 0, 0]
    s.budget.research_iterations = 3
    assert stop_rules.evaluate(s, cfg.stop_rules, 0.0).code is StopReasonCode.NO_MARGINAL_GAIN
    s.budget.tool_calls = cfg.stop_rules.max_tool_calls
    r = stop_rules.evaluate(s, cfg.stop_rules, 0.0)
    assert r.code is StopReasonCode.BUDGET_TOOL_CALLS and r.group.value == "cap"      # caps first
    s2 = RunState(run_id="r", created_utc="2026-10-02T09:00:00Z")
    s2.budget.research_iterations = cfg.stop_rules.max_research_iterations
    assert stop_rules.evaluate(s2, cfg.stop_rules, 0.0).detail == "max_research_iterations"


# ------------------------------------------------------------------------------ stage 1 concurrency


class Gated:
    """A stage 1 member that ends only when the test opens its gate, and records what had ended
    when it started."""

    def __init__(self, name: PhaseName, log: list[str], gates: dict[str, asyncio.Event],
                 seen: dict[str, list[str]]) -> None:
        self.name, self.log, self.gates, self.seen = name, log, gates, seen

    async def run(self, ctx: RunContext) -> RunContext:
        self.seen[self.name.value] = list(self.log)
        await self.gates[self.name.value].wait()
        self.log.append(self.name.value)
        ctx.state.add_degradation(DegradationType.OTHER, f"{self.name.value} ended", "test")
        return ctx


MEMBERS = ["understand", "plan", "assess", "research"]


def _orders() -> list[tuple[str, ...]]:
    """Every order in which the four members can end: research only after understand and plan."""
    return [o for o in itertools.permutations(MEMBERS)
            if o.index("research") > max(o.index("understand"), o.index("plan"))]


@pytest.mark.parametrize("order", _orders(), ids="-".join)
async def test_stage_1_members_end_in_any_order(tmp_path: Path, order: tuple[str, ...]) -> None:
    clock, log = FakeClock(), []
    gates = {m: asyncio.Event() for m in MEMBERS}
    seen: dict[str, list[str]] = {}
    ctx = make_ctx(tmp_path, clock)
    members = {m: Gated(PhaseName(m), log, gates, seen) for m in MEMBERS}
    run = asyncio.create_task(Orchestrator(phases(log, **members)).run(ctx))
    for m in order:
        for _ in range(50):                             # let the member start (research waits for its deps)
            await asyncio.sleep(0)
            if m in seen:
                break
        assert m in seen, f"{m} never started"
        gates[m].set()
        for _ in range(50):
            await asyncio.sleep(0)
            if m in log:
                break
    ctx = await run
    assert log == ["ingest", *order, "refine", "verify", "report"]
    assert set(seen["research"]) >= {"understand", "plan"}                  # STAGE_1_DEPENDS
    assert not {"understand", "plan"} & set(seen["assess"])                 # assess did not wait for them
    ckpts = sorted((load_checkpoint(f) for f in ctx.run_dir.checkpoints.iterdir()), key=lambda c: c.ordinal)
    stage1 = [c.phase.value for c in ckpts][1:5]
    assert stage1 == [*[m for m in order if m != "assess"], "assess"]       # each member on its end; assess closes
    elapsed = [c.state.budget.elapsed_s for c in ckpts]
    assert elapsed == sorted(elapsed)                                        # set at every checkpoint
    events = sorted(d.event for d in ctx.state.degradations)
    assert events == sorted(f"{m} ended" for m in MEMBERS)                   # every member merged exactly once
    assert [d.id for d in ctx.state.degradations] == [f"DEG-{i:03d}" for i in range(1, 5)]


async def test_a_checkpoint_never_holds_a_running_members_state(tmp_path: Path) -> None:
    """Members run on copies of the run state: understand's checkpoint, written while plan is still
    running, has none of plan's writes; plan's own checkpoint has them."""
    clock, log = FakeClock(), []
    gate = asyncio.Event()

    class SlowPlan:
        name = PhaseName.PLAN

        async def run(self, ctx: RunContext) -> RunContext:
            ctx.state.queries_issued = 7
            ctx.state.add_degradation(DegradationType.OTHER, "plan wrote this", "test")
            await gate.wait()
            return ctx

    class LateAssess:
        name = PhaseName.ASSESS

        async def run(self, ctx: RunContext) -> RunContext:
            for _ in range(5):
                await asyncio.sleep(0)
            gate.set()
            return ctx

    ctx = make_ctx(tmp_path, clock)
    await Orchestrator(phases(log, plan=SlowPlan(), assess=LateAssess())).run(ctx)
    understand = load_checkpoint(ctx.run_dir.checkpoints / "02-understand.json")
    plan = load_checkpoint(ctx.run_dir.checkpoints / "03-plan.json")
    assert understand.ordinal is not None and plan.ordinal is not None and understand.ordinal < plan.ordinal
    assert understand.state.queries_issued == 0 and understand.state.degradations == []
    assert plan.state.queries_issued == 7 and [d.event for d in plan.state.degradations] == ["plan wrote this"]
    assert ctx.state.queries_issued == 7 and len(ctx.state.degradations) == 1


async def test_stage_1_backstop_stops_a_member_past_the_limit(tmp_path: Path) -> None:
    """A member still running after stage_1_end plus the grace is stopped and disclosed; the run goes on."""
    clock, log = FakeClock(), []
    ctx = make_ctx(tmp_path, clock)

    class Hung:
        name = PhaseName.RESEARCH

        async def run(self, ctx: RunContext) -> RunContext:
            clock.advance(ctx.config.stop_rules.stage_limits_s.stage_1_end + 1)
            await asyncio.Event().wait()                                  # never ends
            return ctx

    orch = Orchestrator(phases(log, research=Hung()))
    orch.stage1_grace_s, orch.stage1_poll_s = 0.0, 0.01
    ctx = await orch.run(ctx)
    assert log == ["ingest", "understand", "plan", "assess", "refine", "verify", "report"]
    assert ctx.state.stop_reason is not None and ctx.state.stop_reason.detail == "stage_limits_s.stage_1_end"
    assert any("research was still running" in d.event for d in ctx.state.degradations)
    assert PhaseName.RESEARCH in ctx.state.completed_phases


async def test_plan_only_starts_neither_research_nor_assess(tmp_path: Path) -> None:
    clock, log = FakeClock(), []
    ctx = make_ctx(tmp_path, clock)
    ctx.plan_only = True
    await Orchestrator(phases(log)).run(ctx)
    assert log == ["ingest", "understand", "plan"]
    assert latest_checkpoint(ctx.run_dir).phase is PhaseName.PLAN


# ============================================================================= a crash inside one assess shard


def _shard_phase(crash: set[int]) -> Any:
    """An AssessPhase whose shards answer with no finding, except the launch indexes in ``crash``,
    which raise at their start (what a ``process:`` fault with ``shard`` does; robustness BEH-29)."""
    from sit_review_agent.llm.outputs import AssessOutput, CriterionCoverage
    from sit_review_agent.phases.assess import AssessPhase, ShardResult

    phase = AssessPhase()

    async def run_shard(ctx: RunContext, shard: object, index: int, count: int) -> ShardResult:
        if index in crash:
            raise RuntimeError(f"injected fault: raise_in_stage assess shard {index}/{count}")
        criteria = list(shard.criteria)  # type: ignore[attr-defined]
        out = AssessOutput(findings=[], sound_areas=[], coverage=[
            CriterionCoverage(criterion_id=c, outcome="no_issue", finding_ids=[], note="checked: no issue")
            for c in criteria])
        return ShardResult(index=index, name=shard.name, criteria=criteria, outcome="done", output=out,  # type: ignore[attr-defined]
                           call_id=f"llm-{index}", model="fake", prompt_hash="x")

    phase.run_shard = run_shard  # type: ignore[method-assign]
    return phase


async def test_a_crash_inside_one_shard_ends_that_shard_only(tmp_path: Path) -> None:
    """BEH-29: the shard ends with outcome ``error``, disclosed by name and class with its criteria
    not assessed; the other shards' results stand and nothing is raised."""
    ctx = make_ctx(tmp_path, FakeClock())
    k = len(ctx.config.agent.assess.shards_for(ctx.config.criteria.ids()))     # the configured groups
    phase = _shard_phase({k})                                                    # the last shard crashes
    results = await phase.run_shards(ctx)
    assert [r.outcome for r in results] == ["done"] * (k - 1) + ["error"]
    crashed = results[-1]
    assert crashed.detail.startswith("RuntimeError: injected fault") and crashed.output is None
    events = [d.event for d in crashed.delta.degradations]
    assert len(events) == 1 and events[0].startswith(f"assess shard {k}/{k} ({crashed.name}) failed (RuntimeError")
    assert all(not r.delta.degradations for r in results[:-1])
    phase.merge(ctx, results)
    rows = {c.criterion_id: c for c in ctx.state.coverage}
    lost = crashed.criteria
    assert all(rows[c].outcome == "not_applicable" and rows[c].note.startswith("not assessed") for c in lost)
    assert all(rows[c].outcome == "no_issue" for r in results[:-1] for c in r.criteria)
    assert any(d.event.startswith(f"assess shard {k}/{k}") for d in ctx.state.degradations)


async def test_every_shard_crashing_is_a_stage_crash(tmp_path: Path) -> None:
    ctx = make_ctx(tmp_path, FakeClock())
    k = len(ctx.config.agent.assess.shards_for(ctx.config.criteria.ids()))
    with pytest.raises(StageCrash) as info:
        await _shard_phase(set(range(1, k + 1))).run_shards(ctx)
    assert info.value.phase == "assess" and int(info.value.exit_code) == 4
    assert isinstance(info.value.cause, RuntimeError) and f"shard 1/{k}" in str(info.value.cause)
