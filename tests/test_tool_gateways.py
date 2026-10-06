"""Workstream B, phase 2: MCPToolGateway (fake sessions and the real mcp 2.2.0 streamable-HTTP client
over an in-process ASGI server, no sockets), PolicyToolGateway (allowlist, URL policy, sanitiser,
budget), source extraction and authority classes.

Covers the removed ``tests/test_pending.py`` entry ``test_mcp_gateway_cold_start_and_session_reinit``
("one retry on cold-start-like failure; re-initialize on 404; 401 disables all servers").
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
from mcp import MCPError, types

from sit_review_agent.clock import FakeClock
from sit_review_agent.config import ConfigOverrides, EffectiveConfig, load_config
from sit_review_agent.models import SourceAuthority, ToolCallStatus
from sit_review_agent.progress import NullProgress
from sit_review_agent.tools.cassette import Redactor
from sit_review_agent.tools.gateway import (
    FakeToolGateway,
    MCPToolGateway,
    PolicyToolGateway,
    ServerHealth,
    ToolErrorClass,
    ToolSpec,
    qualify,
)
from sit_review_agent.tools.mcp_client import classify_exception, make_http_session_factory
from sit_review_agent.tools.policy import SeenUrls, check_urls, sanitise_args
from sit_review_agent.tools.sources import classify_authority, extract_sources, independence_key

KEY = "CANARY-MCP-7f3a9c0d1e2f"
SEARCH = qualify("mcp-internet-search", "search")
SCHOLAR = qualify("mcp-research-information", "search_works")
BROWSE = qualify("mcp-browser-automation-pw", "navigate")


def cfg(**overrides: Any) -> EffectiveConfig:
    return load_config(overrides=ConfigOverrides(**overrides)) if overrides else load_config()


# =============================================================================== fake MCP sessions


class FakeSession:
    """Scripted stand-in for ``mcp.ClientSession``: ``init`` and ``calls`` are lists of actions
    consumed in order (``"ok"``, ``("sleep", s)``, ``("status", code)``, an exception, or a str)."""

    def __init__(self, server: str, script: dict[str, Any], clock: FakeClock, on_response: Any) -> None:
        self.server, self.script, self.clock, self.on_response = server, script, clock, on_response

    async def _act(self, queue: list[Any]) -> Any:
        action = queue.pop(0) if queue else "ok"
        if isinstance(action, tuple) and action[0] == "sleep":
            await self.clock.sleep(action[1])
            return "ok"
        if isinstance(action, tuple) and action[0] == "status":
            self.on_response(action[1], None)
            raise MCPError(-32603, "Server returned an error response")
        if isinstance(action, BaseException):
            raise action
        return action

    async def initialize(self) -> Any:
        self.script["inits"] += 1
        await self._act(self.script.setdefault("init", []))
        return types.InitializeResult(protocol_version="2025-11-25", capabilities=types.ServerCapabilities(),
                                      server_info=types.Implementation(name=self.server, version="0"))

    async def list_tools(self, *, params: Any = None) -> Any:
        return types.ListToolsResult(tools=[types.Tool(name=n, description=f"{n} tool", input_schema={"type": "object"})
                                            for n in self.script.get("tools", ["search"])])

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None,
                        read_timeout_seconds: float | None = None) -> Any:
        self.script["calls_made"] += 1
        out = await self._act(self.script.setdefault("calls", []))
        text = out if isinstance(out, str) and out != "ok" else f"result of {name} {arguments}"
        return types.CallToolResult(content=[types.TextContent(type="text", text=text)], is_error=False)


def fake_factory(scripts: dict[str, dict[str, Any]], clock: FakeClock, seen_headers: list[dict[str, str]]) -> Any:
    @contextlib.asynccontextmanager
    async def factory(server: str, url: str, headers: dict[str, str], timeout_s: float,
                      on_response: Any) -> AsyncIterator[FakeSession]:
        seen_headers.append(dict(headers))
        s = scripts.setdefault(server, {})
        s.setdefault("inits", 0)
        s.setdefault("calls_made", 0)
        yield FakeSession(server, s, clock, on_response)

    return factory


def mcp_gateway(scripts: dict[str, dict[str, Any]], clock: FakeClock, *, key: str | None = KEY,
                config: EffectiveConfig | None = None) -> tuple[MCPToolGateway, list[dict[str, str]], NullProgress]:
    c = config or cfg()
    progress = NullProgress()
    gw = MCPToolGateway(c.tools, c.endpoints.servers, clock=clock, progress=progress, api_key=key)
    headers: list[dict[str, str]] = []
    gw.session_factory = fake_factory(scripts, clock, headers)
    return gw, headers, progress


async def test_mcp_cold_start_retry_then_ok() -> None:
    import httpx2 as hx

    clock = FakeClock()
    scripts = {"mcp-internet-search": {"init": [hx.ReadTimeout("cold")]}}
    gw, headers, progress = mcp_gateway(scripts, clock)
    res = await gw.call(SEARCH, {"query": "q"})
    assert res.ok and res.text.startswith("result of search")
    assert scripts["mcp-internet-search"]["inits"] == 2                    # one cold-start retry
    assert [a.error_class for a in res.attempts] == [ToolErrorClass.COLD_START, None]
    assert clock.monotonic() >= 15.0                                       # COLD_RETRY_DELAY_S on the virtual clock
    assert any("waking mcp-internet-search" in e.message for e in progress.events)
    assert headers[0] == {"Authorization": f"Bearer {KEY}"}                # tools.yaml auth_header
    assert gw.protocol_versions["mcp-internet-search"] == "2025-11-25"
    again = await gw.call(SEARCH, {"query": "q2"})
    assert again.ok and scripts["mcp-internet-search"]["inits"] == 2       # session reused
    await gw.aclose()


async def test_mcp_in_band_failure_becomes_a_tool_error_naming_the_server() -> None:
    import json

    failed = {"results": [], "provider_used": None,
              "attempts": [{"provider": "tavily", "outcome": "skipped", "reason": "TAVILY_API_KEY not configured"}]}
    ok = {"results": [{"link": "https://a.example/x", "title": "T", "snippet": "S"}], "provider_used": "duckduckgo"}
    clock = FakeClock()
    scripts = {"mcp-internet-search": {"calls": [json.dumps(failed), json.dumps(ok)]}}
    gw, _, _ = mcp_gateway(scripts, clock)
    bad = await gw.call(SEARCH, {"query": "q"})
    assert not bad.ok and bad.is_error and bad.status is ToolCallStatus.ERROR
    assert bad.error_class is ToolErrorClass.TOOL_ERROR
    assert bad.error_message is not None and bad.error_message.startswith("mcp-internet-search: ")
    assert "empty result list" in bad.error_message and extract_sources(bad) == []
    good = await gw.call(SEARCH, {"query": "q2"})
    assert good.ok and good.error_message is None
    await gw.aclose()


async def test_mcp_auth_header_is_bearer_built_from_the_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shipped tools.yaml sends ``Authorization: Bearer <SIT_MCP_API_KEY>`` and nothing else
    (probe 2026-10-03: Bearer answered HTTP 200 on all four servers, no auth got HTTP 401)."""
    fake = "fake-value-for-the-header-test-0123456789"
    monkeypatch.setenv("SIT_MCP_API_KEY", fake)
    c = cfg()
    assert c.tools.auth_env == "SIT_MCP_API_KEY" and c.tools.auth_header == "Authorization"
    gw, headers, _ = mcp_gateway({"mcp-internet-search": {}}, FakeClock(), key=None)
    res = await gw.call(SEARCH, {"query": "q"})
    assert res.ok
    assert headers == [{"Authorization": f"Bearer {fake}"}]
    await gw.aclose()


