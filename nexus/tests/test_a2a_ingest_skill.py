"""ingest_governed_doc artifact mapping (Phase 3, SPEC §5.2, §5.4).

Maps an ingest outcome to an A2A artifact: a successful ingest -> completed task with a
provenance summary (resource_rid, classification, approved_hash, idempotent_hit) and the
document body NEVER echoed back; a quarantined/failed ingest -> failed task + reason.
"""

from __future__ import annotations

import a2a.compat.v0_3.types as a2a_types

from nexus.a2a.ingest_skill import (
    IngestOutcome,
    build_ingest_artifact,
    extract_governed_doc,
)

_DOC = {
    "id": "SPEC-x", "title": "X", "status": "approved", "approved_by": "u",
    "content_hash": "sha256:abc", "body": "# X\n비밀: 본문", "source": "specs/SPEC-x.md",
}


def _data(artifact: dict) -> dict:
    return [p["data"] for p in artifact["parts"] if p.get("kind") == "data"][0]


def test_successful_ingest_maps_to_completed_with_provenance():
    outcome = IngestOutcome(
        resource_rid="doc_123", classification="INTERNAL", chunks_indexed=4,
        quarantined=False, approved_hash="sha256:abc", idempotent_hit=False,
    )
    artifact, state, reason = build_ingest_artifact(outcome, _DOC, tenant="acme")

    assert state == a2a_types.TaskState.completed.value
    assert reason is None
    data = _data(artifact)
    assert data["resource_rid"] == "doc_123"
    assert data["classification"] == "INTERNAL"
    assert data["approved_hash"] == "sha256:abc"
    assert data["idempotent_hit"] is False
    assert data["chunks_indexed"] == 4
    assert data["doc_id"] == "SPEC-x"
    # the document body is never echoed back over A2A
    blob = str(artifact)
    assert "비밀" not in blob and "본문" not in blob


def test_artifact_validates_against_pinned_schema():
    outcome = IngestOutcome("doc_1", "INTERNAL", 1, False, "sha256:abc", False)
    artifact, _s, _r = build_ingest_artifact(outcome, _DOC, tenant="acme")
    assert len(a2a_types.Artifact.model_validate(artifact).parts) == 2


def test_quarantined_ingest_maps_to_failed():
    outcome = IngestOutcome(
        resource_rid="", classification="INTERNAL", chunks_indexed=0,
        quarantined=True, approved_hash="sha256:abc", idempotent_hit=False,
    )
    artifact, state, reason = build_ingest_artifact(outcome, _DOC, tenant="acme")
    assert state == a2a_types.TaskState.failed.value
    assert reason is not None and ("quarantine" in reason.lower() or "격리" in reason)
    assert _data(artifact)["quarantined"] is True


def test_idempotent_hit_surfaced():
    outcome = IngestOutcome("doc_1", "INTERNAL", 0, False, "sha256:abc", True)
    artifact, state, _r = build_ingest_artifact(outcome, _DOC, tenant="acme")
    assert state == a2a_types.TaskState.completed.value
    assert _data(artifact)["idempotent_hit"] is True


def test_extract_governed_doc_from_message():
    params = {"message": {"parts": [{"kind": "data", "data": _DOC}]}}
    doc = extract_governed_doc(params)
    assert doc is not None and doc["id"] == "SPEC-x"


def test_extract_governed_doc_rejects_incomplete_payload():
    params = {"message": {"parts": [{"kind": "data", "data": {"id": "x"}}]}}  # missing fields
    assert extract_governed_doc(params) is None
    assert extract_governed_doc({"message": {"parts": [{"kind": "text", "text": "hi"}]}}) is None
