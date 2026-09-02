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

class _Row(dict):
    """asyncpg.Record 처럼 __getitem__ 으로 읽히는 최소 대역."""


async def test_the_search_function_never_runs_the_visibility_query(monkeypatch):
    """`hybrid_search` 는 이 진단을 부르지 않는다 — 첫 판이 그렇게 했다가 CI 를 40분 세웠다.

    `hybrid_search` 는 DB 없이 도는 단위 테스트 수백 개가 부르는 함수다. 거기에 DB 왕복 하나를
    얹으면 죽은 이벤트 루프에 묶인 전역 asyncpg 풀을 집고, 커넥션이 열린 트랜잭션째 남아
    `documents` 에 AccessShareLock 을 쥔다 — 뒤따르는 모든 TRUNCATE 가 그 뒤에 줄을 선다.
    두 번째 판(응답 조립 + 타임아웃)도 같은 이유로 매달렸다: 붙들고 있던 것은 질의가 아니라
    커넥션이었다. 그래서 진단은 자기 엔드포인트에만 산다.
    """
    touched = []

    async def tripwire(query, *args):
        touched.append(query)
        return _Row(total=0, visible=0)
    monkeypatch.setattr(hybrid.db, "fetch_one", tripwire)

    async def no_hits(*a, **k):
        # 경로 계약 = (결과, 1위 원점수). 빈 결과의 원점수는 None 이다 (0.0 이 아니다).
        return [], None
    monkeypatch.setattr(hybrid, "_bm25_search", no_hits)
    monkeypatch.setattr(hybrid, "_vector_search", no_hits)

    r = await hybrid.hybrid_search("아무거나", tenant="t", clearance="PUBLIC", route="hybrid_only")
    assert r.hits == []
    assert touched == [], "검색 함수가 DB 진단을 돌렸다 — 스위트를 세우는 그 배선이다"


# ── 가중 채널 융합 (SPEC-nexus-multi-turn-retrieval §3.3, U3) ────────────────────
#
# 채널 = 무엇을 물었나(재작성/원문). 경로 = 어떻게 찾았나(BM25/vector). 축이 둘이고,
# 가중은 **채널당 한 번** 걸린다.

from nexus.search.hybrid import ChannelResults, fuse_channels  # noqa: E402


def test_one_channel_at_weight_one_is_exactly_the_old_fusion():
    """§4 I1 의 수치적 근거. 이력이 없으면 채널이 하나고, 그 결과는 예전과 글자 그대로 같다."""
    bm25 = [("a", 1), ("b", 2)]
    vector = [("b", 1), ("c", 2)]
    old = _rrf_fusion(bm25, vector, k=60)
    new = fuse_channels([ChannelResults(bm25=bm25, vector=vector, weight=1.0)], k=60)
    assert [(r["rid"], r["score"]) for r in old] == [(r["rid"], r["score"]) for r in new]


def test_the_weight_applies_once_per_channel_not_once_per_leg():
    """1.3 이 2.6 이 되면 안 된다 — 두 경로를 다 타는 채널은 그래도 채널 하나다."""
    one_leg = fuse_channels([ChannelResults(bm25=[("a", 1)], weight=2.0)], k=60)
    two_legs = fuse_channels(
        [ChannelResults(bm25=[("a", 1)], vector=[("a", 1)], weight=2.0)], k=60)
    unit = 1.0 / 62
    assert one_leg[0]["score"] == pytest.approx(2.0 * unit)
    assert two_legs[0]["score"] == pytest.approx(2.0 * (unit + unit))


def test_identical_channels_scale_every_score_and_change_no_order():
    """중복 제거의 실제 효과. "자동으로 강화된다" 는 산술적으로 거짓이다 (§3.3).

    두 채널의 질의가 같으면 순위 목록도 같고, 가중 합산은 **모든 문서에 같은 배수**를 곱한다.
    관측 가능한 유일한 변화는 절대 점수의 팽창이고, 그것은 §4 I6 이 다룬다.
    """
    ranks = [("a", 1), ("b", 2), ("c", 3)]
    single = fuse_channels([ChannelResults(bm25=ranks, weight=1.0)], k=60)
    doubled = fuse_channels([ChannelResults(bm25=ranks, weight=1.3),
                             ChannelResults(bm25=ranks, weight=0.5)], k=60)
    assert [r["rid"] for r in single] == [r["rid"] for r in doubled]
    for a, b in zip(single, doubled):
        assert b["score"] == pytest.approx(a["score"] * 1.8)


