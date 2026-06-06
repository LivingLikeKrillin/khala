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
