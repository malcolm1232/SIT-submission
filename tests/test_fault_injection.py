"""Workstream B, phase 2: robustness fault injection at L0 (virtual clock, no network).

The runbook §7 drills: INF-01 cold start, INF-07 shared-key 401 / INF-24 all tools down,
LLM-01/02/03 rate limit / spend cap / overload, LLM-06 refusal, NET-01 network lost mid-run; plus
the other P0 tool faults the policy layer must absorb (INF-03/04/05/09/10/11/18/19/25, INF-12/13/14).
Faults are injected BELOW the policy (``build_tool_gateway(..., fault_schedule=...)``) and below the
LLM retry policy (``FaultInjectingLLMGateway``), so the policies are what is tested.

Covers the ``tests/test_pending.py`` entry ``test_fault_injection_drills``.
"""

from __future__ import annotations

import asyncio
import contextlib
import heapq
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from mcp import types

from sit_review_agent.clock import FakeClock, isoformat_z
from sit_review_agent.config import ConfigOverrides, EffectiveConfig, load_config
from sit_review_agent.context import RunContext
from sit_review_agent.errors import (
    ExitCode,
    LLMAuthError,
    LLMOverloadedError,
    LLMRateLimitError,
    LLMSchemaError,
    LLMTimeoutError,
    LLMTruncatedError,
    LLMUnavailableError,
)
from sit_review_agent.ingest.pdf import Document
from sit_review_agent.llm.gateway import FakeGateway, FakeResponse, FaultInjectingLLMGateway, LLMRequest, ToolUse
from sit_review_agent.llm.outputs import PlanOutput, QuestionAnswer, ResearchOutput
from sit_review_agent.models import DegradationType, StopReasonCode, ToolCallStatus
from sit_review_agent.orchestrator import Orchestrator
from sit_review_agent.phases.research import ResearchPhase
from sit_review_agent.progress import NullProgress
from sit_review_agent.prompts import PromptBundle
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.state.decision_registry import DecisionRegistry
from sit_review_agent.state.evidence_ledger import EvidenceLedger
from sit_review_agent.state.run_state import ResearchPlan, ResearchQuestion, RunState
from sit_review_agent.states import PHASE_ORDER, PhaseName
from sit_review_agent.tools.faults import FaultSchedule, load_fault_schedule
from sit_review_agent.tools.gateway import (
    FakeToolGateway,
    FaultInjectingGateway,
    MCPToolGateway,
    PolicyToolGateway,
    ToolErrorClass,
    ToolSpec,
    build_tool_gateway,
    qualify,
)
from sit_review_agent.tools.mcp_client import find_layer

R = PhaseName.RESEARCH
KEY = "CANARY-MCP-7f3a9c0d1e2f"
SEARCH = qualify("mcp-internet-search", "search")
SCHOLAR = qualify("mcp-research-information", "search_works")
SPECS = [ToolSpec("mcp-internet-search", "search", "Web search", {"type": "object"}, "search"),
         ToolSpec("mcp-research-information", "search_works", "Scholarly search", {"type": "object"}, "scholarly")]
HANDLERS = {
    SEARCH: lambda a: ("1. Vendor docs\n   URL: https://docs.vendor.example/"
                       f"{a.get('query', 'q').replace(' ', '-')}\n   ok"),
    SCHOLAR: lambda a: json.dumps({"results": [{"title": "Paper", "doi": f"10.1/{a.get('query', 'q')}",
                                                "abstract": "Measured.", "venue": "V"}]}),
}
DOC = "[[PAGE 1]]\n1 Intro\nThe service sends 5,000 emails per day and filters ten million vectors.\n"


class SchedulingClock(FakeClock):
    """Virtual clock whose concurrent sleeps overlap (``FakeClock.sleep`` advances immediately, so
    parallel sleeps would add up). Every sleeper registers a wake-up time; once all runnable tasks
    have had a chance to reach their next sleep, time jumps to the earliest wake-up."""

    def __init__(self) -> None:
        super().__init__()
        self._heap: list[tuple[float, int, asyncio.Future[None]]] = []
        self._seq = 0
        self._driver: asyncio.Task[None] | None = None

    async def sleep(self, seconds: float) -> None:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        self._seq += 1
        heapq.heappush(self._heap, (self.monotonic() + max(0.0, seconds), self._seq, fut))
        if self._driver is None or self._driver.done():
            self._driver = loop.create_task(self._drive())
        await fut

    async def _drive(self) -> None:
        while self._heap:
            for _ in range(50):
                await asyncio.sleep(0)
            if not self._heap:
                return
            at, _, fut = heapq.heappop(self._heap)
            if at > self.monotonic():
                self.advance(at - self.monotonic())
            if not fut.done():
                fut.set_result(None)


