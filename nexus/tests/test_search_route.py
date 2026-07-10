"""`route` 는 다리를 고르는가 — SPEC-nexus-search-recall §4.2, §6.

`route` 는 그래프 보강만 게이트했다. `keyword_only` 든 `vector_only` 든 BM25 와 벡터가 **언제나
둘 다** 돌았고, `route_used` 는 받은 값을 그대로 되돌려 주어 호출자에게 "당신 선택이 반영됐다"
고 말했다. 없는 손잡이를 API·MCP·CLI 가 광고했다.

그래서 이 테스트는 `route_used` 를 읽지 않는다. **각 다리가 실제로 몇 번 불렸는지 센다.**
거짓말을 한 바로 그 필드로 거짓말을 검증할 수는 없다.
"""

from __future__ import annotations

import pytest

from nexus.search import hybrid


@pytest.fixture
def legs(monkeypatch):
    """BM25/벡터 다리를 세는 스파이. DB 도 Ollama 도 필요 없다."""
    calls = {"bm25": 0, "vector": 0}

    async def fake_bm25(query, tenant, clearance, top_k=20):
        calls["bm25"] += 1
        return [("chunk_a", 1)]

    async def fake_vector(query, svc, tenant, clearance, top_k=20):
        calls["vector"] += 1
        return [("chunk_b", 1)]

    async def fake_enrich(fused, tenant):
        return []

    monkeypatch.setattr(hybrid, "_bm25_search", fake_bm25)
    monkeypatch.setattr(hybrid, "_vector_search", fake_vector)
    monkeypatch.setattr(hybrid, "_enrich_hits", fake_enrich)
    return calls


class _Svc:
    """EmbeddingService 자리표시자 — 벡터 다리가 도는지만 본다."""


@pytest.mark.parametrize(
    ("route", "bm25", "vector"),
    [
        ("keyword_only", 1, 0),
        ("vector_only", 0, 1),
        ("hybrid_only", 1, 1),
        ("hybrid_then_graph", 1, 1),
        ("graph_then_hybrid", 1, 1),
    ],
)
async def test_each_route_runs_exactly_the_legs_it_names(legs, route, bm25, vector):
    await hybrid.hybrid_search("질의", embedding_svc=_Svc(), route=route)
    assert (legs["bm25"], legs["vector"]) == (bm25, vector), f"{route} 가 광고한 다리를 안 돌렸다"


async def test_keyword_only_issues_no_embedding_call(legs):
    """임베딩 호출은 느리고 돈이 든다. keyword_only 를 고른 사람은 그걸 피하려던 것이다."""
    await hybrid.hybrid_search("질의", embedding_svc=_Svc(), route="keyword_only")
    assert legs["vector"] == 0


async def test_vector_only_without_an_embedding_service_returns_nothing(legs):
    """조용히 BM25 검색이 되어 `route_used='vector_only'` 라고 보고하면 안 된다 (§4.2)."""
    res = await hybrid.hybrid_search("질의", embedding_svc=None, route="vector_only")
    assert legs["bm25"] == 0 and legs["vector"] == 0
    assert res.hits == []


async def test_an_unknown_route_is_refused_not_silently_treated_as_hybrid(legs):
    with pytest.raises(ValueError, match="unknown_route"):
        await hybrid.hybrid_search("질의", embedding_svc=_Svc(), route="nope")
    assert legs == {"bm25": 0, "vector": 0}


async def test_the_error_names_the_routes_that_do_exist():
    with pytest.raises(ValueError) as e:
        await hybrid.hybrid_search("질의", route="nope")
    for r in ("keyword_only", "vector_only", "hybrid_only"):
        assert r in str(e.value)
