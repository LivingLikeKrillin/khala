"""001_supersession 마이그레이션을 REAL 러너(scripts.migrate.migrate)로 구동하는 통합 테스트.

SQL 파일을 직접 읽지 않고 프로덕션 러너를 태워, superseded_by 컬럼 + v_entropy_signals 뷰가
실제로 적용되는지(그리고 재실행이 멱등인지) 검증한다. init.sql 베이스라인 위에 델타로 얹힌다.

NOTE(Windows + pytest-asyncio): 이 환경에서 session async fixture가 깨지므로 자체
SelectorEventLoop + asyncpg 풀을 돌리고, db._pool 에 주입해 nexus.db 헬퍼가 이를 쓰게 한다
(test_a2a_provenance_db.py 의 _run 헬퍼 참고).
"""

from __future__ import annotations

import asyncio
import os

import asyncpg
import pytest

from nexus import db
from scripts import migrate as migrate_mod

DB_URL = os.environ.get("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 미설정")


def _run(coro_fn):
    loop = asyncio.SelectorEventLoop()

    async def _outer():
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        db._pool = pool  # nexus.db 헬퍼(migrate 러너가 쓰는 get_pool)가 이 풀을 사용
        try:
            return await coro_fn(pool)
        finally:
            await pool.close()
            db._pool = None

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()


def test_runner_applies_supersession_migration():
    async def body(pool):
        await migrate_mod.migrate(status_only=False)

        col = await pool.fetchval(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='documents' AND column_name='superseded_by'"
        )
        assert col == 1

        row = await pool.fetchrow("SELECT * FROM v_entropy_signals")
        assert set(row.keys()) >= {
            "reingest_overwrite_events",
            "exact_dup_pairs",
            "title_stem_collisions",
            "supersessions",
        }

        # 멱등 재실행: 에러 없이 통과해야 한다.
        await migrate_mod.migrate(status_only=False)

    _run(body)
