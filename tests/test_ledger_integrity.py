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


# ── open items carried by frozen records (debt I-006) ────────────────────────


def _items(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "open-items.yaml"
    p.write_text(body, encoding="utf-8")
    return p


_GOOD = """
- id: x
  source: ADR-0009 row 1
  owner: someone
  state: open
  what: a thing
  trigger: any SPEC whose linked_adrs contains ADR-0008 must say whether it addresses this
  checked_by: scripts/ledger_integrity.py
"""


def test_the_real_open_items_file_is_well_formed():
    assert li.check_open_items(ROOT) == []


def test_a_missing_file_is_a_failure_not_a_pass(tmp_path: Path):
    """The point of the file is that frozen records have somewhere observable to keep an item.
    Absence must not read as 'nothing open'."""
    problems = li.check_open_items(ROOT, tmp_path / "absent.yaml")
    assert problems and "missing" in problems[0]


def test_an_item_missing_owner_or_trigger_fails(tmp_path: Path):
    p = _items(tmp_path, "- id: x\n  source: s\n  state: open\n  what: w\n")
    assert li.check_open_items(ROOT, p)


def test_an_item_claiming_a_mechanical_check_must_have_a_mechanical_trigger(tmp_path: Path):
    """The failure ADR-0009 named: a trigger nothing can observe. An item may not claim this script
    checks it while carrying 'when it matters'."""
    bad = _GOOD.replace(
        "trigger: any SPEC whose linked_adrs contains ADR-0008 must say whether it addresses this",
        "trigger: when someone needs it")
    assert li.check_open_items(ROOT, _items(tmp_path, bad))
    assert li.check_open_items(ROOT, _items(tmp_path, _GOOD)) == []


def test_closing_an_item_requires_saying_how(tmp_path: Path):
    closed = _GOOD.replace("state: open", "state: closed")
    assert li.check_open_items(ROOT, _items(tmp_path, closed))
    assert li.check_open_items(ROOT, _items(tmp_path, closed + "  closed_by: PR #163\n")) == []


def test_duplicate_ids_are_caught(tmp_path: Path):
    assert li.check_open_items(ROOT, _items(tmp_path, _GOOD + _GOOD))


# ── the normaliser's boundary, enumerated (debt I-012) ───────────────────────


@pytest.mark.parametrize("transform, semantic", [
    (lambda b: b + "\n\n", False),
    (lambda b: b + "   ", False),
    (lambda b: b.replace("\n", "   \n", 1), True),
])
def test_the_whitespace_gap_is_bounded_not_just_pinned(transform, semantic):
    """I-012: pinning "whitespace-only does not fail" freezes the blind spot without measuring it.

    `_normalize` rstrips each line and strips leading/trailing newlines, so trailing whitespace is
    invisible to the stamp - **including where Markdown gives it meaning.** Two trailing spaces are
    a hard line break, so an edit that changes how an approved artifact renders passes by design.

    This enumerates the boundary rather than asserting one green case: each transform is recorded
    with whether it can change rendering. A future `_normalize` that folds *more* than this makes
    the substantive set (above) go green, and a future one that folds less makes these fail - either
    way the change is visible instead of silent.
    """
    from khala.arbiter.hashing import content_hash

    assert content_hash(transform(BODY)) == content_hash(BODY)
    if semantic:
        # documented, not fixed: fixing it means changing the hash, which invalidates every stamp
        pytest.xfail("trailing double space is a Markdown hard break and the stamp cannot see it")


def test_the_stamp_sees_every_non_whitespace_change_in_the_boundary_set():
    """The other half of the bound: anything that is not purely trailing/edge whitespace must move
    the hash. Without this the gap has no ceiling."""
    from khala.arbiter.hashing import content_hash

    base = content_hash(BODY)
    mutations = {
        "a digit": BODY.replace("0.402", "0.403"),
        "a letter's case": BODY.replace("A stamped", "A Stamped"),
        "an added sentence": BODY + "one more sentence.\n",
        "an internal double space": BODY.replace("two  spaces", "two spaces"),
    }
    for label, changed in mutations.items():
        assert changed != BODY, f"{label}: the mutation is a no-op — a control that cannot fail"
        assert content_hash(changed) != base, f"{label} slipped past the stamp"
