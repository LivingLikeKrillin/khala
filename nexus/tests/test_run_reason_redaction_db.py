"""`notion_sync_runs.reason` 은 자격증명이 DB 에 영구히 남을 수 있는 유일한 경로다 — REAL Postgres.

SPEC-nexus-notion-connection-health §4.6.

오늘의 `notion_client` 는 예외 문자열에 토큰을 담지 않는다(2026-07-10, bogus 토큰으로 실제 API 를
때려 확인). 그러니 이건 **회귀 방지 가드**다. 요청 헤더를 예외에 붙이는 버전이 나오는 순간,
`finish_run(reason=str(e)[:500])` 이 토큰을 그 컬럼에 적어 넣고, 그것은 실행 기록을 보여주는
모든 표면에서 읽힌다. 그래서 테스트가 토큰을 예외에 **직접 주입**한다 — 가정하지 않고 밟는다.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "acme"
_TOKEN = "ntn_secret_value_do_not_leak_0000000000"


@pytest.fixture
async def clean(db_pool, monkeypatch):
    from nexus import db
    from nexus.sources.schema import ensure_schema

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await ensure_schema(con)
        await con.execute("DELETE FROM notion_sync_runs")
    monkeypatch.setenv("NOTION_TOKEN", _TOKEN)
    yield
    db._pool = None


async def test_a_reason_carrying_the_token_is_stored_redacted(clean):
    from nexus import db
    from nexus.sources import runs_store

    run_id = await runs_store.create_run(_TENANT, reconcile=False, dry_run=False)
    # notion_client 가 언젠가 헤더를 예외에 실어 보낼 때의 모습
    await runs_store.finish_run(
        run_id, status="failed",
        reason=f"HTTPStatusError: 401 for url … headers={{'Authorization': 'Bearer {_TOKEN}'}}")

    stored = await db.fetch_val("SELECT reason FROM notion_sync_runs WHERE run_id=$1", run_id)
    assert _TOKEN not in stored
    assert "[REDACTED]" in stored
    assert "401" in stored              # 진단 정보는 남는다. 자격증명만 지운다.


async def test_an_ordinary_reason_is_untouched(clean):
    from nexus import db
    from nexus.sources import runs_store

    run_id = await runs_store.create_run(_TENANT, reconcile=False, dry_run=False)
    await runs_store.finish_run(run_id, status="failed", reason="plan_stale")

    assert await db.fetch_val(
        "SELECT reason FROM notion_sync_runs WHERE run_id=$1", run_id) == "plan_stale"


async def test_redaction_does_not_blank_the_reason_when_no_token_is_set(clean, monkeypatch):
    from nexus import db
    from nexus.sources import runs_store

    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    run_id = await runs_store.create_run(_TENANT, reconcile=False, dry_run=False)
    await runs_store.finish_run(run_id, status="failed", reason="lock_unavailable")

    assert await db.fetch_val(
        "SELECT reason FROM notion_sync_runs WHERE run_id=$1", run_id) == "lock_unavailable"
