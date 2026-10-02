"""Runtime policies decided on 2026-10-02 (owner-delegated to the coordinator; workstream W1):

* LLM-05: model attempts bounded by the run deadline (``llm.runtime.RunDeadline``) in both live
  gateways, the fake gateway and the fault wrapper; research keeps time for assess; a cut assess
  is disclosed as "out of time before assessment";
* NET-02: connection errors on the first model call get a short window, then "no network";
  ``anthropic_api`` runs its no-retry preflight before ``models.retrieve``;
* INF-08: live MCP servers enabled and the key unset -> usage error before any model call;
* LLM-10: pre-send size check from characters against 80 % of the context window;
* OPS-10: ``ClaudeCodeGateway`` logs ``elapsed_s`` on successful calls;
* ``process:`` fault entries applied by the orchestrator (and validated by the loader);
* the demo profile and the default deadline.

Offline: fake SDK client, fake ``claude -p`` runner, virtual clock; no key, no network.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx2
import pytest

from sit_review_agent.clock import FakeClock
from sit_review_agent.config import (
    AuthorityHosts,
    ConfigOverrides,
    EffectiveConfig,
    LLMSettings,
    Transport,
    load_config,
)
from sit_review_agent.errors import (
    ConfigError,
    LLMConnectionError,
    LLMContextTooLongError,
    LLMDeadlineError,
    LLMOverloadedError,
    LLMTimeoutError,
)
from sit_review_agent.llm.claude_code import ClaudeCodeGateway, CompletedRun
from sit_review_agent.llm.gateway import (
    AnthropicGateway,
    FakeGateway,
    FakeResponse,
    FaultInjectingLLMGateway,
    LLMRequest,
)
from sit_review_agent.llm.runtime import (
    CONTEXT_MARGIN,
    OUT_OF_TIME_BEFORE_ASSESSMENT,
    ContextGuard,
    RunDeadline,
    RuntimeLimits,
    attach_runtime,
    build_runtime,
)
from sit_review_agent.models import SourceAuthority
from sit_review_agent.paths import config_dir, repo_root
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.states import PhaseName
from sit_review_agent.tools.faults import FaultSchedule, load_fault_schedule

A = PhaseName.ASSESS
REQ = httpx2.Request("POST", "https://api.anthropic.invalid/v1/messages")
SAMPLE_HOSTS = ("github.com/pgvector", "pgvector.dev", "kafka.apache.org")


# ============================================================================= helpers


@pytest.fixture(scope="module")
def base() -> EffectiveConfig:
    return load_config()


class Elapsed:
    """A settable run clock for :class:`RunDeadline`."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t


def deadline(t: float = 0.0, *, deadline_s: float | None = 540, reserve: float = 120, research: float = 200,
             min_attempt: float = 10.0) -> tuple[RuntimeLimits, Elapsed]:
    el = Elapsed(t)
    return RuntimeLimits(deadline=RunDeadline(deadline_s, reserve, research, el, min_attempt_s=min_attempt)), el


def req(phase: PhaseName = A, text: str = "Assess the design.", *, pdf_b64: str | None = None) -> LLMRequest:
    content: list[dict[str, Any]] = []
    if pdf_b64 is not None:
        content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                       "data": pdf_b64}})
    content.append({"type": "text", "text": text})
    return LLMRequest(phase=phase, conversation_id=f"{phase.value}-0", system="You are a reviewer.",
                      messages=[{"role": "user", "content": content}], effort="high", max_tokens=1000)


def cli_ok(text: str = "ok", n: int = 1) -> dict[str, Any]:
    return {"type": "result", "subtype": "success", "is_error": False, "result": "",
            "structured_output": {"text": text}, "stop_reason": "end_turn", "num_turns": 2,
            "total_cost_usd": 0.01 * n, "usage": {"input_tokens": 10, "output_tokens": 5},
            "modelUsage": {"claude-opus-5-5": {"inputTokens": 10 * n, "outputTokens": 5 * n}}}


