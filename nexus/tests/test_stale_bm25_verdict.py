"""BM25 색인 낡음 하니스의 **판정 규칙** (`OPEN.md` A92). 순수 — DB 없다.

⛔ **A93 을 반복하지 않으려고 있는 검사다.** 어제 낡음 하니스의 대조군이 빈 집합이 되자
`0/466` 이 *"낡은 게 없다"* 인지 *"아무것도 못 가른다"* 인지 구별되지 않았고, 그 부재가
**침묵으로** 표현됐다. 여기서는 수를 못 믿는 경우마다 **판정을 안 낸다.**
"""

from __future__ import annotations

from scripts.check_stale_bm25 import verdict


def _v(checked, mismatched, *, matched=0, n=10):
    return verdict(checked=checked, mismatched=mismatched,
                   shuffled_matched=matched, shuffled_n=n)


def test_a_healthy_run_reports_the_count():
    v = _v(466, 3)
    assert v["usable"] is True and v["stale"] == 3


def test_a_clean_corpus_reports_zero_and_that_zero_is_usable():
    """⭐ 대조군이 섰으므로 이 0 은 *가르지 못한 0* 이 아니다."""
    v = _v(466, 0)
    assert v["usable"] is True and v["stale"] == 0


def test_nothing_to_look_at_is_not_a_result():
    """⛔ 0건을 보고 '낡은 것 0' 이라고 적으면 없는 사실을 만든다."""
    assert _v(0, 0)["usable"] is False


def test_a_shuffled_pair_that_matches_kills_the_verdict():
    """⛔ 서로 다른 텍스트를 같다고 부르는 비교는 **아무 말도 못 한다.**"""
    v = _v(466, 3, matched=1)
    assert v["usable"] is False and "뒤섞은 짝" in v["why"]


def test_an_empty_shuffled_control_kills_the_verdict():
    """A93 그 자체 — 대조군이 비면 그것이 실패다."""
    v = _v(466, 3, n=0)
    assert v["usable"] is False and "대조군이 비었다" in v["why"]


def test_everything_mismatching_is_read_as_our_own_tokeniser_not_the_corpus():
    """⚠ 전수 불일치는 코퍼스가 전부 낡은 것보다 **이 스크립트가 색인기와 다른 것**이 훨씬
    그럴듯하다. 그 수를 결함으로 보고하면 존재하지 않는 사고를 만든다."""
    v = _v(466, 466)
    assert v["usable"] is False and "토큰화가 색인기와" in v["why"]


def test_all_but_one_mismatching_is_still_reported():
    """⛔ 전수만 거른다 — '거의 전부' 를 같이 거르면 진짜 사전 교체를 못 보게 된다."""
    v = _v(466, 465)
    assert v["usable"] is True and v["stale"] == 465
