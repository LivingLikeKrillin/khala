"""낡음 하니스의 **대조군이 비어 있을 수 없는가** (`OPEN.md` A93). 순수 — DB 없다.

⛔ **무엇이 있었나.** 대조군이 *`updated_at` 이 특정 날짜인 행* 으로 정의돼 있었다. 그 날짜의
행이 사라지자 대조군이 빈 집합이 됐고, 코드는 대조군 줄을 **아예 안 찍은 채 판정을 냈다.**
그때 나온 `0/466` 은 *낡은 게 없다* 와 *이 계측기는 아무것도 못 가른다* 에 똑같이 들어맞았다.

⭐ **그래서 여기서 지키는 것은 수가 아니라 침묵의 금지다**: 대조군이 비면 그것 자체가 실패이고,
판정은 안 나온다.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from scripts.check_stale_vectors import (
    FRESH_COSINE,
    controls_allow_a_verdict,
    negative_control,
    positive_control,
)

_NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


def _row(rid: str, *, written: datetime | None, updated: datetime, model: str = "KURE-v1") -> dict:
    return {"rid": rid, "written_at": written, "updated_at": updated, "model": model}


# ── 양성 대조군 ──────────────────────────────────────────────────────────────


def test_a_vector_written_after_its_row_is_the_control():
    """⭐ 이것이 날짜를 안 쓰는 정의다 — 코퍼스가 굴러가는 한 계속 채워진다."""
    rows = [_row("a", written=_NOW, updated=_NOW - timedelta(hours=1))]
    assert positive_control(rows, "KURE-v1") == ["a"]


def test_a_vector_written_before_its_row_is_not_the_control():
    """그 행은 **낡았을 수도 있다** — 대조군에 넣으면 하니스 검증이 순환이 된다."""
    rows = [_row("a", written=_NOW - timedelta(hours=1), updated=_NOW)]
    assert positive_control(rows, "KURE-v1") == []


def test_a_row_from_another_model_is_not_the_control():
    """⚠ 시각이 맞아도 다른 모델이 쓴 벡터는 지금 모델로 재계산하면 다르다 —
    넣으면 **멀쩡한 하니스를 고장났다고 부른다.**"""
    rows = [_row("a", written=_NOW, updated=_NOW - timedelta(hours=1), model="nomic-embed-text")]
    assert positive_control(rows, "KURE-v1") == []


def test_a_row_with_no_stamp_is_not_the_control():
    """도장이 없으면 **시각을 모른다.** 모르는 것을 대조군에 넣지 않는다."""
    rows = [_row("a", written=None, updated=_NOW)]
    assert positive_control(rows, "KURE-v1") == []


# ── 음성 대조군 ──────────────────────────────────────────────────────────────


def test_shuffled_pairs_below_the_threshold_mean_the_threshold_separates_something():
    neg = negative_control([0.61, 0.65, 0.70], FRESH_COSINE)
    assert neg["discriminates"] is True
    assert neg["n"] == 3


def test_a_single_duplicate_chunk_does_not_fail_the_negative_control():
    """⚠ 본문이 같은 청크의 짝은 **정당하게 1.0** 이다. 최댓값으로 판정하면 중복 하나가
    대조군을 떨어뜨린다 — 그래서 중앙값으로 판정하고 최댓값은 보고만 한다."""
    neg = negative_control([0.61, 0.65, 1.0], FRESH_COSINE)
    assert neg["discriminates"] is True
    assert neg["at_or_above"] == 1 and neg["max"] == 1.0


def test_an_instrument_that_returns_one_for_everything_fails_the_negative_control():
    """⛔ 양성 대조군만으로는 이것을 못 잡는다 — 늘 1.0 을 내는 하니스도 양성은 통과한다."""
    assert negative_control([1.0, 1.0, 1.0], FRESH_COSINE)["discriminates"] is False


# ── 판정을 내도 되는가 ───────────────────────────────────────────────────────


def test_both_controls_healthy_allows_the_verdict():
    ok, why = controls_allow_a_verdict(1.0, negative_control([0.6, 0.7], FRESH_COSINE), FRESH_COSINE)
    assert ok and why == ""


def test_an_empty_positive_control_withholds_the_verdict():
    """⛔ **이것이 A93 그 자체다.** 예전 코드는 여기서 아무 말 없이 판정을 찍었다."""
    ok, why = controls_allow_a_verdict(None, negative_control([0.6], FRESH_COSINE), FRESH_COSINE)
    assert not ok and "양성 대조군이 비었다" in why


def test_an_empty_negative_control_withholds_the_verdict_and_says_how_to_fix_it():
    """말만 하고 처방을 안 주면 다음 사람이 그냥 무시한다."""
    ok, why = controls_allow_a_verdict(1.0, negative_control([], FRESH_COSINE), FRESH_COSINE)
    assert not ok and "--fresh" in why


def test_a_broken_instrument_withholds_the_verdict():
    ok, why = controls_allow_a_verdict(0.4, negative_control([0.6], FRESH_COSINE), FRESH_COSINE)
    assert not ok and "고장난" in why


def test_a_threshold_that_separates_nothing_withholds_the_verdict():
    ok, why = controls_allow_a_verdict(1.0, negative_control([1.0, 1.0], FRESH_COSINE), FRESH_COSINE)
    assert not ok and "가르지 못한다" in why