def cli_err(result: str) -> dict[str, Any]:
    return {"type": "result", "subtype": "error_during_execution", "is_error": True, "result": result,
            "stop_reason": None, "num_turns": 1, "total_cost_usd": 0.0, "usage": {}}


class Runner:
    def __init__(self, *script: Any) -> None:
        self.script = list(script)
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, argv: list[str], stdin: str, env: dict[str, str], cwd: Path,
                       timeout_s: float) -> CompletedRun:
        self.calls.append({"timeout_s": timeout_s, "argv": argv})
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item if isinstance(item, CompletedRun) else CompletedRun(0, json.dumps(item), "")


def claude(tmp_path: Path, cfg: EffectiveConfig, *script: Any,
           clock: FakeClock | None = None) -> tuple[ClaudeCodeGateway, Runner, RunDir, FakeClock]:
    rd = RunDir(tmp_path / "run").create()
    runner, clk = Runner(*script), clock or FakeClock()
    return ClaudeCodeGateway(cfg, rd, clock=clk, runner=runner), runner, rd, clk


class _Stream:
    def __init__(self, item: Any) -> None:
        self.item = item

    async def get_final_message(self) -> Any:
        if self.item == "hang":
            await asyncio.sleep(30)
        return self.item


class _Manager:
    def __init__(self, item: Any) -> None:
        self.item = item

    async def __aenter__(self) -> _Stream:
        if isinstance(self.item, BaseException):
            raise self.item
        return _Stream(self.item)

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class _Messages:
    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.calls = 0

    def stream(self, **kwargs: Any) -> _Manager:
        self.calls += 1
        return _Manager(self.script.pop(0))


def anthropic_gw(tmp_path: Path, cfg: EffectiveConfig, *script: Any) -> tuple[AnthropicGateway, _Messages, FakeClock]:
    msgs = _Messages(list(script))
    client = SimpleNamespace(messages=msgs, beta=SimpleNamespace(messages=msgs))
    clk = FakeClock()
    return AnthropicGateway(cfg, RunDir(tmp_path / "run").create(), clock=clk, client=client), msgs, clk


def conn_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=REQ)


def log(rd: RunDir) -> list[dict[str, Any]]:
    return JsonlWriter(rd.llm_log).read()


# ============================================================================= LLM-05: the deadline


def test_phase_budgets_keep_the_reserves() -> None:
    lim, el = deadline(100)
    d = lim.deadline
    assert d is not None
    assert d.phase_budget(A) == 540 - 100 - 120                      # assess, refine, understand, plan
    assert d.phase_budget(PhaseName.RESEARCH) == 540 - 100 - 120 - 200  # research also keeps assess's time
    assert d.phase_budget(PhaseName.VERIFY) == d.phase_budget(PhaseName.REPORT) == 440   # the reserve itself
    assert d.attempt_timeout(A, 1800) == (320, True)                 # bounded by the deadline
    assert d.attempt_timeout(A, 60) == (60, False)                   # the configured timeout is shorter
    assert d.can_retry(A, 300) and not d.can_retry(A, 315)
    el.t = 415
    with pytest.raises(LLMDeadlineError, match="no time left for a assess model call"):
        d.attempt_timeout(A, 1800)                                   # 5 s left: no attempt is started


def test_runs_without_a_deadline_rule_keep_the_full_timeout(base: EffectiveConfig) -> None:
    stop = base.stop_rules.model_copy(update={"active": [r for r in base.stop_rules.active if r != "deadline"]})
    lim = build_runtime(base.model_copy(update={"stop_rules": stop}), lambda: 99_999.0)
    assert lim.deadline is not None and lim.deadline.deadline_s is None
    assert lim.deadline.attempt_timeout(A, 1800) == (1800, False)