async def test_mcp_cold_start_gives_up_after_the_allowance() -> None:
    import httpx2 as hx

    clock = FakeClock()
    scripts = {"mcp-internet-search": {"init": [hx.ReadTimeout("cold"), hx.ReadTimeout("still cold")]}}
    gw, _, _ = mcp_gateway(scripts, clock)
    res = await gw.call(SEARCH, {"query": "q"})
    assert not res.ok and res.error_class is ToolErrorClass.COLD_START and res.status is ToolCallStatus.TIMEOUT
    assert len(res.attempts) == 2 and gw.health["mcp-internet-search"] is ServerHealth.DOWN


async def test_mcp_session_expired_reinitialises_once() -> None:
    clock = FakeClock()
    scripts = {"mcp-internet-search": {"calls": [MCPError(-32600, "Session terminated"), "fresh"]}}
    gw, _, _ = mcp_gateway(scripts, clock)
    res = await gw.call(SEARCH, {"query": "q"})
    assert res.ok and res.text == "fresh"
    assert scripts["mcp-internet-search"]["inits"] == 2                    # exactly one re-initialise
    assert [a.error_class for a in res.attempts] == [ToolErrorClass.SESSION_EXPIRED, None]


async def test_mcp_401_twice_disables_every_server_and_never_leaks_the_key() -> None:
    clock = FakeClock()
    scripts = {"mcp-internet-search": {"init": [("status", 401), ("status", 401)]},
               "mcp-research-information": {}}
    gw, _, progress = mcp_gateway(scripts, clock)
    first = await gw.call(SEARCH, {"query": "q"})
    assert first.error_class is ToolErrorClass.AUTH and not gw.auth_failed  # one strike: not yet confirmed
    second = await gw.call(SEARCH, {"query": "q"})                         # the confirmation
    assert second.error_class is ToolErrorClass.AUTH and gw.auth_failed
    assert all(h in (ServerHealth.DOWN, ServerHealth.DISABLED) for h in gw.health.values())
    other = await gw.call(SCHOLAR, {"query": "q"})
    assert other.error_class is ToolErrorClass.AUTH
    assert scripts["mcp-research-information"].get("inits", 0) == 0         # never contacted
    assert await gw.list_tools() == []
    blob = repr([first, second, other]) + " ".join(e.message for e in progress.events)
    assert "SIT_MCP_API_KEY" in second.error_message and KEY not in blob


