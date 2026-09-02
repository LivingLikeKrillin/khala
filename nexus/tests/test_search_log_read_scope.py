"""범위가 붙어도 `search_log` 가 실제로 앉는가 — 그리고 **범위가 남는가.**

⛔ **왜 이 검사가 있나 (실측 2026-09-02).** 읽기 범위를 붙이면서 `req.tenant` 에 목록을
넣었다. 그 필드는 `str` 이고 `search_log.tenant` 도 TEXT 다. 적재가 터졌는데
`record_search` 는 **절대 raise 안 하도록** 만들어져 있어서 조용히 죽었고, **범위를 붙인 그
시각부터 하루 넘게 신호가 한 줄도 안 쌓였다.**

검사가 1,800개 초록인 채였다. 아무도 *"쌓이는가"* 를 안 물었기 때문이다.
"""

from __future__ import annotations

import os

import pytest

from nexus.search.signals import SearchSignals, extract_signals

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")


def _sig(**kw) -> SearchSignals:
    # ⚠ **진짜 `SearchResult` 를 쓴다.** 손으로 만든 가짜는 필드가 빠져도 조용히 지나가고,
    # 그러면 이 검사가 프로덕션과 다른 것을 본다 — 이 리포가 반복해서 데인 모양이다.
    from nexus.search.hybrid import SearchResult
    return extract_signals(SearchResult(route_used="hybrid_only"), None,
                           path="t", tenant="acme", clearance="INTERNAL",
                           query="질문", **kw)


def test_a_scope_list_becomes_text_not_a_list():
    """⛔ 목록을 그대로 두면 TEXT 컬럼에 못 들어간다 — 그게 로그를 죽였다."""
    sig = _sig(read_scope=["default", "design_docs"])
    assert sig.read_scope == "default,design_docs"
    assert isinstance(sig.read_scope, str)


def test_no_scope_leaves_it_empty():
    """대조군 — 범위를 안 주는 배포는 오늘과 같다."""
    assert _sig().read_scope is None


def test_a_single_string_scope_passes_through():
    assert _sig(read_scope="default").read_scope == "default"


@pytest.mark.asyncio
async def test_the_row_actually_lands_with_its_scope(db_pool):
    """⛔ **가장 중요한 검사.** 필드가 있는 것과 행이 앉는 것은 다르다."""
    from nexus import db
    from nexus.search.signals import record_search

    db._pool = db_pool
    await db.ensure_search_log()
    async with db_pool.acquire() as con:
        before = await con.fetchval("SELECT count(*) FROM search_log")

    await record_search(_sig(read_scope=["default", "design_docs"]), await_persist=True)

    async with db_pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT tenant, read_scope FROM search_log ORDER BY id DESC LIMIT 1")
        after = await con.fetchval("SELECT count(*) FROM search_log")
    db._pool = None

    assert after == before + 1, "행이 안 앉았다 — 적재가 조용히 죽는 그 모양이다"
    assert row["tenant"] == "acme", "귀속은 단일 테넌트다"
    assert row["read_scope"] == "default,design_docs", "범위가 안 남으면 수요가 오귀속된다"
