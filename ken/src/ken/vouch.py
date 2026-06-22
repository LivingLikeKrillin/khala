"""Timestamp parsing for the schedule reducer.

v0's one-shot vouch (record_vouch / vouch_log / is_fresh) is superseded by the
attempt ledger + derived `is_vouched` (added in the derived-vouch task). What
remains here is `_parse_ts`, the tz-safe ISO-8601 parser used by `schedule.due`.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp into a tz-aware datetime.

    `datetime.fromisoformat` on 3.11+ accepts a trailing 'Z'. A naive timestamp
    (e.g. a hand-edited ledger line lacking an offset) is coerced to UTC so it is
    never subtracted against an aware datetime (which would raise TypeError and
    poison org-wide coverage).
    """
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
