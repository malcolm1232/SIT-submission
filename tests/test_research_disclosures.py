"""Research disclosures after sit_sample_tools_1 (docs/live_runs/sit_sample_tools_1/MEASUREMENT.md
defects 2 and 3): the tool-error disclosure counts the calls attempted and failed, names the error
class and what stayed unverified; the stop reason is ``sufficient_evidence`` only when a question
was answered.

The research fixture of ``test_research_phase.py`` (booking design, RQ-001 web search, RQ-002
scholarly) over the live MCP gateway with fake sessions: the web search server closes every session
at once (a reopen does not help), the scholarly server answers.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from mcp import MCPError, types

from sit_review_agent.clock import FakeClock
from sit_review_agent.llm.gateway import FakeResponse
from sit_review_agent.models import DegradationType, StopReasonCode
from sit_review_agent.phases.research import ResearchPhase
from sit_review_agent.tools.gateway import MCPToolGateway, ToolErrorClass, qualify
from test_research_phase import PAPERS, final, make_ctx, tu

KEY = "CANARY-MCP-7f3a9c0d1e2f"
WEB = qualify("mcp-internet-search", "search_web")
SCHOLAR = qualify("mcp-research-information", "search_works")


class _Session:
    def __init__(self, server: str, log: dict[str, int]) -> None:
        self.server, self.log = server, log

    async def initialize(self) -> Any:
        self.log[self.server] = self.log.get(self.server, 0) + 1
        return types.InitializeResult(protocol_version="2025-11-25", capabilities=types.ServerCapabilities(),
                                      server_info=types.Implementation(name=self.server, version="0"))

    async def list_tools(self, *, params: Any = None) -> Any:
        name = "search_web" if self.server == "mcp-internet-search" else "search_works"
        return types.ListToolsResult(tools=[types.Tool(name=name, description=name, input_schema={
            "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})])

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None,
                        read_timeout_seconds: float | None = None) -> Any:
        if self.server == "mcp-internet-search":
            raise MCPError(-32000, "Connection closed")
        return types.CallToolResult(content=[types.TextContent(type="text", text=PAPERS)], is_error=False)


def live_base(clock: FakeClock, inits: dict[str, int]) -> MCPToolGateway:
    from sit_review_agent.config import load_config

    c = load_config()
    gw = MCPToolGateway(c.tools, {s: "http://127.0.0.1:9/mcp" for s in c.endpoints.servers}, clock=clock,
                        api_key=KEY)

    @contextlib.asynccontextmanager
    async def factory(server: str, url: str, headers: dict[str, str], timeout_s: float,
                      on_response: Any) -> AsyncIterator[_Session]:
        yield _Session(server, inits)

    gw.session_factory = factory
    return gw


def run_script(*answers: tuple[str, str, list[str]]) -> list[FakeResponse]:
    return [FakeResponse(tool_uses=[*(tu(i, WEB, query=f"mailer limit {i}") for i in range(1, 6)),
                                    tu(6, SCHOLAR, query="filtered hnsw latency")]),
            final(*answers, stop=True)]


async def test_tool_error_disclosure_counts_calls_classes_and_unverified_questions(tmp_path: Path) -> None:
    clock = FakeClock()
    inits: dict[str, int] = {}
    script = run_script(("RQ-001", "unanswered", []), ("RQ-002", "partial", ["EV-001"]))
    ctx = await ResearchPhase().run(make_ctx(tmp_path, script, base=live_base(clock, inits), clock=clock))
    errs = [d for d in ctx.state.degradations if d.type is DegradationType.TOOL_ERROR]
    assert len(errs) == 1, [d.event for d in ctx.state.degradations]
    d = errs[0]
    assert d.event.startswith("mcp-internet-search/search_web: 5 of 5 call(s) failed (session_closed x5); "
                              "last error: session closed (MCP error -32000: Connection closed)"), d.event
    assert d.event.endswith("; the tool was then disabled for the run"), d.event
    assert d.impact == "no call to search_web returned evidence; unverified: RQ-001", d.impact
    assert "that call contributed no evidence" not in d.impact
    assert inits["mcp-internet-search"] >= 2                         # a reopen was tried before it counted


async def test_tool_error_disclosure_names_successes_too(tmp_path: Path) -> None:
    """A tool that failed once and answered once: the counts say so."""
    clock = FakeClock()
    inits: dict[str, int] = {}
    base = live_base(clock, inits)
    script = [FakeResponse(tool_uses=[tu(1, SCHOLAR, query="a"), tu(2, WEB, query="b")]),
              final(("RQ-001", "unanswered", []), ("RQ-002", "partial", ["EV-001"]), stop=True)]
    ctx = await ResearchPhase().run(make_ctx(tmp_path, script, base=base, clock=clock))
    d = next(d for d in ctx.state.degradations if d.type is DegradationType.TOOL_ERROR)
    assert d.event.startswith("mcp-internet-search/search_web: 1 of 1 call(s) failed (session_closed x1)")
    assert "disabled" not in d.event                                 # one genuine failure is not two
    assert ToolErrorClass.SESSION_CLOSED.value in d.event


async def test_stop_vote_with_nothing_answered_is_not_sufficient_evidence(tmp_path: Path) -> None:
    """sit_sample_tools_1: 0 of 9 answered, web search disabled, scholarly evidence in the ledger, the
    model voted to stop: the reason was ``sufficient_evidence``."""
    clock = FakeClock()
    script = run_script(("RQ-001", "unanswered", []), ("RQ-002", "partial", ["EV-001"]))
    ctx = await ResearchPhase().run(make_ctx(tmp_path, script, base=live_base(clock, {}), clock=clock))
    assert any(e.source_type.value == "external" for e in ctx.ledger)     # evidence was gathered
    stop = ctx.state.stop_reason
    assert stop.code is StopReasonCode.TOOL_FAILURE, stop
    assert stop.detail == "model_stop_vote with no question answered; mcp-internet-search__search_web unusable"


async def test_stop_vote_with_one_answer_of_three_is_not_sufficient_evidence(tmp_path: Path) -> None:
    """Run fix E (3 Oct 2026): a stop vote with 1 of the plan's 3 questions answered and no source
    cited by a finding is recorded as the reason that fits, never ``sufficient_evidence``."""
    clock = FakeClock()
    script = run_script(("RQ-001", "unanswered", []), ("RQ-002", "answered", ["EV-001", "EV-002"]))
    ctx = await ResearchPhase().run(make_ctx(tmp_path, script, base=live_base(clock, {}), clock=clock))
    assert ctx.state.stop_reason.code is StopReasonCode.NO_MARGINAL_GAIN
    assert ctx.state.stop_reason.detail.startswith("sufficient_evidence not met (model_stop_vote): 1 of 3 ")
