"""저장된 `source_kind` 가 실제 출처를 말하는가 — REAL Postgres.

**이 검사가 없어서 결함이 살아남았다.** `test_notion_source.py` 는 컨버터가 만든 dict 에
`source_kind == "wiki"` 가 들어 있는지 단언하고 초록이었다. 그 값은 CSF→임시파일→INSERT 세 홉을
지나며 버려졌고, 파이프라인은 `'git'` 을 문자열 상수로 박고 있었다. 그래서 Notion 페이지 108건이
전부 "git 저장소에서 왔다" 고 적힌 채 앉아 있었다.

생산자의 dict 가 아니라 **DB 에 앉은 행**을 본다.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "srckind"
_PAGE = "ext-notion-742fb34f-38a5-4d5c-bdeb-7d754774a61f.md"


@pytest.fixture
async def clean(db_pool):
    from nexus import db

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    yield
    db._pool = None


async def _ingest(tmp_path, filename: str):
    from nexus.ingest.pipeline import run_ingest

    (tmp_path / filename).write_text(
        "---\ntitle: 로그인 정책\n---\n\n## 본문\n\n비로그인 사용자는 조회만 가능하다.\n",
        encoding="utf-8")
    return await run_ingest(str(tmp_path), force=True, tenant=_TENANT)


async def _kinds(table: str) -> list[str]:
    from nexus import db

    rows = await db.fetch_all(
        f"SELECT DISTINCT source_kind::text AS k FROM {table} WHERE tenant=$1", _TENANT)
    return sorted(r["k"] for r in rows)


async def test_a_notion_page_is_stored_as_wiki(clean, tmp_path):
    """`ext-notion-…` 은 위키에서 왔다. 그렇게 적혀야 한다."""
    await _ingest(tmp_path, _PAGE)
    assert await _kinds("documents") == ["wiki"]


async def test_the_chunks_say_it_too(clean, tmp_path):
    """청크는 인용이 매달리는 자리다. 문서만 고치면 절반만 참이 된다."""
    await _ingest(tmp_path, _PAGE)
    assert await _kinds("chunks") == ["wiki"]


async def test_a_repo_file_is_still_git(clean, tmp_path):
    """**대조군.** 전부 wiki 로 바꿔 놓고 통과하는 검사가 되면 안 된다."""
    await _ingest(tmp_path, "runbook.md")
    assert await _kinds("documents") == ["git"]


async def test_reingesting_repairs_a_row_that_was_written_wrong(clean, tmp_path):
    """갱신 목록에 없으면 **재적재로도 안 고쳐진다** — 108건이 그 상태였다."""
    from nexus import db

    await _ingest(tmp_path, _PAGE)
    await db.execute("UPDATE documents SET source_kind='git' WHERE tenant=$1", _TENANT)
    await db.execute("UPDATE chunks SET source_kind='git' WHERE tenant=$1", _TENANT)

    await _ingest(tmp_path, _PAGE)

    assert await _kinds("documents") == ["wiki"]
    assert await _kinds("chunks") == ["wiki"]
