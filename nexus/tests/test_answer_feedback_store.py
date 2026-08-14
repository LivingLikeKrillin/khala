"""답변 피드백 저장 (SPEC-nexus-answer-feedback U1, approved 2026-08-14).

👎 는 **지표가 아니라 단서**다. 팀이 5명이라 비율은 영원히 안 나오고, 그 사실을 설계 전제로
삼는다 — 그래서 이 층이 하는 일은 **수와 사유 코드를 정직하게 세는 것** 하나다.

지키는 불변식 (SPEC §4):

  I1   표에 신원이 없다 (principal·user_id·그 파생 해시 컬럼 부재)
  I2   `answer_key` 는 CSPRNG 이고 **발급→저장 경로를 실행해서** 확인한다
  I3   `answer_key` 는 이 두 표에만 있다 (principal 을 가진 표와 동거 금지)
  I5   투표는 INSERT — 두 번째 투표가 첫 투표를 덮지 않는다
  I6   피드백 실패가 답변을 죽이지 않는다 + 제안 행이 없어도 투표를 안 버린다
  I7   만료된 키는 투표를 못 받는다
  I10  투표는 **결속된 메시지**에서만 받는다
  I12  포인터 컬럼은 90일 뒤 지워지고, 수와 사유 코드는 남는다
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.feedback import store as F  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요 — 저장 경로를 태운다")

_T = "fb_test"
_CH, _TS = "C123", "1700000000.000100"


# `nexus.db` 의 **전역 풀**을 연다 — 저장 함수가 보는 풀과 검사가 보는 풀이 갈라지면
# 앞 테스트가 닫은 루프에 걸려 'Event loop is closed' 로 죽는다
# (`test_query_text_retention.py` 가 같은 이유로 같은 모양을 쓴다).

async def _clear(dbmod):
    await dbmod.execute("DELETE FROM answer_vote WHERE tenant = $1", _T)
    await dbmod.execute("DELETE FROM answer_offered WHERE tenant = $1", _T)


@pytest.fixture
async def clean_db(db_url):
    from nexus import db as dbmod

    os.environ["DATABASE_URL"] = db_url
    await dbmod.get_pool()
    try:
        await _clear(dbmod)
        yield dbmod
        await _clear(dbmod)
    finally:
        await dbmod.close_pool()


# ── I2 — 키는 CSPRNG 이고, 발급한 값이 실제로 그 칸에 앉는다 ──────────────────

def test_the_key_comes_from_a_csprng_not_a_counter():
    """**"두 번 부르면 다르다" 는 검사가 아니다** — 카운터도, 타임스탬프도 통과한다.

    소스 수준으로 발급기를 못 박는다. 이것만으로도 부족해서 아래 검사가 경로를 실행한다.
    """
    import inspect

    src = inspect.getsource(F.issue_key)
    assert "secrets.token_urlsafe" in src, "발급기가 CSPRNG 가 아니다"
    assert F.issue_key() != F.issue_key()
    assert len(F.issue_key()) >= 22, "128비트 미만이면 열거를 못 막는다"


@pytest.mark.asyncio
async def test_the_issued_key_is_the_one_that_lands_in_the_column(clean_db):
    """소스 문자열 검사만 두면 이 리포가 기록한 거짓 초록 유형이 된다 — 경로를 태운다."""
    from nexus import db

    key = F.issue_key()
    await F.record_offer(tenant=_T, answer_key=key, channel_id=_CH, message_ts=_TS)
    row = await db.fetch_one(
        "SELECT answer_key FROM answer_offered WHERE tenant = $1", _T)
    assert row["answer_key"] == key, "발급한 값과 저장된 값이 다르다"


# ── I1·I3 — 신원이 없고, 키가 다른 표와 동거하지 않는다 ───────────────────────

@pytest.mark.asyncio
async def test_neither_table_has_an_identity_column(clean_db):
    from nexus import db

    for table in ("answer_offered", "answer_vote"):
        rows = await db.fetch_all(
            "SELECT column_name FROM information_schema.columns WHERE table_name = $1", table)
        cols = {r["column_name"] for r in rows}
        for banned in ("principal", "user_id", "slack_user_id", "voter", "voter_hash"):
            assert banned not in cols, f"{table} 에 {banned} 가 있다 — §3.4 위반"


@pytest.mark.asyncio
async def test_the_key_lives_in_exactly_two_tables(clean_db):
    """`retention_key` 에 건 교차표 검사와 같은 모양. **principal 을 가진 표와 동거 금지.**"""
    from nexus import db

    rows = await db.fetch_all(
        "SELECT table_name FROM information_schema.columns WHERE column_name = 'answer_key'")
    assert {r["table_name"] for r in rows} == {"answer_offered", "answer_vote"}


# ── I5 — 투표는 INSERT ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_second_vote_does_not_overwrite_the_first(clean_db):
    """한 답변을 여럿이 본다. 덮어쓰면 **분모는 남고 분자가 조용히 유실된다.**"""
    from nexus import db

    key = F.issue_key()
    await F.record_offer(tenant=_T, answer_key=key, channel_id=_CH, message_ts=_TS)
    a = await F.record_vote(tenant=_T, answer_key=key, verdict="up",
                            channel_id=_CH, message_ts=_TS)
    b = await F.record_vote(tenant=_T, answer_key=key, verdict="down",
                            channel_id=_CH, message_ts=_TS)

    assert a != b
    rows = await db.fetch_all("SELECT verdict FROM answer_vote WHERE tenant = $1", _T)
    assert len(rows) == 2 and {r["verdict"] for r in rows} == {"up", "down"}


# ── I10 — 결속된 메시지에서만 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_vote_from_another_message_is_refused(clean_db):
    """결속이 없으면 `answer_key` 는 30일짜리 **무기명 자격증명**이다."""
    from nexus import db

    key = F.issue_key()
    await F.record_offer(tenant=_T, answer_key=key, channel_id=_CH, message_ts=_TS)

    with pytest.raises(F.VoteRefused):
        await F.record_vote(tenant=_T, answer_key=key, verdict="down",
                            channel_id="C999", message_ts=_TS)
    with pytest.raises(F.VoteRefused):
        await F.record_vote(tenant=_T, answer_key=key, verdict="down",
                            channel_id=_CH, message_ts="1700000000.999999")

    rows = await db.fetch_all("SELECT id FROM answer_vote WHERE tenant = $1", _T)
    assert rows == [], "거절된 투표가 표에 남았다"


# ── I7 — 만료 ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_key_older_than_thirty_days_stops_accepting_votes(clean_db):
    from nexus import db

    key = F.issue_key()
    await F.record_offer(tenant=_T, answer_key=key, channel_id=_CH, message_ts=_TS)
    await db.execute(
        "UPDATE answer_offered SET offered_at = $1 WHERE tenant = $2 AND answer_key = $3",
        datetime.now(timezone.utc) - timedelta(days=31), _T, key)

    with pytest.raises(F.VoteRefused):
        await F.record_vote(tenant=_T, answer_key=key, verdict="up",
                            channel_id=_CH, message_ts=_TS)


# ── I6 — 제안 행이 없어도 투표를 버리지 않는다 ────────────────────────────────

@pytest.mark.asyncio
async def test_an_orphan_vote_is_kept_and_marked(clean_db):
    """제안 쓰기는 best-effort 다. 투표를 FK 로 막으면 **시스템이 불안정할 때 정확히 그때의
    투표만 통째로 사라진다.** 대신 `synthesized` 로 표시해 분모에서 뺀다."""
    from nexus import db

    key = F.issue_key()          # 제안 행을 만들지 않는다
    before = F.counters["orphan_votes"]["unknown_key"]
    vote_id = await F.record_vote(tenant=_T, answer_key=key, verdict="down",
                                  channel_id=_CH, message_ts=_TS)

    assert vote_id
    off = await db.fetch_one(
        "SELECT synthesized, notice_version FROM answer_offered WHERE tenant=$1 AND answer_key=$2",
        _T, key)
    assert off["synthesized"] is True
    assert off["notice_version"] is None, "고지 버전을 지어내면 안 된다 — 모르는 것은 NULL 이다"
    assert F.counters["orphan_votes"]["unknown_key"] == before + 1


@pytest.mark.asyncio
async def test_synthesized_rows_are_excluded_from_the_denominator(clean_db):
    """§5.3 — 제안이 아니었던 것을 제안으로 세면 분모가 부푼다."""
    real = F.issue_key()
    await F.record_offer(tenant=_T, answer_key=real, channel_id=_CH, message_ts=_TS)
    await F.record_vote(tenant=_T, answer_key=real, verdict="up",
                        channel_id=_CH, message_ts=_TS)
    orphan = F.issue_key()
    await F.record_vote(tenant=_T, answer_key=orphan, verdict="down",
                        channel_id=_CH, message_ts=_TS)

    counts = await F.tally(tenant=_T)
    assert counts["offered"] == 1, "synthesized 행이 분모에 들어갔다"
    assert counts["answers_with_votes"] == 1, "분자도 같은 모집단이어야 한다"
    assert counts["synthesized"] == 1


# ── 사유 UPDATE 의 가드 셋 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_reason_lands_on_the_vote_it_was_asked_about(clean_db):
    from nexus import db

    key = F.issue_key()
    await F.record_offer(tenant=_T, answer_key=key, channel_id=_CH, message_ts=_TS)
    first = await F.record_vote(tenant=_T, answer_key=key, verdict="down",
                                channel_id=_CH, message_ts=_TS)
    second = await F.record_vote(tenant=_T, answer_key=key, verdict="down",
                                 channel_id=_CH, message_ts=_TS)

    assert await F.set_reason(vote_id=second, reason="ignored_format") is True
    rows = {r["id"]: r["reason"]
            for r in await db.fetch_all("SELECT id, reason FROM answer_vote WHERE tenant=$1", _T)}
    assert rows[second] == "ignored_format"
    assert rows[first] is None, "남의 투표에 사유가 적혔다 — 유일한 산출물이 오염된다"


@pytest.mark.asyncio
async def test_a_reason_cannot_be_written_twice(clean_db):
    key = F.issue_key()
    await F.record_offer(tenant=_T, answer_key=key, channel_id=_CH, message_ts=_TS)
    vid = await F.record_vote(tenant=_T, answer_key=key, verdict="down",
                              channel_id=_CH, message_ts=_TS)
    assert await F.set_reason(vote_id=vid, reason="not_found") is True
    assert await F.set_reason(vote_id=vid, reason="wrong_evidence") is False, (
        "오래된 ephemeral 을 다시 눌러 사유가 덮어써졌다")


@pytest.mark.asyncio
async def test_an_up_vote_takes_no_reason(clean_db):
    key = F.issue_key()
    await F.record_offer(tenant=_T, answer_key=key, channel_id=_CH, message_ts=_TS)
    vid = await F.record_vote(tenant=_T, answer_key=key, verdict="up",
                              channel_id=_CH, message_ts=_TS)
    assert await F.set_reason(vote_id=vid, reason="not_found") is False


@pytest.mark.asyncio
async def test_an_unknown_reason_code_is_refused(clean_db):
    """사유 집합은 스키마가 강제한다 — 자유 텍스트 컬럼이 되면 §2 와 마찰한다."""
    key = F.issue_key()
    await F.record_offer(tenant=_T, answer_key=key, channel_id=_CH, message_ts=_TS)
    vid = await F.record_vote(tenant=_T, answer_key=key, verdict="down",
                              channel_id=_CH, message_ts=_TS)
    with pytest.raises(Exception):
        await F.set_reason(vote_id=vid, reason="그냥 마음에 안 듦")


# ── I6 — 저장 실패가 답변을 죽이지 않는다 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_a_failing_offer_write_does_not_raise():
    """답변 경로에서 부른다. 여기서 예외가 나가면 피드백이 답변을 죽인다.

    `monkeypatch` 를 안 쓰고 손으로 되돌린다 — 그 픽스처의 되돌림은 conftest 의 teardown
    **뒤에** 돌 수 있고, 그러면 정리 코드가 이 가짜 예외를 맞는다(실제로 그랬다).
    """
    async def boom(*a, **k):
        raise RuntimeError("DB 없음")

    real = F.db.execute
    F.db.execute = boom
    try:
        await F.record_offer(tenant=_T, answer_key=F.issue_key(),
                             channel_id=_CH, message_ts=_TS)   # 예외가 안 나가야 한다
    finally:
        F.db.execute = real


# ── I12 — 포인터는 90일 뒤 지워지고 수는 남는다 ───────────────────────────────

@pytest.mark.asyncio
async def test_pointers_expire_but_the_counts_survive(clean_db):
    from nexus import db

    key = F.issue_key()
    await F.record_offer(tenant=_T, answer_key=key, channel_id=_CH, message_ts=_TS)
    await F.record_vote(tenant=_T, answer_key=key, verdict="down",
                        channel_id=_CH, message_ts=_TS)
    await db.execute(
        "UPDATE answer_offered SET offered_at = $1 WHERE tenant = $2 AND answer_key = $3",
        datetime.now(timezone.utc) - timedelta(days=91), _T, key)

    n = await F.purge_pointers()
    assert n == 1

    off = await db.fetch_one(
        "SELECT channel_id, message_ts FROM answer_offered WHERE tenant=$1 AND answer_key=$2",
        _T, key)
    assert off["channel_id"] is None and off["message_ts"] is None, "추정 경로가 남았다"
    counts = await F.tally(tenant=_T)
    assert counts["offered"] == 1 and counts["answers_with_votes"] == 1, "집계가 같이 죽었다"