def schedule(**kw: Any) -> FaultSchedule:
    return FaultSchedule.model_validate({"id": kw.pop("id", "TEST"), "seed": kw.pop("seed", 42), **kw})


def config(**overrides: Any) -> EffectiveConfig:
    return load_config(overrides=ConfigOverrides(**overrides)) if overrides else load_config()


def tool_stack(tmp_path: Path, sched: FaultSchedule, clock: FakeClock, *, c: EffectiveConfig | None = None,
               base: Any = None) -> tuple[Any, FakeToolGateway, PolicyToolGateway]:
    c = c or config()
    fake = base or FakeToolGateway(SPECS, HANDLERS, clock=clock)
    rd = RunDir(tmp_path / "tools-run").create()
    gw = build_tool_gateway(c, rd, clock=clock, progress=NullProgress(), fault_schedule=sched, base=fake)
    return gw, fake, find_layer(gw, PolicyToolGateway)


# =============================================================================== INF-01 cold start


class SlowSession:
    def __init__(self, clock: FakeClock, counts: dict[str, int], server: str) -> None:
        self.clock, self.counts, self.server = clock, counts, server

    async def initialize(self) -> Any:
        self.counts[self.server] = self.counts.get(self.server, 0) + 1
        await self.clock.sleep(90)                                       # scaled-to-zero container waking
        return types.InitializeResult(protocol_version="2025-11-25", capabilities=types.ServerCapabilities(),
                                      server_info=types.Implementation(name=self.server, version="0"))

    async def list_tools(self, *, params: Any = None) -> Any:
        return types.ListToolsResult(tools=[types.Tool(name="search", input_schema={"type": "object"})])

    async def call_tool(self, name: str, arguments: Any = None, read_timeout_seconds: float | None = None) -> Any:
        return types.CallToolResult(content=[types.TextContent(type="text", text="ok")], is_error=False)


async def test_inf01_warm_up_runs_in_parallel_with_one_attempt_per_server() -> None:
    c = config()
    servers = [s.model_copy(update={"enabled": True, "allow_tools": ["*"]}) for s in c.tools.servers]
    tools = c.tools.model_copy(update={"servers": servers})
    clock = SchedulingClock()
    progress = NullProgress()
    counts: dict[str, int] = {}
    gw = MCPToolGateway(tools, c.endpoints.servers, clock=clock, progress=progress, api_key=KEY)

    @contextlib.asynccontextmanager
    async def factory(server: str, url: str, headers: dict[str, str], timeout_s: float,
                      on_response: Any) -> AsyncIterator[SlowSession]:
        assert timeout_s == 150                                          # the cold-start allowance
        yield SlowSession(clock, counts, server)

    gw.session_factory = factory
    health = await gw.warm_up()
    assert all(h.value == "ok" for h in health.values()) and len(health) == 4
    assert clock.monotonic() <= 1.2 * 90                                 # four cold starts overlapped
    assert counts == {s.name: 1 for s in servers}                        # at most 2 attempts per server
    waking = [e.message for e in progress.events if e.message.startswith("waking")]
    assert len(waking) == 4 and all("(~90 s)" in m for m in waking)
    await gw.aclose()


def research_ctx(tmp_path: Path, script: list[FakeResponse], tools: Any, *, clock: FakeClock,
                 c: EffectiveConfig | None = None, llm: Any = None) -> RunContext:
    c = c or config()
    rd = RunDir(tmp_path / "run").create()
    state = RunState(run_id="run", created_utc=isoformat_z(clock.now_utc()))
    state.plan = ResearchPlan(questions=[
        ResearchQuestion(id="RQ-001", criterion_id="c", question="Mail limit?", rationale="r", needs_external=True,
                         capability="search", queries=["limit"], section_refs=["1"]),
        ResearchQuestion(id="RQ-002", criterion_id="c", question="Latency?", rationale="r", needs_external=True,
                         capability="scholarly", queries=["latency"], section_refs=["1"])])
    state.budget.started_monotonic = clock.monotonic()
    state.current_phase = R
    return RunContext(config=c, run_dir=rd, state=state, llm=llm or FakeGateway({R: script}, clock=clock),
                      tools=tools, ledger=EvidenceLedger(rd, clock=clock), registry=DecisionRegistry(),
                      prompts=PromptBundle.load(), clock=clock, progress=NullProgress(),
                      documents={"DOC-001": Document.from_page_marked_text(DOC, doc_id="DOC-001")})


