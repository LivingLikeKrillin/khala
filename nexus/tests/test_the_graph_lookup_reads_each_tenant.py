"""그래프 조회는 읽기 범위의 **테넌트마다** 묻는다 — 범위를 통째로 넘기지 않는다.

⛔ **왜 생겼나 (2026-10-01).** 읽기 범위는 2026-08-31 부터 튜플이다. 그래프 보강은 그 튜플을
`get_neighbors(tenant=…)` 에 그대로 넘겼고, 저장소는 테넌트를 문자열 하나로 받는다(`tenant = $2`,
`f_graph_neighbors` 의 text 인자). asyncpg 가 매번 `expected str, got tuple` 로 거절했고, 부른 쪽은
경고 한 줄(`graph_search_partial_failed`)만 남긴 채 빈 그래프를 돌려줬다 — 09-22 이후 라이브 로그에
99회. 간선이 없던 코퍼스라 결과는 안 바뀌었지만, 간선이 생기는 날 조용히 빠진다.

같은 부류가 08-31 에 절 채움에서 났고(`scope_sql.py` 머리말), 그때 만든 회귀 검사
(`test_read_scope_reaches_every_enrichment.py`)는 그래프를 안 돌려서 이것을 못 봤다.

⛔ **둘째 결함: 죽은 그래프가 「간선 없음」과 같은 값이었다.** API 계약과 `hybrid.LEGS` 는
`degraded` 에 `"graph"` 가 들어갈 수 있다고 적는데, 그 값을 넣는 코드가 없었다.
"""

from __future__ import annotations

import pytest

from nexus.repositories.graph import EdgeResult, SubGraph
from nexus.search import hybrid

_RID = "ent_payment"
_OTHER = "ent_refund"
_NAME = "결제 서비스"


class _StrictRepo:
    """저장소처럼 테넌트를 **문자열 하나로만** 받는다 — asyncpg 가 튜플을 거절하는 자리를 흉내 낸다.

    엔티티는 `home` 테넌트에만 산다. 다른 테넌트로 물으면 저장소처럼 빈 서브그래프에 rid 를
    이름 자리에 준다(범위 밖 seed 의 이름을 새지 않는 규칙, `graph.py`).
    """

    def __init__(self, home: str = "t_home", fail_rids: frozenset[str] = frozenset()):
        self.home, self.fail_rids, self.calls = home, fail_rids, []

    async def get_neighbors(self, entity_rid, hops=1, *, tenant, clearance):
        self.calls.append((entity_rid, tenant))
        if not isinstance(tenant, str):
            raise TypeError(f"invalid input for query argument $2: {tenant!r} "
                            f"(expected str, got {type(tenant).__name__})")
        if entity_rid in self.fail_rids:
            raise RuntimeError("그래프 DB 가 죽었다")
        if tenant != self.home:
            return SubGraph(center_rid=entity_rid, center_name=entity_rid, edges=[],
                            observed_edges=[])
        edge = EdgeResult(rid=f"edge_{entity_rid}", edge_type="CALLS", from_rid=entity_rid,
                          from_name=_NAME, to_rid="ent_settle", to_name="정산 서비스",
                          confidence=0.9, source_category="DESIGNED")
        return SubGraph(center_rid=entity_rid, center_name=_NAME, edges=[edge], observed_edges=[])


@pytest.fixture
def quiet_legs(monkeypatch):
    """그래프 밖의 경로는 비운다 — 이 파일이 보는 것은 그래프 보강 하나다."""
    async def no_bm25(query, *a, **k):
        return [], None

    async def no_enrich(fused, tenant, max_snippet_chars=300):
        return []

    monkeypatch.setattr(hybrid, "_bm25_search", no_bm25)
    monkeypatch.setattr(hybrid, "_enrich_hits", no_enrich)


async def _search(repo, scope, entity_rids=(_RID,)):
    return await hybrid.hybrid_search(
        "결제 서비스 장애", tenant=scope, clearance="INTERNAL", graph_repo=repo,
        route="graph_then_hybrid", entity_rids=list(entity_rids), config={"search": {}})


@pytest.mark.asyncio
async def test_a_one_element_tuple_scope_reaches_the_graph(quiet_legs):
    """오늘의 단일 테넌트 배포 모양이다 — 라이브에서 99회 거절된 바로 그 값."""
    repo = _StrictRepo()
    result = await _search(repo, ("t_home",))
    assert repo.calls == [(_RID, "t_home")]
    assert result.graph is not None and [e.rid for e in result.graph.edges] == [f"edge_{_RID}"]
    assert result.degraded == []


@pytest.mark.asyncio
async def test_a_two_tenant_scope_asks_each_and_names_the_centre_where_it_lives(quiet_legs):
    """엔티티가 없는 테넌트가 **먼저** 와도 중심 이름은 엔티티가 사는 쪽에서 온다.

    병합은 첫 서브그래프를 중심으로 쓴다(`_merge_subgraphs`). 없는 쪽이 첫째가 되면 이름
    자리에 rid 가 뜬다.
    """
    repo = _StrictRepo()
    result = await _search(repo, ("t_elsewhere", "t_home"))
    assert sorted(repo.calls) == [(_RID, "t_elsewhere"), (_RID, "t_home")]
    assert result.graph.center_name == _NAME
    assert [e.rid for e in result.graph.edges] == [f"edge_{_RID}"]


@pytest.mark.asyncio
async def test_a_string_scope_is_asked_exactly_as_before(quiet_legs):
    """옛 계약(문자열)은 엔티티당 한 번이다 — 호출 수가 늘지 않는다."""
    repo = _StrictRepo()
    await _search(repo, "t_home", entity_rids=(_RID, _OTHER))
    assert repo.calls == [(_RID, "t_home"), (_OTHER, "t_home")]


@pytest.mark.asyncio
async def test_a_dead_graph_is_named_not_returned_as_an_empty_one(quiet_legs):
    """⛔ 「간선이 없었다」와 「그래프가 죽었다」는 다른 사실이다 — 계약대로 `degraded` 에 싣는다."""
    result = await _search(_StrictRepo(fail_rids=frozenset({_RID})), ("t_home",))
    assert result.graph is None
    assert result.degraded == ["graph"]


@pytest.mark.asyncio
async def test_a_partly_dead_graph_is_still_named(quiet_legs):
    """엔티티 하나라도 못 물었으면 그래프는 온전하지 않다 — 살아난 쪽은 그대로 싣는다."""
    result = await _search(_StrictRepo(fail_rids=frozenset({_OTHER})), ("t_home",),
                           entity_rids=(_RID, _OTHER))
    assert [e.rid for e in result.graph.edges] == [f"edge_{_RID}"]
    assert result.degraded == ["graph"]


@pytest.mark.asyncio
async def test_an_empty_graph_is_not_a_dead_one(quiet_legs):
    """반대쪽 — 간선이 없는 것은 죽은 것이 아니다."""
    result = await _search(_StrictRepo(home="t_nobody"), ("t_home",))
    assert result.graph is not None and result.graph.edges == []
    assert result.degraded == []
