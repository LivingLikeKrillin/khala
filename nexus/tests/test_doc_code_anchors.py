"""앵커 추출·바인딩·재검사 (SPEC-nexus-doc-code-anchors §3.2, §3.3, §3.4).

⚠ 여기 나오는 심볼 이름과 문장은 전부 지어낸 것이다. 대상 저장소의 이름을 픽스처로 쓰지 말 것.
"""

from __future__ import annotations

from nexus.index.anchors import (
    AMBIGUOUS_NOW,
    CHANGED,
    FRESH,
    ORPHANED,
    bind,
    extract_candidates,
    recheck,
)


# ---------------------------------------------------------------- 추출

def test_picks_up_backticked_identifiers():
    text = "재시도는 `WidgetDispatcher` 가 맡고, 상한은 `MAX_ATTEMPTS` 다."
    assert extract_candidates(text) == ["WidgetDispatcher", "MAX_ATTEMPTS"]


def test_ignores_unbackticked_prose():
    assert extract_candidates("WidgetDispatcher 가 재시도를 맡는다") == []


def test_deduplicates_within_a_chunk():
    text = "`Widget` 은 ... 그리고 `Widget` 은 또한 ..."
    assert extract_candidates(text) == ["Widget"]


def test_rejects_dotted_names_rather_than_guessing_the_last_segment():
    """마지막 조각만 떼는 것은 추측이고, 추측한 앵커는 영구히 남는다 (§3.2)."""
    assert extract_candidates("`Widget.dispatch` 를 부른다") == []


def test_rejects_reserved_words():
    """예약어는 선언 이름이 될 수 없다 — 거부 분모를 정직하게 유지한다."""
    assert extract_candidates("`public` 과 `class` 와 `void`") == []


def test_rejects_single_character_tokens():
    assert extract_candidates("`i` 와 `x` 를 쓴다") == []


def test_does_not_extract_paths_endpoints_or_config_keys():
    """SPEC §2 — Java 심볼 인덱스에 대해 구조적으로 바인딩 불가라 분모만 오염시킨다."""
    text = "`src/main/java/Widget.java` 와 `/api/v1/widgets` 와 `widget.retry.max`"
    assert extract_candidates(text) == []


# ---------------------------------------------------------------- 바인딩

def _resolver(table: dict[str, list[tuple[str, str, str]]]):
    return lambda name: table.get(name, [])


def test_unique_match_becomes_an_anchor():
    table = {"WidgetDispatcher": [("WidgetDispatcher", "Widget.java", "h1")]}

    result = bind(["WidgetDispatcher"], _resolver(table))

    assert not result.refusals
    assert result.anchors[0].file_path == "Widget.java"
    assert result.anchors[0].span_hash == "h1"


def test_zero_matches_is_a_recorded_refusal_not_a_dropped_candidate():
    """거부를 버리면 재바인딩이 불가능해지고 수율이 실행 순서를 측정하게 된다 (§3.3)."""
    result = bind(["Nowhere"], _resolver({}))

    assert not result.anchors
    assert result.refusals[0].reason == "unresolved"
    assert result.refusals[0].match_count == 0


def test_ambiguous_match_refuses_and_keeps_the_count():
    """오버로드나 동명이인. 추측해 하나를 고르면 거짓 앵커가 영구히 남는다."""
    table = {"send": [("send", "A.java", "h1"), ("send", "B.java", "h2")]}

    result = bind(["send"], _resolver(table))

    assert not result.anchors
    assert result.refusals[0].reason == "ambiguous"
    assert result.refusals[0].match_count == 2


def test_mixed_batch_splits_cleanly():
    table = {
        "Alpha": [("Alpha", "A.java", "h1")],
        "Beta": [("Beta", "B.java", "h2"), ("Beta", "C.java", "h3")],
    }

    result = bind(["Alpha", "Beta", "Gamma"], _resolver(table))

    assert [a.candidate for a in result.anchors] == ["Alpha"]
    assert {(r.candidate, r.reason) for r in result.refusals} == {
        ("Beta", "ambiguous"), ("Gamma", "unresolved")}