def both_then_final(n: int = 1) -> list[FakeResponse]:
    return [FakeResponse(tool_uses=[ToolUse("t1", SEARCH, {"query": "limit"}),
                                    ToolUse("t2", SCHOLAR, {"query": "latency"})]),
            FakeResponse(parsed=ResearchOutput(answers=[
                QuestionAnswer(question_id="RQ-001", status="partial", summary="s", evidence_ids=["EV-001"])],
                stop_requested=False, stop_rationale="r"))]


async def test_inf01_cold_first_calls_overlap_in_the_research_loop(tmp_path: Path) -> None:
    clock = SchedulingClock()
    sched = schedule(id="INF-01", mcp=[{"match": {"server": "*", "call_index": 0},
                                        "fault": {"type": "latency", "seconds": 90}}])
    gw, fake, _ = tool_stack(tmp_path, sched, clock)
    base_cfg = config()
    one = base_cfg.stop_rules.model_copy(update={"max_research_iterations": 1})
    c = base_cfg.model_copy(update={"stop_rules": one})
    ctx = await ResearchPhase().run(research_ctx(tmp_path, both_then_final(), gw, clock=clock, c=c))
    assert clock.monotonic() <= 1.2 * 90
    assert {e.tool.server for e in ctx.ledger} == {"mcp-internet-search", "mcp-research-information"}
    assert all(c.status is ToolCallStatus.OK for c in ctx.state.tool_calls)


# =============================================================================== INF-07 / INF-24


async def test_inf07_shared_key_401_disables_every_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIT_MCP_API_KEY", KEY)
    yaml_path = tmp_path / "INF-07.yaml"
    yaml_path.write_text("id: INF-07\nmcp:\n  - match: {server: '*'}\n    fault: {type: auth, status: 401}\n")
    sched = load_fault_schedule(yaml_path)
    clock = FakeClock()
    gw, fake, pol = tool_stack(tmp_path, sched, clock)
    script = [*both_then_final()[:1],
              FakeResponse(parsed=ResearchOutput(answers=[], stop_requested=True, stop_rationale="no tools"))]
    ctx = await ResearchPhase().run(research_ctx(tmp_path, script, gw, clock=clock))
    inj = find_layer(gw, FaultInjectingGateway)
    attempts = [r for r in inj.injected if r["fault"] == "auth"]
    assert len(attempts) <= 4 and pol.auth_disabled                     # 2 parallel calls, <= 1 confirmation each
    assert all(len(json.loads(line)["attempts"]) <= 2
               for line in (tmp_path / "tools-run" / "tools.jsonl").read_text().splitlines())
    assert fake.calls == []
    assert ctx.state.stop_reason.code is StopReasonCode.TOOL_FAILURE
    events = " ".join(d.event for d in ctx.state.degradations)
    assert "SIT_MCP_API_KEY" in events and "No external research was possible" in events
    assert KEY not in events and KEY not in (tmp_path / "tools-run" / "tools.jsonl").read_text()
    assert len(ctx.ledger) == 0 and [q.status for q in ctx.state.plan.questions] == ["unanswered", "unanswered"]
    assert await gw.list_tools() == []
    later = await gw.call(SCHOLAR, {"query": "x"})
    assert later.error_class is ToolErrorClass.AUTH and len(inj.injected) == len(attempts)   # never sent


async def test_inf24_all_servers_down_is_a_doc_only_review(tmp_path: Path) -> None:
    clock = FakeClock()
    sched = schedule(id="INF-24", mcp=[{"match": {"server": "*"}, "fault": {"type": "down"}}])
    gw, fake, pol = tool_stack(tmp_path, sched, clock)
    script = [FakeResponse(tool_uses=[ToolUse(f"t{i}", SEARCH if i % 2 else SCHOLAR, {"query": f"q{i}"})
                                      for i in range(1, 7)]),
              FakeResponse(parsed=ResearchOutput(answers=[], stop_requested=True, stop_rationale="down"))]
    ctx = await ResearchPhase().run(research_ctx(tmp_path, script, gw, clock=clock))
    assert pol.server_open("mcp-internet-search") and pol.server_open("mcp-research-information")
    assert ctx.state.stop_reason.code is StopReasonCode.TOOL_FAILURE and len(ctx.ledger) == 0
    assert any(d.event.startswith("No external research was possible") for d in ctx.state.degradations)
    assert any("circuit breaker open" in d.event for d in ctx.state.degradations)
    assert clock.monotonic() < 150                                       # breakers, not 4 x 150 s serial waits


