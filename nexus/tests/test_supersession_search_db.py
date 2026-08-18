"""DB-backed proof of the DOCUMENT-LEVEL supersession search gate (entropy spine, Slice 1 §5.2).

When a document row is `status='superseded'`, none of its chunks may surface as search
candidates — even if a chunk row is still `status='active'` (a cascade miss). This gate is
INDEPENDENT of the chunk-level `c.status = 'active'` gate: document B below has an active
chunk but a superseded document, and must still be excluded.

Runs against a **real Postgres** (docker-compose.test.yml, migration 001 applied). Uses its own
SelectorEventLoop + injected pool — pytest-asyncio's async fixtures are broken on this Windows
env (see test_a2a_provenance_db). Skips (loudly) if NEXUS_TEST_DB_URL is unset.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

from nexus.rid import chunk_rid, doc_rid

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요 (docker-compose.test.yml)")

_TENANT = "default"
_TERM = "supersessionmarker"  # single ascii token → tsquery "'supersessionmarker'"

_DOC_A = doc_rid("specs/active-A.md")
_DOC_B = doc_rid("specs/superseded-B.md")
_CHUNK_A = chunk_rid(_DOC_A, "root", 0)
_CHUNK_B = chunk_rid(_DOC_B, "root", 0)


def _run(coro_fn):
    """Own SelectorEventLoop (asyncpg needs it on Windows). Wire nexus.db to the test pool."""
    from nexus import db

    loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()

    async def _outer():
        import asyncpg
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        db._pool = pool
        try:
            async with pool.acquire() as con:
                await con.execute("TRUNCATE documents, chunks CASCADE")
            return await coro_fn()
        finally:
            await pool.close()
            db._pool = None

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()


async def _seed_doc(rid: str, source_uri: str, status: str) -> None:
    from nexus import db
    await db.execute(
        """
        INSERT INTO documents (rid, tenant, classification, source_uri, hash, status, title)
        VALUES ($1, $2, 'INTERNAL', $3, 'h', $4::resource_status, $5)
        """,
        rid, _TENANT, source_uri, status, source_uri,
    )


async def _seed_chunk(rid: str, doc: str, source_uri: str) -> None:
    """Active, non-quarantined, INTERNAL chunk whose tsvector contains the search term."""
    from nexus import db
    await db.execute(
        """
        INSERT INTO chunks (rid, tenant, classification, source_uri, doc_rid, chunk_text,
                            is_quarantined, status, tsvector_ko)
        VALUES ($1, $2, 'INTERNAL', $3, $4, $5, false, 'active',
                to_tsvector('simple', $5))
        """,
        rid, _TENANT, source_uri, doc, f"{_TERM} content",
    )


def test_superseded_document_chunk_excluded_from_bm25_candidates():
    from nexus import db
    from nexus.search.hybrid import _bm25_search

    async def inner():
        # doc A active, doc B superseded — BUT both chunks left at status='active'
        await _seed_doc(_DOC_A, "specs/active-A.md", "active")
        await _seed_doc(_DOC_B, "specs/superseded-B.md", "superseded")
        await _seed_chunk(_CHUNK_A, _DOC_A, "specs/active-A.md")
        await _seed_chunk(_CHUNK_B, _DOC_B, "specs/superseded-B.md")

        # sanity: B's chunk really IS active (cascade-miss simulation), so the exclusion
        # cannot be explained by the chunk-level gate.
        b_status = await db.fetch_val("SELECT status FROM chunks WHERE rid = $1", _CHUNK_B)
        assert b_status == "active"

        results, _top = await _bm25_search(_TERM, _TENANT, "INTERNAL", top_k=20)
        rids = {rid for rid, _rank in results}

        assert _CHUNK_A in rids, "active document's chunk must be a candidate"
        assert _CHUNK_B not in rids, (
            "superseded document's chunk must be excluded even though its chunk row is active "
            "(document-level gate independent of chunk-level gate)"
        )

    _run(inner)
