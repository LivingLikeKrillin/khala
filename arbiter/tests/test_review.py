import pytest
from khala.arbiter.ledger import Ledger
from khala.arbiter.artifacts import Artifact, Status
from khala.arbiter.critique import critique
from khala.arbiter.review import approve
from khala.arbiter.sidecar import Issue, Sidecar
from khala.arbiter.errors import ReviewError
from helpers import FakeCritic


def _make_critiqued_ledger(docs_root):
    ledger = Ledger(docs_root, now=lambda: "t")
    sid = ledger.record("spec", "A")
    critique(ledger, sid, FakeCritic(), now=lambda: "t")
    return ledger, sid


def test_approve_requires_all_issues_dispositioned(docs_root):
    ledger, sid = _make_critiqued_ledger(docs_root)
    with pytest.raises(ReviewError, match="undispositioned"):
        approve(ledger, sid, [], "reviewer", now=lambda: "t2")


def test_reject_requires_reason(docs_root):
    ledger, sid = _make_critiqued_ledger(docs_root)
    with pytest.raises(ReviewError, match="reason"):
        approve(ledger, sid, [{"issue_id": "I-001", "disposition": "rejected"}], "reviewer", now=lambda: "t2")


def test_accepted_requires_body_edit(docs_root):
    ledger, sid = _make_critiqued_ledger(docs_root)
    with pytest.raises(ReviewError, match="미수정"):
        approve(ledger, sid, [{"issue_id": "I-001", "disposition": "accepted"}], "reviewer", now=lambda: "t2")


def test_accepted_with_edit_succeeds_and_stamps(docs_root):
    ledger, sid = _make_critiqued_ledger(docs_root)
    art = Artifact.load(ledger._resolve(sid))
    art.body += "\nfixed the invariant\n"
    art.save()
    approve(ledger, sid, [{"issue_id": "I-001", "disposition": "accepted"}], "reviewer", now=lambda: "t2")
    a2 = Artifact.load(ledger._resolve(sid))
    assert a2.status == Status.APPROVED
    assert a2.meta["approved_by"] == "reviewer"
    assert a2.meta["content_hash"] == a2.recompute_hash()


def test_all_rejected_no_edit_required(docs_root):
    ledger, sid = _make_critiqued_ledger(docs_root)
    approve(ledger, sid, [{"issue_id": "I-001", "disposition": "rejected", "reason": "wrong"}],
            "reviewer", now=lambda: "t2")
    assert Artifact.load(ledger._resolve(sid)).status == Status.APPROVED


def test_approve_fail_closed_without_sidecar(docs_root):
    ledger = Ledger(docs_root, now=lambda: "t")
    sid = ledger.record("spec", "A")  # never critiqued
    with pytest.raises(ReviewError, match="critique"):
        approve(ledger, sid, [], "reviewer", now=lambda: "t2")


def test_approve_adr_yields_accepted_not_approved(docs_root):
    ledger = Ledger(docs_root, now=lambda: "t")
    aid = ledger.record("adr", "A Decision")
    critique(ledger, aid, FakeCritic(), now=lambda: "t")
    a = Artifact.load(ledger._resolve(aid))
    a.body += "\nfixed\n"
    a.save()
    approve(ledger, aid, [{"issue_id": "I-001", "disposition": "accepted"}], "reviewer", now=lambda: "t2")
    assert Artifact.load(ledger._resolve(aid)).status == Status.ACCEPTED


def test_approve_with_zero_issues_succeeds(docs_root):
    ledger = Ledger(docs_root, now=lambda: "t")
    sid = ledger.record("spec", "A")
    critique(ledger, sid, FakeCritic(issues=[]), now=lambda: "t")  # critic found nothing
    approve(ledger, sid, [], "reviewer", now=lambda: "t2")
    assert Artifact.load(ledger._resolve(sid)).status == Status.APPROVED


# --- behavioral post-state of dispositioned issues (Probe Gap A) ---
# Every test above asserts the Artifact's meta (status/approved_by/hash) but none
# pins the Sidecar issue records that approve() writes. Mutation testing showed the
# whole disposition-writeback loop could be disabled (`for i in []`) or its guard
# inverted while staying green. These tests assert that side-effect directly.

def test_approve_persists_disposition_onto_open_issue(docs_root):
    ledger, sid = _make_critiqued_ledger(docs_root)
    approve(
        ledger, sid,
        [{"issue_id": "I-001", "disposition": "rejected", "reason": "out of scope"}],
        "reviewer", now=lambda: "t2",
    )
    sc = Sidecar.read(ledger.reviews / f"{sid}.md")
    issue = next(i for i in sc.issues if i.issue_id == "I-001")
    assert issue.status == "rejected"
    assert issue.disposition_reason == "out of scope"


def test_approve_leaves_already_closed_issue_untouched(docs_root):
    ledger, sid = _make_critiqued_ledger(docs_root)
    # Inject two already-closed issues (from a prior round) that are NOT in this
    # round's dispositions. They must stay out of the open set and keep their record.
    sc_path = ledger.reviews / f"{sid}.md"
    sc = Sidecar.read(sc_path)
    sc.issues.append(Issue("I-PRIOR-A", "cat", "low", "old", "deferred", "deferred last round"))
    sc.issues.append(Issue("I-PRIOR-R", "cat", "low", "old", "rejected", "rejected last round"))
    sc.write(sc_path)

    approve(
        ledger, sid,
        [{"issue_id": "I-001", "disposition": "rejected", "reason": "out of scope"}],
        "reviewer", now=lambda: "t2",
    )

    sc2 = Sidecar.read(sc_path)
    by_id = {i.issue_id: i for i in sc2.issues}
    assert by_id["I-001"].status == "rejected"            # this round's issue updated
    assert by_id["I-PRIOR-A"].status == "deferred"        # prior records preserved
    assert by_id["I-PRIOR-A"].disposition_reason == "deferred last round"
    assert by_id["I-PRIOR-R"].status == "rejected"
    assert by_id["I-PRIOR-R"].disposition_reason == "rejected last round"
