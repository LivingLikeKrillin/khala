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
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from nexus.ingest.pipeline import ORIGIN_TIME_KEYS, origin_updated_at


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
    """어느 키도 없으면 모르는 것이다."""
    assert origin_updated_at({}) is None


# ── 파일이 적는 이름과 YAML 이 주는 타입 ──────────────────────────────────────
#
# ⛔ **이 묶음이 없어서 파일 경로가 이 칸을 한 번도 안 채웠다 (실측 2026-09-20).**
# 위의 검사들은 전부 `origin_last_edited` 에 **문자열**을 넣어서 통과했다. 그 둘 다
# 노션 커넥터의 사실이고, 파일을 쓰는 사람의 사실이 아니다.

def test_it_reads_the_key_a_person_writes_in_a_file():
    """⛔ 내가 설명층에 *"`updated:` 한 줄이면 채워진다"* 고 답했는데 **틀린 답이었다.**

    그 이름은 읽히지 않았고, 이 리포 자신의 합성 SOP 여섯 편이 그 이름을 적은 채
    여섯 편 다 NULL 이었다. 답이 틀렸다는 증거가 우리 코퍼스 안에 있었다.
    """
    assert origin_updated_at({"updated": "2026-09-18T01:02:03Z"}) == datetime(
        2026, 9, 18, 1, 2, 3, tzinfo=timezone.utc)


def test_a_bare_date_is_read_although_yaml_makes_it_a_date_object():
    """⛔ **키를 고치는 것만으로는 안 됐다.** `updated: 2026-09-18` 은 따옴표가 없으므로
    YAML 이 `datetime.date` 로 준다. `isinstance(raw, str)` 이 그것을 떨궜다.

    따옴표를 붙인 사람만 통과하는 규칙은 규칙이 아니다 — 문서를 쓰는 사람은 YAML 타입
    승격을 모른다.
    """
    assert origin_updated_at({"updated": date(2026, 9, 18)}) == datetime(
        2026, 9, 18, tzinfo=timezone.utc)


def test_a_datetime_object_keeps_its_time_of_day():
    """⛔ `datetime` 은 `date` 의 하위 타입이다. 검사 순서를 바꾸면 시·분·초가 조용히
    자정으로 잘리고, 그 손실은 날짜만 보는 어떤 표에서도 안 보인다."""
    got = origin_updated_at({"updated": datetime(2026, 9, 18, 13, 45, 7)})
    assert got == datetime(2026, 9, 18, 13, 45, 7, tzinfo=timezone.utc)
    assert (got.hour, got.minute) != (0, 0), "시각이 자정으로 잘렸다"


def test_the_source_system_wins_over_the_hand_written_line():
    """둘 다 있으면 원본 시스템이 이긴다 — 손으로 적은 값은 갱신을 잊을 수 있다."""
    got = origin_updated_at({
        "origin_last_edited": "2026-03-14T05:33:00.000Z",
        "updated": date(2020, 1, 1),
    })
    assert got == datetime(2026, 3, 14, 5, 33, tzinfo=timezone.utc)


def test_an_unreadable_first_key_falls_through_to_the_second():
    """⛔ 앞 키가 **있지만 못 읽을 때** 거기서 멈추면, 읽을 수 있는 값을 손에 쥐고 버린다."""
    assert origin_updated_at({"origin_last_edited": "어제", "updated": date(2026, 9, 18)}) == \
        datetime(2026, 9, 18, tzinfo=timezone.utc)


@pytest.mark.parametrize("raw", ["", "   ", "어제", "2026-13-45", None, 17, [], {"a": 1}])
def test_the_new_key_is_as_unexceptional_as_the_old_one(raw):
    """새 키도 적재를 죽이지 않는다 — 옛 키와 같은 성질을 같은 값들로 확인한다."""
    assert origin_updated_at({"updated": raw}) is None


def test_our_own_synthetic_corpus_declares_a_key_this_function_reads():
    """⭐ **대조군이 리포 안에 있다.** 이 검사가 잡으려는 것은 회귀 하나다 — 합성 SOP 가
    적는 이름과 이 함수가 읽는 이름이 다시 갈리는 것.

    그 갈림이 조용했던 이유는 적재가 **성공**했기 때문이다. 칸 하나가 비는 것은 실패가
    아니라서 아무 경보도 안 울렸다.
    """
    import frontmatter as fm_lib

    sop_dir = Path(__file__).resolve().parents[1] / "synthetic" / "picasso-sop"
    files = sorted(sop_dir.glob("SOP-*.md"))
    assert files, f"합성 SOP 를 못 찾았다: {sop_dir}"
    for path in files:
        meta = dict(fm_lib.loads(path.read_text(encoding="utf-8")).metadata)
        assert origin_updated_at(meta) is not None, (
            f"{path.name} 의 frontmatter 에 이 함수가 읽는 시각 키가 없다 "
            f"(읽는 키: {', '.join(ORIGIN_TIME_KEYS)})")


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


# ── 이음매: 값이 **커넥터에서 파이프라인까지** 살아 오는가 ────────────────────

def test_the_value_survives_the_seam_that_dropped_it():
    """⛔ **이 검사가 없어서 프로덕션이 조용히 틀렸다.**

    위 검사들은 `_save_document` 를 **직접** 불러서 통과했다. 실제 노션 경로는
    `ConvertedDoc → build_csf → 임시 마크다운 → collector → pipeline` 이고, 그 사슬의
    첫 칸(`build_csf`)이 이 값을 **버리고 있었다.** 그래서 마이그레이션을 넣고 적재를
    돌렸는데도 126건 전부 `미상` 이었다.

    이 리포가 이미 적어 둔 실패다 — *"생산자의 dict 를 검사했다."* 그래서 여기서는 사슬을
    **통과시켜서** 확인한다.

    ⭐ 같은 이음매에서 값이 사라진 것이 **세 번째**다: 제목 · 그림 수 · 그리고 이것.
    """
    import frontmatter as fm_lib

    from nexus.a2a.server import _csf_to_markdown_file
    from nexus.ingest.pipeline import origin_updated_at
    from nexus.ingest.sources.base import ConvertedDoc
    from nexus.ingest.sources.notion_importer import build_csf

    conv = ConvertedDoc(
        page_id="p1", markdown="본문",
        frontmatter={"title": "정책", "origin_last_edited": "2025-05-06T07:08:09.000Z"})
    csf = build_csf(conv, "p1", {"url": "https://example.invalid/p1"}, [])
    assert csf.get("origin_last_edited"), "build_csf 가 값을 버렸다 — 여기가 끊겼던 자리다"

    parsed = fm_lib.loads(_csf_to_markdown_file(csf))
    assert origin_updated_at(dict(parsed.metadata)) == datetime(
        2025, 5, 6, 7, 8, 9, tzinfo=timezone.utc), "임시 파일 frontmatter 까지 안 닿았다"


def test_a_page_without_an_edit_time_adds_no_frontmatter_key():
    """대조군 — 값이 없으면 임시 파일은 오늘과 **글자 그대로 같아야** 한다."""
    from nexus.a2a.server import _csf_to_markdown_file
    from nexus.ingest.sources.base import ConvertedDoc
    from nexus.ingest.sources.notion_importer import build_csf

    conv = ConvertedDoc(page_id="p2", markdown="본문", frontmatter={"title": "정책"})
    md = _csf_to_markdown_file(build_csf(conv, "p2", {"url": "u"}, []))
    assert "origin_last_edited" not in md
