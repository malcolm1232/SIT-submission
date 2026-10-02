"""Injectable clock (robustness §5.1 "virtual clock").

Gateways, budgets, stop rules, the progress heartbeat and the watchdog read time only through a
:class:`Clock`, so fault scenarios with 90 s cold starts run in milliseconds under :class:`FakeClock`.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def monotonic(self) -> float:
        """Seconds from an arbitrary origin; only differences are meaningful."""
        ...

    def now_utc(self) -> datetime:
        """Timezone-aware wall-clock time."""
        ...

    async def sleep(self, seconds: float) -> None:
        ...


class SystemClock:
    """Real time."""

    def monotonic(self) -> float:
        return time.monotonic()

    def now_utc(self) -> datetime:
        return datetime.now(UTC)

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


class FakeClock:
    """Virtual time: ``sleep`` advances instantly. Start time is fixed for reproducible logs."""

    def __init__(self, start: datetime | None = None) -> None:
        self._start = start or datetime(2026, 10, 2, 9, 0, 0, tzinfo=UTC)
        self._elapsed = 0.0

    def monotonic(self) -> float:
        return self._elapsed

    def now_utc(self) -> datetime:
        return self._start + timedelta(seconds=self._elapsed)

    def advance(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("cannot move a FakeClock backwards")
        self._elapsed += seconds

    async def sleep(self, seconds: float) -> None:
        self.advance(max(0.0, seconds))
        await asyncio.sleep(0)


def isoformat_z(dt: datetime) -> str:
    """RFC 3339 UTC timestamp with a ``Z`` suffix and second precision (schema ``date-time``)."""
    return dt.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
