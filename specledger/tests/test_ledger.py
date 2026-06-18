import pytest

from specledger.ledger import Ledger
from specledger.artifacts import Artifact, Status
from specledger.errors import ImmutableArtifactError


def make_ledger(docs_root):
    return Ledger(docs_root, now=lambda: "2026-06-06T00:00Z")


# ── Task 7: Ledger.record ────────────────────────────────────────────────────

def test_record_spec_creates_draft(docs_root):
    led = make_ledger(docs_root)
    sid = led.record("spec", "Virtual DJ Playlist")
    assert sid == "SPEC-virtual-dj-playlist"
    a = Artifact.load(docs_root / "specs" / f"{sid}.md")
    assert a.status == Status.DRAFT
    assert a.meta["title"] == "Virtual DJ Playlist"


def test_record_adr_creates_proposed_monotonic(docs_root):
    led = make_ledger(docs_root)
    assert led.record("adr", "First") == "ADR-0001"
    assert led.record("adr", "Second") == "ADR-0002"
    a = Artifact.load(docs_root / "adr" / "ADR-0001-first.md")
    assert a.status == Status.PROPOSED


# ── Task 8: Ledger.status ────────────────────────────────────────────────────

def test_status_reports_all(docs_root):
    led = make_ledger(docs_root)
    led.record("spec", "A")
    led.record("adr", "B")
    rep = led.status()
    assert {r["id"] for r in rep} == {"SPEC-a", "ADR-0001"}


def test_status_repairs_tampered_approved_spec(docs_root):
    led = make_ledger(docs_root)
    sid = led.record("spec", "A")
    a = Artifact.load(docs_root / "specs" / f"{sid}.md")
    a.meta["status"] = "approved"
    a.meta["content_hash"] = a.recompute_hash()
    a.save()
    a2 = Artifact.load(a.path)
    a2.body += "\nsneaky edit\n"
    a2.save()
    rep = {r["id"]: r for r in led.status()}
    assert rep[sid]["status"] == "in_review"
    assert Artifact.load(a.path).status == Status.IN_REVIEW
    assert rep[sid]["needs_review"] is True


def test_status_flags_tampered_accepted_adr_without_reset(docs_root):
    led = make_ledger(docs_root)
    aid = led.record("adr", "Decide")
    p = led._resolve(aid)
    a = Artifact.load(p)
    a.meta["status"] = "accepted"
    a.meta["content_hash"] = a.recompute_hash()
    a.save()
    a2 = Artifact.load(p)
    a2.body += "\ntamper\n"
    a2.save()
    rep = {r["id"]: r for r in led.status()}
    assert rep[aid]["tampered"] is True
    assert Artifact.load(p).status == Status.ACCEPTED


# ── Task 9: Ledger.supersede ─────────────────────────────────────────────────

def test_supersede_links_both(docs_root):
    led = make_ledger(docs_root)
    old = led.record("adr", "Old")
    new = led.record("adr", "New")
    led.supersede(old, new)
    a_old = Artifact.load(led._resolve(old))
    a_new = Artifact.load(led._resolve(new))
    assert a_old.status == Status.SUPERSEDED
    assert a_old.meta["superseded_by"] == new
    assert a_new.meta["supersedes"] == old


def test_supersede_rejects_non_adr(docs_root):
    led = make_ledger(docs_root)
    sid = led.record("spec", "S")
    aid = led.record("adr", "A")
    with pytest.raises(ImmutableArtifactError):
        led.supersede(sid, aid)


# ── Task 10: Ledger.index ────────────────────────────────────────────────────

def test_index_groups_by_status(docs_root):
    led = make_ledger(docs_root)
    led.record("spec", "Draft One")
    sid = led.record("spec", "Approved One")
    a = Artifact.load(docs_root / "specs" / f"{sid}.md")
    a.meta["status"] = "approved"
    a.meta["content_hash"] = a.recompute_hash()
    a.save()
    out = led.index()
    text = out.read_text(encoding="utf-8")
    assert out.name == "INDEX.md"
    assert "🟢" in text and "🔴" in text
    assert "SPEC-approved-one" in text
    assert text.index("🔴") < text.index("🟢")


def test_index_escapes_pipe_in_title(docs_root):
    led = make_ledger(docs_root)
    sid = led.record("spec", "Foo | Bar")
    out = led.index()
    text = out.read_text(encoding="utf-8")
    assert "Foo \\| Bar" in text
    assert sid in text


# ── Review-found regressions ─────────────────────────────────────────────────

def test_status_single_artifact_scope(docs_root):
    led = make_ledger(docs_root)
    led.record("spec", "A")
    led.record("spec", "B")
    rep = led.status("SPEC-a")
    assert len(rep) == 1
    assert rep[0]["id"] == "SPEC-a"


def test_status_flags_approved_spec_missing_hash_as_needs_review(docs_root):
    led = make_ledger(docs_root)
    sid = led.record("spec", "A")
    a = Artifact.load(docs_root / "specs" / f"{sid}.md")
    a.meta["status"] = "approved"  # promoted with NO content_hash (bypass attempt)
    a.save()
    rep = {r["id"]: r for r in led.status()}
    assert rep[sid]["status"] == "in_review"
    assert rep[sid]["needs_review"] is True
    assert Artifact.load(a.path).status == Status.IN_REVIEW


def test_supersede_rejects_self(docs_root):
    led = make_ledger(docs_root)
    aid = led.record("adr", "A")
    with pytest.raises(ValueError, match="itself"):
        led.supersede(aid, aid)


def test_supersede_rejects_already_superseded(docs_root):
    led = make_ledger(docs_root)
    a1 = led.record("adr", "One")
    a2 = led.record("adr", "Two")
    a3 = led.record("adr", "Three")
    led.supersede(a1, a2)
    with pytest.raises(ImmutableArtifactError, match="already superseded"):
        led.supersede(a1, a3)


# ── Robustness: non-artifact markdown (e.g. README) must be ignored ───────────

def test_status_and_index_skip_markdown_without_id(docs_root):
    """A README.md (no frontmatter id) in specs/ or adr/ must not crash status()/index()."""
    led = make_ledger(docs_root)
    sid = led.record("spec", "Real Spec")
    (docs_root / "specs" / "README.md").write_text("# Specs\n\nnot an artifact\n", encoding="utf-8")
    (docs_root / "adr" / "README.md").write_text("# ADRs\n", encoding="utf-8")

    report = led.status()  # must not raise
    ids = [r["id"] for r in report]
    assert sid in ids
    assert all(r["id"] for r in report)  # no entry with an empty/missing id

    out = led.index()  # must not raise
    assert out.exists()
