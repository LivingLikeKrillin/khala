"""코드 시맨틱 카드 — 후보·파싱·규칙 재검사·낡음 (SPEC-nexus-code-semantic-cards §3.1~§3.4).

⚠ 여기 Java 는 전부 지어낸 것이다. 대상 저장소의 소스를 픽스처로 복사하지 말 것.

이 파일에서 가장 중요한 것은 **소스 경계** 검사다. 앞 단위는 이름·경로·줄·해시만 저장했으므로
"소스 미저장" 이 자명했지만, 카드는 소스를 막 읽은 모델이 쓴 산문이라 자명하지 않다.
"""

from __future__ import annotations

import pytest

from nexus.index.cards import (
    FRESH,
    MAX_CODE_TERMS,
    ORPHANED,
    STALE,
    Card,
    CardParseError,
    CardSpan,
    card_state,
    check_card,
    is_card_candidate,
    is_near_duplicate,
    parse_card,
)

SRC = """\
public void dispatch(String payload) {
    if (attempts >= MAX_ATTEMPTS) {
        throw new RetryExhaustedException("too many attempts");
    }
    send(payload);
}
"""

SPAN = CardSpan(repo="r", file_path="Widget.java", start_line=10, end_line=15,
                symbol="dispatch", span_hash="h1")


def _card(**over) -> Card:
    base = dict(
        subject="결제 재시도",
        behavior="시도 횟수가 상한에 닿으면 예외를 던지고, 아니면 전송한다.",
        domain_terms=("결제", "재시도"),
        code_terms=("dispatch", "MAX_ATTEMPTS"),
        spans=(SPAN,),
        commit_sha="c1",
        generator="m·p1·2hops",
    )
    base.update(over)
    return Card(**base)


# ---------------------------------------------------------------- §3.1 후보

def test_types_are_always_candidates_however_short():
    assert is_card_candidate("class", 1, 2)
    assert is_card_candidate("interface", 1, 1)


def test_a_short_method_is_not_a_candidate():
    """게터·한 줄 위임자는 모델 호출을 쓰고 아무것도 서술하지 않는다."""
    assert not is_card_candidate("method", 1, 3)


def test_a_long_method_is_a_candidate():
    assert is_card_candidate("method", 1, 20)


def test_an_anchored_symbol_is_a_candidate_regardless_of_length():
    """문서가 이미 그 이름을 불렀으므로 서술할 값어치가 증명돼 있다."""
    assert is_card_candidate("method", 1, 2, anchored=True)


# ---------------------------------------------------------------- §3.2 파싱

def test_parses_a_plain_json_card():
    raw = '{"subject":"결제","behavior":"재시도한다","domain_terms":["결제"],"code_terms":["dispatch"]}'

    card = parse_card(raw, spans=[SPAN], commit_sha="c1", generator="g")

    assert card.subject == "결제"
    assert card.domain_terms == ("결제",)
    assert card.spans == (SPAN,)          # 호출자가 채운다
    assert card.generator == "g"


def test_strips_a_fenced_code_block():
    raw = '```json\n{"subject":"a","behavior":"b"}\n```'
    assert parse_card(raw, spans=[SPAN], commit_sha="c", generator="g").subject == "a"


def test_rejects_non_json():
    with pytest.raises(CardParseError):
        parse_card("설명하자면 이렇습니다", spans=[SPAN], commit_sha="c", generator="g")


def test_rejects_a_card_missing_behavior():
    with pytest.raises(CardParseError):
        parse_card('{"subject":"a"}', spans=[SPAN], commit_sha="c", generator="g")


def test_spans_come_from_the_caller_not_the_model():
    """모델이 말한 경로·줄은 틀릴 수 있고, 틀린 포인터는 카드를 통째로 버리게 만든다."""
    raw = '{"subject":"a","behavior":"b","spans":[{"file_path":"WRONG.java"}]}'

    card = parse_card(raw, spans=[SPAN], commit_sha="c", generator="g")

    assert card.spans[0].file_path == "Widget.java"


# --------------------------------------------- §3.2 소스 경계 (사용자 제약)

def test_a_clean_card_passes():
    assert check_card(_card(), {"Widget.java:10-15": SRC}) == []


def test_a_verbatim_source_line_in_prose_is_a_violation():
    """모델이 설명 대신 코드를 옮겨 적으면, 그 순간 카드가 유출 경로가 된다."""
    leaked = _card(behavior="이 메서드는 if (attempts >= MAX_ATTEMPTS) { 를 검사한다.")

    problems = check_card(leaked, {"Widget.java:10-15": SRC})

    assert any("소스 줄이 그대로" in p for p in problems)


def test_a_source_string_literal_in_prose_is_a_violation():
    leaked = _card(behavior='실패하면 too many attempts 라고 알린다.')

    problems = check_card(leaked, {"Widget.java:10-15": SRC})

    assert any("문자열 리터럴" in p for p in problems)


