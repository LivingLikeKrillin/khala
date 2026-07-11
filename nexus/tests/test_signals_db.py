"""search_log 영속 + v_search_health 집계 (DB 통합). NEXUS_TEST_DB_URL 필요."""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

_DB = os.getenv("NEXUS_TEST_DB_URL")
# skip은 conftest가 integration 마커로 처리(NEXUS_TEST_DB_URL 미설정 시) — 별도 데코레이터 불필요.


async def test_ensure_creates_table_and_view_idempotently():
    from nexus import db
    os.environ["DATABASE_URL"] = _DB or ""
    await db.get_pool()
    try:
        await db.ensure_search_log()
        await db.ensure_search_log()  # 멱등 — 두 번 호출해도 실패 없음
        # 뷰 존재 확인
        val = await db.fetch_val("SELECT count(*) FROM v_search_health")
        assert val is not None
    finally:
        await db.close_pool()


async def test_record_search_persists_and_view_aggregates():
    from nexus import db
    from nexus.search.signals import SearchSignals, record_search
    os.environ["DATABASE_URL"] = _DB or ""
    await db.get_pool()
    try:
        await db.ensure_search_log()
        await db.execute("DELETE FROM search_log WHERE path = 'test_agg'")
        # no_answer 1건 + 정상 1건
        for no_ans in (True, False):
            sig = SearchSignals(
                path="test_agg", tenant="t", clearance="INTERNAL", route="hybrid_only",
                query_sha256="x", query_len=1, n_snippets=0 if no_ans else 3,
                top_score=None if no_ans else 0.5, n_entities=0,
                graph_requested=False, n_graph_edges=0, no_answer=no_ans,
                llm_failed=False, latency_ms=100,
            )
            await record_search(sig, await_persist=True)
        row = await db.fetch_one(
            "SELECT n, no_answer_rate FROM v_search_health WHERE path = 'test_agg'"
        )
        assert row["n"] == 2
        assert float(row["no_answer_rate"]) == pytest.approx(0.5)
    finally:
        await db.execute("DELETE FROM search_log WHERE path = 'test_agg'")
        await db.close_pool()


async def test_citation_fabrication_rate_excludes_unmeasured():
    """n_citations/unverified_citations 적재 + v_search_health fabrication rate. NULL(미측정) 제외."""
    from nexus import db
    from nexus.search.signals import SearchSignals, record_search
    os.environ["DATABASE_URL"] = _DB or ""
    await db.get_pool()

    def _sig(n_cit, unver):
        return SearchSignals(
            path="test_cit", tenant="t", clearance="INTERNAL", route="hybrid_only",
            query_sha256="x", query_len=1, n_snippets=3, top_score=0.5, n_entities=0,
            graph_requested=False, n_graph_edges=0, no_answer=False, llm_failed=False,
            latency_ms=10, n_citations=n_cit, unverified_citations=unver,
        )
    try:
        await db.ensure_search_log()
        await db.execute("DELETE FROM search_log WHERE path = 'test_cit'")
        await record_search(_sig(2, 1), await_persist=True)          # 측정: 2건 중 1 미검증
        await record_search(_sig(None, None), await_persist=True)    # 미측정(답변 없음) → NULL
        row = await db.fetch_one(
            "SELECT citation_fabrication_rate FROM v_search_health WHERE path = 'test_cit'")
        assert float(row["citation_fabrication_rate"]) == pytest.approx(0.5)   # 1/2, NULL 행 제외
        # 원시 행: 미측정은 NULL 로 적재됐는가
        nulls = await db.fetch_val(
            "SELECT count(*) FROM search_log WHERE path='test_cit' AND n_citations IS NULL")
        assert nulls == 1
    finally:
        await db.execute("DELETE FROM search_log WHERE path = 'test_cit'")
        await db.close_pool()