async def test_mcp_missing_key_and_disabled_server() -> None:
    gw, _, _ = mcp_gateway({}, FakeClock(), key="")
    res = await gw.call(SEARCH, {"query": "q"})
    assert res.error_class is ToolErrorClass.AUTH and "SIT_MCP_API_KEY is not set" in res.error_message
    off = await gw.call(BROWSE, {"url": "https://example.org"})            # browser is disabled in tools.yaml
    assert off.error_class is ToolErrorClass.NOT_ALLOWED and off.status is ToolCallStatus.BLOCKED


async def test_mcp_list_tools_qualifies_names_and_capabilities() -> None:
    clock = FakeClock()
    scripts = {"mcp-internet-search": {"tools": ["search", "fetch", "bad name!"]},
               "mcp-research-information": {"tools": ["search_works"]}}
    gw, _, progress = mcp_gateway(scripts, clock)
    health = await gw.warm_up()
    assert health["mcp-internet-search"] is ServerHealth.OK
    names = sorted(t.qualified_name for t in await gw.list_tools())
    assert names == ["mcp-internet-search__fetch", "mcp-internet-search__search",
                     "mcp-research-information__search_works"]
    caps = {t.qualified_name: t.capability for t in await gw.list_tools()}
    assert caps[SCHOLAR] == "scholarly" and caps[SEARCH] == "search"
    assert any("skipped" in e.message for e in progress.events)
    assert any("ready (" in e.message for e in progress.events)


