"""DB-backed test for the re-ingest event hook (Nexus 엔트로피 척추 Slice 1, Task 5).

Proves against a **real Postgres** (docker-compose.test.yml) that `_save_document`
appends exactly one `doc_reingest_events` row **only when a document's content_hash
changes** versus the previously stored row — never on first save, never on an
unchanged re-save. This is the overwrite signal feeding `v_entropy_signals`.

Uses its own SelectorEventLoop — pytest-asyncio's async fixtures are broken on this
Windows env (see test_a2a_provenance_db.py which this mirrors).
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요 (docker-compose.test.yml)")

_TENANT = "acme"
_URI = "acme:specs/reingest-me.md"


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
                await con.execute("TRUNCATE documents, chunks, doc_reingest_events CASCADE")
            return await coro_fn()
        finally:
            await pool.close()
            db._pool = None

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()


def _collected(content_hash: str):
    from nexus.ingest.collector import CollectedFile
    return CollectedFile(
        path="/tmp/reingest-me.md",  # type: ignore[arg-type]  # not touched by _save_document
        relative_path="specs/reingest-me.md",
        content="# Reingest Me\n\n본문 텍스트.",
        content_hash=content_hash,
        frontmatter={},
        canonical_uri=_URI,
    )


def _classification():
    from nexus.ingest.classifier import ClassificationResult
    return ClassificationResult()  # INTERNAL, not quarantined, ko/markdown


def test_reingest_event_only_on_content_hash_change():
    from nexus import db
    from nexus.ingest.pipeline import _save_document
    from nexus.rid import doc_rid

    async def inner():
        rid = doc_rid(_URI)

        async def event_count():
            return await db.fetch_val(
                "SELECT count(*) FROM doc_reingest_events WHERE rid = $1", rid,
            )

        # (a) first save (new doc) → no prior row → no event
        await _save_document(_collected("hash-v1"), _classification(), _TENANT)
        assert await event_count() == 0, "first save must not append an event"

        # (b) re-save with the SAME content_hash → unchanged → still no event
        await _save_document(_collected("hash-v1"), _classification(), _TENANT)
        assert await event_count() == 0, "unchanged re-save must not append an event"

        # (c) re-save with a DIFFERENT content_hash → exactly one event, old→new
        await _save_document(_collected("hash-v2"), _classification(), _TENANT)
        assert await event_count() == 1, "changed content_hash must append exactly one event"

        row = await db.fetch_one(
            "SELECT old_content_hash, new_content_hash, tenant "
            "FROM doc_reingest_events WHERE rid = $1", rid,
        )
        assert row["old_content_hash"] == "hash-v1"
        assert row["new_content_hash"] == "hash-v2"
        assert row["tenant"] == _TENANT

    _run(inner)
