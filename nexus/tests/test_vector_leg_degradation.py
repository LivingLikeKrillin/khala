"""벡터 다리는 죽어도 검색은 답한다 — 단, 죽었다고 말한다
(SPEC-nexus-embedding-cutover-seam §4.4).

교체 SPEC §5 는 "임베딩 백엔드가 없으면 벡터 다리는 빈 결과를 내고 키워드 다리가 답한다. 검색은
degrade 되지 error 가 되지 않는다" 고 약속했지만, `_vector_search` 의 try 는 `embed_query` 만
감싸고 있었다 — SQL 예외는 `asyncio.gather` 를 타고 그대로 500 으로 나갔다. 차원 불일치는 정확히
그 경로로 온다.

그리고 반대쪽 실수도 막는다: **죽은 DB 를 우회해 키워드로 답하는 것**은 `nexus/CLAUDE.md` 가
금지한다. 그래서 분류는 좁고, 애매하면 503 이다.
"""

from __future__ import annotations

import asyncpg
import httpx
import pytest

from nexus.providers.embedding import WrongVectorDimensions
from nexus.search.hybrid import LEGS, SearchResult, degrades_the_leg


def _pg(cls, message: str = "boom"):
    """asyncpg 예외 인스턴스 — 이 라이브러리는 예외를 SQLSTATE 로 만들어 준다."""
    return cls(message)


# ── 무엇이 다리만 죽이고, 무엇이 배포가 아픈 것인가 ──────────────────────────


@pytest.mark.parametrize("exc", [
    _pg(asyncpg.exceptions.DataError, "different vector dimensions 768 and 1024"),
])
def test_a_data_error_degrades_the_leg(exc):
    """차원 불일치(SQLSTATE 22000)는 **이 질의의 벡터**의 성질이다 — 재시도로 낫지 않는다."""
    assert degrades_the_leg(exc) is True


@pytest.mark.parametrize("exc", [
    _pg(asyncpg.exceptions.ConnectionDoesNotExistError),
    _pg(asyncpg.exceptions.TooManyConnectionsError),
    _pg(asyncpg.exceptions.CannotConnectNowError),
    _pg(asyncpg.exceptions.QueryCanceledError),          # statement timeout — 부하의 신호다
    _pg(asyncpg.exceptions.InsufficientPrivilegeError),  # GRANT 누락 — 배포의 상태다
    asyncpg.exceptions.InterfaceError("pool is closing"),
    TimeoutError("pool acquire"),
])
def test_everything_else_propagates_and_becomes_a_503(exc):
    """애매하면 503 이다. 잘못된 503 은 보이는 장애, 잘못된 degrade 는 조용히 나빠진 답이다."""
    assert degrades_the_leg(exc) is False


def test_the_legal_degraded_values_are_the_legs_themselves():
    """문자열이 자유롭게 들어가면 소비자가 무엇을 기대해야 할지 알 수 없다."""
    assert set(LEGS) == {"bm25", "vector", "graph"}
    assert SearchResult().degraded == []


# ── 다리 래퍼: 빈 결과와 죽은 다리를 구분한다 ────────────────────────────────


class _Svc:
    """임베딩 서비스 스텁 — 무엇을 던질지 시험이 고른다."""

    def __init__(self, error: BaseException | None = None):
        self.error = error
        self.model, self.backend, self.dimensions = "KURE-v1", "sidecar", 1024

    async def embed_query(self, query: str) -> list[float]:
        if self.error:
            raise self.error
        return [0.1] * self.dimensions


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [
    RuntimeError("임베딩 사이드카가 아직 준비되지 않았다"),      # 503 from the sidecar
    httpx.ConnectError("connection refused"),                    # 사이드카가 아예 없다
    WrongVectorDimensions("768 != 1024"),                        # 잘못 띄운 체크포인트
])
async def test_an_embedding_backend_failure_degrades_the_leg_instead_of_vanishing(error):
    """예전엔 여기서 빈 리스트를 조용히 냈다 — '못 찾았다' 와 '죽었다' 가 같은 모양이었다."""
    from nexus.search.hybrid import _vector_leg

    hits, degraded = await _vector_leg("결제", _Svc(error), "default", "INTERNAL", 10, None)
    assert (hits, degraded) == ([], True)


@pytest.mark.asyncio
async def test_a_working_leg_is_not_marked_degraded(monkeypatch):
    """음성 대조군 — 항상 degraded 를 켜는 구현도 위 시험을 통과한다."""
    from nexus.search import hybrid

    async def _fake_fetch_all(sql, *args):
        return [{"rid": "chunk_a", "distance": 0.1}]

    monkeypatch.setattr(hybrid.db, "fetch_all", _fake_fetch_all)
    hits, degraded = await hybrid._vector_leg("결제", _Svc(), "default", "INTERNAL", 10, None)
    assert hits == [("chunk_a", 1)] and degraded is False


@pytest.mark.asyncio
async def test_a_connection_failure_is_not_swallowed(monkeypatch):
    """503 이어야 할 것이 200 으로 나가면, 죽은 DB 를 우회해 답한 것이 된다."""
    from nexus.search import hybrid

    async def _boom(sql, *args):
        raise asyncpg.exceptions.ConnectionDoesNotExistError("connection lost")

    monkeypatch.setattr(hybrid.db, "fetch_all", _boom)
    with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
        await hybrid._vector_leg("결제", _Svc(), "default", "INTERNAL", 10, None)


@pytest.mark.asyncio
async def test_a_dimension_mismatch_degrades_and_keyword_results_survive(monkeypatch):
    """**오늘의 상태를 잡았을 시험이다**: 차원 불일치가 500 이 아니라 degrade 로 끝나는가."""
    from nexus.search import hybrid

    async def _mismatch(sql, *args):
        if "tsvector_ko" in sql:
            return [{"rid": "chunk_kw", "rank_score": 1.0}]
        raise asyncpg.exceptions.DataError("different vector dimensions 768 and 1024")

    async def _enriched(fused, tenant, max_snippet_chars=300):
        return [hybrid.SearchHit(rid=r["rid"], doc_rid="doc", score=r["score"]) for r in fused]

    monkeypatch.setattr(hybrid.db, "fetch_all", _mismatch)
    monkeypatch.setattr(hybrid, "_enrich_hits", _enriched)

    result = await hybrid.hybrid_search(
        query="결제", tenant="default", clearance="INTERNAL", top_k=5,
        embedding_svc=_Svc(), route="hybrid_only")

    assert result.degraded == ["vector"], "죽은 다리는 결과에 표시돼야 한다"
    assert [h["rid"] if isinstance(h, dict) else h.rid for h in result.hits] == ["chunk_kw"], (
        "키워드 다리는 계속 답해야 한다 — 이게 degrade 와 장애의 차이다")
