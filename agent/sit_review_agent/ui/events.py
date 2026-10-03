"""The progress event contract the page reads: ``runs/<id>/progress.jsonl`` as the agent writes it.

One JSON object per line, written by ``sit_review_agent.progress.ProgressJsonl`` beside
``progress.log`` and described by ``spec/progress_event.schema.json`` (the schema is the contract;
:data:`TYPES` repeats its ``type`` enum and ``tests/test_ui_events.py`` pins the two to each other).
The page never parses ``message``; it draws from ``type`` and ``fields`` only, and shows ``message``
verbatim in the status feed for the records that also printed a console line (``console``).

Line shape (every key required)::

    {"v": 1, "seq": 1, "t": 0.0, "run_s": null, "type": "run_started", "phase": "run",
     "kind": "step", "console": false, "message": "...", "fields": {...}}

* ``seq``: 1, 2, 3, ... in file order; the SSE id, so a reconnect resumes after the last one seen.
  A resumed run appends to the same file and continues the sequence.
* ``t``: seconds since the sink's first event (the ``[mm:ss]`` the console prints).
* ``run_s``: seconds on the run clock (resume-adjusted, the clock the stage limits use), or null
  before the run clock starts. The page draws elapsed time against a limit from ``run_s``.
* ``type``: one of :data:`TYPES`; ``status`` is a line with no data.
* ``kind``: ``step | wait | warn | done | draft``.
* ``console``: true when the record is also a console and ``progress.log`` line.

Fields the page reads, by type (``spec/progress_event.schema.json`` lists every required key):

``run_started``       run_id, run_dir, mode (``replay`` for ``dra replay``), resumed, profile, deadline_s,
                      stage_limits_s {stage_1_end, refine_end, verdict_end}, documents [{doc_id, role,
                      title, pages, ...}], shards [{index, name, criteria}]
``run_resuming``      run_id, start_at
``document_ingested`` role, title, pages, sections
``phase_started``     stage (the phase is the record's ``phase``)
``phase_done``        stage, seconds, stopped_at_limit, stage_closed
``phase_skipped``     stage, reason
``research_skipped``  reason
``research_doc_only`` detail, degradation_id
``call_opened``       call_id, stage, shard, shard_name, purpose, attempt, iteration
``call_status``       calls [{call_id, phase, label, thinking_tokens, items, chars}] (one record per tick)
``call_closed``       call_id, shard, outcome (ok | cut | refusal | truncated | error | cancelled |
                      interrupted | replaced), kept_items (a cut), wall_s, usage
``call_retry``        reason, stage
``draft_item``        item, list, index, call_id, shard, and for a finding severity, kind, title
``shard_drafted``     shard, shard_name, shards, call_id, findings, sound_areas, drafts [{index, kind,
                      severity, title}]
``shard_cut``         shard, shard_name, shards, call_id, cut_at_s, kept, kept_drafts, criteria_not_assessed,
                      degradation_id
``shard_failed``      shard, shard_name, shards, error, criteria
``shards_merged``     shards, findings, sound_areas, degraded_shards
``call_cut``          stage, call_id, at_s, kept_items, kept
``stop_rule``         code, detail, stage, to
``milestone``         name (intent, plan, merged, verified) and its counts
``verdict``           label, confidence, findings, unresolved, limitations
``run_error``         error, exit_code, resumable, resume
``run_finished``      run_id, outcome, exit_code, report_md, report_json, wall_s, cost_usd, cost_is_lower_bound
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: The record version this reader understands (``spec/progress_event.schema.json`` ``v``).
VERSION = 1
#: The schema's ``type`` enum, in its order (pinned to the schema file by ``tests/test_ui_events.py``).
TYPES = (
    "anchor_repair", "anchors_verified", "answer_incomplete", "answer_unusable", "assess_started", "call_bounded",
    "call_closed",
    "call_cut", "call_opened", "call_retry", "call_status", "citations_dropped", "cost_lower_bound",
    "deadline_warning", "declined", "document_ingested", "draft_item", "fault_injected", "fault_schedule",
    "heartbeat", "intent_ready", "interrupted", "mcp_warmup", "milestone", "not_assessed", "phase_done",
    "phase_skipped", "phase_started", "plan_approval", "plan_approval_waiting", "plan_criteria_added",
    "plan_criterion_skipped", "plan_only_stop", "plan_question", "plan_ready", "plan_started", "preflight",
    "refine_fallback", "refine_skipped", "refine_started", "refined", "registry_anchor", "report_written",
    "research_answer_ignored", "research_deadline", "research_doc_only", "research_evidence_ignored",
    "research_iteration", "research_skipped", "research_started", "research_stop_ignored", "research_stopped",
    "review_inputs_found", "revision_rejected", "run_dir", "run_error", "run_finished", "run_resuming",
    "run_started", "shard_cut", "shard_declined", "shard_drafted", "shard_failed", "shard_started",
    "shard_truncated", "shards_ended", "shards_kept", "shards_merged", "stage_limit_passed", "status",
    "stop_rule", "stopped_after_plan", "tool_round", "tool_status", "tools_down", "truncated_twice",
    "understand_started", "verdict",
)
KINDS = ("step", "wait", "warn", "done", "draft")
STARTED = "run_started"
FINISHED = "run_finished"
#: The terminal's marker before a message (``progress.ConsoleProgress``), shown in the status feed.
MARKERS = {"step": "", "wait": "... ", "warn": "WARN ", "done": "OK ", "draft": "DRAFT "}


def _is_number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def event_problems(ev: Any) -> list[str]:
    """Why ``ev`` is not a usable record (empty when it is). A type outside :data:`TYPES` is not a
    problem here: the record is passed through and the page ignores what it does not draw, so a
    type added to the agent later never makes the reader drop lines."""
    if not isinstance(ev, dict):
        return ["not a JSON object"]
    out: list[str] = []
    if ev.get("v") != VERSION:
        out.append(f"v is not {VERSION}")
    if not isinstance(ev.get("seq"), int) or isinstance(ev.get("seq"), bool) or ev["seq"] < 1:
        out.append("seq is not a positive integer")
    if not _is_number(ev.get("t")) or ev["t"] < 0:
        out.append("t is not a non-negative number")
    if ev.get("run_s") is not None and (not _is_number(ev.get("run_s")) or ev["run_s"] < 0):
        out.append("run_s is not a non-negative number or null")
    if not isinstance(ev.get("type"), str) or not ev["type"]:
        out.append("type is not a string")
    if not isinstance(ev.get("phase"), str):
        out.append("phase is not a string")
    if ev.get("kind") not in KINDS:
        out.append(f"kind {ev.get('kind')!r} is not one of {KINDS}")
    if not isinstance(ev.get("console"), bool):
        out.append("console is not a boolean")
    if not isinstance(ev.get("message"), str):
        out.append("message is not a string")
    if not isinstance(ev.get("fields"), dict):
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


def started(evs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The first ``run_started`` record's fields (a resumed run has a second one)."""
    return next((e["fields"] for e in evs if e.get("type") == STARTED), None)


