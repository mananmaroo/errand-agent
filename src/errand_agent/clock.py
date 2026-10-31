"""A controllable clock so slot-expiry and timeouts are testable and reproducible."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Clock:
    """A fake monotonic clock measured in seconds from an arbitrary origin.

    Nothing in the system calls real wall-clock time for *logic* (expiry,
    budgets). Real time is used only for latency measurement in traces.
    """

    _now: float = 0.0

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds
