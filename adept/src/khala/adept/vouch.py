"""Derived vouch: an artifact is vouched iff none of its current questions are due.

`is_vouched` consumes the rebuilt per-question states and the spaced-repetition
schedule (`schedule.due`), so a vouch decays once any question is overdue for
re-test. Pure — `now` is an explicit argument. Caller invariant: `now` >= every
recorded attempt timestamp (production callers use wall-clock now).
"""

from __future__ import annotations

from ken.models import Question, ReviewState
from ken.schedule import due


def is_vouched(questions: list[Question], states: dict[str, ReviewState], *, now: str) -> bool:
    """True iff NONE of the artifact's current questions are due.

    `schedule.due` already treats never-attempted, failed (interval_idx resets to
    0 -> due immediately), and stale-hash (no state) questions as due. An artifact
    with no questions has no due questions -> vacuously vouched.
    """
    return not due(states, [q.id for q in questions], now=now)
