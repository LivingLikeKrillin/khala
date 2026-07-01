"""resolve_active_doc: ref(rid|source_uri|basename) → active 문서 rid, 모호하면 거부. 스펙 §4.1."""
import asyncio
import os

import asyncpg
import pytest

from nexus import db
from nexus.rid import doc_rid

DB_URL = os.environ.get("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 미설정")

_T = "acme"
# source_uri 는 실제 저장형(tenant 접두 포함) = canonical_uri
_A = doc_rid(f"{_T}:specs/A.md")
_SUP = doc_rid(f"{_T}:specs/old.md")       # superseded 문서 (패스스루 대상)
_UB = doc_rid(f"{_T}:x/U_B.md")            # LIKE 메타문자(_) 검증용
_UBX = doc_rid(f"{_T}:x/UxB.md")           # a_b 가 axb 에 오매치되면 안 됨
_D1 = doc_rid(f"{_T}:x/D.md")              # 동명 basename 다건
_D2 = doc_rid(f"{_T}:y/D.md")


async def _seed(conn):
    rows = [
        (_A,   _T, f"{_T}:specs/A.md",   "active"),
        (_SUP, _T, f"{_T}:specs/old.md", "superseded"),
        (_UB,  _T, f"{_T}:x/U_B.md",     "active"),
        (_UBX, _T, f"{_T}:x/UxB.md",     "active"),
        (_D1,  _T, f"{_T}:x/D.md",       "active"),
        (_D2,  _T, f"{_T}:y/D.md",       "active"),
    ]
    for rid, tenant, uri, status in rows:
        await conn.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, status) "
            "VALUES ($1, $2, $3, 'h', 'ch', $4)", rid, tenant, uri, status)


def _run(body):
    loop = asyncio.SelectorEventLoop()

    async def _outer():
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        db._pool = pool
        try:
            async with pool.acquire() as con:
                await con.execute("TRUNCATE documents, chunks CASCADE")
                await _seed(con)
            return await body()
        finally:
            await pool.close()
            db._pool = None

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()


def test_resolve_active_doc_rules():
    from nexus.supersede import resolve_active_doc

    async def body():
        # 1) rid 패스스루 (status 무관 — superseded rid 도 그대로)
        assert await resolve_active_doc(_A, _T) == _A
        assert await resolve_active_doc(_SUP, _T) == _SUP
        # 2) source_uri 정확일치: 상대경로(tenant 접두 자동) 및 완전형 둘 다
        assert await resolve_active_doc("specs/A.md", _T) == _A
        assert await resolve_active_doc(f"{_T}:specs/A.md", _T) == _A
        # 3) basename 매치
        assert await resolve_active_doc("A.md", _T) == _A
        # 4) LIKE 메타문자 이스케이프: 'U_B.md' 는 U_B 에만 매치(UxB 오매치 금지) → 정확히 1건
        assert await resolve_active_doc("U_B.md", _T) == _UB
        # 5) 0건 → ValueError
        with pytest.raises(ValueError, match="일치하는 active 문서 없음"):
            await resolve_active_doc("nope.md", _T)
        # 6) 다건 → ValueError (후보 source_uri 나열)
        with pytest.raises(ValueError, match="여러 문서가 일치") as ei:
            await resolve_active_doc("D.md", _T)
        msg = str(ei.value)
        assert f"{_T}:x/D.md" in msg and f"{_T}:y/D.md" in msg

    _run(body)
