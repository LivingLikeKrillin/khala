"""Classification clearance ordering — the single source of truth.

Mirrors the Postgres ``classification_level`` enum (``PUBLIC < INTERNAL < RESTRICTED``).
``base_filter`` compares ``classification <= clearance``; this module is the only place the
order lives on the Python side, so a test can assert parity with the SQL enum.
"""

from __future__ import annotations

# PUBLIC < INTERNAL < RESTRICTED. Keep in lockstep with the SQL ``classification_level`` enum.
ORDER: dict[str, int] = {"PUBLIC": 0, "INTERNAL": 1, "RESTRICTED": 2}
LEVELS: tuple[str, ...] = tuple(ORDER)


def parse(level: str | None) -> str | None:
    """Return a valid canonical level, or ``None`` for unknown/invalid input."""
    if level is None:
        return None
    norm = str(level).strip().upper()
    return norm if norm in ORDER else None


def floor_public(level: str | None) -> str:
    """Coerce any input to a valid level, flooring unknown/invalid input to ``PUBLIC``.

    Fail-safe: a typo (``"INTERNL"``) becomes ``PUBLIC``, never something higher, and never
    reaches the Postgres ``::classification_level`` cast (which would raise → 500).
    """
    return parse(level) or "PUBLIC"


def min_level(a: str, b: str) -> str:
    """Lower of two *valid* levels. Inputs must already be canonical (use ``floor_public``)."""
    return a if ORDER[a] <= ORDER[b] else b
