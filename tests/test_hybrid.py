"""Hybrid 검색 테스트 — RRF fusion, route 판별."""

from khala.search.hybrid import _rrf_fusion
from khala.search.router import determine_route


class TestRRFFusion:
    def test_basic_fusion(self):
        bm25 = [("chunk_a", 1), ("chunk_b", 2), ("chunk_c", 3)]
        vector = [("chunk_b", 1), ("chunk_c", 2), ("chunk_d", 3)]
        fused = _rrf_fusion(bm25, vector, k=60, final_top_k=10)
        rids = [f["rid"] for f in fused]
        assert rids[0] == "chunk_b"

    def test_empty_inputs(self):
        assert _rrf_fusion([], [], k=60, final_top_k=10) == []

    def test_bm25_only(self):
        fused = _rrf_fusion([("chunk_a", 1)], [], k=60, final_top_k=10)
        assert len(fused) == 1
        assert fused[0]["vector_rank"] is None

    def test_top_k_limit(self):
        bm25 = [(f"chunk_{i}", i + 1) for i in range(20)]
        vector = [(f"chunk_{i+10}", i + 1) for i in range(20)]
        fused = _rrf_fusion(bm25, vector, k=60, final_top_k=5)
        assert len(fused) == 5


class TestRouteDetection:
    def test_auto_default(self):
        assert determine_route("일반 질문입니다") == "hybrid_only"

    def test_explicit_route(self):
        assert determine_route("질문", requested_route="graph_then_hybrid") == "graph_then_hybrid"

    def test_graph_keyword_ko(self):
        route = determine_route("결제 서비스의 의존성이 뭐야?")
        assert route in ("hybrid_then_graph", "graph_then_hybrid")

    def test_multiple_entities(self):
        route = determine_route(
            "결제 서비스와 알림 서비스",
            entity_names=["payment-service", "notification-service"],
        )
        assert route == "graph_then_hybrid"
