from khala.adept.models import Attempt, Question, ReviewState


def test_question_has_id():
    q = Question(id="abc123", text="why?")
    assert q.id == "abc123"


def test_attempt_roundtrip():
    a = Attempt(
        person="kr",
        artifact_id="a1",
        question_id="q1",
        content_hash="sha256:x",
        passed=True,
        score=0.9,
        ts="2026-06-23T00:00:00Z",
    )
    assert Attempt.from_dict(a.to_dict()) == a


def test_review_state_fields():
    st = ReviewState(
        question_id="q1",
        content_hash="sha256:x",
        interval_idx=2,
        last_ts="2026-06-23T00:00:00Z",
        last_passed=True,
        fail_count=1,
    )
    assert st.interval_idx == 2 and st.last_passed is True and st.fail_count == 1
