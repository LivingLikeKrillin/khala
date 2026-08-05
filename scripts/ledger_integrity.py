#!/usr/bin/env python
"""Recompute the stamped body hash of every approved governance artifact.

`SPEC-nexus-retrieval-backstop-detector` §3. Arbiter already implements this comparison
(`ledger.status()`); what was missing is that nothing runs it unattended — and that for SPECs
`ledger.status()` **rewrites the file**, resetting `status` to `in_review` and saving
(`ledger.py:73-77`), so detection there edits the evidence. This job therefore recomputes the
hash itself and never calls `status()`.

What it detects: **an edit that did not update the stamp.** What it does not detect, disclosed so a
green check is not read as covering it:

1. a body edit with the stamp recomputed in the same commit — `content_hash` is frontmatter, which
   the body hash does not cover;
2. `status: approved` → `draft`, which silently removes a file from scope;
3. deletion of the frontmatter `id`, which moves a file from checked to skipped.

(2) and (3) are why the manifest exists: every id it lists must still be present and selected.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "arbiter" / "src"))

from khala.arbiter.artifacts import Artifact  # noqa: E402

STAMPED = {"approved", "accepted"}
DEFAULT_MANIFEST = ROOT / "governance" / "integrity-manifest.txt"


def _artifacts(root: Path):
    """Yield (path, Artifact|None).

    A file that will not parse is reported, never skipped silently.
    """
    for d in ("specs", "adr"):
        for p in sorted((root / d).glob("*.md")):
            try:
                a = Artifact.load(p)
            except Exception:  # noqa: BLE001 — a malformed artifact is a finding, not a crash
                yield p, None
                continue
            yield p, (a if a.meta.get("id") else None)


def read_manifest(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def check(root: Path, manifest_path: Path) -> tuple[int, list[str], list[str], list[str]]:
    """Return (checked, mismatches, skipped, manifest_failures)."""
    checked = 0
    mismatches: list[str] = []
    skipped: list[str] = []
    selected: set[str] = set()

    for p, a in _artifacts(root):
        rel = p.relative_to(root).as_posix()
        if a is None:
            skipped.append(f"{rel} (unparseable or carries no id)")
            continue
        if a.meta.get("status") not in STAMPED:
            continue
        selected.add(a.meta["id"])
        checked += 1
        stored = a.meta.get("content_hash")
        if not stored:
            mismatches.append(f"{rel}: status={a.meta['status']} but no content_hash")
        elif a.recompute_hash() != stored:
            mismatches.append(f"{rel}: body no longer matches its stamp")

    manifest_failures = [f"{aid}: listed in the manifest but not selected (absent, unparseable, "
                         f"or status no longer approved/accepted)"
                         for aid in read_manifest(manifest_path) if aid not in selected]
    return checked, mismatches, skipped, manifest_failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--write-manifest", action="store_true",
                    help="rewrite the manifest from what is currently selected")
    args = ap.parse_args(argv)

    checked, mismatches, skipped, manifest_failures = check(args.root, args.manifest)

    if args.write_manifest:
        ids = sorted(a.meta["id"] for _, a in _artifacts(args.root)
                     if a is not None and a.meta.get("status") in STAMPED)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(
            "# Artifacts whose stamps ledger_integrity.py must keep checking.\n"
            "# A listed id that stops being selected fails the job - see the SPEC's\n"
            "# bypasses (2) and (3).\n"
            + "\n".join(ids) + "\n", encoding="utf-8", newline="\n")
        print(f"manifest rewritten: {len(ids)} ids")
        return 0

    print(f"checked {checked} approved/accepted artifacts")
    for s in skipped:
        print(f"  skipped: {s}")
    for m in mismatches:
        print(f"  MISMATCH {m}")
    for f in manifest_failures:
        print(f"  MANIFEST {f}")

    if mismatches or manifest_failures:
        print(f"\n✗ {len(mismatches)} mismatch(es), {len(manifest_failures)} manifest failure(s)")
        return 1
    print("✓ every stamped artifact still matches its body")
    return 0


if __name__ == "__main__":
    sys.exit(main())
