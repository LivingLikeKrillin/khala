"""연결 진단 HTTP 표면 + 자격증명 불변식 — SPEC-nexus-notion-connection-health §4.4~§4.6, §6.

여기서 고정하는 것:
  · `GET /sources/notion/health` 는 `manage_sources` 뒤에 있다. 토큰만 비밀이 아니다 —
    워크스페이스 이름과 문서 제목도 조직 문서 트리의 모양을 드러낸다.
  · Notion 이 통째로 죽어도 이 엔드포인트는 200 을 준다. 진단이 진단 대상과 함께 죽으면
    정작 필요할 때 쓸모가 없다.
  · root 등록은 **거부하지 않는다.** 등록하고 나서 Notion 에서 공유하는 건 정상 순서다.
    다만 그 자리에서 도달 불가를 말해 준다.
  · 토큰 값은 `notion_sync_runs.reason` 에 영원히 남을 수 있는 유일한 경로다. 지운다.
"""

from __future__ import annotations

import os

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "acme"
_TOKEN = "ntn_secret_value_do_not_leak_0000000000"
_PAGE = "fc054c8f-cc62-409c-8154-deafb826cac9"


@pytest.fixture(autouse=True)
def _restore_probe():
    """각 테스트가 `probe_connection` 을 갈아끼운다. 되돌리지 않으면 다음 테스트의 `real` 이
    앞 테스트의 패치본이 되고, transport 인자가 삼켜져 첫 handler 가 영원히 쓰인다."""
    import nexus.sources.api as sources_api
    original = sources_api.probe_connection
    yield
    sources_api.probe_connection = original


def _client(capabilities=("manage_sources",), notion_token=_TOKEN, handler=None):
    from contextlib import asynccontextmanager

    from nexus import db
    from nexus.auth import Principal
    from nexus.sources.api import dep, router
    from nexus.sources.schema import ensure_schema

    @asynccontextmanager
    async def lifespan(app):
        import asyncpg
        pool = await asyncpg.create_pool(os.environ["NEXUS_TEST_DB_URL"], min_size=1, max_size=5)
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
        name="t", tenant=_TENANT, clearance="INTERNAL", capabilities=tuple(capabilities))

    if notion_token:
        os.environ["NOTION_TOKEN"] = notion_token
    else:
        os.environ.pop("NOTION_TOKEN", None)

    if handler is not None:
        import nexus.sources.api as sources_api
        from nexus.sources.notion_health import probe_connection as real   # 항상 원본

        async def patched(token, roots, **_):
            return await real(token, roots, transport=httpx.MockTransport(handler))

        sources_api.probe_connection = patched
    return TestClient(app)


def _ok(request):
    if request.url.path == "/v1/users/me":
        return httpx.Response(200, json={"name": "실증 테스트",
                                         "bot": {"workspace_name": "어느 워크스페이스"}})
    return httpx.Response(200, json={"properties": {"t": {"type": "title",
                                                          "title": [{"plain_text": "System Architecture"}]}}})


def _unreachable(request):
    if request.url.path == "/v1/users/me":
        return httpx.Response(200, json={"name": "bot", "bot": {"workspace_name": "w"}})
    return httpx.Response(404, json={"code": "object_not_found"})


# ── §4.5 게이트 ───────────────────────────────────────────────────────────────

def test_health_requires_manage_sources():
    """토큰만 비밀이 아니다 — 워크스페이스·문서 제목도 조직의 모양을 드러낸다 (I-002)."""
    with _client(capabilities=(), handler=_ok) as c:
        assert c.get("/sources/notion/health").status_code == 403


def test_health_reports_the_integration_and_the_workspace():
    with _client(handler=_ok) as c:
        c.post("/sources/notion/roots", json={"url_or_id": _PAGE})
        d = c.get("/sources/notion/health").json()["data"]

        assert d["token"]["state"] == "ok"
        assert d["token"]["integration"] == "실증 테스트"
        assert d["token"]["workspace"] == "어느 워크스페이스"
        assert d["token"]["prefix"] == "ntn_"
        assert d["roots"][0]["state"] == "reachable"
        assert d["roots"][0]["title"] == "System Architecture"
        assert d["checked_at"]


def test_health_is_200_even_when_notion_is_entirely_down():
    """진단이 진단 대상과 함께 죽으면 정작 필요할 때 쓸모가 없다."""
    def dead(request):
        raise httpx.ConnectError("no route to host")

    with _client(handler=dead) as c:
        c.post("/sources/notion/roots", json={"url_or_id": _PAGE})
        r = c.get("/sources/notion/health")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["token"]["state"] == "unknown"
        assert d["roots"][0]["state"] == "unknown"


def test_health_without_a_token_is_not_configured():
    with _client(notion_token="", handler=_ok) as c:
        d = c.get("/sources/notion/health").json()["data"]
        assert d["token"]["state"] == "not_configured"
        assert d["token"]["prefix"] == ""


def test_the_health_response_never_carries_the_token_or_an_exception_string():
    def leaky(request):
        raise httpx.ConnectError(f"Authorization: Bearer {_TOKEN}")

    with _client(handler=leaky) as c:
        c.post("/sources/notion/roots", json={"url_or_id": _PAGE})
        body = c.get("/sources/notion/health").text
        assert _TOKEN not in body and "Bearer" not in body


def test_the_health_response_has_no_field_for_free_text():
    """응답을 allow-list 로 못 박는다 — 나중에 `str(e)` 를 끼워 넣으면 이 테스트가 깨진다 (I-003)."""
    with _client(handler=_unreachable) as c:
        c.post("/sources/notion/roots", json={"url_or_id": _PAGE})
        d = c.get("/sources/notion/health").json()["data"]
        assert set(d) == {"token", "roots", "checked_at"}
        assert set(d["token"]) == {"state", "integration", "workspace", "prefix"}
        assert set(d["roots"][0]) == {"root_id", "state", "title", "remedy"}


# ── §4.4 등록은 보고하되 거부하지 않는다 ──────────────────────────────────────

def test_registering_an_unreachable_root_still_writes_the_row_and_says_so():
    """등록하고 나서 Notion 에서 공유하는 것은 정상 순서다. 거부하면 그 흐름이 깨진다 (I-004)."""
    with _client(handler=_unreachable) as c:
        r = c.post("/sources/notion/roots", json={"url_or_id": _PAGE})
        assert r.status_code == 201
        d = r.json()["data"]
        assert d["state"] == "unreachable"
        assert "integration" in d["remedy"]
        assert d["title"] is None

        roots = c.get("/sources/notion/roots").json()["data"]["roots"]
        assert [x["root_id"] for x in roots] == [_PAGE]      # 행은 쓰였다


def test_registering_a_reachable_root_returns_its_title():
    with _client(handler=_ok) as c:
        d = c.post("/sources/notion/roots", json={"url_or_id": _PAGE}).json()["data"]
        assert d["state"] == "reachable" and d["title"] == "System Architecture"


def test_registration_still_rejects_garbage_that_is_not_a_page_id():
    with _client(handler=_ok) as c:
        assert c.post("/sources/notion/roots", json={"url_or_id": "그냥 문장"}).status_code == 400


def test_registration_without_a_token_writes_the_row_and_reports_unknown():
    with _client(notion_token="", handler=_ok) as c:
        d = c.post("/sources/notion/roots", json={"url_or_id": _PAGE}).json()["data"]
        assert d["state"] == "unknown"
        assert len(c.get("/sources/notion/roots").json()["data"]["roots"]) == 1
