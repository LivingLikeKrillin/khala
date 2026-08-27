"""판독기 재현율의 순수 로직 — SPEC-nexus-vision-reproducibility §4.

정규화가 판정을 만든다. 그래서 스크립트가 아니라 모듈에 있고, 여기서 못박는다.
"""

from __future__ import annotations

import pytest

from nexus.ingest.vision_health import (
    MAX_VARIATION,
    normalize,
    passes,
    summarize,
    tokens,
    variation,
)


def test_pipe_becomes_a_space_never_a_weld():
    """§4.2 — 지우면 어느 판독에도 없는 식별자가 만들어진다. 표를 쓰는 쪽만 피해를 본다."""
    idents, _ = tokens("| 60 | FENDI |")
    assert idents == {"60", "FENDI"}
    assert "60FENDI" not in idents


@pytest.mark.parametrize("raw,expect", [
    ("Ａｖａ＿０１", "Ava_01"),          # 전각 → NFKC
    ("① 지갑 연결", "1 지갑 연결"),      # 동그라미 숫자 → NFKC
    ("2−2. 설정", "2-2. 설정"),          # U+2212 → ASCII
    ("# 제목", "제목"),                  # 마크다운 헤딩
    ("> 인용", "인용"),
    ("값    사이   공백", "값 사이 공백"),
])
def test_rendering_folds(raw, expect):
    assert normalize(raw) == expect


def test_a_value_survives_normalisation():
    """`0.1.6` 은 서식이 아니라 값이다 — 접히면 안 된다."""
    idents, _ = tokens("Ver. 0.1.6")
    assert "0.1.6" in idents


def test_scaffold_only_rows_disappear():
    assert normalize("|---|---|\n| 값 |") == "값"


def test_token_classes_do_not_leak():
    idents, hangul = tokens("디제잉 포인트 60 Ava_01")
    assert idents == {"60", "Ava_01"}
    assert hangul == {"디제잉", "포인트"}


def test_a_mixed_script_identifier_is_one_token():
    """앞선 판은 ASCII 에 앵커돼 `툴팁_사용가이드_02` 를 `02` 로 잘랐다.

    조각을 "이 문자열이 그림에 있습니까" 로 물으면 거의 답할 수 없고 — 2026-08-11 판정에서
    대조군 하나가 그래서 뒤집혔다 — 서로 다른 식별자를 읽은 두 판독이 그 조각에서 **일치로**
    세어진다.
    """
    idents, hangul = tokens("툴팁_사용가이드_02")
    assert idents == {"툴팁_사용가이드_02"}
    assert hangul == set(), "식별자로 간 구간은 한글 축에서 이중으로 세지 않는다"


def test_two_different_mixed_identifiers_no_longer_collide():
    a, _ = tokens("툴팁_사용가이드_02")
    b, _ = tokens("툴팁_설정_02")
    assert a != b, "잘린 조각(`02`)에서 거짓 일치가 나면 안 된다"


def test_a_number_glued_to_hangul_stays_whole():
    idents, hangul = tokens("최대100곡")
    assert idents == {"최대100곡"} and hangul == set()


def test_pure_hangul_is_never_an_identifier():
    idents, hangul = tokens("파티룸 정책")
    assert idents == set() and hangul == {"파티룸", "정책"}


def test_dash_range_is_not_folded_and_that_is_pinned():
    """§4.3 — 알려진 한계다. 조용히 '고쳐서' 용접이 생기지 않도록 시험이 붙잡는다."""
    a, _ = tokens("10–20")
    b, _ = tokens("10 - 20")
    assert a == {"10-20"}
    assert b == {"10", "20"}
    assert a != b


def test_variation_endpoints():
    """§4.1 — 평가 하니스의 양 끝."""
    assert variation("Ava_01 60", "Ava_01 60") == 0.0
    assert variation("Ava_01", "ZZZ_99") == 1.0


def test_variation_ignores_text_with_no_identifiers():
    """그림에 글자가 없는 경우다. 잴 것이 없는 것은 불안정이 아니다."""
    assert variation("", "") == 0.0
    assert variation("디제잉", "포인트") == 0.0


def test_unmeasured_is_not_a_pass():
    """NULL 은 '괜찮다' 가 아니라 '아무도 안 쟀다' 다 — 지금 44행의 상태."""
    assert passes(None) is False
    assert passes(0.0) is True
    assert passes(MAX_VARIATION) is True
    assert passes(MAX_VARIATION + 0.001) is False


def test_summarize_reports_both_rates():
    pairs = [("Ava_01 60", "Ava_01 60"), ("Ava_01 60", "Ava_01 61")]
    s = summarize(pairs)
    assert s["images"] == 2
    assert s["identical"] == 1
    # 두 번째 쌍: 합집합 {Ava_01,60,61}, 대칭차 {60,61} → 2/3 over the union of both pairs
    assert 0 < s["variation"] < 1
    assert s["passes"] is False


def test_summarize_of_a_perfect_reader_passes():
    s = summarize([("Ava_01", "Ava_01"), ("60", "60")])
    assert s["variation"] == 0.0 and s["passes"] is True
    assert s["identical"] == 2
