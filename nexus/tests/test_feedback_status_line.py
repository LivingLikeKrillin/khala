"""👎 의 수가 **이미 보는 자리**에 나오는가 (SPEC-nexus-answer-feedback §3.7).

⛔ **왜 있나 (실측 2026-09-11).** §3.7 은 푸시를 지우면서 대안을 하나 내걸었다 —
*"수는 `nexus status` 에도 한 줄로 나온다. 이미 보는 자리에 놓는 것이 이 단계에서 할 수 있는
전부이고, 전달 방식은 §5.3 평가일에 실제 비율을 손에 쥐고 정한다."* 그 한 줄이 없었다.

수는 `persistence-health` 에만 있었는데, 그것은 사람이 따로 떠올려 쳐야 하는 **또 하나의 조회
명령**이다. §3.7 이 스스로 적어 둔 잔여 위험이 *"아무도 조회를 안 하면 자료는 쌓이기만 한다"*
이고, 그 위험을 덜려던 대안이 같은 모양으로 들어가 있었다. 이 리포는 인덱스 커버리지에서
한 번 그렇게 데였다 — 감지기는 찍었고 **전달**이 없었다.
"""

from __future__ import annotations

import datetime as dt

from nexus.feedback.store import status_lines


def _row(votes: int, down: int, reasoned: int, last=dt.datetime(2026, 8, 30, 11, 6)):
    return {"votes": votes, "down": down, "reasoned": reasoned, "last_at": last}


def test_the_count_reaches_the_line():
    """라이브 실측 2026-09-11 의 모양 그대로."""
    out = status_lines(_row(3, 2, 2))
    assert out[0].startswith("답변 피드백:")
    assert "투표 3건" in out[0]
    assert "👎 2" in out[0] and "사유 2" in out[0]
    assert "2026-08-30" in out[0]


def test_a_down_vote_names_the_command_that_opens_it():
    """수만 보이면 다음 동작이 없다. §3.7 이 조회를 대안으로 내걸었으므로 그 이름을 같이 낸다."""
    out = status_lines(_row(3, 2, 2))
    assert any("nexus feedback" in line for line in out)


def test_no_down_vote_does_not_offer_the_command():
    """대조군 — 볼 것이 없는데 조회를 권하면 그 줄이 곧 무시된다."""
    out = status_lines(_row(1, 0, 0))
    assert not any("nexus feedback" in line for line in out)


def test_empty_is_not_reported_as_broken():
    """⚠ 이 표는 사람이 누를 때만 쌓이고 오래 비어 있는 것이 기본값이다.
    빈 것과 안 도는 것을 한 문장으로 말하면 읽는 사람이 못 가른다."""
    out = status_lines(_row(0, 0, 0))
    assert len(out) == 1
    assert "아직 없음" in out[0]
    assert "사람이 누를 때만" in out[0]


def test_a_missing_row_is_the_empty_case_not_a_crash():
    """구버전 DB·빈 표에서 `fetch_one` 이 None 을 준다. 진단이 상태를 죽이면 안 된다."""
    assert status_lines(None) == status_lines(_row(0, 0, 0))


def test_a_null_timestamp_does_not_break_the_line():
    out = status_lines(_row(2, 1, 1, last=None))
    assert "마지막 —" in out[0]


def test_thousands_are_separated():
    """월 10표 추정이지만 서식이 수를 못 읽게 만들면 안 된다."""
    out = status_lines(_row(1234, 567, 89))
    assert "1,234" in out[0] and "567" in out[0]
