"""notion_sources / notion_sync_runs 를 REAL Postgres 로 검증한다.

SPEC-nexus-notion-source-console §4.1(roots) · §4.2(run 상태·단일실행·크래시 스윕).

핵심 불변식:
  1. tenant 당 running 인 run 은 최대 1개 — advisory lock 과 **독립인** DB 레벨 백스톱.
  2. 크래시 스윕은 lock 을 잡을 수 있는 행만 failed 로 만든다 (살아있는 잡을 죽이지 않는다).
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "acme"
_ROOT = "2740c71b-b9dc-80ef-b43a-ea3676e632c8"


def _run(coro_fn):
    from nexus import db

    loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()

    async def _outer():
        import asyncpg
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5)
        db._pool = pool
        try:
            from nexus.sources.schema import ensure_schema
            async with pool.acquire() as con:
                await ensure_schema(con)
                await con.execute("DELETE FROM notion_sync_runs")
                await con.execute("DELETE FROM notion_sources")
            return await coro_fn()
        finally:
            await pool.close()
            db._pool = None

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()


# ── §4.1 roots ────────────────────────────────────────────────────────────────

def test_roots_are_stored_canonically_and_listed():
    from nexus.sources import roots_store

    async def inner():
        # 사람은 URL 을 붙여넣는다 — 대시 없는 형태.
        bare = _ROOT.replace("-", "")
        await roots_store.add_root(_TENANT, f"https://www.notion.so/Team-{bare}", label="팀 위키")
        rows = await roots_store.list_roots(_TENANT)
        assert [r["root_id"] for r in rows] == [_ROOT]      # 대시 포함 소문자로 저장
        assert rows[0]["label"] == "팀 위키"

    _run(inner)


def test_adding_the_same_page_twice_in_any_notation_is_a_duplicate():
    from nexus.sources import roots_store
    from nexus.sources.errors import DuplicateRoot

    async def inner():
        await roots_store.add_root(_TENANT, _ROOT)
        with pytest.raises(DuplicateRoot):
            await roots_store.add_root(_TENANT, _ROOT.replace("-", "").upper())

    _run(inner)


def test_roots_are_tenant_scoped():
    from nexus.sources import roots_store

    async def inner():
        await roots_store.add_root(_TENANT, _ROOT)
        assert await roots_store.list_roots("other") == []

    _run(inner)


def test_removing_a_root_does_not_touch_documents():
    from nexus.sources import roots_store

    async def inner():
        await roots_store.add_root(_TENANT, _ROOT)
        assert await roots_store.remove_root(_TENANT, _ROOT) is True
        assert await roots_store.list_roots(_TENANT) == []
        assert await roots_store.remove_root(_TENANT, _ROOT) is False   # 멱등

    _run(inner)


# ── §4.2 run 상태 ─────────────────────────────────────────────────────────────

def test_only_one_running_row_per_tenant_at_the_db_level():
    """advisory lock 을 우회하는 버그가 생겨도 데이터 레벨에서 막힌다 (I-015)."""
    import asyncpg

    from nexus.sources import runs_store

    async def inner():
        await runs_store.create_run(_TENANT, reconcile=True, dry_run=True)
        with pytest.raises(asyncpg.UniqueViolationError):
            await runs_store.create_run(_TENANT, reconcile=True, dry_run=True)

    _run(inner)


def test_a_finished_run_frees_the_tenant():
    from nexus.sources import runs_store

    async def inner():
        r1 = await runs_store.create_run(_TENANT, reconcile=False, dry_run=False)
        await runs_store.finish_run(r1, status="succeeded", counts={"ingested": 3})
        r2 = await runs_store.create_run(_TENANT, reconcile=False, dry_run=False)
        assert r2 != r1

        latest = await runs_store.latest_run(_TENANT)
        assert latest["run_id"] == r2 and latest["status"] == "running"

    _run(inner)


def test_run_ids_are_uuid4_hex():
    from nexus.sources import runs_store

    async def inner():
        rid = await runs_store.create_run(_TENANT, reconcile=False, dry_run=False)
        assert len(rid) == 32 and all(c in "0123456789abcdef" for c in rid)

    _run(inner)


# ── §4.2 크래시 스윕 ──────────────────────────────────────────────────────────

def test_startup_sweep_fails_an_orphaned_run():
    """프로세스가 죽으면 lock 이 풀린다 → 그 행은 interrupted 로 정리된다."""
    from nexus import db
    from nexus.sources import runs_store

    async def inner():
        rid = await runs_store.create_run(_TENANT, reconcile=False, dry_run=False)
        swept = await runs_store.sweep_orphaned_runs()
        assert swept == [rid]
        row = await db.fetch_one("SELECT status, reason FROM notion_sync_runs WHERE run_id=$1", rid)
        assert row["status"] == "failed" and row["reason"] == "interrupted"

    _run(inner)


def test_startup_sweep_leaves_a_live_run_alone():
    """다른 커넥션이 그 테넌트의 lock 을 쥐고 있으면 = 살아있는 잡이다. 건드리면 안 된다 (I-004)."""
    from nexus import db
    from nexus.sources import runs_store

    async def inner():
        rid = await runs_store.create_run(_TENANT, reconcile=False, dry_run=False)
        pool = await db.get_pool()
        holder = await pool.acquire()          # 살아있는 잡의 전용 커넥션을 흉내
        try:
            got = await holder.fetchval(
                "SELECT pg_try_advisory_lock(hashtext($1)::bigint)", f"notion_sync:{_TENANT}"
            )
            assert got is True
            assert await runs_store.sweep_orphaned_runs() == []      # 아무것도 안 쓸어감
            row = await db.fetch_one("SELECT status FROM notion_sync_runs WHERE run_id=$1", rid)
            assert row["status"] == "running"
        finally:
            await holder.execute("SELECT pg_advisory_unlock_all()")
            await pool.release(holder)

    _run(inner)
