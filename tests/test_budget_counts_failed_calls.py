"""The token budget counts failed model calls (Session 4 accounting fixes, interface change).

``state.budget`` (read by the ``budget_tokens`` stop rule) used to count only calls that returned
a result. A call that raised (truncated at the output cap, declined, schema-invalid) was billed but
not counted, so a run could pass its token budget unnoticed. Every :class:`LLMError` now carries
the usage its failed attempts were billed for (``LLMError.usage``; ``None`` when no attempt
reported usage), the gateways set it, and every phase that handles the error adds it to the budget.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import test_ingest_verify_report as ivr
import test_llm_phases as lp
import test_research_phase as rp
from sit_review_agent.clock import FakeClock
from sit_review_agent.config import EffectiveConfig, load_config
from sit_review_agent.errors import LLMDeadlineError, LLMRefusalError, LLMSchemaError, LLMTruncatedError
from sit_review_agent.llm.claude_code import ClaudeCodeGateway, CompletedRun
from sit_review_agent.llm.gateway import FakeGateway, FakeResponse, FaultInjectingLLMGateway, LLMRequest, Usage
from sit_review_agent.llm.outputs import PlanOutput
from sit_review_agent.llm.runtime import RunDeadline, RuntimeLimits, attach_runtime
from sit_review_agent.models import StopReasonCode
from sit_review_agent.orchestrator import RunRequest, run_review
from sit_review_agent.phases.report import _verdict_call
from sit_review_agent.phases.research import ResearchPhase
from sit_review_agent.phases.understand import UnderstandPhase
from sit_review_agent.phases.verify import VerifyPhase
from sit_review_agent.progress import NullProgress
from sit_review_agent.rundir import RunDir
from sit_review_agent.selftest import FIXTURE_DIR, fixture_gateway, selftest_config
from sit_review_agent.states import PhaseName
from sit_review_agent.tools.faults import FaultSchedule

BILLED = Usage(input_tokens=7_000, output_tokens=5_000, cache_creation_input_tokens=300, cache_read_input_tokens=200)


def budget_of(ctx: Any) -> tuple[int, int]:
    b = ctx.state.budget
    return b.input_tokens, b.output_tokens


@pytest.fixture(scope="module")
def cfg() -> EffectiveConfig:
    return load_config()


# ============================================================================== phases


async def test_understand_counts_two_truncated_calls(tmp_path: Path, cfg: EffectiveConfig) -> None:
    ctx = lp.make_ctx(tmp_path, cfg, {PhaseName.UNDERSTAND: [FakeResponse(stop_reason="max_tokens", usage=BILLED)] * 2})
    await UnderstandPhase().run(ctx)
    assert ctx.state.intent_summary is None                           # the truncated-twice fallback
    assert budget_of(ctx) == (2 * BILLED.total_input_tokens, 2 * BILLED.output_tokens)
    b = ctx.state.budget
    assert (b.cache_read_input_tokens, b.cache_creation_input_tokens) == (400, 600)


async def test_understand_counts_declined_and_schema_invalid_calls(tmp_path: Path, cfg: EffectiveConfig) -> None:
    declined = lp.make_ctx(tmp_path / "a", cfg, {PhaseName.UNDERSTAND: [
        FakeResponse(stop_reason="refusal", usage=BILLED)] * 2})
    await UnderstandPhase().run(declined)
    assert budget_of(declined) == (2 * BILLED.total_input_tokens, 2 * BILLED.output_tokens)
    ok = Usage(input_tokens=1_000, output_tokens=200)
    repaired = lp.make_ctx(tmp_path / "b", cfg, {PhaseName.UNDERSTAND: [
        FakeResponse(parsed={"not": "an understand output"}, usage=BILLED),
        FakeResponse(parsed=lp.understand_output(), usage=ok)]})
    await UnderstandPhase().run(repaired)
    assert repaired.state.intent_summary is not None
    assert budget_of(repaired) == (BILLED.total_input_tokens + 1_000, BILLED.output_tokens + 200)


async def test_research_counts_a_truncated_call(tmp_path: Path) -> None:
    ctx = await ResearchPhase().run(rp.make_ctx(tmp_path, [FakeResponse(stop_reason="max_tokens", usage=BILLED)]))
    assert ctx.state.stop_reason is not None and ctx.state.stop_reason.detail == "max_tokens"
    assert budget_of(ctx) == (BILLED.total_input_tokens, BILLED.output_tokens)


async def test_verify_counts_a_declined_repair_call(tmp_path: Path) -> None:
    ctx = await ivr.ingested(tmp_path, {"verify": [FakeResponse(stop_reason="refusal", usage=BILLED)]})
    ctx.state.finding_drafts = [ivr.draft("FND-001", anchors=[ivr.anchor("1", 2, ivr.Q_FAKE)], kind="strength",
                                          disposition="no_change")]
    ctx.state.finding_meta = {"FND-001": ivr.meta("FND-001")}
    ctx = await VerifyPhase().run(ctx)
    assert any("repair call failed" in d.event for d in ctx.state.degradations)
    assert budget_of(ctx) == (BILLED.total_input_tokens, BILLED.output_tokens)


async def test_report_counts_declined_verdict_calls(tmp_path: Path) -> None:
    ctx = await ivr.ingested(tmp_path, {"report": [FakeResponse(stop_reason="refusal", usage=BILLED)] * 2})
    out, reason = await _verdict_call(ctx)
    assert out is None and reason is not None and reason.startswith("LLMRefusalError")
    assert budget_of(ctx) == (2 * BILLED.total_input_tokens, 2 * BILLED.output_tokens)


# ============================================================================== the stop rule


async def test_budget_rule_fires_on_failed_calls_alone(tmp_path: Path) -> None:
    """Understand truncated twice spends 2 x 7,500 input tokens; with a 10,000-token budget the
    run must stop before plan. Before the fix the budget read 0 and the run went on."""
    base = selftest_config(tmp_path)
    cfg = base.model_copy(update={"stop_rules": base.stop_rules.model_copy(update={"max_input_tokens": 10_000})})

    def gateway(rd: Any, clock: Any, progress: Any) -> Any:
        gw = fixture_gateway(rd, clock=clock)
        for _ in range(2):
            gw.script["understand"].appendleft(FakeResponse(stop_reason="max_tokens", usage=BILLED))  # type: ignore[attr-defined]
        return gw

    out = await run_review(RunRequest(pdf=FIXTURE_DIR / "design.pages.txt", config=cfg, run_id="budget"),
                           llm_factory=gateway, clock=FakeClock(), progress=NullProgress())
    assert out.exit_code == 0
    state = json.loads((RunDir(out.run_dir).root / "state.json").read_text(encoding="utf-8"))
    assert state["budget"]["input_tokens"] >= 2 * BILLED.total_input_tokens
    assert state["stop_reason"]["code"] == StopReasonCode.BUDGET_TOKENS.value
    assert "plan" not in (state.get("llm_calls") or {})                 # no model call after the cap fired


# ============================================================================== gateways set LLMError.usage


def _cli(stop: str | None = "end_turn", *, is_error: bool = False, result: str = "",
         cost: float = 0.0) -> dict[str, Any]:
    return {"type": "result", "subtype": "error_during_execution" if is_error else "success", "is_error": is_error,
            "result": result, "structured_output": None, "stop_reason": stop, "num_turns": 2,
            "total_cost_usd": cost, "usage": {"input_tokens": 100, "output_tokens": 20,
                                              "cache_creation_input_tokens": 1000, "cache_read_input_tokens": 50},
            "modelUsage": {"claude-opus-5-5": {"inputTokens": 100, "outputTokens": 20}}}


class _Runner:
    def __init__(self, *script: Any) -> None:
        self.script = list(script)

    async def __call__(self, argv: list[str], stdin: str, env: dict[str, str], cwd: Path,
                       timeout_s: float) -> CompletedRun:
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return CompletedRun(0, json.dumps(item), "")


def _req(phase: PhaseName = PhaseName.PLAN) -> LLMRequest:
    return LLMRequest(phase=phase, conversation_id=f"{phase.value}-0", system="You are a reviewer.",
                      messages=[{"role": "user", "content": [{"type": "text", "text": "Plan."}]}], effort="high",
                      max_tokens=4321, output_schema=PlanOutput)


def _claude(tmp_path: Path, cfg: EffectiveConfig, *script: Any) -> ClaudeCodeGateway:
    llm = cfg.agent.llm.model_copy(update={"backoff_base_s": 0.0, "backoff_max_s": 0.0})
    c = cfg.model_copy(update={"agent": cfg.agent.model_copy(update={"llm": llm})})
    return ClaudeCodeGateway(c, RunDir(tmp_path / "run").create(), clock=FakeClock(), runner=_Runner(*script))


async def test_claude_code_error_carries_the_billed_usage_of_every_attempt(tmp_path: Path,
                                                                           cfg: EffectiveConfig) -> None:
    gw = _claude(tmp_path, cfg, _cli(None, is_error=True, result="API Error: 529 overloaded"),
                 _cli("max_tokens"))
    with pytest.raises(LLMTruncatedError) as ei:
        await gw.call(_req())
    assert ei.value.usage == Usage(200, 40, 2000, 100)                  # the overloaded attempt and the truncated one


async def test_claude_code_killed_attempt_reports_no_usage(tmp_path: Path, cfg: EffectiveConfig) -> None:
    gw = _claude(tmp_path, cfg, TimeoutError())
    attach_runtime(gw, RuntimeLimits(deadline=RunDeadline(540, 120, 200, lambda: 220.0)))
    with pytest.raises(LLMDeadlineError) as ei:
        await gw.call(_req(PhaseName.ASSESS))
    assert ei.value.usage is None                                       # unknown, never a made-up zero


async def test_fake_and_fault_gateways_set_usage(tmp_path: Path, cfg: EffectiveConfig) -> None:
    fake = FakeGateway({"plan": [FakeResponse(stop_reason="refusal", usage=BILLED),
                                 FakeResponse(parsed={"bad": 1}, usage=BILLED)]})
    for err in (LLMRefusalError, LLMSchemaError):
        with pytest.raises(err) as ei:
            await fake.call(_req())
        assert ei.value.usage == BILLED
    inner = FakeGateway({"plan": [FakeResponse(parsed={"questions": [], "criteria_skipped": []}, usage=BILLED)]})
    sched = FaultSchedule.model_validate({"id": "T", "llm": [{"match": {"stage": "plan"},
                                                              "fault": {"type": "schema_violation"}}]})
    wrapped = FaultInjectingLLMGateway(inner, sched, clock=FakeClock(), policy=cfg.agent.llm)
    with pytest.raises(LLMSchemaError) as ei2:
        await wrapped.call(_req())
    assert ei2.value.usage == BILLED                                    # the inner call was billed
    injected = FaultInjectingLLMGateway(FakeGateway({}), FaultSchedule.model_validate(
        {"id": "R", "llm": [{"match": {"stage": "plan"}, "fault": {"type": "stop_reason", "value": "refusal"}}]}),
        clock=FakeClock(), policy=cfg.agent.llm)
    with pytest.raises(LLMRefusalError) as ei3:
        await injected.call(_req())
    assert ei3.value.usage is None                                      # an injected fault spends nothing


async def test_replay_counts_a_recorded_failed_call_like_the_live_run(tmp_path: Path) -> None:
    from sit_review_agent.replay import replay_run

    cfg = selftest_config(tmp_path)

    def gateway(rd: Any, clock: Any, progress: Any) -> Any:
        gw = fixture_gateway(rd, clock=clock)
        gw.script["understand"].appendleft(FakeResponse(stop_reason="max_tokens", usage=BILLED))  # type: ignore[attr-defined]
        return gw

    out = await run_review(RunRequest(pdf=FIXTURE_DIR / "design.pages.txt", config=cfg, run_id="rec"),
                           llm_factory=gateway, clock=FakeClock(), progress=NullProgress())
    assert out.exit_code == 0
    rep = await replay_run(Path(out.run_dir), run_root=str(tmp_path / "replays"))
    assert rep.exit_code == 0, rep.differences

    def budget(d: Path) -> dict[str, Any]:
        return dict(json.loads((d / "state.json").read_text(encoding="utf-8"))["budget"])

    recorded, replayed = budget(Path(out.run_dir)), budget(Path(rep.run_dir))
    assert recorded["output_tokens"] >= BILLED.output_tokens
    assert {k: replayed[k] for k in ("input_tokens", "output_tokens")} == {
        k: recorded[k] for k in ("input_tokens", "output_tokens")}


@pytest.mark.parametrize("err", [LLMDeadlineError, LLMRefusalError, LLMSchemaError, LLMTruncatedError])
async def test_research_counts_every_handled_failure(tmp_path: Path, err: type) -> None:
    kw = {"category": None} if err is LLMRefusalError else {"max_tokens": 10} if err is LLMTruncatedError else {}
    fails = [FakeResponse(raises=_with_usage(err("scripted", **kw))) for _ in range(2)]
    ctx = await ResearchPhase().run(rp.make_ctx(tmp_path, fails + [FakeResponse(stop_reason="max_tokens")]))
    assert ctx.state.budget.output_tokens >= BILLED.output_tokens


def _with_usage(e: Any) -> Any:
    e.usage = BILLED
    return e


async def test_a_deadline_cut_after_billed_attempts_is_counted(tmp_path: Path, cfg: EffectiveConfig) -> None:
    cut = LLMDeadlineError("cut by the run deadline", usage=BILLED)    # e.g. an overloaded attempt, then the cut
    ctx = lp.make_ctx(tmp_path, cfg, {PhaseName.UNDERSTAND: [FakeResponse(raises=cut)]})
    await UnderstandPhase().run(ctx)
    assert budget_of(ctx) == (BILLED.total_input_tokens, BILLED.output_tokens)
