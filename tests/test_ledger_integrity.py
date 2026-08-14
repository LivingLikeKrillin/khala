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
              stamp: str | None = "auto", retractions: list[str] | None = None) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    h = content_hash(body) if stamp == "auto" else stamp
    fm = [f"id: {aid}", "type: spec", f"title: {aid}", f"status: {status}"]
    for r in retractions or []:
        fm.append(f"retractions:\n- {r}")
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


def _closed(extra: str = "") -> str:
    """Closing an item drops its trigger — there is nothing left to watch for."""
    body = "\n".join(ln for ln in _GOOD.splitlines() if not ln.startswith("  trigger:"))
    return body.replace("state: open", "state: closed") + "\n" + extra


def test_closing_an_item_requires_saying_how(tmp_path: Path):
    assert li.check_open_items(ROOT, _items(tmp_path, _closed()))
    assert li.check_open_items(ROOT, _items(tmp_path, _closed("  closed_by: PR #163\n"))) == []


def test_a_closed_item_may_not_keep_a_trigger_or_a_reason_it_is_open(tmp_path: Path):
    """A closed row that still says what to watch for, or why it is open, reads as open — and this
    ledger is read by skimming.

    Found on two real rows (`ko-eval-store-loss`, `packb-corpus-substance`), both closed with the
    fields left behind and neither noticed. Fixing it exposed a contradiction in the checker
    itself: `trigger` was required of *every* item, so a closed row was obliged to keep one.
    """
    good = _closed("  closed_by: measured, and the measurement went against it\n")
    assert li.check_open_items(ROOT, _items(tmp_path, good)) == []
    for stale in ("  trigger: watch for the next SPEC\n", "  why_still_open: not taken up\n"):
        assert li.check_open_items(ROOT, _items(tmp_path, good + stale)), \
            f"닫힌 항목이 {stale.split(':')[0].strip()} 를 들고 있는데 통과했다"


def test_an_open_item_still_must_carry_a_trigger(tmp_path: Path):
    """반대 방향. 닫힌 쪽을 풀어주면서 열린 쪽까지 느슨해지면 ADR-0009 가 거부한 형태가 돌아온다."""
    no_trigger = "\n".join(ln for ln in _GOOD.splitlines() if not ln.startswith("  trigger:"))
    assert li.check_open_items(ROOT, _items(tmp_path, no_trigger))


def test_duplicate_ids_are_caught(tmp_path: Path):
    assert li.check_open_items(ROOT, _items(tmp_path, _GOOD + _GOOD))


# ── retractions live outside the frozen body (OPEN.md H5 / A5) ───────────────

_QUOTE = "It reports Recall@10 of 0.402 over the pack"


def _retractions(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "retractions.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def _entry(**over) -> str:
    """Serialised by yaml itself. Hand-rolling the quoting turned a newline in a quote into a
    literal backslash-n, and the failure looked like the checker's."""
    import yaml

    e = {"target": "SPEC-a", "retracted_by": "SPEC-b", "signed_by": "someone",
         "signed_at": "2026-08-15", "quote": _QUOTE, "why": "it was wrong"}
    e.update(over)
    return yaml.safe_dump([e], allow_unicode=True, sort_keys=False)


def _repo_with_target(repo: Path, *, status="approved", pointer=("SPEC-b",)) -> Path:
    _artifact(repo / "specs", "SPEC-a", status, retractions=list(pointer))
    return repo


def test_a_well_formed_retraction_passes(repo: Path):
    """Positive control. Without it the checks below could be passing for the wrong reason."""
    _repo_with_target(repo)
    assert li.check_retractions(repo, _retractions(repo, _entry())) == []


def test_a_retraction_the_document_does_not_point_back_to_is_flagged(repo: Path):
    """**The one that matters.** A retraction nobody sees is worse than a broken hash — the
    reader of the approved document would learn nothing."""
    _repo_with_target(repo, pointer=())
    problems = li.check_retractions(repo, _retractions(repo, _entry()))
    assert problems and "point back" in problems[0]


def test_a_pointer_with_no_entry_behind_it_is_flagged(repo: Path):
    """The other direction: a badge that outlives its reason. Deleting the entry must not
    quietly leave the document marked as retracted."""
    _repo_with_target(repo)
    problems = li.check_retractions(repo, _retractions(repo, "[]"))
    assert problems and "no entry" in problems[0]


def test_quoting_a_sentence_the_document_does_not_contain_is_flagged(repo: Path):
    """Retracting a sentence that is not there retracts nothing, and nothing else would notice."""
    _repo_with_target(repo)
    problems = li.check_retractions(
        repo, _retractions(repo, _entry(quote="It reports Recall@10 of 0.999")))
    assert problems and "not in" in problems[0]


@pytest.mark.parametrize("quote", [
    "It reports Recall@10 of 0.402 … with two  spaces above.",     # elided middle
    "It reports Recall@10\nof 0.402 over the pack",                 # rewrapped by an editor
])
def test_an_elided_or_rewrapped_quote_still_matches(repo: Path, quote):
    """Whitespace and `…` are how people quote. If either failed, the lesson learned would be
    to stop quoting — and the quote is what makes a retraction locatable."""
    _repo_with_target(repo)
    assert li.check_retractions(repo, _retractions(repo, _entry(quote=quote))) == []


def test_an_entry_missing_a_field_is_flagged(repo: Path):
    _repo_with_target(repo)
    body = "".join(ln for ln in _entry().splitlines(keepends=True)
                   if not ln.startswith("  signed_by:"))
    problems = li.check_retractions(repo, _retractions(repo, body))
    assert problems and "signed_by" in problems[0]


def test_retracting_something_that_was_never_signed_is_flagged(repo: Path):
    """A draft carries no signed claim, so there is nothing to withdraw."""
    _repo_with_target(repo, status="draft")
    problems = li.check_retractions(repo, _retractions(repo, _entry()))
    assert problems and "not stamped" in problems[0]


def test_a_missing_sidecar_is_not_a_failure(repo: Path):
    """Absence of retractions is the normal state. Only a pointer with nothing behind it is."""
    _artifact(repo / "specs", "SPEC-a", "approved")
    assert li.check_retractions(repo, repo / "absent.yaml") == []


def test_the_real_repository_retractions_are_consistent():
    assert li.check_retractions(ROOT) == []


def test_the_frozen_bodies_carry_no_retraction_footnote():
    """The regression this replaced: footnotes were added to two approved SPECs, the stamps
    broke, and master stayed red for fifteen merges (#240-#254). The bodies are frozen; the
    stamp check above proves they match, and this proves the retraction did not go back in."""
    for name in ("SPEC-nexus-a2a-external-exposure-audit-phase2",
                 "SPEC-nexus-query-text-retention"):
        text = (ROOT / "specs" / f"{name}.md").read_text(encoding="utf-8")
        _, _, body = text[3:].partition("\n---")
        assert "철회" not in body, f"{name}: a retraction is back inside the signed body"


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