def test_a_number_in_prose_is_allowed():
    """'3회 재시도' 는 서술로서 정당하다. 숫자를 막으면 카드의 값이 사라진다 —
    막는 것은 `MAX_ATTEMPTS = 2` 같은 소스 줄이지 숫자 자체가 아니다."""
    ok = _card(behavior="상한은 3회이며, 넘으면 예외를 던진다.")

    assert check_card(ok, {"Widget.java:10-15": SRC}) == []


def test_short_source_lines_do_not_trigger_false_violations():
    """`}` 나 `);` 까지 대조하면 모든 카드가 걸린다."""
    ok = _card(behavior="분기하고 전송한다. }")

    assert check_card(ok, {"Widget.java:10-15": SRC}) == []


def test_code_terms_must_be_bare_identifiers():
    bad = _card(code_terms=("attempts >= MAX_ATTEMPTS",))

    problems = check_card(bad, {"Widget.java:10-15": SRC})

    assert any("식별자가 아님" in p for p in problems)


def test_code_terms_must_actually_appear_in_the_span():
    bad = _card(code_terms=("nowhereNear",))

    problems = check_card(bad, {"Widget.java:10-15": SRC})

    assert any("span 에 없음" in p for p in problems)


def test_code_terms_are_capped():
    bad = _card(code_terms=tuple(f"t{i}" for i in range(MAX_CODE_TERMS + 1)))

    problems = check_card(bad, {"Widget.java:10-15": SRC})

    assert any("code_terms 과다" in p for p in problems)


def test_a_span_that_does_not_exist_is_a_violation():
    problems = check_card(_card(), {"Widget.java:10-15": SRC},
                          known_spans={("Other.java", 1, 2)})

    assert any("span 미실재" in p for p in problems)


def test_card_has_no_source_like_field():
    """필드 이름 수준에서도 막는다 — 나중에 누가 스니펫 칸을 추가하면 여기서 걸린다."""
    banned = {"source", "text", "body", "snippet", "content", "code", "lines"}
    assert banned.isdisjoint(Card.__dataclass_fields__.keys())


# ---------------------------------------------------------------- 밀도

def test_near_duplicate_cards_are_detected():
    a = _card(subject="결제 재시도", behavior="상한에 닿으면 예외를 던진다")
    b = _card(subject="결제 재시도", behavior="상한에 닿으면 예외를 던진다")

    assert is_near_duplicate(a, b)


def test_different_cards_are_not_near_duplicates():
    a = _card(subject="결제 재시도", behavior="상한에 닿으면 예외를 던진다")
    b = _card(subject="정산 마감", behavior="월말에 장부를 닫고 보고서를 만든다")

    assert not is_near_duplicate(a, b)


# ---------------------------------------------------------------- §3.4 낡음

def test_unchanged_spans_are_fresh():
    assert card_state(_card(), {("Widget.java", "dispatch"): "h1"}) == FRESH


def test_a_changed_span_is_stale():
    """설명이 참이었던 코드가 움직였다 — 카드에 관한 사실이지 코드에 관한 사실이 아니다."""
    assert card_state(_card(), {("Widget.java", "dispatch"): "h2"}) == STALE


def test_a_vanished_span_is_orphaned():
    assert card_state(_card(), {}) == ORPHANED


def test_a_card_without_spans_is_orphaned():
    assert card_state(_card(spans=()), {}) == ORPHANED


def test_staleness_needs_no_model():
    """이 판정 경로에는 LLM 이 없다 — 해시 비교다. import 로 못박는다."""
    import inspect

    import nexus.index.cards as mod

    src = inspect.getsource(mod.card_state)
    for token in ("llm", "LLMService", "generate", "anthropic"):
        assert token not in src


# ------------------------------------------------- 생성기 (경계·신원)

def test_generator_id_carries_model_and_prompt_version():
    """프롬프트가 바뀌면 카드의 의미가 바뀐다. 세대가 섞이지 않게 신원을 싣는다."""
    from nexus.index.card_gen import PROMPT_VERSION, generator_id

    gid = generator_id("some-model")

    assert "some-model" in gid
    assert PROMPT_VERSION in gid


def test_source_collection_stops_at_the_byte_cap(tmp_path):
    """한 카드가 저장소를 다 읽지 않게 — §6.4 가 게이트하는 비용이 여기서 샌다."""
    from nexus.index.card_gen import collect_sources

    (tmp_path / "Big.java").write_text("\n".join(f"line {i};" for i in range(500)),
                                       encoding="utf-8")
    spans = [CardSpan("r", "Big.java", 1, 200, "a", "h"),
             CardSpan("r", "Big.java", 201, 400, "b", "h")]

    out = collect_sources(tmp_path, spans, max_bytes=1200)

    assert len(out) == 1                       # 두 번째 홉은 상한에 걸려 끊긴다
    assert len(next(iter(out.values()))) <= 1200   # 대상 span 은 잘려서라도 실린다