def test_default_deadline_and_demo_profile(base: EffectiveConfig) -> None:
    sr = base.stop_rules
    assert (sr.deadline_seconds, sr.report_reserve_seconds, sr.assess_reserve_seconds) == (3600, 180, 600)
    assert "deadline" in sr.active and base.agent.llm.timeout_s == 1800
    demo = load_config(overrides=ConfigOverrides(profile="demo"))
    assert demo.stop_rules.deadline_seconds == 540
    e = demo.agent.effort
    assert (e.plan, e.research, e.assess, e.refine, e.verify, e.report) == ("medium", "low", "medium", "medium",
                                                                            "medium", "medium")
    assert demo.stop_rules.report_reserve_seconds + demo.stop_rules.assess_reserve_seconds < 540
    text = (config_dir() / "profiles" / "demo.yaml").read_text(encoding="utf-8")
    assert "UNMEASURED" in text and "USER_DECISIONS #1" in text and "forks" in text
    lim = build_runtime(demo, lambda: 0.0)
    assert lim.deadline is not None and lim.deadline.attempt_timeout(A, 1800) == (420, True)


async def test_claude_code_attempt_is_cut_at_the_deadline_and_not_retried(tmp_path: Path,
                                                                          base: EffectiveConfig) -> None:
    gw, runner, rd, _ = claude(tmp_path, base, TimeoutError(), cli_ok())
    attach_runtime(gw, deadline(220)[0])                              # 540 - 220 - 120 = 200 s left for assess
    with pytest.raises(LLMDeadlineError, match="cut after 200 s by the run deadline") as ei:
        await gw.call(req())
    assert len(runner.calls) == 1 and runner.calls[0]["timeout_s"] == 200
    assert ei.value.call_id == "llm-0001"
    entry = log(rd)[-1]
    assert entry["outcome"] == "LLMDeadlineError" and entry["timeout_s"] == 200


async def test_claude_code_starts_no_attempt_without_time(tmp_path: Path, base: EffectiveConfig) -> None:
    gw, runner, _, _ = claude(tmp_path, base, cli_ok())
    attach_runtime(gw, deadline(415)[0])
    with pytest.raises(LLMDeadlineError) as ei:
        await gw.call(req())
    assert runner.calls == [] and ei.value.call_id == "llm-0001"


async def test_claude_code_retry_never_starts_past_the_deadline(tmp_path: Path, base: EffectiveConfig) -> None:
    gw, runner, _, _ = claude(tmp_path, base, cli_err("API Error: 529 overloaded"), cli_ok())
    gw.runtime = RuntimeLimits(deadline=RunDeadline(540, 120, 200, Elapsed(409)))
    with pytest.raises(LLMDeadlineError, match="after LLMOverloadedError"):
        await gw.call(req())                                          # 11 s left; backoff + 10 s does not fit
    assert len(runner.calls) == 1


async def test_claude_code_without_a_deadline_uses_the_configured_timeout(tmp_path: Path,
                                                                          base: EffectiveConfig) -> None:
    gw, runner, _, _ = claude(tmp_path, base, cli_ok())
    attach_runtime(gw, deadline(0, deadline_s=None)[0])
    await gw.call(req())
    assert runner.calls[0]["timeout_s"] == 1800


async def test_anthropic_attempt_is_cut_at_the_deadline(tmp_path: Path, base: EffectiveConfig) -> None:
    gw, msgs, _ = anthropic_gw(tmp_path, base, "hang", "hang")
    lim, _ = deadline(540 - 120 - 0.2, min_attempt=0.05)               # 0.2 s of real time left
    attach_runtime(gw, lim)
    with pytest.raises(LLMDeadlineError, match="cut after 0 s by the run deadline"):
        await asyncio.wait_for(gw.call(req()), 5)
    assert msgs.calls == 1                                            # never retried


