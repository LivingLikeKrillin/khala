"""DB-backed test: 재적재가 청크의 **세대 키**(chunks.hash)를 따라 옮긴다.

`revive()`·`unsupersede()` 는 "현재 세대만 되살린다" 를 `chunks.hash = documents.content_hash`
로 표현한다 (lifecycle.py). 그 등식이 성립한다는 근거로 docstring 이 든 것은
*"pipeline.py 가 같은 값으로 둘 다 쓴다"* 인데, **쓰지 않았다** — `_save_document` 의
ON CONFLICT 는 `content_hash` 를 갱신하고 `_save_chunks` 의 ON CONFLICT 는 `hash` 를
갱신하지 않았다. 그래서 문서를 한 번이라도 고쳐 재적재하면 두 값이 갈라지고, 그 뒤의
soft_delete → revive 는 **청크를 0건 되살린 채 문서만 active 로 세운다.**

그 상태의 이름은 유령 문서다: 목록·개수·커버리지에는 건강하게 보이는데 어떤 다리도
읽지 못한다. 라이브 `default` 에서 실제로 하나 나왔다(`SLACK_BOT.md`, 청크 12개 전부
soft_deleted, 해시 불일치) — 팀이 묻는 코퍼스다.

Own SelectorEventLoop + asyncpg pool injected into nexus.db (mirrors
test_superseded_reingest_chunks_db.py — pytest-asyncio async fixtures are broken here).
"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys

import pytest

DB_URL = os.getenv("NEXUS_TEST_DB_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요 (docker-compose.test.yml)")

_TENANT = "acme"


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
            return await coro_fn()
        finally:
            await pool.close()
            db._pool = None

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()


def _run_no_truncate(coro_fn):
    """`_run` 과 같되 코퍼스를 비우지 않는다 — 자기 테넌트만 치우는 검사용."""
    from nexus import db

    loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()

    async def _outer():
        import asyncpg
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=3)
        db._pool = pool
        try:
            return await coro_fn()
        finally:
            await pool.close()
            db._pool = None

    try:
        return loop.run_until_complete(_outer())
    finally:
        loop.close()


def _make_inputs(uri: str, content_hash: str, *, quarantined: bool = False):
    from nexus.ingest.classifier import ClassificationResult
    from nexus.ingest.collector import CollectedFile

    collected = CollectedFile(
        path=pathlib.Path(uri),
        relative_path=uri,
        content="body",
        content_hash=content_hash,
        frontmatter={},
        canonical_uri=uri,
    )
    classification = ClassificationResult(
        classification="INTERNAL", language="ko",
        is_quarantined=quarantined,
        pii_types=["jwt"] if quarantined else [],
    )
    return collected, classification


def test_reingest_moves_the_chunk_generation_key_forward():
    """편집된 문서를 재적재하면 청크의 hash 가 새 content_hash 와 같아진다."""
    from nexus import db
    from nexus.ingest.chunker import ChunkData
    from nexus.ingest.pipeline import _save_chunks, _save_document

    async def inner():
        uri = "docs/guide.md"
        col1, cls1 = _make_inputs(uri, "hash-v1")
        rid = await _save_document(col1, cls1, _TENANT)
        await _save_chunks(
            [ChunkData(chunk_text="v1 text", section_path="root", chunk_index=0, token_count=2)],
            rid, col1, cls1, _TENANT,
        )

        # 편집 후 재적재: 같은 rid, 다른 본문 → 새 content_hash
        col2, cls2 = _make_inputs(uri, "hash-v2")
        await _save_document(col2, cls2, _TENANT)
        await _save_chunks(
            [ChunkData(chunk_text="v2 text", section_path="root", chunk_index=0, token_count=2)],
            rid, col2, cls2, _TENANT,
        )

        doc_hash = await db.fetch_val("SELECT content_hash FROM documents WHERE rid=$1", rid)
        chunk_hashes = [r["hash"] for r in await db.fetch_all(
            "SELECT hash FROM chunks WHERE doc_rid=$1", rid)]
        assert doc_hash == "hash-v2"
        assert chunk_hashes == ["hash-v2"], (
            f"청크의 세대 키가 문서를 따라오지 않았다: doc={doc_hash} chunks={chunk_hashes}. "
            "revive()·unsupersede() 가 이 등식으로 '현재 세대' 를 고른다."
        )

    _run(inner)


def test_revive_after_an_edit_brings_the_chunks_back():
    """세대 키가 갈리면 revive 가 문서만 살리고 청크는 죽은 채 둔다 — 유령 문서."""
    from nexus import db
    from nexus.ingest.chunker import ChunkData
    from nexus.ingest.pipeline import _save_chunks, _save_document
    from nexus.lifecycle import revive, soft_delete

    async def inner():
        uri = "docs/guide.md"
        col1, cls1 = _make_inputs(uri, "hash-v1")
        rid = await _save_document(col1, cls1, _TENANT)
        await _save_chunks(
            [ChunkData(chunk_text="v1 text", section_path="root", chunk_index=0, token_count=2)],
            rid, col1, cls1, _TENANT,
        )
        col2, cls2 = _make_inputs(uri, "hash-v2")
        await _save_document(col2, cls2, _TENANT)
        await _save_chunks(
            [ChunkData(chunk_text="v2 text", section_path="root", chunk_index=0, token_count=2)],
            rid, col2, cls2, _TENANT,
        )

        assert await soft_delete(rid, _TENANT) == "soft_deleted"
        assert await revive(rid, _TENANT) == "revived"

        alive = await db.fetch_val(
            "SELECT count(*) FROM chunks WHERE doc_rid=$1 AND status='active'", rid)
        assert alive == 1, (
            "되살린 문서가 읽을 수 있는 청크를 0건 갖고 있다 — 목록에는 보이는데 "
            "어떤 다리도 못 읽는 유령 문서다."
        )

    _run(inner)


def test_status_reports_a_document_no_bridge_can_read():
    """커버리지는 청크를 센다 — 청크가 0건인 문서는 그 모집단에 아예 없다.

    그래서 유령은 커버리지 100% 로 보인다. 문서 단위로 따로 세어야 보인다.
    """
    from nexus import db
    from nexus.index.embed_health import fetch_unreachable_documents
    from nexus.ingest.chunker import ChunkData
    from nexus.ingest.pipeline import _save_chunks, _save_document

    async def inner():
        # 1) 정상 문서 — 활성 청크 1개
        col_ok, cls_ok = _make_inputs("docs/ok.md", "hash-ok")
        rid_ok = await _save_document(col_ok, cls_ok, _TENANT)
        await _save_chunks(
            [ChunkData(chunk_text="ok", section_path="root", chunk_index=0, token_count=1)],
            rid_ok, col_ok, cls_ok, _TENANT,
        )

        # 2) 격리 문서 — 청크가 없는 것이 **의도**다. 이미 따로 세어 보고된다.
        col_q, cls_q = _make_inputs("docs/secret.md", "hash-q", quarantined=True)
        await _save_document(col_q, cls_q, _TENANT)

        # 3) 유령 — active 인데 살아 있는 청크가 0건
        col_g, cls_g = _make_inputs("docs/ghost.md", "hash-g")
        rid_g = await _save_document(col_g, cls_g, _TENANT)
        await _save_chunks(
            [ChunkData(chunk_text="gone", section_path="root", chunk_index=0, token_count=1)],
            rid_g, col_g, cls_g, _TENANT,
        )
        await db.execute("UPDATE chunks SET status='soft_deleted' WHERE doc_rid=$1", rid_g)

        rows = await fetch_unreachable_documents()
        by_tenant = {r["tenant"]: r for r in rows}
        assert _TENANT in by_tenant, "유령 문서가 있는데 아무 행도 안 나왔다"
        assert by_tenant[_TENANT]["unreachable"] == 1, (
            f"유령은 1건이어야 한다(격리는 의도라 제외): {by_tenant[_TENANT]}")
        assert "docs/ghost.md" in by_tenant[_TENANT]["examples"]

    _run(inner)


def test_nexus_status_names_the_unreachable_document(monkeypatch):
    """감지기가 아니라 **전달**을 검사한다 — 이 리포는 그 실패를 이미 한 번 기록했다.

    `nexus status` 를 실제로 실행해 유령의 **이름**이 사람 눈앞에 오는지 본다. 함수만
    검사하면 `cli.py` 에서 호출부가 사라져도 초록이다.
    """
    from typer.testing import CliRunner

    from nexus import db
    from nexus.cli import app
    from nexus.ingest.chunker import ChunkData
    from nexus.ingest.pipeline import _save_chunks, _save_document

    # 전용 테넌트로 심는다 — 예시는 테넌트별 배열이라, 다른 테스트의 유령이 섞여도
    # 이 테넌트의 줄은 결정적이다.
    tenant = "ghost_surface"

    async def seed():
        col, cls = _make_inputs("docs/ghost-surface.md", "hash-g")
        rid = await _save_document(col, cls, tenant)
        await _save_chunks(
            [ChunkData(chunk_text="gone", section_path="root", chunk_index=0, token_count=1)],
            rid, col, cls, tenant,
        )
        await db.execute("UPDATE chunks SET status='soft_deleted' WHERE doc_rid=$1", rid)

    async def purge():
        await db.execute("DELETE FROM chunks WHERE tenant=$1", tenant)
        await db.execute("DELETE FROM documents WHERE tenant=$1", tenant)

    _run_no_truncate(purge)
    _run_no_truncate(seed)
    monkeypatch.setenv("DATABASE_URL", DB_URL)
    db._pool = None
    try:
        result = CliRunner().invoke(app, ["status"])
        out = result.stdout + str(result.stderr or "")
        assert f"읽을 수 없는 문서 {tenant}" in out, f"유령이 상태 출력에 한 줄도 안 나왔다\n{out}"
        assert "docs/ghost-surface.md" in out, f"개수만 찍고 어느 문서인지는 안 찍었다\n{out}"
    finally:
        db._pool = None
        _run_no_truncate(purge)


def test_a_healthy_corpus_reports_nothing():
    """대조군: 유령이 없으면 행도 없다 — 늘 울리는 경보는 경보가 아니다."""
    from nexus.index.embed_health import fetch_unreachable_documents
    from nexus.ingest.chunker import ChunkData
    from nexus.ingest.pipeline import _save_chunks, _save_document

    async def inner():
        col, cls = _make_inputs("docs/ok.md", "hash-ok")
        rid = await _save_document(col, cls, _TENANT)
        await _save_chunks(
            [ChunkData(chunk_text="ok", section_path="root", chunk_index=0, token_count=1)],
            rid, col, cls, _TENANT,
        )
        assert await fetch_unreachable_documents() == []

    _run(inner)
