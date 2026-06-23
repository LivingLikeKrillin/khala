"""Tests for ken.service — the shared orchestration layer (CLI + API)."""

from ken.llm import FakeLLM
from ken.service import (
    coverage_report,
    ensure_questions,
    register_artifact,
)


def _seed(tmp_path):
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    man = tmp_path / "m.yaml"
    ref = register_artifact(str(art), manifest=str(man))
    return man, ref


def test_ensure_questions_generates_when_missing(tmp_path):
    man, ref = _seed(tmp_path)
    qs_store = tmp_path / "q.json"
    qs = ensure_questions(
        ref.artifact_id,
        manifest=str(man),
        questions_store=str(qs_store),
        llm=FakeLLM(responses=["Q1?\nQ2?\nQ3?"]),
        n=3,
    )
    assert [q.text for q in qs] == ["Q1?", "Q2?", "Q3?"] and all(q.id for q in qs)


def test_ensure_questions_regenerates_when_stale(tmp_path):
    man, ref = _seed(tmp_path)
    qs_store = tmp_path / "q.json"
    ensure_questions(
        ref.artifact_id,
        manifest=str(man),
        questions_store=str(qs_store),
        llm=FakeLLM(responses=["OLD?"]),
        n=1,
    )
    (tmp_path / "a.md").write_text("CHANGED content now.\n", encoding="utf-8")
    # registry.load_manifest computes content_hash LIVE, so the stored questions are
    # now stale (stored hash != current). ensure_questions must regenerate.
    qs = ensure_questions(
        ref.artifact_id,
        manifest=str(man),
        questions_store=str(qs_store),
        llm=FakeLLM(responses=["NEW?"]),
        n=1,
    )
    assert [q.text for q in qs] == ["NEW?"]


def test_coverage_report_zero_when_unanswered(tmp_path):
    man, ref = _seed(tmp_path)
    qs_store = tmp_path / "q.json"
    led = tmp_path / "l.jsonl"
    ensure_questions(
        ref.artifact_id,
        manifest=str(man),
        questions_store=str(qs_store),
        llm=FakeLLM(responses=["Q1?"]),
        n=1,
    )
    rep = coverage_report(manifest=str(man), questions_store=str(qs_store), ledger=str(led))
    assert rep.total == 1 and rep.covered == 0 and rep.orphans == [ref.artifact_id]