async def test_fault_wrapper_hang_is_cut_on_the_run_clock(tmp_path: Path, base: EffectiveConfig) -> None:
    clock = FakeClock()
    inner = FakeGateway({"assess": [FakeResponse(text="late")]}, run_dir=RunDir(tmp_path / "r").create(), clock=clock)
    sched = FaultSchedule.model_validate({"id": "T", "llm": [{"match": {"stage": "assess"},
                                                              "fault": {"type": "hang"}}]})
    gw = FaultInjectingLLMGateway(inner, sched, clock=clock, policy=base.agent.llm)
    attach_runtime(gw, RuntimeLimits(deadline=RunDeadline(540, 120, 200, clock.monotonic)))
    with pytest.raises(LLMDeadlineError):
        await gw.call(req())
    assert clock.monotonic() == 420 and inner.calls == []             # waited the bounded timeout only


async def test_fault_wrapper_without_deadline_waits_the_configured_timeout(tmp_path: Path,
                                                                          base: EffectiveConfig) -> None:
    clock = FakeClock()
    inner = FakeGateway({"assess": [FakeResponse(text="ok")]}, clock=clock)
    sched = FaultSchedule.model_validate({"id": "T", "llm": [{"match": {"stage": "assess", "attempt": 0},
                                                              "fault": {"type": "hang"}}]})
    gw = FaultInjectingLLMGateway(inner, sched, clock=clock, policy=LLMSettings(timeout_s=1800))
    res = await gw.call(req())
    assert res.text == "ok" and 1800 <= clock.monotonic() < 1900 and res.attempts[0].outcome == "LLMTimeoutError"


async def test_fake_gateway_refuses_a_call_without_time(base: EffectiveConfig) -> None:
    gw = FakeGateway({"assess": [FakeResponse(text="x")]})
    attach_runtime(gw, deadline(415)[0])
    with pytest.raises(LLMDeadlineError):
        await gw.call(req())
    assert gw.calls == []


def test_research_keeps_the_assess_reserve(tmp_path: Path, base: EffectiveConfig) -> None:
    from sit_review_agent.context import RunContext
    from sit_review_agent.phases.research import _ResearchRun
    from sit_review_agent.progress import NullProgress
    from sit_review_agent.prompts import PromptBundle
    from sit_review_agent.state.decision_registry import DecisionRegistry
    from sit_review_agent.state.evidence_ledger import EvidenceLedger
    from sit_review_agent.state.run_state import RunState

    clock = FakeClock()
    rd = RunDir(tmp_path / "run").create()
    ctx = RunContext(config=base, run_dir=rd, state=RunState(run_id="r", created_utc="2026-10-02T09:00:00Z"),
                     llm=FakeGateway({}), tools=None, ledger=EvidenceLedger(rd, clock=clock),
                     registry=DecisionRegistry(), prompts=PromptBundle.load(), clock=clock, progress=NullProgress())
    sr = base.stop_rules
    assert _ResearchRun(ctx).params.report_reserve_seconds == sr.report_reserve_seconds + sr.assess_reserve_seconds


async def test_deadline_before_assess_is_disclosed_as_out_of_time(tmp_path: Path, base: EffectiveConfig) -> None:
    from sit_review_agent.context import RunContext
    from sit_review_agent.orchestrator import Orchestrator
    from sit_review_agent.progress import NullProgress
    from sit_review_agent.prompts import PromptBundle
    from sit_review_agent.state.decision_registry import DecisionRegistry
    from sit_review_agent.state.evidence_ledger import EvidenceLedger
    from sit_review_agent.state.run_state import RunState
    from sit_review_agent.states import PHASE_ORDER

    clock, ran = FakeClock(), []

    class Step:
        def __init__(self, name: PhaseName) -> None:
            self.name = name

        async def run(self, ctx: Any) -> Any:
            ran.append(self.name.value)
            if self.name is PhaseName.RESEARCH:
                clock.advance(base.stop_rules.deadline_seconds)        # research overran the deadline
            return ctx

    rd = RunDir(tmp_path / "run").create()
    ctx = RunContext(config=base, run_dir=rd, state=RunState(run_id="r", created_utc="2026-10-02T09:00:00Z"),
                     llm=FakeGateway({}), tools=None, ledger=EvidenceLedger(rd, clock=clock),
                     registry=DecisionRegistry(), prompts=PromptBundle.load(), clock=clock, progress=NullProgress())
    await Orchestrator({p: Step(p) for p in PHASE_ORDER}).run(ctx)
    assert "assess" not in ran and ran[-2:] == ["verify", "report"]
    events = [d.event for d in ctx.state.degradations]
    assert any(e.startswith(OUT_OF_TIME_BEFORE_ASSESSMENT) for e in events)


