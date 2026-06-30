import pytest

from khala.adept.attempt import append_attempt, load_attempts
from khala.adept.models import Attempt


def mk(passed=True, ts="2026-06-23T00:00:00Z", qid="q1"):
    return Attempt("kr", "a1", qid, "sha256:h", passed, 0.9, ts)


def test_append_then_load(tmp_path):
    p = tmp_path / "att.jsonl"
    append_attempt(mk(), ledger_path=p)
    append_attempt(mk(passed=False), ledger_path=p)
    got = load_attempts(p)
    assert len(got) == 2 and got[1].passed is False


def test_append_fails_loud(tmp_path):
    with pytest.raises(OSError):
        append_attempt(mk(), ledger_path=tmp_path / "no" / "a.jsonl", make_parents=False)


def test_load_absent_is_empty(tmp_path):
    assert load_attempts(tmp_path / "absent.jsonl") == []
