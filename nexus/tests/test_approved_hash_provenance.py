"""approved_hash rides the retrieval read path end-to-end (SPEC §5.4 read-back side).

The Phase 3 E2E (ecosystem `tests/`) found that `retrieve_grounded` provenance dropped the
`approved_hash` — so Observer's `SpecRef.approvedHash` could not resolve *via retrieval*. This
locks the field through every read-path hop: a `SearchHit` carrying `approved_hash` →
`assemble_packet` Provenance → `generate_answer` provenance dict → `build_grounded_artifact`
artifact provenance. Pure unit tests; no DB/LLM (the DB column `documents.content_hash` already
exists and is wired into the enrichment query, exercised by the DB-backed run).
"""

from __future__ import annotations

from nexus.a2a.mapping import build_grounded_artifact
from nexus.llm.answer import AnswerResult, generate_answer
from nexus.search.evidence_packet import assemble_packet
from nexus.search.hybrid import SearchHit

_HASH = "sha256:deadbeef"


def _data_part(artifact: dict) -> dict:
    return [p["data"] for p in artifact["parts"] if p.get("kind") == "data"][0]


async def test_assemble_packet_carries_approved_hash_from_hit():
    hits = [SearchHit(rid="c1", doc_rid="d1", doc_title="T", source_uri="git://d.md",
                      snippet="x", score=0.9, classification="INTERNAL", approved_hash=_HASH)]
    packet = await assemble_packet(hits)
    assert packet.provenance[0].approved_hash == _HASH


async def test_generate_answer_provenance_dict_includes_approved_hash():
    hits = [SearchHit(rid="c1", doc_rid="d1", doc_title="T", source_uri="git://d.md",
                      snippet="x", score=0.9, classification="INTERNAL", approved_hash=_HASH)]
    # no snippets path is fine — provenance is built from the packet regardless of the LLM call
    packet = await assemble_packet(hits)
    result = await generate_answer(query="q", packet=packet, llm_svc=None, route_used="vector")
    assert result.provenance[0]["approved_hash"] == _HASH


def test_build_grounded_artifact_provenance_includes_approved_hash():
    result = AnswerResult(
        answer="ok",
        evidence_snippets=[{"chunk_rid": "c1", "doc_title": "T", "section_path": "S",
                            "source_uri": "git://d.md", "text": "t", "score": 0.9}],
        provenance=[{"doc_rid": "d1", "source_uri": "git://d.md", "source_version": "v1",
                     "approved_hash": _HASH}],
        route_used="vector",
    )
    artifact, _state, _reason = build_grounded_artifact(result, tenant="acme", clearance="INTERNAL")
    assert _data_part(artifact)["provenance"][0]["approved_hash"] == _HASH


def test_provenance_approved_hash_defaults_empty_when_absent():
    """Back-compat: a provenance dict without approved_hash maps to '' (never KeyError)."""
    result = AnswerResult(
        answer="ok",
        evidence_snippets=[{"chunk_rid": "c1", "doc_title": "T", "section_path": "S",
                            "source_uri": "git://d.md", "text": "t", "score": 0.9}],
        provenance=[{"doc_rid": "d1", "source_uri": "git://d.md", "source_version": "v1"}],
        route_used="vector",
    )
    artifact, _state, _reason = build_grounded_artifact(result, tenant="t", clearance="PUBLIC")
    assert _data_part(artifact)["provenance"][0]["approved_hash"] == ""
