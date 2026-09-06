"""`written_at` 감지기의 **순수** 절반 — DB 없이 돈다.

⛔ **이 감지기가 무엇이 아닌지가 핵심이다.** `candidates` 는 *낡은 벡터 수*가 아니라
**낡을 수 있는 것의 상한**이다. `updated_at` 은 내용이 안 바뀐 재적재에도 움직이는데 그때는
무효화가 안 걸린다. 이 구분이 무너지면 이 감지기는 상시 거짓 경보가 되고, 이 리포는 이미
그렇게 데였다 — 진짜 `pending=51` 한 줄이 거짓 경보 739줄에 묻혔다.
"""

from __future__ import annotations

from nexus.index.provenance import summarize_freshness


def _counts(filled: int, fresh: int, cand: int, unstamped: int) -> dict:
    return {"filled": filled, "provably_fresh": fresh,
            "candidates": cand, "unstamped": unstamped}


def test_the_output_is_the_set_that_still_needs_recomputing():
    """⭐ 감지기의 산출물은 *"낡았다"* 가 아니라 **"확인할 것은 이만큼뿐이다"** 이다."""
    s = summarize_freshness(_counts(2045, 1736, 309, 0))
    assert s["must_recheck"] == 309
    assert s["ruled_out"] == 1736


def test_unstamped_rows_are_counted_as_needing_a_check_not_as_fresh():
    """⚠ 시간을 모르는 행을 신선 쪽에 넣으면 **모른다와 괜찮다가 같아진다.**"""
    s = summarize_freshness(_counts(100, 60, 10, 30))
    assert s["must_recheck"] == 40, "미상 30 이 확인 대상에 들어가야 한다"
    assert s["ruled_out"] == 60


def test_a_store_with_no_stamps_at_all_says_so_instead_of_saying_fresh():
    """⛔ 도장이 하나도 없으면 이 감지기는 **아무 말도 못 한다.** 그 사실이 보여야 한다."""
    s = summarize_freshness(_counts(500, 0, 0, 500))
    assert s["blind"] is True
    assert s["ruled_out"] == 0


def test_an_empty_column_is_not_blind_because_there_is_nothing_to_be_blind_about():
    """벡터가 0개면 감지기가 눈먼 것이 아니라 볼 것이 없는 것이다 — 둘을 같이 부르면
    새 배포가 켜지자마자 경보를 낸다."""
    assert summarize_freshness(_counts(0, 0, 0, 0))["blind"] is False


def test_the_counts_pass_through_so_the_caller_can_report_the_raw_numbers():
    """요약이 원수를 삼키면 읽는 사람이 이 감지기의 감도를 못 가늠한다."""
    s = summarize_freshness(_counts(10, 4, 3, 3))
    for k, v in _counts(10, 4, 3, 3).items():
        assert s[k] == v
