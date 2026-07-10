"""`nexus sources health` — REAL Postgres. SPEC-nexus-notion-connection-health §4.5.

CLI 는 DB 를 직접 읽고 Notion 을 직접 묻는다(HTTP 를 경유하지 않는다). 그러므로 capability 가
아니라 **셸에 접근할 수 있느냐**가 경계다 — 이미 `.env` 를 읽을 수 있는 사람이다.

여기서 고정하는 것: 진단이 Notion 장애로 죽지 않고, 사람이 읽을 문장으로 답한다.
"""

from __future__ import annotations

import asyncio
import os
import sys

import asyncpg
import httpx
import pytest
from typer.testing import CliRunner

from nexus import db
from nexus.cli import app

DB_URL = os.environ.get("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 미설정")

_T = "default"
_PAGE = "fc054c8f-cc62-409c-8154-deafb826cac9"
_TOKEN = "ntn_secret_value_do_not_leak_0000000000"


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


@pytest.fixture(autouse=True)
def _prepared(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    monkeypatch.setenv("NOTION_TOKEN", _TOKEN)

    async def _p():
        from nexus.sources.schema import ensure_schema
        pool = await asyncpg.create_pool(DB_URL)
        db._pool = pool
        async with pool.acquire() as con:
            await ensure_schema(con)
            await con.execute("DELETE FROM notion_sources")
            await con.execute(
                "INSERT INTO notion_sources (tenant, root_id, label) VALUES ($1,$2,'')",
                _T, _PAGE)
        await db.close_pool()

    asyncio.run(_p())


def _patch_probe(monkeypatch, handler):
    import nexus.cli as cli_mod
    from nexus.sources.notion_health import probe_connection as real

    async def patched(token, roots, **_):
        return await real(token, roots, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(cli_mod, "probe_connection", patched, raising=False)


def test_health_prints_the_integration_and_the_root_title(monkeypatch):
    def ok(request):
        if request.url.path == "/v1/users/me":
            return httpx.Response(200, json={"name": "실증 테스트",
                                             "bot": {"workspace_name": "어느 워크스페이스"}})
        return httpx.Response(200, json={"properties": {"t": {"type": "title", "title": [
            {"plain_text": "System Architecture"}]}}})

    _patch_probe(monkeypatch, ok)
    r = CliRunner().invoke(app, ["sources", "health"])
    assert r.exit_code == 0, r.output
    assert "실증 테스트" in r.output and "어느 워크스페이스" in r.output
    assert "System Architecture" in r.output
    assert _TOKEN not in r.output


def test_an_unreachable_root_prints_its_remedy_and_exits_nonzero(monkeypatch):
    """진단이 문제를 찾았으면 종료코드로도 말한다 — 스크립트가 읽을 수 있어야 한다."""
    def unreachable(request):
        if request.url.path == "/v1/users/me":
            return httpx.Response(200, json={"name": "b", "bot": {"workspace_name": "w"}})
        return httpx.Response(404, json={"code": "object_not_found"})

    _patch_probe(monkeypatch, unreachable)
    r = CliRunner().invoke(app, ["sources", "health"])
    assert r.exit_code == 1
    assert "Connections" in r.output or "연결" in r.output


def test_health_survives_notion_being_down(monkeypatch):
    def dead(request):
        raise httpx.ConnectError("no route to host")

    _patch_probe(monkeypatch, dead)
    r = CliRunner().invoke(app, ["sources", "health"])
    assert r.exit_code == 1                       # 모른다 = 초록이 아니다
    assert "확인하지 못" in r.output
    assert _TOKEN not in r.output
