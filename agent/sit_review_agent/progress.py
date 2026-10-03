"""Visible progress (runbook §5, robustness DEMO-15): one line per step and a heartbeat at least
every 10 s while waiting on a cold MCP server or a long streaming model call.

Lines look like ``[02:41] research | waking mcp-research-information (~90 s)``.

From the model's event stream (latency redesign W1, design section 4): :class:`CallTracker` prints one
status line at least every 10 s listing each open model call with its thinking-token estimate or its
streamed item count; :func:`draft_line` labels each finished item of a streamed answer as a draft,
unverified; :func:`milestone` names the stage milestones. Every line is one physical line
(:func:`one_line`): model text never brings a newline or a terminal control sequence to the console
or to ``progress.log``, and progress never writes to the structured logs (``llm.jsonl`` and the rest).

Structured events (UI design note section 5, workstream UI-W1): every event also has a type
(``ProgressEvent.event``, ``"status"`` for a plain line) and a ``fields`` dict filled at the emit
sites that carry data, so a reader never parses the message. :func:`emit_event` and
:func:`ctx_event` emit a console line with its fields; :func:`record_event` writes an event that
has no console line (``run_started``, ``call_opened``, ``call_closed``, ``run_finished``), so the
console and ``progress.log`` stay byte for byte what they were. A sink with ``jsonl_path`` appends
one JSON object per event to ``progress.jsonl`` (:class:`ProgressJsonl`; schema in
``spec/progress_event.schema.json`` and ``agent/README.md``), flushed per event so a reader can tail
it live. The JSONL never carries model prose: a console line that quotes model text (a plan
question, a non-finding draft item, an error message) is written there with a ``public`` message
built from codes and counts only, and a draft finding keeps only its title and severity.
:class:`CallEventsGateway` is the LLM layer that emits ``call_opened`` and ``call_closed`` for every
model call, whatever the backend.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import re
import sys
from collections.abc import AsyncIterator, Callable, Mapping
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


#: Version of the ``progress.jsonl`` record (``v``); ``spec/progress_event.schema.json`` describes it.
EVENT_SCHEMA_VERSION = 1
#: File name of the structured progress stream, beside ``progress.log`` in the run directory.
PROGRESS_JSONL = "progress.jsonl"


@dataclass(frozen=True)
class ProgressEvent:
    phase: str
    message: str
    kind: ProgressKind = "step"
    elapsed_s: float = 0.0
    #: The event type (``spec/progress_event.schema.json``); ``"status"`` for a line without data.
    event: str = "status"
    #: The event's data, filled at the emit site (call ID, stage, shard, counts, severity, ...).
    fields: Mapping[str, Any] = field(default_factory=dict)
    #: ``False`` for an event that has no console line (``record_event``).
    console: bool = True
    #: The message written to ``progress.jsonl`` when the console line quotes model text.
    public: str | None = None
    #: Run-clock seconds when the event was emitted (``None`` before the run clock starts).
    run_s: float | None = None


class ProgressSink(Protocol):
    def emit(self, phase: str, message: str, kind: ProgressKind = "step") -> None:
        ...


def _json_safe(v: Any) -> Any:
    """``v`` as JSON values: mappings, lists and scalars kept, anything else as its string."""
    if isinstance(v, Mapping):
        return {str(k): _json_safe(x) for k, x in v.items()}
    if isinstance(v, list | tuple | set | frozenset):
        return [_json_safe(x) for x in v]
    if v is None or isinstance(v, bool | int | str):
        return v
    if isinstance(v, float):
        return round(v, 3)
    value = getattr(v, "value", None)          # an enum
    return value if isinstance(value, str) else str(v)


class ProgressJsonl:
    """Appends one JSON object per event to ``path`` (``progress.jsonl``), opened and closed per
    event so every line is on disk when :meth:`write` returns (a reader can tail the file). A
    resumed run appends to the same file and continues its sequence numbers."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._seq: int | None = None

    def _next_seq(self) -> int:
        if self._seq is None:
            self._seq = 0
            if self.path.is_file():
                with open(self.path, encoding="utf-8") as fh:
                    self._seq = sum(1 for line in fh if line.strip())
        self._seq += 1
        return self._seq

    def record(self, ev: ProgressEvent) -> dict[str, Any]:
        return {"v": EVENT_SCHEMA_VERSION, "seq": self._next_seq(), "t": round(ev.elapsed_s, 3),
                "run_s": None if ev.run_s is None else round(ev.run_s, 3), "type": ev.event,
                "phase": one_line(ev.phase), "kind": ev.kind, "console": ev.console,
                "message": one_line(ev.public if ev.public is not None else ev.message),
                "fields": _json_safe(dict(ev.fields))}

    def write(self, ev: ProgressEvent) -> None:
        line = json.dumps(self.record(ev), ensure_ascii=False, separators=(",", ":"))
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")


