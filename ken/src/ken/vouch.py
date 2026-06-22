"""Vouch freshness (pure) and the fail-loud JSONL ledger.

`is_fresh` is a pure function — no IO. Persistence (record_vouch / load_vouches)
is fail-loud: a write that fails raises (a vouch is the product's core record and
is NEVER silently dropped — this is the deliberate deviation from nexus signals.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ken.models import Vouch


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp into a tz-aware datetime.

    `datetime.fromisoformat` on 3.11+ accepts a trailing 'Z'. Both vouch.ts and
    `now` go through this same parser so both are tz-aware before subtracting.
    """
    return datetime.fromisoformat(ts)


def is_fresh(vouch: Vouch, *, current_hash: str, now: str, ttl_days: int) -> bool:
    """A vouch is fresh iff it passed, its hash matches the artifact's current
    hash, and it is within the TTL window."""
    if not vouch.passed:
        return False
    if vouch.content_hash != current_hash:
        return False
    return (_parse_ts(now) - _parse_ts(vouch.ts)) < timedelta(days=ttl_days)
