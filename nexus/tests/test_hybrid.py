"""Hybrid 검색 테스트 — RRF fusion, route 판별, 멀티-엔티티 그래프 병합."""

import pytest

from nexus.repositories.graph import EdgeResult, ObservedEdgeResult, SubGraph
from nexus.search import hybrid
from nexus.search.hybrid import _merge_subgraphs, _rrf_fusion
from nexus.search.router import determine_route


def _edge(rid: str, from_name: str, to_name: str, hop: int = 1) -> EdgeResult:
    return EdgeResult(
        rid=rid, edge_type="CALLS",
        from_rid=f"entity_{from_name}", from_name=from_name,
        to_rid=f"entity_{to_name}", to_name=to_name,
        confidence=0.6, source_category="DESIGNED", hop=hop,
    )


def _observed(rid: str, from_name: str, to_name: str) -> ObservedEdgeResult:
    return ObservedEdgeResult(
        rid=rid, edge_type="CALLS_OBSERVED",
        from_rid=f"entity_{from_name}", from_name=from_name,
        to_rid=f"entity_{to_name}", to_name=to_name,
        call_count=10, error_rate=0.0, latency_p95=100.0,
        last_seen_at="2026-06-19", sample_trace_ids=[], trace_query_ref="",
    )


def _subgraph(center: str, edges: list[EdgeResult],
              observed: list[ObservedEdgeResult] | None = None) -> SubGraph:
    return SubGraph(
        center_rid=f"entity_{center}", center_name=center,
        edges=edges, observed_edges=observed or [],
    )


class TestRRFFusion:
    def test_basic_fusion(self):
        bm25 = [("chunk_a", 1), ("chunk_b", 2), ("chunk_c", 3)]
        vector = [("chunk_b", 1), ("chunk_c", 2), ("chunk_d", 3)]
        fused = _rrf_fusion(bm25, vector, k=60)
        rids = [f["rid"] for f in fused]
        assert rids[0] == "chunk_b"

    def test_empty_inputs(self):
        assert _rrf_fusion([], [], k=60) == []

    def test_bm25_only(self):
        fused = _rrf_fusion([("chunk_a", 1)], [], k=60)
        assert len(fused) == 1
        assert fused[0]["vector_rank"] is None

    def test_returns_full_deduped_union_no_cut(self):
        # 컷은 이제 _diversify 몫 — fusion 은 전체 병합 리스트를 돌려준다.
        bm25 = [(f"chunk_{i}", i + 1) for i in range(20)]
        vector = [(f"chunk_{i+10}", i + 1) for i in range(20)]
        fused = _rrf_fusion(bm25, vector, k=60)
        assert len(fused) == 30                       # chunk_0..29 의 합집합


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


class TestMergeSubgraphs:
    def test_empty_returns_none(self):
        assert _merge_subgraphs([]) is None

    def test_filters_none_entries(self):
        sg = _subgraph("payment", [_edge("e1", "payment", "order")])
        merged = _merge_subgraphs([None, sg, None])
        assert merged is not None
        assert merged.center_name == "payment"
        assert len(merged.edges) == 1

    def test_single_subgraph_passthrough(self):
        sg = _subgraph("payment", [_edge("e1", "payment", "order")])
        merged = _merge_subgraphs([sg])
        assert merged.center_name == "payment"
        assert {e.rid for e in merged.edges} == {"e1"}

    def test_unions_edges_from_multiple_entities(self):
        # 두 엔티티(payment, notification)에서 펼친 서로 다른 edge가 합쳐진다
        sg1 = _subgraph("payment", [_edge("e1", "payment", "order")])
        sg2 = _subgraph("notification", [_edge("e2", "notification", "user")])
        merged = _merge_subgraphs([sg1, sg2])
        assert {e.rid for e in merged.edges} == {"e1", "e2"}

    def test_center_is_first_subgraph(self):
        sg1 = _subgraph("payment", [_edge("e1", "payment", "order")])
        sg2 = _subgraph("notification", [_edge("e2", "notification", "user")])
        assert _merge_subgraphs([sg1, sg2]).center_name == "payment"
        assert _merge_subgraphs([sg2, sg1]).center_name == "notification"

    def test_dedups_edge_by_rid_keeping_smaller_hop(self):
        # 같은 edge가 한 탐색에선 2-hop, 다른 탐색에선 1-hop으로 잡히면 가까운 쪽 유지
        sg1 = _subgraph("payment", [_edge("shared", "payment", "order", hop=2)])
        sg2 = _subgraph("order", [_edge("shared", "payment", "order", hop=1)])
        merged = _merge_subgraphs([sg1, sg2])
        assert len(merged.edges) == 1
        assert merged.edges[0].hop == 1

    def test_dedups_observed_edge_by_rid(self):
        obs = _observed("o1", "payment", "order")
        sg1 = _subgraph("payment", [], [obs])
        sg2 = _subgraph("order", [], [obs])
        merged = _merge_subgraphs([sg1, sg2])
        assert len(merged.observed_edges) == 1


