"""Scrub a recorded ``claude -p --output-format stream-json`` stream into a test fixture.

Usage: ``python tests/fixtures/stream/scrub_stream.py <raw.jsonl> <fixture.jsonl>``.

The raw streams were recorded on 2026-10-03 through ``ClaudeCodeGateway`` (Claude Code 2.1.288,
Haiku 4.5, ``--setting-sources ""``; latency redesign W1). Kept: every event's type, order and
numeric fields, the streamed answer (``input_json_delta``) and the ``result`` object. Removed or
replaced: session ids, event uuids, message, request and tool-use ids, thinking signatures, the
init event's machine details (working directory, memory paths, plugins, agents, skills, sockets,
capabilities) and the account's rate-limit event. A scrubbed fixture holds no path, user name,
email, key or session value; ``tests/test_stream_fixtures.py`` checks that.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

SESSION = "00000000-0000-4000-8000-000000000000"
INIT_KEEP = ("type", "subtype", "model", "claude_code_version", "apiKeySource", "permissionMode", "output_style",
             "tools", "mcp_servers")
DROP_TYPES = {"rate_limit_event"}
#: API object ids anywhere in a string (a tool-use id is echoed inside the tool result too).
ID_RE = re.compile(r"\b(msg|toolu|req)_[A-Za-z0-9]{10,}")


def _scrub(v: Any, key: str = "") -> Any:
    if isinstance(v, dict):                 # keys too: ``wire_tool_inputs`` is keyed by tool-use id
        return {ID_RE.sub(lambda m: m.group(1) + "_fixture", k): _scrub(x, k) for k, x in v.items()}
    if isinstance(v, list):
        return [_scrub(x, key) for x in v]
    if isinstance(v, str):
        if key == "session_id":
            return SESSION
        if key == "signature":
            return ""
        if key in ("id", "tool_use_id") and v.startswith(("msg_", "toolu_")):
            return v.split("_", 1)[0] + "_fixture"
        if key == "request_id":
            return "req_fixture"
        if key == "timestamp":
            return "2026-10-03T00:00:00.000Z"
        return ID_RE.sub(lambda m: m.group(1) + "_fixture", v)
    return v


def scrub_lines(lines: list[str]) -> list[str]:
    out: list[str] = []
    for n, line in enumerate(x for x in lines if x.strip()):
        ev = json.loads(line)
        if ev.get("type") in DROP_TYPES:
            continue
        if ev.get("type") == "system" and ev.get("subtype") == "init":
            ev = {k: ev[k] for k in INIT_KEEP if k in ev}
        ev = _scrub(ev)
        if "uuid" in ev:
            ev["uuid"] = f"00000000-0000-4000-8000-{n:012d}"
        out.append(json.dumps(ev, ensure_ascii=False, separators=(",", ":")))
    return out


def main(src: str, dst: str) -> None:
    lines = Path(src).read_text(encoding="utf-8").splitlines()
    Path(dst).write_text("".join(x + "\n" for x in scrub_lines(lines)), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