def under_review(fields: dict[str, Any] | None) -> dict[str, Any]:
    """The document under review from a ``run_started`` record's ``documents``."""
    docs = (fields or {}).get("documents") or []
    docs = [d for d in docs if isinstance(d, dict)]
    return next((d for d in docs if d.get("role") == "under_review"), docs[0] if docs else {})


async def tail(path: Path, *, after_seq: int = 0, poll_s: float = 0.25,
               stop: Callable[[], bool] | None = None) -> AsyncIterator[dict[str, Any]]:
    """Yield the events of ``path`` above ``after_seq``, then follow the file as it grows, until a
    ``run_finished`` event is the last line of the file or ``stop()`` is true after a read that found
    nothing. A ``run_finished`` with lines after it is a failed run that was resumed (``dra resume``
    appends to the same file and continues the sequence), so the stream goes on."""
    offset = 0
    last = after_seq
    while True:
        res = read_new(path, offset)
        offset = res.offset
        for ev in res.events:
            if ev["seq"] > last:
                last = ev["seq"]
                yield ev
        if res.events and res.events[-1].get("type") == FINISHED:   # also when at or below after_seq
            return
        if not res.events and stop is not None and stop():
            return
        await asyncio.sleep(poll_s)


def sse_frame(ev: dict[str, Any]) -> str:
    """One server-sent event: the id is the sequence number (``Last-Event-ID`` on reconnect)."""
    return f"id: {ev['seq']}\nevent: progress\ndata: {json.dumps(ev, ensure_ascii=False, separators=(',', ':'))}\n\n"
