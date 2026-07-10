"""`nexus doc hide|restore` · `nexus unsupersede` — REAL Postgres. SPEC §4.6.

CLI 는 경로로 문서를 부른다. 숨긴 문서는 active 가 아니므로 상태를 가리지 않는 해석기가
필요하다 — 이게 없으면 되돌리려는 사람이 rid 를 손으로 옮겨 적어야 한다.
"""

from __future__ import annotations

import asyncio
import os
import sys

import asyncpg
import pytest
from typer.testing import CliRunner

from nexus import db
from nexus.cli import app

DB_URL = os.environ.get("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 미설정")

_T = "default"


@pytest.fixture(autouse=True)
def _selector_policy():
    if sys.platform == "win32":
        prev = asyncio.get_event_loop_policy()
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        try:
            yield
        finally:
            asyncio.set_event_loop_policy(prev)
    else:
        yield


def _prepare():
    async def _p():
        from nexus.documents.schema import ensure_lifecycle_schema
        pool = await asyncpg.create_pool(DB_URL)
        db._pool = pool
        async with pool.acquire() as con:
            await ensure_lifecycle_schema(con)
            await con.execute("TRUNCATE documents, chunks, doc_supersession_events CASCADE")
            for rid, uri in [("doc_old", f"{_T}:specs/old.md"), ("doc_new", f"{_T}:specs/new.md")]:
                await con.execute(
                    "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, status) "
                    "VALUES ($1,$2,$3,'h','ch','active')", rid, _T, uri)
        await db.close_pool()
    asyncio.run(_p())


def _row(rid):
    async def _q():
        conn = await asyncpg.connect(DB_URL)
        try:
            return await conn.fetchrow("SELECT status::text, hold FROM documents WHERE rid=$1", rid)
        finally:
            await conn.close()
    return asyncio.run(_q())


@pytest.fixture(autouse=True)
def _db_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    _prepare()


def _run(*args):
    return CliRunner().invoke(app, list(args))


def test_hide_by_path_then_restore_by_path():
    r = _run("doc", "hide", "specs/old.md")
    assert r.exit_code == 0, r.output
    row = _row("doc_old")
    assert row["status"] == "soft_deleted" and row["hold"] is True

    # 숨긴 뒤에도 같은 경로로 부를 수 있다
    r = _run("doc", "restore", "specs/old.md")
    assert r.exit_code == 0, r.output
    assert _row("doc_old")["status"] == "active"


def test_hide_tells_the_user_what_happened_and_how_to_undo():
    out = _run("doc", "hide", "specs/old.md").output
    assert "검색에서 사라집니다" in out
    assert "nexus doc restore" in out


def test_hide_refuses_a_superseded_document():
    assert _run("supersede", "specs/old.md", "--by", "specs/new.md").exit_code == 0
    r = _run("doc", "hide", "specs/old.md")
    assert r.exit_code == 1
    assert "unsupersede" in r.output


def test_unsupersede_requires_a_reason_and_records_it():
    _run("supersede", "specs/old.md", "--by", "specs/new.md")

    r = _run("unsupersede", "specs/old.md")            # --reason 없음
    assert r.exit_code != 0

    r = _run("unsupersede", "specs/old.md", "--reason", "오지정이었다")
    assert r.exit_code == 0, r.output
    assert _row("doc_old")["status"] == "active"

    async def _q():
        conn = await asyncpg.connect(DB_URL)
        try:
            return await conn.fetchval(
                "SELECT reason FROM doc_supersession_events "
                "WHERE rid='doc_old' AND action='unsuperseded'")
        finally:
            await conn.close()
    assert asyncio.run(_q()) == "오지정이었다"


def test_unknown_path_is_refused_not_silently_ignored():
    r = _run("doc", "hide", "specs/nope.md")
    assert r.exit_code == 1 and "거부" in r.output
