#!/usr/bin/env python3
# Install: python3 -m venv .venv && . .venv/bin/activate && pip install "mcp>=2,<3" httpx
"""Probe the four SIT lab MCP servers (streamable HTTP, Azure Container Apps).

Answers, per server:
  * which HTTP header (or query parameter) carries the shared API key,
  * the negotiated MCP protocolVersion and serverInfo,
  * the tool list (name, description, input schema),
  * cold-start vs warm initialize latency,
  * one harmless sample call (internet-search) / the rejection text (document-intelligence).

The key is read from SIT_MCP_API_KEY and is redacted from every byte this script writes or prints.

Usage:
  export SIT_MCP_API_KEY=...            # value from the lab brief, never commit it
  python3 probe_mcp_servers.py          # writes ./mcp_probe_results.json, exits 0 even on partial failure
  python3 probe_mcp_servers.py --only mcp-internet-search
  python3 probe_mcp_servers.py --self-test   # offline: in-process MCP echo server on localhost
"""

from __future__ import annotations

import sys

if sys.version_info < (3, 11):
    sys.exit("probe_mcp_servers.py needs Python 3.11+ (ExceptionGroup). On macOS: brew install python@3.12")

import argparse
import asyncio
import importlib.metadata
import json
import logging
import os
import socket
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit, urlunsplit

INSTALL_HINT = 'python3 -m venv .venv && . .venv/bin/activate && pip install "mcp>=2,<3" httpx'

try:
    import anyio
    import httpx
    import httpx2  # transport library used by mcp 2.x (installed as an mcp dependency)
    from mcp import ClientSession, MCPError, types
    from mcp.client.streamable_http import streamable_http_client  # mcp 2.x name (1.x: streamablehttp_client)
except ImportError as exc:  # pragma: no cover - environment problem
    sys.exit(f"Missing/incompatible dependency ({exc}). Install with:\n  {INSTALL_HINT}")

MCP_VERSION = importlib.metadata.version("mcp")
if not MCP_VERSION.startswith("2."):
    sys.exit(f"mcp {MCP_VERSION} found, this probe targets mcp 2.x. Install with:\n  {INSTALL_HINT}")

try:
    from mcp_types.version import LATEST_HANDSHAKE_VERSION
except ImportError:  # pragma: no cover
    LATEST_HANDSHAKE_VERSION = "2025-11-25"

# --------------------------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------------------------

ENV_KEY = "SIT_MCP_API_KEY"
_HOST_SUFFIX = "delightfulsky-d55e63aa.southeastasia.azurecontainerapps.io"

SERVERS: dict[str, dict[str, Any]] = {
    "mcp-internet-search": {"url": f"https://mcp-internet-search.{_HOST_SUFFIX}/mcp", "sample": "search"},
    "mcp-browser-automation-pw": {"url": f"https://mcp-browser-automation-pw.{_HOST_SUFFIX}/mcp", "sample": None},
    "mcp-research-information": {"url": f"https://mcp-research-information.{_HOST_SUFFIX}/mcp", "sample": None},
    "mcp-document-intelligence": {"url": f"https://mcp-document-intelligence.{_HOST_SUFFIX}/mcp", "sample": "docintel"},
}

# Order matters: the first variant that yields a successful MCP initialize wins.
AUTH_VARIANTS: list[tuple[str, str, str | None]] = [
    # (label, kind, header name)
    ("Authorization: Bearer", "header", "Authorization"),
    ("X-API-Key", "header", "X-API-Key"),
    ("x-api-key", "header", "x-api-key"),
    ("api-key", "header", "api-key"),
    ("Ocp-Apim-Subscription-Key", "header", "Ocp-Apim-Subscription-Key"),
    ("?api_key= query parameter", "query", None),
]

FIRST_TIMEOUT_S = 180.0  # first request per server may have to wake a scaled-to-zero container
LATER_TIMEOUT_S = 30.0
COLD_RETRY_DELAY_S = 15.0
COLD_START_STATUSES = {502, 503, 504}
SEARCH_QUERY = "model context protocol"
DOCINTEL_TEXT = "Hello from the SIT MCP probe. This is a short plain-text test document."
CLIENT_INFO = {"name": "sit-mcp-probe", "version": "1.0"}
REDACTED = "***REDACTED***"

