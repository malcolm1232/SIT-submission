"""Visible progress (runbook §5, robustness DEMO-15): one line per step and a heartbeat at least
every 10 s while waiting on a cold MCP server or a long streaming model call.

Lines look like ``[02:41] research | waking mcp-research-information (~90 s)``.

From the model's event stream (latency redesign W1, design section 4): :class:`CallTracker` prints one
status line at least every 10 s listing each open model call with its thinking-token estimate or its
streamed item count; :func:`draft_line` labels each finished item of a streamed answer as a draft,
unverified; :func:`milestone` names the stage milestones. Every line is one physical line
(:func:`one_line`): model text never brings a newline or a terminal control sequence to the console
or to ``progress.log``, and progress never writes to the structured logs (``llm.jsonl`` and the rest).
"""

from __future__ import annotations

import asyncio
import contextlib
import re
import sys
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol, TextIO

from sit_review_agent.clock import Clock, SystemClock

ProgressKind = Literal["step", "wait", "warn", "done", "draft"]

#: Control characters (C0, DEL, C1) and Unicode line and paragraph separators.
_CONTROL_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|[\x00-\x1f\x7f-\x9f\u2028\u2029]+")


def one_line(text: str) -> str:
    """``text`` as one terminal-safe line: ANSI sequences dropped, every other control character,
    newline and line separator replaced by a space, runs of spaces collapsed."""
    return re.sub(r" {2,}", " ", _CONTROL_RE.sub(lambda m: "" if m.group(0).startswith("\x1b[") else " ",
                                                 text)).strip()


@dataclass(frozen=True)
class ProgressEvent:
    phase: str
    message: str
    kind: ProgressKind = "step"
    elapsed_s: float = 0.0


class ProgressSink(Protocol):
    def emit(self, phase: str, message: str, kind: ProgressKind = "step") -> None:
        ...


@dataclass
class ConsoleProgress:
    """Prints progress lines to ``stream`` and mirrors them to ``log_path`` (``progress.log``)."""

    clock: Clock = field(default_factory=SystemClock)
    stream: TextIO = field(default_factory=lambda: sys.stderr)   # read at construction, not import
    log_path: Path | None = None
    events: list[ProgressEvent] = field(default_factory=list)
    _t0: float | None = None

    def emit(self, phase: str, message: str, kind: ProgressKind = "step") -> None:
        now = self.clock.monotonic()
        if self._t0 is None:
            self._t0 = now
        elapsed = now - self._t0
        ev = ProgressEvent(phase=phase, message=message, kind=kind, elapsed_s=elapsed)
        self.events.append(ev)
        mm, ss = divmod(int(elapsed), 60)
        marker = {"step": "", "wait": "... ", "warn": "WARN ", "done": "OK ", "draft": "DRAFT "}[kind]
        line = f"[{mm:02d}:{ss:02d}] {one_line(phase):<10} | {marker}{one_line(message)}"
        print(line, file=self.stream, flush=True)
        if self.log_path is not None:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")


@dataclass
class NullProgress:
    """Collects events without printing (tests)."""

    events: list[ProgressEvent] = field(default_factory=list)

    def emit(self, phase: str, message: str, kind: ProgressKind = "step") -> None:
        self.events.append(ProgressEvent(phase=phase, message=message, kind=kind))


@contextlib.asynccontextmanager
async def heartbeat(sink: ProgressSink, phase: str, describe: Callable[[], str], *,
                    clock: Clock, interval_s: float = 10.0) -> AsyncIterator[None]:
    """While the body runs, emit ``describe()`` as a ``wait`` line every ``interval_s`` seconds."""

    async def beat() -> None:
        while True:
            await clock.sleep(interval_s)
            sink.emit(phase, describe(), "wait")

    task = asyncio.create_task(beat())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


# ------------------------------------------------------------------------------ the event stream


@dataclass
class OpenCall:
    """One model call in flight, as the status line shows it."""

    call_id: str
    phase: str
    label: str = ""
    thinking_tokens: int = 0
    items: int = 0
    chars: int = 0

    def describe(self) -> str:
        name = f"{self.call_id} {self.phase}" + (f" {self.label}" if self.label else "")
        if self.items:
            return f"{name}: {self.items} items streamed ({self.chars:,} chars)"
        if self.chars:
            return f"{name}: answer streaming ({self.chars:,} chars)"
        if self.thinking_tokens:
            return f"{name}: thinking ~{self.thinking_tokens:,} tokens"
        return f"{name}: starting"


