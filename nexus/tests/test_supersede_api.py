"""POST /supersede 엔드포인트를 REAL Postgres에 대해 end-to-end로 검증한다 (스펙 §5.3, Task 7).

라우트 → supersede() 코어 → NexusResponse 봉투(payload는 data 하위)까지 실제 HTTP로 관통한다.

NOTE(Windows + asyncpg): asyncpg는 SelectorEventLoop를 요구한다. TestClient의 blocking
portal이 그 정책으로 루프를 만들도록 정책을 세팅하고, 최소 앱의 lifespan에서 풀을 그 루프에
바인딩·시드한다(테넌트 격리: effective_scope는 principal.tenant를 쓰므로 시드도 그 테넌트).
"""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from nexus.auth.principal import Principal
from nexus.rid import chunk_rid, doc_rid

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요 (docker-compose.test.yml)")

_TENANT = "acme"
_OTHER_TENANT = "rival"  # principal 은 acme — 이 테넌트 문서는 절대 손대면 안 된다
_RID_A = doc_rid("specs/A.md")
_RID_B = doc_rid("specs/B.md")
_CHUNK_A = chunk_rid(_RID_A, "", 0)
_RID_FOREIGN = doc_rid("specs/FOREIGN.md")  # rival 테넌트의 활성 문서
_RID_SUP = doc_rid("specs/SUP.md")  # acme 테넌트의 superseded(비활성) 문서


async def _seed(conn) -> None:
    """활성 A(청크 1개)+활성 B(테넌트 acme) + rival 테넌트의 활성 문서 하나를 시드한다."""
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
    # 다른 테넌트(rival)의 활성 문서 — acme principal 의 supersede 가 못 건드려야 한다.
    await conn.execute(
        "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, status) "
        "VALUES ($1, $2, $3, $4, $5, 'active')",
        _RID_FOREIGN, _OTHER_TENANT, "specs/FOREIGN.md", "hash-f", "chash-f",
    )
    # acme 테넌트의 superseded(비활성) 문서 — resolver 는 rid passthrough(status-agnostic)로
    # 이 rid 를 그대로 통과시키고, core 가 active 여부를 재검증한다(seam guard).
    await conn.execute(
        "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, status, superseded_by) "
        "VALUES ($1, $2, $3, $4, $5, 'superseded', $6)",
        _RID_SUP, _TENANT, "specs/SUP.md", "hash-s", "chash-s", _RID_B,
    )


def _doc_status(rid: str, tenant: str) -> str | None:
    """검증용: 별도 SelectorEventLoop 연결로 문서 status 를 되읽는다(요청과 물리 DB 공유)."""
    async def _q():
        import asyncpg

        conn = await asyncpg.connect(DB_URL)
        try:
            return await conn.fetchval(
                "SELECT status FROM documents WHERE rid = $1 AND tenant = $2", rid, tenant,
            )
        finally:
            await conn.close()

    return asyncio.run(_q())


def _client() -> TestClient:
    """/supersede 만 마운트한 최소 앱. lifespan에서 풀을 portal 루프에 바인딩·시드하고,
    principal 을 테넌트 acme + manage_documents 로 오버라이드한다.

    라우트는 nexus.documents.api 로 이전했다(capability 게이트가 붙었다).
    """
    from nexus.documents.api import dep, router

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        import asyncpg

        from nexus import db

        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        db._pool = pool
        async with pool.acquire() as con:
            from nexus.documents.schema import ensure_lifecycle_schema
            await ensure_lifecycle_schema(con)
            await con.execute("TRUNCATE documents, chunks, doc_supersession_events CASCADE")
            await _seed(con)
        try:
            yield
        finally:
            await pool.close()
            db._pool = None

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    app.dependency_overrides[dep] = lambda: Principal(
        name="test", tenant=_TENANT, clearance="INTERNAL",
        capabilities=("manage_documents",),
    )
    return TestClient(app)


@pytest.fixture(autouse=True)
def _selector_loop_policy():
    """asyncpg는 Windows에서 SelectorEventLoop가 필요하다 — TestClient portal 루프에 적용."""
    if sys.platform == "win32":
        prev = asyncio.get_event_loop_policy()
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        try:
            yield
        finally:
            asyncio.set_event_loop_policy(prev)
    else:
        yield


def test_supersede_valid_pair_returns_superseded():
    """활성 A → 활성 B: HTTP 200, data.result == 'superseded' (봉투 하위 payload)."""
    with _client() as client:
        resp = client.post(
            "/supersede",
            json={"old_ref": _RID_A, "new_ref": _RID_B, "tenant": _TENANT},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["result"] == "superseded"


def test_supersede_by_path_ref_returns_superseded():
    with _client() as client:
        resp = client.post("/supersede",
                           json={"old_ref": "specs/A.md", "new_ref": "specs/B.md", "tenant": _TENANT})
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["result"] == "superseded"


def test_self_supersession_is_400():
    """자기참조(old==new)는 ValueError → HTTP 400, 메시지가 detail로 노출된다."""
    with _client() as client:
        resp = client.post(
            "/supersede",
            json={"old_ref": _RID_A, "new_ref": _RID_A, "tenant": _TENANT},
        )
    assert resp.status_code == 400, resp.text
    assert "self-supersession" in resp.json()["detail"]


def test_superseded_new_ref_rejected_400():
    """seam guard: resolver 는 superseded rid 를 status-agnostic 하게 통과시키고,
    core 가 new 는 active 여야 한다며 거부 → HTTP 400.

    (rid 를 ref 로 써서 passthrough 분기를 태운다 — 경로였다면 active-only source_uri
    조회에서 0-match 로 걸러져 다른 경로가 된다.)
    """
    with _client() as client:
        resp = client.post(
            "/supersede",
            json={"old_ref": _RID_A, "new_ref": _RID_SUP, "tenant": _TENANT},
        )
    assert resp.status_code == 400, resp.text
    assert "not found or not active" in resp.json()["detail"]


def test_superseded_old_ref_noops_200():
    """seam guard: old 가 비활성(superseded)이면 core 가 noop → HTTP 200, result=='noop'.

    resolver 는 여기서도 superseded rid 를 그대로 통과시킨다(passthrough).
    """
    with _client() as client:
        resp = client.post(
            "/supersede",
            json={"old_ref": _RID_SUP, "new_ref": _RID_B, "tenant": _TENANT},
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["result"] == "noop"


def test_cross_tenant_old_rid_is_confined_not_superseded():
    """테넌트 격리 회귀 가드: acme principal 이 rival 문서를 old_rid 로 지정해도 손대지 못한다.

    effective_scope 가 req.tenant 를 무시하고 principal.tenant(acme)로 강제하므로,
    supersede 는 acme 스코프에서 old_rid 를 못 찾아 400. rival 문서는 여전히 'active'.
    (이 clamp 를 제거했다면 rival 문서가 supersede 되어 이 테스트가 RED 가 된다 — load-bearing.)
    """
    with _client() as client:
        resp = client.post(
            "/supersede",
            # 클라이언트가 rival 을 요청해도 서버는 principal(acme)로 강제한다.
            json={"old_ref": _RID_FOREIGN, "new_ref": _RID_B, "tenant": _OTHER_TENANT},
        )
    assert resp.status_code == 400, resp.text
    assert "일치하는 active 문서 없음" in resp.json()["detail"]
    # 격리 확인: rival 문서는 손대지 않았다 — 여전히 active.
    assert _doc_status(_RID_FOREIGN, _OTHER_TENANT) == "active"
