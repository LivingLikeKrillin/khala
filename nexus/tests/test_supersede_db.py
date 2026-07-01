"""supersede() 프리미티브의 결정규칙을 REAL Postgres에 대해 검증한다 (스펙 §5.3).

명시적·멱등·자동감지 없음. 결정규칙 순서 고정: 자기참조 → new 검증 → old 존재 → old 상태.

NOTE(Windows + pytest-asyncio): 이 환경에서 async fixture가 깨지므로 자체 SelectorEventLoop
+ asyncpg 풀을 돌리고 db._pool 에 주입한다 (test_a2a_provenance_db.py 의 _run 헬퍼 참고).
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

from nexus.rid import chunk_rid, doc_rid

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요 (docker-compose.test.yml)")

_TENANT = "acme"
_RID_A = doc_rid("specs/A.md")
_RID_B = doc_rid("specs/B.md")
_CHUNK_A = chunk_rid(_RID_A, "", 0)
_RID_D = doc_rid("specs/D.md")  # soft_deleted 문서 (범위 밖 — 카스케이드 금지)
_CHUNK_D = chunk_rid(_RID_D, "", 0)
_RID_N = doc_rid("specs/N.md")  # superseded 문서 (비활성 new 후보)


async def _seed(conn) -> None:
    """활성 문서 A(청크 1개 포함) + 활성 문서 B + soft_deleted D(청크 포함) + superseded N 을 심는다."""
    await conn.execute(
        "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, status) "
        "VALUES ($1, $2, $3, $4, $5, 'active')",
        _RID_A, _TENANT, "specs/A.md", "hash-a", "chash-a",
    )
    await conn.execute(
        "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, status) "
        "VALUES ($1, $2, $3, $4, $5, 'active')",
        _RID_B, _TENANT, "specs/B.md", "hash-b", "chash-b",
    )
    await conn.execute(
        "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, chunk_text, status) "
        "VALUES ($1, $2, $3, $4, $5, 'active')",
        _CHUNK_A, _TENANT, "specs/A.md", _RID_A, "본문 A",
    )
    # soft_deleted 문서 D + soft_deleted 청크 — supersede 는 이를 건드리면 안 된다.
    await conn.execute(
        "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, status) "
        "VALUES ($1, $2, $3, $4, $5, 'soft_deleted')",
        _RID_D, _TENANT, "specs/D.md", "hash-d", "chash-d",
    )
    await conn.execute(
        "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, chunk_text, status) "
        "VALUES ($1, $2, $3, $4, $5, 'soft_deleted')",
        _CHUNK_D, _TENANT, "specs/D.md", _RID_D, "본문 D",
    )
    # superseded 문서 N — 비활성이므로 new_rid 로 쓰면 거부되어야 한다.
    await conn.execute(
        "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, status) "
        "VALUES ($1, $2, $3, $4, $5, 'superseded')",
        _RID_N, _TENANT, "specs/N.md", "hash-n", "chash-n",
    )


def _run(coro_fn):
    """Own SelectorEventLoop (asyncpg needs it on Windows). Wire nexus.db to the test pool."""
    from nexus import db

    loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()

    async def _outer():
        import asyncpg
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        db._pool = pool
        try:
            async with pool.acquire() as con:
                await con.execute("TRUNCATE documents, chunks CASCADE")
                await _seed(con)
            return await coro_fn()
        finally:
            await pool.close()
            db._pool = None

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()


def test_supersede_decision_rules():
    from nexus import db
    from nexus.supersede import supersede

    async def inner():
        # ── 규칙 1: 자기참조 금지 ──
        with pytest.raises(ValueError):
            await supersede(_RID_A, _RID_A, _TENANT)

        # ── 규칙 2: new_rid 부재/비활성 → ValueError ──
        with pytest.raises(ValueError):
            await supersede(_RID_A, "doc_missing", _TENANT)

        # ── 규칙 3: old_rid 부재 → ValueError (new 는 유효한 활성 B) ──
        with pytest.raises(ValueError):
            await supersede("doc_missing", _RID_B, _TENANT)

        # ── 규칙 4: A → B supersede 성공 ──
        result = await supersede(_RID_A, _RID_B, _TENANT)
        assert result == "superseded"

        a_row = await db.fetch_one(
            "SELECT status, superseded_by FROM documents WHERE rid = $1 AND tenant = $2",
            _RID_A, _TENANT,
        )
        assert a_row["status"] == "superseded"
        assert a_row["superseded_by"] == _RID_B

        chunk_row = await db.fetch_one(
            "SELECT status FROM chunks WHERE rid = $1", _CHUNK_A,
        )
        assert chunk_row["status"] == "superseded"

        # ── 규칙 5: 재호출 → noop, superseded_by 불변 ──
        again = await supersede(_RID_A, _RID_B, _TENANT)
        assert again == "noop"
        a_row2 = await db.fetch_one(
            "SELECT superseded_by FROM documents WHERE rid = $1 AND tenant = $2",
            _RID_A, _TENANT,
        )
        assert a_row2["superseded_by"] == _RID_B

    _run(inner)


def test_soft_deleted_old_is_noop_no_chunk_corruption():
    """Issue 1 회귀 가드: soft_deleted old → 'noop', 청크 카스케이드 없음, 상태 불변."""
    from nexus import db
    from nexus.supersede import supersede

    async def inner():
        result = await supersede(_RID_D, _RID_B, _TENANT)
        assert result == "noop"

        d_row = await db.fetch_one(
            "SELECT status, superseded_by FROM documents WHERE rid = $1 AND tenant = $2",
            _RID_D, _TENANT,
        )
        assert d_row["status"] == "soft_deleted"  # 문서 상태 불변
        assert d_row["superseded_by"] == ""        # superseded_by 미설정 (기본값)

        chunk_row = await db.fetch_one(
            "SELECT status FROM chunks WHERE rid = $1", _CHUNK_D,
        )
        assert chunk_row["status"] == "soft_deleted"  # 청크 오염 없음 (NOT 'superseded')

    _run(inner)


def test_new_exists_but_not_active_raises():
    """규칙 2 후반: new 가 존재하되 비활성(superseded)이면 ValueError."""
    from nexus.supersede import supersede

    async def inner():
        with pytest.raises(ValueError):
            await supersede(_RID_A, _RID_N, _TENANT)

    _run(inner)
