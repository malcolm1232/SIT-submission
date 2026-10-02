"""Pure policy checks used by :class:`~sit_review_agent.tools.gateway.PolicyToolGateway` (workstream B).

* URL policy (``config/url_policy.yaml``, ADR-001 "fixed action types, adaptive queries", audit C18):
  deny/allow domain modes, ``fetch_only_from_results`` (a fetched URL must have appeared in an
  earlier tool result or in the document) and ``reject_added_query_strings`` (a URL whose query
  string was not in the URL as seen is refused: robustness ADV-05, the exfiltration channel).
* Argument sanitiser (robustness ADV-05, OPS-03, INV-08): no secret, canary, key-shaped token,
  private-key block or bulk document text may leave the process in tool arguments.

Everything here is deterministic and side-effect free; the gateway turns a refusal into a
``blocked`` :class:`~sit_review_agent.tools.gateway.ToolResult`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from sit_review_agent.config import UrlPolicy
from sit_review_agent.tools.cassette import Redactor

#: URLs anywhere in text (tool results, document text, arguments).
URL_RE = re.compile(r"https?://[^\s<>\"'`\])}]+", re.IGNORECASE)
#: Argument keys whose value is a URL to fetch (browser / page-fetch tools).
FETCH_KEYS = frozenset({"url", "uri", "href", "link", "page_url", "target_url", "address", "source_url"})
#: Robustness §6.4 canaries (``CANARY-MCP-7f3a…``, ``CANARY-LLM-c21e…``).
CANARY_RE = re.compile(r"CANARY-[A-Za-z]+-[0-9A-Za-z]{2,}")
#: Key-shaped tokens that must never be sent anywhere (patterns, not values).
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}")),
    ("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}")),
    ("slack_token", re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{16,}", re.IGNORECASE)),
    ("credential_assignment", re.compile(
        r"\b(api[_-]?key|access[_-]?token|secret|password|passwd)\b\s*[=:]\s*['\"]?[^\s'\"&]{8,}", re.IGNORECASE)),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}")),
)
#: A long unbroken base64/hex run is how bulk content gets smuggled into a query (ADV-05).
BLOB_RE = re.compile(r"[A-Za-z0-9+/=_-]{120,}")
#: No single argument string may carry more than this many characters (document exfiltration).
MAX_ARG_CHARS = 2000


def _strings(obj: Any, key: str | None = None) -> Iterator[tuple[str | None, str]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(v, str(k))
    elif isinstance(obj, list | tuple):
        for v in obj:
            yield from _strings(v, key)
    elif isinstance(obj, str):
        yield key, obj


def sanitise_args(args: dict[str, Any], redactor: Redactor) -> str | None:
    """Return the reason the arguments must not be sent, or ``None``. Never echoes the secret."""
    for key, value in _strings(args):
        if redactor.contains_secret(value):
            return f"argument {key!r} contains a configured secret"
        if CANARY_RE.search(value):
            return f"argument {key!r} contains a canary token"
        for label, pat in SECRET_PATTERNS:
            if pat.search(value):
                return f"argument {key!r} contains a {label.replace('_', ' ')}-shaped value"
        if len(value) > MAX_ARG_CHARS:
            return (f"argument {key!r} is {len(value)} characters (limit {MAX_ARG_CHARS}; possible document "
                    "exfiltration)")
        for m in BLOB_RE.finditer(value):
            if not URL_RE.fullmatch(m.group(0)):
                return f"argument {key!r} carries a {len(m.group(0))}-character encoded blob"
    return None


def scrub_args(args: dict[str, Any], redactor: Redactor) -> dict[str, Any]:
    """Arguments with every risky string replaced, for logging a blocked call (INV-08)."""

    def walk(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: walk(x) for k, x in v.items()}
        if isinstance(v, list | tuple):
            return [walk(x) for x in v]
        if isinstance(v, str):
            bad = (redactor.contains_secret(v) or CANARY_RE.search(v) or len(v) > MAX_ARG_CHARS
                   or any(p.search(v) for _, p in SECRET_PATTERNS) or BLOB_RE.search(v))
            return "***BLOCKED***" if bad else v
        return v

    return walk(args)


# ------------------------------------------------------------------------------ URLs


def normalise_url(url: str) -> str:
    """Lower-case scheme and host, drop the fragment and a trailing ``/`` of the path."""
    p = urlsplit(url.strip().rstrip(".,;:"))
    path = p.path.rstrip("/") if p.path not in ("", "/") else ""
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, p.query, ""))


def url_base(url: str) -> str:
    """:func:`normalise_url` without the query string."""
    p = urlsplit(normalise_url(url))
    return urlunsplit((p.scheme, p.netloc, p.path, "", ""))


def urls_in(obj: Any) -> list[str]:
    """Every http(s) URL in a nested structure of strings."""
    out: list[str] = []
    for _, s in _strings(obj):
        out.extend(m.group(0).rstrip(".,;:") for m in URL_RE.finditer(s))
    return out


def domain_matches(host: str, domains: Iterable[str]) -> bool:
    host = host.lower().split(":")[0]
    for d in domains:
        d = d.lower().lstrip(".")
        if d and (host == d or host.endswith("." + d)):
            return True
    return False


class SeenUrls:
    """URLs the agent may fetch: seen in an earlier tool result or cited by the document."""

    def __init__(self) -> None:
        self.exact: set[str] = set()
        self.bases: set[str] = set()

    def add(self, urls: Iterable[str]) -> None:
        for u in urls:
            try:
                self.exact.add(normalise_url(u))
                self.bases.add(url_base(u))
            except ValueError:
                continue

    def __len__(self) -> int:
        return len(self.exact)


def fetch_urls(args: dict[str, Any]) -> list[str]:
    """URLs the call would fetch: values of fetch-like keys, or any argument that *is* a URL."""
    out: list[str] = []
    for key, value in _strings(args):
        v = value.strip()
        if (key or "").lower() in FETCH_KEYS or URL_RE.fullmatch(v):
            out.append(v)
    return out


def check_urls(args: dict[str, Any], policy: UrlPolicy, seen: SeenUrls) -> str | None:
    """Return why the URL policy refuses ``args``, or ``None``."""
    to_fetch = fetch_urls(args)
    all_urls = set(urls_in(args)) | set(to_fetch)
    for url in sorted(all_urls):
        try:
            p = urlsplit(url)
        except ValueError:
            return "unparseable URL in arguments"
        if url in to_fetch and p.scheme.lower() not in ("http", "https"):
            return f"scheme {p.scheme or '(none)'!r} is not allowed (http/https only)"
        host = (p.hostname or "").lower()
        if not host and url in to_fetch:
            return "URL without a host"
        if policy.mode == "deny" and domain_matches(host, policy.deny_domains):
            return f"domain {host} is denied by url_policy.yaml"
        if policy.mode == "allow" and not domain_matches(host, policy.allow_domains):
            return f"domain {host} is not in url_policy.yaml allow_domains"
        if policy.reject_added_query_strings and p.query and normalise_url(url) not in seen.exact:
            return f"query string on {host} was not in any URL seen in results or the document"
    if policy.fetch_only_from_results:
        for url in to_fetch:
            if url_base(url) not in seen.bases:
                return "URL did not appear in an earlier tool result or in the document"
    return None
