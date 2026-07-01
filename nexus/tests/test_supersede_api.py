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
_RID_A = doc_rid("specs/A.md")
_RID_B = doc_rid("specs/B.md")
_CHUNK_A = chunk_rid(_RID_A, "", 0)


async def _seed(conn) -> None:
    """활성 문서 A(청크 1개) + 활성 문서 B 를 시드한다."""
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


def _client() -> TestClient:
    """/supersede 만 마운트한 최소 앱. lifespan에서 풀을 portal 루프에 바인딩·시드하고,
    get_principal을 테넌트 acme 프린시펄로 오버라이드한다."""
    from nexus.api import NexusResponse, get_principal, supersede_docs

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        import asyncpg

        from nexus import db

        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        db._pool = pool
        async with pool.acquire() as con:
            await con.execute("TRUNCATE documents, chunks CASCADE")
            await _seed(con)
        try:
            yield
        finally:
            await pool.close()
            db._pool = None

    app = FastAPI(lifespan=lifespan)
    app.post("/supersede", response_model=NexusResponse)(supersede_docs)
    app.dependency_overrides[get_principal] = lambda: Principal(
        name="test", tenant=_TENANT, clearance="INTERNAL",
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
            json={"old_rid": _RID_A, "new_rid": _RID_B, "tenant": _TENANT},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["result"] == "superseded"


def test_self_supersession_is_400():
    """자기참조(old==new)는 ValueError → HTTP 400, 메시지가 detail로 노출된다."""
    with _client() as client:
        resp = client.post(
            "/supersede",
            json={"old_rid": _RID_A, "new_rid": _RID_A, "tenant": _TENANT},
        )
    assert resp.status_code == 400, resp.text
    assert "self-supersession" in resp.json()["detail"]
