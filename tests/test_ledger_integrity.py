"""`scripts/ledger_integrity.py` — SPEC-nexus-retrieval-backstop-detector §5.

Zero failures over the real repository proves nothing on its own, so the boundary is pinned from
both sides: edits that **must** be flagged, and the one documented edit that must **not** be
(whitespace, which `hashing._normalize` folds by design). Pinning only the green half would let a
later widening of the normaliser hide more edits with every test still passing.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "arbiter" / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from khala.arbiter.hashing import content_hash  # noqa: E402

import ledger_integrity as li  # noqa: E402

BODY = """# A stamped artifact

It reports Recall@10 of 0.402 over the pack, with two  spaces above.

## A heading
"""


def _artifact(dirpath: Path, aid: str, status: str, body: str = BODY,
              stamp: str | None = "auto") -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    h = content_hash(body) if stamp == "auto" else stamp
    fm = [f"id: {aid}", "type: spec", f"title: {aid}", f"status: {status}"]
    if h is not None:
        fm.append(f"content_hash: {h}")
    p = dirpath / f"{aid}.md"
    p.write_text("---\n" + "\n".join(fm) + "\n---\n\n" + body, encoding="utf-8", newline="\n")
    return p


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    (tmp_path / "specs").mkdir()
    (tmp_path / "adr").mkdir()
    return tmp_path


def _run(repo: Path, manifest: Path | None = None):
    return li.check(repo, manifest or (repo / "nope.txt"))


def test_a_clean_repository_passes_and_reports_what_it_checked(repo: Path):
    _artifact(repo / "specs", "SPEC-a", "approved")
    _artifact(repo / "adr", "ADR-0001", "accepted")
    checked, mismatches, skipped, manifest = _run(repo)
    assert checked == 2
    assert mismatches == [] and manifest == []


@pytest.mark.parametrize("mutate, label", [
    (lambda b: b.replace("Recall", "Recakl"), "a single character"),
    (lambda b: b.replace("0.402", "0.502"), "a reported number"),
    (lambda b: b.replace("over the pack, ", ""), "a deleted phrase"),
    (lambda b: b.replace("two  spaces", "two spaces"), "an internal double space collapsed"),
    (lambda b: b.replace("## A heading", "## a heading"), "a heading's case"),
])
def test_substantive_edits_are_flagged(repo: Path, mutate, label):
    """The half that gives the job teeth. Each of these changes what the artifact says."""
    p = _artifact(repo / "specs", "SPEC-a", "approved")
    p.write_text(p.read_text(encoding="utf-8").replace(BODY, mutate(BODY)),
                 encoding="utf-8", newline="\n")
    _, mismatches, _, _ = _run(repo)
    assert len(mismatches) == 1, f"{label} was not flagged"
    assert "SPEC-a" in mismatches[0]


def test_whitespace_only_edits_are_not_flagged_by_design(repo: Path):
    """The documented blind spot, pinned so a widened normaliser shows up as this test's twin
    (the parametrised set above) going green when it should not."""
    p = _artifact(repo / "specs", "SPEC-a", "approved")
    p.write_text(p.read_text(encoding="utf-8").replace(BODY, BODY + "\n\n   \n"),
                 encoding="utf-8", newline="\n")
    _, mismatches, _, _ = _run(repo)
    assert mismatches == []


def test_an_approved_artifact_with_no_stamp_fails(repo: Path):
    _artifact(repo / "specs", "SPEC-a", "approved", stamp=None)
    _, mismatches, _, _ = _run(repo)
    assert len(mismatches) == 1 and "no content_hash" in mismatches[0]


def test_unstamped_statuses_are_out_of_scope(repo: Path):
    _artifact(repo / "specs", "SPEC-a", "in_review", stamp="sha256:deadbeef")
    _artifact(repo / "specs", "SPEC-b", "draft", stamp=None)
    checked, mismatches, _, _ = _run(repo)
    assert checked == 0 and mismatches == []


def test_a_malformed_artifact_is_named_not_silently_dropped(repo: Path):
    (repo / "specs" / "broken.md").write_text("no frontmatter here\n", encoding="utf-8")
    _, _, skipped, _ = _run(repo)
    assert any("broken.md" in s for s in skipped)


def test_the_manifest_catches_an_artifact_leaving_scope(repo: Path):
    """Bypasses (2) and (3): flipping `status` or deleting `id` removes a file from selection
    without touching the body hash. The manifest is what notices."""
    _artifact(repo / "specs", "SPEC-a", "approved")
    manifest = repo / "manifest.txt"
    manifest.write_text("# comment\nSPEC-a\nSPEC-gone\n", encoding="utf-8")

    _, _, _, failures = _run(repo, manifest)
    assert len(failures) == 1 and "SPEC-gone" in failures[0]

    # now demote the one that is present - the body and its stamp are untouched
    p = repo / "specs" / "SPEC-a.md"
    p.write_text(p.read_text(encoding="utf-8").replace("status: approved", "status: draft"),
                 encoding="utf-8", newline="\n")
    _, mismatches, _, failures = _run(repo, manifest)
    assert mismatches == [], "the body still matches; the demotion is the finding"
    assert any("SPEC-a" in f for f in failures)


def test_the_run_is_read_only(repo: Path):
    """`ledger.status()` rewrites a mismatched SPEC to `in_review` and saves it, so detection
    there edits the evidence. This job must not, and a refactor routing it back through
    `status()` has to fail here."""
    p = _artifact(repo / "specs", "SPEC-a", "approved")
    p.write_text(p.read_text(encoding="utf-8").replace("0.402", "0.502"),
                 encoding="utf-8", newline="\n")
    before = p.read_bytes()
    _, mismatches, _, _ = _run(repo)
    assert mismatches, "precondition: this run must have something to report"
    assert p.read_bytes() == before, "the run modified an artifact it was only asked to check"


def test_the_real_repository_is_clean():
    """No corpus size is pinned - that would go red on every legitimate addition and train
    maintainers to bump the number. The invariant is zero mismatches."""
    checked, mismatches, _, manifest_failures = li.check(ROOT, li.DEFAULT_MANIFEST)
    assert mismatches == [], mismatches
    assert manifest_failures == [], manifest_failures
    assert checked > 0, "the selector matched nothing - a broken glob would look like success"


def test_the_cli_exits_nonzero_on_a_mismatch(repo: Path):
    _artifact(repo / "specs", "SPEC-a", "approved")
    p = repo / "specs" / "SPEC-a.md"
    p.write_text(p.read_text(encoding="utf-8").replace("0.402", "0.502"),
                 encoding="utf-8", newline="\n")
    r = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts" / "ledger_integrity.py"),
         "--root", str(repo), "--manifest", str(repo / "nope.txt")],
        capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 1
    assert "MISMATCH" in r.stdout
