"""인용 → 원본 그림, DB 를 거쳐 (SPEC-nexus-vision-source-ref §5).

**가져오기는 스텁이고 DB 는 진짜다.** 라이브 코퍼스를 픽스처로 쓰지 않는다: 이 SPEC 의 초안은
살아 있는 Notion 블록·맞는 per-root 토큰·안 만료된 서명 URL 에 단언을 걸었는데, §4 가 그 셋 다
사라질 수 있다고 적어 둔 것들이다. 그러면 시험은 무관한 이유로 빨갛거나 skip 된다.

여기서 진짜여야 하는 것은 **행과 제약**이다. 손잡이의 유일성은 애플리케이션이 아니라 인덱스가
지키고, 참조가 실제로 저장됐는지는 mock 이 아니라 다시 읽은 값이 말한다.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_T = "vsr_test"
_URI = f"{_T}:ext-notion-p1.md"
_BYTES = b"\x89PNG fake image bytes"


@pytest.fixture
async def clean(db_pool):
    from nexus import db

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM vision_extractions WHERE tenant = ANY($1)",
                          [_T, "vsr_empty"])
    yield
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM vision_extractions WHERE tenant = ANY($1)",
                          [_T, "vsr_empty"])
    db._pool = None


class _Reader:
    """판독기 스텁. **호출 횟수를 센다** — 캐시 적중이 재추출로 새면 여기서 잡힌다."""

    model = "test-vision"

    def __init__(self, reply="| 아바타 | 해금 |\n|---|---|\n| A | 1200 |"):
        self.reply, self.calls = reply, 0

    async def vision_extract(self, system, image_b64, media_type, max_tokens):
        self.calls += 1
        return self.reply, "end_turn"


def _stub_fetch(monkeypatch, data=_BYTES):
    from nexus.ingest import vision_store

    async def _fetch(url):
        return data, "image/png"

    monkeypatch.setattr(vision_store, "_fetch_bytes", _fetch)


async def _walk(monkeypatch, reader=None, block_id="blk-1", data=_BYTES):
    """한 장짜리 적재를 돈다 → (본문, 판독기)."""
    from nexus.ingest import vision_store
    from nexus.ingest.sources.notion_convert import image_slot

    _stub_fetch(monkeypatch, data)
    reader = reader or _Reader()
    body, n = await vision_store.apply(
        image_slot(block_id), [{"block_id": block_id, "url": "https://s3/x.png", "caption": ""}],
        tenant=_T, llm_svc=reader, source_uri=_URI)
    return body, reader, n


async def _row(sha: str):
    from nexus import db

    return await db.fetch_one(
        "SELECT text, block_id, source_uri FROM vision_extractions "
        "WHERE tenant = $1 AND image_sha256 = $2", _T, sha)


# ── §5.1 저장 경로가 참조를 남기는가 ─────────────────────────────────────────

async def test_the_reference_is_written_on_the_save_path(clean, monkeypatch):
    """mock 으로 `source_ref()` 가 불렸는지 보지 않는다. **행에서 다시 읽는다.**"""
    from nexus.ingest import vision

    body, reader, n = await _walk(monkeypatch)
    assert n == 1 and reader.calls == 1

    sha = vision.image_sha256(_BYTES)
    row = await _row(sha)
    assert row["block_id"] == "blk-1"
    assert row["source_uri"] == _URI
    assert vision.source_ref(row["source_uri"], row["block_id"], sha).startswith(_URI + "#blk-1#")


# ── §5.3 캐시 적중이 참조를 채우되 판독을 안 건드리는가 ──────────────────────

async def test_a_cache_hit_fills_the_reference_without_touching_the_text(clean, monkeypatch,
                                                                        db_pool):
    """ADR-0010 §5 는 "바뀌지 않은 바이트는 재추출하지 않는다" 이므로 저장 경로가 통째로
    건너뛰어진다 — 재적재만으로는 옛 행의 참조가 영원히 안 채워진다.

    **판독을 대체하는 것과 그 판독이 어디서 왔는지 적는 것은 다르다.** §5 가 지키는 것은 앞의
    것이다. 그래서 `text` 를 앞뒤로 비교한다.
    """
    from nexus.ingest import vision

    sha = vision.image_sha256(_BYTES)
    identity = vision.extractor_identity()
    async with db_pool.acquire() as con:
        await con.execute(
            "INSERT INTO vision_extractions (tenant, image_sha256, extractor_identity, text) "
            "VALUES ($1,$2,$3,$4)", _T, sha, identity, "옛 판독 결과")

    before = await _row(sha)
    assert before["block_id"] == "" and before["text"] == "옛 판독 결과"

    _, reader, _ = await _walk(monkeypatch)
    assert reader.calls == 0, "캐시 적중인데 판독기를 다시 불렀다 — 참조 채우기가 재추출로 샜다"

    after = await _row(sha)
    assert after["text"] == before["text"], "참조를 적으면서 판독을 바꿨다"
    assert after["block_id"] == "blk-1" and after["source_uri"] == _URI


async def test_an_existing_reference_is_not_overwritten(clean, monkeypatch, db_pool):
    """먼저 적힌 참조가 이긴다 — 같은 그림이 두 문서에 있을 때 나중 걷기가 앞 문서의 귀속을
    지우면, 참조는 있는데 **틀린** 상태가 된다. 그건 없는 것보다 나쁘다."""
    from nexus.ingest import vision

    sha = vision.image_sha256(_BYTES)
    async with db_pool.acquire() as con:
        await con.execute(
            "INSERT INTO vision_extractions (tenant, image_sha256, extractor_identity, text, "
            "  block_id, source_uri) VALUES ($1,$2,$3,'옛','first-block','first:uri.md')",
            _T, sha, vision.extractor_identity())

    await _walk(monkeypatch)
    row = await _row(sha)
    assert row["block_id"] == "first-block" and row["source_uri"] == "first:uri.md"


# ── §5.5 끝에서 끝: 청크 → 참조 → 바이트 → 같은 sha ────────────────────────

async def test_a_citation_resolves_all_the_way_back_to_the_same_bytes(clean, monkeypatch):
    """이 SPEC 이 존재하는 이유 그 자체. 한 번도 해석된 적 없는 참조가 지금까지의 상태였다."""
    from nexus.ingest import vision, vision_source
    from nexus.ingest.chunker import chunk_document

    body, _, _ = await _walk(monkeypatch)
    chunks = chunk_document(body, language="ko", trust_vision_markers=True)
    machine = [c for c in chunks if c.provenance_tier == "machine_read"]
    assert machine, "machine_read 청크가 없다 — 배선이 그 앞에서 끊겼다"

    ref = await vision_source.resolve_source(_T, machine[0].chunk_text)
    assert isinstance(ref, vision_source.SourceRef)
    assert ref.block_id == "blk-1" and ref.source_uri == _URI

    # 참조로 원본을 다시 가져온다 (스텁 소스: block_id → 바이트).
    source = {"blk-1": _BYTES}
    fetched = source[ref.block_id]
    assert vision.image_sha256(fetched) == ref.image_sha256


# ── §5.6 §2.2 표의 모든 줄 ──────────────────────────────────────────────────

async def test_a_handle_with_no_row_says_so(clean):
    from nexus.ingest import vision, vision_source

    text = vision.build_block(vision.Extraction("표", vision.extractor_identity(), "f" * 64))
    out = await vision_source.resolve_source(_T, text)
    assert isinstance(out, vision_source.Unresolvable) and out.reason == "no extraction row"


async def test_a_row_without_a_reference_is_distinct_from_no_row(clean, db_pool):
    """둘을 뭉개는 것은 `ObjectNotFound` 를 삭제로 읽은 것과 같은 종류의 실수다."""
    from nexus.ingest import vision, vision_source

    sha = "e" * 64
    identity = vision.extractor_identity()
    async with db_pool.acquire() as con:
        await con.execute(
            "INSERT INTO vision_extractions (tenant, image_sha256, extractor_identity, text) "
            "VALUES ($1,$2,$3,'표')", _T, sha, identity)

    out = await vision_source.resolve_source(
        _T, vision.build_block(vision.Extraction("표", identity, sha)))
    assert isinstance(out, vision_source.Unresolvable)
    assert out.reason == "reference not recorded"


async def test_an_ambiguous_handle_raises_rather_than_picking_one(clean, db_pool):
    """유일 인덱스가 없거나 깨진 상태를 **일부러 만들어** 확인한다.

    인용이 *다른 그림*으로 해석되는 것은 해석 못 하는 것보다 나쁘다. 그래서 이 경우 함수는
    고르지 않고 raise 한다 — 인덱스가 있으니 못 일어난다고 가정하면, 인덱스가 사라진 날
    조용히 틀린 답을 준다.
    """
    from nexus.ingest import vision, vision_source

    identity = vision.extractor_identity()
    prefix = "abcdef0123456789"
    async with db_pool.acquire() as con:
        await con.execute("DROP INDEX IF EXISTS idx_vision_handle")
        try:
            for tail in ("0", "1"):
                await con.execute(
                    "INSERT INTO vision_extractions (tenant, image_sha256, extractor_identity, "
                    "  text, block_id) VALUES ($1,$2,$3,'표','b')",
                    _T, prefix + tail * 48, identity)
            with pytest.raises(vision_source.AmbiguousHandle):
                await vision_source.resolve_source(
                    _T, vision.build_block(vision.Extraction("표", identity, prefix + "0" * 48)))
        finally:
            await con.execute("DELETE FROM vision_extractions WHERE tenant = $1", _T)
            await con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_vision_handle "
                "ON vision_extractions (tenant, left(image_sha256, 16), extractor_identity)")


# ── §5.8 유일성은 코드가 아니라 인덱스가 지킨다 ─────────────────────────────

async def test_the_index_refuses_a_second_row_sharing_the_first_sixteen(clean, db_pool):
    """오늘의 44개 sha 를 세어 본 것으로는 **다음** 이미지에 대해 아무것도 말하지 못한다.
    그래서 측정이 아니라 제약이다."""
    import asyncpg

    from nexus.ingest import vision

    identity = vision.extractor_identity()
    prefix = "0123456789abcdef"
    async with db_pool.acquire() as con:
        await con.execute(
            "INSERT INTO vision_extractions (tenant, image_sha256, extractor_identity, text, "
            "  block_id) VALUES ($1,$2,$3,'표','b1')", _T, prefix + "a" * 48, identity)
        with pytest.raises(asyncpg.UniqueViolationError):
            await con.execute(
                "INSERT INTO vision_extractions (tenant, image_sha256, extractor_identity, text, "
                "  block_id) VALUES ($1,$2,$3,'표','b2')", _T, prefix + "b" * 48, identity)


# ── §5.9 표면: 해석 불가가 몇 건인가 ────────────────────────────────────────

async def test_unresolvable_is_counted_over_extraction_rows(clean, db_pool):
    """청크 쪽 술어로 억제하면 **청크가 없는 추출**(빈 판독)의 미해석 상태가 0 으로 보고된다.
    그 4건이 이 SPEC 이 조정한 숫자의 전부였다."""
    from nexus.ingest import vision
    from nexus.ingest.vision_source import unresolvable_count

    identity = vision.extractor_identity()
    async with db_pool.acquire() as con:
        await con.execute(
            "INSERT INTO vision_extractions (tenant, image_sha256, extractor_identity, text, "
            "  block_id) VALUES ($1,$2,$3,'표','b1')", _T, "1" * 64, identity)
        await con.execute(                                   # 참조 없음
            "INSERT INTO vision_extractions (tenant, image_sha256, extractor_identity, text) "
            "VALUES ($1,$2,$3,'표')", _T, "2" * 64, identity)
        await con.execute(                                   # 빈 판독 + 참조 없음
            "INSERT INTO vision_extractions (tenant, image_sha256, extractor_identity, text) "
            "VALUES ($1,$2,$3,'')", _T, "3" * 64, identity)

    got = await unresolvable_count(_T)
    assert got["rows"] == 3 and got["current_rows"] == 3
    assert got["unresolvable"] == 2 and got["empty_text"] == 1
    assert got["retired_unresolvable"] == 0


async def test_a_retired_readers_rows_are_counted_apart(clean, db_pool):
    """은퇴한 신원의 행은 **어떤 걷기도 다시 닿지 않는다** — ADR-0010 §5 가 저장을 신원으로
    키잉하기 때문이다. 합쳐 세면 영원히 안 꺼지는 ⚠ 가 되고, 게다가 부정확하다: 활성 인용은
    전부 현 신원의 마커를 이고 있으므로 그 행을 가리키는 인용이 없다.

    라이브 적재가 이걸 드러냈다 — 현 판독기 44행은 전부 채워졌는데 카운터는 44건 미해석이라고
    찍었고, 그 44건은 전부 은퇴한 판독기의 것이었다.
    """
    from nexus.ingest import vision
    from nexus.ingest.vision_source import unresolvable_count

    async with db_pool.acquire() as con:
        await con.execute(                                   # 현 판독기 — 참조 있음
            "INSERT INTO vision_extractions (tenant, image_sha256, extractor_identity, text, "
            "  block_id) VALUES ($1,$2,$3,'표','b1')", _T, "4" * 64, vision.extractor_identity())
        await con.execute(                                   # 은퇴한 판독기 — 참조 없음
            "INSERT INTO vision_extractions (tenant, image_sha256, extractor_identity, text) "
            "VALUES ($1,$2,'retired-reader/000000','표')", _T, "5" * 64)

    got = await unresolvable_count(_T)
    assert got["rows"] == 2 and got["current_rows"] == 1
    assert got["unresolvable"] == 0, "현 판독기는 전부 해석 가능한데 ⚠ 가 켜졌다"
    assert got["retired_unresolvable"] == 1


async def test_a_tenant_with_no_extractions_has_nothing_to_say(clean):
    """새 상시 경보를 만들지 않는다 — rows 가 0 이면 status 는 한 줄도 안 찍는다."""
    from nexus.ingest.vision_source import unresolvable_count

    assert (await unresolvable_count("vsr_empty"))["rows"] == 0


# ── §5.10 마이그레이션 ──────────────────────────────────────────────────────

async def test_migration_016_is_idempotent_and_leaves_old_rows_empty(clean, db_pool):
    from pathlib import Path

    from nexus.ingest import vision

    sql = (Path(__file__).resolve().parents[1] / "migrations"
           / "016_vision_source_ref.sql").read_text(encoding="utf-8")
    async with db_pool.acquire() as con:
        await con.execute(
            "INSERT INTO vision_extractions (tenant, image_sha256, extractor_identity, text) "
            "VALUES ($1,$2,$3,'옛 행')", _T, "9" * 64, vision.extractor_identity())
        await con.execute(sql)
        await con.execute(sql)                              # 두 번째도 통과해야 한다
        row = await con.fetchrow(
            "SELECT text, block_id, source_uri FROM vision_extractions "
            "WHERE tenant = $1 AND image_sha256 = $2", _T, "9" * 64)
    assert row["text"] == "옛 행"
    assert row["block_id"] == "" and row["source_uri"] == ""
