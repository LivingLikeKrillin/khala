"""문서 **자신의** 수정 시각을 저장한다 — 그리고 그것이 적재 시각과 다른 것임을 지킨다.

⛔ **왜 생겼나 (실측 2026-09-02).** *"성능이 별로인 이유가 문서가 낡아서인가"* 를 물어
`documents.updated_at` 으로 쟀더니 **126건 전부 "3개월 이내"** 가 나왔다. 하마터면
*"문서는 안 낡았다"* 고 보고할 뻔했다 — 그 칸은 **우리 적재 시각**이고, 그 수가 말한 것은
우리가 8월에 적재했다는 사실뿐이다. 내용이 그대로여도 재적재하면 모든 문서가 새것이 된다.

값은 이미 오고 있었다: 노션 커넥터가 `origin_last_edited` 로 frontmatter 에 싣는다.
**저장되는 자리가 없었을 뿐이고**, 그래서 코드 전체에서 그 이름이 두 곳에만 나왔다.

⚠ 이 파일은 **저장**만 지킨다. 신선도 경고는 오늘과 똑같이 적재 시각으로 돈다 — 경고를
바꾸는 것은 사용자가 보는 것을 바꾸는 일이라 별도 결정이다.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from nexus.ingest.pipeline import origin_updated_at


# ── 순수: 무엇을 읽고 무엇을 안 읽는가 ────────────────────────────────────────

def test_it_reads_what_notion_actually_sends():
    """노션은 `Z` 로 끝나는 ISO 8601 을 준다."""
    got = origin_updated_at({"origin_last_edited": "2026-03-14T05:33:00.000Z"})
    assert got == datetime(2026, 3, 14, 5, 33, tzinfo=timezone.utc)


def test_a_naive_timestamp_is_read_as_utc():
    """⛔ naive 를 TIMESTAMPTZ 에 넣으면 서버 시간대만큼 조용히 옮겨 앉는다.

    그 오차는 나이 분포에서 안 보인다 — 몇 시간이라 어느 묶음도 안 바꾸기 때문이다.
    """
    got = origin_updated_at({"origin_last_edited": "2026-03-14T05:33:00"})
    assert got is not None and got.tzinfo is not None
    assert got == datetime(2026, 3, 14, 5, 33, tzinfo=timezone.utc)


@pytest.mark.parametrize("raw", ["", "   ", "어제", "2026-13-45", None, 17, [], {"a": 1}])
def test_a_value_it_cannot_read_is_none_never_an_exception(raw):
    """⛔ **적재가 죽으면 안 된다.** 원본이 준 문자열 하나 때문에 문서 전체를 잃는 거래는 나쁘다."""
    assert origin_updated_at({"origin_last_edited": raw}) is None


def test_a_missing_key_is_none():
    """파일 적재처럼 원본 수정 시각이라는 개념이 없는 경로 — 그것은 결함이 아니다."""
    assert origin_updated_at({}) is None


def test_none_means_unknown_not_new():
    """이 파일이 지키는 성질을 문장으로 박아 둔다.

    `None` 을 "새것" 으로 읽으면 이 칸은 `updated_at` 과 똑같은 거짓말을 하게 된다.
    읽는 쪽(`nexus doc-age`)이 `미상` 을 따로 세는 이유다.
    """
    assert origin_updated_at({"origin_last_edited": ""}) is None


# ── 배선: 값이 실제로 행에 앉는가 ────────────────────────────────────────────

pytestmark_db = pytest.mark.skipif(
    not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "origin_updated_at_test"


@pytestmark_db
@pytest.mark.asyncio
async def test_the_column_actually_holds_the_origin_time(db_pool):
    """⛔ 필드가 있는 것과 행에 앉는 것은 다르다 — 이 리포가 34시간짜리 침묵으로 배운 것."""
    from nexus import db
    from nexus.ingest.classifier import ClassificationResult
    from nexus.ingest.collector import CollectedFile
    from nexus.ingest.pipeline import _save_document

    previous = db._pool
    db._pool = db_pool
    try:
        async with db_pool.acquire() as con:
            await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
        collected = CollectedFile(
            path=None, relative_path="a.md", content="본문", content_hash="h",
            frontmatter={"title": "문서", "origin_last_edited": "2024-01-02T03:04:05.000Z"},
            canonical_uri=f"{_TENANT}:a.md")
        cls = ClassificationResult(classification="INTERNAL", is_quarantined=False,
                                   pii_types=[], doc_type="NOTE", language="ko")
        rid = await _save_document(collected, cls, _TENANT)

        async with db_pool.acquire() as con:
            row = await con.fetchrow(
                "SELECT origin_updated_at, updated_at FROM documents WHERE rid=$1", rid)
        assert row["origin_updated_at"] == datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        assert row["updated_at"] > row["origin_updated_at"], \
            "적재 시각이 원본 시각과 같아졌다 — 두 칸이 같은 것을 담으면 이 작업은 무의미하다"

        # ⛔ 두 번째 적재가 그 값을 **지우면 안 된다.** 커넥터가 시각을 못 준 재적재가
        #    이미 알던 것을 NULL 로 덮으면, 아는 것이 모르는 것으로 바뀐다.
        collected.frontmatter.pop("origin_last_edited")
        collected.content_hash = "h2"
        await _save_document(collected, cls, _TENANT)
        async with db_pool.acquire() as con:
            again = await con.fetchval(
                "SELECT origin_updated_at FROM documents WHERE rid=$1", rid)
        assert again == datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc), \
            "재적재가 아는 값을 지웠다"

        async with db_pool.acquire() as con:
            await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    finally:
        db._pool = previous