def test_classify_exception_shapes() -> None:
    import httpx2 as hx

    grp = BaseExceptionGroup("tg", [ExceptionGroup("inner", [hx.ConnectError("refused")])])
    assert classify_exception(grp).error_class is ToolErrorClass.CONNECTION
    assert classify_exception(hx.ReadTimeout("t"), first_contact=True).error_class is ToolErrorClass.COLD_START
    assert classify_exception(hx.ReadTimeout("t")).error_class is ToolErrorClass.TIMEOUT
    err = MCPError(-32603, "Server returned an error response")
    assert classify_exception(err, status_hint=(503, None), first_contact=True).error_class is ToolErrorClass.COLD_START
    assert classify_exception(err, status_hint=(503, None)).error_class is ToolErrorClass.HTTP_5XX
    rl = classify_exception(err, status_hint=(429, 20.0))
    assert rl.error_class is ToolErrorClass.HTTP_4XX and rl.retry_after_s == 20.0
    assert classify_exception(err, status_hint=(403, None)).error_class is ToolErrorClass.AUTH
    assert classify_exception(MCPError(-32700, "bad json")).error_class is ToolErrorClass.MALFORMED
    assert classify_exception(MCPError(-32602, "invalid params")).error_class is ToolErrorClass.TOOL_ERROR


# =============================================================================== the real MCP client, offline