def test_not_assessed_verdict_is_never_a_certification() -> None:
    from sit_review_agent.phases.report import assessment_cut, not_assessed_verdict

    v = not_assessed_verdict()
    assert v.label.value == "not_fit" and v.confidence == 0.0 and v.rationale.startswith("Not assessed")
    assert assessment_cut([f"{OUT_OF_TIME_BEFORE_ASSESSMENT}: the assess call was cut"])
    assert not assessment_cut(["stop rule deadline (deadline) before refine"])


# ============================================================================= NET-02: first call, no network


async def test_claude_code_first_call_connection_errors_get_a_short_window(tmp_path: Path,
                                                                           base: EffectiveConfig) -> None:
    gw, runner, _, clock = claude(tmp_path, base, *[cli_err("API Error: Connection error (fetch failed)")] * 5)
    with pytest.raises(LLMConnectionError, match="^no network") as ei:
        await gw.call(req(PhaseName.UNDERSTAND))
    assert 2 <= len(runner.calls) < base.agent.llm.max_retries + 1 and clock.monotonic() <= 10
    assert "resume" in str(ei.value) and ei.value.exit_code == 3


async def test_claude_code_later_calls_keep_the_full_retry_policy(tmp_path: Path, base: EffectiveConfig) -> None:
    errors = [cli_err("API Error: Connection error (fetch failed)")] * 5
    gw, runner, _, _ = claude(tmp_path, base, cli_ok(), *errors)
    await gw.call(req(PhaseName.UNDERSTAND))
    with pytest.raises(LLMConnectionError) as ei:
        await gw.call(req(PhaseName.PLAN))
    assert not str(ei.value).startswith("no network")
    assert len(runner.calls) == 1 + base.agent.llm.max_retries + 1   # the whole budget


async def test_claude_code_overload_on_the_first_call_is_not_cut_short(tmp_path: Path, base: EffectiveConfig) -> None:
    gw, runner, _, _ = claude(tmp_path, base, *[cli_err("API Error: 529 overloaded")] * 5)
    with pytest.raises(LLMOverloadedError):
        await gw.call(req(PhaseName.UNDERSTAND))
    assert len(runner.calls) == base.agent.llm.max_retries + 1       # 429/529/5xx keep the full policy


async def test_anthropic_first_call_connection_errors_get_a_short_window(tmp_path: Path,
                                                                         base: EffectiveConfig) -> None:
    gw, msgs, clock = anthropic_gw(tmp_path, base, *[conn_error() for _ in range(5)])
    with pytest.raises(LLMConnectionError, match="^no network"):
        await gw.call(req(PhaseName.UNDERSTAND))
    assert 2 <= msgs.calls < base.agent.llm.max_retries + 1 and clock.monotonic() <= 10


async def test_anthropic_preflight_offline_is_no_network(tmp_path: Path, base: EffectiveConfig) -> None:
    gw, msgs, _ = anthropic_gw(tmp_path, base, conn_error())
    with pytest.raises(LLMConnectionError, match="^no network"):
        await gw.preflight()
    assert msgs.calls == 1                                            # no retries


class _Probe(FakeGateway):
    """A backend with ``preflight`` and ``models_retrieve`` that records their order."""

    def __init__(self, order: list[str], fail: Exception | None = None, **kw: Any) -> None:
        super().__init__(**kw)
        self.order, self.fail = order, fail

    async def preflight(self) -> None:
        self.order.append("preflight")
        if self.fail is not None:
            raise self.fail

    async def models_retrieve(self) -> dict[str, Any]:
        self.order.append("models_retrieve")
        return {"id": "claude-opus-5-5", "max_input_tokens": 1_000_000}


