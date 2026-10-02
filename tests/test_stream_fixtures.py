"""The gateway and ``llm.partial`` on REAL ``claude -p`` event streams (latency redesign W1).

``tests/fixtures/stream/haiku_*.jsonl`` were recorded on 2026-10-03 through ``ClaudeCodeGateway``
(Claude Code 2.1.288, Haiku 4.5, ``--setting-sources ""``) and scrubbed by ``scrub_stream.py``:
``haiku_short`` is a finished three-finding answer, ``haiku_cut`` an answer cut by a 10.5 s stage
limit, ``haiku_trivial`` a one-word text answer. The tests replay them line by line, so the parser
is checked against what the CLI writes, not against a guess.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from sit_review_agent.clock import FakeClock
from sit_review_agent.config import EffectiveConfig, load_config
from sit_review_agent.errors import LLMDeadlineError
from sit_review_agent.llm.claude_code import ClaudeCodeGateway, CompletedRun, StreamTimeout
from sit_review_agent.llm.gateway import LLMRequest, Usage
from sit_review_agent.llm.partial import JSON_CHARS_PER_TOKEN, StreamParser
from sit_review_agent.llm.runtime import RunDeadline, RuntimeLimits, attach_runtime
from sit_review_agent.paths import repo_root
from sit_review_agent.progress import NullProgress
from sit_review_agent.rundir import JsonlWriter, RunDir
from sit_review_agent.states import PhaseName

FIXTURES = repo_root() / "tests" / "fixtures" / "stream"
NAMES = ("haiku_short", "haiku_cut", "haiku_trivial")


def lines(name: str) -> list[str]:
    return (FIXTURES / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()


def events(name: str) -> list[dict[str, Any]]:
    return [json.loads(x) for x in lines(name)]


class Item(BaseModel):
    title: str
    detail: str


class Findings(BaseModel):
    findings: list[Item]


class Replay:
    """Feeds a recorded stream through ``on_line``; ``cut`` raises the runner's timeout after it."""

    def __init__(self, name: str, *, cut: bool = False, between: Callable[[str], None] | None = None) -> None:
        self.lines, self.cut, self.between = lines(name), cut, between
        self.argv: list[str] = []

    async def __call__(self, argv: list[str], stdin: str, env: dict[str, str], cwd: Path, timeout_s: float, *,
                       on_line: Callable[[str], None] | None = None) -> CompletedRun:
        self.argv = argv
        for line in self.lines:
            if on_line is not None:
                on_line(line)
            if self.between is not None:
                self.between(line)
        stdout = "".join(x + "\n" for x in self.lines)
        if self.cut:
            raise StreamTimeout(stdout=stdout, stderr="")
        return CompletedRun(0, stdout, "")


@pytest.fixture(scope="module")
def cfg() -> EffectiveConfig:
    return load_config()


def assess(schema: Any = Findings) -> LLMRequest:
    return LLMRequest(phase=PhaseName.ASSESS, conversation_id="assess-1", system="s",
                      messages=[{"role": "user", "content": [{"type": "text", "text": "doc"}]}], effort="low",
                      max_tokens=8000, output_schema=schema)


# ------------------------------------------------------------------------------ the fixtures themselves


@pytest.mark.parametrize("name", NAMES)
def test_fixtures_are_scrubbed(name: str) -> None:
    text = (FIXTURES / f"{name}.jsonl").read_text(encoding="utf-8")
    for needle in ("sk-ant", "oauth", "/Users/", "/home/", "/private/", "malco", "cwd", "memory_paths", "plugins",
                   "rate_limit", "messaging_socket"):
        assert needle not in text.lower(), needle
    assert not re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}", text)
    assert not re.search(r"\b(msg|toolu|req)_[A-Za-z0-9]{10,}", text)
    sessions = {e.get("session_id") for e in events(name)} - {None}
    assert sessions == {"00000000-0000-4000-8000-000000000000"}
    assert all(not e.get("event", {}).get("delta", {}).get("signature") for e in events(name))


@pytest.mark.parametrize("name", NAMES)
def test_the_events_the_parser_relies_on_are_in_the_real_stream(name: str) -> None:
    evs = events(name)
    kinds = [(e["type"], e.get("subtype") or e.get("event", {}).get("type")) for e in evs]
    assert kinds[0] == ("system", "init")
    assert ("stream_event", "message_start") in kinds and ("system", "thinking_tokens") in kinds
    starts = [e["event"]["content_block"] for e in evs if e.get("event", {}).get("type") == "content_block_start"]
    assert any(b.get("type") == "tool_use" and b.get("name") == "StructuredOutput" for b in starts)
    deltas = [e["event"]["delta"]["type"] for e in evs if e.get("event", {}).get("type") == "content_block_delta"]
    assert "input_json_delta" in deltas
    if name == "haiku_cut":
        assert "result" not in {e["type"] for e in evs}
    else:
        last = evs[-1]
        assert last["type"] == "result"
        # the keys the gateway reads, as --output-format json printed them
        assert {"is_error", "structured_output", "usage", "modelUsage", "total_cost_usd", "stop_reason", "num_turns",
                "terminal_reason", "subtype"} <= set(last)


