"""Project-root discovery for the ken CLI.

A ken project root is the nearest ancestor directory (including the start dir)
that contains `ken.manifest.yaml`. The CLI anchors its three state files to the
discovered root so commands work from any subdirectory. This is a CLI concern —
the engine/registry stays root-agnostic unless explicitly given a root.
"""

from __future__ import annotations

from pathlib import Path

MANIFEST_NAME = "ken.manifest.yaml"
QUESTIONS_NAME = "ken.questions.json"
LEDGER_NAME = "ken.attempts.jsonl"


def discover_root(start: Path) -> Path | None:
    """Nearest ancestor (incl. start) containing ken.manifest.yaml, else None."""
    start = start.resolve()
    for d in [start, *start.parents]:
        if (d / MANIFEST_NAME).is_file():
            return d
    return None
