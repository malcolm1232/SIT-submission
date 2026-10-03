"""The single choke point for every tool call (ADR-001, robustness §5.1, §10 item 1).

Layers, outermost first, assembled by :func:`build_tool_gateway`::

    LoggingToolGateway     writes tools.jsonl (one line per logical call)
    PolicyToolGateway      allowlist, URL policy, argument sanitiser, per-server breaker, budget
    SelfReplayGateway      on resume: serves calls already in this run's tools.jsonl (ADR-009)
    FaultInjectingGateway  robustness fault schedule (below the policy, so the policy is tested)
    RecordingGateway       --record: writes redacted cassettes
    base                   MCPToolGateway (live) | ReplayGateway (cassettes) | FakeToolGateway

Tool names the model sees are qualified ``<server>__<tool>`` (:func:`qualify`); the gateway
returns failures as :class:`ToolResult` with ``status != ok`` (they go back to the model as
``is_error`` tool results) and raises only for policy violations and strict replay misses.
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import os
import random
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from sit_review_agent.clock import Clock, SystemClock, isoformat_z
from sit_review_agent.config import EffectiveConfig, ToolsConfig, Transport
from sit_review_agent.errors import ReplayMiss, ToolNotAllowedError
from sit_review_agent.models import ResearchLogEntry, ToolCallStatus
from sit_review_agent.progress import ProgressSink
from sit_review_agent.rundir import JsonlWriter, RunDir, write_json_atomic
from sit_review_agent.states import PhaseName
from sit_review_agent.tools.cassette import (
    Redactor,
    canonical_args,
    cassette_key,
    cassette_path,
    tools_list_path,
)
from sit_review_agent.tools.faults import FaultSchedule

QUALIFIER = "__"
_TOOL_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def qualify(server: str, tool: str) -> str:
    """Model-facing tool name. Must match the API's ``^[a-zA-Z0-9_-]{1,64}$``."""
    name = f"{server}{QUALIFIER}{tool}"
    if not _TOOL_NAME_RE.match(name):
        raise ValueError(f"tool name {name!r} is not a valid API tool name")
    return name


def split_qualified(name: str) -> tuple[str, str]:
    server, sep, tool = name.partition(QUALIFIER)
    if not sep or not server or not tool:
        raise ToolNotAllowedError(f"unqualified tool name {name!r} (expected <server>{QUALIFIER}<tool>)")
    return server, tool


class ToolErrorClass(StrEnum):
    COLD_START = "cold_start"            # timeout / 502 / 503 / 504 on a sleeping container
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    HTTP_4XX = "http_4xx"
    HTTP_5XX = "http_5xx"
    AUTH = "auth"                        # 401 / 403: shared key, disables every server (INF-07)
    SESSION_EXPIRED = "session_expired"  # 404 on a stale Mcp-Session-Id: re-initialize (INF-09)
    SESSION_CLOSED = "session_closed"    # -32000 "Connection closed", EOF, reset: reopen once (NET-06)
    TOOL_ERROR = "tool_error"            # isError: true from the server
    MALFORMED = "malformed"
    BLOCKED = "blocked"                  # URL policy or sanitiser
    NOT_ALLOWED = "not_allowed"          # disabled server or tool not in allow_tools
    SERVER_DOWN = "server_down"          # breaker open
    BUDGET = "budget"                    # max_tool_calls reached
    REPLAY_MISS = "replay_miss"          # lenient replay returned an empty result
    UNKNOWN = "unknown"


