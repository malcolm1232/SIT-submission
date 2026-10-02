"""Cassette keys, argument canonicalisation and secret redaction (REPRODUCIBILITY §6, robustness §6.2).

Cassette layout: ``<cassette_dir>/tools/<server>/<tool>/<key>.json`` with the robustness §6.2
fields; ``<cassette_dir>/tools_list/<server>.json`` holds the recorded ``tools/list``.
Cassette key = SHA-256 of ``server|tool|canonical_args``.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus

from sit_review_agent.hashing import canonical_json, sha256_text

REDACTED = "***REDACTED***"

#: Argument keys dropped before hashing (volatile per call).
VOLATILE_ARG_KEYS = frozenset({"request_id", "requestId", "timestamp", "nonce", "_meta", "session_id"})
#: Argument keys whose string value is lower-cased before hashing (queries).
QUERY_ARG_KEYS = frozenset({"query", "q", "search", "search_query", "keywords"})
_WS = re.compile(r"\s+")


def canonical_args(args: dict[str, Any]) -> dict[str, Any]:
    """Keys sorted (by canonical JSON), whitespace collapsed, queries lower-cased, volatile keys dropped."""

    def norm(key: str | None, v: Any) -> Any:
        if isinstance(v, dict):
            return {k: norm(k, x) for k, x in v.items() if k not in VOLATILE_ARG_KEYS}
        if isinstance(v, list):
            return [norm(None, x) for x in v]
        if isinstance(v, str):
            s = _WS.sub(" ", v).strip()
            return s.lower() if key in QUERY_ARG_KEYS else s
        return v

    return norm(None, args)


def cassette_key(server: str, tool: str, args: dict[str, Any]) -> str:
    return sha256_text(f"{server}|{tool}|{canonical_json(canonical_args(args))}")


def cassette_path(cassette_dir: Path, server: str, tool: str, key: str) -> Path:
    return cassette_dir / "tools" / server / tool / f"{key}.json"


def tools_list_path(cassette_dir: Path, server: str) -> Path:
    return cassette_dir / "tools_list" / f"{server}.json"


class Redactor:
    """Replaces every form of each secret (raw, URL-encoded) with ``***REDACTED***``.
    Same approach as scripts/probe_mcp_servers.py. Applied to cassettes, logs and checkpoints (INV-08)."""

    def __init__(self, secrets: Iterable[str]) -> None:
        forms: set[str] = set()
        for s in secrets:
            if s:
                forms |= {s, quote(s, safe=""), quote_plus(s)}
        self.forms = sorted(forms, key=len, reverse=True)

    @classmethod
    def from_env(cls, names: Iterable[str] = ("SIT_MCP_API_KEY", "ANTHROPIC_API_KEY")) -> Redactor:
        return cls(os.environ.get(n, "") for n in names)

    def text(self, value: str) -> str:
        for f in self.forms:
            value = value.replace(f, REDACTED)
        return value

    def deep(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {self.deep(k): self.deep(v) for k, v in obj.items()}
        if isinstance(obj, list | tuple):
            return [self.deep(v) for v in obj]
        if isinstance(obj, str):
            return self.text(obj)
        return obj

    def contains_secret(self, value: str) -> bool:
        return any(f in value for f in self.forms)
