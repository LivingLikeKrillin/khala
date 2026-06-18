"""Lossless parity (SPEC §7 test_a2a_parity).

The same answer routed through the A2A artifact mapping must preserve the exact answer
text and the exact evidence set (source_uri + text) that the direct /search/answer path
returns — the mapping drops nothing.
"""

from __future__ import annotations

from nexus.a2a.mapping import build_grounded_artifact
from nexus.llm.answer import AnswerResult


def _direct_result() -> AnswerResult:
    return AnswerResult(
        answer="결제 서비스는 payment.events 토픽을 발행합니다.",
        evidence_snippets=[
            {"chunk_rid": "c1", "doc_title": "Payment", "section_path": "Topics",
             "source_uri": "git://docs/payment.md", "text": "payment.events 발행", "score": 0.9},
            {"chunk_rid": "c2", "doc_title": "Catalog", "section_path": "Events",
             "source_uri": "git://docs/events.md", "text": "결제 완료 이벤트", "score": 0.6},
        ],
        provenance=[{"doc_rid": "d1", "source_uri": "git://docs/payment.md", "source_version": "v2"}],
        route_used="graph",
    )


def test_answer_text_is_identical_between_paths():
    direct = _direct_result()
    artifact, _state, _reason = build_grounded_artifact(direct, "acme", "INTERNAL")
    a2a_text = [p["text"] for p in artifact["parts"] if p["kind"] == "text"][0]
    assert a2a_text == direct.answer


def test_evidence_set_is_preserved_between_paths():
    direct = _direct_result()
    artifact, _state, _reason = build_grounded_artifact(direct, "acme", "INTERNAL")
    a2a_data = [p["data"] for p in artifact["parts"] if p["kind"] == "data"][0]

    direct_set = {(s["source_uri"], s["text"]) for s in direct.evidence_snippets}
    a2a_set = {(e["source_uri"], e["text"]) for e in a2a_data["evidence"]}
    assert a2a_set == direct_set