# ---------------------------------------------------------------- 재검사

def test_same_hash_is_fresh():
    assert recheck("h1", [("Widget", "Widget.java", "h1")]) == FRESH


def test_different_hash_is_changed():
    assert recheck("h1", [("Widget", "Widget.java", "h2")]) == CHANGED


def test_missing_symbol_is_orphaned():
    assert recheck("h1", []) == ORPHANED


def test_symbol_that_became_ambiguous_is_retired_not_repointed():
    """바인딩 이후 동명 심볼이 생긴 경우. 다시 겨누면 조용히 다른 것을 가리키게 된다."""
    state = recheck("h1", [("Widget", "A.java", "h1"), ("Widget", "B.java", "h9")])

    assert state == AMBIGUOUS_NOW


def test_moved_file_with_identical_text_stays_fresh():
    """키는 이름이고, 문서가 주장한 것은 텍스트다 (§3.4)."""
    assert recheck("h1", [("Widget", "moved/Widget.java", "h1")]) == FRESH


# ------------------------------------------- 철회된 언급 (취소선)
#
# 취소선의 뜻은 하나가 아니다. 실측(문서 1,396개·취소선 112개)에서 이름 철회는 2개뿐이었고
# 나머지는 위험표·체크리스트의 "해소됨" 표시였다. 그래서 규칙은 **이름만 감싼 취소선**으로
# 좁다. 처음에 문장째 지웠더니 실재하는 메서드로 유일 해소되던 앵커 하나가 사라졌다.


def test_a_struck_through_name_is_not_a_candidate():
    """마크다운 취소선은 철회다. 고친 사람에게 같은 항목을 다시 올리면 목록이 신뢰를 잃는다."""
    text = "예시: `WidgetSearchRequest`, ~~`WidgetPageRequest`~~ ⚠️ 후속 미확인"

    assert extract_candidates(text) == ["WidgetSearchRequest"]


def test_struck_through_text_does_not_swallow_the_rest_of_the_line():
    """비탐욕 매칭이 아니면 취소선 하나가 줄 전체를 지운다."""
    text = "~~`Old`~~ 는 없어졌고 `New` 를 쓰십시오"

    assert extract_candidates(text) == ["New"]


def test_a_name_both_struck_and_live_still_counts():
    """다른 곳에서 여전히 주장되고 있으면 후보다 — 한 번 취소선이 붙었다고 사면되지 않는다."""
    text = "~~`Widget`~~ 였으나, 실제로는 `Widget` 가 여전히 쓰입니다"

    assert extract_candidates(text) == ["Widget"]


def test_unmatched_tildes_do_not_eat_the_document():
    text = "~~ 열렸지만 안 닫힘 `Widget` 계속"

    assert extract_candidates(text) == ["Widget"]


def test_a_struck_sentence_is_a_resolved_concern_not_a_retracted_name():
    """실제 회귀. 위험표에서 취소선은 '이 우려는 해소됐다' 는 뜻이고, 해소된 우려가 부르는
    이름은 **실재한다**. 문장째 지웠다가 유일 해소되던 진짜 앵커 하나를 잃었다.
    """
    text = "| 12.4 ~~`WidgetEvent`에 `widgetId` 미노출~~ | **해소됨** — 게터 확인 |"

    assert extract_candidates(text) == ["WidgetEvent", "widgetId"]


def test_a_struck_sentence_does_not_rescue_a_name_struck_on_its_own():
    """두 규칙이 한 문서에 같이 있어도 서로 간섭하지 않는다."""
    text = "~~`Retired`~~ 삭제됨\n| 3.1 ~~`Live` 미노출~~ | 해소됨 |"

    assert extract_candidates(text) == ["Live"]
