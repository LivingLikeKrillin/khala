"""ref(rid | 경로 | URI) → rid 해석 — REAL Postgres. SPEC-nexus-document-lifecycle §4.6.

`resolve_active_doc` 는 경로 조회를 **active 로만** 좁힌다. supersede 에는 맞다(대상이 active 여야
하므로). 하지만 hide 를 되돌리거나 supersession 을 취소할 때 대상은 정의상 active 가 아니다 —
그 경로로는 문서를 영영 이름으로 부를 수 없고, 사용자는 rid 를 손으로 옮겨 적어야 한다.

그래서 상태를 가리지 않는 해석기가 따로 필요하다. 모호성은 여전히 거부한다.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_T = "acme"


@pytest.fixture
async def seeded(db_pool):
    from nexus import db
    from nexus.documents.schema import ensure_lifecycle_schema

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await ensure_lifecycle_schema(con)
        await con.execute("TRUNCATE documents, chunks, doc_supersession_events CASCADE")
        for rid, uri, status in [
            ("doc_active", f"{_T}:specs/live.md", "active"),
            ("doc_hidden", f"{_T}:specs/hidden.md", "soft_deleted"),
            ("doc_gone", f"{_T}:specs/gone.md", "superseded"),
        ]:
            await con.execute(
                "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, status) "
                "VALUES ($1,$2,$3,'h','h',$4::resource_status)", rid, _T, uri, status)
    yield
    db._pool = None


async def test_a_hidden_document_can_be_named_by_its_path(seeded):
    """숨긴 문서는 active 가 아니다. 되돌리려면 이름으로 부를 수 있어야 한다."""
    from nexus.documents.resolve import resolve_doc

    assert await resolve_doc("specs/hidden.md", _T) == "doc_hidden"
    assert await resolve_doc("specs/gone.md", _T) == "doc_gone"
    assert await resolve_doc("specs/live.md", _T) == "doc_active"


async def test_rid_passes_through_untouched(seeded):
    from nexus.documents.resolve import resolve_doc

    assert await resolve_doc("doc_hidden", _T) == "doc_hidden"


async def test_unknown_ref_is_refused_by_name(seeded):
    from nexus.documents.resolve import resolve_doc

    with pytest.raises(ValueError, match="없음"):
        await resolve_doc("specs/nope.md", _T)


async def test_an_ambiguous_basename_is_refused_and_lists_the_candidates(seeded):
    """같은 파일명이 두 디렉터리에 있으면 사람에게 되묻는다 — 아무거나 고르지 않는다."""
    from nexus import db
    from nexus.documents.resolve import resolve_doc

    await db.execute(
        "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, status) "
        "VALUES ('doc_dup', $1, $2, 'h','h','soft_deleted')", _T, f"{_T}:archive/hidden.md")

    with pytest.raises(ValueError) as e:
        await resolve_doc("hidden.md", _T)
    assert "specs/hidden.md" in str(e.value) and "archive/hidden.md" in str(e.value)


async def test_resolve_active_doc_still_refuses_non_active_paths(seeded):
    """기존 계약 불변 — supersede 는 여전히 active 만 경로로 받는다."""
    from nexus.supersede import resolve_active_doc

    with pytest.raises(ValueError):
        await resolve_active_doc("specs/hidden.md", _T)
    assert await resolve_active_doc("specs/live.md", _T) == "doc_active"