# --------------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------------


class Redactor:
    def __init__(self, secret: str):
        self.secret = secret
        # also catch URL-encoded forms (the ?api_key= variant puts the key in the URL)
        self.forms = sorted({secret, quote(secret, safe=""), quote_plus(secret)} - {""}, key=len, reverse=True)

    def s(self, text: Any) -> Any:
        if isinstance(text, str):
            for form in self.forms:
                text = text.replace(form, REDACTED)
        return text

    def deep(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {self.s(k): self.deep(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self.deep(v) for v in obj]
        return self.s(obj)


def leaf_exceptions(exc: BaseException) -> list[BaseException]:
    """Flatten (possibly nested) ExceptionGroups raised by anyio task groups."""
    if isinstance(exc, BaseExceptionGroup):
        out: list[BaseException] = []
        for sub in exc.exceptions:
            out.extend(leaf_exceptions(sub))
        return out
    return [exc]


def describe_exc(exc: BaseException) -> str:
    parts = []
    for leaf in leaf_exceptions(exc):
        name = type(leaf).__name__
        if isinstance(leaf, MCPError):
            parts.append(f"{name}(code={leaf.error.code}): {leaf.error.message}")
        elif isinstance(leaf, (httpx.HTTPStatusError, httpx2.HTTPStatusError)):
            parts.append(f"{name}: HTTP {leaf.response.status_code} {leaf}")
        else:
            parts.append(f"{name}: {leaf}" if str(leaf) else name)
    return " | ".join(parts)


def is_cold_start_like(exc: BaseException | None, status: int | None) -> bool:
    if status in COLD_START_STATUSES:
        return True
    if exc is None:
        return False
    cold_types = (
        httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ReadError,
        httpx2.TimeoutException, httpx2.RemoteProtocolError, httpx2.ReadError,
        TimeoutError,
    )
    return any(isinstance(e, cold_types) for e in leaf_exceptions(exc))


def auth_material(url: str, key: str, variant: tuple[str, str, str | None]) -> tuple[str, dict[str, str]]:
    _, kind, header = variant
    if kind == "query":
        parts = urlsplit(url)
        query = parse_qsl(parts.query) + [("api_key", key)]
        return urlunsplit(parts._replace(query=urlencode(query))), {}
    assert header is not None
    value = f"Bearer {key}" if header == "Authorization" else key
    return url, {header: value}


def parse_sse_messages(text: str) -> list[Any]:
    messages, data_lines = [], []
    for line in text.splitlines() + [""]:
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
        elif line == "" and data_lines:
            try:
                messages.append(json.loads("\n".join(data_lines)))
            except json.JSONDecodeError:
                pass
            data_lines = []
    return messages


def quiet_library_logs() -> None:
    for name in ("httpx", "httpx2", "mcp", "uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)


def now() -> float:
    return time.perf_counter()


def log(server: str, msg: str, redact: Redactor) -> None:
    print(redact.s(f"[{time.strftime('%H:%M:%S')}] {server:<27} {msg}"), flush=True)


# --------------------------------------------------------------------------------------------
# Raw JSON-RPC over HTTP (independent of the SDK: gives exact HTTP status and survives SDK quirks)
# --------------------------------------------------------------------------------------------

BASE_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@dataclass
class RawResult:
    status: int | None = None
    headers: dict[str, str] | None = None
    message: Any = None  # JSON-RPC response matching our id
    body_snippet: str | None = None
    elapsed_s: float | None = None
    error: BaseException | None = None


async def raw_rpc(client: httpx.AsyncClient, url: str, headers: dict[str, str], payload: dict[str, Any]) -> RawResult:
    res = RawResult()
    t0 = now()
    try:
        async with client.stream("POST", url, json=payload, headers={**BASE_HEADERS, **headers}) as resp:
            res.status = resp.status_code
            res.headers = {k: v for k, v in resp.headers.items() if k.lower() != "set-cookie"}
            ctype = resp.headers.get("content-type", "")
            if "id" not in payload:  # notification: nothing to read
                await resp.aread()
            elif "text/event-stream" in ctype and resp.status_code < 400:
                buf = ""
                async for chunk in resp.aiter_text():
                    buf += chunk
                    for msg in parse_sse_messages(buf):
                        if isinstance(msg, dict) and msg.get("id") == payload["id"]:
                            res.message = msg
                    if res.message is not None:
                        break
                res.body_snippet = buf[:2000]
            else:
                body = (await resp.aread()).decode("utf-8", "replace")
                res.body_snippet = body[:2000]
                try:
                    res.message = json.loads(body)
                except json.JSONDecodeError:
                    pass
    except Exception as exc:  # noqa: BLE001 - record everything
        res.error = exc
    res.elapsed_s = round(now() - t0, 3)
    return res


def init_payload(req_id: int = 1) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "method": "initialize",
        "params": {"protocolVersion": LATEST_HANDSHAKE_VERSION, "capabilities": {}, "clientInfo": CLIENT_INFO},
    }


async def raw_initialize(url: str, headers: dict[str, str], timeout: float) -> RawResult:
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:
        res = await raw_rpc(client, url, headers, init_payload())
        sid = (res.headers or {}).get("mcp-session-id")
        if sid:  # be polite: close the session we just opened
            try:
                await client.delete(url, headers={**headers, "mcp-session-id": sid}, timeout=10)
            except Exception:  # noqa: BLE001
                pass
        return res


async def raw_list_tools(url: str, headers: dict[str, str], timeout: float) -> list[dict[str, Any]]:
    """Fallback when the SDK path fails: initialize -> initialized -> tools/list (paginated)."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout), follow_redirects=True) as client:
        init = await raw_rpc(client, url, headers, init_payload())
        if init.error or not isinstance(init.message, dict) or "result" not in init.message:
            raise RuntimeError(f"raw initialize failed: status={init.status} body={init.body_snippet!r}")
        h = dict(headers)
        if sid := (init.headers or {}).get("mcp-session-id"):
            h["mcp-session-id"] = sid
        h["mcp-protocol-version"] = init.message["result"].get("protocolVersion", LATEST_HANDSHAKE_VERSION)
        await raw_rpc(client, url, h, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools, cursor, req_id = [], None, 2
        while True:
            payload = {"jsonrpc": "2.0", "id": req_id, "method": "tools/list", "params": {"cursor": cursor} if cursor else {}}
            r = await raw_rpc(client, url, h, payload)
            if r.error:
                raise r.error
            if not isinstance(r.message, dict) or "result" not in r.message:
                raise RuntimeError(f"raw tools/list failed: status={r.status} body={r.body_snippet!r}")
            for t in r.message["result"].get("tools", []):
                tools.append({"name": t.get("name"), "title": t.get("title"), "description": t.get("description"),
                              "input_schema": t.get("inputSchema"), "output_schema": t.get("outputSchema"),
                              "annotations": t.get("annotations")})
            cursor = r.message["result"].get("nextCursor")
            req_id += 1
            if not cursor:
                return tools


# --------------------------------------------------------------------------------------------
# SDK session (mcp 2.x streamable HTTP client)
# --------------------------------------------------------------------------------------------


async def with_sdk_session(url: str, headers: dict[str, str], timeout: float,
                           work: Callable[[ClientSession, types.InitializeResult, float], Awaitable[Any]]) -> Any:
    hard_limit = timeout * 3 + 30  # guard against any hang inside the transport
    with anyio.fail_after(hard_limit):
        async with httpx2.AsyncClient(headers=headers, timeout=httpx2.Timeout(timeout)) as http_client:
            async with streamable_http_client(url, http_client=http_client) as (read, write):
                async with ClientSession(read, write, read_timeout_seconds=timeout,
                                         client_info=types.Implementation(**CLIENT_INFO)) as session:
                    t0 = now()
                    init = await session.initialize()
                    return await work(session, init, round(now() - t0, 3))


def tool_record(tool: types.Tool) -> dict[str, Any]:
    d = tool.model_dump(mode="json", by_alias=True, exclude_none=True)
    return {"name": d.get("name"), "title": d.get("title"), "description": d.get("description"),
            "input_schema": d.get("inputSchema"), "output_schema": d.get("outputSchema"),
            "annotations": d.get("annotations")}


def pick_sample(kind: str, tools: list[dict[str, Any]]) -> tuple[str, dict[str, Any]] | None:
    def props(t: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        schema = t.get("input_schema") or {}
        return schema.get("properties") or {}, list(schema.get("required") or [])

    def fill(t: dict[str, Any], text: str, preferred: tuple[str, ...]) -> dict[str, Any]:
        p, required = props(t)
        strings = [k for k, v in p.items() if (v or {}).get("type") in ("string", None)]
        main = next((k for k in preferred if k in p), None) or next((k for k in required if k in strings), None) \
            or (strings[0] if strings else None)
        args: dict[str, Any] = {main: text} if main else {}
        for k in required:
            if k in args:
                continue
            typ = (p.get(k) or {}).get("type")
            args[k] = {"integer": 1, "number": 1, "boolean": False, "array": [], "object": {}}.get(typ, text)
        for k, v in p.items():  # keep searches small
            if k not in args and (v or {}).get("type") == "integer" and any(s in k.lower() for s in ("max", "limit", "count", "num")):
                args[k] = 3
        return args

    names = [t["name"] for t in tools]
    if kind == "search":
        order = ["search", "web_search", "internet_search", "duckduckgo_search", "ddg_search"]
        name = next((n for n in order if n in names), None) or next(
            (n for n in names if "search" in n.lower() and "fetch" not in n.lower()), None)
        if not name:
            return None
        t = next(t for t in tools if t["name"] == name)
        return name, fill(t, SEARCH_QUERY, ("query", "q", "search_query", "keywords", "text"))
    if kind == "docintel":
        words = ("extract", "convert", "markdown", "parse", "read", "document")
        name = next((n for w in words for n in names if w in n.lower()), names[0] if names else None)
        if not name:
            return None
        t = next(t for t in tools if t["name"] == name)
        return name, fill(t, DOCINTEL_TEXT, ("text", "content", "source", "input", "document", "uri", "url", "path", "file_path"))
    if kind == "echo":
        return ("echo", {"text": SEARCH_QUERY}) if "echo" in names else None
    return None


def call_record(result: types.CallToolResult, verbatim: bool) -> dict[str, Any]:
    blocks = [b.model_dump(mode="json", by_alias=True, exclude_none=True) for b in result.content]
    texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    joined = "\n".join(texts)
    limit = 8000 if verbatim else 2000
    sc = result.structured_content
    return {
        "is_error": result.is_error,
        "content_count": len(blocks),
        "content_types": [b.get("type") for b in blocks],
        "text": joined[:limit],
        "text_truncated": len(joined) > limit,
        "text_length": len(joined),
        "structured_content_type": type(sc).__name__ if sc is not None else None,
        "structured_content_keys": sorted(sc.keys()) if isinstance(sc, dict) else None,
        "structured_content_preview": json.dumps(sc)[:1500] if sc is not None else None,
    }


# --------------------------------------------------------------------------------------------
# Per-server probe
# --------------------------------------------------------------------------------------------


def attempt_entry(label: str, timeout: float, res: RawResult, retry: bool) -> dict[str, Any]:
    msg = res.message if isinstance(res.message, dict) else None
    result = (msg or {}).get("result") if msg else None
    ok = res.status is not None and 200 <= res.status < 300 and isinstance(result, dict) and "protocolVersion" in result
    return {
        "variant": label,
        "cold_start_retry": retry,
        "timeout_s": timeout,
        "http_status": res.status,
        "initialize_ok": ok,
        "protocol_version": result.get("protocolVersion") if ok else None,
        "server_info": result.get("serverInfo") if ok else None,
        "capabilities": result.get("capabilities") if ok else None,
        "instructions": result.get("instructions") if ok else None,
        "jsonrpc_error": (msg or {}).get("error") if msg else None,
        "elapsed_s": res.elapsed_s,
        "response_headers": res.headers,
        "body_snippet": None if ok else res.body_snippet,
        "error": describe_exc(res.error) if res.error else None,
    }


async def probe_server(name: str, cfg: dict[str, Any], key: str, redact: Redactor) -> dict[str, Any]:
    url = cfg["url"]
    out: dict[str, Any] = {
        "url": url, "winning_header_variant": None, "attempts": [], "protocol_version": None,
        "server_info": None, "capabilities": None, "instructions": None, "tools": [], "cold_start_s": None,
        "warm_s": None, "first_response_s": None, "sdk": None, "no_auth_control": None,
        "sample_call": None, "errors": [],
        "timing_notes": ("first_response_s = time to the very first HTTP response of any status (container wake); "
                         "cold_start_s = first successful raw initialize POST; warm_s = identical POST repeated "
                         "immediately; sdk.initialize_s = full SDK handshake once warm."),
    }
    first_request = True
    winner: tuple[str, str, dict[str, str]] | None = None

    for variant in AUTH_VARIANTS:
        label = variant[0]
        v_url, v_headers = auth_material(url, key, variant)
        timeout = FIRST_TIMEOUT_S if first_request else LATER_TIMEOUT_S
        log(name, f"trying {label} (timeout {timeout:.0f}s)", redact)
        res = await raw_initialize(v_url, v_headers, timeout)
        entry = attempt_entry(label, timeout, res, retry=False)
        out["attempts"].append(entry)
        if out["first_response_s"] is None and res.status is not None:
            out["first_response_s"] = res.elapsed_s

        if not entry["initialize_ok"] and first_request and is_cold_start_like(res.error, res.status):
            log(name, f"cold-start-like failure ({entry['error'] or res.status}); retrying once in {COLD_RETRY_DELAY_S:.0f}s", redact)
            await anyio.sleep(COLD_RETRY_DELAY_S)
            res = await raw_initialize(v_url, v_headers, FIRST_TIMEOUT_S)
            entry = attempt_entry(label, FIRST_TIMEOUT_S, res, retry=True)
            out["attempts"].append(entry)
            if out["first_response_s"] is None and res.status is not None:
                out["first_response_s"] = res.elapsed_s
        first_request = False

        log(name, f"  -> HTTP {entry['http_status']} initialize_ok={entry['initialize_ok']} "
                  f"{entry['elapsed_s']}s {entry['error'] or ''}", redact)
        if entry["initialize_ok"]:
            winner = (label, v_url, v_headers)
            out.update(winning_header_variant=label, protocol_version=entry["protocol_version"],
                       server_info=entry["server_info"], capabilities=entry["capabilities"],
                       instructions=entry["instructions"], cold_start_s=entry["elapsed_s"])
            break
        if res.status is None:
            # No HTTP response at all even after the cold-start retry: header choice cannot matter.
            out["errors"].append(f"{label}: no HTTP response ({entry['error']}); skipping remaining variants")
            break
        out["errors"].append(f"{label}: HTTP {res.status}" + (f" error_field={entry['jsonrpc_error']}" if entry["jsonrpc_error"] else ""))

    if winner is None:
        out["errors"].append("no auth variant produced a successful MCP initialize")
        return out

    label, v_url, v_headers = winner

    # Warm initialize: identical raw POST immediately after the cold one.
    warm = await raw_initialize(v_url, v_headers, LATER_TIMEOUT_S)
    warm_entry = attempt_entry(label + " (warm repeat)", LATER_TIMEOUT_S, warm, retry=False)
    out["warm_s"] = warm.elapsed_s if warm_entry["initialize_ok"] else None
    if not warm_entry["initialize_ok"]:
        out["errors"].append(f"warm repeat initialize failed: HTTP {warm.status} {warm_entry['error']}")
    log(name, f"cold_start_s={out['cold_start_s']} warm_s={out['warm_s']}", redact)

    # SDK path: initialize, tools/list, optional sample call.
    sample_kind = cfg.get("sample")

    async def work(session: ClientSession, init: types.InitializeResult, init_s: float) -> None:
        out["sdk"] = {"initialize_ok": True, "initialize_s": init_s, "protocol_version": init.protocol_version,
                      "server_info": init.server_info.model_dump(mode="json", by_alias=True, exclude_none=True),
                      "mcp_package_version": MCP_VERSION, "client_offered_version": LATEST_HANDSHAKE_VERSION}
        tools: list[dict[str, Any]] = []
        cursor = None
        t0 = now()
        while True:
            lr = await session.list_tools(params=types.PaginatedRequestParams(cursor=cursor) if cursor else None)
            tools.extend(tool_record(t) for t in lr.tools)
            cursor = lr.next_cursor
            if not cursor:
                break
        out["sdk"]["tools_list_s"] = round(now() - t0, 3)
        out["tools"] = tools
        log(name, f"tools/list -> {len(tools)} tools: {', '.join(t['name'] for t in tools)}", redact)
        if not sample_kind:
            return
        pick = pick_sample(sample_kind, tools)
        if pick is None:
            out["sample_call"] = {"error": f"no suitable tool found for sample kind {sample_kind!r}"}
            return
        tool_name, args = pick
        rec: dict[str, Any] = {"tool": tool_name, "arguments": args}
        t1 = now()
        try:
            result = await session.call_tool(tool_name, args, read_timeout_seconds=90)
            rec.update(call_record(result, verbatim=(sample_kind == "docintel")))
        except Exception as exc:  # noqa: BLE001 - MCPError carries the server's rejection verbatim
            rec["error"] = describe_exc(exc)
        rec["elapsed_s"] = round(now() - t1, 3)
        out["sample_call"] = rec
        log(name, f"sample call {tool_name} -> {rec.get('is_error', 'exception')} in {rec['elapsed_s']}s", redact)

    try:
        await with_sdk_session(v_url, v_headers, LATER_TIMEOUT_S * 2, work)
    except BaseException as exc:  # noqa: BLE001 - includes ExceptionGroup from anyio task groups
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        msg = describe_exc(exc)
        out["sdk"] = {**(out["sdk"] or {"initialize_ok": False}), "error": msg, "mcp_package_version": MCP_VERSION}
        out["errors"].append(f"SDK session failed: {msg}")
        log(name, f"SDK session failed: {msg}", redact)
        if not out["tools"]:
            try:
                out["tools"] = await raw_list_tools(v_url, v_headers, LATER_TIMEOUT_S)
                out["errors"].append("tools obtained via raw JSON-RPC fallback")
            except Exception as exc2:  # noqa: BLE001
                out["errors"].append(f"raw tools/list fallback failed: {describe_exc(exc2)}")

    # Control: does the server accept a request with no credentials at all?
    ctrl = await raw_initialize(url, {}, LATER_TIMEOUT_S)
    c = attempt_entry("no auth (control)", LATER_TIMEOUT_S, ctrl, retry=False)
    out["no_auth_control"] = {"http_status": c["http_status"], "initialize_ok": c["initialize_ok"],
                              "elapsed_s": c["elapsed_s"], "error": c["error"],
                              "www_authenticate": (c["response_headers"] or {}).get("www-authenticate")}
    log(name, f"no-auth control -> HTTP {c['http_status']} initialize_ok={c['initialize_ok']}", redact)
    return out


async def safe_probe(name: str, cfg: dict[str, Any], key: str, redact: Redactor, results: dict[str, Any]) -> None:
    try:
        results[name] = await probe_server(name, cfg, key, redact)
    except Exception as exc:  # noqa: BLE001 - never let one server kill the run
        results[name] = {"url": cfg["url"], "errors": [f"probe crashed: {describe_exc(exc)}",
                                                        traceback.format_exc()[-3000:]]}


async def run_all(servers: dict[str, dict[str, Any]], key: str, redact: Redactor, sequential: bool) -> dict[str, Any]:
    results: dict[str, Any] = {}
    if sequential:
        for name, cfg in servers.items():
            await safe_probe(name, cfg, key, redact, results)
    else:  # servers are independent containers, so wake them in parallel
        async with anyio.create_task_group() as tg:
            for name, cfg in servers.items():
                tg.start_soon(safe_probe, name, cfg, key, redact, results)
    return {name: results[name] for name in servers}


# --------------------------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------------------------


def summary_table(results: dict[str, Any]) -> str:
    cols = ["server", "auth variant", "proto", "serverInfo", "tools", "cold s", "warm s", "no-auth", "sample", "errors"]
    rows = []
    for name, r in results.items():
        si = r.get("server_info") or {}
        sc = r.get("sample_call") or {}
        sample = "-" if not sc else ("exception" if "error" in sc and "is_error" not in sc
                                     else ("isError" if sc.get("is_error") else "ok"))
        ctrl = r.get("no_auth_control") or {}
        rows.append([
            name, r.get("winning_header_variant") or "NONE", r.get("protocol_version") or "-",
            f"{si.get('name', '-')} {si.get('version', '')}".strip(), str(len(r.get("tools") or [])),
            str(r.get("cold_start_s") if r.get("cold_start_s") is not None else "-"),
            str(r.get("warm_s") if r.get("warm_s") is not None else "-"),
            str(ctrl.get("http_status", "-")) if ctrl else "-", sample, str(len(r.get("errors") or [])),
        ])
    widths = [max(len(c), *(len(row[i]) for row in rows)) for i, c in enumerate(cols)] if rows else [len(c) for c in cols]
    line = "  ".join(c.ljust(w) for c, w in zip(cols, widths))
    sep = "  ".join("-" * w for w in widths)
    body = "\n".join("  ".join(v.ljust(w) for v, w in zip(row, widths)) for row in rows)
    details = []
    for name, r in results.items():
        for e in (r.get("errors") or [])[:8]:
            details.append(f"  {name}: {e.splitlines()[0][:220]}")
        sc = r.get("sample_call") or {}
        if sc:
            txt = (sc.get("error") or sc.get("text") or "").replace("\n", " ")
            details.append(f"  {name}: sample {sc.get('tool')} -> {txt[:220]}")
    return "\n".join([line, sep, body] + (["", "Details:"] + details if details else []))


def write_results(path: Path, results: dict[str, Any], redact: Redactor, meta: dict[str, Any]) -> None:
    doc = redact.deep({"_meta": meta, **results})
    text = json.dumps(doc, indent=2, ensure_ascii=False, default=str)
    if redact.secret and redact.secret in text:  # belt and braces
        raise RuntimeError("API key would leak into output; refusing to write")
    path.write_text(text + "\n", encoding="utf-8")


def meta_block(mode: str, started: float) -> dict[str, Any]:
    return {"mode": mode, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "total_runtime_s": round(time.time() - started, 1), "python": sys.version.split()[0],
            "mcp_version": MCP_VERSION, "httpx_version": httpx.__version__,
            "client_offered_protocol_version": LATEST_HANDSHAKE_VERSION,
            "auth_variants_in_order": [v[0] for v in AUTH_VARIANTS], "api_key_env": ENV_KEY,
            "api_key": REDACTED}


# --------------------------------------------------------------------------------------------
# Self-test: in-process MCP server (echo tool) behind an X-API-Key check, on localhost
# --------------------------------------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_selftest_server(expected_key: str) -> tuple[Any, int]:
    import uvicorn
    from mcp.server.mcpserver import MCPServer

    server = MCPServer("sit-probe-selftest")

    @server.tool()
    def echo(text: str) -> str:
        """Echo the input text back."""
        return f"echo: {text}"

    inner = server.streamable_http_app(streamable_http_path="/mcp", host="127.0.0.1")

    async def app(scope, receive, send):  # minimal ASGI auth gate: only X-API-Key is accepted
        if scope["type"] == "http":
            hdrs = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            if hdrs.get("x-api-key") != expected_key:
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"ApiKey")]})
                await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
                return
        await inner(scope, receive, send)

    port = free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", lifespan="on")
    userver = uvicorn.Server(config)
    thread = threading.Thread(target=userver.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not userver.started and time.time() < deadline:
        time.sleep(0.05)
    if not userver.started:
        raise RuntimeError("self-test server failed to start")
    quiet_library_logs()
    return userver, port


def run_self_test(output: Path) -> int:
    global FIRST_TIMEOUT_S, LATER_TIMEOUT_S, COLD_RETRY_DELAY_S
    FIRST_TIMEOUT_S, LATER_TIMEOUT_S, COLD_RETRY_DELAY_S = 10.0, 10.0, 0.5
    key = "selftest-dummy-key-0123456789"
    redact = Redactor(key)
    started = time.time()
    userver, port = start_selftest_server(key)
    servers = {
        "selftest-echo": {"url": f"http://127.0.0.1:{port}/mcp", "sample": "echo"},
        "selftest-unreachable": {"url": f"http://127.0.0.1:{free_port()}/mcp", "sample": None},
    }
    try:
        results = asyncio.run(run_all(servers, key, redact, sequential=True))
    finally:
        userver.should_exit = True
    write_results(output, results, redact, meta_block("self-test", started))
    print()
    print(summary_table(redact.deep(results)))

    r, u = results["selftest-echo"], results["selftest-unreachable"]
    checks = {
        "Bearer variant rejected with HTTP 401": r["attempts"][0]["http_status"] == 401,
        "X-API-Key variant wins": r["winning_header_variant"] == "X-API-Key",
        "protocolVersion negotiated": bool(r["protocol_version"]),
        "serverInfo recorded": (r["server_info"] or {}).get("name") == "sit-probe-selftest",
        "SDK initialize ok": bool((r["sdk"] or {}).get("initialize_ok")),
        "tools/list has echo with schema": any(t["name"] == "echo" and t["input_schema"] for t in r["tools"]),
        "sample echo call round-trips": (r["sample_call"] or {}).get("text", "").endswith(SEARCH_QUERY),
        "cold and warm timings recorded": r["cold_start_s"] is not None and r["warm_s"] is not None,
        "no-auth control rejected": (r["no_auth_control"] or {}).get("http_status") == 401,
        "unreachable server recorded cleanly": u["winning_header_variant"] is None and len(u["errors"]) >= 2,
        "key absent from JSON file": key not in output.read_text(encoding="utf-8"),
    }
    print("\nSelf-test checks:")
    for desc, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {desc}")
    passed = all(checks.values())
    print(f"\nSelf-test {'PASSED' if passed else 'FAILED'}; results in {output}")
    return 0 if passed else 1


# --------------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description="Probe the SIT lab MCP servers (auth header, protocol, tools, cold start).")
    ap.add_argument("--self-test", action="store_true", help="run against an in-process localhost MCP echo server")
    ap.add_argument("--only", action="append", choices=sorted(SERVERS), help="probe only this server (repeatable)")
    ap.add_argument("--sequential", action="store_true", help="probe servers one at a time (default: in parallel)")
    ap.add_argument("--output", type=Path, default=None, help="results path (default ./mcp_probe_results.json)")
    args = ap.parse_args()

    if args.self_test:
        return run_self_test(args.output or Path("./mcp_probe_selftest_results.json"))

    key = os.environ.get(ENV_KEY, "").strip()
    if not key:
        print(f"Refusing to run: environment variable {ENV_KEY} is not set.\n"
              f"  export {ENV_KEY}='<shared API key from the lab brief, section 2.2>'", file=sys.stderr)
        return 2

    quiet_library_logs()
    redact = Redactor(key)
    output = args.output or Path("./mcp_probe_results.json")
    servers = {n: SERVERS[n] for n in (args.only or SERVERS)}
    started = time.time()
    print(f"Probing {len(servers)} server(s) with mcp {MCP_VERSION}; first contact may take 1-2 min per server "
          f"(scale-to-zero). Worst case ~10 min.", flush=True)
    results: dict[str, Any] = {}
    try:
        results = asyncio.run(run_all(servers, key, redact, args.sequential))
    except KeyboardInterrupt:
        print("Interrupted; writing partial results.", file=sys.stderr)
    except BaseException as exc:  # noqa: BLE001 - always leave a results file behind
        print(redact.s(f"Unexpected failure: {describe_exc(exc)}"), file=sys.stderr)
    for name, cfg in servers.items():
        results.setdefault(name, {"url": cfg["url"], "errors": ["not probed (run interrupted)"]})
    write_results(output, results, redact, meta_block("live", started))
    print()
    print(summary_table(redact.deep(results)))
    print(f"\nWrote {output.resolve()} (API key redacted). Paste it back into the Claude session.")
    return 0  # always 0 so partial results can be shared


if __name__ == "__main__":
    sys.exit(main())
