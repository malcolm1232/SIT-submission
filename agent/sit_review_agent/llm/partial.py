"""Incremental reading of ``claude -p --output-format stream-json`` (latency redesign W1, ADR-012 draft).

The CLI streams the structured answer as ``input_json_delta`` events of one ``StructuredOutput``
tool-use block (verified with Claude Code 2.1.288 on Haiku, ``tests/fixtures/stream/``). Two parts:

* :class:`JsonItemScanner` reads the growing JSON text one chunk at a time and reports every value
  of the answer's root object whose JSON has closed, and every finished item of a root-level array
  (an assess shard's finished findings while the array is still open). It never repairs or guesses:
  an item counts only once its closing bracket (or the separator after a scalar) has streamed.
* :class:`StreamParser` reads the event lines: the answer text (through the scanner), the input
  tokens of ``message_start``, the CLI's ``thinking_tokens`` estimates, the streamed characters and
  the last ``result`` event, which carries the same object ``--output-format json`` printed.

On a cut (run deadline or stage limit) the gateway raises
:class:`~sit_review_agent.errors.LLMDeadlineError` with :meth:`StreamParser.partial` and
:meth:`StreamParser.estimated_usage`. The estimate is never measured usage: the call's logged
``usage`` stays ``null`` with ``usage_unrecorded: deadline_cut`` (``docs/transcripts/session4/
accounting_fixes.md``) and the estimate is logged apart as ``estimated_usage`` with ``estimated: true``.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sit_review_agent.llm.gateway import Usage

#: Name of the tool-use block in which ``claude -p --json-schema`` streams the structured answer.
STRUCTURED_OUTPUT_TOOL = "StructuredOutput"
#: Characters of streamed answer JSON per output token, for the estimate of a cut call. Measured on
#: two finished Haiku answers on 2026-10-03 (``tests/fixtures/stream/haiku_short.jsonl`` and one
#: probe): ``input_json_delta`` characters over the visible output tokens (``output_tokens`` minus
#: ``output_tokens_details.thinking_tokens`` of the ``result`` event) gave 3.30 and 3.34. Those
#: answers were short, so the tool-call framing is in the count and a long answer likely runs at more
#: characters per token: the estimate leans high. The CLI's ``thinking_tokens`` events leaned high
#: too (320 and 417 estimated against 208 and 293 billed). UNVERIFIED on Opus.
JSON_CHARS_PER_TOKEN = 3.3
#: Characters kept of each CLI tool result that rejected an answer (its schema check's message).
REJECTION_TEXT_CHARS = 500

ItemCallback = Callable[[str, int, Any], None]


class RepeatedAnswer(Exception):  # noqa: N818 - a signal, not an error
    """Raised from :meth:`StreamParser.feed_line` when, after a complete answer the caller accepted,
    the CLI starts another API message: ``claude -p --json-schema`` checks each ``StructuredOutput``
    call against the schema and, when its own check rejects it, sends the rejection back as the tool
    result and the model writes the whole answer again in a new turn. The caller ends the call and
    uses the accepted answer (``StreamParser.accepted``)."""


# ------------------------------------------------------------------------------ the JSON scanner


@dataclass
class _Frame:
    kind: str                              # "{" or "["
    path: tuple[Any, ...]                  # keys and indexes from the document root to this container
    key: str | None = None                 # object: the key whose value is being read
    expect_key: bool = True                # object: the next string is a key
    start: int | None = None               # start of the value or item being read (buffer index)
    index: int = 0                         # array: items finished so far


class JsonItemScanner:
    """Finished values of a JSON object that is still streaming.

    ``root`` is the path of the object whose fields are reported: ``()`` for a plain answer,
    ``("final",)`` for the tool-calling envelope ``{"tool_calls": [...], "final": {...}}``. ``on_item``
    is called with ``(key, index, item)`` as each item of a root-level array closes."""

    def __init__(self, root: tuple[Any, ...] = (), on_item: ItemCallback | None = None) -> None:
        self.root = root
        self.on_item = on_item
        self._text = ""
        self._stack: list[_Frame] = []
        self._in_string = False
        self._escape = False
        self._string_start = 0
        self._values: dict[str, Any] = {}          # root fields whose JSON closed
        self._items: dict[str, list[Any]] = {}     # finished items of root-level arrays
        self._order: list[str] = []
        self.closed = False                         # the document's outermost object closed

    @property
    def chars(self) -> int:
        return len(self._text)

    @property
    def text(self) -> str:
        """The JSON text read so far."""
        return self._text

    def feed(self, chunk: str) -> None:
        base = len(self._text)
        self._text += chunk
        text = self._text
        for i in range(base, len(text)):
            self._step(text[i], i)

    # ---------------------------------------------------------------- state machine

    def _step(self, c: str, i: int) -> None:
        if self._in_string:
            if self._escape:
                self._escape = False
            elif c == "\\":
                self._escape = True
            elif c == '"':
                self._in_string = False
                top = self._stack[-1] if self._stack else None
                if top is not None and top.kind == "{" and top.expect_key and top.start is None:
                    try:
                        top.key = json.loads(self._text[self._string_start:i + 1])
                    except ValueError:
                        top.key = None
                    top.expect_key = False
            return
        if c in " \t\r\n:":
            return
        top = self._stack[-1] if self._stack else None
        if c == '"':
            self._in_string = True
            self._string_start = i
            if top is not None and not (top.kind == "{" and top.expect_key):
                self._begin(top, i)
            return
        if c in "{[":
            path: tuple[Any, ...] = ()
            if top is not None:
                self._begin(top, i)
                path = top.path + ((top.key,) if top.kind == "{" else (top.index,))
            self._stack.append(_Frame(kind=c, path=path))
            return
        if c in "}]":
            if top is None:
                return
            self._end_scalar(top, i)
            self._stack.pop()
            if not self._stack:
                self.closed = True
                return
            parent = self._stack[-1]
            if parent.start is not None:
                self._finish(parent, self._text[parent.start:i + 1])
            return
        if c == ",":
            if top is not None:
                self._end_scalar(top, i)
                if top.kind == "{":
                    top.expect_key = True
            return
        if top is not None:                 # a number, true, false or null starts or continues
            self._begin(top, i)

    def _begin(self, frame: _Frame, i: int) -> None:
        if frame.start is None:
            frame.start = i

    def _end_scalar(self, frame: _Frame, i: int) -> None:
        if frame.start is not None:
            self._finish(frame, self._text[frame.start:i].strip())

    def _finish(self, frame: _Frame, raw: str) -> None:
        """The value or item that started at ``frame.start`` closed with text ``raw``."""
        frame.start = None
        try:
            value = json.loads(raw)
        except ValueError:
            value, ok = None, False
        else:
            ok = True
        if frame.kind == "[":
            idx = frame.index
            frame.index += 1
            if ok and len(frame.path) == len(self.root) + 1 and frame.path[:-1] == self.root:
                key = frame.path[-1]
                if isinstance(key, str):
                    self._remember(key)
                    self._items.setdefault(key, []).append(value)
                    if self.on_item is not None:
                        self.on_item(key, idx, value)
        elif ok and frame.path == self.root and frame.key is not None:
            self._remember(frame.key)
            self._values[frame.key] = value
        if frame.kind == "{":
            frame.key = None

    def _remember(self, key: str) -> None:
        if key not in self._order:
            self._order.append(key)

    # ---------------------------------------------------------------- results

    def snapshot(self) -> dict[str, Any] | None:
        """The answer as far as it has closed: every finished root field, and for each root-level
        array still open, the items finished so far. ``None`` when nothing has closed."""
        out: dict[str, Any] = {}
        for key in self._order:
            if key in self._values:
                out[key] = self._values[key]
            elif key in self._items:
                out[key] = list(self._items[key])
        return out or None

    def item_count(self) -> int:
        """Finished items of root-level arrays (closed arrays included)."""
        snap = self.snapshot() or {}
        return sum(len(v) for v in snap.values() if isinstance(v, list))


# ------------------------------------------------------------------------------ the event stream


@dataclass
class StreamParser:
    """State of one ``claude -p`` attempt read from its ``stream-json`` lines.

    ``root`` is passed to the :class:`JsonItemScanner` of the structured answer. ``on_item`` is
    called for each finished root-level array item; ``on_event`` after every parsed line (the
    progress tracker reads the counters).

    Every complete answer block is kept in ``answers`` (parsed). ``accept`` decides whether a
    complete answer is usable (the gateway's own schema check); the first one it accepts is
    ``accepted``. With ``stop_on_repeat`` a new API message after the accepted answer raises
    :class:`RepeatedAnswer` (the CLI's schema check rejected an answer the gateway accepts, and the
    model is writing it again); ``accepted_usage`` is then the measured usage of the messages so far."""

    root: tuple[Any, ...] = ()
    on_item: ItemCallback | None = None
    on_event: Callable[[StreamParser], None] | None = None
    result: dict[str, Any] | None = None                 # the last ``result`` event
    message_usage: dict[str, Any] | None = None          # ``usage`` of the last ``message_start``
    thinking_tokens: int = 0                             # the CLI's last thinking-token estimate
    text_chars: int = 0                                  # streamed characters outside the answer JSON
    lines: int = 0
    non_json_lines: int = 0
    messages: int = 0
    accept: Callable[[dict[str, Any]], bool] | None = None
    stop_on_repeat: bool = False
    answers: list[dict[str, Any]] = field(default_factory=list)   # every complete answer block, in order
    accepted: dict[str, Any] | None = None               # the first complete answer ``accept`` took
    accepted_message: int = 0                            # the API message (1-based) that wrote it
    scanner: JsonItemScanner = field(init=False)
    _answer_block: int | None = field(default=None, init=False)
    _answer_open: bool = field(default=False, init=False)
    _message_usage: list[dict[str, Any]] = field(default_factory=list, init=False)   # usage of each API message
    #: The CLI's tool results for answers it did not take (``is_error``, or followed by another API
    #: message): the start of each text, so a rejection by the CLI's own schema check can be named.
    rejections: list[dict[str, Any]] = field(default_factory=list)
    _tool_result: dict[str, Any] | None = field(default=None, init=False)
    _pending: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.scanner = JsonItemScanner(self.root, self.on_item)

    # ---------------------------------------------------------------- input

    def feed_text(self, text: str) -> None:
        """Feed raw stdout (any chunking); complete lines are parsed, a trailing partial line waits."""
        data = self._pending + text
        *complete, self._pending = data.split("\n")
        for line in complete:
            self.feed_line(line)

    def flush(self) -> None:
        """Parse a last line that had no newline (the end of stdout)."""
        if self._pending:
            line, self._pending = self._pending, ""
            self.feed_line(line)

    def feed_line(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        self.lines += 1
        try:
            ev = json.loads(line)
        except ValueError:
            self.non_json_lines += 1
            return
        if not isinstance(ev, dict):
            self.non_json_lines += 1
            return
        self._event(ev)
        if self.on_event is not None:
            self.on_event(self)

    def _event(self, ev: dict[str, Any]) -> None:
        kind = ev.get("type")
        if kind == "result":
            self.result = ev
            return
        if kind == "user":
            self._user_event(ev)
            return
        if kind == "system" and ev.get("subtype") == "thinking_tokens":
            n = ev.get("estimated_tokens")
            if isinstance(n, int | float) and not isinstance(n, bool):
                self.thinking_tokens = max(self.thinking_tokens, int(n))
            return
        if kind != "stream_event":
            return
        inner = ev.get("event")
        if not isinstance(inner, dict):
            return
        etype = inner.get("type")
        if etype == "message_start":
            self.messages += 1
            msg = inner.get("message")
            usage = msg.get("usage") if isinstance(msg, dict) else None
            if isinstance(usage, dict):
                self.message_usage = usage
            self._message_usage.append(dict(usage) if isinstance(usage, dict) else {})
            if self._tool_result is not None:           # the CLI asked again after this tool result
                self.rejections.append(self._tool_result)
                self._tool_result = None
            if self.stop_on_repeat and self.accepted is not None and self.messages > self.accepted_message:
                raise RepeatedAnswer(f"API message {self.messages} started after the answer of message "
                                     f"{self.accepted_message} was accepted")
        elif etype == "message_delta":
            usage = inner.get("usage")
            if isinstance(usage, dict) and self._message_usage:
                self._message_usage[-1].update(usage)       # the message's final counts
        elif etype == "content_block_start":
            block = inner.get("content_block")
            if isinstance(block, dict) and block.get("type") == "tool_use" \
                    and block.get("name") == STRUCTURED_OUTPUT_TOOL:
                # A new answer block (the CLI may re-ask for schema-valid output): read it afresh.
                self._answer_block = inner.get("index")
                self._answer_open = True
                self.scanner = JsonItemScanner(self.root, self.on_item)
        elif etype == "content_block_stop":
            if self._answer_open and inner.get("index") == self._answer_block:
                self._answer_open = False
                self._answer_closed()
        elif etype == "content_block_delta":
            delta = inner.get("delta")
            if not isinstance(delta, dict):
                return
            dtype = delta.get("type")
            if dtype == "input_json_delta" and inner.get("index") == self._answer_block:
                part = delta.get("partial_json")
                if isinstance(part, str):
                    self.scanner.feed(part)
            elif dtype == "text_delta":
                text = delta.get("text")
                if isinstance(text, str):
                    self.text_chars += len(text)

    def _user_event(self, ev: dict[str, Any]) -> None:
        """A tool result the CLI wrote for an answer block."""
        msg = ev.get("message")
        content = msg.get("content") if isinstance(msg, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            body = block.get("content")
            if isinstance(body, list):
                body = " ".join(str(b.get("text", "")) for b in body if isinstance(b, dict))
            entry = {"is_error": block.get("is_error"), "text": str(body or "")[:REJECTION_TEXT_CHARS]}
            if block.get("is_error") is True:
                self.rejections.append(entry)
                self._tool_result = None
            else:
                self._tool_result = entry

    def _answer_closed(self) -> None:
        """The answer block's JSON is complete: keep it, and accept it if it is the first usable one."""
        try:
            data = json.loads(self.scanner.text)
        except ValueError:
            return
        if not isinstance(data, dict):
            return
        self.answers.append(data)
        if self.accepted is None and self.accept is not None and self.accept(data):
            self.accepted = data
            self.accepted_message = self.messages

    # ---------------------------------------------------------------- output

    def accepted_usage(self) -> Usage:
        """Measured usage of the API messages streamed so far: each message's ``message_delta``
        counts (or its ``message_start`` counts when it ended before its delta). For a call ended at
        :class:`RepeatedAnswer` this is the answering message in full plus the input of the message
        the CLI had just started; nothing is estimated."""
        total = Usage()
        for u in self._message_usage:
            def n(key: str, u: dict[str, Any] = u) -> int:
                v = u.get(key)
                return int(v) if isinstance(v, int | float) and not isinstance(v, bool) else 0

            total = total + Usage(n("input_tokens"), n("output_tokens"), n("cache_creation_input_tokens"),
                                  n("cache_read_input_tokens"))
        return total

    @property
    def answer_chars(self) -> int:
        return self.scanner.chars

    @property
    def started(self) -> bool:
        """The API message started (the call was sent and may be billed)."""
        return self.message_usage is not None

    def item_count(self) -> int:
        return self.scanner.item_count()

    def partial(self) -> dict[str, Any] | None:
        """What a cut attempt salvages (``LLMDeadlineError.partial``): finished root fields and the
        finished items of root-level arrays, or ``None``."""
        return self.scanner.snapshot()

    def estimated_usage(self) -> Usage | None:
        """Estimated usage of an attempt that ended without a ``result`` event: input tokens (and
        cache reads and writes) from ``message_start``; output tokens as the CLI's last thinking
        estimate plus the streamed characters at :data:`JSON_CHARS_PER_TOKEN`. ``None`` when no API
        message started. An ESTIMATE: never added to measured usage."""
        u = self.message_usage
        if u is None:
            return None

        def n(key: str) -> int:
            v = u.get(key)
            return int(v) if isinstance(v, int | float) and not isinstance(v, bool) else 0

        visible = math.ceil((self.answer_chars + self.text_chars) / JSON_CHARS_PER_TOKEN)
        output = max(n("output_tokens"), self.thinking_tokens + visible)
        return Usage(n("input_tokens"), output, n("cache_creation_input_tokens"), n("cache_read_input_tokens"))

    def estimate_basis(self) -> dict[str, Any]:
        """How :meth:`estimated_usage` was reached, for the log."""
        return {"thinking_tokens": self.thinking_tokens, "streamed_chars": self.answer_chars + self.text_chars,
                "chars_per_token": JSON_CHARS_PER_TOKEN}


def parse_cli_stdout(stdout: str, parser: StreamParser | None = None) -> tuple[dict[str, Any] | None, StreamParser]:
    """The CLI's final result object from complete stdout: the last ``result`` event of a stream,
    or the single JSON object of ``--output-format json`` (the harness judges and older recordings
    use it; the gateway itself always streams). ``parser`` may already hold the lines (fed live)."""
    p = parser if parser is not None else StreamParser()
    if parser is None:
        p.feed_text(stdout)
        p.flush()
    if p.result is not None:
        return p.result, p
    try:
        whole = json.loads(stdout)
    except ValueError:
        return None, p
    return (whole if isinstance(whole, dict) else None), p
