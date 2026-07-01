"""DB-backed test: chunks of a non-active document stay superseded on re-ingest.

Regression guard (Nexus 엔트로피 척추 Slice 1, final review): editing/re-ingesting a
SUPERSEDED document's source must NOT reactivate its chunks. `supersede(old,new)` marks
the doc `superseded` and cascades `chunks.status='superseded'`; a later `_save_chunks`
(edited source / `nexus ingest --force`) previously flipped those chunks back to `active`
via `ON CONFLICT DO UPDATE SET status='active'`, manufacturing the exact
"active chunks under a dead document" split the entropy feature exists to prevent.

The fix: chunk status tracks the parent document's status at save time — active doc ⇒
chunks active (unchanged), non-active doc ⇒ chunks written/updated as superseded.

Own SelectorEventLoop + asyncpg pool injected into nexus.db — pytest-asyncio's async
fixtures are broken on this Windows env (mirrors test_a2a_provenance_db.py).
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요 (docker-compose.test.yml)")

_TENANT = "acme"


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


def _make_inputs(uri: str):
    from nexus.ingest.classifier import ClassificationResult
    from nexus.ingest.collector import CollectedFile

    collected = CollectedFile(
        path=__import__("pathlib").Path(uri),
        relative_path=uri,
        content="body",
        content_hash="hash-" + uri,
        frontmatter={},
        canonical_uri=uri,
    )
    classification = ClassificationResult(classification="INTERNAL", language="ko")
    return collected, classification


def test_reingest_of_superseded_doc_keeps_chunks_superseded():
    """A superseded doc's re-ingested chunks (upserted + brand-new) stay superseded."""
    from nexus import db
    from nexus.ingest.chunker import ChunkData
    from nexus.ingest.pipeline import _save_chunks, _save_document
    from nexus.rid import chunk_rid
    from nexus.supersede import supersede

    async def inner():
        # 1) seed active doc A (with a chunk) and active replacement doc B
        col_a, cls_a = _make_inputs("specs/old.md")
        rid_a = await _save_document(col_a, cls_a, _TENANT)
        section, idx0 = "root", 0
        await _save_chunks(
            [ChunkData(chunk_text="original A text", section_path=section, chunk_index=idx0, token_count=2)],
            rid_a, col_a, cls_a, _TENANT,
        )

        col_b, cls_b = _make_inputs("specs/new.md")
        rid_b = await _save_document(col_b, cls_b, _TENANT)

        # 2) supersede A by B ⇒ A superseded, A's chunks superseded
        assert await supersede(rid_a, rid_b, _TENANT) == "superseded"
        doc_status = await db.fetch_val("SELECT status FROM documents WHERE rid=$1", rid_a)
        assert doc_status == "superseded"

        # 3) re-ingest A's source (edited): same section/idx ⇒ ON CONFLICT upsert,
        #    plus a brand-new chunk (idx 1). Simulates editing the dead source file.
        chunk_rid_0 = chunk_rid(rid_a, section, idx0)
        chunk_rid_1 = chunk_rid(rid_a, section, 1)
        await _save_chunks(
            [
                ChunkData(chunk_text="EDITED A text", section_path=section, chunk_index=idx0, token_count=2),
                ChunkData(chunk_text="NEW A chunk", section_path=section, chunk_index=1, token_count=2),
            ],
            rid_a, col_a, cls_a, _TENANT,
        )

        # 4) doc still superseded; both chunks superseded (NOT reactivated)
        assert await db.fetch_val("SELECT status FROM documents WHERE rid=$1", rid_a) == "superseded"
        st0 = await db.fetch_val("SELECT status FROM chunks WHERE rid=$1", chunk_rid_0)
        st1 = await db.fetch_val("SELECT status FROM chunks WHERE rid=$1", chunk_rid_1)
        assert st0 == "superseded", f"upserted chunk must stay superseded, got {st0!r}"
        assert st1 == "superseded", f"new chunk under a dead doc must be superseded, got {st1!r}"

        # no active chunk may exist under a superseded document
        active = await db.fetch_val(
            "SELECT count(*) FROM chunks WHERE doc_rid=$1 AND status='active'", rid_a)
        assert active == 0, "a superseded document must have zero active chunks"

    _run(inner)


def test_reingest_of_active_doc_keeps_chunks_active():
    """Contrast: the guard is conditional — an ACTIVE doc's re-ingested chunks stay active."""
    from nexus import db
    from nexus.ingest.chunker import ChunkData
    from nexus.ingest.pipeline import _save_chunks, _save_document
    from nexus.rid import chunk_rid

    async def inner():
        col, cls = _make_inputs("specs/live.md")
        rid = await _save_document(col, cls, _TENANT)
        section, idx0 = "root", 0

        await _save_chunks(
            [ChunkData(chunk_text="original text", section_path=section, chunk_index=idx0, token_count=2)],
            rid, col, cls, _TENANT,
        )
        # re-ingest (edited) while the doc is still active
        await _save_chunks(
            [ChunkData(chunk_text="EDITED text", section_path=section, chunk_index=idx0, token_count=2)],
            rid, col, cls, _TENANT,
        )

        st = await db.fetch_val("SELECT status FROM chunks WHERE rid=$1", chunk_rid(rid, section, idx0))
        assert st == "active", f"active doc's re-ingested chunk must stay active, got {st!r}"

    _run(inner)
