from __future__ import annotations

import pytest

pytest.importorskip("a2a.compat.v0_3.types")

from nexus.a2a.external_ingest_skill import (  # noqa: E402
    EXTERNAL_LABEL,
    ExternalIngestOutcome,
    build_external_ingest_artifact,
    compute_source_hash,
    extract_external_spec,
    validate_external_spec,
)


def _csf(body="# Title\n\n본문", source_tool="manifest", source_id="p-1", title="Payment PRD"):
    return {
        "id": f"ext-{source_tool}-{source_id}",
        "kind": "PRD",
        "title": title,
        "provenance": {
            "source_tool": source_tool,
            "source_id": source_id,
            "source_url": "https://manifest.app/p-1",
            "source_hash": compute_source_hash(body),
        },
        "body": body,
    }


def _params(csf):
    return {"message": {"parts": [{"kind": "data", "data": csf}]}}


def test_extract_returns_doc_when_all_required_present():
    csf = _csf()
    assert extract_external_spec(_params(csf)) == csf


def test_extract_returns_none_when_provenance_missing():
    csf = _csf()
    del csf["provenance"]["source_hash"]
    assert extract_external_spec(_params(csf)) is None


def test_validate_accepts_well_formed_csf():
    assert validate_external_spec(_csf()) is None


def test_validate_rejects_id_not_matching_provenance():
    csf = _csf()
    csf["id"] = "ext-wrong-id"
    assert "id must be" in validate_external_spec(csf)


def test_validate_rejects_source_hash_mismatch():
    csf = _csf()
    csf["body"] = "tampered body"  # hash no longer matches
    assert "source_hash" in validate_external_spec(csf)


def test_build_artifact_completed_carries_labels_and_never_echoes_body():
    csf = _csf(body="비밀 본문")
    outcome = ExternalIngestOutcome(
        resource_rid="doc_x", labels=[EXTERNAL_LABEL], chunks_indexed=3,
        idempotent_hit=False, source_hash=csf["provenance"]["source_hash"],
    )
    artifact_json, state, reason = build_external_ingest_artifact(outcome, csf, "acme")
    assert state == "completed"
    assert reason is None
    blob = repr(artifact_json)
    assert EXTERNAL_LABEL in blob
    assert "비밀 본문" not in blob


def test_build_artifact_failed_on_error():
    outcome = ExternalIngestOutcome(
        resource_rid="", labels=[], chunks_indexed=0, idempotent_hit=False,
        source_hash="h", error="boom",
    )
    _aj, state, reason = build_external_ingest_artifact(outcome, _csf(), "acme")
    assert state == "failed"
    assert reason == "boom"