def _live_no_tools(tmp_path: Path) -> EffectiveConfig:
    cfg = load_config(overrides=ConfigOverrides(no_tools=True))
    return cfg.model_copy(update={"agent": cfg.agent.model_copy(update={"run_root": str(tmp_path / "runs"),
                                                                        "transport": Transport.LIVE})})


async def test_preflight_runs_before_models_retrieve_and_stops_the_run_offline(tmp_path: Path) -> None:
    from sit_review_agent.orchestrator import RunRequest, run_review
    from sit_review_agent.progress import NullProgress
    from sit_review_agent.selftest import FIXTURE_DIR

    order: list[str] = []
    cfg = _live_no_tools(tmp_path)
    out = await run_review(RunRequest(pdf=FIXTURE_DIR / "design.pages.txt", config=cfg, run_id="offline"),
                           llm_factory=lambda rd, c, p: _Probe(order, LLMConnectionError("no network: test"),
                                                               script={}, run_dir=rd, clock=c),
                           clock=FakeClock(), progress=NullProgress())
    assert out.exit_code == 3 and order == ["preflight"]               # models.retrieve never retried offline
    fail = json.loads((out.run_dir / "failure.json").read_text(encoding="utf-8"))
    assert fail["error"] == "LLMConnectionError" and fail["message"].startswith("no network")


async def test_preflight_then_models_retrieve_when_online(tmp_path: Path) -> None:
    from sit_review_agent.orchestrator import RunRequest, run_review
    from sit_review_agent.progress import NullProgress
    from sit_review_agent.selftest import FIXTURE_DIR, fixture_script

    order: list[str] = []
    cfg = _live_no_tools(tmp_path)
    out = await run_review(RunRequest(pdf=FIXTURE_DIR / "design.pages.txt", config=cfg, run_id="online",
                                      plan_only=True),
                           llm_factory=lambda rd, c, p: _Probe(order, script=fixture_script(cfg.criteria.ids()),
                                                               run_dir=rd, clock=c),
                           clock=FakeClock(), progress=NullProgress(), stdout=__import__("io").StringIO())
    assert out.exit_code == 0 and order == ["preflight", "models_retrieve"]


# ============================================================================= INF-08: missing MCP key


