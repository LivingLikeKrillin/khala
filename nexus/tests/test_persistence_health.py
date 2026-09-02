"""적재 건강 신호 — **오래 비어 있는 것과 고장을 구별해서 내는가.**

⛔ **왜 이 검사가 있나 (2026-09-02).** `search_log` 가 34시간 죽어 있었는데 검사 1,800개가
초록이었다. 실패 경고는 로그에 찍혔지만 아무도 안 읽었다 — 그래서 사람이 볼 수 있는 자리를
만들었다.

⛔ **그리고 만들자마자 내가 그것을 오독했다.** `search_answer_text` 가 62시간째 2행인 것을
두 번째 결함으로 읽었는데, 그 표는 슬랙이 답을 낼 때만 쌓이고 그동안 질문이 없었다. 정상이다.
**경과 시간만 내면 읽는 사람이 그렇게 읽는다** — 그래서 `driven_by` 가 조항이다.
"""

from __future__ import annotations

import os

import pytest

from nexus.health.persistence import SINKS, SinkHealth, describe

pytestmark_db = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"),
                                   reason="NEXUS_TEST_DB_URL 필요")


def _h(**kw) -> SinkHealth:
    base = dict(table="t", what="무엇", driven_by="무엇이 쓰나", rows=3,
                last_write="2026-09-02 02:00:00", hours_since=1.0)
    base.update(kw)
    return SinkHealth(**base)


def test_every_sink_declares_what_drives_it():
    """⛔ **조항이다.** 이것 없이는 '오래 비었다' 가 고장인지 조용함인지 못 읽는다."""
    for table, col, what, driven in SINKS:
        assert driven.strip(), f"{table} 에 driven_by 가 없다"
        assert col.strip() and what.strip()


def test_the_output_carries_the_driver_next_to_the_age():
    out = describe([_h(hours_since=62.1)])
    assert "62.1시간 전" in out
    assert "쓰게 하는 것: 무엇이 쓰나" in out


def test_the_output_warns_that_silence_is_not_failure():
    """⛔ 내가 한 오독을 읽는 사람이 반복하지 않게 맨 위에 적는다."""
    assert "고장은 아니다" in describe([_h()])


def test_a_missing_table_is_not_the_same_as_zero_rows():
    """표가 없는 것과 0행은 다른 사실이다 — 처방도 다르다."""
    out = describe([_h(exists=False, rows=0, last_write=None, hours_since=None)])
    assert "표가 없다" in out


def test_a_never_written_table_says_so():
    out = describe([_h(rows=0, last_write=None, hours_since=None)])
    assert "없음" in out and "—" in out


@pytestmark_db
@pytest.mark.asyncio
async def test_it_reads_a_real_database(db_pool):
    """⛔ 배선 검사. 표를 손으로 만든 검사만 있으면 질의가 틀려도 초록이다."""
    from nexus import db
    from nexus.health.persistence import check

    db._pool = db_pool
    await db.ensure_search_log()
    rows = await check()
    db._pool = None

    assert len(rows) == len(SINKS)
    by_name = {r.table: r for r in rows}
    assert by_name["search_log"].exists
    assert all(r.driven_by for r in rows)
