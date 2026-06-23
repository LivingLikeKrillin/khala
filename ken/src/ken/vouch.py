"""Vouch freshness (pure) and the fail-loud JSONL ledger.

`is_fresh` is a pure function — no IO. Persistence (record_vouch / load_vouches)
is fail-loud: a write that fails raises (a vouch is the product's core record and
is NEVER silently dropped — this is the deliberate deviation from nexus signals.py).
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ken.models import Vouch


def _parse_ts(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp into a tz-aware datetime.

    `datetime.fromisoformat` on 3.11+ accepts a trailing 'Z'. A naive timestamp
    (e.g. a hand-edited ledger line lacking an offset) is coerced to UTC so it is
    never subtracted against an aware datetime (which would raise TypeError and
    poison org-wide coverage). Both vouch.ts and `now` go through this parser.
    """
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_fresh(vouch: Vouch, *, current_hash: str, now: str, ttl_days: int) -> bool:
    """A vouch is fresh iff it passed, its hash matches the artifact's current
    hash, and it is within the TTL window."""
    if not vouch.passed:
        return False
    if vouch.content_hash != current_hash:
        return False
    return (_parse_ts(now) - _parse_ts(vouch.ts)) < timedelta(days=ttl_days)


def record_vouch(vouch: Vouch, *, ledger_path, make_parents: bool = True) -> None:
    """Append a vouch to the JSONL ledger. FAIL-LOUD: IO errors propagate.

    A vouch is the product's core record, so a failed write raises (OSError)
    rather than being silently swallowed. This is the deliberate deviation from
    nexus signals.py's fire-and-forget pattern.
    """
    path = Path(ledger_path)
    if make_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(vouch.to_dict()) + "\n")


def load_vouches(ledger_path) -> list[Vouch]:
    """Load all vouches from the JSONL ledger; returns [] if the file is absent."""
    path = Path(ledger_path)
    if not path.exists():
        return []
    vouches: list[Vouch] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            vouches.append(Vouch.from_dict(json.loads(line)))
    return vouches
