"""MCP session recovery (NET-06; docs/live_runs/sit_sample_tools_1/MEASUREMENT.md defects 1 and 2).

The first with-tools run held the internet-search session the warm-up opened at 2 s with no call
until 132 s; every ``search_web`` call then failed with ``MCP error -32000: Connection closed`` in
under 0.05 s, the client read it as a tool error, and the gateway disabled the tool. Here a fake MCP
server closes its session after an idle period or after N calls (the way mcp 2.x behaves once a
session's stream has ended: every later request fails at once), and the real mcp client is driven
over an in-process server that ends a call's stream without a response. No network, no key.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

import anyio
import httpx2
import pytest
from mcp import MCPError, types

from sit_review_agent.clock import FakeClock
from sit_review_agent.config import load_config
from sit_review_agent.models import ToolCallStatus
from sit_review_agent.progress import NullProgress
from sit_review_agent.tools.gateway import (
    MCPToolGateway,
    ToolErrorClass,
    qualify,
)
from sit_review_agent.tools.mcp_client import classify_exception, make_http_session_factory

KEY = "CANARY-MCP-7f3a9c0d1e2f"
SERVER = "mcp-internet-search"
SEARCH = qualify(SERVER, "search_web")


# =============================================================================== a fake MCP server


class FakeServer:
    """Server-side state shared by every session the client opens: ``idle_close_s`` closes a session
    that saw no request for that long; ``close_after`` closes a session after that many calls;
    ``fail_reopened`` keeps every session closed (the reopen does not help). ``tool_error`` answers
    ``isError`` (a genuine tool failure)."""

    def __init__(self, clock: FakeClock, *, idle_close_s: float | None = None, close_after: int | None = None,
                 fail_reopened: bool = False, tool_error: bool = False) -> None:
        self.clock = clock
        self.idle_close_s, self.close_after = idle_close_s, close_after
        self.fail_reopened, self.tool_error = fail_reopened, tool_error
        self.inits = 0
        self.calls = 0
        self.closed_calls = 0
        self.gate: asyncio.Event | None = None          # a call waits on it when set (in-flight tests)
        self.gated: FakeSession | None = None             # only this session's calls wait (None = every session)
        self.sessions: list[FakeSession] = []


class FakeSession:
    def __init__(self, server: FakeServer) -> None:
        self.srv = server
        server.sessions.append(self)
        self.closed = False
        self.calls = 0
        self.last = server.clock.monotonic()

    def _check(self) -> None:
        now = self.srv.clock.monotonic()
        idle_closed = self.srv.idle_close_s is not None and now - self.last > self.srv.idle_close_s
        if self.closed or idle_closed or (self.srv.fail_reopened and self.srv.inits > 1):
            self.closed = True
            self.srv.closed_calls += 1
            raise MCPError(-32000, "Connection closed")
        self.last = now

    async def initialize(self) -> Any:
        self.srv.inits += 1
        self.last = self.srv.clock.monotonic()
        return types.InitializeResult(protocol_version="2025-11-25", capabilities=types.ServerCapabilities(),
                                      server_info=types.Implementation(name="fake", version="0"))

    async def list_tools(self, *, params: Any = None) -> Any:
        self._check()
        return types.ListToolsResult(tools=[types.Tool(name="search_web", description="web",
                                                       input_schema={"type": "object"})])

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None,
                        read_timeout_seconds: float | None = None) -> Any:
        self._check()
        if self.srv.gate is not None and self.srv.gated in (None, self):
            await self.srv.gate.wait()
            if self.closed:                            # closed by the server while this call was in flight
                self.srv.closed_calls += 1
                raise MCPError(-32000, "Connection closed")
        self.calls += 1
        self.srv.calls += 1
        if self.srv.close_after is not None and self.calls >= self.srv.close_after:
            self.closed = True                         # this call is answered; the next one meets a closed session
        if self.srv.tool_error:
            return types.CallToolResult(content=[types.TextContent(type="text", text="bad query")], is_error=True)
        return types.CallToolResult(content=[types.TextContent(type="text", text=f"result {arguments}")],
                                    is_error=False)


def factory_for(server: FakeServer) -> Any:
    @contextlib.asynccontextmanager
    async def factory(name: str, url: str, headers: dict[str, str], timeout_s: float,
                      on_response: Any) -> AsyncIterator[FakeSession]:
        yield FakeSession(server)

    return factory


def gateway(server: FakeServer, clock: FakeClock, *, idle_reopen_s: float | None = None) -> MCPToolGateway:
    c = load_config()
    tools = c.tools if idle_reopen_s is None else c.tools.model_copy(update={"session_idle_reopen_s": idle_reopen_s})
    gw = MCPToolGateway(tools, {SERVER: "http://127.0.0.1:9/mcp"}, clock=clock, progress=NullProgress(), api_key=KEY)
    gw.session_factory = factory_for(server)
    return gw


def lines(gw: MCPToolGateway) -> list[str]:
    assert isinstance(gw.progress, NullProgress)
    return [e.message for e in gw.progress.events]


# =============================================================================== classification


def test_closed_session_is_a_session_error_not_a_tool_error() -> None:
    """The run's error, and the transport's equivalents, on an established session."""
    assert classify_exception(MCPError(-32000, "Connection closed")).error_class is ToolErrorClass.SESSION_CLOSED
    assert classify_exception(MCPError(-32000, "SSE stream ended without a response")).error_class \
        is ToolErrorClass.SESSION_CLOSED
    for exc in (anyio.ClosedResourceError(), anyio.EndOfStream(), anyio.BrokenResourceError(),
                ConnectionResetError("reset by peer"), BrokenPipeError()):
        assert classify_exception(exc).error_class is ToolErrorClass.SESSION_CLOSED, exc
    wrapped = httpx2.ReadError("read failed")
    wrapped.__cause__ = ConnectionResetError("reset by peer")
    grp = BaseExceptionGroup("tg", [ExceptionGroup("inner", [wrapped])])
    assert classify_exception(grp).error_class is ToolErrorClass.SESSION_CLOSED
    # A genuine tool-side MCP error stays a tool error; first contact keeps its cold-start meaning.
    assert classify_exception(MCPError(-32602, "invalid params")).error_class is ToolErrorClass.TOOL_ERROR
    assert classify_exception(wrapped, first_contact=True).error_class is ToolErrorClass.COLD_START
    assert classify_exception(ConnectionResetError(), first_contact=True).error_class is ToolErrorClass.CONNECTION


# =============================================================================== reopen on error


async def test_session_closed_after_n_calls_is_reopened_once_and_the_call_retried_once() -> None:
    clock = FakeClock()
    srv = FakeServer(clock, close_after=2)
    gw = gateway(srv, clock)
    for q in ("a", "b"):
        assert (await gw.call(SEARCH, {"query": q})).ok
    res = await gw.call(SEARCH, {"query": "c"})                 # meets the closed session
    assert res.ok and res.text == "result {'query': 'c'}"
    assert srv.inits == 2                                       # exactly one reopen, a new initialize
    assert [a.error_class for a in res.attempts] == [ToolErrorClass.SESSION_CLOSED, None]
    assert res.attempts[-1].message == "retried once after the session was reopened"
    assert [e["reason"].startswith("closed by the server") for e in gw.session_events] == [True]
    assert any("session reopened (closed by the server" in m and "not a degradation" in m for m in lines(gw))
    await gw.aclose()


async def test_the_runs_five_concurrent_calls_on_a_closed_session_share_one_reopen() -> None:
    """sit_sample_tools_1: five search_web calls in one round on a dead session (idle reopen off)."""
    clock = FakeClock()
    srv = FakeServer(clock, idle_close_s=100.0)
    gw = gateway(srv, clock, idle_reopen_s=0)
    assert (await gw.list_tools())[0].name == "search_web"      # the warm-up session at 2 s
    clock.advance(130.0)
    results = await asyncio.gather(*(gw.call(SEARCH, {"query": f"q{i}"}) for i in range(5)))
    assert all(r.ok for r in results), [r.error_message for r in results]
    assert srv.inits == 2                                       # one reopen for all five
    assert len(gw.session_events) == 1 and gw.session_events[0]["reason"].startswith("closed by the server")
    assert any(r.attempts[0].error_class is ToolErrorClass.SESSION_CLOSED for r in results)
    await gw.aclose()


async def test_a_second_failure_after_the_reopen_is_returned_and_the_session_dropped() -> None:
    clock = FakeClock()
    srv = FakeServer(clock, close_after=1, fail_reopened=True)
    gw = gateway(srv, clock)
    assert (await gw.call(SEARCH, {"query": "a"})).ok
    res = await gw.call(SEARCH, {"query": "b"})
    assert not res.ok and res.error_class is ToolErrorClass.SESSION_CLOSED and res.status is ToolCallStatus.ERROR
    assert [a.error_class for a in res.attempts] == [ToolErrorClass.SESSION_CLOSED] * 2   # retried once, no more
    assert srv.inits == 2 and SERVER not in gw._conns                                     # the next call reconnects
    await gw.aclose()


async def test_a_late_failure_on_the_old_session_does_not_drop_the_new_one() -> None:
    """A call still in flight on the closed session fails after another call has already reopened it:
    it retries on the new session instead of replacing it again."""
    clock = FakeClock()
    srv = FakeServer(clock)
    gw = gateway(srv, clock)
    assert (await gw.call(SEARCH, {"query": "warm"})).ok
    old = srv.sessions[0]
    srv.gate, srv.gated = asyncio.Event(), old
    late = asyncio.create_task(gw.call(SEARCH, {"query": "late"}))
    await asyncio.sleep(0)
    old.closed = True                                           # the server closes the session
    early = await gw.call(SEARCH, {"query": "early"})           # meets it, reopens
    assert early.ok and srv.inits == 2
    srv.gate.set()
    res = await late
    assert res.ok and [a.error_class for a in res.attempts] == [ToolErrorClass.SESSION_CLOSED, None]
    assert srv.inits == 2 and len(gw.session_events) == 1       # the new session was kept
    await gw.aclose()


# =============================================================================== reopen on idle


async def test_an_idle_session_is_reopened_before_the_call() -> None:
    clock = FakeClock()
    srv = FakeServer(clock, idle_close_s=100.0)
    gw = gateway(srv, clock)
    assert gw.tools.session_idle_reopen_s == 60.0               # config/tools.yaml default
    await gw.list_tools()                                       # warm-up
    clock.advance(130.0)
    res = await gw.call(SEARCH, {"query": "q"})
    assert res.ok and srv.inits == 2 and srv.closed_calls == 0  # never met the closed session
    assert [a.error_class for a in res.attempts] == [None]      # no failed attempt
    assert res.attempts[0].message is not None and "idle 130 s" in res.attempts[0].message
    ev = gw.session_events
    assert len(ev) == 1 and ev[0]["idle_s"] == 130.0 and "session_idle_reopen_s 60 s" in ev[0]["reason"]
    assert any("idle 130 s" in m for m in lines(gw))
    await gw.aclose()


async def test_a_session_used_within_the_idle_limit_is_kept() -> None:
    clock = FakeClock()
    srv = FakeServer(clock)
    gw = gateway(srv, clock)
    for _ in range(4):
        clock.advance(50.0)                                     # each gap under 60 s
        assert (await gw.call(SEARCH, {"query": "q"})).ok
    assert srv.inits == 1 and gw.session_events == []
    await gw.aclose()


async def test_no_idle_reopen_while_a_call_is_in_flight() -> None:
    clock = FakeClock()
    srv = FakeServer(clock)
    gw = gateway(srv, clock)
    assert (await gw.call(SEARCH, {"query": "warm"})).ok
    srv.gate = asyncio.Event()
    slow = asyncio.create_task(gw.call(SEARCH, {"query": "slow"}))
    await asyncio.sleep(0)
    clock.advance(65.0)                                         # the slow call has run 65 s
    fast = asyncio.create_task(gw.call(SEARCH, {"query": "fast"}))
    await asyncio.sleep(0)
    srv.gate.set()
    a, b = await slow, await fast
    assert a.ok and b.ok and srv.inits == 1 and gw.session_events == []
    await gw.aclose()


# =============================================================================== the real mcp client


def asgi_server(gate: dict[str, Any]) -> tuple[Any, Any]:
    """An in-process MCPServer (the shape of the probe's self-test server) that, while
    ``gate["end_stream"]`` > 0, answers a ``tools/call`` with an event stream that ends without a
    response: the real mcp client then fails the call with ``MCPError(-32000, ...)``."""
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("fake-search")

    @server.tool()
    def search_web(query: str) -> str:
        """Web search."""
        return f"1. Result for {query}\n   URL: https://docs.example.org/{query.replace(' ', '-')}"

    inner = server.streamable_http_app(streamable_http_path="/mcp", json_response=True)

    async def app(scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and gate.get("end_stream"):
            body = b""
            more = True
            while more:
                msg = await receive()
                body += msg.get("body", b"")
                more = msg.get("more_body", False)
            if b'"tools/call"' in body:
                gate["end_stream"] -= 1
                gate.setdefault("ended", 0)
                gate["ended"] += 1
                await send({"type": "http.response.start", "status": 200,
                            "headers": [(b"content-type", b"text/event-stream")]})
                await send({"type": "http.response.body", "body": b""})
                return
            sent = False

            async def replay() -> Any:
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            await inner(scope, replay, send)
            return
        await inner(scope, receive, send)

    return server, app


@pytest.fixture
def quiet_mcp_logs() -> None:
    import logging

    for name in ("mcp", "httpx", "httpx2", "uvicorn"):
        logging.getLogger(name).setLevel(logging.WARNING)


@pytest.mark.usefixtures("quiet_mcp_logs")
async def test_real_mcp_client_reopens_a_session_whose_stream_ended() -> None:
    gate: dict[str, Any] = {}
    server, app = asgi_server(gate)
    c = load_config()
    gw = MCPToolGateway(c.tools, {SERVER: "http://127.0.0.1:9/mcp"}, clock=FakeClock(), progress=NullProgress(),
                        api_key=KEY)
    gw.session_factory = make_http_session_factory(httpx2.ASGITransport(app=app))
    async with server.session_manager.run():
        assert (await gw.call(SEARCH, {"query": "first"})).ok
        gate["end_stream"] = 1
        res = await gw.call(SEARCH, {"query": "second"})
        assert gate["ended"] == 1
        assert res.ok and "docs.example.org/second" in res.text, res.error_message
        assert [a.error_class for a in res.attempts] == [ToolErrorClass.SESSION_CLOSED, None]
        assert len(gw.session_events) == 1
        await gw.aclose()
