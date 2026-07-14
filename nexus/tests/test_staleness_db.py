"""근거 신선도 — updated_at 스레드 (DB 통합) — SPEC-nexus-answer-staleness-warning §5.

_enrich_hits 의 SQL SELECT 가 documents.updated_at 을 SearchHit 로 실어 나르는지(순수 테스트가
못 덮는 부분). NEXUS_TEST_DB_URL 필요.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

pytestmark = pytest.mark.integration

_DB = os.getenv("NEXUS_TEST_DB_URL")


async def test_enrich_threads_document_updated_at_and_doc_type():
    from nexus import db
    from nexus.search.hybrid import _enrich_hits
    os.environ["DATABASE_URL"] = _DB or ""
    await db.get_pool()
    ts = datetime(2025, 1, 15, tzinfo=timezone.utc)
    try:
        await db.execute("DELETE FROM chunks WHERE rid = 'st_c'")
        await db.execute("DELETE FROM documents WHERE rid = 'st_doc'")
        await db.execute(
            "INSERT INTO documents (rid, source_uri, hash, doc_type, updated_at) "
            "VALUES ('st_doc','git://st','h','RUNBOOK',$1)", ts)
        await db.execute(
            "INSERT INTO chunks (rid, source_uri, doc_rid, chunk_text) "
            "VALUES ('st_c','git://st','st_doc','hello')")

        hits = await _enrich_hits(
            [{"rid": "st_c", "score": 1.0, "bm25_rank": 1, "vector_rank": None}], "default")
        assert len(hits) == 1
        assert hits[0].updated_at == ts            # updated_at 이 SearchHit 까지 흘렀다
        assert hits[0].doc_type == "RUNBOOK"
    finally:
        await db.execute("DELETE FROM chunks WHERE rid = 'st_c'")
        await db.execute("DELETE FROM documents WHERE rid = 'st_doc'")
        await db.close_pool()