# =============================================================================== policy under faults


async def test_inf04_persistent_500_three_attempts_then_breaker(tmp_path: Path) -> None:
    clock = FakeClock()
    sched = schedule(id="INF-04", mcp=[{"match": {"server": "mcp-research-information"},
                                        "fault": {"type": "http_status", "status": 500}}])
    gw, fake, pol = tool_stack(tmp_path, sched, clock)
    for i in range(3):
        res = await gw.call(SCHOLAR, {"query": f"q{i}"})
        assert res.error_class is ToolErrorClass.HTTP_5XX and len(res.attempts) == 3
    assert pol.server_open("mcp-research-information")
    refused = await gw.call(SCHOLAR, {"query": "q9"})
    assert refused.error_class is ToolErrorClass.SERVER_DOWN
    assert [t.server for t in await gw.list_tools()] == ["mcp-internet-search"]   # fallback capability remains
    assert (await gw.call(SEARCH, {"query": "fallback"})).ok


async def test_inf05_retry_after_is_honoured_and_concurrency_lowered(tmp_path: Path) -> None:
    clock = FakeClock()
    sched = schedule(id="INF-05", mcp=[{"match": {"server": "mcp-internet-search", "call_index": 0},
                                        "fault": {"type": "http_status", "status": 429, "retry_after": 20}}])
    gw, fake, pol = tool_stack(tmp_path, sched, clock)
    res = await gw.call(SEARCH, {"query": "q"})
    assert res.ok and len(res.attempts) == 2 and clock.monotonic() >= 20
    assert pol._caps["mcp-internet-search"] == 1                          # noqa: SLF001


async def test_inf09_session_expired_one_reinitialise(tmp_path: Path) -> None:
    clock = FakeClock()
    sched = schedule(id="INF-09", mcp=[{"match": {"server": "mcp-internet-search", "call_index": 1},
                                        "fault": {"type": "session_expired"}}])
    gw, fake, _ = tool_stack(tmp_path, sched, clock)
    assert (await gw.call(SEARCH, {"query": "a"})).ok
    res = await gw.call(SEARCH, {"query": "b"})
    assert res.ok and [a.error_class for a in res.attempts] == [ToolErrorClass.SESSION_EXPIRED, None]
    assert clock.monotonic() == 0                                         # replayed at once, no backoff


@pytest.mark.parametrize("kind", ["html", "non_json", "truncated_json", "wrong_id"])
async def test_inf10_malformed_body_retried_once(tmp_path: Path, kind: str) -> None:
    clock = FakeClock()
    sched = schedule(id="INF-10", mcp=[{"match": {"server": "mcp-internet-search"},
                                        "fault": {"type": "malformed_body", "kind": kind}}])
    gw, fake, _ = tool_stack(tmp_path, sched, clock)
    res = await gw.call(SEARCH, {"query": "q"})
    assert res.error_class is ToolErrorClass.MALFORMED and len(res.attempts) == 2 and kind in res.error_message
    assert fake.calls == []


async def test_inf11_tool_error_not_retried_then_unusable(tmp_path: Path) -> None:
    clock = FakeClock()
    msg = "rejects all inputs because no allowed local root or remote domains are configured"
    sched = schedule(id="INF-11", mcp=[{"match": {"tool": "search_works"}, "fault": {"type": "tool_error",
                                                                                      "message": msg}}])
    gw, fake, pol = tool_stack(tmp_path, sched, clock)
    first = await gw.call(SCHOLAR, {"query": "a"})
    assert first.error_class is ToolErrorClass.TOOL_ERROR and len(first.attempts) == 1 and msg in first.text
    await gw.call(SCHOLAR, {"query": "b"})
    third = await gw.call(SCHOLAR, {"query": "c"})
    assert third.error_class is ToolErrorClass.NOT_ALLOWED and SCHOLAR in pol.unusable_tools
    assert SCHOLAR not in [t.qualified_name for t in await gw.list_tools()]
    assert not pol.server_open("mcp-research-information")                # the server itself answered


