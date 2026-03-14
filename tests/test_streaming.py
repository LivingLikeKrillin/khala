"""SSE 스트리밍 테스트 — 이벤트 파싱, Evidence 조립."""

import json

from khala.search.evidence_packet import (
    EvidenceSnippet,
    EvidencePacket,
    Provenance,
    assemble_packet,
    format_for_llm,
)
from khala.search.hybrid import SearchHit
from khala.repositories.graph import SubGraph, EdgeResult, ObservedEdgeResult


class TestSSEEventFormat:
    """SSE 이벤트 문자열이 올바른 형식인지 검증."""

    def _make_sse_event(self, event_type, data):
        """api.py의 SSE 생성 방식 모방."""
        return f"event: {event_type}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    def test_evidence_event(self):
        data = {
            "evidence_snippets": [{"chunk_rid": "c1", "doc_title": "문서"}],
            "provenance": [{"doc_rid": "d1", "source_uri": "git://test"}],
            "route_used": "hybrid_only",
        }
        event = self._make_sse_event("evidence", data)
        assert event.startswith("event: evidence\n")
        assert "data: " in event
        assert event.endswith("\n\n")
        parsed = json.loads(event.split("data: ")[1].strip())
        assert parsed["route_used"] == "hybrid_only"

    def test_answer_delta_event(self):
        event = self._make_sse_event("answer_delta", {"text": "결제 서비스는 "})
        assert "answer_delta" in event
        parsed = json.loads(event.split("data: ")[1].strip())
        assert parsed["text"] == "결제 서비스는 "

    def test_done_event(self):
        event = self._make_sse_event("done", {"timing_ms": {"total_ms": 1234}})
        parsed = json.loads(event.split("data: ")[1].strip())
        assert parsed["timing_ms"]["total_ms"] == 1234

    def test_error_event(self):
        event = self._make_sse_event("error", {"error": "DB 연결 실패"})
        parsed = json.loads(event.split("data: ")[1].strip())
        assert parsed["error"] == "DB 연결 실패"

    def test_korean_in_sse(self):
        """한국어 문자열이 ensure_ascii=False로 올바르게 인코딩되는지."""
        event = self._make_sse_event("answer_delta", {"text": "한국어 답변입니다"})
        assert "한국어 답변입니다" in event

    def test_graph_event(self):
        data = {
            "center": "payment-service",
            "designed_edges": [
                {"type": "CALLS", "from": "payment-service", "to": "notification-service", "confidence": 0.9}
            ],
            "observed_edges": [],
        }
        event = self._make_sse_event("graph", data)
        parsed = json.loads(event.split("data: ")[1].strip())
        assert parsed["center"] == "payment-service"
        assert len(parsed["designed_edges"]) == 1


class TestEvidenceForStreaming:
    """스트리밍 엔드포인트에서 evidence 직렬화 검증."""

    def _make_hits(self):
        return [
            SearchHit(
                rid="c1", doc_rid="d1", doc_title="결제 설계",
                section_path="아키텍처 > 결제", source_uri="docs/payment.md",
                source_version="abc123",
                snippet="결제 서비스는 payment.completed 토픽을 발행한다",
                score=0.92, classification="INTERNAL",
            ),
            SearchHit(
                rid="c2", doc_rid="d2", doc_title="API 명세",
                section_path="결제 API", source_uri="docs/api-spec.md",
                source_version="def456",
                snippet="POST /payments → 결제 처리",
                score=0.78, classification="INTERNAL",
            ),
        ]

    def test_evidence_snippet_serialization(self):
        hits = self._make_hits()
        packet = assemble_packet(hits)
        snippets = [
            {
                "chunk_rid": s.chunk_rid,
                "doc_title": s.doc_title,
                "section_path": s.section_path,
                "source_uri": s.source_uri,
                "text": s.text,
                "score": s.score,
            }
            for s in packet.snippets
        ]
        assert len(snippets) == 2
        assert snippets[0]["doc_title"] == "결제 설계"
        # JSON 직렬화 가능한지 확인
        serialized = json.dumps(snippets, ensure_ascii=False)
        assert "결제 설계" in serialized

    def test_provenance_serialization(self):
        hits = self._make_hits()
        packet = assemble_packet(hits)
        prov = [
            {"doc_rid": p.doc_rid, "source_uri": p.source_uri, "source_version": p.source_version}
            for p in packet.provenance
        ]
        assert len(prov) == 2
        assert prov[0]["source_version"] == "abc123"

    def test_graph_findings_serialization(self):
        graph = SubGraph(
            center_rid="ent_abc", center_name="payment-service",
            edges=[EdgeResult(
                rid="e1", edge_type="CALLS", from_rid="ent_a", from_name="payment-service",
                to_rid="ent_b", to_name="notification-service",
                confidence=0.9, source_category="DESIGNED", hop=1,
            )],
            observed_edges=[ObservedEdgeResult(
                rid="o1", edge_type="CALLS_OBSERVED", from_rid="ent_a", from_name="payment-service",
                to_rid="ent_b", to_name="notification-service",
                call_count=1500, error_rate=0.02, latency_p95=120.5,
                last_seen_at="2026-03-15T00:00:00", sample_trace_ids=["trace-001"],
                trace_query_ref="tempo://query/abc",
            )],
        )
        data = {
            "center": graph.center_name,
            "designed_edges": [
                {"type": e.edge_type, "from": e.from_name, "to": e.to_name, "confidence": e.confidence}
                for e in graph.edges
            ],
            "observed_edges": [
                {"type": o.edge_type, "from": o.from_name, "to": o.to_name,
                 "call_count": o.call_count, "error_rate": o.error_rate}
                for o in graph.observed_edges
            ],
        }
        serialized = json.dumps(data, ensure_ascii=False)
        assert "payment-service" in serialized
        assert "1500" in serialized