class CallTracker:
    """Open model calls of one gateway and their status line (design section 4: at least every
    10 s, each open call with its thinking-token estimate or its streamed item count).

    One ticker serves every concurrent call: it starts with the first open call and stops when the
    last one closes, so four assess shards give one line per interval, not four."""

    def __init__(self, sink: ProgressSink, clock: Clock, *, interval_s: float = 10.0) -> None:
        self.sink = sink
        self.clock = clock
        self.interval_s = interval_s
        self.calls: dict[str, OpenCall] = {}
        self._task: asyncio.Task[None] | None = None

    @property
    def ticking(self) -> bool:
        return self._task is not None and not self._task.done()

    def open(self, call_id: str, phase: str, label: str = "") -> None:
        self.calls[call_id] = OpenCall(call_id=call_id, phase=phase, label=label)
        if not self.ticking:
            try:
                self._task = asyncio.get_running_loop().create_task(self._tick())
            except RuntimeError:          # no running loop (a synchronous caller): no ticker
                self._task = None

    def update(self, call_id: str, *, thinking_tokens: int | None = None, items: int | None = None,
               chars: int | None = None) -> None:
        call = self.calls.get(call_id)
        if call is None:
            return
        if thinking_tokens is not None:
            call.thinking_tokens = thinking_tokens
        if items is not None:
            call.items = items
        if chars is not None:
            call.chars = chars

    def close(self, call_id: str) -> None:
        self.calls.pop(call_id, None)
        if not self.calls and self._task is not None:
            self._task.cancel()
            self._task = None

    def status_line(self) -> str | None:
        if not self.calls:
            return None
        n = len(self.calls)
        head = f"{n} open call{'s' if n != 1 else ''}"
        return head + ": " + "; ".join(c.describe() for c in self.calls.values())

    async def _tick(self) -> None:
        while True:
            await self.clock.sleep(self.interval_s)
            line = self.status_line()
            if line is None:
                return
            phases = {c.phase for c in self.calls.values()}
            self.sink.emit(phases.pop() if len(phases) == 1 else "model", line, "wait")


#: Singular names of the root-level lists a streamed answer finishes item by item.
_ITEM_NAMES = {"findings": "finding", "revisions": "revision", "questions": "question",
               "sound_areas": "sound area", "tool_calls": "tool call"}
#: Fields tried, in order, for the short text of a draft line.
_ITEM_TEXT_FIELDS = ("title", "question", "statement", "note", "why_sound", "finding_id", "id")


def draft_line(key: str, index: int, item: Any, *, call_id: str, phase: str, width: int = 110) -> str:
    """The progress line for item ``index`` of the streamed root-level list ``key``: labelled draft
    and unverified (it has not been through refine or verify), on one line."""
    name = _ITEM_NAMES.get(key, f"{key} item")
    text = ""
    if isinstance(item, dict):
        sev = item.get("severity")
        for f in _ITEM_TEXT_FIELDS:
            v = item.get(f)
            if isinstance(v, str) and v.strip():
                text = v
                break
        if isinstance(sev, str) and sev:
            text = f"[{sev}] {text}"
        action = item.get("action")
        if isinstance(action, str) and action:
            text = f"{text} ({action})" if text else action
    elif isinstance(item, str):
        text = item
    text = one_line(text)
    if len(text) > width:
        text = text[:width - 3].rstrip() + "..."
    head = f"draft {name} {index + 1} (unverified; {call_id} {phase})"
    return f"{head}: {text}" if text else head


#: Stage milestones shown live (design section 4: the intent and registry count at about 140 s,
#: the plan at about 110 s, the merged list at about 210 s, the verified report at about 445 s).
#: The orchestrator and phases (W2) call :func:`milestone` with these names.
MILESTONES: dict[str, str] = {
    "intent": "intent ready, registry {registry_entries} entries",
    "plan": "plan ready, {questions} research questions",
    "merged": "merged list ready, {findings} findings from {shards} shards",
    "verified": "verified report ready, {findings} findings",
}


def milestone(sink: ProgressSink | None, name: str, phase: str, **counts: Any) -> None:
    """Emit milestone ``name`` (a :data:`MILESTONES` key) with its counts as a ``done`` line."""
    if sink is None:
        return
    sink.emit(phase, f"milestone {name}: " + MILESTONES[name].format(**counts), "done")
