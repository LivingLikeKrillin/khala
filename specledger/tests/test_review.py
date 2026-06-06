import pytest
from specledger.ledger import Ledger
from specledger.artifacts import Artifact, Status
from specledger.critique import critique
from specledger.review import approve
from specledger.errors import ReviewError
from helpers import FakeCritic


def _make_critiqued_ledger(docs_root):
    ledger = Ledger(docs_root, now=lambda: "t")
    sid = ledger.record("spec", "A")
    critique(ledger, sid, FakeCritic(), now=lambda: "t")
    return ledger, sid


def test_approve_requires_all_issues_dispositioned(docs_root):
    ledger, sid = _make_critiqued_ledger(docs_root)
    with pytest.raises(ReviewError, match="undispositioned"):
        approve(ledger, sid, [], "eisen", now=lambda: "t2")


def test_reject_requires_reason(docs_root):
    ledger, sid = _make_critiqued_ledger(docs_root)
    with pytest.raises(ReviewError, match="reason"):
        approve(ledger, sid, [{"issue_id": "I-001", "disposition": "rejected"}], "eisen", now=lambda: "t2")


def test_accepted_requires_body_edit(docs_root):
    ledger, sid = _make_critiqued_ledger(docs_root)
    with pytest.raises(ReviewError, match="미수정"):
        approve(ledger, sid, [{"issue_id": "I-001", "disposition": "accepted"}], "eisen", now=lambda: "t2")


def test_accepted_with_edit_succeeds_and_stamps(docs_root):
    ledger, sid = _make_critiqued_ledger(docs_root)
    art = Artifact.load(ledger._resolve(sid))
    art.body += "\nfixed the invariant\n"
    art.save()
    approve(ledger, sid, [{"issue_id": "I-001", "disposition": "accepted"}], "eisen", now=lambda: "t2")
    a2 = Artifact.load(ledger._resolve(sid))
    assert a2.status == Status.APPROVED
    assert a2.meta["approved_by"] == "eisen"
    assert a2.meta["content_hash"] == a2.recompute_hash()


def test_all_rejected_no_edit_required(docs_root):
    ledger, sid = _make_critiqued_ledger(docs_root)
    approve(ledger, sid, [{"issue_id": "I-001", "disposition": "rejected", "reason": "wrong"}],
            "eisen", now=lambda: "t2")
    assert Artifact.load(ledger._resolve(sid)).status == Status.APPROVED


def test_approve_fail_closed_without_sidecar(docs_root):
    ledger = Ledger(docs_root, now=lambda: "t")
    sid = ledger.record("spec", "A")  # never critiqued
    with pytest.raises(ReviewError, match="critique"):
        approve(ledger, sid, [], "eisen", now=lambda: "t2")


def test_approve_adr_yields_accepted_not_approved(docs_root):
    ledger = Ledger(docs_root, now=lambda: "t")
    aid = ledger.record("adr", "A Decision")
    critique(ledger, aid, FakeCritic(), now=lambda: "t")
    a = Artifact.load(ledger._resolve(aid))
    a.body += "\nfixed\n"
    a.save()
    approve(ledger, aid, [{"issue_id": "I-001", "disposition": "accepted"}], "eisen", now=lambda: "t2")
    assert Artifact.load(ledger._resolve(aid)).status == Status.ACCEPTED


def test_approve_with_zero_issues_succeeds(docs_root):
    ledger = Ledger(docs_root, now=lambda: "t")
    sid = ledger.record("spec", "A")
    critique(ledger, sid, FakeCritic(issues=[]), now=lambda: "t")  # critic found nothing
    approve(ledger, sid, [], "eisen", now=lambda: "t2")
    assert Artifact.load(ledger._resolve(sid)).status == Status.APPROVED
