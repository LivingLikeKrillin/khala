"""DB-backed test: re-embedding jitter fix (Nexus 엔트로피 척추 Slice 1, Task 4).

`_save_chunks`' upsert must invalidate (NULL) a chunk's embedding/tsvector ONLY when
its TEXT actually changed. Chunks whose text is unchanged must KEEP their existing
embedding/tsvector — otherwise every re-ingest needlessly re-embeds every chunk ("jitter").

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


async def _seed_vectors(db, rid: str) -> None:
    """Set the chunk's embedding + tsvector to non-NULL, simulating a completed index run."""
    await db.execute(
        """
        UPDATE chunks
        SET embedding = array_fill(0.1::float8, ARRAY[768])::vector,
            tsvector_ko = to_tsvector('simple', 'seeded')
        WHERE rid = $1
        """,
        rid,
    )


def test_text_changed_chunk_is_invalidated():
    """Case A: chunk_text differs on re-save ⇒ embedding + tsvector nulled (awaiting recompute)."""
    from nexus import db
    from nexus.ingest.chunker import ChunkData
    from nexus.ingest.pipeline import _save_chunks, _save_document
    from nexus.rid import chunk_rid

    async def inner():
        collected, classification = _make_inputs("specs/case-a.md")
        parent_rid = await _save_document(collected, classification, _TENANT)

        section_path, idx = "root", 0
        rid = chunk_rid(parent_rid, section_path, idx)

        # 1) first save
        await _save_chunks(
            [ChunkData(chunk_text="original text", section_path=section_path, chunk_index=idx, token_count=2)],
            parent_rid, collected, classification, _TENANT,
        )
        # 2) simulate index run: embedding + tsvector populated
        await _seed_vectors(db, rid)
        seeded = await db.fetch_one(
            "SELECT embedding IS NOT NULL AS has_emb, tsvector_ko IS NOT NULL AS has_ts FROM chunks WHERE rid=$1", rid,
        )
        assert seeded["has_emb"] and seeded["has_ts"], "precondition: seeded vectors present"

        # 3) re-save with DIFFERENT text (same rid → ON CONFLICT)
        await _save_chunks(
            [ChunkData(chunk_text="CHANGED text", section_path=section_path, chunk_index=idx, token_count=2)],
            parent_rid, collected, classification, _TENANT,
        )

        row = await db.fetch_one(
            "SELECT chunk_text, embedding, tsvector_ko FROM chunks WHERE rid=$1", rid,
        )
        assert row["chunk_text"] == "CHANGED text"
        assert row["embedding"] is None, "text changed ⇒ embedding must be invalidated (NULL)"
        assert row["tsvector_ko"] is None, "text changed ⇒ tsvector must be invalidated (NULL)"

    _run(inner)


def test_text_unchanged_chunk_is_preserved():
    """Case B: chunk_text identical on re-save ⇒ embedding + tsvector preserved (no jitter)."""
    from nexus import db
    from nexus.ingest.chunker import ChunkData
    from nexus.ingest.pipeline import _save_chunks, _save_document
    from nexus.rid import chunk_rid

    async def inner():
        collected, classification = _make_inputs("specs/case-b.md")
        parent_rid = await _save_document(collected, classification, _TENANT)

        section_path, idx = "root", 0
        rid = chunk_rid(parent_rid, section_path, idx)
        same_text = "unchanged text"

        await _save_chunks(
            [ChunkData(chunk_text=same_text, section_path=section_path, chunk_index=idx, token_count=2)],
            parent_rid, collected, classification, _TENANT,
        )
        await _seed_vectors(db, rid)

        # re-save with the SAME text
        await _save_chunks(
            [ChunkData(chunk_text=same_text, section_path=section_path, chunk_index=idx, token_count=2)],
            parent_rid, collected, classification, _TENANT,
        )

        row = await db.fetch_one(
            "SELECT chunk_text, embedding, tsvector_ko FROM chunks WHERE rid=$1", rid,
        )
        assert row["chunk_text"] == same_text
        assert row["embedding"] is not None, "text unchanged ⇒ embedding must be preserved"
        assert row["tsvector_ko"] is not None, "text unchanged ⇒ tsvector must be preserved"

    _run(inner)