async def test_inf19_hang_times_out_within_the_read_timeout(tmp_path: Path) -> None:
    clock = FakeClock()
    sched = schedule(id="INF-19", mcp=[{"match": {"server": "mcp-internet-search", "call_index": 0},
                                        "fault": {"type": "hang"}}])
    gw, fake, _ = tool_stack(tmp_path, sched, clock)
    res = await gw.call(SEARCH, {"query": "q"})
    assert res.ok and res.attempts[0].error_class is ToolErrorClass.TIMEOUT
    assert res.attempts[0].elapsed_s <= 60 + 1                            # call_timeout_s + 1 s


async def test_inf03_and_inf25_breaker_opens_then_half_open_probe_recovers(tmp_path: Path) -> None:
    clock = FakeClock()
    sched = schedule(id="INF-25", mcp=[{"match": {"server": "mcp-research-information"},
                                        "fault": {"type": "down", "duration_seconds": 180}}])
    gw, fake, pol = tool_stack(tmp_path, sched, clock)
    for i in range(3):
        assert not (await gw.call(SCHOLAR, {"query": f"q{i}"})).ok
    assert pol.server_open("mcp-research-information")
    clock.advance(200)                                                    # past the outage and the cooldown
    probe = await gw.call(SCHOLAR, {"query": "after"})
    assert probe.ok and not pol.server_open("mcp-research-information")


async def test_inf18_flaky_absorbed_by_retries_for_ten_seeds(tmp_path: Path) -> None:
    ok = total = 0
    for seed in range(1, 11):
        clock = FakeClock()
        sched = schedule(id="INF-18", seed=seed, mcp=[{"match": {"server": "*"}, "fault": {
            "type": "flaky", "p": 0.3, "inner": [{"type": "http_status", "status": 502},
                                                 {"type": "connection_reset"}, {"type": "hang"}]}}])
        gw, _, _ = tool_stack(tmp_path / f"s{seed}", sched, clock)
        for i in range(10):
            res = await gw.call(SEARCH if i % 2 else SCHOLAR, {"query": f"q{i}"})
            ok += res.ok
            total += 1
    assert ok / total >= 0.9


async def test_inf12_13_14_content_faults(tmp_path: Path) -> None:
    drift = tmp_path / "drift.json"
    drift.write_text(json.dumps([{"name": "search_v2", "description": "renamed", "input_schema": {"type": "object"}}]))
    clock = FakeClock()
    sched = schedule(id="MIX", mcp=[
        {"match": {"server": "mcp-internet-search"}, "fault": {"type": "schema_drift", "tools_list": str(drift)}},
        {"match": {"tool": "search", "nth": [0]}, "fault": {"type": "empty_result"}},
        {"match": {"tool": "search", "nth": [1]}, "fault": {"type": "truncate_text", "fraction": 0.5}},
        {"match": {"tool": "search_works"}, "fault": {"type": "partial_result", "keep": 1}}])
    gw, _, _ = tool_stack(tmp_path, sched, clock)
    names = sorted(t.qualified_name for t in await gw.list_tools())
    assert names == ["mcp-internet-search__search_v2", SCHOLAR]
    empty = await gw.call(SEARCH, {"query": "a"})
    assert empty.ok and empty.text == ""
    half = await gw.call(SEARCH, {"query": "abcdef"})
    assert half.ok and len(half.text) < len(HANDLERS[SEARCH]({"query": "abcdef"}))
    part = await gw.call(SCHOLAR, {"query": "p"})
    assert part.ok and len(json.loads(part.text)["results"]) == 1


async def test_after_seconds_and_offline_window(tmp_path: Path) -> None:
    clock = FakeClock()
    sched = schedule(id="NET", network=[{"type": "offline", "from_seconds": 100, "duration_seconds": 50}])
    gw, fake, _ = tool_stack(tmp_path, sched, clock)
    assert (await gw.call(SEARCH, {"query": "a"})).ok
    clock.advance(110)
    off = await gw.call(SEARCH, {"query": "b"})
    assert not off.ok and off.error_class is ToolErrorClass.CONNECTION and "offline" in off.error_message
    clock.advance(60)
    assert (await gw.call(SEARCH, {"query": "c"})).ok


# =============================================================================== LLM faults


