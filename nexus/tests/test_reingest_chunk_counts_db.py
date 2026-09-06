"""재적재가 **청크 수를 바꿨는가** 를 기록하는가 — postgres. NEXUS_TEST_DB_URL 이 필요하다.

⛔ **왜 이 기록이 있나 (`OPEN.md` A90).** 2026-09-06 측정(`scripts/rechunk_churn.py`): 청크 rid
이탈의 트리거는 편집 위치가 아니라 **청크 수 변화**다. 작은 편집은 rid 를 하나도 안 바꾸고,
청크를 하나 늘리는 편집은 그 뒤를 거의 전부 바꾼다 — 그리고 그 이탈은 사실상 전량이 낭비다.

그래서 처방을 고르기 전 남은 미지수가 *"그런 편집이 얼마나 자주 오는가"* 하나이고,
`doc_reingest_events` 는 해시 전후만 적고 청크 수를 안 적어서 그 질문에 답할 수 없었다.

⚠ **NULL 은 "안 바뀜" 이 아니라 "기록 안 됨" 이다.** 041 이전의 행은 영원히 NULL 이고,
읽는 쪽은 세 상태를 갈라야 한다 — 안 기록됨 · 같음 · 다름. 그 구분을 지우면 옛 재적재가
전부 *"청크 수가 안 바뀐 재적재"* 로 세어져 빈도가 희석된다.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "acme"
_URI = "acme:specs/chunk-counts.md"

#: 청크 하나에 들어가는 짧은 본문과, 목표 토큰을 넘겨 여러 청크로 갈리는 긴 본문.
_SHORT = "# 제목\n\n짧은 본문 한 문단이다."
_LONG = "# 제목\n\n" + "\n\n".join(["긴 본문 문단이다. " * 60] * 12)


def _run(coro_fn):
    """자기 SelectorEventLoop (`test_reingest_event_db.py` 와 같은 관례)."""
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


def _collected(content: str, content_hash: str):
    from nexus.ingest.collector import CollectedFile
    return CollectedFile(
        path="/tmp/chunk-counts.md",  # type: ignore[arg-type]
        relative_path="specs/chunk-counts.md",
        content=content,
        content_hash=content_hash,
        frontmatter={},
        canonical_uri=_URI,
    )


def _classification():
    from nexus.ingest.classifier import ClassificationResult
    return ClassificationResult()


async def _ingest(content: str, content_hash: str) -> int:
    """`_save_document` → 청킹 → `_save_chunks` 를 프로덕션 순서대로 태운다."""
    from nexus.ingest.chunker import chunk_document
    from nexus.ingest.pipeline import _save_chunks, _save_document

    col, cls = _collected(content, content_hash), _classification()
    rid = await _save_document(col, cls, _TENANT)
    chunks = chunk_document(content, language="ko", config={})
    return await _save_chunks(chunks, rid, col, cls, _TENANT)


async def _counts(content_hash: str):
    from nexus import db
    return await db.fetch_one(
        "SELECT chunks_before, chunks_after FROM doc_reingest_events "
        "WHERE new_content_hash = $1", content_hash)


def test_a_first_ingest_records_nothing_because_it_is_not_a_reingest():
    """⛔ 첫 적재에 수를 적으면 **바뀐 적 없는 문서가 표본에 들어와** 빈도를 희석한다."""
    from nexus import db

    async def inner():
        await _ingest(_SHORT, "hash-v1")
        assert await db.fetch_val("SELECT count(*) FROM doc_reingest_events") == 0

    _run(inner)


def test_a_reingest_that_keeps_the_chunk_count_records_both_and_they_are_equal():
    """수가 같다는 것도 **기록돼야 한다** — 안 적으면 분모가 사라지고 빈도를 못 낸다."""
    async def inner():
        await _ingest(_SHORT, "hash-v1")
        await _ingest(_SHORT + "\n\n한 문장 더.", "hash-v2")
        row = await _counts("hash-v2")
        assert row is not None, "재적재인데 이벤트가 없다"
        assert row["chunks_before"] == row["chunks_after"], dict(row)
        assert row["chunks_before"] >= 1

    _run(inner)


def test_a_reingest_that_changes_the_chunk_count_shows_it():
    """⭐ 이것이 A90 이 세려는 사건이다 — 이 행만이 rid 이탈을 뜻한다."""
    async def inner():
        await _ingest(_SHORT, "hash-v1")
        await _ingest(_LONG, "hash-v2")
        row = await _counts("hash-v2")
        assert row is not None
        assert row["chunks_after"] > row["chunks_before"], dict(row)

    _run(inner)


def test_the_two_columns_cannot_be_filled_one_at_a_time():
    """한쪽만 있는 행은 **어느 쪽으로도 읽을 수 없다** — 제약이 그 상태를 막는다."""
    import asyncpg

    from nexus import db

    async def inner():
        await db.execute(
            "INSERT INTO doc_reingest_events (rid, tenant, old_content_hash, new_content_hash) "
            "VALUES ('doc_x', $1, 'a', 'b')", _TENANT)
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await db.execute(
                "UPDATE doc_reingest_events SET chunks_before = 3 WHERE rid = 'doc_x'")

    _run(inner)


def test_an_older_event_keeps_null_rather_than_being_backfilled_with_zero():
    """⚠ **NULL 은 '안 바뀜' 이 아니다.** 0 으로 채우면 없는 사실을 만들어 낸다."""
    from nexus import db

    async def inner():
        await db.execute(
            "INSERT INTO doc_reingest_events (rid, tenant, old_content_hash, new_content_hash) "
            "VALUES ('doc_old', $1, 'a', 'b')", _TENANT)
        row = await db.fetch_one(
            "SELECT chunks_before, chunks_after FROM doc_reingest_events WHERE rid = 'doc_old'")
        assert row["chunks_before"] is None and row["chunks_after"] is None

    _run(inner)
