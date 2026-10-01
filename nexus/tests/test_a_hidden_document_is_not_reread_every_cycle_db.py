"""숨긴 문서는 **내용이 같으면** 주기마다 다시 읽히지 않는다.

⛔ **왜 생겼나 (실측 2026-10-01).** 정시 재적재가 숨긴 설계 명세(`soft_deleted`) 하나를 **매시**
「바뀜」으로 잡아 156 조각을 다시 만들었다 — 파일은 그 사이 한 번도 안 바뀌었다. 수집기의 「안 바뀜」
비교가 `status = 'active'` 행만 봐서, 숨긴 문서는 비교할 행이 없어 늘 바뀐 것이 됐다. 그런데 재적재는
숨긴 문서를 되살리지 않는다(문서 갱신이 `status` 를 건드리지 않는다) — 그러니 다시 읽어도 바뀌는 것이
없고, 남는 것은 매시의 헛일과 「바뀜 1」이라는 거짓 신호와 움직이는 `updated_at` 뿐이었다. 소비자가
곁에서 보고 알려 왔다.

⚠ **반대쪽도 지킨다.** 숨긴 뒤에 파일이 **실제로** 바뀌었으면 한 번은 읽어야 한다 — 내용을 최신으로
두어야 나중에 되살릴 때 옛 본문이 안 나온다. 그다음 주기부터는 다시 「안 바뀜」이다.
"""

from __future__ import annotations

import pytest

from nexus.ingest.collector import collect_files

_TENANT = "hidden_reread_probe"

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def wired(db_pool):
    """수집기가 쓰는 전역 풀을 시험 DB 로 물린다 — 안 물리면 조회가 조용히 실패해 전부 「바뀜」이다
    (`test_label_edit_is_a_change_db.py` 머리말)."""
    from nexus import db

    before = db._pool
    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM documents WHERE tenant = $1", _TENANT)
    try:
        yield db_pool
    finally:
        async with db_pool.acquire() as con:
            await con.execute("DELETE FROM documents WHERE tenant = $1", _TENANT)
        db._pool = before


def _write(d, name: str, body: str = "본문이다.\n") -> None:
    (d / name).write_text(f"# 제목\n\n{body}", encoding="utf-8")


async def _hash_of(tmp_path) -> str:
    got = await collect_files(str(tmp_path), "**/*.md", force=True, tenant=_TENANT)
    return got.files[0].content_hash


async def _seed(pool, name: str, content_hash: str, status: str) -> None:
    uri = f"{_TENANT}:{name}"
    async with pool.acquire() as con:
        await con.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title, status) "
            "VALUES ($1, $2, $3, 'h', $4, 't', $5::resource_status)",
            f"doc_{abs(hash(uri))}", _TENANT, uri, content_hash, status)


async def _collect(tmp_path):
    return await collect_files(str(tmp_path), "**/*.md", tenant=_TENANT)


@pytest.mark.parametrize("status", ["soft_deleted", "superseded"])
async def test_a_hidden_document_with_the_same_content_is_unchanged(tmp_path, wired, status):
    """⛔ 이 검사가 이 단위의 이유다 — 라이브에서 매시 156 조각을 다시 만들던 모양."""
    _write(tmp_path, "spec.md")
    await _seed(wired, "spec.md", await _hash_of(tmp_path), status)

    got = await _collect(tmp_path)
    assert (got.found, got.unchanged, len(got.files)) == (1, 1, 0), "숨긴 문서가 「바뀜」으로 잡혔다"


async def test_a_hidden_document_whose_file_changed_is_read_once(tmp_path, wired):
    """숨긴 뒤 파일이 실제로 바뀌었으면 읽는다 — 본문은 최신으로 둔다(되살아나지는 않는다)."""
    _write(tmp_path, "spec.md", "옛 본문이다.\n")
    await _seed(wired, "spec.md", await _hash_of(tmp_path), "soft_deleted")
    _write(tmp_path, "spec.md", "새 본문이다.\n")

    got = await _collect(tmp_path)
    assert (got.unchanged, len(got.files)) == (0, 1)


async def test_an_active_document_is_still_compared_as_before(tmp_path, wired):
    """대조 — 활성 문서의 「안 바뀜」은 그대로다."""
    _write(tmp_path, "doc.md")
    await _seed(wired, "doc.md", await _hash_of(tmp_path), "active")

    got = await _collect(tmp_path)
    assert (got.unchanged, len(got.files)) == (1, 0)