def llm_req(phase: PhaseName = R, schema: Any = None) -> LLMRequest:
    return LLMRequest(phase=phase, conversation_id=f"c-{phase.value}", system="s",
                      messages=[{"role": "user", "content": "x"}], effort="high", max_tokens=1000,
                      output_schema=schema)


def fault_llm(tmp_path: Path, rules: list[dict[str, Any]], script: list[FakeResponse] | None = None, *,
              clock: FakeClock | None = None, **kw: Any) -> tuple[FaultInjectingLLMGateway, FakeGateway, FakeClock]:
    clock = clock or FakeClock()
    rd = RunDir(tmp_path / "llm-run").create()
    inner = FakeGateway({R: script or [FakeResponse(text="ok")], PhaseName.PLAN: script or []}, run_dir=rd,
                        clock=clock)
    inner.progress = NullProgress()  # type: ignore[attr-defined]
    return FaultInjectingLLMGateway(inner, schedule(llm=rules, **kw), clock=clock), inner, clock


async def test_llm01_429_retry_after_is_honoured(tmp_path: Path) -> None:
    gw, inner, clock = fault_llm(tmp_path, [{"match": {"stage": "research", "attempt": 0},
                                             "fault": {"type": "http_status", "status": 429, "retry_after": 15}}])
    res = await gw.call(llm_req())
    assert res.text == "ok" and clock.monotonic() >= 15 and len(inner.calls) == 1
    assert any("retry 1/4" in e.message for e in inner.progress.events)  # type: ignore[attr-defined]


async def test_llm02_spend_cap_exits_within_the_retry_budget(tmp_path: Path) -> None:
    gw, inner, clock = fault_llm(tmp_path, [{"match": {}, "fault": {"type": "http_status", "status": 429}}])
    with pytest.raises(LLMRateLimitError) as info:
        await gw.call(llm_req())
    assert info.value.retry_after_s is None and info.value.exit_code is ExitCode.LLM_UNAVAILABLE
    assert inner.calls == []
    logged = [e for e in JsonlWriter(RunDir(tmp_path / "llm-run").llm_log).read() if e.get("fault")]
    assert len(logged) == 5 and [e["attempt"] for e in logged] == [0, 1, 2, 3, 4]   # max_retries 4 -> 5 attempts


async def test_llm03_overload_backs_off_then_raises(tmp_path: Path) -> None:
    gw, inner, clock = fault_llm(tmp_path, [{"match": {}, "fault": {"type": "http_status", "status": 529}}])
    with pytest.raises(LLMOverloadedError):
        await gw.call(llm_req())
    assert 2 + 4 + 8 + 16 >= clock.monotonic() >= (2 + 4 + 8 + 16) / 2  # jittered exponential backoff
    gw2, _, _ = fault_llm(tmp_path / "b", [{"match": {"attempt": 0}, "fault": {"type": "http_status", "status": 503}}])
    assert (await gw2.call(llm_req())).text == "ok"


async def test_llm05_hang_times_out_and_is_retried(tmp_path: Path) -> None:
    gw, inner, clock = fault_llm(tmp_path, [{"match": {"attempt": 0}, "fault": {"type": "hang"}}])
    assert (await gw.call(llm_req())).text == "ok" and clock.monotonic() >= 600
    gw2, _, _ = fault_llm(tmp_path / "b", [{"match": {}, "fault": {"type": "hang"}}])
    with pytest.raises(LLMTimeoutError):
        await gw2.call(llm_req())


async def test_llm_non_retryable_faults(tmp_path: Path) -> None:
    gw, inner, _ = fault_llm(tmp_path, [{"match": {"stage": "research"}, "fault": {"type": "auth", "status": 401}}])
    with pytest.raises(LLMAuthError) as info:
        await gw.call(llm_req())
    assert "ANTHROPIC_API_KEY" in str(info.value) and inner.calls == []
    gw, _, _ = fault_llm(tmp_path / "t", [{"match": {}, "fault": {"type": "stop_reason", "value": "max_tokens",
                                                                   "truncate_at_fraction": 0.6}}])
    with pytest.raises(LLMTruncatedError):
        await gw.call(llm_req())
    plan = [FakeResponse(parsed={"questions": [], "criteria_skipped": []})]
    gw, inner, _ = fault_llm(tmp_path / "s", [{"match": {"stage": "plan"}, "fault": {
        "type": "schema_violation", "drop_field": "criteria_skipped"}}], plan)
    with pytest.raises(LLMSchemaError) as sinfo:
        await gw.call(llm_req(PhaseName.PLAN, PlanOutput))
    assert "criteria_skipped" in str(sinfo.value) and len(inner.calls) == 1
    gw, inner, _ = fault_llm(tmp_path / "o", [{"match": {"stage": "assess"}, "fault": {"type": "auth"}}])
    assert (await gw.call(llm_req())).text == "ok"                       # stage does not match: passes through


