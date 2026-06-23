"""Tests for ken.service — the shared orchestration layer (CLI + API)."""

from ken.llm import FakeLLM
from ken.service import (
    coverage_report,
    ensure_questions,
    grade_answer,
    list_artifacts,
    register_artifact,
)
from ken.stores.file_store import FileStore


class _Boom:
    def generate(self, s, u):
        raise RuntimeError("llm down")


def _seed(tmp_path):
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    store = FileStore(
        manifest=str(tmp_path / "m.yaml"),
        questions=str(tmp_path / "q.json"),
        ledger=str(tmp_path / "l.jsonl"),
    )
    ref = register_artifact(str(art), store=store)
    return store, ref


def test_ensure_questions_generates_when_missing(tmp_path):
    store, ref = _seed(tmp_path)
    qs = ensure_questions(
        ref.artifact_id,
        store=store,
        llm=FakeLLM(responses=["Q1?\nQ2?\nQ3?"]),
        n=3,
    )
    assert [q.text for q in qs] == ["Q1?", "Q2?", "Q3?"] and all(q.id for q in qs)


def test_ensure_questions_regenerates_when_stale(tmp_path):
    store, ref = _seed(tmp_path)
    ensure_questions(
        ref.artifact_id,
        store=store,
        llm=FakeLLM(responses=["OLD?"]),
        n=1,
    )
    (tmp_path / "a.md").write_text("CHANGED content now.\n", encoding="utf-8")
    # registry.load_manifest computes content_hash LIVE, so the stored questions are
    # now stale (stored hash != current). ensure_questions must regenerate.
    qs = ensure_questions(
        ref.artifact_id,
        store=store,
        llm=FakeLLM(responses=["NEW?"]),
        n=1,
    )
    assert [q.text for q in qs] == ["NEW?"]


def test_coverage_report_zero_when_unanswered(tmp_path):
    store, ref = _seed(tmp_path)
    ensure_questions(
        ref.artifact_id,
        store=store,
        llm=FakeLLM(responses=["Q1?"]),
        n=1,
    )
    rep = coverage_report(store=store, now="2026-06-23T02:00:00Z")
    assert rep.total == 1 and rep.covered == 0 and rep.orphans == [ref.artifact_id]


def test_grade_answer_pass_records(tmp_path):
    store, ref = _seed(tmp_path)
    qs = ensure_questions(
        ref.artifact_id, store=store, llm=FakeLLM(responses=["Q1?"]), n=1,
    )
    res = grade_answer(
        ref.artifact_id, qs[0].id, "a good answer", person="kr",
        store=store,
        llm=FakeLLM(responses=['{"passed": true, "score": 0.9, "rationale": "ok"}']),
        now="2026-06-23T00:00:00Z",
    )
    assert res.passed and res.remediation is None
    assert len(store.load_attempts()) == 1


def test_grade_answer_fail_includes_remediation(tmp_path):
    store, ref = _seed(tmp_path)
    qs = ensure_questions(
        ref.artifact_id, store=store, llm=FakeLLM(responses=["Q1?"]), n=1,
    )
    # FakeLLM returns verdict (fail) then remediation text, in call order
    res = grade_answer(
        ref.artifact_id, qs[0].id, "wrong", person="kr",
        store=store,
        llm=FakeLLM(responses=['{"passed": false, "score": 0.1, "rationale": "no"}',
                               "Here is why: the service publishes orders..."]),
        now="2026-06-23T00:00:00Z",
    )
    assert res.passed is False and res.remediation and "publishes" in res.remediation


def test_grade_answer_fail_closed_on_grade_llm_error(tmp_path):
    store, ref = _seed(tmp_path)
    qs = ensure_questions(
        ref.artifact_id, store=store, llm=FakeLLM(responses=["Q1?"]), n=1,
    )
    res = grade_answer(
        ref.artifact_id, qs[0].id, "x", person="kr", store=store, llm=_Boom(),
        now="2026-06-23T00:00:00Z",
    )
    assert res.passed is False  # fail-closed; attempt still recorded


def test_remediation_llm_failure_yields_none_but_records(tmp_path):
    store, ref = _seed(tmp_path)
    qs = ensure_questions(
        ref.artifact_id, store=store, llm=FakeLLM(responses=["Q1?"]), n=1,
    )

    # one-shot llm: verdict fail, then raises on the remediation call
    class _FailRemediate:
        def __init__(self):
            self.calls = 0

        def generate(self, s, u):
            self.calls += 1
            if self.calls == 1:
                return '{"passed": false, "score": 0.0, "rationale": "no"}'
            raise RuntimeError("remediation down")

    res = grade_answer(
        ref.artifact_id, qs[0].id, "x", person="kr", store=store, llm=_FailRemediate(),
        now="2026-06-23T00:00:00Z",
    )
    assert res.passed is False and res.remediation is None
    assert len(store.load_attempts()) == 1  # recorded despite remediation failure


def test_list_artifacts_orphan_when_unanswered(tmp_path):
    store, ref = _seed(tmp_path)
    ensure_questions(
        ref.artifact_id, store=store, llm=FakeLLM(responses=["Q1?"]), n=1,
    )
    rows = list_artifacts(store=store, now="2026-06-23T02:00:00Z")
    assert len(rows) == 1
    row = rows[0]
    assert row.artifact_id == ref.artifact_id
    assert row.status == "orphan" and row.weak_count == 0


def test_list_artifacts_vouched_with_weak_count(tmp_path):
    store, ref = _seed(tmp_path)
    qs = ensure_questions(
        ref.artifact_id, store=store, llm=FakeLLM(responses=["Q1?"]), n=1,
    )
    # fail once (records fail_count=1), then pass (latest attempt passes -> vouched)
    grade_answer(
        ref.artifact_id, qs[0].id, "wrong", person="kr", store=store,
        llm=FakeLLM(responses=['{"passed": false, "score": 0.0, "rationale": "no"}', "fix it"]),
        now="2026-06-23T00:00:00Z",
    )
    grade_answer(
        ref.artifact_id, qs[0].id, "right", person="kr", store=store,
        llm=FakeLLM(responses=['{"passed": true, "score": 1.0, "rationale": "ok"}']),
        now="2026-06-23T01:00:00Z",
    )
    rows = list_artifacts(store=store, now="2026-06-23T02:00:00Z")
    assert rows[0].status == "vouched" and rows[0].weak_count == 1
