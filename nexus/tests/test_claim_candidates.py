"""claim 후보 추출기 — 무엇을 후보로 세고 무엇을 **버렸다고 말하는가**.

⛔ 이 파일이 지키는 성질 하나: **버린 것이 보여야 한다.** 후보를 `문서가 그 값을 말한다` 로
좁히면 목록이 267 → 11 로 줄어드는데(실측 2026-09-03), 줄어든 사실을 시트가 말하지 않으면
읽는 사람은 그 11개가 전부라고 읽는다. 이 리포가 반복해서 데인 모양이다 — 좁힌 것을 안 적으면
좁힘이 사실로 승격된다.
"""

from __future__ import annotations

from scripts.claim_candidates import COMMON_CHUNKS, MIN_DIGITS, bucket, literal, sites_in


# ── 무엇을 값으로 보는가 ─────────────────────────────────────────────────────

def test_a_plain_number_is_a_value():
    assert literal("100") == "100"
    assert literal(" 4000L ") == "4000"
    assert literal("10_000") == "10000"


def test_a_single_digit_is_not_searchable_in_prose():
    """한 자리 수는 문서 아무 데나 나온다 — 세면 잡음이 결과가 된다."""
    assert literal("5") is None
    assert MIN_DIGITS == 2


def test_an_expression_or_reference_is_not_a_value():
    """계산식·상수 참조는 문서에서 찾을 수 있는 모양이 아니다."""
    assert literal("60 * 1000") is None
    assert literal("OTHER_CONST") is None
    assert literal('"문자열"') is None


# ── 코드에서 자리를 뽑는가 ───────────────────────────────────────────────────

def test_a_static_final_constant_is_a_site():
    got = sites_in("public static final int MAX_TASKS = 100;", "ProjectService")
    assert got == [("ProjectService", "MAX_TASKS", "100")]


def test_a_value_annotation_is_a_site_too():
    """`@Size(max = 30)` 은 상수가 아니지만 **정책 값이 사는 자리**다 — 실물의 절반이 이 모양이다."""
    got = sites_in("@Size(max = 30)\nprivate String name;", "CreateRequest")
    assert got == [("CreateRequest", "@Size.max", "30")]


def test_an_annotation_with_two_attributes_yields_two_sites():
    got = sites_in("@Range(min = 10, max = 200)", "R")
    assert [s[1] for s in got] == ["@Range.min", "@Range.max"]


def test_a_lowercase_field_is_not_a_constant():
    """`static final` 이라도 상수 이름 모양이 아니면 값이 아니라 참조일 때가 많다."""
    assert sites_in("static final int maxTasks = 100;", "S") == []


# ── 버린 것을 말하는가 ───────────────────────────────────────────────────────

def test_a_value_the_documents_never_mention_is_not_a_candidate():
    """문서가 말한 적 없는 상수는 claim 이 되어도 어떤 질문에도 안 붙는다."""
    assert bucket(0) == "문서에 없음"


def test_a_value_that_appears_everywhere_cannot_be_judged():
    """흔한 수는 '문서가 그 값을 말한다' 가 뜻을 잃는 지점이 있다."""
    assert bucket(COMMON_CHUNKS + 1) == "흔해서 판정 못 함"


def test_the_threshold_is_inclusive_so_the_boundary_is_a_candidate():
    assert bucket(COMMON_CHUNKS) == "후보"
    assert bucket(1) == "후보"


def test_the_three_buckets_are_exhaustive():
    """넷째 칸이 생기면 어딘가로 조용히 사라지는 자리가 나온다."""
    assert {bucket(n) for n in (0, 1, COMMON_CHUNKS, COMMON_CHUNKS + 1, 9999)} == {
        "문서에 없음", "후보", "흔해서 판정 못 함"}
