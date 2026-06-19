"""search_log 영속 + v_search_health 집계 (DB 통합). NEXUS_TEST_DB_URL 필요."""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

_DB = os.getenv("NEXUS_TEST_DB_URL")
# skip은 conftest가 integration 마커로 처리(NEXUS_TEST_DB_URL 미설정 시) — 별도 데코레이터 불필요.


async def test_ensure_creates_table_and_view_idempotently():
    from nexus import db
    os.environ["DATABASE_URL"] = _DB
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
    os.environ["DATABASE_URL"] = _DB
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
        assert float(row["no_answer_rate"]) == 0.5
    finally:
        await db.execute("DELETE FROM search_log WHERE path = 'test_agg'")
        await db.close_pool()
