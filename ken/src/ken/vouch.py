"""Timestamp parsing for the schedule reducer.

v0's one-shot vouch (record_vouch / vouch_log / is_fresh) is superseded by the
attempt ledger + derived `is_vouched` (added in the derived-vouch task). What
remains here is `_parse_ts`, the tz-safe ISO-8601 parser used by `schedule.due`.
"""

from __future__ import annotations

from ken.models import Question, ReviewState


def is_vouched(questions: list[Question], states: dict[str, ReviewState]) -> bool:
    """A person vouches for an artifact iff EVERY current question has a state
    whose latest attempt passed.

    A question with no state (never-attempted, or all its attempts were against a
    stale hash and were dropped by `schedule.rebuild`) blocks the vouch. v1 has no
    calendar TTL — staleness is hash-change + fail-on-retest — so this takes no
    `now`. An artifact with no questions is vacuously vouched.
    """
    for q in questions:
        st = states.get(q.id)
        if st is None or not st.last_passed:
            return False
    return True