# ── 0건의 원인을 가른다 (2026-08-13 슬랙 파일럿에서 관측) ─────────────────────────
#
# "질의가 안 맞아서 0건" 과 "이 등급으로 볼 문서가 하나도 없어서 0건" 은 다른 사실이고 고칠
# 사람도 다르다. 그 둘이 섞여 있던 동안 봇은 후자에 대고 "인덱싱된 문서에서 답을 찾지
# 못했습니다" 라고 답했다 — 뒤진 문서가 0건이었으므로 거짓이다.

class _Row(dict):
    """asyncpg.Record 처럼 __getitem__ 으로 읽히는 최소 대역."""


@pytest.mark.parametrize("total,visible,expected", [
    (0, 0, False),    # 코퍼스가 비었다 — 설정 결함이 아니다 (EMPTY_CORPUS 가 맡는다)
    (116, 5, False),  # 보이는 문서가 있다 — 그냥 못 찾은 것이다
    (116, 0, True),   # 문서는 있는데 하나도 안 보인다 — 설정 결함
])
async def test_visibility_gap_is_only_the_third_case(monkeypatch, total, visible, expected):
    async def fake(query, *args):
        return _Row(total=total, visible=visible)
    monkeypatch.setattr(hybrid.db, "fetch_one", fake)
    assert await hybrid._no_visible_documents("default", "PUBLIC") is expected


async def test_a_failed_probe_never_claims_a_config_defect(monkeypatch):
    """진단이 못 돌면 False 다. 모르는 것을 단정하면 멀쩡한 검색 실패가 설정 결함으로 보고된다."""
    async def boom(query, *args):
        raise RuntimeError("db down")
    monkeypatch.setattr(hybrid.db, "fetch_one", boom)
    assert await hybrid._no_visible_documents("default", "PUBLIC") is False


async def test_the_probe_runs_only_when_there_are_no_hits(monkeypatch):
    """결과가 있는 요청에는 COUNT 두 개를 붙이지 않는다 — 진단 비용은 0건에만 든다.

    배선을 행동으로 건다: `hybrid_search` 가 이 함수를 **부르는지**를 본다. 예전 결함 넷 중
    셋이 '함수는 맞는데 아무도 안 부른다' 였다.
    """
    calls = []

    async def spy(tenant, clearance):
        calls.append((tenant, clearance))
        return True

    monkeypatch.setattr(hybrid, "_no_visible_documents", spy)

    async def no_hits(*a, **k):
        return []
    monkeypatch.setattr(hybrid, "_bm25_search", no_hits)
    monkeypatch.setattr(hybrid, "_vector_search", no_hits)

    r = await hybrid.hybrid_search("아무거나", tenant="t", clearance="PUBLIC", route="hybrid_only")
    assert r.hits == []
    assert calls == [("t", "PUBLIC")], "0건인데 가시성 진단을 안 불렀다"
    assert r.no_visible_documents is True
