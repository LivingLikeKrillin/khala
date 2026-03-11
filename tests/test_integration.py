"""통합 테스트 — Chunking, Evidence Packet, Search Text."""

from khala.ingest.chunker import chunk_document, _estimate_tokens
from khala.models.chunk import Chunk
from khala.search.evidence_packet import assemble_packet, format_for_llm
from khala.search.hybrid import SearchHit
from khala.utils import get_search_text


class TestChunker:
    def test_empty_document(self):
        assert chunk_document("") == []

    def test_single_section(self):
        chunks = chunk_document("# 제목\n\n이것은 짧은 문서입니다.")
        assert len(chunks) >= 1
        assert chunks[0].section_path == "제목"

    def test_multiple_sections(self):
        content = "# H1\n\n내용1\n\n## H2\n\n내용2\n\n# H1-2\n\n내용3"
        chunks = chunk_document(content)
        assert len(chunks) >= 2

    def test_code_block_preserved(self):
        content = "# 코드\n\n```python\ndef hello():\n    print('hello')\n```"
        chunks = chunk_document(content)
        assert any("def hello" in c.chunk_text for c in chunks)


class TestTokenEstimation:
    def test_korean(self):
        assert _estimate_tokens("결제 서비스가 알림을 전송한다", "ko") > 0

    def test_english(self):
        assert _estimate_tokens("Payment service sends notifications", "en") > 0

    def test_empty(self):
        assert _estimate_tokens("", "ko") == 0


class TestGetSearchText:
    def test_with_section_path(self):
        chunk = Chunk(rid="test", rtype="chunk", section_path="H1 > H2", chunk_text="본문 텍스트")
        result = get_search_text(chunk)
        assert "[H1 > H2]" in result
        assert "본문 텍스트" in result

    def test_with_context_prefix(self):
        chunk = Chunk(
            rid="test", rtype="chunk", section_path="H1", chunk_text="본문",
            context_prefix="[컨텍스트: 결제]",
        )
        result = get_search_text(chunk)
        assert "[컨텍스트: 결제]" in result
        assert "[H1]" not in result


class TestEvidencePacket:
    def test_assemble_basic(self):
        hits = [SearchHit(
            rid="c1", doc_rid="d1", doc_title="설계문서",
            section_path="아키텍처", source_uri="docs/design.md",
            snippet="내용", score=0.85, classification="INTERNAL",
        )]
        packet = assemble_packet(hits)
        assert len(packet.snippets) == 1
        assert len(packet.provenance) == 1

    def test_format_for_llm(self):
        hits = [SearchHit(
            rid="c1", doc_rid="d1", doc_title="설계문서",
            section_path="아키텍처", source_uri="docs/design.md",
            snippet="내용", score=0.85, classification="INTERNAL",
        )]
        text = format_for_llm(assemble_packet(hits))
        assert "근거" in text
        assert "설계문서" in text

    def test_dedup_provenance(self):
        hits = [
            SearchHit(rid="c1", doc_rid="d1", doc_title="T", snippet="a", score=0.9, classification="INTERNAL"),
            SearchHit(rid="c2", doc_rid="d1", doc_title="T", snippet="b", score=0.8, classification="INTERNAL"),
        ]
        packet = assemble_packet(hits)
        assert len(packet.provenance) == 1
