"""문서 생애주기 HTTP 계약 — SPEC-nexus-document-lifecycle §4.3 · §4.4 · §5.

여기서 고정하는 것:
  · origin 유도 (notion / upload / file), 잘못된 접미사는 URL 을 **추측하지 않는다**
  · status 필터가 응답이 내보내는 모든 상태를 받는다 (pruned 가 도달 불가하면 안 된다)
  · manage_documents 없으면 파괴적 경로는 전부 403 — /supersede 포함
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "acme"


# ── §4.3 origin 유도 (순수) ───────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("source_uri", "origin", "url"),
    [
        (f"{_TENANT}:ext-notion-2740c71b-b9dc-80ef-b43a-ea3676e632c8.md",
         "notion", "https://www.notion.so/2740c71bb9dc80efb43aea3676e632c8"),
        (f"{_TENANT}:uploads/note.md", "upload", None),
        (f"{_TENANT}:docs/design/api.md", "file", None),
        # 접미사가 canonical page id 가 아니면 URL 을 **추측하지 않는다**
        (f"{_TENANT}:ext-notion-not-a-page-id.md", "notion", None),
    ],
)
def test_origin_is_derived_from_source_uri(source_uri, origin, url):
    from nexus.documents.origin import derive_origin

    assert derive_origin(source_uri) == (origin, url)


# ── §4.4 status 필터 → SQL 술어 (순수) ────────────────────────────────────────

def test_every_reportable_status_is_also_a_filter_value():
    """pruned 를 응답에 내보내면서 필터로 못 받으면 그 행에 도달할 길이 없다 (I-006)."""
    from nexus.documents.filters import STATUS_FILTERS

    assert set(STATUS_FILTERS) == {"active", "hidden", "pruned", "superseded", "all"}


def test_hidden_and_pruned_are_the_same_status_different_hold():
    from nexus.documents.filters import STATUS_FILTERS

    assert "hold = true" in STATUS_FILTERS["hidden"].lower()
    assert "hold = false" in STATUS_FILTERS["pruned"].lower()
    assert "soft_deleted" in STATUS_FILTERS["hidden"]
    assert "soft_deleted" in STATUS_FILTERS["pruned"]


# ── HTTP ──────────────────────────────────────────────────────────────────────

def _client(capabilities=("manage_documents",)):
    from contextlib import asynccontextmanager

    from nexus import db
    from nexus.auth import Principal
    from nexus.documents.api import dep, router
    from nexus.documents.schema import ensure_lifecycle_schema

    @asynccontextmanager
    async def lifespan(app):
        import asyncpg
        pool = await asyncpg.create_pool(os.environ["NEXUS_TEST_DB_URL"], min_size=1, max_size=5)
        db._pool = pool
        async with pool.acquire() as con:
            await ensure_lifecycle_schema(con)
            await con.execute("TRUNCATE documents, chunks, doc_supersession_events CASCADE")
            await con.execute(
                "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title, status) "
                "VALUES ('doc_a', $1, $2, 'h', 'h', '결제 정책', 'active'), "
                "       ('doc_b', $1, $3, 'h2', 'h2', '배포 런북', 'active')",
                _TENANT, f"{_TENANT}:ext-notion-2740c71b-b9dc-80ef-b43a-ea3676e632c8.md",
                f"{_TENANT}:uploads/runbook.md",
            )
        try:
            yield
        finally:
            await pool.close()
            db._pool = None

    app = FastAPI(lifespan=lifespan)
    app.include_router(router)
    app.dependency_overrides[dep] = lambda: Principal(
        name="t", tenant=_TENANT, clearance="INTERNAL", capabilities=tuple(capabilities))
    return TestClient(app)


def test_list_returns_origin_and_link():
    with _client() as c:
        rows = c.get("/documents", params={"tenant": _TENANT}).json()["data"]["documents"]
        by_rid = {r["rid"]: r for r in rows}
        assert by_rid["doc_a"]["origin"] == "notion"
        assert by_rid["doc_a"]["origin_url"].endswith("2740c71bb9dc80efb43aea3676e632c8")
        assert by_rid["doc_b"]["origin"] == "upload" and by_rid["doc_b"]["origin_url"] is None


def test_title_search_is_case_insensitive_substring():
    with _client() as c:
        rows = c.get("/documents", params={"q": "결제"}).json()["data"]["documents"]
        assert [r["rid"] for r in rows] == ["doc_a"]
        assert c.get("/documents", params={"q": "없는제목"}).json()["data"]["documents"] == []


def test_hide_then_the_document_is_only_visible_under_the_hidden_filter():
    with _client() as c:
        assert c.post("/documents/doc_a/hide").status_code == 200
        assert [r["rid"] for r in c.get("/documents").json()["data"]["documents"]] == ["doc_b"]

        hidden = c.get("/documents", params={"status": "hidden"}).json()["data"]["documents"]
        assert [r["rid"] for r in hidden] == ["doc_a"]
        assert hidden[0]["hold"] is True

        # pruned 필터에는 안 잡힌다 — 사람이 숨긴 것이지 재조정이 내린 게 아니다
        assert c.get("/documents", params={"status": "pruned"}).json()["data"]["documents"] == []

        assert c.post("/documents/doc_a/restore").status_code == 200
        assert len(c.get("/documents").json()["data"]["documents"]) == 2


def test_restore_a_superseded_document_is_409():
    with _client() as c:
        assert c.post("/supersede", json={"old_ref": "doc_a", "new_ref": "doc_b"}).status_code == 200
        r = c.post("/documents/doc_a/restore")
        assert r.status_code == 409 and "unsupersede" in r.text


def test_unsupersede_requires_a_reason():
    with _client() as c:
        c.post("/supersede", json={"old_ref": "doc_a", "new_ref": "doc_b"})
        assert c.post("/documents/doc_a/unsupersede", json={"reason": "   "}).status_code == 400
        assert c.post("/documents/doc_a/unsupersede", json={"reason": "오지정"}).status_code == 200
        assert len(c.get("/documents").json()["data"]["documents"]) == 2


def test_hide_a_superseded_document_is_409():
    with _client() as c:
        c.post("/supersede", json={"old_ref": "doc_a", "new_ref": "doc_b"})
        assert c.post("/documents/doc_a/hide").status_code == 409


# ── §4.4 capability (파괴적 경로 전부) ────────────────────────────────────────

def test_destructive_paths_require_manage_documents_including_supersede():
    """/supersede 는 지금까지 무권한이었다 — 인증만 하면 누구나 문서를 검색에서 지웠다."""
    with _client(capabilities=()) as c:
        assert c.get("/documents").status_code == 200                       # 읽기는 열려 있다
        assert c.post("/documents/doc_a/hide").status_code == 403
        assert c.post("/documents/doc_a/restore").status_code == 403
        assert c.post("/documents/doc_a/unsupersede", json={"reason": "r"}).status_code == 403
        assert c.post("/supersede", json={"old_ref": "doc_a", "new_ref": "doc_b"}).status_code == 403
