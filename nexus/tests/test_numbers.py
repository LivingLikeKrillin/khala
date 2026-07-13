"""답변 숫자의 근거 대조 — SPEC-nexus-answer-number-verification §5.

validate_numbers 순수 함수: 답변의 유의미한 숫자가 LLM 이 본 것(evidence + query)에
실재하는지 결정론적으로 대조한다. LLM 판정 없음.
"""

from __future__ import annotations

from nexus.llm.numbers import validate_numbers


def _by_value(report):
    return {n.value: n.grounded for n in report.numbers}


def test_significant_number_present_is_grounded_absent_is_unverified():
    r = validate_numbers("점유율은 47% 이고 지연은 250ms 이다.",
                         evidence_text="측정 결과 점유율 47% 로 나타났다.")
    g = _by_value(r)
    assert g["47%"] is True
    assert g["250"] is False           # 250 은 근거에 없음 (ms 는 숫자 토큰 밖)
    assert r.unverified_count == 1


def test_number_only_in_query_is_grounded():
    # 사용자가 질문에 넣은 수치는 모델에 주어진 것 — 되풀이는 fabrication 아님(I-001).
    r = validate_numbers("요청하신 500건 기준으로 계산했습니다.",
                         evidence_text="근거에는 수치가 없다.",
                         query="500건일 때 어떻게 되나?")
    assert _by_value(r)["500"] is True
    assert r.unverified_count == 0


def test_percent_class_is_distinct():
    # 5% 는 5.00% 와 같지만 bare 5 와는 다르다(I-002).
    r1 = validate_numbers("오류율은 5% 이다.", evidence_text="error_rate 5.00%")
    assert _by_value(r1)["5%"] is True

    r2 = validate_numbers("오류율은 5% 이다.", evidence_text="서비스 5 개가 있다.")
    assert _by_value(r2)["5%"] is False        # bare 5 로는 grounding 안 됨
    assert r2.unverified_count == 1


def test_canonicalization_matches_surface_variants():
    r = validate_numbers(
        "신뢰도 0.85, 총 1,000 건, 지연 120ms.",
        evidence_text="confidence 0.85 로 측정. 총 1000 건. latency 120ms.",
    )
    g = _by_value(r)
    assert g["0.85"] is True            # 0.85 == 0.85
    assert g["1,000"] is True           # 1,000 == 1000
    assert g["120"] is True             # 120 == 120 (ms 는 숫자 토큰 밖)
    assert r.unverified_count == 0


def test_significance_filter_skips_bare_small_integers():
    # bare 3 은 근거에 없어도 검사 대상이 아니다; 47(>=10)·3.14(소수)·50% 는 검사된다.
    r = validate_numbers(
        "3 개의 서비스가 47 번 호출되며 비율은 3.14, 목표는 50% 이다.",
        evidence_text="근거에는 관련 수치가 없다.",
    )
    g = _by_value(r)
    assert "3" not in g                 # bare 소수(小數) 정수 — skip
    assert g["47"] is False
    assert g["3.14"] is False
    assert g["50%"] is False
    assert r.unverified_count == 3


def test_version_like_tokens_excluded():
    # 버전/IP(점 2개 이상)는 숫자로 추출되지 않는다(I-005).
    r = validate_numbers("버전 3.2.1 로 배포했다.", evidence_text="근거 없음")
    assert r.numbers == []
    assert r.unverified_count == 0


def test_duplicate_unverified_number_counted_once():
    r = validate_numbers("47% 였고 다시 47%, 또 47% 였다.", evidence_text="근거 없음")
    assert len(r.numbers) == 1
    assert r.numbers[0].value == "47%"
    assert r.unverified_count == 1


def test_coincidental_collision_is_grounded_documented_miss():
    # 무관한 47% 가 근거 어딘가에 있으면 grounded 로 본다(알려진 false negative).
    r = validate_numbers("성장률은 47% 이다.",
                         evidence_text="전혀 다른 맥락의 오류율 47% 가 언급됨.")
    assert _by_value(r)["47%"] is True
    assert r.unverified_count == 0


def test_trailing_sentence_period_not_part_of_number():
    r = validate_numbers("최종 점유율은 47.", evidence_text="점유율 47 확인.")
    assert _by_value(r)["47"] is True


def test_empty_and_no_significant_numbers():
    assert validate_numbers("", evidence_text="근거 47%").unverified_count == 0
    assert validate_numbers("", evidence_text="근거 47%").numbers == []
    r = validate_numbers("서비스가 3 개, 팀이 2 개 있다.", evidence_text="근거 없음")
    assert r.numbers == []              # 전부 bare small → 검사 대상 없음
    assert r.unverified_count == 0


def test_never_raises_on_odd_input():
    for bad in ("버전 3.2.1", "%", "1,,2", "$", "3-5", "-5 도 있다", "숫자 없음"):
        validate_numbers(bad, evidence_text=bad, query=bad)   # 예외만 안 나면 통과