# ------------------------------------------------------------------------------ finished answers


def test_short_answer_through_the_gateway(tmp_path: Path, cfg: EffectiveConfig) -> None:
    import asyncio

    sink = NullProgress()
    drafts_at_line: list[int] = []
    runner = Replay("haiku_short", between=lambda _: drafts_at_line.append(
        sum(1 for e in sink.events if e.kind == "draft")))
    rd = RunDir(tmp_path / "run").create()
    gw = ClaudeCodeGateway(cfg, rd, clock=FakeClock(), runner=runner, progress=sink)
    res = asyncio.run(gw.call(assess()))
    final = events("haiku_short")[-1]
    assert isinstance(res.parsed, Findings) and len(res.parsed.findings) == 3
    assert res.parsed.model_dump() == final["structured_output"]
    assert res.usage == Usage(1250, 520, 0, 0) == gw.usage_total()
    assert gw.cost_total_usd == pytest.approx(final["total_cost_usd"])
    drafts = [e.message for e in sink.events if e.kind == "draft"]
    assert len(drafts) == 3 and all(d.startswith(f"draft finding {i + 1} (unverified; llm-0001 assess)")
                                    for i, d in enumerate(drafts))
    assert drafts_at_line.index(3) < len(drafts_at_line) - 1           # all three shown before the result line
    assert JsonlWriter(rd.llm_log).read()[-1]["outcome"] == "ok"


def test_every_prefix_of_the_short_stream_salvages_a_prefix_of_the_answer() -> None:
    final = events("haiku_short")[-1]["structured_output"]["findings"]
    p = StreamParser()
    counts = []
    for line in lines("haiku_short"):
        p.feed_line(line)
        part = p.partial()
        got = (part or {}).get("findings", [])
        assert got == final[:len(got)]
        counts.append(len(got))
    assert counts == sorted(counts) and counts[-1] == 3


def test_trivial_text_answer_and_hermetic_input_tokens(tmp_path: Path, cfg: EffectiveConfig) -> None:
    """The hermetic figure (design M3: 1,137 input tokens on a trivial Haiku call with
    ``--setting-sources ""``; this recording: 1,131 with the gateway's own system prompt and schema,
    against 2,570 with the user settings, design M2)."""
    import asyncio

    rd = RunDir(tmp_path / "run").create()
    gw = ClaudeCodeGateway(cfg, rd, clock=FakeClock(), runner=Replay("haiku_trivial"))
    res = asyncio.run(gw.call(assess(None)))
    assert res.text == "ok"
    start = next(e for e in events("haiku_trivial") if e.get("event", {}).get("type") == "message_start")
    assert start["event"]["message"]["usage"]["input_tokens"] == res.usage.input_tokens == 1131
    assert events("haiku_trivial")[0]["apiKeySource"] == "none"        # subscription login, no API key


# ------------------------------------------------------------------------------ the cut


def test_recorded_cut_salvages_its_finished_findings(tmp_path: Path, cfg: EffectiveConfig) -> None:
    import asyncio

    rd = RunDir(tmp_path / "run").create()
    gw = ClaudeCodeGateway(cfg, rd, clock=FakeClock(), runner=Replay("haiku_cut", cut=True))
    attach_runtime(gw, RuntimeLimits(deadline=RunDeadline(540, 75, 200, lambda: 0.0, stage_limits={
        "stage_1_end": 10.5, "refine_end": 465.0, "verdict_end": 530.0})))
    with pytest.raises(LLMDeadlineError, match="by the stage 1 limit") as ei:
        asyncio.run(gw.call(assess()))
    err = ei.value
    assert err.salvaged_items == 5 and err.partial is not None
    salvaged = Findings.model_validate(err.partial)                    # every salvaged item is a whole finding
    assert len(salvaged.findings) == 5
    chars = sum(len(e["event"]["delta"]["partial_json"]) for e in events("haiku_cut")
                if e.get("event", {}).get("delta", {}).get("type") == "input_json_delta")
    thinking = max(e["estimated_tokens"] for e in events("haiku_cut") if e.get("subtype") == "thinking_tokens")
    assert err.usage is None
    assert err.estimated_usage == Usage(1270, thinking + math.ceil(chars / JSON_CHARS_PER_TOKEN), 0, 0)
    assert gw.usage_total() == Usage() and gw.cost_total_usd == 0.0
    entry = JsonlWriter(rd.llm_log).read()[-1]
    assert entry["usage"] is None and entry["usage_unrecorded"] == "deadline_cut"
    assert entry["usage_estimate"]["estimated"] is True and entry["salvaged_items"] == 5


def test_recorded_cut_mid_finding_never_yields_half_a_finding() -> None:
    p = StreamParser()
    seen = 0
    for line in lines("haiku_cut"):
        p.feed_line(line)
        part = p.partial()
        if part:
            Findings.model_validate(part)                              # whatever the cut point
            assert len(part["findings"]) >= seen
            seen = len(part["findings"])
    assert seen == 5 and p.answer_chars > 0 and not p.scanner.closed
