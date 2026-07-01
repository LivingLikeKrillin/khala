"""nexus supersede 가 경로 ref 로 동작하는지(스펙 ①)."""
import asyncio
import os
import sys

import asyncpg
import pytest
from typer.testing import CliRunner

from nexus import db
from nexus.cli import app
from nexus.rid import doc_rid

DB_URL = os.environ.get("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 미설정")

_T = "default"
_OLD = doc_rid(f"{_T}:specs/old.md")
_NEW = doc_rid(f"{_T}:specs/new.md")


async def _seed(conn):
    for rid, uri in [(_OLD, f"{_T}:specs/old.md"), (_NEW, f"{_T}:specs/new.md")]:
        await conn.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, status) "
            "VALUES ($1, $2, $3, 'h', 'ch', 'active')", rid, _T, uri)


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
        pool = await asyncpg.create_pool(DB_URL)
        db._pool = pool
        async with pool.acquire() as con:
            await con.execute("TRUNCATE documents, chunks CASCADE")
            await _seed(con)
        await db.close_pool()
    asyncio.run(_p())


def _status(rid):
    async def _q():
        conn = await asyncpg.connect(DB_URL)
        try:
            return await conn.fetchval("SELECT status FROM documents WHERE rid=$1", rid)
        finally:
            await conn.close()
    return asyncio.run(_q())


def test_supersede_cli_by_path(monkeypatch):
    # CLI 커맨드는 자체 풀을 get_pool()=os.getenv("DATABASE_URL", 5432기본)으로 만든다.
    # 시드/커맨드가 같은 테스트 DB(5433)에 붙도록 DATABASE_URL 을 가리킨다(monkeypatch=자동복원).
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    _prepare()
    result = CliRunner().invoke(app, ["supersede", "specs/old.md", "--by", "specs/new.md"])
    assert result.exit_code == 0, result.output
    assert "superseded" in result.output
    assert _status(_OLD) == "superseded"


def test_supersede_cli_ambiguous_or_missing_rejects(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    _prepare()
    result = CliRunner().invoke(app, ["supersede", "nope.md", "--by", "specs/new.md"])
    assert result.exit_code == 1
    assert "거부" in result.output
