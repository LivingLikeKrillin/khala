"""DB-backed live run of the approved_hash provenance loop (Phase 3 §3.2/§5.4).

Proves end-to-end against a **real Postgres** (docker-compose.test.yml): the production A2A
ingest bridge (`server._default_ingest_fn` — exactly what the `ingest_governed_doc` skill calls)
persists the governed doc's `content_hash` into `documents.approved_hash`, and the retrieval
read path (`hybrid._enrich_hits` → `assemble_packet`) surfaces it — so the stamp Arbiter
sends is the stamp a retrieving consumer (Observer's `SpecRef.approvedHash`) reads back.

No Ollama/LLM: vector/graph steps fail gracefully (caught in `run_ingest`); the read-back is
driven from the BM25/enrichment path, which needs neither. Uses its own SelectorEventLoop —
pytest-asyncio's async fixtures are broken on this Windows env (see conftest / test_claim_integration).
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요 (docker-compose.test.yml)")

_TENANT = "acme"
_STAMP = "sha256:arbiter-stamp-abcdef0123456789"
_DOC = {
    "id": "SPEC-payment-topics",
    "title": "Payment Topics",
    "status": "approved",
    "approved_by": "alice",
    "content_hash": _STAMP,
    "body": "# Payment Topics\n\n결제 서비스는 payment.events 토픽을 발행한다. 이는 승인된 스펙이다.",
    "source": "specs/SPEC-payment-topics.md",
}


def _run(coro_fn):
    """Own SelectorEventLoop (asyncpg needs it on Windows). Wire nexus.db to the test pool."""
    from nexus import db

    loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()

    async def _outer():
        import asyncpg
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        db._pool = pool  # all db.execute/fetch_* in the pipeline + search use this pool
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


def test_governed_ingest_persists_and_retrieval_reads_back_the_stamp():
    from nexus import db
    from nexus.a2a.server import _default_ingest_fn
    from nexus.search.evidence_packet import assemble_packet
    from nexus.search.hybrid import _enrich_hits

    async def inner():
        # ── ingest over the production A2A bridge (the skill's default ingest_fn) ──
        outcome = await _default_ingest_fn(_DOC, _TENANT)
        assert outcome.quarantined is False
        assert outcome.approved_hash == _STAMP

        # the document row carries the governance stamp, distinct from the file content_hash
        doc_row = await db.fetch_one(
            "SELECT rid, approved_hash, content_hash FROM documents WHERE tenant = $1", _TENANT,
        )
        assert doc_row is not None
        assert doc_row["approved_hash"] == _STAMP
        assert doc_row["content_hash"] != _STAMP  # nexus's own change-detection hash

        # ── read-back through the retrieval enrichment path ──
        chunk = await db.fetch_one(
            "SELECT rid FROM chunks WHERE doc_rid = $1 AND status = 'active' LIMIT 1",
            doc_row["rid"],
        )
        assert chunk is not None, "expected at least one indexed chunk"

        hits = await _enrich_hits(
            [{"rid": chunk["rid"], "score": 1.0, "bm25_rank": 1, "vector_rank": None}], _TENANT,
        )
        assert len(hits) == 1
        assert hits[0].approved_hash == _STAMP  # SearchHit carries it from documents.approved_hash

        packet = assemble_packet(hits)
        assert packet.provenance[0].approved_hash == _STAMP  # surfaces in provenance → A2A artifact

    _run(inner)


def test_idempotent_republish_is_noop_changed_body_supersedes():
    """SPEC §5.4: same (id, content_hash) ⇒ one resource + idempotent_hit; new body supersedes."""
    from nexus import db
    from nexus.a2a.server import _default_ingest_fn

    async def inner():
        async def doc_count():
            return await db.fetch_val(
                "SELECT count(*) FROM documents WHERE tenant = $1", _TENANT,
            )

        # 1) first publish ⇒ real ingest, not idempotent
        first = await _default_ingest_fn(_DOC, _TENANT)
        assert first.idempotent_hit is False
        assert first.chunks_indexed > 0
        assert await doc_count() == 1

        # 2) re-publish identical (id, content_hash) ⇒ no-op upsert, idempotent, no duplicate
        again = await _default_ingest_fn(_DOC, _TENANT)
        assert again.idempotent_hit is True
        assert again.resource_rid == first.resource_rid
        assert again.chunks_indexed == 0
        assert await doc_count() == 1  # not duplicated

        # 3) changed body (new content_hash) ⇒ supersede: same resource, re-indexed, new stamp
        changed = {**_DOC, "content_hash": "sha256:arbiter-stamp-v2",
                   "body": _DOC["body"] + "\n\n## v2\n토픽 정의가 갱신되었다."}
        superseded = await _default_ingest_fn(changed, _TENANT)
        assert superseded.idempotent_hit is False
        assert superseded.resource_rid == first.resource_rid  # same logical resource
        assert await doc_count() == 1
        row = await db.fetch_one(
            "SELECT approved_hash FROM documents WHERE rid = $1 AND tenant = $2",
            first.resource_rid, _TENANT,
        )
        assert row["approved_hash"] == "sha256:arbiter-stamp-v2"  # superseded to the new stamp

    _run(inner)


def test_record_audit_persists_to_a2a_audit_table():
    """SPEC §5.6/§19: a2a.audit records are durably mirrored to the a2a_audit table, PII-safe."""
    from nexus import db
    from nexus.a2a.audit import query_sha256, record_audit

    async def inner():
        await db.execute("TRUNCATE a2a_audit")
        # a grant and a denial
        await record_audit(skill="ingest_governed_doc", query="", principal="writer",
                           tenant=_TENANT, clearance="INTERNAL", task_state="completed",
                           evidence_count=2, denied=False, latency_ms=5)
        await record_audit(skill="ingest_governed_doc", query="비밀", principal="reader",
                           tenant=_TENANT, clearance="INTERNAL", denied=True,
                           reason="forbidden_no_capability", latency_ms=1)

        rows = await db.fetch_all("SELECT * FROM a2a_audit ORDER BY id")
        assert len(rows) == 2
        assert rows[0]["denied"] is False and rows[0]["task_state"] == "completed"
        assert rows[0]["evidence_count"] == 2
        assert rows[1]["denied"] is True and rows[1]["reason"] == "forbidden_no_capability"
        # PII-safe: only the hash/len of the query are stored, never the raw text
        assert rows[1]["query_sha256"] == query_sha256("비밀")
        assert rows[1]["query_len"] == len("비밀")
        cols = rows[1].keys()
        assert "query" not in cols  # no raw-query column exists at all

    _run(inner)
