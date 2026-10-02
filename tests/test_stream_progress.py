"""Progress from the CLI event stream (latency redesign W1, design section 4 "Progress shown live").

A status line at least every 10 s listing each open call with its thinking-token estimate or its
streamed item count; a line per draft item labelled draft and unverified; the stage milestones; one
line per event, never a control character from model text in the terminal or ``progress.log``.
Offline; virtual clock or real asyncio time of a few milliseconds.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path

from sit_review_agent.clock import FakeClock, SystemClock
from sit_review_agent.progress import (
    MILESTONES,
    CallTracker,
    ConsoleProgress,
    NullProgress,
    draft_line,
    one_line,
)


def test_status_line_lists_every_open_call() -> None:
    sink = NullProgress()
    tracker = CallTracker(sink, FakeClock())
    tracker.open("llm-0003", "assess", "shard 1 intent_fitness")
    tracker.open("llm-0004", "assess", "shard 2")
    tracker.open("llm-0005", "understand")
    tracker.update("llm-0003", thinking_tokens=4210)
    tracker.update("llm-0004", thinking_tokens=3900, items=3, chars=13_500)
    line = tracker.status_line()
    assert line is not None
    assert "3 open calls" in line
    assert "llm-0003 assess shard 1 intent_fitness: thinking ~4,210 tokens" in line
    assert "llm-0004 assess shard 2: 3 items streamed (13,500 chars)" in line
    assert "llm-0005 understand: starting" in line
    tracker.close("llm-0003")
    tracker.close("llm-0004")
    tracker.close("llm-0005")
    assert tracker.status_line() is None


def test_status_lines_come_at_least_every_10_s() -> None:
    async def scenario() -> list[str]:
        sink = NullProgress()
        tracker = CallTracker(sink, SystemClock(), interval_s=0.02)
        tracker.open("llm-0001", "assess")
        tracker.update("llm-0001", thinking_tokens=50)
        await asyncio.sleep(0.09)
        tracker.close("llm-0001")
        await asyncio.sleep(0.05)                     # no line once nothing is open
        return [e.message for e in sink.events]

    lines = asyncio.run(scenario())
    assert 3 <= len(lines) <= 5, lines
    assert all("llm-0001 assess: thinking ~50 tokens" in m for m in lines)
    assert CallTracker(NullProgress(), SystemClock()).interval_s <= 10.0


def test_tracker_ticker_stops_when_the_last_call_closes() -> None:
    async def scenario() -> bool:
        tracker = CallTracker(NullProgress(), SystemClock(), interval_s=0.01)
        tracker.open("a", "plan")
        tracker.open("b", "plan")
        tracker.close("a")
        running = tracker.ticking
        tracker.close("b")
        await asyncio.sleep(0.03)
        return running and not tracker.ticking

    assert asyncio.run(scenario())


def test_draft_line_is_labelled_and_single_line() -> None:
    item = {"id": "FND-002", "severity": "high", "title": "Retries\nwithout idempotency \x1b[31mkeys\x1b[0m"}
    line = draft_line("findings", 1, item, call_id="llm-0004", phase="assess")
    assert line.startswith("draft finding 2 (unverified; llm-0004 assess): [high] Retries without idempotency")
    assert "\n" not in line and "\x1b" not in line
    assert draft_line("revisions", 0, {"finding_id": "FND-001", "action": "keep"}, call_id="c",
                      phase="refine").startswith("draft revision 1 (unverified; c refine)")
    assert draft_line("registry", 4, "a bare string", call_id="c", phase="understand") \
        .startswith("draft registry item 5 (unverified; c understand)")
    assert len(draft_line("findings", 0, {"title": "x" * 500}, call_id="c", phase="assess")) < 200


def test_console_lines_stay_one_per_event(tmp_path: Path) -> None:
    out = io.StringIO()
    log = tmp_path / "progress.log"
    con = ConsoleProgress(clock=FakeClock(), stream=out, log_path=log)
    con.emit("assess", "draft finding 1 (unverified): two\nlines\r\x07", "draft")
    printed = out.getvalue().splitlines()
    assert len(printed) == 1 and "DRAFT draft finding 1 (unverified): two lines" in printed[0]
    assert log.read_text(encoding="utf-8").count("\n") == 1
    assert one_line("a\tb c\x00") == "a b c"


def test_milestones_name_the_design_stages() -> None:
    assert set(MILESTONES) == {"intent", "plan", "merged", "verified"}
    sink = NullProgress()
    from sit_review_agent.progress import milestone

    milestone(sink, "intent", "understand", registry_entries=12)
    milestone(sink, "merged", "refine", findings=17, shards=4)
    msgs = [e.message for e in sink.events]
    assert msgs[0] == "milestone intent: intent ready, registry 12 entries"
    assert msgs[1] == "milestone merged: merged list ready, 17 findings from 4 shards"
    assert all(e.kind == "done" for e in sink.events)
