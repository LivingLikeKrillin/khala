"""The grounding bridge: ``AnswerResult`` -> A2A task artifact (SPEC §5.4).

This is the heart of the spike. The mapping is **total** and **lossless** for the
grounding fields. A response with no evidence maps to the A2A ``failed`` state — never to
a confident answer without evidence (invariant §6.1). "System decides, LLM narrates":
``confidence`` is a deterministic coarse band derived here, not asserted by the LLM.

Shapes are bound to the pinned A2A SDK (``a2a-sdk==1.1.0``); the JSON-RPC wire form of the
spec types lives in ``a2a.compat.v0_3.types``. The contract tests, not these field names,
are the spec (SPEC §9).
"""

from __future__ import annotations

import uuid

from a2a.compat.v0_3.types import Artifact, DataPart, TaskState, TextPart

from nexus.llm.answer import AnswerResult

# Plain-text reason attached to a failed (no-evidence) task.
NO_EVIDENCE_REASON = "답변을 생성할 수 없습니다 — 근거 부족"


def derive_confidence(evidence_count: int, llm_failed: bool) -> str:
    """A deterministic, coarse confidence band — system-decided, never LLM-asserted.

    More independent corroborating sources ⇒ higher confidence. An LLM failure floors the
    band to ``LOW`` (the evidence is real, but the narration is not). Resolves the SPEC §10
    open question in favour of a coarse band over a raw score (whose scale is route-specific
    and not meaningfully comparable across BM25/vector/graph).
    """
    if evidence_count <= 0:
        return "LOW"
    if llm_failed:
        return "LOW"
    if evidence_count >= 3:
        return "HIGH"
    if evidence_count == 2:
        return "MEDIUM"
    return "LOW"


def _evidence_payload(result: AnswerResult) -> list[dict]:
    """Map ``evidence_snippets`` -> the data part ``.evidence[]`` shape (SPEC §5.4)."""
    return [
        {
            "doc_title": s.get("doc_title", ""),
            "section_path": s.get("section_path", ""),
            "text": s.get("text", ""),
            "score": s.get("score"),
            "source_uri": s.get("source_uri", ""),
        }
        for s in result.evidence_snippets
    ]


def build_grounded_artifact(
    result: AnswerResult,
    tenant: str,
    clearance: str,
) -> tuple[dict, str, str | None]:
    """Map a Nexus grounded answer to an A2A artifact + task state.

    Returns ``(artifact_json, task_state, reason)`` where ``artifact_json`` is a
    spec-shaped (camelCase) dict that round-trips through the SDK ``Artifact`` model,
    ``task_state`` is the A2A ``TaskState`` wire value, and ``reason`` is a plain-text
    failure reason (only when the task failed, else ``None``).

    - **No evidence ⇒ ``failed``** with ``NO_EVIDENCE_REASON``; a confident answer is never
      emitted without ≥1 evidence snippet. The (empty) evidence shape is still attached.
    - **Evidence present ⇒ ``completed``**, even if the LLM narration failed (the answer
      text then carries the fallback + raw evidence, and confidence is floored to LOW).
    """
    evidence = _evidence_payload(result)
    has_evidence = len(evidence) > 0

    data = {
        "evidence": evidence,
        "provenance": [
            {
                "source_uri": p.get("source_uri", ""),
                "source_version": p.get("source_version", ""),
                "doc_rid": p.get("doc_rid", ""),
                # SPEC §5.4: the accountable-review stamp, so a consumer (Probe's
                # SpecRef.approvedHash) can verify retrieval against Arbiter's hash.
                "approved_hash": p.get("approved_hash", ""),
            }
            for p in result.provenance
        ],
        "confidence": derive_confidence(len(evidence), result.llm_failed),
        "route": result.route_used,
        "policy": {"tenant": tenant, "clearance_applied": clearance},
    }

    artifact = Artifact(
        artifact_id=uuid.uuid4().hex,
        name="grounded_answer",
        parts=[TextPart(text=result.answer), DataPart(data=data)],
    )
    artifact_json = artifact.model_dump(mode="json", by_alias=True, exclude_none=True)

    if has_evidence:
        return artifact_json, TaskState.completed.value, None
    return artifact_json, TaskState.failed.value, NO_EVIDENCE_REASON
