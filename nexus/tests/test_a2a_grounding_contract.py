"""The grounding-preservation guard (SPEC §3.3, §6.1).

The single load-bearing test of the spike: the ``NexusResponse -> A2A artifact`` mapping
must be total and lossless for the grounding fields, and a no-evidence response must map
to the A2A ``failed`` state — never to a confident answer without evidence.

These are pure unit tests over ``build_grounded_artifact`` (no DB / LLM / network).
"""

from __future__ import annotations

import a2a.compat.v0_3.types as a2a_types

from nexus.a2a.mapping import build_grounded_artifact
from nexus.llm.answer import AnswerResult


def _grounded_result() -> AnswerResult:
    """An AnswerResult shaped exactly like the existing /search/answer data path."""
    return AnswerResult(
        answer="결제 서비스는 `payment.events` 토픽을 발행합니다.",
        evidence_snippets=[
            {
                "chunk_rid": "chunk_abc",
                "doc_title": "Payment Service Design",
                "section_path": "Events/Topics",
                "source_uri": "git://docs/payment.md",
                "text": "payment.events 토픽을 발행한다.",
                "score": 0.92,
            },
            {
                "chunk_rid": "chunk_def",
                "doc_title": "Event Catalog",
                "section_path": "Topics",
                "source_uri": "git://docs/events.md",
                "text": "payment.events: 결제 완료 이벤트",
                "score": 0.71,
            },
        ],
        provenance=[
            {"doc_rid": "doc_p", "source_uri": "git://docs/payment.md", "source_version": "v3"},
            {"doc_rid": "doc_e", "source_uri": "git://docs/events.md", "source_version": "v1"},
        ],
        route_used="graph",
        timing_ms={"total_ms": 120},
    )


def _data_part(artifact: dict) -> dict:
    """Return the single ``application/json`` data part's payload from an artifact dict."""
    data_parts = [p["data"] for p in artifact["parts"] if p.get("kind") == "data"]
    assert len(data_parts) == 1, f"expected exactly one data part, got {len(data_parts)}"
    return data_parts[0]


def _text_part(artifact: dict) -> str:
    text_parts = [p["text"] for p in artifact["parts"] if p.get("kind") == "text"]
    assert len(text_parts) == 1, f"expected exactly one text part, got {len(text_parts)}"
    return text_parts[0]


def test_grounded_answer_maps_to_completed_artifact_with_full_evidence():
    artifact, state, reason = build_grounded_artifact(
        _grounded_result(), tenant="acme", clearance="INTERNAL"
    )

    assert state == a2a_types.TaskState.completed.value  # "completed"
    assert reason is None

    # (a) narrated answer present
    assert _text_part(artifact) == "결제 서비스는 `payment.events` 토픽을 발행합니다."

    data = _data_part(artifact)
    # (b) structured evidence packet — every grounding field present and lossless
    assert len(data["evidence"]) == 2
    first = data["evidence"][0]
    assert first["source_uri"] == "git://docs/payment.md"
    assert first["section_path"] == "Events/Topics"
    assert first["doc_title"] == "Payment Service Design"
    assert first["text"]
    assert first["score"] == 0.92

    assert len(data["provenance"]) == 2
    assert data["provenance"][0]["source_uri"] == "git://docs/payment.md"
    assert data["provenance"][0]["source_version"] == "v3"

    assert data["confidence"]  # present (coarse band)
    assert data["route"] == "graph"
    assert data["policy"] == {"tenant": "acme", "clearance_applied": "INTERNAL"}


def test_artifact_validates_against_pinned_a2a_schema():
    """The produced artifact must round-trip through the pinned SDK's Artifact model."""
    artifact, _state, _reason = build_grounded_artifact(
        _grounded_result(), tenant="acme", clearance="INTERNAL"
    )
    parsed = a2a_types.Artifact.model_validate(artifact)
    assert len(parsed.parts) == 2


def test_no_evidence_maps_to_failed_state_never_a_confident_answer():
    """The guard: a no-evidence response yields TASK failed + reason, no confident answer."""
    no_evidence = AnswerResult(
        answer="제공된 문서에서 해당 정보를 찾을 수 없습니다.",
        evidence_snippets=[],
        provenance=[],
        route_used="vector",
    )
    artifact, state, reason = build_grounded_artifact(
        no_evidence, tenant="acme", clearance="INTERNAL"
    )

    assert state == a2a_types.TaskState.failed.value  # "failed", not an invented state
    assert reason is not None and "근거" in reason
    # The data part still carries the (empty) evidence shape — never omitted.
    data = _data_part(artifact)
    assert data["evidence"] == []


def test_evidence_was_retrieved_but_llm_failed_still_carries_evidence():
    """LLM failure with evidence present is still grounded (completed), confidence floored."""
    llm_failed = AnswerResult(
        answer="답변을 생성할 수 없습니다. 아래 근거를 직접 확인해주세요.",
        evidence_snippets=[
            {"chunk_rid": "c1", "doc_title": "D", "section_path": "S",
             "source_uri": "git://d.md", "text": "근거", "score": 0.5},
        ],
        provenance=[{"doc_rid": "doc_d", "source_uri": "git://d.md", "source_version": "v1"}],
        route_used="vector",
        llm_failed=True,
    )
    artifact, state, reason = build_grounded_artifact(
        llm_failed, tenant="acme", clearance="INTERNAL"
    )
    assert state == a2a_types.TaskState.completed.value
    data = _data_part(artifact)
    assert len(data["evidence"]) == 1
    assert data["confidence"] == "LOW"  # llm failure floors confidence


def test_confidence_is_a_deterministic_band_from_evidence_count():
    """System decides (deterministic), LLM narrates: confidence is a coarse, derived band."""
    def result_with(n: int) -> AnswerResult:
        return AnswerResult(
            answer="ok",
            evidence_snippets=[
                {"chunk_rid": f"c{i}", "doc_title": "D", "section_path": "S",
                 "source_uri": f"git://d{i}.md", "text": "t", "score": 0.9}
                for i in range(n)
            ],
            provenance=[{"doc_rid": "d", "source_uri": "git://d.md", "source_version": "v"}],
            route_used="vector",
        )

    _, _, _ = build_grounded_artifact(result_with(1), "t", "PUBLIC")
    bands = {
        n: _data_part(build_grounded_artifact(result_with(n), "t", "PUBLIC")[0])["confidence"]
        for n in (1, 2, 3)
    }
    assert bands == {1: "LOW", 2: "MEDIUM", 3: "HIGH"}
