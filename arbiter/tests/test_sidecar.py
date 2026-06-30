from specledger.sidecar import Sidecar, Issue


def test_write_then_read_roundtrips(docs_root):
    p = docs_root / ".reviews" / "SPEC-x.md"
    sc = Sidecar(
        target="SPEC-x",
        critiqued_hash="sha256:abc",
        critiqued_at="2026-06-06T13:00Z",
        issues=[Issue("I-001", "missing-invariant", "high", "no invariant stated", "open", None)],
        narrative="prose here",
    )
    sc.write(p)
    back = Sidecar.read(p)
    assert back.target == "SPEC-x"
    assert back.critiqued_hash == "sha256:abc"
    assert back.issues[0].issue_id == "I-001"
    assert back.issues[0].status == "open"
    assert back.narrative.strip() == "prose here"


def test_open_issue_count(docs_root):
    sc = Sidecar(
        target="SPEC-x", critiqued_hash="sha256:abc", critiqued_at="t",
        issues=[
            Issue("I-001", "x", "high", "d", "open", None),
            Issue("I-002", "y", "low", "d", "accepted", None),
        ],
        narrative="",
    )
    assert sc.open_issue_count() == 1
