"""The progress event contract the page reads (docs/design/ui_design.md section 5).

One JSON object per line of ``runs/<id>/progress.jsonl``, written by the agent beside
``progress.log`` (workstream UI-W1). The page never parses ``message``; it draws from ``event``
and ``fields`` only, and shows ``message`` verbatim in the status feed (the terminal's line).

Line shape (keys this module relies on; extra keys are passed through untouched)::

    {"seq": 1, "t": 0.0, "phase": "run", "kind": "step", "message": "...",
     "event": "run started", "fields": {...}}

* ``seq``: 1, 2, 3, ... in file order; the SSE id, so a reconnect resumes after the last one seen.
* ``t``: seconds on the run clock (``ProgressEvent.elapsed_s``).
* ``kind``: ``step | wait | warn | done | draft`` (``progress.ProgressKind``).
* ``event``: a name from :data:`EVENTS`, or ``null`` for a plain status line.

``fields`` by event (all optional unless marked; the page shows what is present and nothing else):

``run started``     run_id*, argv, profile, deadline_s*, stage_limits_s {stage_1_end, refine_end,
                    verdict_end}*, document {doc_id, title, pages, sections}
``phase started``   phase*
``phase done``      phase*, seconds
``milestone``       name* (intent, plan, merged, verified) and its counts (registry_entries,
                    questions, findings, ...), text
``call opened``     call_id*, phase*, shard_index, shard_count, shard_name
``call status``     call_id*, phase*, thinking_tokens, items, chars (one per open call per tick)
``call closed``     call_id*, phase*, outcome (ok | cut | error | declined | truncated), kept_items
``draft``           call_id*, phase*, shard_index, shard_count, item (finding, revision, ...),
                    index, finding_kind, severity, title
``stage cut``       stage*, at_s*, call_id, kept (what the cut call kept)
``skipped``         phase*, degradation_id, reason
``stop rule``       code*, skip_to
``run finished``    outcome*, exit_code*, report_path

These names and keys are this workstream's reading of section 5; the integration pass joins them
with UI-W1's emitter (docs/transcripts/session4/ui_w2.md, "for the integration pass").
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EVENTS = ("run started", "phase started", "phase done", "milestone", "call opened", "call status",
          "call closed", "draft", "stage cut", "skipped", "stop rule", "run finished")
KINDS = ("step", "wait", "warn", "done", "draft")
FINISHED = "run finished"
#: The terminal's marker before a message (``progress.ConsoleProgress``), shown in the status feed.
MARKERS = {"step": "", "wait": "... ", "warn": "WARN ", "done": "OK ", "draft": "DRAFT "}


def event_problems(ev: Any) -> list[str]:
    """Why ``ev`` is not a usable event line (empty when it is)."""
    if not isinstance(ev, dict):
        return ["not a JSON object"]
    out: list[str] = []
    if not isinstance(ev.get("seq"), int) or isinstance(ev.get("seq"), bool) or ev["seq"] < 1:
        out.append("seq is not a positive integer")
    if not isinstance(ev.get("t"), int | float) or isinstance(ev.get("t"), bool):
        out.append("t is not a number")
    if not isinstance(ev.get("phase"), str):
        out.append("phase is not a string")
    if ev.get("kind") not in KINDS:
        out.append(f"kind {ev.get('kind')!r} is not one of {KINDS}")
    if not isinstance(ev.get("message"), str):
        out.append("message is not a string")
    name = ev.get("event")
    if name is not None and name not in EVENTS:
        out.append(f"event {name!r} is not a known event")
    if not isinstance(ev.get("fields", {}), dict):
        out.append("fields is not an object")
    return out


@dataclass
class ReadResult:
    events: list[dict[str, Any]]
    offset: int          # byte offset after the last complete line read
    bad_lines: int = 0


def read_new(path: Path, offset: int = 0, after_seq: int = 0) -> ReadResult:
    """The complete lines of ``path`` from byte ``offset`` whose ``seq`` is above ``after_seq``.
    A last line without its newline is left for the next read (the writer is mid-line)."""
    if not path.is_file():
        return ReadResult([], offset)
    with path.open("rb") as fh:
        fh.seek(offset)
        data = fh.read()
    end = data.rfind(b"\n")
    if end < 0:
        return ReadResult([], offset)
    events: list[dict[str, Any]] = []
    bad = 0
    for raw in data[:end].split(b"\n"):
        if not raw.strip():
            continue
        try:
            ev = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            bad += 1
            continue
        if event_problems(ev):
            bad += 1
            continue
        if ev["seq"] > after_seq:
            events.append(ev)
    return ReadResult(events, offset + end + 1, bad)


def read_all(path: Path) -> list[dict[str, Any]]:
    return read_new(path).events


async def tail(path: Path, *, after_seq: int = 0, poll_s: float = 0.25,
               stop: Callable[[], bool] | None = None) -> AsyncIterator[dict[str, Any]]:
    """Yield the events of ``path`` above ``after_seq``, then follow the file as it grows, until a
    ``run finished`` event has been yielded or ``stop()`` is true after a read that found nothing."""
    offset = 0
    last = after_seq
    while True:
        res = read_new(path, offset, last)
        offset = res.offset
        for ev in res.events:
            last = ev["seq"]
            yield ev
            if ev.get("event") == FINISHED:
                return
        if not res.events and stop is not None and stop():
            return
        await asyncio.sleep(poll_s)


def sse_frame(ev: dict[str, Any]) -> str:
    """One server-sent event: the id is the sequence number (``Last-Event-ID`` on reconnect)."""
    return f"id: {ev['seq']}\nevent: progress\ndata: {json.dumps(ev, ensure_ascii=False, separators=(',', ':'))}\n\n"
