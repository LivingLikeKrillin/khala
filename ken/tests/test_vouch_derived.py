from ken.models import Attempt, Question
from ken.schedule import rebuild
from ken.vouch import is_vouched


def att(qid, passed, ts, h="sha256:cur"):  # local helper
    return Attempt("kr", "a1", qid, h, passed, 1.0, ts)


def _states(atts, qids):
    return rebuild(atts, current_hashes={q: "sha256:cur" for q in qids})


def test_all_pass_vouched_when_fresh():
    qs = [Question(id="q1", text="a"), Question(id="q2", text="b")]
    atts = [att("q1", True, "2026-06-20T00:00:00Z"), att("q2", True, "2026-06-20T00:00:00Z")]
    states = _states(atts, ["q1", "q2"])
    assert is_vouched(qs, states, now="2026-06-20T01:00:00Z") is True  # before +1d


def test_all_pass_decays_when_overdue():
    qs = [Question(id="q1", text="a")]
    atts = [att("q1", True, "2026-06-20T00:00:00Z")]  # rung 1 -> next_due +1d
    states = _states(atts, ["q1"])
    assert is_vouched(qs, states, now="2026-06-22T00:00:00Z") is False  # past next_due


def test_zero_attempt_question_blocks():
    qs = [Question(id="q1", text="a"), Question(id="q2", text="b")]
    atts = [att("q1", True, "2026-06-20T00:00:00Z")]  # q2 never attempted
    states = _states(atts, ["q1", "q2"])
    assert is_vouched(qs, states, now="2026-06-20T01:00:00Z") is False


def test_failed_question_blocks_at_boundary():
    qs = [Question(id="q1", text="a")]
    atts = [att("q1", False, "2026-06-20T00:00:00Z")]  # rung 0 -> next_due == last_ts
    states = _states(atts, ["q1"])
    # boundary: now == last_ts -> now >= next_due -> due -> not vouched
    assert is_vouched(qs, states, now="2026-06-20T00:00:00Z") is False


def test_stale_hash_blocks():
    qs = [Question(id="q1", text="a")]
    atts = [att("q1", True, "2026-06-20T00:00:00Z", h="sha256:OLD")]
    states = rebuild(atts, current_hashes={"q1": "sha256:NEW"})  # stale -> no state
    assert is_vouched(qs, states, now="2026-06-20T01:00:00Z") is False


def test_empty_questions_vouched():
    assert is_vouched([], {}, now="2026-06-20T00:00:00Z") is True
