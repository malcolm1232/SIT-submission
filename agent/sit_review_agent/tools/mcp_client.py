"""Live MCP plumbing behind :class:`~sit_review_agent.tools.gateway.MCPToolGateway` (workstream B).

The client pattern is the one verified by ``scripts/probe_mcp_servers.py`` (mcp 2.x)::

    async with httpx2.AsyncClient(headers={auth_header: key}, timeout=httpx2.Timeout(t)) as http:
        async with streamable_http_client(url, http_client=http) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=t, client_info=...) as session:
                await session.initialize(); await session.list_tools(); await session.call_tool(...)

What mcp 2.2.0 does with HTTP errors (read from ``mcp/client/streamable_http.py``
``_handle_post_request`` and confirmed offline over ``httpx2.ASGITransport``): a 404 on a request
that carries an ``Mcp-Session-Id`` becomes ``MCPError(-32600, "Session terminated")``; every other
status >= 400 becomes ``MCPError(-32603, "Server returned an error response")`` and **the status
code is lost**. The session factory therefore installs an httpx2 ``response`` event hook that
records each error status (and ``Retry-After``) so :func:`classify_exception` can tell a 401 from a
503. Transport exceptions arrive as (possibly nested) ``ExceptionGroup`` leaves, as in the probe.

Sessions are owned by one long-lived task per server (:class:`ServerConnection`), because anyio
cancel scopes inside ``streamable_http_client`` must be entered and exited by the same task while
calls come from many tasks (warm-up, research rounds).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from sit_review_agent.tools.gateway import ToolErrorClass

#: Client identity sent in ``initialize`` (no version: nothing volatile).
CLIENT_INFO = {"name": "sit-review-agent", "version": "1.0"}
#: HTTP statuses that look like a scaled-to-zero container waking (probe ``COLD_START_STATUSES``).
COLD_START_STATUSES = frozenset({502, 503, 504})
#: Pause before the cold-start retry (probe ``COLD_RETRY_DELAY_S``).
COLD_RETRY_DELAY_S = 15.0
#: JSON-RPC codes used by mcp 2.2.0's streamable HTTP client for synthesised errors.
INVALID_REQUEST = -32600
INTERNAL_ERROR = -32603
METHOD_NOT_FOUND = -32601
PARSE_ERROR = -32700
INVALID_PARAMS = -32602
#: mcp 2.x ``CONNECTION_CLOSED``: the session's stream ended (the server closed it, or the transport
#: died). Every later request on that session fails with it at once until it is reopened.
CONNECTION_CLOSED = -32000

#: ``on_response(status, retry_after_s)`` callback the session factory calls for every HTTP error.
ResponseHook = Callable[[int, float | None], None]


class SessionLike(Protocol):
    """The subset of ``mcp.ClientSession`` the gateway uses (tests provide fakes)."""

    async def initialize(self) -> Any: ...

    async def list_tools(self, *, params: Any = None) -> Any: ...

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None,
                        read_timeout_seconds: float | None = None) -> Any: ...


#: ``factory(server, url, headers, timeout_s, on_response)`` -> async context manager yielding a
#: session that is **not yet initialised**.
SessionFactory = Callable[[str, str, dict[str, str], float, ResponseHook],
                          contextlib.AbstractAsyncContextManager[SessionLike]]


def make_http_session_factory(http_transport: Any | None = None) -> SessionFactory:
    """The live factory: httpx2 client (auth headers, timeout, error-status hook) + mcp 2.x
    ``streamable_http_client`` + ``ClientSession``. ``http_transport`` (an ``httpx2`` transport such
    as ``ASGITransport``) lets tests drive the real MCP client against an in-process server with
    no sockets; ``None`` means the network."""

    @contextlib.asynccontextmanager
    async def factory(server: str, url: str, headers: dict[str, str], timeout_s: float,
                      on_response: ResponseHook) -> AsyncIterator[SessionLike]:
        import httpx2
        from mcp import ClientSession, types
        from mcp.client.streamable_http import streamable_http_client

        async def hook(resp: Any) -> None:
            if resp.status_code >= 400:
                on_response(resp.status_code, _retry_after(resp.headers.get("retry-after")))

        kwargs: dict[str, Any] = {"headers": headers, "timeout": httpx2.Timeout(timeout_s),
                                  "event_hooks": {"response": [hook]}}
        if http_transport is not None:
            kwargs["transport"] = http_transport
        async with httpx2.AsyncClient(**kwargs) as http:
            async with streamable_http_client(url, http_client=http) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timeout_s,
                                         client_info=types.Implementation(**CLIENT_INFO)) as session:
                    yield session

    return factory


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def auth_headers(header: str, key: str) -> dict[str, str]:
    """``Authorization`` gets ``Bearer <key>``; any other header carries the bare key (probe
    ``auth_material``)."""
    return {header: f"Bearer {key}" if header.lower() == "authorization" else key}


# ------------------------------------------------------------------------------ classification


def leaf_exceptions(exc: BaseException) -> list[BaseException]:
    """Flatten nested ``ExceptionGroup``s raised by anyio task groups (probe helper)."""
    if isinstance(exc, BaseExceptionGroup):
        out: list[BaseException] = []
        for sub in exc.exceptions:
            out.extend(leaf_exceptions(sub))
        return out
    return [exc]


@dataclass(frozen=True)
class Failure:
    """A classified failure: what the gateway puts on the ToolResult."""

    error_class: ToolErrorClass
    message: str
    http_status: int | None = None
    retry_after_s: float | None = None


class StatusLog:
    """Recent HTTP error statuses of one server (filled by the factory's response hook)."""

    def __init__(self) -> None:
        self._items: deque[tuple[int, float | None]] = deque(maxlen=16)

    def record(self, status: int, retry_after_s: float | None) -> None:
        self._items.append((status, retry_after_s))

    def last(self) -> tuple[int | None, float | None]:
        return self._items[-1] if self._items else (None, None)

    def clear(self) -> None:
        self._items.clear()


def classify_status(status: int, *, first_contact: bool, retry_after_s: float | None = None) -> Failure:
    """Error class of an HTTP status (cold-start statuses count as cold start only on first contact)."""
    if status in (401, 403):
        return Failure(ToolErrorClass.AUTH, f"HTTP {status} (authentication refused)", status)
    if status in COLD_START_STATUSES and first_contact:
        return Failure(ToolErrorClass.COLD_START, f"HTTP {status} while the server may be waking", status)
    if status >= 500:
        return Failure(ToolErrorClass.HTTP_5XX, f"HTTP {status}", status)
    if status == 429:
        return Failure(ToolErrorClass.HTTP_4XX, "HTTP 429 (rate limited)", status, retry_after_s)
    return Failure(ToolErrorClass.HTTP_4XX, f"HTTP {status}", status)


def classify_exception(exc: BaseException, *, status_hint: tuple[int | None, float | None] = (None, None),
                       first_contact: bool = False) -> Failure:
    """Map anything the MCP client can raise onto a :class:`ToolErrorClass` (never raises)."""
    try:
        import httpx2
        from mcp import MCPError
    except ImportError:  # pragma: no cover - environment problem
        httpx2 = None  # type: ignore[assignment]
        MCPError = ()  # type: ignore[assignment,misc]  # noqa: N806
    leaves = leaf_exceptions(exc)
    leaf = next((e for e in leaves if not isinstance(e, asyncio.CancelledError)), leaves[0])
    status, retry_after = status_hint
    name = type(leaf).__name__
    if MCPError and isinstance(leaf, MCPError):
        code, msg = leaf.error.code, leaf.error.message
        if code == INVALID_REQUEST and "session terminated" in msg.lower():
            return Failure(ToolErrorClass.SESSION_EXPIRED, "session terminated (HTTP 404)", 404)
        if code == CONNECTION_CLOSED:
            # Not a tool error: the session is gone (sit_sample_tools_1 lost five web searches to
            # this after a 130 s idle session). The gateway reopens the session and retries once.
            return Failure(ToolErrorClass.SESSION_CLOSED, f"session closed (MCP error {code}: {msg[:200]})")
        if code == INTERNAL_ERROR and "error response" in msg.lower():
            if status is not None:
                return classify_status(status, first_contact=first_contact, retry_after_s=retry_after)
            return Failure(ToolErrorClass.HTTP_5XX, "server returned an error response (status unknown)")
        if code == PARSE_ERROR:
            return Failure(ToolErrorClass.MALFORMED, f"unparseable response: {msg[:200]}")
        if code == METHOD_NOT_FOUND and status == 404:
            return Failure(ToolErrorClass.HTTP_4XX, "HTTP 404 (endpoint not found)", 404)
        return Failure(ToolErrorClass.TOOL_ERROR, f"MCP error {code}: {msg[:300]}")
    if not first_contact and _is_closed_session(leaf):
        # On first contact the same exceptions keep their cold-start / connection meaning below.
        return Failure(ToolErrorClass.SESSION_CLOSED, f"session closed ({_closed_name(leaf)})")
    if isinstance(leaf, TimeoutError | asyncio.TimeoutError) or (
            httpx2 is not None and isinstance(leaf, httpx2.TimeoutException)):
        cls = ToolErrorClass.COLD_START if first_contact else ToolErrorClass.TIMEOUT
        return Failure(cls, f"timed out ({name})")
    if httpx2 is not None and isinstance(leaf, httpx2.HTTPStatusError):
        st = leaf.response.status_code
        return classify_status(st, first_contact=first_contact,
                               retry_after_s=_retry_after(leaf.response.headers.get("retry-after")))
    if httpx2 is not None and isinstance(leaf, httpx2.RemoteProtocolError | httpx2.ReadError):
        cls = ToolErrorClass.COLD_START if first_contact else ToolErrorClass.CONNECTION
        return Failure(cls, f"connection dropped ({name})")
    if (httpx2 is not None and isinstance(leaf, httpx2.TransportError)) or isinstance(leaf, ConnectionError | OSError):
        return Failure(ToolErrorClass.CONNECTION, f"connection failed ({name})")
    if isinstance(leaf, json.JSONDecodeError | ValueError):
        return Failure(ToolErrorClass.MALFORMED, f"malformed response ({name})")
    return Failure(ToolErrorClass.UNKNOWN, f"{name}: {str(leaf)[:200]}")


def _closed_types() -> tuple[type[BaseException], ...]:
    """Exceptions that mean the session's stream is gone: anyio's closed, broken and ended streams
    and a connection reset or broken pipe at the socket."""
    out: list[type[BaseException]] = [ConnectionResetError, BrokenPipeError, EOFError]
    try:
        import anyio

        out += [anyio.ClosedResourceError, anyio.BrokenResourceError, anyio.EndOfStream]
    except ImportError:  # pragma: no cover - environment problem
        pass
    return tuple(out)


def _chain(exc: BaseException) -> list[BaseException]:
    out: list[BaseException] = []
    cur: BaseException | None = exc
    while cur is not None and len(out) < 8 and cur not in out:
        out.append(cur)
        cur = cur.__cause__ or cur.__context__
    return out


def _is_closed_session(leaf: BaseException) -> bool:
    """True when ``leaf`` (or what it wraps, as ``httpx2.ReadError`` wraps a reset) says the stream is
    closed, ended or reset."""
    types_ = _closed_types()
    return any(isinstance(e, types_) for e in _chain(leaf))


def _closed_name(leaf: BaseException) -> str:
    types_ = _closed_types()
    hit = next((e for e in _chain(leaf) if isinstance(e, types_)), leaf)
    return type(hit).__name__


# ------------------------------------------------------------------------------ connection owner


class ServerConnection:
    """One live session, owned by a dedicated task (enter and exit happen in that task)."""

    def __init__(self) -> None:
        self.session: SessionLike | None = None
        self.init_result: Any = None
        self.error: BaseException | None = None
        self._ready = asyncio.Event()
        self._closing = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def alive(self) -> bool:
        return self.session is not None and self._task is not None and not self._task.done()

    async def open(self, factory: SessionFactory, server: str, url: str, headers: dict[str, str],
                   timeout_s: float, on_response: ResponseHook) -> None:
        """Start the owner task and wait (at most ``timeout_s`` plus a margin) for ``initialize``.
        Raises the classified cause (``TimeoutError`` on a hang)."""

        async def owner() -> None:
            try:
                async with factory(server, url, headers, timeout_s, on_response) as session:
                    self.init_result = await session.initialize()
                    self.session = session
                    self._ready.set()
                    await self._closing.wait()
            except asyncio.CancelledError:
                raise
            except BaseException as exc:  # noqa: BLE001 - ExceptionGroups from anyio included
                if self.error is None:
                    self.error = exc
            finally:
                self.session = None          # the owner only exits once the session is unusable
                self._ready.set()

        self._task = asyncio.create_task(owner(), name=f"mcp-session-{server}")
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout_s + 5.0)
        except TimeoutError:
            await self.close()
            raise TimeoutError(f"initialize did not complete within {timeout_s:.0f}s") from None
        except BaseException:
            # Cancelled while waiting (the run ended or the warm-up was cancelled): the owner task
            # is not registered with the gateway yet, so nobody else would ever stop it. There is
            # no session to close gracefully, so it is cancelled at once.
            self._closing.set()
            task, self._task = self._task, None
            self.session = None
            if task is not None:
                task.cancel()
                with contextlib.suppress(BaseException):
                    await task
            raise
        if self.session is None:
            err = self.error or ConnectionError("session closed during initialize")
            await self.close()
            raise err

    async def close(self) -> None:
        self._closing.set()
        task, self._task = self._task, None
        self.session = None
        if task is None:
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=5.0)
        except (TimeoutError, asyncio.CancelledError, Exception):  # noqa: BLE001
            task.cancel()
            with contextlib.suppress(BaseException):
                await task


