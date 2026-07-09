"""외부-적재 후처리 메타데이터(label / doc_type / prov_inputs) 규칙을 REAL Postgres 로 검증한다.

이 로직은 원래 a2a/server.py 의 _default_external_ingest_fn 안에 인라인이었고, run_ingest(임베딩·
mecab) 의존 때문에 테스트가 없었다. DB 쓰기만 떼어내 규칙을 고정한다.

핵심 규칙:
  · quarantined 행에는 **아무것도** 쓰지 않는다.
  · label/doc_type 은 실제로 재색인된 경우에만 쓴다(기존 동작).
  · prov_inputs(source_roots)는 **멱등 히트에도** 쓴다 — 그래야 백필이 성립한다
    (SPEC-nexus-notion-reconciliation §3.1).
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요 (docker-compose.test.yml)")

_TENANT = "acme"
_RID = "doc_extmeta0001"
_RID_Q = "doc_extmeta0002"


async def _seed(conn) -> None:
    for rid, quar in ((_RID, False), (_RID_Q, True)):
        await conn.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, doc_type, is_quarantined) "
            "VALUES ($1, $2, $3, 'h', 'h', 'markdown', $4)",
            rid, _TENANT, f"{_TENANT}:ext-notion-{rid}.md", quar,
        )


def _run(coro_fn):
    from nexus import db

    loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()

    async def _outer():
        import asyncpg
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        db._pool = pool
        try:
            async with pool.acquire() as con:
                await con.execute("TRUNCATE documents, chunks CASCADE")
                await _seed(con)
            return await coro_fn()
        finally:
            await pool.close()
            db._pool = None

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()


def _doc(roots=None, kind="ADR"):
    prov = {"source_tool": "notion", "source_id": "p1"}
    if roots:
        prov["source_roots"] = roots
    return {"id": "ext-notion-p1", "kind": kind, "body": "x", "provenance": prov}


def test_fresh_ingest_writes_label_doc_type_and_provenance():
    from nexus import db
    from nexus.ingest.external_metadata import EXTERNAL_LABEL, apply_external_metadata

    async def inner():
        await apply_external_metadata(_RID, _TENANT, _doc(roots=["rootA"]),
                                      idempotent=False, quarantined=False)
        row = await db.fetch_one(
            "SELECT labels, doc_type, prov_inputs FROM documents WHERE rid=$1", _RID)
        assert EXTERNAL_LABEL in row["labels"]
        assert row["doc_type"] == "ADR"
        assert row["prov_inputs"] == ["rootA"]

    _run(inner)


def test_idempotent_hit_still_writes_provenance_but_not_label():
    """변경 없는 페이지도 root 귀속은 갱신되어야 한다 — 아니면 레거시 행이 영영 백필되지 않는다."""
    from nexus import db
    from nexus.ingest.external_metadata import EXTERNAL_LABEL, apply_external_metadata

    async def inner():
        await apply_external_metadata(_RID, _TENANT, _doc(roots=["rootA"]),
                                      idempotent=True, quarantined=False)
        row = await db.fetch_one(
            "SELECT labels, doc_type, prov_inputs FROM documents WHERE rid=$1", _RID)
        assert row["prov_inputs"] == ["rootA"]      # 기록됨
        assert EXTERNAL_LABEL not in row["labels"]  # 재색인 없었으므로 라벨은 그대로
        assert row["doc_type"] == "markdown"        # doc_type 도 그대로

    _run(inner)


def test_label_is_not_duplicated_on_repeat():
    from nexus import db
    from nexus.ingest.external_metadata import EXTERNAL_LABEL, apply_external_metadata

    async def inner():
        for _ in range(3):
            await apply_external_metadata(_RID, _TENANT, _doc(), idempotent=False, quarantined=False)
        row = await db.fetch_one("SELECT labels FROM documents WHERE rid=$1", _RID)
        assert row["labels"].count(EXTERNAL_LABEL) == 1

    _run(inner)


def test_quarantined_row_receives_nothing():
    from nexus import db
    from nexus.ingest.external_metadata import apply_external_metadata

    async def inner():
        await apply_external_metadata(_RID_Q, _TENANT, _doc(roots=["rootA"]),
                                      idempotent=False, quarantined=True)
        row = await db.fetch_one(
            "SELECT labels, doc_type, prov_inputs FROM documents WHERE rid=$1", _RID_Q)
        assert row["labels"] == []
        assert row["doc_type"] == "markdown"
        assert row["prov_inputs"] == []

    _run(inner)


def test_missing_source_roots_leaves_prov_inputs_alone():
    """비-Notion 외부 적재(source_roots 없음)는 prov_inputs 를 건드리지 않는다."""
    from nexus import db
    from nexus.ingest.external_metadata import apply_external_metadata

    async def inner():
        await apply_external_metadata(_RID, _TENANT, _doc(), idempotent=False, quarantined=False)
        row = await db.fetch_one("SELECT prov_inputs FROM documents WHERE rid=$1", _RID)
        assert row["prov_inputs"] == []

    _run(inner)