def asgi_server(gate: dict[str, Any]) -> tuple[Any, Any]:
    """An in-process MCPServer behind an auth gate (``Authorization: Bearer <key>``, the shape the
    owner's probe of 2026-10-03 found on all four SIT servers) that can also return a scripted
    status once (``gate["once"]``). Served through httpx2.ASGITransport: no sockets."""
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("fake-search")

    @server.tool()
    def search(query: str) -> str:
        """Web search."""
        return f"1. Result for {query}\n   URL: https://docs.example.org/{query.replace(' ', '-')}\n   A snippet."

    inner = server.streamable_http_app(streamable_http_path="/mcp", json_response=True)

    async def app(scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http":
            h = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            status = None
            if h.get("authorization") != f"Bearer {gate['key']}":
                status = 401
            elif gate.get("once") and (gate["once"][0] != 404 or "mcp-session-id" in h):
                status = gate.pop("once")[0]
            if status is not None:
                gate.setdefault("served", []).append(status)
                await send({"type": "http.response.start", "status": status,
                            "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"refused"})
                return
        await inner(scope, receive, send)

    return server, app


@pytest.fixture
def quiet_mcp_logs() -> None:
    import logging

    for name in ("mcp", "httpx", "httpx2", "uvicorn"):
        logging.getLogger(name).setLevel(logging.WARNING)


@pytest.mark.usefixtures("quiet_mcp_logs")
async def test_real_mcp_client_over_asgi_transport() -> None:
    gate: dict[str, Any] = {"key": KEY}
    server, app = asgi_server(gate)
    c = cfg()
    endpoints = {**c.endpoints.servers, "mcp-internet-search": "http://127.0.0.1:8000/mcp"}
    gw = MCPToolGateway(c.tools, endpoints, clock=FakeClock(), progress=NullProgress(), api_key=KEY)
    gw.session_factory = make_http_session_factory(httpx2.ASGITransport(app=app))
    async with server.session_manager.run():
        specs = [t for t in await gw.list_tools() if t.server == "mcp-internet-search"]
        assert [t.name for t in specs] == ["search"] and specs[0].input_schema["required"] == ["query"]
        res = await gw.call(SEARCH, {"query": "hnsw latency"})
        assert res.ok and "https://docs.example.org/hnsw-latency" in res.text
        assert extract_sources(res)[0].url_or_citation == "https://docs.example.org/hnsw-latency"
        gate["once"] = [404]                                               # stale session: re-initialise once
        res2 = await gw.call(SEARCH, {"query": "second"})
        assert res2.ok and gate["served"] == [404]
        assert [a.error_class for a in res2.attempts] == [ToolErrorClass.SESSION_EXPIRED, None]
        gate["once"] = [503]                                               # status code recovered via the hook
        res3 = await gw.call(SEARCH, {"query": "third"})
        assert res3.error_class is ToolErrorClass.HTTP_5XX and res3.attempts[-1].http_status == 503
        gate["key"] = "rotated"                                            # INF-07: the shared key was rotated
        await gw.aclose()                                                  # force a fresh initialize
        res4 = await gw.call(SEARCH, {"query": "fourth"})
        assert res4.error_class is ToolErrorClass.AUTH and res4.attempts[-1].http_status == 401
        await gw.aclose()
    assert gw.protocol_versions["mcp-internet-search"]


# =============================================================================== policy gateway


def fake_inner(handlers: dict[str, Any] | None = None) -> FakeToolGateway:
    specs = [ToolSpec("mcp-internet-search", "search", "web search", {"type": "object"}, "search"),
             ToolSpec("mcp-internet-search", "fetch", "fetch a page", {"type": "object"}, "search"),
             ToolSpec("mcp-research-information", "search_works", "papers", {"type": "object"}, "scholarly")]
    default = {
        SEARCH: lambda a: f"1. Official limits\n   URL: https://docs.vendor.example/limits?tab=2\n   {a.get('query')}",
        qualify("mcp-internet-search", "fetch"): lambda a: f"# Page {a['url']}\nThe limit is 2,000 per day.",
        SCHOLAR: lambda a: '{"results": [{"title": "A paper", "doi": "10.1145/1234", "abstract": "We measure."}]}',
    }
    return FakeToolGateway(specs, {**default, **(handlers or {})}, clock=FakeClock())


def policy(config: EffectiveConfig | None = None, inner: Any = None,
           secrets: tuple[str, ...] = (KEY,)) -> tuple[PolicyToolGateway, FakeToolGateway]:
    inner = inner or fake_inner()
    return PolicyToolGateway(inner, config or cfg(), Redactor(secrets), clock=FakeClock(),
                             progress=NullProgress()), inner


def with_url_policy(c: EffectiveConfig, **kw: Any) -> EffectiveConfig:
    return c.model_copy(update={"url_policy": c.url_policy.model_copy(update=kw)})


async def test_policy_allowlist_and_unqualified_names() -> None:
    c = cfg()
    servers = [s.model_copy(update={"allow_tools": ["search"]}) if s.name == "mcp-internet-search" else s
               for s in c.tools.servers]
    narrowed = c.model_copy(update={"tools": c.tools.model_copy(update={"servers": servers})})
    gw, inner = policy(narrowed)
    assert sorted(t.qualified_name for t in await gw.list_tools()) == sorted([SCHOLAR, SEARCH])
    blocked = await gw.call(qualify("mcp-internet-search", "fetch"), {"url": "https://docs.vendor.example/x"})
    assert blocked.status is ToolCallStatus.BLOCKED and blocked.error_class is ToolErrorClass.NOT_ALLOWED
    odd = await gw.call("search", {"query": "x"})                         # unqualified: a result, not an exception
    assert odd.error_class is ToolErrorClass.NOT_ALLOWED
    off = await gw.call(BROWSE, {"url": "https://x.example"})             # disabled server (tools.yaml)
    assert off.error_class is ToolErrorClass.NOT_ALLOWED
    assert inner.calls == [] and gw.calls_made == 0                      # refusals never reach the server


@pytest.mark.parametrize("args, needle", [
    ({"query": f"rate limits {KEY}"}, "configured secret"),
    ({"query": "CANARY-LLM-c21e99 pgvector"}, "canary"),
    ({"query": "x sk-ant-api03-abcdefghijklmnop"}, "anthropic key"),
    ({"query": "api_key=supersecretvalue123"}, "credential assignment"),
    ({"query": "a" * 2500}, "possible document"),
    ({"query": "data " + "QUJD" * 40}, "encoded blob"),
    ({"filters": {"nested": ["ghp_abcdefghijklmnopqrstuvwxyz0123"]}}, "github token"),
])
async def test_policy_sanitiser_blocks_secrets_and_bulk_text(args: dict[str, Any], needle: str) -> None:
    gw, inner = policy()
    res = await gw.call(SEARCH, args)
    assert res.status is ToolCallStatus.BLOCKED and res.error_class is ToolErrorClass.BLOCKED
    assert needle in res.error_message
    assert inner.calls == []
    logged = repr(res.log_entry())
    assert KEY not in logged and "CANARY-LLM" not in logged and "sk-ant-api03" not in logged


def test_sanitiser_allows_normal_queries() -> None:
    red = Redactor([KEY])
    assert sanitise_args({"query": "pgvector filtered query latency 9.5M vectors", "limit": 10}, red) is None
    assert sanitise_args({"url": "https://docs.example.org/a/b?x=1"}, red) is None


async def test_policy_url_deny_and_allow_modes() -> None:
    seen = SeenUrls()
    seen.add(["https://evil.example/a", "https://docs.vendor.example/limits"])
    base = cfg().url_policy
    deny = base.model_copy(update={"deny_domains": ["evil.example"]})
    assert "denied" in check_urls({"url": "https://sub.evil.example/a"}, deny, seen)
    assert check_urls({"url": "https://docs.vendor.example/limits"}, deny, seen) is None
    allow = base.model_copy(update={"mode": "allow", "allow_domains": ["vendor.example"]})
    assert check_urls({"url": "https://docs.vendor.example/limits"}, allow, seen) is None
    assert "not in url_policy.yaml allow_domains" in check_urls({"url": "https://evil.example/a"}, allow, seen)
    assert check_urls({"query": "no urls here"}, allow, seen) is None    # searches are not fetches
    assert "scheme" in check_urls({"url": "file:///etc/passwd"}, base, seen)
    # The real fetch tool (probe 2026-10-03: internet-search `fetch_url`) takes a `urls` array;
    # every element is policed, and read_document's `uri` is a fetch key too.
    assert "denied" in check_urls({"urls": ["https://docs.vendor.example/limits", "https://evil.example/a"]},
                                  deny, seen)
    assert check_urls({"urls": ["https://docs.vendor.example/limits"], "max_chars": 4000}, deny, seen) is None
    assert "scheme" in check_urls({"uri": "file:///etc/passwd"}, base, seen)


async def test_policy_fetch_only_from_results_and_added_query_strings() -> None:
    gw, inner = policy()
    fetch = qualify("mcp-internet-search", "fetch")
    early = await gw.call(fetch, {"url": "https://docs.vendor.example/limits"})
    assert early.status is ToolCallStatus.BLOCKED and "did not appear" in early.error_message
    found = await gw.call(SEARCH, {"query": "vendor limits"})            # result lists .../limits?tab=2
    assert found.ok
    ok = await gw.call(fetch, {"url": "https://docs.vendor.example/limits"})
    assert ok.ok
    same_query = await gw.call(fetch, {"url": "https://docs.vendor.example/limits?tab=2"})
    assert same_query.ok
    exfil = await gw.call(fetch, {"url": "https://docs.vendor.example/limits?tab=2&k=secretdoc"})
    assert exfil.status is ToolCallStatus.BLOCKED and "query string" in exfil.error_message
    embedded = await gw.call(SEARCH, {"query": "see https://attacker.example/?d=stolen"})
    assert embedded.status is ToolCallStatus.BLOCKED
    gw.seed_urls(["https://cited.example.org/paper"])                    # cited by the document
    cited = await gw.call(fetch, {"url": "https://cited.example.org/paper"})
    assert cited.ok
    assert [n for n, _ in inner.calls].count(fetch) == 3


async def test_policy_fetch_policy_can_be_switched_off() -> None:
    c = with_url_policy(cfg(), fetch_only_from_results=False, reject_added_query_strings=False)
    gw, _ = policy(c)
    res = await gw.call(qualify("mcp-internet-search", "fetch"), {"url": "https://any.example/p?x=1"})
    assert res.ok


async def test_policy_budget() -> None:
    gw, inner = policy(cfg(max_tool_calls=2))
    assert (await gw.call(SEARCH, {"query": "a"})).ok
    assert (await gw.call(SEARCH, {"query": "b"})).ok
    third = await gw.call(SEARCH, {"query": "c"})
    assert third.error_class is ToolErrorClass.BUDGET and third.status is ToolCallStatus.BLOCKED
    assert len(inner.calls) == 2


# =============================================================================== sources


def _res(server: str, tool: str, text: str, args: dict[str, Any] | None = None, structured: Any = None) -> Any:
    from sit_review_agent.tools.gateway import _result

    return _result("call-0001", server, tool, args or {"query": "q"}, status=ToolCallStatus.OK,
                   started_at="2026-10-02T09:00:00Z", text=text, structured_content=structured)


def test_extract_sources_from_text_hits_json_records_and_pages() -> None:
    text = ("1. PostgreSQL: Documentation: pgvector indexes\n   URL: https://www.postgresql.org/docs/current/x.html\n"
            "   Index types and filtering.\n2. My blog post\n   URL: https://someone.medium.com/post\n   Opinions.\n"
            "See also [RFC 9110](https://www.rfc-editor.org/rfc/rfc9110).")
    srcs = extract_sources(_res("mcp-internet-search", "search", text))
    assert [s.url_or_citation for s in srcs] == ["https://www.postgresql.org/docs/current/x.html",
                                                  "https://someone.medium.com/post",
                                                  "https://www.rfc-editor.org/rfc/rfc9110"]
    assert srcs[0].title == "PostgreSQL: Documentation: pgvector indexes" and srcs[0].excerpt.startswith("Index types")
    assert [s.authority for s in srcs] == [SourceAuthority.PRIMARY_OFFICIAL, SourceAuthority.INFORMAL,
                                           SourceAuthority.PRIMARY_OFFICIAL]
    assert srcs[2].title == "RFC 9110" and not any(s.read_in_full for s in srcs)

    records = {"results": [
        {"title": "Filtered ANN search", "doi": "https://doi.org/10.1145/3589282", "abstract": "We study filters.",
         "venue": "SIGMOD"},
        {"title": "A preprint", "doi": "10.48550/arXiv.2401.00001", "abstract": "Early results."},
        {"title": "No link", "authors": [{"name": "A. Author"}, {"name": "B"}], "year": 2024, "venue": "VLDB"}]}
    srcs = extract_sources(_res("mcp-research-information", "search_works", "", structured=records))
    assert [s.url_or_citation for s in srcs] == ["https://doi.org/10.1145/3589282",
                                                  "https://doi.org/10.48550/arXiv.2401.00001",
                                                  "A. Author et al.. (2024). No link. VLDB"]
    assert [s.authority for s in srcs] == [SourceAuthority.PEER_REVIEWED, SourceAuthority.SECONDARY,
                                           SourceAuthority.PEER_REVIEWED]
    assert srcs[0].read_in_full and not srcs[2].read_in_full            # abstract shown = record read

    page = extract_sources(_res("mcp-internet-search", "fetch", "# Limits\nAt most 2,000 messages per day.",
                                args={"url": "https://learn.microsoft.com/azure/limits"}))
    assert len(page) == 1 and page[0].read_in_full and page[0].title == "Limits"
    assert page[0].authority is SourceAuthority.PRIMARY_OFFICIAL and "2,000" in page[0].content

    blob = extract_sources(_res("mcp-internet-search", "search", "no links, just prose"))
    assert blob[0].url_or_citation.startswith("mcp:mcp-internet-search/search?")
    wrapped = extract_sources(_res("x", "search", "", structured={"result": "Doc\nURL: https://nist.gov/a"}))
    assert wrapped[0].url_or_citation == "https://nist.gov/a"
    from sit_review_agent.tools.gateway import _result
    failed = _result("call-9", "x", "search", {}, status=ToolCallStatus.ERROR, started_at="2026-10-02T09:00:00Z",
                     text="boom", is_error=True)
    assert extract_sources(failed) == []


@pytest.mark.parametrize("url, expected", [
    ("https://www.iso.org/standard/27001", SourceAuthority.PRIMARY_OFFICIAL),
    ("https://pdpc.gov.sg/guidelines", SourceAuthority.PRIMARY_OFFICIAL),
    ("https://www.cms.gov/x", SourceAuthority.PRIMARY_OFFICIAL),
    ("https://docs.aws.amazon.com/lambda/latest/dg/limits.html", SourceAuthority.PRIMARY_OFFICIAL),
    ("https://developer.example-vendor.com/api", SourceAuthority.PRIMARY_OFFICIAL),
    ("https://dl.acm.org/doi/10.1145/1", SourceAuthority.PEER_REVIEWED),
    ("doi:10.1109/5.771073", SourceAuthority.PEER_REVIEWED),
    ("https://arxiv.org/abs/2401.00001", SourceAuthority.SECONDARY),
    ("https://en.wikipedia.org/wiki/HNSW", SourceAuthority.SECONDARY),
    ("https://aws.amazon.com/blogs/database/x", SourceAuthority.SECONDARY),
    ("https://stackoverflow.com/q/1", SourceAuthority.INFORMAL),
    ("https://best-10-vector-dbs-2026.example.net/", SourceAuthority.INFORMAL),
    ("mcp:server/tool?{}", SourceAuthority.INFORMAL),
])
def test_classify_authority(url: str, expected: SourceAuthority) -> None:
    assert classify_authority(url) is expected


def test_independence_key() -> None:
    assert independence_key("https://docs.example.com/a") == independence_key("https://www.example.com/b")
    assert independence_key("https://a.example.co.uk/x") == "example.co.uk"
    assert independence_key("https://doi.org/10.1/a") != independence_key("https://doi.org/10.1/b")


def test_policy_module_has_no_secret_values(tmp_path: Path) -> None:
    import sit_review_agent.tools.policy as pol

    assert KEY not in Path(pol.__file__).read_text(encoding="utf-8")


# =============================================================================== preflight


class FakeLLM:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error

    async def preflight(self) -> None:
        if self.error is not None:
            raise self.error


async def test_preflight_all_green(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from sit_review_agent.selftest import run_preflight

    monkeypatch.setenv("SIT_MCP_API_KEY", KEY)
    out = io.StringIO()
    gw, _, _ = mcp_gateway({"mcp-internet-search": {}, "mcp-research-information": {"tools": ["search_works"]}},
                           FakeClock())
    ok = await run_preflight(cfg(), mcp=gw, llm=FakeLLM(), stream=out)
    text = out.getvalue()
    key_row = next(line for line in text.splitlines() if line.startswith("MCP key SIT_MCP_API_KEY"))
    assert ok and " OK " in key_row and "value not shown" in key_row
    assert "mcp-internet-search" in text and "1 tools, protocol 2025-11-25" in text
    assert "LLM backend claude_code" in text and KEY not in text and "preflight: OK" in text


async def test_preflight_missing_key_names_the_variable_and_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from sit_review_agent.selftest import run_preflight

    monkeypatch.delenv("SIT_MCP_API_KEY", raising=False)
    out = io.StringIO()
    ok = await run_preflight(cfg(), llm=FakeLLM(), stream=out)
    assert not ok and "SIT_MCP_API_KEY" in out.getvalue() and "--no-tools" in out.getvalue()


async def test_preflight_unreachable_servers_and_llm_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    import httpx2 as hx

    from sit_review_agent.errors import LLMAuthError
    from sit_review_agent.selftest import run_preflight

    monkeypatch.setenv("SIT_MCP_API_KEY", KEY)
    scripts = {s: {"init": [hx.ConnectError("refused")] * 3}
               for s in ("mcp-internet-search", "mcp-research-information")}
    gw, _, _ = mcp_gateway(scripts, FakeClock())
    out = io.StringIO()
    ok = await run_preflight(cfg(), mcp=gw, llm=FakeLLM(LLMAuthError("check the Claude Code login")), stream=out)
    text = out.getvalue()
    assert not ok and "WARN" in text and "no server reachable" in text and "check the Claude Code login" in text
    assert KEY not in text


async def test_preflight_doc_only_config(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    from sit_review_agent.selftest import run_preflight

    monkeypatch.delenv("SIT_MCP_API_KEY", raising=False)
    out = io.StringIO()
    assert await run_preflight(cfg(no_tools=True), llm=FakeLLM(), stream=out)
    assert "SKIP" in out.getvalue()
