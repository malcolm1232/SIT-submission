"""Visible progress (runbook §5, robustness DEMO-15): one line per step and a heartbeat at least
every 10 s while waiting on a cold MCP server or a long streaming model call.

Lines look like ``[02:41] research | waking mcp-research-information (~90 s)``.
"""

from __future__ import annotations

import asyncio
import contextlib
import sys
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, TextIO

from sit_review_agent.clock import Clock, SystemClock

ProgressKind = Literal["step", "wait", "warn", "done"]


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
        marker = {"step": "", "wait": "... ", "warn": "WARN ", "done": "OK "}[kind]
        line = f"[{mm:02d}:{ss:02d}] {phase:<10} | {marker}{message}"
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
