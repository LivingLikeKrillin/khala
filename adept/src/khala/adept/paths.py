"""Project-root discovery for the adept CLI.

A adept project root is the nearest ancestor directory (including the start dir)
that contains `adept.manifest.yaml`. The CLI anchors its three state files to the
discovered root so commands work from any subdirectory. This is a CLI concern —
the engine/registry stays root-agnostic unless explicitly given a root.
"""

from __future__ import annotations

from pathlib import Path

MANIFEST_NAME = "adept.manifest.yaml"
QUESTIONS_NAME = "adept.questions.json"
LEDGER_NAME = "adept.attempts.jsonl"


def discover_root(start: Path) -> Path | None:
    """Nearest ancestor (incl. start) containing adept.manifest.yaml, else None."""
    start = start.resolve()
    for d in [start, *start.parents]:
        if (d / MANIFEST_NAME).is_file():
            return d
    return None