async def test_llm06_refusal_in_research_is_recorded_and_the_phase_completes(tmp_path: Path) -> None:
    clock = FakeClock()
    gw, inner, _ = fault_llm(tmp_path, [{"match": {"stage": "research"}, "fault": {
        "type": "stop_reason", "value": "refusal", "category": None}}], clock=clock)
    tools = FakeToolGateway(SPECS, HANDLERS, clock=clock)
    ctx = await ResearchPhase().run(research_ctx(tmp_path, [], tools, clock=clock, llm=gw))
    assert ctx.state.declined_sections == ["research"] and inner.calls == []
    assert ctx.state.stop_reason.detail == "model_declined" and gw.refusals()[0]["stage"] == "research"
    assert any(d.type is DegradationType.OTHER and "category: none given" in d.event for d in ctx.state.degradations)


async def test_llm_flaky_is_deterministic(tmp_path: Path) -> None:
    rules = [{"match": {}, "fault": {"type": "flaky", "p": 0.5, "inner": [{"type": "connection_reset"}]}}]
    times = []
    for i in range(2):
        gw, _, clock = fault_llm(tmp_path / f"f{i}", rules, [FakeResponse(text="ok")] * 3, seed=7)
        for _ in range(3):
            await gw.call(llm_req())
        times.append(clock.monotonic())
    assert times[0] == times[1]


# =============================================================================== NET-01 through the orchestrator


class Noop:
    def __init__(self, name: PhaseName) -> None:
        self.name = name

    async def run(self, ctx: RunContext) -> RunContext:
        return ctx


async def test_net01_network_lost_in_research_checkpoints_and_exits_3(tmp_path: Path) -> None:
    clock = FakeClock()
    sched = schedule(id="NET-01", network=[{"type": "offline", "from_seconds": 0, "duration_seconds": 120}])
    tools, fake, _ = tool_stack(tmp_path, sched, clock)
    inner = FakeGateway({R: both_then_final()}, clock=clock)
    llm = FaultInjectingLLMGateway(inner, sched, clock=clock)
    ctx = research_ctx(tmp_path, [], tools, clock=clock, llm=llm)
    ctx.state.current_phase = None
    phases = {p: Noop(p) for p in PHASE_ORDER}
    phases[R] = ResearchPhase()                                           # type: ignore[assignment]
    with pytest.raises(LLMUnavailableError) as info:
        await Orchestrator(phases).run(ctx)                               # type: ignore[arg-type]
    assert info.value.exit_code is ExitCode.LLM_UNAVAILABLE
    assert ctx.run_dir.state.exists()                                     # state flushed for resume
    assert [p.value for p in ctx.state.completed_phases] == ["ingest", "understand", "plan"]
    assert sorted(f.name for f in ctx.run_dir.checkpoints.iterdir())[-1] == "03-plan.json"
    assert len(ctx.ledger) == 0 and fake.calls == [] and inner.calls == []
    assert clock.monotonic() < 120                                        # gave up within the retry budget


async def test_net01_tools_offline_but_model_reachable_continues_doc_only(tmp_path: Path) -> None:
    clock = FakeClock()
    sched = schedule(id="NET-01b", network=[{"type": "offline", "from_seconds": 0}])
    tools, fake, _ = tool_stack(tmp_path, sched, clock)
    script = [FakeResponse(tool_uses=[ToolUse(f"t{i}", SEARCH if i % 2 else SCHOLAR, {"query": f"q{i}"})
                                      for i in range(1, 7)]),
              FakeResponse(parsed=ResearchOutput(answers=[], stop_requested=True, stop_rationale="offline"))]
    ctx = await ResearchPhase().run(research_ctx(tmp_path, script, tools, clock=clock))
    assert ctx.state.stop_reason.code is StopReasonCode.TOOL_FAILURE and fake.calls == []
    assert any(d.type is DegradationType.TOOL_UNAVAILABLE for d in ctx.state.degradations)
