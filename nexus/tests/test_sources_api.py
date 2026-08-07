"""소스 콘솔 HTTP 계약 — SPEC-nexus-notion-source-console §4.6 · §4.7 · §5.

라우터만 검증한다(실제 Notion 워크는 sync_job 쪽 테스트). 여기서 고정하는 것:
  · capability 게이트 (manage_sources 없으면 403)
  · confirm_plan 과 다른 파라미터의 동시 전달 → 400
  · 동기 실패면(409/400/503) run 행을 만들지 않는다
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "acme"
_ROOT_URL = "https://www.notion.so/Team-1a2b3c4d5e6f4a7b8c9d0e1f2a3b4c5d"
_ROOT_ID = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"


@pytest.fixture(autouse=True)
def _selector_loop_policy():
    if sys.platform == "win32":
        prev = asyncio.get_event_loop_policy()
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        try:
            yield
        finally:
            asyncio.set_event_loop_policy(prev)
    else:
        yield


def _client(capabilities=("manage_sources",), notion_token="tok"):
    from contextlib import asynccontextmanager

    from nexus import db
    from nexus.auth import Principal
    from nexus.sources.api import dep, router
    from nexus.sources.schema import ensure_schema

    @asynccontextmanager
    async def lifespan(app):
        import asyncpg
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=5)
        db._pool = pool
        async with pool.acquire() as con:
            await ensure_schema(con)
            await con.execute("DELETE FROM notion_sync_runs")
            await con.execute("DELETE FROM notion_sources")
        try:
            yield
        finally:
            await pool.close()
            db._pool = None

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    app.dependency_overrides[dep] = lambda: Principal(
        name="test", tenant=_TENANT, clearance="INTERNAL", capabilities=tuple(capabilities),
    )
    if notion_token:
        os.environ["NOTION_TOKEN"] = notion_token
    else:
        os.environ.pop("NOTION_TOKEN", None)
    return TestClient(app)


# ── roots CRUD ────────────────────────────────────────────────────────────────

def test_add_root_by_url_then_list_it():
    with _client() as c:
        r = c.post("/sources/notion/roots", json={"url_or_id": _ROOT_URL, "label": "팀 위키"})
        assert r.status_code == 201, r.text
        assert r.json()["data"]["root_id"] == _ROOT_ID

        listed = c.get("/sources/notion/roots").json()["data"]
        assert [x["root_id"] for x in listed["roots"]] == [_ROOT_ID]
        assert listed["token_configured"] is True


def test_duplicate_root_is_409():
    with _client() as c:
        c.post("/sources/notion/roots", json={"url_or_id": _ROOT_ID})
        r = c.post("/sources/notion/roots", json={"url_or_id": _ROOT_URL})  # 같은 페이지, 다른 표기
        assert r.status_code == 409


def test_unparseable_root_is_400():
    with _client() as c:
        assert c.post("/sources/notion/roots", json={"url_or_id": "https://example.com/x"}).status_code == 400


def test_delete_root_is_idempotent_and_says_documents_survive():
    with _client() as c:
        c.post("/sources/notion/roots", json={"url_or_id": _ROOT_ID})
        r = c.delete(f"/sources/notion/roots/{_ROOT_ID}")
        assert r.status_code == 200
        assert r.json()["data"]["documents_deleted"] == 0
        assert c.delete(f"/sources/notion/roots/{_ROOT_ID}").status_code == 404


# ── capability 게이트 (§4.7) ──────────────────────────────────────────────────

def test_reads_are_open_but_writes_need_manage_sources():
    with _client(capabilities=()) as c:
        assert c.get("/sources/notion/roots").status_code == 200          # 읽기는 통과
        assert c.post("/sources/notion/roots", json={"url_or_id": _ROOT_ID}).status_code == 403
        assert c.delete(f"/sources/notion/roots/{_ROOT_ID}").status_code == 403
        assert c.post("/sources/notion/sync", json={}).status_code == 403


# ── sync 파라미터 계약 (§4.4) ─────────────────────────────────────────────────

def test_confirm_plan_with_any_other_parameter_is_400():
    """미리보기와 다른 조건으로 확정하는 길을 막는다 (I-006)."""
    with _client() as c:
        for extra in ({"reconcile": True}, {"dry_run": True}, {"force": True}, {"since": "2026-01-01"}):
            body = {"confirm_plan": "deadbeef", **extra}
            r = c.post("/sources/notion/sync", json=body)
            assert r.status_code == 400, f"{extra} → {r.status_code}"


def test_confirm_plan_for_unknown_run_is_404():
    with _client() as c:
        assert c.post("/sources/notion/sync", json={"confirm_plan": "0" * 32}).status_code == 404


def test_sync_without_notion_token_is_503_and_creates_no_run():
    from nexus.sources import runs_store

    with _client(notion_token="") as c:
        c.post("/sources/notion/roots", json={"url_or_id": _ROOT_ID})  # 이건 토큰 불필요
        assert c.post("/sources/notion/sync", json={}).status_code == 503

    async def _check():
        assert await runs_store.latest_run(_TENANT) is None

    _drain(_check)


def test_sync_with_no_roots_registered_is_400():
    with _client() as c:
        assert c.post("/sources/notion/sync", json={}).status_code == 400


def _drain(coro_fn):
    """TestClient 밖에서 DB 를 다시 열어 확인한다(앱 lifespan 이 풀을 닫았으므로)."""
    import asyncpg

    from nexus import db

    loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()

    async def _outer():
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=2)
        db._pool = pool
        try:
            return await coro_fn()
        finally:
            await pool.close()
            db._pool = None

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()
