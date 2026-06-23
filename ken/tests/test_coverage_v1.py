from ken.coverage import compute_coverage_v1
from ken.models import ArtifactRef, Attempt, Question


def att(qid, passed, ts, h="sha256:cur"):  # local helper
    return Attempt("kr", "a1", qid, h, passed, 1.0, ts)


def test_coverage_and_weakness():
    arts = [ArtifactRef("a1", "/a", "sha256:cur")]
    qmap = {"a1": ("sha256:cur", [Question(id="q1", text="x"), Question(id="q2", text="y")])}
    atts = [
        att("q1", True, "2026-06-20T00:00:00Z"),
        att("q2", False, "2026-06-20T00:00:00Z"),
        att("q2", False, "2026-06-20T01:00:00Z"),
    ]
    rep = compute_coverage_v1(arts, qmap, atts)
    assert rep.total == 1 and rep.covered == 0 and rep.orphans == ["a1"]
    assert any(w.question_id == "q2" and w.fail_count == 2 for w in rep.weakness)


def test_fully_vouched_artifact_covered():
    arts = [ArtifactRef("a1", "/a", "sha256:cur")]
    qmap = {"a1": ("sha256:cur", [Question(id="q1", text="x")])}
    atts = [att("q1", True, "2026-06-20T00:00:00Z")]
    rep = compute_coverage_v1(arts, qmap, atts)
    assert rep.total == 1 and rep.covered == 1 and rep.orphans == [] and rep.ratio == 1.0


def test_artifact_without_questions_is_orphan():
    arts = [ArtifactRef("a1", "/a", "sha256:cur")]
    rep = compute_coverage_v1(arts, {}, [])
    assert rep.covered == 0 and rep.orphans == ["a1"]


def test_stale_store_hash_is_orphan():
    # questions stored against an old hash -> not bound to current content -> orphan
    arts = [ArtifactRef("a1", "/a", "sha256:NEW")]
    qmap = {"a1": ("sha256:OLD", [Question(id="q1", text="x")])}
    atts = [att("q1", True, "2026-06-20T00:00:00Z", h="sha256:OLD")]
    rep = compute_coverage_v1(arts, qmap, atts)
    assert rep.covered == 0 and rep.orphans == ["a1"]
