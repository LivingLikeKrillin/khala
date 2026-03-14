"""Slack Bot 테스트 — 포매터, 쿼리 추출."""

from khala.slack.formatter import format_answer, format_error
from khala.slack.bot import _extract_query


class TestExtractQuery:
    def test_basic_mention(self):
        text = "<@U12345ABC> 결제 서비스 장애 원인?"
        assert _extract_query(text) == "결제 서비스 장애 원인?"

    def test_multiple_spaces(self):
        text = "<@U12345ABC>   payment service   "
        assert _extract_query(text) == "payment service"

    def test_no_mention(self):
        text = "직접 질문입니다"
        assert _extract_query(text) == "직접 질문입니다"

    def test_empty(self):
        assert _extract_query("") == ""
        assert _extract_query("<@U12345ABC>") == ""


class TestFormatAnswer:
    def _make_answer_data(self):
        return {
            "answer": "결제 서비스는 payment.completed 토픽을 발행합니다.",
            "evidence_snippets": [
                {
                    "chunk_rid": "c1",
                    "doc_title": "결제 설계 문서",
                    "section_path": "아키텍처 > 이벤트",
                    "source_uri": "docs/payment.md",
                    "text": "payment.completed 이벤트를 Kafka로 발행",
                    "score": 0.92,
                },
                {
                    "chunk_rid": "c2",
                    "doc_title": "API 명세",
                    "section_path": "결제 API",
                    "source_uri": "docs/api.md",
                    "text": "POST /payments 호출 시 결제 처리",
                    "score": 0.78,
                },
            ],
            "graph_findings": {
                "designed_edges": [
                    {"type": "PUBLISHES", "from": "payment-service", "to": "payment.completed", "confidence": 0.9}
                ],
                "observed_edges": [
                    {"type": "CALLS_OBSERVED", "from": "payment-service", "to": "notification-service", "calls": 1500}
                ],
            },
            "provenance": [
                {"doc_rid": "d1", "source_uri": "docs/payment.md", "source_version": "abc123"},
            ],
            "route_used": "hybrid_then_graph",
            "timing_ms": {"total_ms": 450, "bm25_ms": 30},
        }

    def test_blocks_structure(self):
        blocks = format_answer(self._make_answer_data())
        assert isinstance(blocks, list)
        assert len(blocks) >= 2

        # 첫 블록: 답변 본문
        assert blocks[0]["type"] == "section"
        assert "결제 서비스" in blocks[0]["text"]["text"]

    def test_evidence_included(self):
        blocks = format_answer(self._make_answer_data())
        block_texts = " ".join(
            el.get("text", "")
            for b in blocks if b["type"] == "context"
            for el in b.get("elements", [])
        )
        assert "결제 설계 문서" in block_texts

    def test_graph_included(self):
        blocks = format_answer(self._make_answer_data())
        block_texts = " ".join(
            el.get("text", "")
            for b in blocks if b["type"] == "context"
            for el in b.get("elements", [])
        )
        assert "payment-service" in block_texts

    def test_provenance_included(self):
        blocks = format_answer(self._make_answer_data())
        block_texts = " ".join(
            el.get("text", "")
            for b in blocks if b["type"] == "context"
            for el in b.get("elements", [])
        )
        assert "docs/payment.md" in block_texts

    def test_long_answer_truncated(self):
        data = self._make_answer_data()
        data["answer"] = "긴 답변 " * 1000  # ~4000자
        blocks = format_answer(data)
        answer_text = blocks[0]["text"]["text"]
        assert len(answer_text) < 4100
        assert "생략" in answer_text

    def test_empty_answer(self):
        data = {"answer": "", "evidence_snippets": [], "provenance": []}
        blocks = format_answer(data)
        assert isinstance(blocks, list)
        assert len(blocks) >= 1

    def test_no_graph(self):
        data = self._make_answer_data()
        data["graph_findings"] = None
        blocks = format_answer(data)
        assert isinstance(blocks, list)

    def test_route_and_timing(self):
        blocks = format_answer(self._make_answer_data())
        last_texts = " ".join(
            el.get("text", "")
            for b in blocks if b["type"] == "context"
            for el in b.get("elements", [])
        )
        assert "hybrid_then_graph" in last_texts


class TestFormatError:
    def test_error_block(self):
        blocks = format_error("DB 연결 실패")
        assert len(blocks) == 1
        assert blocks[0]["type"] == "section"
        assert "DB 연결 실패" in blocks[0]["text"]["text"]
        assert "오류" in blocks[0]["text"]["text"]
