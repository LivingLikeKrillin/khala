"""`written_at` 감지기의 DB 절반 — postgres. `NEXUS_TEST_DB_URL` 이 필요하다.

⛔ **왜 자기 모듈인가.** 이 파일은 `TRUNCATE` 를 한다. 다른 DB 검사와 한 모듈에 섞으면 그쪽
픽스처의 행을 지운다 — 2026-09-05 에 실제로 그렇게 30개 모듈을 죽였다.

⭐ **여기서 지키는 성질은 하나다**: *벡터가 행 갱신 뒤에 쓰였으면 낡을 수 없다.* 그 반대편
(`후보`)은 **판정이 아니라 상한**이고, 그 사실을 검사가 직접 말한다.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "freshness_probe"
_COL = "embedding_1024"
_DIM = 1024


def _run(coro_fn):
    """자기 SelectorEventLoop (`test_reingest_chunk_counts_db.py` 와 같은 관례)."""
    from nexus import db

    loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()

    async def _outer():
        import asyncpg
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        db._pool = pool
        try:
            async with pool.acquire() as con:
                await con.execute("TRUNCATE documents, chunks, chunk_vector_provenance CASCADE")
            return await coro_fn()
        finally:
            await pool.close()
            db._pool = None

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()


async def _seed(rid: str, *, updated_at: datetime, stamped_at: datetime | None) -> None:
    """청크 하나와 (선택적으로) 그 벡터의 출처 도장."""
    from nexus import db

    await db.execute(
        "INSERT INTO documents (rid, tenant, source_uri, hash, status, title) "
        "VALUES ($1, $2, $3, 'h', 'active', 't') ON CONFLICT (rid) DO NOTHING",
        "doc_fresh", _TENANT, "t:doc.md")
    await db.execute(
        f"INSERT INTO chunks (rid, tenant, doc_rid, source_uri, chunk_text, section_path, "
        f"                    chunk_index, status, is_quarantined, updated_at, hash, {_COL}) "
        f"VALUES ($1, $2, 'doc_fresh', 't:doc.md', 'body', '', 0, 'active', false, $3, 'h', $4::vector)",
        rid, _TENANT, updated_at, "[" + ",".join(["0.1"] * _DIM) + "]")
    if stamped_at is not None:
        await db.execute(
            "INSERT INTO chunk_vector_provenance (chunk_rid, column_name, model, written_at) "
            "VALUES ($1, $2, 'KURE-v1', $3)", rid, _COL, stamped_at)


def test_a_vector_written_after_the_row_cannot_be_stale():
    """⭐ 이것이 감지기의 실제 산출물이다 — 재계산에서 **빼도 되는** 집합."""
    from nexus.index.provenance import fetch_freshness

    async def inner():
        now = datetime.now(timezone.utc)
        await _seed("c_fresh", updated_at=now - timedelta(hours=1), stamped_at=now)
        c = await fetch_freshness(_COL, tenant=_TENANT)
        assert c == {"filled": 1, "provably_fresh": 1, "candidates": 0, "unstamped": 0}, c

    _run(inner)


def test_a_vector_older_than_its_row_is_a_candidate_not_a_verdict():
    """⛔ 후보는 **상한**이다 — 내용이 안 바뀐 재적재도 `updated_at` 을 민다."""
    from nexus.index.provenance import fetch_freshness

    async def inner():
        now = datetime.now(timezone.utc)
        await _seed("c_cand", updated_at=now, stamped_at=now - timedelta(hours=1))
        c = await fetch_freshness(_COL, tenant=_TENANT)
        assert c["candidates"] == 1 and c["provably_fresh"] == 0, c

    _run(inner)


def test_a_vector_with_no_stamp_is_neither_fresh_nor_stale():
    """⚠ 시간을 모르는 것을 신선 쪽에 넣으면 **모른다와 괜찮다가 같아진다.**"""
    from nexus.index.provenance import fetch_freshness

    async def inner():
        now = datetime.now(timezone.utc)
        await _seed("c_unstamped", updated_at=now, stamped_at=None)
        c = await fetch_freshness(_COL, tenant=_TENANT)
        assert c["unstamped"] == 1
        assert c["provably_fresh"] == 0 and c["candidates"] == 0, c

    _run(inner)


def test_a_row_whose_vector_is_null_is_not_this_detectors_business():
    """⛔ NULL 인 행은 **재임베딩 큐가 이미 본다.** 여기서 또 세면 두 수가 같은 것을 세고,
    이 감지기가 답하려는 질문(*큐가 못 보는 것*)이 흐려진다."""
    from nexus import db
    from nexus.index.provenance import fetch_freshness

    async def inner():
        await db.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, status, title) "
            "VALUES ('doc_fresh', $1, 't:doc.md', 'h', 'active', 't')", _TENANT)
        await db.execute(
            "INSERT INTO chunks (rid, tenant, doc_rid, source_uri, chunk_text, section_path, "
            "chunk_index, status, is_quarantined, hash) "
            "VALUES ('c_null', $1, 'doc_fresh', 't:doc.md', 'body', '', 0, 'active', false, 'h')",
            _TENANT)
        c = await fetch_freshness(_COL, tenant=_TENANT)
        assert c["filled"] == 0, c

    _run(inner)


def test_an_unknown_column_is_refused_rather_than_defaulted():
    """⛔ 오타를 기본값으로 삼키면 **어느 세대를 보고 있는지 아무도 모른다** —
    `resolve_column` 이 이 리포에서 이미 그 이유로 존재한다."""
    from nexus.index.provenance import fetch_freshness
    from nexus.index.vector_index import UnknownVectorColumn

    async def inner():
        with pytest.raises(UnknownVectorColumn):
            await fetch_freshness("embedding_9999", tenant=_TENANT)

    _run(inner)
