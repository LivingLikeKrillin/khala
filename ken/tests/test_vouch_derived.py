from ken.models import Attempt, Question
from ken.schedule import rebuild
from ken.vouch import is_vouched


def att(qid, passed, ts, h="sha256:cur"):  # local helper
    return Attempt("kr", "a1", qid, h, passed, 1.0, ts)


def test_all_pass_vouched():
    qs = [Question(id="q1", text="a"), Question(id="q2", text="b")]
    atts = [att("q1", True, "2026-06-20T00:00:00Z"), att("q2", True, "2026-06-20T00:00:00Z")]
    states = rebuild(atts, current_hashes={"q1": "sha256:cur", "q2": "sha256:cur"})
    assert is_vouched(qs, states) is True


def test_zero_attempt_question_blocks():
    qs = [Question(id="q1", text="a"), Question(id="q2", text="b")]
    atts = [att("q1", True, "2026-06-20T00:00:00Z")]  # q2 never attempted
    states = rebuild(atts, current_hashes={"q1": "sha256:cur", "q2": "sha256:cur"})
    assert is_vouched(qs, states) is False


def test_failed_question_blocks():
    qs = [Question(id="q1", text="a")]
    atts = [att("q1", False, "2026-06-20T00:00:00Z")]
    states = rebuild(atts, current_hashes={"q1": "sha256:cur"})
    assert is_vouched(qs, states) is False


def test_stale_hash_blocks():
    qs = [Question(id="q1", text="a")]
    atts = [att("q1", True, "2026-06-20T00:00:00Z", h="sha256:OLD")]
    states = rebuild(atts, current_hashes={"q1": "sha256:NEW"})  # stale -> no state
    assert is_vouched(qs, states) is False


def test_empty_questions_vouched():
    # an artifact with no questions is vacuously vouched (no debt to repay)
    assert is_vouched([], {}) is True
