import pytest

from khala.adept.models import Question
from khala.adept.questions import load_questions, make_question_id, save_questions


def test_save_load_roundtrip_replaces(tmp_path):
    store = tmp_path / "q.json"
    save_questions("a1", "sha256:h1", [Question(id="x", text="q1")], store_path=store)
    save_questions("a1", "sha256:h2", [Question(id="y", text="q2")], store_path=store)  # replace
    h, qs = load_questions("a1", store_path=store)
    assert h == "sha256:h2" and [q.text for q in qs] == ["q2"]


def test_make_question_id_stable():
    assert make_question_id("a1", "sha256:h", 0) == make_question_id("a1", "sha256:h", 0)
    assert make_question_id("a1", "sha256:h", 0) != make_question_id("a1", "sha256:h", 1)


def test_load_absent_is_empty(tmp_path):
    h, qs = load_questions("missing", store_path=tmp_path / "absent.json")
    assert h is None and qs == []


def test_save_assigns_ids_when_missing(tmp_path):
    store = tmp_path / "q.json"
    save_questions("a1", "sha256:h", [Question(text="q1"), Question(text="q2")], store_path=store)
    _, qs = load_questions("a1", store_path=store)
    assert qs[0].id == make_question_id("a1", "sha256:h", 0)
    assert qs[1].id == make_question_id("a1", "sha256:h", 1)


def test_save_fails_loud(tmp_path):
    with pytest.raises(OSError):
        save_questions(
            "a1",
            "h",
            [Question(id="x", text="q")],
            store_path=tmp_path / "no" / "q.json",
            make_parents=False,
        )
