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

import json
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

    Behaviour: ``connect_timeout_s`` (150 s) for the first ``initialize`` of a cold server; one
    retry on a cold-start-like failure (``ExceptionGroup`` leaf ``httpx2.ReadTimeout``,
    ``RemoteProtocolError``, ``ReadError``, HTTP 502/503/504); on HTTP 404 for a stale session,
    re-``initialize`` once and repeat the call; a confirmed 401/403 marks every server DOWN
    (shared key, INF-07). The key is read from ``tools.auth_env`` and never logged.
    """

    def __init__(self, tools: ToolsConfig, endpoints: Mapping[str, str], *, clock: Clock | None = None,
                 progress: ProgressSink | None = None, ids: CallIds | None = None,
                 api_key: str | None = None) -> None:
        self.tools = tools
        self.endpoints = dict(endpoints)
        self.clock = clock or SystemClock()
        self.progress = progress
        self.ids = ids or CallIds()
        self._api_key = api_key
        self.health: dict[str, ServerHealth] = {
            s.name: (ServerHealth.OK if s.enabled else ServerHealth.DISABLED) for s in tools.servers}
        self.protocol_versions: dict[str, str] = {}

    async def warm_up(self) -> dict[str, ServerHealth]:
        """Initialize + ``tools/list`` on every enabled server in parallel (background, at t=0,
        overlapping ingest/understand; runbook §7 drill 1). Emits a progress line per server."""
        raise NotImplementedError("phase 2: MCPToolGateway.warm_up (workstream B)")

    async def list_tools(self) -> list[ToolSpec]:
        raise NotImplementedError("phase 2: MCPToolGateway.list_tools (workstream B)")

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> ToolResult:
        raise NotImplementedError("phase 2: MCPToolGateway.call (workstream B)")

    async def aclose(self) -> None:
        raise NotImplementedError("phase 2: MCPToolGateway.aclose (workstream B)")


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

    def __init__(self, inner: ToolGateway, schedule: FaultSchedule, *, clock: Clock | None = None) -> None:
        self.inner = inner
        self.schedule = schedule
        self.clock = clock or SystemClock()

    async def list_tools(self) -> list[ToolSpec]:
        raise NotImplementedError("phase 2: FaultInjectingGateway.list_tools (schema_drift; workstream B)")

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> ToolResult:
        raise NotImplementedError("phase 2: FaultInjectingGateway.call (workstream B)")

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

    async def list_tools(self) -> list[ToolSpec]:
        return await self.inner.list_tools()

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> ToolResult:
        raise NotImplementedError("phase 3: SelfReplayGateway.call (workstream C)")

    async def aclose(self) -> None:
        await self.inner.aclose()


class PolicyToolGateway:
    """Allowlist (``tools.yaml allow_tools``), URL policy (``url_policy.yaml``), argument sanitiser
    (secrets and canaries never leave the process, ADV-05), per-server breaker (``ServerHealth``),
    retry with jitter for transient errors, and the ``max_tool_calls`` budget. A refused call is
    returned with status ``blocked``; a budget hit with ``error_class=budget``."""

    def __init__(self, inner: ToolGateway, config: EffectiveConfig, redactor: Redactor, *,
                 clock: Clock | None = None, progress: ProgressSink | None = None) -> None:
        self.inner = inner
        self.config = config
        self.redactor = redactor
        self.clock = clock or SystemClock()
        self.progress = progress
        self.calls_made = 0

    async def list_tools(self) -> list[ToolSpec]:
        raise NotImplementedError("phase 2: PolicyToolGateway.list_tools (workstream B)")

    async def call(self, tool_name: str, args: dict[str, Any], *, phase: PhaseName | None = None) -> ToolResult:
        raise NotImplementedError("phase 2: PolicyToolGateway.call (workstream B)")

    async def aclose(self) -> None:
        await self.inner.aclose()


class LoggingToolGateway:
    """Outermost layer: appends every ToolResult to ``tools.jsonl`` (redacted) and returns it."""

    def __init__(self, inner: ToolGateway, run_dir: RunDir, redactor: Redactor) -> None:
        self.inner = inner
        self.writer = JsonlWriter(run_dir.tools_log)
        self.redactor = redactor

    async def list_tools(self) -> list[ToolSpec]:
        return await self.inner.list_tools()

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
    return LoggingToolGateway(gw, run_dir, redactor)