def test_a_low_weight_channel_still_puts_its_documents_in_the_result():
    """원 질문 채널이 보장하는 것은 **결과에 존재한다는 것**이지 다수결이 아니다 (§3.3)."""
    fused = fuse_channels([
        ChannelResults(bm25=[("rewritten_only", 1)], weight=1.3, name="rewritten"),
        ChannelResults(bm25=[("original_only", 1)], weight=0.5, name="original"),
    ], k=60)
    rids = [r["rid"] for r in fused]
    assert "original_only" in rids
    assert rids[0] == "rewritten_only", "가중이 큰 쪽이 앞선다"


def test_the_best_rank_per_leg_survives_across_channels():
    """칸은 둘인데 채널은 넷의 순위를 만든다 — 고르지 않으면 나중 채널이 앞 채널을 덮는다."""
    fused = fuse_channels([
        ChannelResults(bm25=[("a", 5)], name="rewritten"),
        ChannelResults(bm25=[("a", 2)], name="original"),
    ], k=60)
    assert fused[0]["bm25_rank"] == 2


def test_per_channel_ranks_are_kept_for_diagnosis():
    """SPEC §8("재작성이 mecab tsvector 텀을 흔드는가")은 이 값으로만 답할 수 있다."""
    fused = fuse_channels([
        ChannelResults(bm25=[("a", 1)], vector=[("a", 4)], name="rewritten"),
        ChannelResults(bm25=[("a", 7)], name="original"),
    ], k=60)
    assert fused[0]["channel_ranks"] == {"rewritten": {"bm25": 1, "vector": 4},
                                         "original": {"bm25": 7}}


# ── hybrid_search 가 채널을 실제로 태우는가 (§4 I1·I2) ──────────────────────────

from nexus.search import hybrid as _H  # noqa: E402


def _spy_legs(monkeypatch):
    """경로 호출을 가로채 **어떤 질의가 어느 경로로 갔는지** 본다."""
    calls = {"bm25": [], "vector": []}

    async def bm25(query, tenant, clearance, top_k=20):
        calls["bm25"].append(query)
        return [(f"c-{query}", 1)], 3.0

    async def vector(query, svc, tenant, clearance, top_k=20, column=None):
        calls["vector"].append(query)
        return [(f"v-{query}", 1)], 0.2

    monkeypatch.setattr(_H, "_bm25_search", bm25)
    monkeypatch.setattr(_H, "_vector_search", vector)

    async def enrich(fused, tenant, max_snippet_chars=300):
        return [_H.SearchHit(rid=r["rid"], doc_rid="d", score=r["score"]) for r in fused]
    monkeypatch.setattr(_H, "_enrich_hits", enrich)
    return calls


async def test_without_channels_each_leg_runs_once_on_the_query(monkeypatch):
    """§4 I1. 이력이 없으면 오늘과 같다 — 질의 하나, 경로 둘, 그게 전부다."""
    calls = _spy_legs(monkeypatch)
    await _H.hybrid_search("결제 토픽", embedding_svc=object(), route="hybrid_only")
    assert calls["bm25"] == ["결제 토픽"] and calls["vector"] == ["결제 토픽"]


async def test_both_channels_ride_both_legs(monkeypatch):
    """§3.3. 원 질문을 vector 에서 빼면 그것은 "언제나 융합에 있다" 가 아니게 된다."""
    calls = _spy_legs(monkeypatch)
    await _H.hybrid_search("무시됨", embedding_svc=object(), route="hybrid_only",
                           channels=[("재작성된 질의", 1.3), ("원문", 0.5)])
    assert calls["bm25"] == ["재작성된 질의", "원문"]
    assert calls["vector"] == ["재작성된 질의", "원문"]


async def test_the_original_channel_reaches_the_results(monkeypatch):
    """§4 I2. 재작성이 못 찾은 문서라도 원 질문이 찾았으면 결과에 있어야 한다."""
    _spy_legs(monkeypatch)
    r = await _H.hybrid_search("무시됨", embedding_svc=object(), route="hybrid_only",
                               channels=[("재작성", 1.3), ("원문", 0.5)])
    rids = [h.rid for h in r.hits]
    assert "c-원문" in rids and "v-원문" in rids


async def test_a_dead_rewriter_leaves_todays_result(monkeypatch):
    """§4 I2 의 degrade 경로. 재작성이 죽으면 원문 채널 하나만 남고, 그것이 오늘이다."""
    _spy_legs(monkeypatch)
    today = await _H.hybrid_search("원문", embedding_svc=object(), route="hybrid_only")
    degraded = await _H.hybrid_search("원문", embedding_svc=object(), route="hybrid_only",
                                      channels=[("원문", 1.0)])
    assert [h.rid for h in today.hits] == [h.rid for h in degraded.hits]
    assert [h.score for h in today.hits] == [h.score for h in degraded.hits]
