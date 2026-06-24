from __future__ import annotations

from nexus.search.evidence_packet import assemble_packet, format_for_llm
from nexus.search.hybrid import SearchHit


def _hit(doc_type="DESIGN"):
    return SearchHit(
        rid="chunk_1", doc_rid="doc_1", doc_title="결제 설계",
        section_path="개요", source_uri="git:payment.md",
        snippet="결제 서비스 명세", score=0.9, classification="INTERNAL",
        doc_type=doc_type,
    )


def test_assemble_packet_propagates_doc_type():
    packet = assemble_packet([_hit("DESIGN")])
    assert packet.snippets[0].doc_type == "DESIGN"


def test_format_for_llm_surfaces_doc_type():
    out = format_for_llm(assemble_packet([_hit("ADR")]))
    assert "ADR" in out


def test_assemble_packet_handles_missing_doc_type():
    packet = assemble_packet([_hit("")])
    assert packet.snippets[0].doc_type == ""