# ------------------------------------------------------------------------------ layer helpers


def find_layer(gw: Any, cls: type) -> Any | None:
    """Walk a gateway stack through ``.inner`` and return the first layer of type ``cls``."""
    seen = 0
    while gw is not None and seen < 16:
        if isinstance(gw, cls):
            return gw
        gw = getattr(gw, "inner", None)
        seen += 1
    return None


def find_attr(gw: Any, name: str) -> Any | None:
    """First ``name`` attribute found walking the stack through ``.inner``."""
    seen = 0
    while gw is not None and seen < 16:
        if hasattr(gw, name):
            return getattr(gw, name)
        gw = getattr(gw, "inner", None)
        seen += 1
    return None


def start_warm_up(gw: Any) -> asyncio.Task[Any] | None:
    """Start the background warm-up of the live MCP layer of ``gw`` (if any) and return the task.

    For ``orchestrator.run_review`` (workstream C): call this right after building the tool stack so
    cold starts overlap ``ingest`` and ``understand`` (robustness §10 item 2, runbook §7 drill 1).
    """
    from sit_review_agent.tools.gateway import MCPToolGateway

    base = find_layer(gw, MCPToolGateway)
    if base is None:
        return None
    return asyncio.create_task(base.warm_up(), name="mcp-warm-up")