class ServerHealth(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"
    DISABLED = "disabled"


@dataclass(frozen=True)
class ToolSpec:
    server: str
    name: str
    description: str
    input_schema: dict[str, Any]
    capability: str | None = None        # search | scholarly | browse (tools.yaml capabilities)

    @property
    def qualified_name(self) -> str:
        return qualify(self.server, self.name)

    def to_api_tool(self) -> dict[str, Any]:
        """Anthropic tool definition. ``strict`` is left to the research phase (MCP schemas may not
        satisfy strict mode's ``additionalProperties: false`` requirement)."""
        return {"name": self.qualified_name, "description": self.description, "input_schema": self.input_schema}


@dataclass(frozen=True)
class ToolAttempt:
    attempt: int
    started_at: str
    elapsed_s: float
    error_class: ToolErrorClass | None = None
    http_status: int | None = None
    message: str | None = None


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    server: str
    tool_name: str
    args: dict[str, Any]                 # canonical arguments
    status: ToolCallStatus
    is_error: bool
    content: list[dict[str, Any]]        # MCP content blocks (model_dump by_alias)
    text: str                            # joined text blocks
    structured_content: Any
    started_at: str
    elapsed_s: float
    cassette_key: str
    attempts: list[ToolAttempt] = field(default_factory=list)
    error_class: ToolErrorClass | None = None
    error_message: str | None = None
    replayed: bool = False

    @property
    def ok(self) -> bool:
        return self.status is ToolCallStatus.OK and not self.is_error

    def log_entry(self) -> dict[str, Any]:
        """One ``tools.jsonl`` line (REPRODUCIBILITY §6)."""
        return {"call_id": self.call_id, "server": self.server, "tool": self.tool_name, "args": self.args,
                "status": self.status.value, "is_error": self.is_error, "content": self.content, "text": self.text,
                "structured_content": self.structured_content, "started_at": self.started_at,
                "elapsed_s": self.elapsed_s, "cassette_key": self.cassette_key,
                "error_class": self.error_class.value if self.error_class else None,
                "error_message": self.error_message, "replayed": self.replayed,
                "attempts": [{**a.__dict__, "error_class": a.error_class.value if a.error_class else None}
                             for a in self.attempts]}

    @classmethod
    def from_log_entry(cls, e: Mapping[str, Any]) -> ToolResult:
        return cls(call_id=e["call_id"], server=e["server"], tool_name=e["tool"], args=e["args"],
                   status=ToolCallStatus(e["status"]), is_error=e["is_error"], content=e["content"], text=e["text"],
                   structured_content=e.get("structured_content"), started_at=e["started_at"],
                   elapsed_s=e["elapsed_s"], cassette_key=e["cassette_key"],
                   attempts=[ToolAttempt(**{**a, "error_class": ToolErrorClass(a["error_class"]) if a.get("error_class")
                                            else None}) for a in e.get("attempts", [])],
                   error_class=ToolErrorClass(e["error_class"]) if e.get("error_class") else None,
                   error_message=e.get("error_message"), replayed=True)

    def research_log_entry(self) -> ResearchLogEntry:
        return ResearchLogEntry(call_id=self.call_id, server=self.server, tool_name=self.tool_name,
                                status=self.status, started_at=self.started_at)


@runtime_checkable
class ToolGateway(Protocol):
    async def list_tools(self) -> list[ToolSpec]:
        """Tools currently offered (enabled, allowed, healthy servers only)."""
        ...

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> ToolResult:
        """Call ``<server>__<tool>``. Failures come back as a ToolResult with ``status != ok``."""
        ...

    async def aclose(self) -> None:
        ...


class CallIds:
    """Allocates run-unique tool call IDs ``call-0001`` (shared by all layers of one run)."""

    def __init__(self, start: int = 0) -> None:
        self._n = start

    def next(self) -> str:
        self._n += 1
        return f"call-{self._n:04d}"

    def advance_to(self, n: int) -> None:
        """Continue after ``call-<n>`` (resume, ADR-009): never goes backwards. Advancing the shared
        object in place keeps every layer that holds it (policy, fault injector, base) in step."""
        self._n = max(self._n, int(n))


def _result(call_id: str, server: str, tool: str, args: dict[str, Any], *, status: ToolCallStatus, started_at: str,
            text: str = "", content: list[dict[str, Any]] | None = None, is_error: bool = False,
            error_class: ToolErrorClass | None = None, error_message: str | None = None,
            replayed: bool = False, elapsed_s: float = 0.0, structured_content: Any = None) -> ToolResult:
    cargs = canonical_args(args)
    return ToolResult(call_id=call_id, server=server, tool_name=tool, args=cargs, status=status, is_error=is_error,
                      content=content if content is not None else ([{"type": "text", "text": text}] if text else []),
                      text=text, structured_content=structured_content, started_at=started_at, elapsed_s=elapsed_s,
                      cassette_key=cassette_key(server, tool, args), error_class=error_class,
                      error_message=error_message, replayed=replayed)


# =============================================================================== base: live MCP


class MCPToolGateway:
    """Direct MCP client over streamable HTTP (mcp 2.x), one session per enabled server.

    Verified pattern (scripts/probe_mcp_servers.py)::

        async with httpx2.AsyncClient(headers={auth_header: key}, timeout=httpx2.Timeout(t)) as http:
            async with streamable_http_client(url, http_client=http) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=t, client_info=...) as s:
                    await s.initialize(); await s.list_tools(); await s.call_tool(name, args, read_timeout_seconds=t)

    Behaviour: ``connect_timeout_s`` (150 s) for every ``initialize`` (a re-initialise after the
    container scaled to zero is a cold start too); ``cold_start_retries`` retries, 15 s apart, on a
    cold-start-like failure (``ExceptionGroup`` leaf ``httpx2.ReadTimeout``, ``RemoteProtocolError``,
    ``ReadError``, HTTP 502/503/504); on a stale session (mcp 2.2.0 surfaces HTTP 404 as
    ``MCPError(-32600, "Session terminated")``), re-``initialize`` once and repeat the call
    (INF-09); on a closed session (``MCPError(-32000, "Connection closed")``, a closed or ended
    stream, a reset connection: :attr:`ToolErrorClass.SESSION_CLOSED`) reopen the session (a new
    ``initialize``, same auth) once and repeat the call once (NET-06); a session idle longer than
    ``tools.session_idle_reopen_s`` is reopened before the next call instead of waiting for that
    error (sit_sample_tools_1: a session idle from 2 s to 132 s failed every web search). Each reopen
    is a disclosed event (a progress line, :attr:`session_events`, and the message of the call's
    attempt in ``tools.jsonl``), not a degradation; a confirmed 401/403 (a second auth refusal on
    any server: the original plus the policy layer's one confirmation retry) marks every server
    DOWN, sets :attr:`auth_failed` and every later call returns ``error_class=auth`` without
    touching the network (shared key,
    INF-07). The key is read from ``tools.auth_env`` (or ``api_key``) and never logged; messages
    name the variable only. Every failure is returned as a :class:`ToolResult`; nothing is raised
    except :class:`~sit_review_agent.errors.ToolNotAllowedError` for an unqualified tool name.

    ``session_factory`` (attribute) builds a session for ``(server, url, headers, timeout_s,
    on_response)``; the default is the live httpx2 + streamable-HTTP factory
    (:func:`~sit_review_agent.tools.mcp_client.make_http_session_factory`). Tests replace it with
    fakes, or with the live factory over ``httpx2.ASGITransport`` and an in-process MCP server.
    """

    #: Hard ceiling added to ``call_timeout_s`` around ``call_tool`` (the session's own read
    #: timeout should fire first; this guards against a wedged transport task group).
    CALL_GRACE_S = 5.0

    def __init__(self, tools: ToolsConfig, endpoints: Mapping[str, str], *, clock: Clock | None = None,
                 progress: ProgressSink | None = None, ids: CallIds | None = None,
                 api_key: str | None = None) -> None:
        from sit_review_agent.tools import mcp_client as mc  # mcp_client imports this module

        self.tools = tools
        self.endpoints = dict(endpoints)
        self.clock = clock or SystemClock()
        self.progress = progress
        self.ids = ids or CallIds()
        self._api_key = api_key
        self.health: dict[str, ServerHealth] = {
            s.name: (ServerHealth.OK if s.enabled else ServerHealth.DISABLED) for s in tools.servers}
        self.protocol_versions: dict[str, str] = {}
        self.session_factory: mc.SessionFactory = mc.make_http_session_factory()
        self.auth_failed = False
        self.last_errors: dict[str, str] = {}
        self._conns: dict[str, mc.ServerConnection] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._status: dict[str, mc.StatusLog] = {}
        self._tools: dict[str, list[ToolSpec]] = {}
        self._auth_strikes = 0
        self._cap_by_server = {srv: cap for cap, srv in tools.capabilities.items()}
        #: Last time each server's session was used (opened, or a call started or ended), monotonic.
        self._last_used: dict[str, float] = {}
        self._inflight: dict[str, int] = {}
        #: Every session reopen: ``{server, reason, idle_s, at_s}`` (disclosed, not a degradation).
        self.session_events: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ helpers
    def _emit(self, message: str, kind: str = "step") -> None:
        if self.progress is not None:
            self.progress.emit("tools", message, kind)  # type: ignore[arg-type]

    def _key(self) -> str:
        if self._api_key is not None:
            return self._api_key.strip()
        return os.environ.get(self.tools.auth_env, "").strip()

    def _auth_message(self, status: int | None) -> str:
        code = f"HTTP {status}" if status else "401/403"
        return (f"MCP authentication refused ({code}); the shared key in environment variable "
                f"{self.tools.auth_env} was rejected")

    def _auth_strike(self, status: int | None) -> None:
        self._auth_strikes += 1
        if self._auth_strikes >= 2 and not self.auth_failed:
            self.auth_failed = True
            for name, h in self.health.items():
                if h is not ServerHealth.DISABLED:
                    self.health[name] = ServerHealth.DOWN
            self._emit(f"{self._auth_message(status)} twice; every MCP server is disabled for this run "
                       f"(shared key). Check {self.tools.auth_env}; the review continues document-only.", "warn")

    async def _drop(self, server: str) -> None:
        conn = self._conns.pop(server, None)
        if conn is not None:
            await conn.close()

    async def _session(self, server: str, attempts: list[ToolAttempt]) -> Any:
        """The live session for ``server``, connecting (with the cold-start allowance) if needed.
        Raises :class:`_ServerFailure`."""
        session, _ = await self._acquire(server, attempts)
        return session

    def _idle_s(self, server: str) -> float | None:
        last = self._last_used.get(server)
        return None if last is None else self.clock.monotonic() - last

    def _touch(self, server: str) -> None:
        self._last_used[server] = self.clock.monotonic()

    def _session_event(self, server: str, reason: str, idle_s: float | None) -> str:
        idle = f"{idle_s:.0f} s" if idle_s is not None else "unknown"
        msg = (f"{server}: session reopened ({reason}; idle {idle}); a new initialize with the same key, "
               "not a degradation")
        self.session_events.append({"server": server, "reason": reason,
                                    "idle_s": round(idle_s, 3) if idle_s is not None else None,
                                    "at_s": round(self.clock.monotonic(), 3)})
        self._emit(msg, "step")
        return msg

    async def _acquire(self, server: str, attempts: list[ToolAttempt]) -> tuple[Any, Any]:
        """``(session, connection)`` for ``server``. A session idle longer than
        ``tools.session_idle_reopen_s`` (and with no call in flight) is reopened first."""
        lock = self._locks.setdefault(server, asyncio.Lock())
        async with lock:
            conn = self._conns.get(server)
            limit = self.tools.session_idle_reopen_s
            idle = self._idle_s(server)
            if (conn is not None and conn.alive and limit > 0 and idle is not None and idle > limit
                    and not self._inflight.get(server)):
                self._session_event(server, f"idle longer than session_idle_reopen_s {limit:.0f} s", idle)
                await self._drop(server)
                conn = None
            if conn is not None and conn.alive:
                return conn.session, conn
            if conn is not None:
                await self._drop(server)
            session = await self._connect(server, attempts)
            return session, self._conns.get(server)

    async def _reopen(self, server: str, failed: Any, attempts: list[ToolAttempt], reason: str) -> None:
        """Replace the connection ``failed`` (unless another call already replaced it)."""
        lock = self._locks.setdefault(server, asyncio.Lock())
        async with lock:
            if self._conns.get(server) is failed:
                self._session_event(server, reason, self._idle_s(server))
                await self._drop(server)

    async def _connect(self, server: str, attempts: list[ToolAttempt]) -> Any:
        from sit_review_agent.tools import mcp_client as mc

        if self.auth_failed:
            raise _ServerFailure(mc.Failure(ToolErrorClass.AUTH, self._auth_message(None) + "; servers disabled"))
        key = self._key()
        if not key:
            raise _ServerFailure(mc.Failure(
                ToolErrorClass.AUTH, f"environment variable {self.tools.auth_env} is not set (use --no-tools for a "
                                     "document-only review)"))
        url = self.endpoints.get(server)
        if not url:
            raise _ServerFailure(mc.Failure(ToolErrorClass.NOT_ALLOWED, f"no endpoint for {server} in endpoints.yaml"))
        headers = mc.auth_headers(self.tools.auth_header, key)
        status = self._status.setdefault(server, mc.StatusLog())
        retries = 0
        while True:
            status.clear()
            conn = mc.ServerConnection()
            t0, started = self.clock.monotonic(), isoformat_z(self.clock.now_utc())
            try:
                await conn.open(self.session_factory, server, url, headers, self.tools.connect_timeout_s, status.record)
            except Exception as exc:  # noqa: BLE001 - classified below, never escapes
                f = mc.classify_exception(exc, status_hint=status.last(), first_contact=True)
                attempts.append(ToolAttempt(attempt=len(attempts), started_at=started,
                                            elapsed_s=round(self.clock.monotonic() - t0, 3),
                                            error_class=f.error_class, http_status=f.http_status,
                                            message=f"initialize: {f.message}"))
                self.last_errors[server] = f.message
                if f.error_class is ToolErrorClass.AUTH:
                    self._auth_strike(f.http_status)
                    raise _ServerFailure(mc.Failure(ToolErrorClass.AUTH, self._auth_message(f.http_status),
                                                    f.http_status)) from None
                if f.error_class is ToolErrorClass.COLD_START and retries < self.tools.cold_start_retries:
                    retries += 1
                    self._emit(f"waking {server} (~90 s): {f.message}; retry {retries}/"
                               f"{self.tools.cold_start_retries} in {mc.COLD_RETRY_DELAY_S:.0f} s", "wait")
                    await self.clock.sleep(mc.COLD_RETRY_DELAY_S)
                    continue
                self.health[server] = (ServerHealth.DOWN if f.error_class in (
                    ToolErrorClass.COLD_START, ToolErrorClass.CONNECTION, ToolErrorClass.TIMEOUT)
                    else ServerHealth.DEGRADED)
                raise _ServerFailure(f) from None
            self._conns[server] = conn
            self._touch(server)
            self._auth_strikes = 0
            if self.health.get(server) is not ServerHealth.DISABLED:
                self.health[server] = ServerHealth.OK
            version = getattr(conn.init_result, "protocol_version", None)
            if version:
                self.protocol_versions[server] = str(version)
            return conn.session

    async def _list_server_tools(self, server: str) -> list[ToolSpec]:
        from sit_review_agent.tools import mcp_client as mc

        attempts: list[ToolAttempt] = []
        for reinit in (False, True):
            session = await self._session(server, attempts)
            try:
                specs: list[ToolSpec] = []
                cursor = None
                while True:
                    params = None
                    if cursor:
                        from mcp import types

                        params = types.PaginatedRequestParams(cursor=cursor)
                    lr = await asyncio.wait_for(session.list_tools(params=params),
                                                timeout=self.tools.call_timeout_s + self.CALL_GRACE_S)
                    for t in lr.tools:
                        try:
                            qualify(server, t.name)
                        except ValueError:
                            self._emit(f"{server}: tool {t.name!r} skipped (name not usable as an API tool name)",
                                       "warn")
                            continue
                        specs.append(ToolSpec(server=server, name=t.name, description=t.description or "",
                                              input_schema=dict(t.input_schema or {"type": "object"}),
                                              capability=self._cap_by_server.get(server)))
                    cursor = getattr(lr, "next_cursor", None)
                    if not cursor:
                        break
            except Exception as exc:  # noqa: BLE001
                f = mc.classify_exception(exc, status_hint=self._status.setdefault(server, mc.StatusLog()).last())
                await self._drop(server)
                if f.error_class in (ToolErrorClass.SESSION_EXPIRED, ToolErrorClass.SESSION_CLOSED) and not reinit:
                    if f.error_class is ToolErrorClass.SESSION_CLOSED:
                        self._session_event(server, "closed during tools/list", self._idle_s(server))
                    continue
                if f.error_class is ToolErrorClass.AUTH:
                    self._auth_strike(f.http_status)
                self.health[server] = ServerHealth.DEGRADED
                self.last_errors[server] = f.message
                raise _ServerFailure(f) from None
            self._touch(server)
            self._tools[server] = specs
            return specs
        raise AssertionError("unreachable")  # pragma: no cover

    def _fail(self, call_id: str, server: str, tool: str, args: dict[str, Any], started: str, t0: float,
              failure: Any, attempts: list[ToolAttempt]) -> ToolResult:
        cls: ToolErrorClass = failure.error_class
        status = (ToolCallStatus.TIMEOUT if cls in (ToolErrorClass.TIMEOUT, ToolErrorClass.COLD_START)
                  else ToolCallStatus.BLOCKED if cls is ToolErrorClass.NOT_ALLOWED else ToolCallStatus.ERROR)
        sc = {"retry_after_s": failure.retry_after_s} if failure.retry_after_s is not None else None
        res = _result(call_id, server, tool, args, status=status, started_at=started, is_error=True,
                      error_class=cls, error_message=failure.message, structured_content=sc,
                      elapsed_s=round(self.clock.monotonic() - t0, 3))
        return dataclasses.replace(res, attempts=list(attempts))

    # ------------------------------------------------------------------ protocol
    async def warm_up(self) -> dict[str, ServerHealth]:
        """Initialize + ``tools/list`` on every enabled server in parallel (background, at t=0,
        overlapping ingest/understand; runbook §7 drill 1). Emits a progress line per server."""

        async def one(server: str) -> None:
            self._emit(f"waking {server} (~90 s)", "wait")
            try:
                specs = await self._list_server_tools(server)
            except _ServerFailure as exc:
                self._emit(f"{server} unavailable after warm-up: {exc.failure.message}", "warn")
                return
            self._emit(f"{server} ready ({len(specs)} tools)", "done")

        await asyncio.gather(*(one(s.name) for s in self.tools.enabled_servers()))
        return dict(self.health)

    async def list_tools(self) -> list[ToolSpec]:
        servers = [s.name for s in self.tools.enabled_servers()
                   if not self.auth_failed and self.health.get(s.name) is not ServerHealth.DOWN]

        async def one(server: str) -> list[ToolSpec]:
            if server in self._tools:
                return self._tools[server]
            try:
                return await self._list_server_tools(server)
            except _ServerFailure:
                return []

        lists = await asyncio.gather(*(one(s) for s in servers))
        return [t for specs in lists for t in specs]

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> ToolResult:
        from sit_review_agent.tools import mcp_client as mc

        server, tool = split_qualified(tool_name)
        call_id = self.ids.next()
        started, t0 = isoformat_z(self.clock.now_utc()), self.clock.monotonic()
        attempts: list[ToolAttempt] = []
        srv = self.tools.server(server)
        if srv is None or not srv.enabled:
            return self._fail(call_id, server, tool, args, started, t0, mc.Failure(
                ToolErrorClass.NOT_ALLOWED, f"server {server} is unknown or disabled"), attempts)
        if self.auth_failed:
            return self._fail(call_id, server, tool, args, started, t0, mc.Failure(
                ToolErrorClass.AUTH, self._auth_message(None) + "; every server is disabled"), attempts)
        reinitialised = False
        note: str | None = None
        while True:
            events_before = len(self.session_events)
            try:
                session, conn = await self._acquire(server, attempts)
            except _ServerFailure as exc:
                return self._fail(call_id, server, tool, args, started, t0, exc.failure, attempts)
            if len(self.session_events) > events_before and note is None:
                ev = self.session_events[-1]
                note = f"session reopened before the call ({ev['reason']}; idle {ev['idle_s']:.0f} s)"
            status_log = self._status.setdefault(server, mc.StatusLog())
            status_log.clear()
            a0, a_started = self.clock.monotonic(), isoformat_z(self.clock.now_utc())
            self._inflight[server] = self._inflight.get(server, 0) + 1
            self._touch(server)
            try:
                raw = await asyncio.wait_for(
                    session.call_tool(tool, args, read_timeout_seconds=self.tools.call_timeout_s),
                    timeout=self.tools.call_timeout_s + self.CALL_GRACE_S)
            except Exception as exc:  # noqa: BLE001 - classified, returned as a result
                f = mc.classify_exception(exc, status_hint=status_log.last(), first_contact=False)
                attempts.append(ToolAttempt(attempt=len(attempts), started_at=a_started,
                                            elapsed_s=round(self.clock.monotonic() - a0, 3), error_class=f.error_class,
                                            http_status=f.http_status, message=f.message))
                self.last_errors[server] = f.message
                if f.error_class is ToolErrorClass.SESSION_EXPIRED and not reinitialised:
                    reinitialised = True
                    self._emit(f"{server}: session expired (HTTP 404); re-initialising once", "warn")
                    await self._drop(server)
                    continue
                if f.error_class is ToolErrorClass.SESSION_CLOSED and not reinitialised:
                    # A session error, not a tool error: reopen once (unless a concurrent call already
                    # did) and repeat the call once; only a second failure counts against the tool.
                    reinitialised = True
                    await self._reopen(server, conn, attempts, f"closed by the server: {f.message}")
                    note = "retried once after the session was reopened"
                    continue
                if f.error_class is ToolErrorClass.AUTH:
                    self._auth_strike(f.http_status)
                    f = mc.Failure(ToolErrorClass.AUTH, self._auth_message(f.http_status), f.http_status)
                if f.error_class in (ToolErrorClass.CONNECTION, ToolErrorClass.TIMEOUT, ToolErrorClass.SESSION_EXPIRED,
                                     ToolErrorClass.SESSION_CLOSED, ToolErrorClass.MALFORMED, ToolErrorClass.UNKNOWN):
                    # The transport may be wedged; reconnect next time (unless a concurrent call already
                    # replaced this connection with a fresh one).
                    if self._conns.get(server) is conn:
                        await self._drop(server)
                return self._fail(call_id, server, tool, args, started, t0, f, attempts)
            finally:
                self._inflight[server] -= 1
                self._touch(server)
            attempts.append(ToolAttempt(attempt=len(attempts), started_at=a_started,
                                        elapsed_s=round(self.clock.monotonic() - a0, 3), message=note))
            self._auth_strikes = 0
            return self._convert(call_id, server, tool, args, started, t0, raw, attempts)

    def _convert(self, call_id: str, server: str, tool: str, args: dict[str, Any], started: str, t0: float,
                 raw: Any, attempts: list[ToolAttempt]) -> ToolResult:
        from sit_review_agent.tools import mcp_client as mc

        if not hasattr(raw, "content"):
            return self._fail(call_id, server, tool, args, started, t0, mc.Failure(
                ToolErrorClass.TOOL_ERROR, f"unsupported MCP result type {type(raw).__name__} (input required?)"),
                attempts)
        content: list[dict[str, Any]] = []
        for b in raw.content or []:
            dump = getattr(b, "model_dump", None)
            content.append(dump(mode="json", by_alias=True, exclude_none=True) if dump else dict(b))
        text = "\n".join(str(b.get("text", "")) for b in content if b.get("type") == "text")
        is_error = bool(getattr(raw, "is_error", False))
        res = _result(call_id, server, tool, args, status=ToolCallStatus.ERROR if is_error else ToolCallStatus.OK,
                      started_at=started, text=text, content=content, is_error=is_error,
                      error_class=ToolErrorClass.TOOL_ERROR if is_error else None,
                      error_message=text[:500] if is_error else None,
                      structured_content=getattr(raw, "structured_content", None),
                      elapsed_s=round(self.clock.monotonic() - t0, 3))
        return dataclasses.replace(res, attempts=list(attempts))

    async def aclose(self) -> None:
        for server in list(self._conns):
            await self._drop(server)


class _ServerFailure(Exception):
    """Internal: a classified failure to reach a server (``failure`` is an ``mcp_client.Failure``)."""

    def __init__(self, failure: Any) -> None:
        super().__init__(failure.message)
        self.failure = failure


# =============================================================================== base: replay


class ReplayGateway:
    """Serves calls from cassettes (``--transport replay`` / ``--replay <fixtures>``).

    ``strict=True`` raises :class:`~sit_review_agent.errors.ReplayMiss` on an unseen call (tests,
    eval). ``strict=False`` returns an empty ``ok`` result tagged ``replay_miss`` (exploration only).
    ``list_tools`` reads ``tools_list/<server>.json`` (a list of ``{name, description, input_schema}``).
    """

    def __init__(self, cassette_dir: str | Path, *, strict: bool = True, servers: Sequence[str] | None = None,
                 clock: Clock | None = None, ids: CallIds | None = None,
                 capabilities: Mapping[str, str] | None = None) -> None:
        self.cassette_dir = Path(cassette_dir)
        self.strict = strict
        self.servers = list(servers) if servers is not None else None
        self.clock = clock or SystemClock()
        self.ids = ids or CallIds()
        self._cap_by_server = {srv: cap for cap, srv in (capabilities or {}).items()}

    async def list_tools(self) -> list[ToolSpec]:
        out: list[ToolSpec] = []
        root = self.cassette_dir / "tools_list"
        if not root.exists():
            return out
        for path in sorted(root.glob("*.json")):
            server = path.stem
            if self.servers is not None and server not in self.servers:
                continue
            for t in json.loads(path.read_text(encoding="utf-8")):
                out.append(ToolSpec(server=server, name=t["name"], description=t.get("description") or "",
                                    input_schema=t.get("input_schema") or {"type": "object"},
                                    capability=self._cap_by_server.get(server)))
        return out

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> ToolResult:
        server, tool = split_qualified(tool_name)
        key = cassette_key(server, tool, args)
        path = cassette_path(self.cassette_dir, server, tool, key)
        started = isoformat_z(self.clock.now_utc())
        call_id = self.ids.next()
        if not path.exists():
            if self.strict:
                raise ReplayMiss(key, server, tool)
            return _result(call_id, server, tool, args, status=ToolCallStatus.OK, started_at=started,
                           error_class=ToolErrorClass.REPLAY_MISS, error_message="lenient replay miss",
                           replayed=True)
        rec = json.loads(path.read_text(encoding="utf-8"))
        res = rec.get("result") or {}
        content = res.get("content") or []
        text = "\n".join(b.get("text", "") for b in content if b.get("type") == "text")
        is_error = bool(res.get("isError"))
        return _result(call_id, server, tool, args, status=ToolCallStatus.ERROR if is_error else ToolCallStatus.OK,
                       started_at=started, text=text, content=content, is_error=is_error,
                       error_class=ToolErrorClass.TOOL_ERROR if is_error else None,
                       structured_content=res.get("structuredContent"), replayed=True,
                       elapsed_s=float(rec.get("latency_ms", 0)) / 1000)

    async def aclose(self) -> None:
        return None


class FakeToolGateway:
    """In-process fake for L0 tests: ``handlers[qualified_name](args) -> text`` (or raises)."""

    def __init__(self, tools: Sequence[ToolSpec], handlers: Mapping[str, Callable[[dict[str, Any]], str]], *,
                 clock: Clock | None = None, ids: CallIds | None = None) -> None:
        self.tools = list(tools)
        self.handlers = dict(handlers)
        self.clock = clock or SystemClock()
        self.ids = ids or CallIds()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def list_tools(self) -> list[ToolSpec]:
        return list(self.tools)

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> ToolResult:
        server, tool = split_qualified(tool_name)
        self.calls.append((tool_name, args))
        started = isoformat_z(self.clock.now_utc())
        call_id = self.ids.next()
        handler = self.handlers.get(tool_name)
        if handler is None:
            return _result(call_id, server, tool, args, status=ToolCallStatus.ERROR, started_at=started,
                           is_error=True, error_class=ToolErrorClass.TOOL_ERROR, error_message="unknown tool",
                           text="unknown tool")
        return _result(call_id, server, tool, args, status=ToolCallStatus.OK, started_at=started, text=handler(args))

    async def aclose(self) -> None:
        return None


# =============================================================================== wrappers


class RecordingGateway:
    """Delegates to ``inner`` and writes one redacted cassette per call (``--record``).
    ``list_tools`` results are written to ``tools_list/<server>.json``. Secrets never reach disk."""

    def __init__(self, inner: ToolGateway, cassette_dir: str | Path, redactor: Redactor, *,
                 clock: Clock | None = None, notes: str = "live recording") -> None:
        self.inner = inner
        self.cassette_dir = Path(cassette_dir)
        self.redactor = redactor
        self.clock = clock or SystemClock()
        self.notes = notes

    async def list_tools(self) -> list[ToolSpec]:
        tools = await self.inner.list_tools()
        by_server: dict[str, list[dict[str, Any]]] = {}
        for t in tools:
            by_server.setdefault(t.server, []).append(
                {"name": t.name, "description": t.description, "input_schema": t.input_schema})
        for server, items in by_server.items():
            write_json_atomic(tools_list_path(self.cassette_dir, server), self.redactor.deep(items))
        return tools

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> ToolResult:
        res = await self.inner.call(tool_name, args, phase=phase)
        if res.status is ToolCallStatus.OK or res.error_class is ToolErrorClass.TOOL_ERROR:
            rec = {"key": res.cassette_key, "server": res.server, "tool": res.tool_name, "args": res.args,
                   "recorded_at": isoformat_z(self.clock.now_utc()), "latency_ms": int(res.elapsed_s * 1000),
                   "transport": {"status": 200},
                   "result": {"content": res.content, "isError": res.is_error,
                              "structuredContent": res.structured_content},
                   "notes": self.notes}
            write_json_atomic(cassette_path(self.cassette_dir, res.server, res.tool_name, res.cassette_key),
                              self.redactor.deep(rec))
        return res

    async def aclose(self) -> None:
        await self.inner.aclose()


class FaultInjectingGateway:
    """Applies the ``mcp:`` rules of a :class:`FaultSchedule` to calls of ``inner`` (robustness
    §5.3 fault types; deterministic ``flaky`` via ``Random(hash(seed, server, tool, call_index))``)."""

    #: Fault types that rewrite an ``ok`` result of ``inner`` instead of replacing the call.
    _CONTENT_FAULTS = frozenset({"empty_result", "partial_result", "truncate_text", "oversize", "url_mismatch"})
    #: Fault types for other layers (LLM, process); ignored here.
    _NOT_MCP = frozenset({"stop_reason", "schema_violation", "offline", "raise_in_stage", "sigint_in_stage",
                          "clock_jump", "schema_drift"})

    def __init__(self, inner: ToolGateway, schedule: FaultSchedule, *, clock: Clock | None = None) -> None:
        from sit_review_agent.tools.mcp_client import find_attr

        self.inner = inner
        self.schedule = schedule
        self.clock = clock or SystemClock()
        tools_cfg = find_attr(inner, "tools")
        #: What a ``hang`` costs: the live gateway's read timeout (robustness INF-19).
        self.call_timeout_s: float = float(getattr(tools_cfg, "call_timeout_s", 60.0))
        self.injected: list[dict[str, Any]] = []        # every fault applied (tests, manifest notes)
        self._t0 = self.clock.monotonic()
        self._ids: CallIds = find_attr(inner, "ids") or CallIds(start=900000)
        self._server_calls: dict[str, int] = {}
        self._tool_calls: dict[str, int] = {}
        self._key_calls: dict[str, int] = {}
        self._contacted: set[str] = set()

    async def list_tools(self) -> list[ToolSpec]:
        """``schema_drift {tools_list: path}`` replaces the matching servers' ``tools/list`` with
        the fixture (a JSON list of ``{name, description, input_schema}``; INF-12)."""
        from sit_review_agent.paths import repo_root
        from sit_review_agent.tools.fault_apply import match_rule
        from sit_review_agent.tools.faults import FaultType

        tools = await self.inner.list_tools()
        for rule in self.schedule.mcp:
            if rule.fault.type is not FaultType.SCHEMA_DRIFT:
                continue
            raw = (rule.fault.model_extra or {}).get("tools_list")
            if not raw:
                continue
            path = Path(raw) if Path(raw).is_absolute() or Path(raw).exists() else repo_root() / raw
            fixture = json.loads(path.read_text(encoding="utf-8"))
            servers = sorted({t.server for t in tools})
            for server in servers:
                if not match_rule(rule.match, server=server, elapsed_s=self.clock.monotonic() - self._t0):
                    continue
                cap = next((t.capability for t in tools if t.server == server), None)
                tools = [t for t in tools if t.server != server] + [
                    ToolSpec(server=server, name=d["name"], description=d.get("description") or "",
                             input_schema=d.get("input_schema") or {"type": "object"}, capability=cap)
                    for d in fixture]
                self.injected.append({"server": server, "fault": "schema_drift"})
        return tools

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> ToolResult:
        from sit_review_agent.tools import fault_apply as fa

        server, tool = split_qualified(tool_name)
        started, t_start = isoformat_z(self.clock.now_utc()), self.clock.monotonic()
        elapsed = t_start - self._t0
        call_index = self._server_calls.get(server, 0)
        self._server_calls[server] = call_index + 1
        nth = self._tool_calls.get(tool_name, 0)
        self._tool_calls[tool_name] = nth + 1
        key = cassette_key(server, tool, args)
        attempt = self._key_calls.get(key, 0)
        self._key_calls[key] = attempt + 1
        stage = phase.value if phase is not None else None
        rng = fa.seeded_rng(self.schedule.seed, server, tool, call_index)
        note = {"server": server, "tool": tool, "call_index": call_index, "attempt": attempt}

        if fa.offline_now(self.schedule, elapsed):
            self.injected.append({**note, "fault": "offline"})
            return self._failed(server, tool, args, started, t_start, ToolErrorClass.CONNECTION,
                                "network unreachable (offline)")
        delay = 0.0
        terminal: Any = None
        content_faults: list[Any] = []
        for rule in self.schedule.mcp:
            if rule.fault.type.value in self._NOT_MCP:
                continue
            if not fa.match_rule(rule.match, server=server, tool=tool, call_index=call_index, nth=nth, stage=stage,
                                 attempt=attempt, elapsed_s=elapsed, args=args):
                continue
            spec = fa.resolve_flaky(rule.fault, rng)
            if spec is None:
                continue
            kind = spec.type.value
            if kind == "latency":
                delay += fa.latency_seconds(spec, rng)
            elif kind == "down" and not fa.down_active(rule, elapsed):
                continue
            elif kind in self._CONTENT_FAULTS:
                content_faults.append(spec)
            elif terminal is None and kind not in self._NOT_MCP:
                terminal = spec
            else:
                continue
            self.injected.append({**note, "fault": kind})
        if delay:
            await self.clock.sleep(delay)
        if terminal is not None:
            return await self._terminal(terminal, server, tool, args, started, t_start)
        res = await self.inner.call(tool_name, args, phase=phase)
        if res.ok:
            self._contacted.add(server)
            for spec in content_faults:
                res = self._degrade(spec, res, rng)
        return dataclasses.replace(res, started_at=started,
                                   elapsed_s=round(res.elapsed_s + delay, 3))

    # ------------------------------------------------------------------ helpers
    def _failed(self, server: str, tool: str, args: dict[str, Any], started: str, t_start: float,
                cls: ToolErrorClass, message: str, *, http_status: int | None = None,
                retry_after_s: float | None = None) -> ToolResult:
        status = ToolCallStatus.TIMEOUT if cls in (ToolErrorClass.TIMEOUT,) else ToolCallStatus.ERROR
        elapsed = round(self.clock.monotonic() - t_start, 3)
        res = _result(self._ids.next(), server, tool, args, status=status, started_at=started, is_error=True,
                      error_class=cls, error_message=f"{message} [injected fault]", elapsed_s=elapsed,
                      structured_content={"retry_after_s": retry_after_s} if retry_after_s is not None else None)
        return dataclasses.replace(res, attempts=[ToolAttempt(attempt=0, started_at=started, elapsed_s=elapsed,
                                                              error_class=cls, http_status=http_status,
                                                              message=message)])

    async def _terminal(self, spec: Any, server: str, tool: str, args: dict[str, Any], started: str,
                        t_start: float) -> ToolResult:
        from sit_review_agent.tools import mcp_client as mc
        from sit_review_agent.tools.fault_apply import param

        kind = spec.type.value
        if kind == "hang":
            await self.clock.sleep(self.call_timeout_s)
            return self._failed(server, tool, args, started, t_start, ToolErrorClass.TIMEOUT,
                                f"no response within {self.call_timeout_s:.0f} s (hang)")
        if kind in ("http_status", "auth"):
            status = int(param(spec, "status", param(spec, "code", param(spec, "value", 401 if kind == "auth"
                                                                               else 500))))
            ra = param(spec, "retry_after")
            f = mc.classify_status(status, first_contact=server not in self._contacted,
                                   retry_after_s=float(ra) if ra is not None else None)
            return self._failed(server, tool, args, started, t_start, f.error_class, f.message,
                                http_status=status, retry_after_s=f.retry_after_s)
        if kind == "connection_reset":
            return self._failed(server, tool, args, started, t_start, ToolErrorClass.CONNECTION,
                                "connection reset by peer")
        if kind == "down":
            return self._failed(server, tool, args, started, t_start, ToolErrorClass.CONNECTION,
                                "connection refused (server down)")
        if kind == "malformed_body":
            return self._failed(server, tool, args, started, t_start, ToolErrorClass.MALFORMED,
                                f"malformed response body ({param(spec, 'kind', 'non_json')})")
        if kind == "session_expired":
            return self._failed(server, tool, args, started, t_start, ToolErrorClass.SESSION_EXPIRED,
                                "session terminated (HTTP 404 on a stale Mcp-Session-Id)", http_status=404)
        if kind == "tool_error":
            message = str(param(spec, "message", "tool error"))
            res = _result(self._ids.next(), server, tool, args, status=ToolCallStatus.ERROR, started_at=started,
                          text=message, is_error=True, error_class=ToolErrorClass.TOOL_ERROR, error_message=message,
                          elapsed_s=round(self.clock.monotonic() - t_start, 3))
            return res
        if kind == "replace_content":
            return self._replaced(spec, server, tool, args, started, t_start)
        return self._failed(server, tool, args, started, t_start, ToolErrorClass.UNKNOWN,
                            f"unsupported fault type {kind}")

    def _replaced(self, spec: Any, server: str, tool: str, args: dict[str, Any], started: str,
                  t_start: float) -> ToolResult:
        """``replace_content {fixture}``: an ``ok`` result built from a cassette-shaped JSON file,
        a ``{content: [...]}`` object, or a plain string (INF-06, INF-15, ADV-04)."""
        from sit_review_agent.paths import repo_root
        from sit_review_agent.tools.fault_apply import param

        raw = str(param(spec, "fixture", ""))
        path = Path(raw) if Path(raw).is_absolute() or Path(raw).exists() else repo_root() / raw
        data = json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else path.read_text("utf-8")
        result = data.get("result", data) if isinstance(data, dict) else {"content": [{"type": "text", "text": data}]}
        content = result.get("content") or []
        text = "\n".join(str(b.get("text", "")) for b in content if b.get("type") == "text")
        is_error = bool(result.get("isError"))
        return _result(self._ids.next(), server, tool, args,
                       status=ToolCallStatus.ERROR if is_error else ToolCallStatus.OK, started_at=started, text=text,
                       content=content, is_error=is_error, error_class=ToolErrorClass.TOOL_ERROR if is_error else None,
                       structured_content=result.get("structuredContent"),
                       elapsed_s=round(self.clock.monotonic() - t_start, 3))

    @staticmethod
    def _degrade(spec: Any, res: ToolResult, rng: random.Random) -> ToolResult:
        from sit_review_agent.tools.fault_apply import param

        kind = spec.type.value
        text = res.text
        structured = res.structured_content
        if kind == "empty_result":
            return dataclasses.replace(res, content=[], text="", structured_content=None)
        if kind == "partial_result":
            keep = int(param(spec, "keep", 1))
            try:
                data = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                data = None
            if isinstance(data, list):
                text = json.dumps(data[:keep], ensure_ascii=False)
            elif isinstance(data, dict):
                for k, v in data.items():
                    if isinstance(v, list):
                        data = {**data, k: v[:keep]}
                        break
                text = json.dumps(data, ensure_ascii=False)
            else:
                parts = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
                text = "\n\n".join(parts[:keep])
            structured = None
        elif kind == "truncate_text":
            text = text[: int(len(text) * float(param(spec, "fraction", 0.5)))]
            structured = None
        elif kind == "oversize":
            target = int(param(spec, "bytes", 2_000_000))
            filler = "lorem ipsum dolor sit amet "
            pad = max(0, target - len(text.encode("utf-8")))
            text = text + "\n" + (filler * (pad // len(filler) + 1))[:pad]
        elif kind == "url_mismatch":
            text = "Page URL: https://url-mismatch.invalid/\n" + text
            structured = {"url": "https://url-mismatch.invalid/"}
        return dataclasses.replace(res, content=[{"type": "text", "text": text}] if text else [], text=text,
                                   structured_content=structured)

    async def aclose(self) -> None:
        await self.inner.aclose()


class SelfReplayGateway:
    """Resume support (ADR-009 item 2): a call whose cassette key already appears with status ok
    in this run's ``tools.jsonl`` (up to the checkpoint offset) is served from there and not
    repeated; everything else goes to ``inner``."""

    def __init__(self, inner: ToolGateway, run_dir: RunDir, *, upto_offset: int | None = None) -> None:
        self.inner = inner
        self.run_dir = run_dir
        self.upto_offset = upto_offset
        self._queues: dict[str, list[dict[str, Any]]] | None = None
        self.served: list[str] = []          # call IDs served from tools.jsonl (tests, manifest)

    def _index(self) -> dict[str, list[dict[str, Any]]]:
        """``cassette_key -> [log entries]`` of ok calls logged before ``upto_offset``, one entry per
        call ID (a call already replayed by an earlier resume is logged twice with the same ID)."""
        if self._queues is None:
            seen: set[str] = set()
            queues: dict[str, list[dict[str, Any]]] = {}
            for e in JsonlWriter(self.run_dir.tools_log).read(self.upto_offset):
                cid = e.get("call_id")
                if not cid or cid in seen or e.get("status") != ToolCallStatus.OK.value or e.get("is_error"):
                    continue
                seen.add(cid)
                queues.setdefault(str(e.get("cassette_key")), []).append(e)
            self._queues = queues
        return self._queues

    async def list_tools(self) -> list[ToolSpec]:
        return await self.inner.list_tools()

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> ToolResult:
        server, tool = split_qualified(tool_name)
        queue = self._index().get(cassette_key(server, tool, args))
        if queue:
            entry = queue.pop(0)             # each logged call is served once, in log order
            self.served.append(str(entry["call_id"]))
            return ToolResult.from_log_entry(entry)
        return await self.inner.call(tool_name, args, phase=phase)

    async def aclose(self) -> None:
        await self.inner.aclose()


def genuine_failure(res: ToolResult) -> bool:
    """A failure that counts against the tool (INF-11, NET-06): a tool error from a live session, or a
    closed session met again after the session was reopened for this call. A session error that the
    reopen recovered, and failures to reach the server, do not count (the breaker handles those)."""
    if res.ok:
        return False
    if res.error_class is ToolErrorClass.TOOL_ERROR:
        return True
    if res.error_class is ToolErrorClass.SESSION_CLOSED:
        return sum(a.error_class is ToolErrorClass.SESSION_CLOSED for a in res.attempts) >= 2
    return False


class PolicyToolGateway:
    """Allowlist (``tools.yaml allow_tools``), URL policy (``url_policy.yaml``), argument sanitiser
    (secrets and canaries never leave the process, ADV-05), per-server breaker (``ServerHealth``),
    retry with jitter for transient errors, and the ``max_tool_calls`` budget. A refused call is
    returned with status ``blocked``; a budget hit with ``error_class=budget``."""

    #: At most this many attempts per logical call (robustness INF-04).
    MAX_ATTEMPTS = 3
    BACKOFF_BASE_S = 1.0
    BACKOFF_MAX_S = 20.0
    #: ``Retry-After`` is honoured up to this many seconds (INF-05 "capped at the remaining budget").
    MAX_RETRY_AFTER_S = 120.0
    #: Consecutive failed logical calls that open a server's breaker (INF-03/04), and how long it
    #: stays open before one half-open probe is let through (INF-25).
    BREAKER_THRESHOLD = 3
    BREAKER_COOLDOWN_S = 60.0
    #: In-flight calls per server, and the reduced cap after a 429 (INF-05).
    DEFAULT_CONCURRENCY = 4
    RATE_LIMITED_CONCURRENCY = 1
    #: Consecutive genuine failures after which a tool is unusable for the run (INF-11): a tool error
    #: from a live session, or a call that failed again after its session was reopened. A session
    #: error the reopen recovered never counts (NET-06, sit_sample_tools_1).
    TOOL_ERROR_LIMIT = 2
    _RETRYABLE = frozenset({ToolErrorClass.COLD_START, ToolErrorClass.TIMEOUT, ToolErrorClass.CONNECTION,
                            ToolErrorClass.HTTP_5XX, ToolErrorClass.UNKNOWN})
    #: Failures that say nothing about the server being unreachable (they reset the breaker).
    _SERVER_ANSWERED = frozenset({ToolErrorClass.TOOL_ERROR, ToolErrorClass.HTTP_4XX, ToolErrorClass.REPLAY_MISS})

    def __init__(self, inner: ToolGateway, config: EffectiveConfig, redactor: Redactor, *,
                 clock: Clock | None = None, progress: ProgressSink | None = None) -> None:
        from sit_review_agent.tools.mcp_client import find_attr
        from sit_review_agent.tools.policy import SeenUrls

        self.inner = inner
        self.config = config
        self.redactor = redactor
        self.clock = clock or SystemClock()
        self.progress = progress
        self.calls_made = 0
        self.seen = SeenUrls()
        self.auth_disabled = False
        self.unusable_tools: set[str] = set()
        #: Disclosable events (breaker opened, auth cascade, tool marked unusable) for the research log.
        self.events: list[str] = []
        self._ids: CallIds = find_attr(inner, "ids") or CallIds(start=800000)
        self._rng = random.Random(0)
        self._failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}
        self._first_call_at: dict[str, float] = {}
        self._tool_error_streak: dict[str, int] = {}
        #: Per tool: logical calls, tool errors, failures after a session reopen, session errors recovered.
        self.tool_counts: dict[str, dict[str, int]] = {}
        self._caps: dict[str, int] = {}
        self._inflight: dict[str, int] = {}
        self._cond: asyncio.Condition | None = None

    # ------------------------------------------------------------------ public helpers
    def seed_urls(self, urls: Sequence[str]) -> None:
        """URLs the document cites: fetchable under ``fetch_only_from_results``."""
        self.seen.add(urls)

    def server_open(self, server: str) -> bool:
        """True while ``server``'s breaker is open (calls are refused without touching it)."""
        until = self._open_until.get(server)
        return until is not None and self.clock.monotonic() < until

    def health(self) -> dict[str, ServerHealth]:
        out: dict[str, ServerHealth] = {}
        for s in self.config.tools.servers:
            if not s.enabled:
                out[s.name] = ServerHealth.DISABLED
            elif self.auth_disabled or self.server_open(s.name):
                out[s.name] = ServerHealth.DOWN
            elif self._failures.get(s.name):
                out[s.name] = ServerHealth.DEGRADED
            else:
                out[s.name] = ServerHealth.OK
        return out

    # ------------------------------------------------------------------ internals
    def _emit(self, phase: PhaseName | None, message: str, kind: str = "warn") -> None:
        if self.progress is not None:
            self.progress.emit(phase.value if phase else "tools", message, kind)  # type: ignore[arg-type]

    def _refuse(self, server: str, tool: str, args: dict[str, Any], cls: ToolErrorClass, message: str, *,
                status: ToolCallStatus = ToolCallStatus.BLOCKED) -> ToolResult:
        return _result(self._ids.next(), server, tool, args, status=status,
                       started_at=isoformat_z(self.clock.now_utc()), is_error=True, error_class=cls,
                       error_message=message)

    @contextlib.asynccontextmanager
    async def _slot(self, server: str) -> Any:
        if self._cond is None:
            self._cond = asyncio.Condition()
        cond = self._cond
        async with cond:
            cap = self._caps.get(server, self.DEFAULT_CONCURRENCY)
            await cond.wait_for(lambda: self._inflight.get(server, 0) < self._caps.get(server, cap))
            self._inflight[server] = self._inflight.get(server, 0) + 1
        try:
            yield
        finally:
            async with cond:
                self._inflight[server] -= 1
                cond.notify_all()

    def _backoff(self, n: int) -> float:
        """Full jitter (seeded, deterministic per gateway instance)."""
        return self._rng.uniform(0.0, min(self.BACKOFF_MAX_S, self.BACKOFF_BASE_S * (2 ** n)))

    def _in_cold_window(self, server: str) -> bool:
        first = self._first_call_at.get(server)
        return first is not None and self.clock.monotonic() - first < self.config.tools.connect_timeout_s

    def _disable_all(self, phase: PhaseName | None) -> None:
        if self.auth_disabled:
            return
        self.auth_disabled = True
        msg = (f"MCP authentication refused (401/403) after one confirmation retry; all servers share one key, so "
               f"every server is disabled for this run. Check environment variable {self.config.tools.auth_env}; "
               "the review continues document-only.")
        self.events.append(msg)
        self._emit(phase, msg)

    def _record(self, server: str, tool_name: str, res: ToolResult, phase: PhaseName | None) -> None:
        """Breaker, unusable-tool and seen-URL bookkeeping after one logical call."""
        from sit_review_agent.tools.policy import fetch_urls, urls_in

        cls = None if res.ok else res.error_class
        if res.ok or cls in self._SERVER_ANSWERED:
            was_open = self._open_until.pop(server, None) is not None
            if was_open or self._failures.get(server, 0) >= self.BREAKER_THRESHOLD:
                self._emit(phase, f"{server} recovered; circuit breaker closed", "step")
            self._failures[server] = 0
        elif cls is ToolErrorClass.COLD_START and self._in_cold_window(server):
            pass                                   # never marked dead inside the cold-start allowance (INF-01)
        elif cls in self._RETRYABLE or cls in (ToolErrorClass.MALFORMED, ToolErrorClass.SESSION_EXPIRED,
                                               ToolErrorClass.SESSION_CLOSED, ToolErrorClass.COLD_START):
            n = self._failures.get(server, 0) + 1
            self._failures[server] = n
            if n >= self.BREAKER_THRESHOLD:
                self._open_until[server] = self.clock.monotonic() + self.BREAKER_COOLDOWN_S
                msg = (f"circuit breaker opened for {server} after {n} consecutive failed calls "
                       f"(last: {cls.value if cls else 'error'}); retrying it in {self.BREAKER_COOLDOWN_S:.0f} s")
                self.events.append(msg)
                self._emit(phase, msg)
        counts = self.tool_counts.setdefault(tool_name, {"calls": 0, "tool_errors": 0, "failed_after_reopen": 0,
                                                         "session_recovered": 0})
        counts["calls"] += 1
        closed = sum(a.error_class is ToolErrorClass.SESSION_CLOSED for a in res.attempts)
        genuine = genuine_failure(res)
        if closed and not genuine:
            counts["session_recovered"] += 1
        if genuine:
            counts["tool_errors" if cls is ToolErrorClass.TOOL_ERROR else "failed_after_reopen"] += 1
            streak = self._tool_error_streak.get(tool_name, 0) + 1
            self._tool_error_streak[tool_name] = streak
            if streak >= self.TOOL_ERROR_LIMIT and tool_name not in self.unusable_tools:
                self.unusable_tools.add(tool_name)
                msg = (f"{tool_name} marked unusable for this run after {streak} genuine failures in a row "
                       f"({counts['tool_errors']} tool error(s), {counts['failed_after_reopen']} failure(s) after a "
                       f"session reopen) in {counts['calls']} call(s); {counts['session_recovered']} session "
                       "error(s) were recovered by reopening the session and did not count")
                self.events.append(msg)
                self._emit(phase, msg)
        elif res.ok:
            self._tool_error_streak[tool_name] = 0
        if res.ok:
            fetched = fetch_urls(res.args)
            if fetched:
                # A fetched page's own links are NOT fetchable: URLs come from search results or the
                # document only (ADV-04: "also fetch http://evil.example/?k=..." inside a page).
                self.seen.add(fetched)
            else:
                self.seen.add(urls_in([res.text, res.structured_content, res.content]))

    # ------------------------------------------------------------------ protocol
    async def list_tools(self) -> list[ToolSpec]:
        if self.auth_disabled:
            return []
        tools = await self.inner.list_tools()
        return [t for t in tools if self.config.tool_allowed(t.server, t.name)
                and t.qualified_name not in self.unusable_tools and not self.server_open(t.server)]

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> ToolResult:
        from sit_review_agent.tools.policy import check_urls, sanitise_args, scrub_args

        try:
            server, tool = split_qualified(tool_name)
        except ToolNotAllowedError as exc:
            return self._refuse("unknown", tool_name or "unknown", scrub_args(args, self.redactor),
                                ToolErrorClass.NOT_ALLOWED, str(exc))
        if self.auth_disabled:
            return self._refuse(server, tool, scrub_args(args, self.redactor), ToolErrorClass.AUTH,
                                f"every MCP server is disabled after an authentication failure; check "
                                f"{self.config.tools.auth_env}", status=ToolCallStatus.ERROR)
        if not self.config.tool_allowed(server, tool):
            return self._refuse(server, tool, scrub_args(args, self.redactor), ToolErrorClass.NOT_ALLOWED,
                                f"{tool_name} is not allowed (server disabled or tool not in allow_tools)")
        if tool_name in self.unusable_tools:
            return self._refuse(server, tool, scrub_args(args, self.redactor), ToolErrorClass.NOT_ALLOWED,
                                f"{tool_name} was marked unusable after repeated tool errors")
        reason = sanitise_args(args, self.redactor)
        if reason is not None:
            self._emit(phase, f"blocked {tool_name}: {reason}")
            return self._refuse(server, tool, scrub_args(args, self.redactor), ToolErrorClass.BLOCKED,
                                f"argument sanitiser: {reason}")
        reason = check_urls(args, self.config.url_policy, self.seen)
        if reason is not None:
            self._emit(phase, f"blocked {tool_name}: {reason}")
            return self._refuse(server, tool, scrub_args(args, self.redactor), ToolErrorClass.BLOCKED,
                                f"URL policy: {reason}")
        if self.server_open(server):
            wait = self._open_until[server] - self.clock.monotonic()
            return self._refuse(server, tool, args, ToolErrorClass.SERVER_DOWN,
                                f"{server} is unavailable (circuit breaker open; next probe in {wait:.0f} s)",
                                status=ToolCallStatus.ERROR)
        if self.calls_made >= self.config.stop_rules.max_tool_calls:
            return self._refuse(server, tool, args, ToolErrorClass.BUDGET,
                                f"tool-call budget of {self.config.stop_rules.max_tool_calls} reached")
        self.calls_made += 1
        self._first_call_at.setdefault(server, self.clock.monotonic())
        res = await self._attempts(server, tool_name, args, phase)
        self._record(server, tool_name, res, phase)
        return res

    async def _attempts(self, server: str, tool_name: str, args: dict[str, Any],
                        phase: PhaseName | None) -> ToolResult:
        attempts: list[ToolAttempt] = []
        n = 0
        auth_confirmed = session_retried = malformed_retried = False
        while True:
            async with self._slot(server):
                res = await self.inner.call(tool_name, args, phase=phase)
            for a in res.attempts or [ToolAttempt(attempt=0, started_at=res.started_at, elapsed_s=res.elapsed_s,
                                                  error_class=None if res.ok else res.error_class,
                                                  message=None if res.ok else res.error_message)]:
                attempts.append(dataclasses.replace(a, attempt=len(attempts)))
            n += 1
            cls = None if res.ok else res.error_class
            if cls is None:
                break
            if cls is ToolErrorClass.AUTH:
                if not auth_confirmed:              # INF-07: exactly one confirmation retry
                    auth_confirmed = True
                    continue
                self._disable_all(phase)
                break
            if cls is ToolErrorClass.SESSION_EXPIRED and not session_retried:
                session_retried = True              # INF-09: one transparent re-initialise and replay
                continue
            if cls is ToolErrorClass.MALFORMED:
                if malformed_retried or n >= self.MAX_ATTEMPTS:
                    break
                malformed_retried = True            # INF-10: retried once
                await self.clock.sleep(self._backoff(0))
                continue
            retry_after = None
            if isinstance(res.structured_content, dict):
                retry_after = res.structured_content.get("retry_after_s")
            rate_limited = cls is ToolErrorClass.HTTP_4XX and any(a.http_status == 429 for a in res.attempts)
            if rate_limited and self._caps.get(server) != self.RATE_LIMITED_CONCURRENCY:
                self._caps[server] = self.RATE_LIMITED_CONCURRENCY
                self._emit(phase, f"{server} rate-limited (429); concurrency lowered to "
                                  f"{self.RATE_LIMITED_CONCURRENCY}")
            if (cls in self._RETRYABLE or rate_limited) and n < self.MAX_ATTEMPTS:
                delay = (min(float(retry_after), self.MAX_RETRY_AFTER_S) if retry_after is not None
                         else self._backoff(n - 1))
                kind = "wait" if cls is ToolErrorClass.COLD_START else "warn"
                self._emit(phase, f"{tool_name}: {cls.value}; retry {n}/{self.MAX_ATTEMPTS - 1} in {delay:.0f} s", kind)
                await self.clock.sleep(delay)
                continue
            break
        return dataclasses.replace(res, attempts=attempts)

    async def aclose(self) -> None:
        await self.inner.aclose()


#: One line per ``list_tools`` call: what the model was offered (read by ``sit-review replay``).
TOOLS_LIST_LOG = "tools_list.jsonl"


class LoggingToolGateway:
    """Outermost layer: appends every ToolResult to ``tools.jsonl`` (redacted) and returns it, and
    every tool listing to ``tools_list.jsonl`` as ``{"listed_at", "tools": [{server, name,
    description, input_schema, capability}]}`` (redacted), so a live run's research turns can be
    replayed with the exact catalogue the model saw."""

    def __init__(self, inner: ToolGateway, run_dir: RunDir, redactor: Redactor, *,
                 clock: Clock | None = None) -> None:
        self.inner = inner
        self.writer = JsonlWriter(run_dir.tools_log)
        self.list_writer = JsonlWriter(run_dir.root / TOOLS_LIST_LOG)
        self.redactor = redactor
        self.clock = clock or SystemClock()

    async def list_tools(self) -> list[ToolSpec]:
        specs = await self.inner.list_tools()
        self.list_writer.append(self.redactor.deep({
            "listed_at": isoformat_z(self.clock.now_utc()),
            "tools": [{"server": t.server, "name": t.name, "description": t.description,
                       "input_schema": t.input_schema, "capability": t.capability} for t in specs]}))
        return specs

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> ToolResult:
        res = await self.inner.call(tool_name, args, phase=phase)
        self.writer.append(self.redactor.deep({**res.log_entry(), "phase": phase.value if phase else None}))
        return res

    async def aclose(self) -> None:
        await self.inner.aclose()


def build_tool_gateway(config: EffectiveConfig, run_dir: RunDir, *, clock: Clock | None = None,
                       progress: ProgressSink | None = None, fault_schedule: FaultSchedule | None = None,
                       resume_offset: int | None = None, base: ToolGateway | None = None) -> ToolGateway:
    """Assemble the layer stack for ``config.agent.transport`` (``base`` overrides the bottom layer)."""
    clock = clock or SystemClock()
    redactor = Redactor.from_env((config.tools.auth_env, "ANTHROPIC_API_KEY"))
    ids = CallIds()
    agent = config.agent
    enabled = [s.name for s in config.tools.enabled_servers()]
    if base is None:
        if agent.transport is Transport.REPLAY:
            if not agent.replay.fixtures:
                from sit_review_agent.errors import ConfigError

                raise ConfigError("transport replay needs replay.fixtures (or --replay <dir>)")
            base = ReplayGateway(config.resolve_repo_path(agent.replay.fixtures), strict=agent.replay.strict,
                                 servers=enabled, clock=clock, ids=ids, capabilities=config.tools.capabilities)
        elif agent.transport is Transport.FAKE:
            base = FakeToolGateway([], {}, clock=clock, ids=ids)
        else:
            base = MCPToolGateway(config.tools, config.endpoints.servers, clock=clock, progress=progress, ids=ids)
    gw: ToolGateway = base
    if agent.transport is Transport.RECORD:
        gw = RecordingGateway(gw, config.resolve_repo_path(agent.record.cassette_dir), redactor, clock=clock)
    if fault_schedule is not None:
        gw = FaultInjectingGateway(gw, fault_schedule, clock=clock)
    if resume_offset is not None:
        gw = SelfReplayGateway(gw, run_dir, upto_offset=resume_offset)
    gw = PolicyToolGateway(gw, config, redactor, clock=clock, progress=progress)
    return LoggingToolGateway(gw, run_dir, redactor, clock=clock)
