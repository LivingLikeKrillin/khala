"""재수집은 제목을 갱신한다 — REAL Postgres.

`INSERT ... ON CONFLICT (rid) DO UPDATE` 가 hash·classification·doc_type·language 는 갱신하면서
**title 은 빼놓았다.** 그래서 문서 제목은 최초 삽입 이후 영원히 고정된다.

Notion 페이지 이름을 제대로 읽도록 고치고 `--force` 로 재동기화해도 제목이 그대로였던 이유다.
파이프라인의 모든 계단이 옳은데 마지막 SQL 한 줄이 없었다.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "reingest"


@pytest.fixture
async def clean(db_pool):
    from nexus import db

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    yield
    db._pool = None


async def _ingest(tmp_path, body: str, force: bool):
    from nexus.ingest.pipeline import run_ingest

    (tmp_path / "note.md").write_text(body, encoding="utf-8")
    return await run_ingest(str(tmp_path), force=force, tenant=_TENANT)


async def test_reingesting_with_a_new_frontmatter_title_updates_the_row(clean, tmp_path):
    from nexus import db

    await _ingest(tmp_path, "---\ntitle: Access 방식\n---\n\n## 본문\n\n내용", force=True)
    first = await db.fetch_val("SELECT title FROM documents WHERE tenant=$1", _TENANT)
    assert first == "Access 방식"

    # 본문은 그대로, 제목만 바뀐다 — content_hash 는 같다.
    await _ingest(tmp_path, "---\ntitle: Index\n---\n\n## 본문\n\n내용", force=True)
    second = await db.fetch_val("SELECT title FROM documents WHERE tenant=$1", _TENANT)

    assert second == "Index", "재수집이 제목을 갱신하지 않는다 — 최초 삽입값에 영원히 갇힌다"


async def test_the_row_is_the_same_document_not_a_duplicate(clean, tmp_path):
    from nexus import db

    await _ingest(tmp_path, "---\ntitle: A\n---\n\n본문", force=True)
    await _ingest(tmp_path, "---\ntitle: B\n---\n\n본문", force=True)

    n = await db.fetch_val("SELECT count(*) FROM documents WHERE tenant=$1", _TENANT)
    assert n == 1