def test_the_subject_span_is_always_included_even_if_oversized(tmp_path):
    """소스가 하나도 없는 프롬프트를 받은 모델은 서술하지 않고 지어낸다."""
    from nexus.index.card_gen import collect_sources

    (tmp_path / "Huge.java").write_text("x" * 5000, encoding="utf-8")
    spans = [CardSpan("r", "Huge.java", 1, 1, "a", "h")]

    out = collect_sources(tmp_path, spans, max_bytes=100)

    assert len(out) == 1
    assert len(next(iter(out.values()))) == 100


def test_callees_finds_called_names():
    from nexus.index.card_gen import callees

    assert {"send", "validate"} <= callees("void f() { validate(x); send(y); }")


def test_prompt_contains_the_source_but_the_card_does_not(tmp_path):
    """소스는 프롬프트까지만 간다. 카드에는 서술과 포인터만 남는다."""
    from nexus.index.card_gen import build_prompt

    prompt = build_prompt("dispatch", {"Widget.java:10-15": SRC})

    assert "MAX_ATTEMPTS" in prompt                       # 프롬프트에는 있고
    card = _card(code_terms=("dispatch",))
    blob = f"{card.subject} {card.behavior}"
    assert "too many attempts" not in blob                # 카드 산문에는 없다


# ------------------------------------------------- §6.1 재현성 측정

def test_identical_runs_agree_completely():
    from nexus.index.cards import term_agreement

    a = term_agreement([("결제", "재시도"), ("결제", "재시도"), ("재시도", "결제")])

    assert a.mean == 1.0
    assert a.pairs == 3          # 3회 → 쌍 3개


def test_five_runs_give_ten_pairs_not_one_number():
    """2회는 구간 없는 점추정이다. 측정하려는 것이 흔들림인데 흔들림을 못 본다."""
    from nexus.index.cards import term_agreement

    a = term_agreement([("결제",)] * 5)

    assert a.pairs == 10


def test_disagreement_shows_up_as_a_range_not_just_a_mean():
    from nexus.index.cards import term_agreement

    a = term_agreement([("결제", "재시도"), ("결제", "재시도"), ("정산",)])

    assert a.low == 0.0          # 세 번째 실행은 앞 둘과 겹치지 않는다
    assert a.high == 1.0
    assert 0.0 < a.mean < 1.0


def test_case_and_space_are_normalised_but_nothing_else():
    """동의어 병합까지 하면 측정 코드가 생성기의 흔들림을 가려버린다."""
    from nexus.index.cards import term_agreement

    assert term_agreement([("결제 ", "Retry"), ("결제", "retry")]).mean == 1.0


def test_a_single_run_cannot_be_measured():
    from nexus.index.cards import term_agreement

    with pytest.raises(ValueError):
        term_agreement([("결제",)])


def test_generator_id_refuses_a_non_string_model():
    """`LLMService` 의 첫 인자는 모델 이름이지 설정이 아니다. 설정을 넘긴 적이 있고,
    그대로 두면 `auth.principals` 를 포함한 설정 전체가 모든 카드에 저장됐을 것이다."""
    from nexus.index.card_gen import generator_id

    with pytest.raises(TypeError):
        generator_id({"auth": {"principals": ["secret"]}})
    with pytest.raises(TypeError):
        generator_id("")
    with pytest.raises(TypeError):
        generator_id(None)


# ---------------------------------------------------------------- 재현성 하니스의 모집단
#
# 세 실험군을 돌려서야 알았다: 무작위 표본 12개 중 10개가 테스트 코드였고, `setUp` 을 업무 용어로
# 서술하라는 요구에는 안정된 답이 없다(일치도 0.017). 그 표본으로 측정한 재현성은 생성기가 아니라
# 모집단을 측정한 것이다. 그래서 경로 판정을 검사로 박는다 — 이 규칙이 조용히 틀리면 다음 측정이
# 또 테스트를 측정한다. (전말: docs/CODE_CARD_REPRODUCIBILITY.md)


def test_test_paths_are_excluded_from_the_card_population():
    from scripts.card_reproducibility import is_test_path

    assert is_test_path("src/test/java/app/FooTest.java")
    assert is_test_path("src/test/java/app/Helper.java")      # 테스트 디렉터리면 이름 무관
    assert is_test_path("app/FooTests.java")
    assert is_test_path("app/FooIT.java")
    assert is_test_path("nexus/tests/test_thing.py")


def test_production_code_that_merely_mentions_test_is_not_excluded():
    """`TestFixtures` 는 프로덕션 경로의 프로덕션 코드다. 이름으로 싸잡으면 모집단이 줄어든다."""
    from scripts.card_reproducibility import is_test_path

    assert not is_test_path("src/main/java/app/TestFixtures.java")
    assert not is_test_path("src/main/java/app/LatestPolicy.java")
    assert not is_test_path("src/main/java/app/Foo.java")