def test_inf08_missing_key_is_a_usage_error_naming_the_fix(base: EffectiveConfig,
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    from sit_review_agent.orchestrator import _run_check_tool_key

    monkeypatch.delenv("SIT_MCP_API_KEY", raising=False)
    live = base.model_copy(update={"agent": base.agent.model_copy(update={"transport": Transport.LIVE})})
    with pytest.raises(ConfigError) as ei:
        _run_check_tool_key(live)
    assert "SIT_MCP_API_KEY" in str(ei.value) and "--no-tools" in str(ei.value) and ei.value.exit_code == 2
    monkeypatch.setenv("SIT_MCP_API_KEY", "   ")
    with pytest.raises(ConfigError):
        _run_check_tool_key(live)                                    # blank is missing


def test_inf08_missing_key_ok_when_no_live_tools(base: EffectiveConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    from sit_review_agent.orchestrator import _run_check_tool_key

    monkeypatch.delenv("SIT_MCP_API_KEY", raising=False)
    for transport in (Transport.REPLAY, Transport.FAKE):
        _run_check_tool_key(base.model_copy(update={"agent": base.agent.model_copy(update={"transport": transport})}))
    no_tools = load_config(overrides=ConfigOverrides(no_tools=True, transport=Transport.LIVE))
    _run_check_tool_key(no_tools)
    monkeypatch.setenv("SIT_MCP_API_KEY", "set-but-not-real")
    _run_check_tool_key(base.model_copy(update={"agent": base.agent.model_copy(update={"transport": Transport.LIVE})}))


async def test_inf08_missing_key_stops_before_any_model_call(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from sit_review_agent.orchestrator import RunRequest, run_review
    from sit_review_agent.selftest import FIXTURE_DIR

    monkeypatch.delenv("SIT_MCP_API_KEY", raising=False)
    cfg = load_config()
    cfg = cfg.model_copy(update={"agent": cfg.agent.model_copy(update={"run_root": str(tmp_path / "runs"),
                                                                       "transport": Transport.LIVE})})
    built: list[str] = []
    with pytest.raises(ConfigError, match="SIT_MCP_API_KEY"):
        await run_review(RunRequest(pdf=FIXTURE_DIR / "design.pages.txt", config=cfg, run_id="nokey"),
                         llm_factory=lambda rd, c, p: built.append("llm"), clock=FakeClock())
    assert built == [] and not (tmp_path / "runs" / "nokey").exists()


# ============================================================================= LLM-10: size before sending


def test_context_estimate_and_error_name_the_document_size() -> None:
    guard = ContextGuard(window_tokens=10_000, pages=lambda: 12)
    small = guard.estimate(req(text="x" * 3_000))
    assert not small.over and small.limit_tokens == int(10_000 * CONTEXT_MARGIN)
    with pytest.raises(LLMContextTooLongError) as ei:
        guard.check(req(text="y" * 30_000), model="claude-opus-5-5")
    msg = str(ei.value)
    assert "was not sent" in msg and "30,0" in msg and "12 pages" in msg and "8,000 tokens" in msg
    assert ei.value.exit_code == 2 and ei.value.estimated_tokens > ei.value.limit_tokens


def test_native_pdf_blocks_count_only_where_they_are_sent() -> None:
    guard = ContextGuard(window_tokens=100_000, pages=lambda: 60)       # 60 pages x 2,000 tokens = 120k
    r = req(text="short", pdf_b64="QUJD" * 10)
    assert guard.estimate(r, native_pdf=True).over
    assert not guard.estimate(r, native_pdf=False).over                 # claude_code drops PDF blocks


async def test_both_live_gateways_refuse_an_oversize_request_before_sending(tmp_path: Path,
                                                                            base: EffectiveConfig) -> None:
    limits = RuntimeLimits(context=ContextGuard(window_tokens=1_000))
    cc, runner, _, _ = claude(tmp_path / "cc", base, cli_ok())
    attach_runtime(cc, limits)
    with pytest.raises(LLMContextTooLongError):
        await cc.call(req(text="z" * 10_000))
    assert runner.calls == []
    api, msgs, _ = anthropic_gw(tmp_path / "api", base, "unused")
    attach_runtime(api, limits)
    with pytest.raises(LLMContextTooLongError):
        await api.call(req(text="z" * 10_000))
    assert msgs.calls == 0


def test_context_window_comes_from_config_retrieve_or_model(base: EffectiveConfig) -> None:
    assert build_runtime(base, lambda: 0.0).context.window_tokens == 1_000_000              # type: ignore[union-attr]
    assert build_runtime(base, lambda: 0.0, retrieved_window=200_000).context.window_tokens == 200_000  # type: ignore[union-attr]
    cfg = base.model_copy(update={"agent": base.agent.model_copy(
        update={"llm": base.agent.llm.model_copy(update={"context_window_tokens": 150_000})})})
    assert build_runtime(cfg, lambda: 0.0, retrieved_window=200_000).context.window_tokens == 150_000  # type: ignore[union-attr]


# ============================================================================= OPS-10: latency logged


async def test_claude_code_logs_latency_on_success(tmp_path: Path, base: EffectiveConfig) -> None:
    gw, _, rd, _ = claude(tmp_path, base, cli_ok())
    await gw.call(req())
    ok = [e for e in log(rd) if e["outcome"] == "ok"]
    assert ok and isinstance(ok[0]["elapsed_s"], float) and ok[0]["timeout_s"] == 1800


# ============================================================================= process faults


def test_loader_rejects_malformed_process_entries(tmp_path: Path) -> None:
    for body in ("process: [{type: raise_in_stage, stage: nowhere}]",
                 "process: [{type: latency, stage: assess, seconds: 1}]",
                 "process: [{type: sigint_in_stage, stage: research, at: middle}]"):
        p = tmp_path / "bad.yaml"
        p.write_text(f"id: BAD\n{body}\n", encoding="utf-8")
        with pytest.raises(ConfigError):
            load_fault_schedule(p)
    ok = tmp_path / "ok.yaml"
    ok.write_text("id: OK\nprocess: [{type: clock_jump, stage: research, seconds: 30}]\n", encoding="utf-8")
    assert load_fault_schedule(ok).process[0].type.value == "clock_jump"


@pytest.mark.parametrize("sid, code", [("BEH-25", 4), ("OPS-04", 130)])
def test_cli_faults_apply_process_entries(sid: str, code: int, tmp_path: Path,
                                         monkeypatch: pytest.MonkeyPatch) -> None:
    """`sit-review run --faults BEH-25 / OPS-04` used to ignore `process:` entries and run clean."""
    from typer.testing import CliRunner

    from sit_review_agent.cli import app
    from sit_review_agent.selftest import FIXTURE_DIR

    monkeypatch.setenv("SIT_MCP_API_KEY", "not-a-real-key-offline-drill")
    cfg = tmp_path / "config"
    shutil.copytree(config_dir(), cfg)
    agent = cfg / "agent.yaml"
    agent.write_text(agent.read_text(encoding="utf-8").replace("run_root: runs", f"run_root: {tmp_path / 'runs'}"),
                     encoding="utf-8")
    cassettes = repo_root() / "tests" / "robustness" / "fixtures" / "cassettes"
    res = CliRunner().invoke(app, ["run", str(FIXTURE_DIR / "design.pages.txt"), "--config", str(cfg),
                                   "--transport", "fake", "--replay", str(cassettes), "--faults", sid,
                                   "--run-id", f"cli-{sid}"])
    assert res.exit_code == code, res.output
    assert "Traceback" not in res.output
    rd = tmp_path / "runs" / f"cli-{sid}"
    fail = json.loads((rd / "failure.json").read_text(encoding="utf-8"))
    assert fail["exit_code"] == code and not (rd / "report.json").exists()
    if sid == "BEH-25":
        assert fail["phase"] == "assess" and (rd / "report.partial.md").is_file()
    else:
        assert fail["completed_phases"] == ["ingest", "understand", "plan"]
    assert "armed" in (rd / "progress.log").read_text(encoding="utf-8")


# ============================================================================= OVF-07: authority hosts in config


def test_authority_hosts_come_from_config_without_the_sample_stack() -> None:
    from sit_review_agent.tools.sources import classify_authority, default_authority_hosts

    hosts = default_authority_hosts()
    listed = {h for name in AuthorityHosts.model_fields for h in getattr(hosts, name)}
    assert hosts.vendor_docs and hosts.standards and not set(SAMPLE_HOSTS) & listed
    assert classify_authority("https://www.iso.org/standard/1") is SourceAuthority.PRIMARY_OFFICIAL
    assert classify_authority("https://pgvector.dev/docs") is SourceAuthority.INFORMAL
    custom = AuthorityHosts(vendor_docs=["vendor.example"])
    assert classify_authority("https://vendor.example/x", custom) is SourceAuthority.PRIMARY_OFFICIAL
    assert classify_authority("https://www.iso.org/x", custom) is SourceAuthority.INFORMAL
    code = (repo_root() / "agent" / "sit_review_agent" / "tools" / "sources.py").read_text(encoding="utf-8")
    assert not [h for h in SAMPLE_HOSTS if h in code]
    assert load_config().url_policy.authority == hosts


def test_timeout_and_deadline_errors_keep_their_exit_codes() -> None:
    assert issubclass(LLMDeadlineError, LLMTimeoutError) and LLMDeadlineError("x").exit_code == 3
    assert LLMConnectionError("x").exit_code == 3 and LLMContextTooLongError("x").exit_code == 2
