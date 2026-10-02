"""The state machine loop and stop rules, with fake phases (no model, no tools)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sit_review_agent import stop_rules
from sit_review_agent.clock import FakeClock, isoformat_z
from sit_review_agent.config import ConfigOverrides, load_config
from sit_review_agent.context import RunContext
from sit_review_agent.errors import StageCrash
from sit_review_agent.llm.gateway import FakeGateway
from sit_review_agent.models import StopReasonCode
from sit_review_agent.orchestrator import Orchestrator
from sit_review_agent.progress import NullProgress
from sit_review_agent.prompts import PromptBundle
from sit_review_agent.rundir import RunDir
from sit_review_agent.state.checkpoint import latest_checkpoint
from sit_review_agent.state.decision_registry import DecisionRegistry
from sit_review_agent.state.evidence_ledger import EvidenceLedger
from sit_review_agent.state.run_state import RunState
from sit_review_agent.states import PHASE_ORDER, PhaseName


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
    assert log == [p.value for p in PHASE_ORDER]
    assert ctx.state.completed_phases == list(PHASE_ORDER)
    files = sorted(p.name for p in ctx.run_dir.checkpoints.iterdir())
    assert files == [f"{i + 1:02d}-{p.value}.json" for i, p in enumerate(PHASE_ORDER)]
    ckpt = latest_checkpoint(ctx.run_dir)
    assert ckpt is not None and ckpt.phase is PhaseName.REPORT and ckpt.hashes.effective_config == ctx.config.sha256()
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
    slow = Recorder(PhaseName.UNDERSTAND, log, clock=clock, advance=95)
    await Orchestrator(phases(log, understand=slow)).run(ctx)
    assert log == ["ingest", "understand", "verify", "report"]
    assert ctx.state.stop_reason is not None and ctx.state.stop_reason.code is StopReasonCode.DEADLINE
    assert ctx.state.degradations and ctx.state.degradations[0].type.value == "budget_or_deadline_hit"


async def test_phase_crash_is_typed_and_state_flushed(tmp_path: Path) -> None:
    clock, log = FakeClock(), []
    ctx = make_ctx(tmp_path, clock)
    with pytest.raises(StageCrash) as info:
        await Orchestrator(phases(log, assess=Recorder(PhaseName.ASSESS, log, fail=True))).run(ctx)
    assert info.value.phase == "assess" and int(info.value.exit_code) == 4
    assert ctx.run_dir.state.exists()
    assert latest_checkpoint(ctx.run_dir).phase is PhaseName.RESEARCH


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
