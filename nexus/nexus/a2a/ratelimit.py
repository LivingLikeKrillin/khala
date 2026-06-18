"""Per-principal rate limiting for the A2A surface (SPEC §21).

A small in-memory sliding-window limiter (no Redis — MVP constraint #8). Keyed per principal,
it gates skill execution *after* auth so one token cannot flood the surface — extending the
default-deny posture from access to volume. The clock is injected for deterministic tests.

In-process only: state does not survive a restart and is not shared across replicas. That is an
accepted MVP boundary — this is a coarse abuse backstop, not a distributed quota.
"""

from __future__ import annotations

import time
from collections.abc import Callable


class RateLimiter:
    """Sliding-window request log per key. ``max_per_window <= 0`` disables the limiter."""

    def __init__(
        self,
        max_per_window: int,
        window_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._max = max_per_window
        self._window = window_s
        self._clock = clock
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        """Record a hit for ``key`` and return whether it is within the window budget."""
        if self._max <= 0:
            return True  # disabled
        now = self._clock()
        cutoff = now - self._window
        bucket = [t for t in self._hits.get(key, []) if t >= cutoff]
        if len(bucket) >= self._max:
            self._hits[key] = bucket  # keep the pruned window; reject
            return False
        bucket.append(now)
        self._hits[key] = bucket
        return True
