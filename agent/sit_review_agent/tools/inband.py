"""In-band tool failures: a call the transport delivered whose payload says the tool failed.

An MCP server can answer a call successfully (no ``isError``) with a payload that reports a
failure. Run ui-261005-170012-2648 stored such payloads as evidence: every web search provider
failed and ``search_web`` answered::

    {"results": [], "provider_used": null,
     "attempts": [{"provider": "duckduckgo", "outcome": "error", "reason": "No results found.",
                   "failure_code": "unknown_error", "result_count": 0},
                  {"provider": "tavily", "outcome": "skipped", "reason": "TAVILY_API_KEY not configured",
                   "failure_code": "no_api_key", "result_count": 0}]}

:func:`inband_failure` reads one payload and returns a short reason when it is such a failure;
the gateway then builds the result as a failure (``ok=False``), so it never becomes evidence.
The rules are conservative: a payload that carries real results or readable text is never a
failure, whatever warning or failed-provider note it also carries. Pure and side-effect free.
"""

from __future__ import annotations

import json
import re
from typing import Any

#: Keys under which a payload carries its result list (as in ``sources._LIST_KEYS``).
RESULT_KEYS = ("results", "items", "hits", "data", "works", "papers", "records", "entries", "organic",
               "organic_results", "web", "documents", "references", "articles", "matches")
#: Keys whose non-empty string value is readable content (a fetched page, a record, an answer).
TEXT_KEYS = ("extracted_text", "content", "text", "markdown", "body", "passage", "page_content", "abstract",
             "snippet", "answer", "summary")
_ERROR_KEYS = ("error", "errors", "exception", "error_message", "errorMessage", "fetch_error")
_MESSAGE_KEYS = ("message", "detail", "reason", "status_message")
_HTTP_KEYS = ("status_code", "statusCode", "http_status", "status")
_FAILED_STATUS = frozenset({"error", "failed", "failure", "fail", "exception", "timeout", "blocked", "denied"})
_SEARCH_WORDS = ("search", "query", "lookup", "find")
#: Provider configuration, quota and rate-limit messages.
PROVIDER_RE = re.compile(r"not configured|no[ _]api[ _]key|api[ _]key (?:is )?(?:missing|invalid|not set)"
                         r"|missing api[ _]key|quota|rate[ _-]?limit|too many requests|\b429\b", re.IGNORECASE)
_TEXT_ERROR_RE = re.compile(r"^\s*(?:error|exception|traceback|failed|failure)\b", re.IGNORECASE)
#: A plain-text payload is judged by a provider message only while it is this short.
_SHORT_TEXT = 300
_REASON_CHARS = 300


def payload_of(text: str, structured_content: Any) -> Any:
    """The payload a result carries: its structured content (unwrapping ``{"result": x}``, the
    wrapper an MCP server puts around a plain return value), else its text parsed as JSON, else
    the text itself."""
    data = structured_content
    if isinstance(data, dict) and set(data) == {"result"}:
        data = data["result"]
    if data is None or data == "":
        data = text or ""
    if isinstance(data, str):
        t = data.strip()
        if t[:1] in ("{", "["):
            try:
                return json.loads(t)
            except json.JSONDecodeError:
                return data
    return data


def inband_failure(tool_name: str, payload: Any) -> str | None:
    """A short reason when ``payload`` (a parsed JSON value or a text) reports that the tool
    failed, else ``None``.

    * A dict with an HTTP status outside 2xx (``status_code``, ``http_status``, numeric ``status``).
    * A dict with real results (a non-empty result list) or readable text is never a failure.
    * Otherwise a dict with an error or exception field, ``success``/``ok`` false, a failed
      ``status`` string, an error or provider message (not configured, no API key, quota, rate
      limit), or a failed provider attempt saying so; and, for a search tool, an empty result list.
    * A list of page records fails only when every record fails; an empty list fails for a search tool.
    * Plain text fails when it starts with an error word, or is short and is a provider message.
    """
    if isinstance(payload, dict) and set(payload) == {"result"}:
        payload = payload["result"]
    if isinstance(payload, str):
        parsed = payload_of(payload, None)
        if not isinstance(parsed, str):
            return inband_failure(tool_name, parsed)
        return _text_failure(payload)
    if isinstance(payload, list):
        return _list_failure(tool_name, payload)
    if isinstance(payload, dict):
        return _dict_failure(tool_name, payload)
    return None


def _clip(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= _REASON_CHARS else s[: _REASON_CHARS - 3].rstrip() + "..."


def _is_search(tool_name: str) -> bool:
    name = tool_name.lower()
    return any(w in name for w in _SEARCH_WORDS)


def _text_failure(text: str) -> str | None:
    t = text.strip()
    if not t:
        return None
    first = t.splitlines()[0]
    if _TEXT_ERROR_RE.match(first):
        return _clip(first)
    if len(t) <= _SHORT_TEXT and PROVIDER_RE.search(t):
        return _clip(t)
    return None


def _http_status(d: dict[str, Any]) -> int | None:
    for k in _HTTP_KEYS:
        v = d.get(k)
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, str) and re.fullmatch(r"\d{3}", v.strip()):
            return int(v)
    return None


def _has_results(d: dict[str, Any]) -> bool:
    return any(isinstance(d.get(k), list) and any(d[k]) for k in RESULT_KEYS)


def _has_text(d: dict[str, Any]) -> bool:
    return any(isinstance(d.get(k), str) and d[k].strip() for k in TEXT_KEYS)


def _err_text(v: Any) -> str | None:
    if isinstance(v, str) and v.strip():
        return v
    if isinstance(v, dict) and v:
        for k in ("message", "detail", "reason", "error", "code"):
            if isinstance(v.get(k), str | int) and str(v[k]).strip():
                return str(v[k])
        return json.dumps(v, ensure_ascii=False, sort_keys=True)
    if isinstance(v, list) and v:
        return "; ".join(t for t in (_err_text(x) for x in v) if t) or None
    return None


def _attempts(d: dict[str, Any]) -> list[dict[str, Any]]:
    raw = d.get("attempts")
    return [a for a in raw if isinstance(a, dict)] if isinstance(raw, list) else []


def _attempt_summary(attempts: list[dict[str, Any]]) -> str:
    parts = []
    for a in attempts:
        provider = str(a.get("provider") or "provider")
        why = a.get("reason") or a.get("failure_code") or a.get("outcome")
        parts.append(f"{provider}: {why}" if why else provider)
    return "; ".join(parts)


def _dict_failure(tool_name: str, d: dict[str, Any]) -> str | None:
    status = _http_status(d)
    if status is not None and not 200 <= status <= 299:
        msg = next((_err_text(d.get(k)) for k in (*_ERROR_KEYS, *_MESSAGE_KEYS) if _err_text(d.get(k))), None)
        return _clip(f"HTTP {status}" + (f": {msg}" if msg else ""))
    if _has_results(d) or _has_text(d):
        return None
    for k in _ERROR_KEYS:
        msg = _err_text(d.get(k))
        if msg:
            return _clip(f"{k}: {msg}")
    for k in ("success", "ok"):
        if d.get(k) is False:
            msg = next((_err_text(d.get(m)) for m in _MESSAGE_KEYS if _err_text(d.get(m))), None)
            return _clip(f"{k} is false" + (f": {msg}" if msg else ""))
    st = d.get("status")
    if isinstance(st, str) and st.strip().lower() in _FAILED_STATUS:
        msg = next((_err_text(d.get(m)) for m in _MESSAGE_KEYS if _err_text(d.get(m))), None)
        return _clip(f"status {st.strip()}" + (f": {msg}" if msg else ""))
    for k in _MESSAGE_KEYS:
        msg = _err_text(d.get(k))
        if msg and (PROVIDER_RE.search(msg) or _TEXT_ERROR_RE.match(msg)):
            return _clip(msg)
    attempts = _attempts(d)
    empty = [k for k in RESULT_KEYS if isinstance(d.get(k), list) and not any(d[k])]
    if empty and _is_search(tool_name):
        summary = _attempt_summary(attempts)
        return _clip(f"{tool_name} returned an empty result list" + (f" ({summary})" if summary else ""))
    reasons = " ".join(str(a.get("reason") or a.get("failure_code") or "") for a in attempts)
    if attempts and not any(str(a.get("outcome", "")).lower() in ("used", "ok", "success") for a in attempts) \
            and PROVIDER_RE.search(reasons):
        return _clip(f"no provider answered ({_attempt_summary(attempts)})")
    return None


def _list_failure(tool_name: str, items: list[Any]) -> str | None:
    if not items:
        return f"{tool_name} returned an empty result list" if _is_search(tool_name) else None
    reasons: list[str] = []
    for item in items:
        if isinstance(item, dict):
            r = _dict_failure(tool_name, item)
        elif isinstance(item, str):
            r = _text_failure(item)
        else:
            r = None
        if r is None:
            return None                     # one usable record: the payload is not a failure
        reasons.append(r)
    return _clip(f"every item failed: {reasons[0]}" if len(reasons) > 1 else reasons[0])
