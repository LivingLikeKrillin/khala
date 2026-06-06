import pytest  # noqa: F401

from specledger.ledger import Ledger
from specledger.artifacts import Artifact, Status
from specledger.errors import ImmutableArtifactError  # noqa: F401


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
