"""Attempt ledger — append-only JSONL. FAIL-LOUD.

One attempt = (person, artifact_id, question_id, content_hash, passed, score, ts).
Append-only: never mutates prior records. Per-question review state is recomputed
from this ledger via `schedule.rebuild` (single source of truth, no cached state).
"""

from __future__ import annotations

import json
from pathlib import Path

from khala.adept.models import Attempt


def append_attempt(
    attempt: Attempt, *, ledger_path: str | Path, make_parents: bool = True
) -> None:
    """Append one attempt to the JSONL ledger. FAIL-LOUD: IO errors propagate."""
    path = Path(ledger_path)
    if make_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(attempt.to_dict()) + "\n")


def load_attempts(ledger_path: str | Path) -> list[Attempt]:
    """Load all attempts from the JSONL ledger; returns [] if the file is absent."""
    path = Path(ledger_path)
    if not path.exists():
        return []
    attempts: list[Attempt] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            attempts.append(Attempt.from_dict(json.loads(line)))
    return attempts