@dataclass
class ConsoleProgress:
    """Prints progress lines to ``stream`` and mirrors them to ``log_path`` (``progress.log``);
    with ``jsonl_path``, also writes every event, with its type and fields, to ``progress.jsonl``.

    ``events`` holds the events that printed a line (as before); ``records`` holds every event,
    including those without a console line. ``run_clock`` (bound by the orchestrator with
    :func:`bind_run_clock` when the run clock starts) gives each event its run-clock offset."""

    clock: Clock = field(default_factory=SystemClock)
    stream: TextIO = field(default_factory=lambda: sys.stderr)   # read at construction, not import
    log_path: Path | None = None
    events: list[ProgressEvent] = field(default_factory=list)
    _t0: float | None = None
    jsonl_path: Path | None = None
    records: list[ProgressEvent] = field(default_factory=list)
    run_clock: Callable[[], float] | None = None
    _jsonl: ProgressJsonl | None = None

    def emit(self, phase: str, message: str, kind: ProgressKind = "step") -> None:
        self.emit_event(phase, message, kind)

    def emit_event(self, phase: str, message: str, kind: ProgressKind = "step", event: str = "status",
                   fields: Mapping[str, Any] | None = None, *, console: bool = True,
                   public: str | None = None) -> None:
        now = self.clock.monotonic()
        if self._t0 is None:
            self._t0 = now
        elapsed = now - self._t0
        ev = ProgressEvent(phase=phase, message=message, kind=kind, elapsed_s=elapsed, event=event,
                           fields=dict(fields or {}), console=console, public=public, run_s=_run_s(self.run_clock))
        self.records.append(ev)
        if console:
            self.events.append(ev)
            mm, ss = divmod(int(elapsed), 60)
            marker = {"step": "", "wait": "... ", "warn": "WARN ", "done": "OK ", "draft": "DRAFT "}[kind]
            line = f"[{mm:02d}:{ss:02d}] {one_line(phase):<10} | {marker}{one_line(message)}"
            print(line, file=self.stream, flush=True)
            if self.log_path is not None:
                with open(self.log_path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
        if self.jsonl_path is not None:
            if self._jsonl is None or self._jsonl.path != Path(self.jsonl_path):
                self._jsonl = ProgressJsonl(self.jsonl_path)
            self._jsonl.write(ev)


@dataclass
class NullProgress:
    """Collects events without printing (tests). ``events`` holds the events that have a console
    line, ``records`` every event; ``jsonl_path`` and ``run_clock`` work as in :class:`ConsoleProgress`."""

    events: list[ProgressEvent] = field(default_factory=list)
    records: list[ProgressEvent] = field(default_factory=list)
    jsonl_path: Path | None = None
    run_clock: Callable[[], float] | None = None
    clock: Clock | None = None
    _jsonl: ProgressJsonl | None = None
    _t0: float | None = None

    def emit(self, phase: str, message: str, kind: ProgressKind = "step") -> None:
        self.emit_event(phase, message, kind)

    def emit_event(self, phase: str, message: str, kind: ProgressKind = "step", event: str = "status",
                   fields: Mapping[str, Any] | None = None, *, console: bool = True,
                   public: str | None = None) -> None:
        elapsed = 0.0
        if self.clock is not None:
            now = self.clock.monotonic()
            if self._t0 is None:
                self._t0 = now
            elapsed = now - self._t0
        ev = ProgressEvent(phase=phase, message=message, kind=kind, elapsed_s=elapsed, event=event,
                           fields=dict(fields or {}), console=console, public=public, run_s=_run_s(self.run_clock))
        self.records.append(ev)
        if console:
            self.events.append(ev)
        if self.jsonl_path is not None:
            if self._jsonl is None or self._jsonl.path != Path(self.jsonl_path):
                self._jsonl = ProgressJsonl(self.jsonl_path)
            self._jsonl.write(ev)


def _run_s(run_clock: Callable[[], float] | None) -> float | None:
    if run_clock is None:
        return None
    try:
        return max(0.0, float(run_clock()))
    except Exception:  # noqa: BLE001 - a clock read must never fail a progress line
        return None


def emit_event(sink: ProgressSink | None, phase: str, message: str, kind: ProgressKind = "step", *,
               event: str, public: str | None = None, data: Mapping[str, Any] | None = None,
               **fields: Any) -> None:
    """Emit ``message`` as before, with its event type and fields (``data`` and the keywords) for
    sinks that keep them (``ConsoleProgress``, ``NullProgress``); any other sink gets the plain
    line. ``public`` replaces the message in ``progress.jsonl`` when the line quotes model text."""
    if sink is None:
        return
    fn = getattr(sink, "emit_event", None)
    if callable(fn):
        fn(phase, message, kind, event, {**(data or {}), **fields}, public=public)
    else:
        sink.emit(phase, message, kind)


def record_event(sink: ProgressSink | None, phase: str, event: str, summary: str, *, kind: ProgressKind = "step",
                 data: Mapping[str, Any] | None = None, **fields: Any) -> None:
    """An event with no console line (``progress.jsonl`` and ``records`` only): the console and
    ``progress.log`` are unchanged by it. ``summary`` is built by code, never from model text."""
    fn = getattr(sink, "emit_event", None) if sink is not None else None
    if callable(fn):
        fn(phase, summary, kind, event, {**(data or {}), **fields}, console=False)


def ctx_event(ctx: Any, message: str, kind: ProgressKind = "step", *, event: str, public: str | None = None,
              data: Mapping[str, Any] | None = None, **fields: Any) -> None:
    """:meth:`RunContext.emit` with an event type and fields (same phase rule: the context's current
    phase, else ``run``)."""
    state = getattr(ctx, "state", None)
    current = getattr(state, "current_phase", None)
    phase = current.value if current is not None else "run"
    emit_event(ctx.progress, phase, message, kind, event=event, public=public, data=data, **fields)


#: A tool gateway's policy refusal line; its reason can quote the model's arguments (a URL, a query).
_BLOCKED_RE = re.compile(r"^blocked (\S+?): ")


class ToolProgress:
    """The sink the tool gateways write to: each of their lines goes to ``sink`` unchanged, typed
    ``tool_status``, and a policy refusal (``blocked <tool>: <reason>``) reaches ``progress.jsonl``
    without its reason, which can quote the model's request."""

    def __init__(self, sink: ProgressSink) -> None:
        self.sink = sink

    def emit(self, phase: str, message: str, kind: ProgressKind = "step") -> None:
        m = _BLOCKED_RE.match(message)
        public = f"blocked {m.group(1)} by the tool policy" if m else None
        emit_event(self.sink, phase, message, kind, event="tool_status", public=public,
                   tool=m.group(1) if m else None, blocked=bool(m))


def bind_run_clock(sink: ProgressSink | None, run_clock: Callable[[], float]) -> None:
    """Give ``sink`` the run clock (seconds since the run started, resume-adjusted) for ``run_s``."""
    if sink is not None and hasattr(sink, "run_clock"):
        sink.run_clock = run_clock  # type: ignore[attr-defined]


@contextlib.asynccontextmanager
async def heartbeat(sink: ProgressSink, phase: str, describe: Callable[[], str], *,
                    clock: Clock, interval_s: float = 10.0) -> AsyncIterator[None]:
    """While the body runs, emit ``describe()`` as a ``wait`` line every ``interval_s`` seconds."""

    async def beat() -> None:
        while True:
            await clock.sleep(interval_s)
            emit_event(sink, phase, describe(), "wait", event="heartbeat")

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
            emit_event(self.sink, phases.pop() if len(phases) == 1 else "model", line, "wait", event="call_status",
                       calls=[{"call_id": c.call_id, "phase": c.phase, "label": c.label,
                               "thinking_tokens": c.thinking_tokens, "items": c.items, "chars": c.chars}
                              for c in self.calls.values()])


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


#: Keys of a streamed item that ``progress.jsonl`` may carry: codes and enums, never model prose.
#: A finding's ``title`` is the one text field kept (UI design note section 5).
_PUBLIC_ITEM_KEYS = ("id", "finding_id", "severity", "kind", "action", "disposition", "category")


def _public_item(key: str, item: Any) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    out = {k: item[k] for k in _PUBLIC_ITEM_KEYS if isinstance(item.get(k), str) and item[k]}
    if key == "findings" and isinstance(item.get("title"), str) and item["title"].strip():
        out["title"] = item["title"]
    return out


def draft_event(key: str, index: int, item: Any, *, call_id: str, phase: str, shard: int | None = None,
                width: int = 110) -> tuple[str, dict[str, Any]]:
    """The ``progress.jsonl`` message and fields of the draft line of :func:`draft_line`: the same
    line built from the item's codes (and a finding's title) only, and the fields ``item``,
    ``list``, ``index`` (1-based), ``call_id``, ``shard`` and the item's ``severity``, ``title``,
    ``kind``, ``action`` and IDs when it has them."""
    pub = _public_item(key, item)
    fields: dict[str, Any] = {"item": _ITEM_NAMES.get(key, f"{key} item"), "list": key, "index": index + 1,
                              "call_id": call_id, "shard": shard}
    for k, v in pub.items():
        fields[k] = one_line(v)[:width] if k == "title" else v
    return draft_line(key, index, pub, call_id=call_id, phase=phase, width=width), fields


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
    emit_event(sink, phase, f"milestone {name}: " + MILESTONES[name].format(**counts), "done", event="milestone",
               name=name, **counts)


# ------------------------------------------------------------------------------ call events


@dataclass
class _PendingCall:
    """One logical model call in flight through a :class:`CallEventsGateway`."""

    owner: Any
    request: Any
    t0: float
    call_id: str | None = None
    attempt: int = 0


#: The logical call the current task is making (each asyncio task has its own copy).
_CURRENT_CALL: contextvars.ContextVar[_PendingCall | None] = contextvars.ContextVar("progress_call", default=None)


def _usage_dict(usage: Any) -> dict[str, int] | None:
    if usage is None:
        return None
    raw = usage if isinstance(usage, Mapping) else getattr(usage, "__dict__", None)
    if not isinstance(raw, Mapping):
        return None
    return {str(k): int(v) for k, v in raw.items() if isinstance(v, int) and not isinstance(v, bool)}


def _kept(partial: Any) -> dict[str, int]:
    """Finished items per list field of a cut call's salvaged answer."""
    if not isinstance(partial, Mapping):
        return {}
    return {str(k): len(v) for k, v in partial.items() if isinstance(v, list)}


class CallEventsGateway:
    """The outermost LLM layer of a run: emits ``call_opened`` when the backend gives a logical
    call its ID and ``call_closed`` when the call returns or raises, for every backend (no console
    line; ``progress.jsonl`` only). Everything else is the inner gateway's (attributes are read
    through), so the layer changes no request, result, ID or log entry.

    The ID is the backend's: the layer hooks ``next_call_id`` on every layer below it that numbers
    calls (``AnthropicGateway``, ``ClaudeCodeGateway``, ``FakeGateway``; ``FaultInjectingLLMGateway``
    borrows its inner's), and the hook names the call of the task that asked, so concurrent calls
    are never confused. A backend that takes its IDs from elsewhere (``ReplayLLMGateway`` serves the
    recorded ones) gets its ``call_opened`` when the call ends, just before ``call_closed``. When
    one logical call is given a second ID (a fault-injector retry), the first is closed with outcome
    ``replaced`` and the second opened with the next ``attempt``."""

    def __init__(self, inner: Any, sink: ProgressSink | None, clock: Clock, *,
                 shard_names: Callable[[], list[str]] | None = None) -> None:
        self.inner = inner
        self.sink = sink
        self.clock = clock
        self.shard_names = shard_names
        self._hook_call_ids()

    def __getattr__(self, name: str) -> Any:
        if name == "inner":
            raise AttributeError(name)
        return getattr(self.inner, name)

    def _hook_call_ids(self) -> None:
        seen: set[int] = set()
        layer = self.inner
        while layer is not None and id(layer) not in seen:
            seen.add(id(layer))
            fn = getattr(layer, "next_call_id", None)
            if callable(fn) and getattr(fn, "__self__", None) is layer and not getattr(fn, "_call_events", False):
                layer.next_call_id = self._hooked(fn)
            layer = getattr(layer, "inner", None)

    def _hooked(self, original: Callable[[], str]) -> Callable[[], str]:
        def next_call_id() -> str:
            call_id = original()
            pending = _CURRENT_CALL.get()
            if pending is not None and pending.owner is self:
                self._opened(pending, call_id)
            return call_id

        next_call_id._call_events = True  # type: ignore[attr-defined]
        return next_call_id

    # -- what a call is
    def _describe(self, pending: _PendingCall) -> dict[str, Any]:
        from sit_review_agent.llm.gateway import assess_shard_index
        from sit_review_agent.states import PhaseName, stage_of

        req = pending.request
        phase = getattr(getattr(req, "phase", None), "value", str(getattr(req, "phase", "")))
        try:
            stage = stage_of(PhaseName(phase)).value
        except (ValueError, StopIteration):
            stage = None
        shard = assess_shard_index(getattr(req, "conversation_id", None))
        name = None
        if shard is not None and self.shard_names is not None:
            try:
                names = list(self.shard_names())
                name = names[shard - 1] if 0 < shard <= len(names) else None
            except Exception:  # noqa: BLE001 - a label must never fail a call
                name = None
        return {"call_id": pending.call_id, "stage": stage, "shard": shard, "shard_name": name,
                "purpose": getattr(req, "purpose", None), "attempt": pending.attempt,
                "iteration": getattr(req, "iteration", None)}

    def _phase(self, pending: _PendingCall) -> str:
        p = getattr(pending.request, "phase", None)
        return str(getattr(p, "value", p or "model"))

    def _opened(self, pending: _PendingCall, call_id: str) -> None:
        if pending.call_id == call_id:
            return
        if pending.call_id is not None:                 # a second ID for the same logical call
            self._emit_closed(pending, outcome="replaced", error=None, usage=None)
            pending.attempt += 1
        pending.call_id = call_id
        pending.t0 = self.clock.monotonic()
        d = self._describe(pending)
        record_event(self.sink, self._phase(pending), "call_opened", f"{call_id} opened", data=d)

    def _emit_closed(self, pending: _PendingCall, *, outcome: str, error: str | None, usage: Any,
                     kind: ProgressKind = "step", **extra: Any) -> None:
        d = self._describe(pending)
        used = _usage_dict(usage)
        d.update({"outcome": outcome, "error": error, "wall_s": round(max(0.0, self.clock.monotonic() - pending.t0), 3),
                  "usage": used, "usage_status": "measured" if used is not None else "unknown", **extra})
        record_event(self.sink, self._phase(pending), "call_closed", f"{pending.call_id} closed: {outcome}",
                     kind=kind, data=d)

    def _closed(self, pending: _PendingCall, *, result: Any = None, exc: BaseException | None = None) -> None:
        call_id = getattr(result, "call_id", None) if exc is None else getattr(exc, "call_id", None)
        if pending.call_id is None:
            if not call_id:
                return                                  # nothing was opened (no ID was ever given)
            self._opened(pending, str(call_id))
        if exc is None:
            attempts = getattr(result, "attempts", None)
            self._emit_closed(pending, outcome="ok", error=None, usage=getattr(result, "usage", None), kind="done",
                              stop_reason=getattr(result, "stop_reason", None), model=getattr(result, "model", None),
                              attempts=len(attempts) if isinstance(attempts, list) else None,
                              resumed=bool(getattr(result, "resumed", False)))
            return
        from sit_review_agent.errors import LLMDeadlineError, LLMRefusalError, LLMTruncatedError

        extra: dict[str, Any] = {}
        if isinstance(exc, LLMDeadlineError):
            outcome = "cut"
            kept = _kept(exc.partial)
            extra = {"kept_items": exc.salvaged_items, "kept": kept,
                     "estimated_usage": _usage_dict(exc.estimated_usage)}
        elif isinstance(exc, LLMRefusalError):
            outcome = "refusal"
        elif isinstance(exc, LLMTruncatedError):
            outcome = "truncated"
        elif isinstance(exc, asyncio.CancelledError):
            outcome = "cancelled"
        elif isinstance(exc, KeyboardInterrupt):
            outcome = "interrupted"
        else:
            outcome = "error"
        self._emit_closed(pending, outcome=outcome, error=type(exc).__name__, usage=getattr(exc, "usage", None),
                          kind="warn", **extra)

    async def call(self, request: Any) -> Any:
        pending = _PendingCall(owner=self, request=request, t0=self.clock.monotonic())
        token = _CURRENT_CALL.set(pending)
        try:
            result = await self.inner.call(request)
        except BaseException as exc:
            self._closed(pending, exc=exc)
            raise
        finally:
            _CURRENT_CALL.reset(token)
        self._closed(pending, result=result)
        return result
