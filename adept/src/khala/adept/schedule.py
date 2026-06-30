"""Pure spaced-repetition reducer — the single ledger->states derivation.

`rebuild` replays each question's attempts (in ts order) into a ReviewState; all
derivations (is_vouched, coverage) consume its output. No IO, no LLM, no wall-clock
at recompute — `now` is an explicit argument to `due`.

Ladder: [0, 1d, 3d, 7d, 30d] (rung 0 = due now). Pass advances one rung (capped at
the last); fail resets to rung 0 and increments the failure counter. next_due is
deterministic: last_attempt.ts + LADDER[interval_idx].
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from khala.adept.models import Attempt, ReviewState

LADDER = [
    timedelta(0),
    timedelta(days=1),
    timedelta(days=3),
    timedelta(days=7),
    timedelta(days=30),
]


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp into a tz-aware datetime.

    `datetime.fromisoformat` on 3.11+ accepts a trailing 'Z'. A naive timestamp
    (e.g. a hand-edited ledger line lacking an offset) is coerced to UTC so it is
    never subtracted against an aware datetime (which would raise TypeError and
    poison org-wide coverage).
    """
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def next_state(state: ReviewState | None, attempt: Attempt) -> ReviewState:
    """Fold one attempt into a question's state (used internally by `rebuild`)."""
    if state is None:
        interval_idx = 0
        fail_count = 0
    else:
        interval_idx = state.interval_idx
        fail_count = state.fail_count

    if attempt.passed:
        interval_idx = min(interval_idx + 1, len(LADDER) - 1)
    else:
        interval_idx = 0
        fail_count += 1

    return ReviewState(
        question_id=attempt.question_id,
        content_hash=attempt.content_hash,
        interval_idx=interval_idx,
        last_ts=attempt.ts,
        last_passed=attempt.passed,
        fail_count=fail_count,
    )


def rebuild(
    attempts: list[Attempt], *, current_hashes: dict[str, str]
) -> dict[str, ReviewState]:
    """Replay attempts into per-question states.

    Only attempts whose `question_id` is in `current_hashes` AND whose
    `content_hash` matches the question's current hash survive. Questions with no
    surviving attempts get NO state entry (caller treats absence as never-attempted
    = not vouched & due).
    """
    by_q: dict[str, list[Attempt]] = {}
    for a in attempts:
        cur = current_hashes.get(a.question_id)
        if cur is None or a.content_hash != cur:
            continue  # orphan question or stale-hash attempt
        by_q.setdefault(a.question_id, []).append(a)

    states: dict[str, ReviewState] = {}
    for qid, atts in by_q.items():
        state: ReviewState | None = None
        for a in sorted(atts, key=lambda x: _parse_ts(x.ts)):
            state = next_state(state, a)
        if state is not None:
            states[qid] = state
    return states


def next_due_at(state: ReviewState) -> datetime:
    """When this question is next due: last attempt ts + the rung's interval.

    Single public source for the expression `due` uses internally, so the two can
    never disagree. Returns a tz-aware datetime (naive last_ts coerced to UTC).
    """
    return _parse_ts(state.last_ts) + LADDER[state.interval_idx]


def due(states: dict[str, ReviewState], all_qids: list[str], *, now: str) -> list[str]:
    """Return the due question ids from the FULL question-id universe.

    A qid is due iff it is absent from `states` (never-attempted / stale-hash) OR
    `now >= last_ts + LADDER[interval_idx]`. `due` owns never-attempted surfacing —
    callers never re-derive it.
    """
    now_dt = _parse_ts(now)
    out: list[str] = []
    for qid in all_qids:
        st = states.get(qid)
        if st is None:
            out.append(qid)
            continue
        if now_dt >= next_due_at(st):
            out.append(qid)
    return out
