"""claim 후보 — **해석되는 모양**으로 내고, 사람의 일을 예/아니오로 줄인다.

⛔ **왜 있나 (실측 2026-09-03).** 해석기의 문법은 `클래스.필드@애노.속성` 이다
(`index/code_source.py: resolve`). 후보 스크립트는 필드 이름을 빼고 `AdminLoginRequest.@Size.max`
로 내밀고 있었고, 그 값은 **읽히지 않는다**. 소유자가 그대로 받아들였다면 후보 11건 중 5건이
값을 못 읽는 claim 으로 심겼을 것이다. 검토 시트가 함정이면 검토를 안 하느니만 못하다.
"""

from __future__ import annotations

from scripts.claim_candidates import (
    claim_id,
    draft,
    field_after,
    is_limit,
    like_accepted,
    quote_line,
    sites_in,
)

JAVA = """
public class CreatePartyroomRequest {
    @NotBlank
    @Size(max = 30)
    private String title;

    @Size(max = 100)
    private String introduction;

    public static final int MAX_GUESTS = 50;
    public static final int SPIN = compute(3);
}
"""


# ── 애노테이션 자리는 필드를 달고 나온다 ─────────────────────────────────────

def test_an_annotation_site_carries_the_field_name():
    """이것이 그날의 결함이다 — 필드가 없으면 해석기가 못 읽는다."""
    got = {sym for _c, sym, _v in sites_in(JAVA, "CreatePartyroomRequest")}
    assert "title@Size.max" in got and "introduction@Size.max" in got


def test_two_fields_in_one_class_do_not_collapse():
    """필드를 빼면 둘이 한 이름이 되고, 어느 값인지 아무도 못 가른다."""
    vals = {sym: v for _c, sym, v in sites_in(JAVA, "X")}
    assert vals["title@Size.max"] == "30" and vals["introduction@Size.max"] == "100"


def test_a_constant_keeps_its_plain_name():
    assert ("X", "MAX_GUESTS", "50") in sites_in(JAVA, "X")


def test_a_computed_constant_is_not_a_site():
    """문서에서 찾을 수 없는 값은 후보가 아니다."""
    assert not any(sym == "SPIN" for _c, sym, _v in sites_in(JAVA, "X"))


def test_an_annotation_with_no_field_after_it_is_dropped():
    """해석 안 되는 자리를 목록에 올리는 것은 사람에게 함정을 내미는 것이다."""
    assert sites_in("@Size(max = 20)", "X") == []


def test_field_after_skips_further_annotations():
    text = "@Size(max = 5)\n    @NotNull\n    private String nickname;"
    assert field_after(text, text.index(")") + 1) == "nickname"


# ── claim_id ────────────────────────────────────────────────────────────────

def test_claim_id_has_no_at_or_dot():
    got = claim_id("CreatePartyroomRequest", "title@Size.max")
    assert "@" not in got and "." not in got and got.startswith("createpartyroomrequest")


def test_two_fields_get_two_ids():
    assert claim_id("X", "title@Size.max") != claim_id("X", "introduction@Size.max")


# ── 승인된 모양과의 대조 (판정이 아니라 참고) ────────────────────────────────

ACCEPTED = ["CreatePartyroomRequest.title@Size.max", "PartyroomData.MAX_NOTICE_CONTENT_LENGTH"]


def test_a_limit_is_recognised_as_the_accepted_shape():
    assert like_accepted("AdminLoginRequest.username@Size.max", ACCEPTED)


def test_a_tuning_knob_is_not():
    """⛔ 그렇다고 목록에서 빼지는 않는다 — 무엇이 정책인지는 소유자가 정한다(A42)."""
    assert like_accepted("WebSocketConfig.CLIENT_TO_SERVER_HEARTBEAT_MS", ACCEPTED) == ""


def test_is_limit_covers_both_shapes():
    assert is_limit("title@Size.max") and is_limit("MAX_NOTICE_CONTENT_LENGTH")
    assert not is_limit("GUEST_FIXED_ID") and not is_limit("STUCK_BUFFER_MS")


def test_nothing_matches_when_nothing_was_accepted_yet():
    """첫 claim 을 심기 전에도 시트가 돌아야 한다."""
    assert like_accepted("X.title@Size.max", []) == ""


# ── 판단 재료 ────────────────────────────────────────────────────────────────

def test_the_quoted_line_is_the_one_stating_the_value():
    body = "앞줄\n공지는 최대 50자까지 등록 가능\n뒷줄"
    assert quote_line(body, "50") == "공지는 최대 50자까지 등록 가능"


def test_no_quote_when_the_value_is_absent():
    assert quote_line("아무 말", "50") == ""


def test_the_draft_drops_boilerplate_words_from_the_class_name():
    """`Create…Request` 같은 껍데기는 사람이 물을 때 쓰는 낱말이 아니다."""
    concepts, _ = draft("CreatePersonaRequest", "nickname@Size.max", "20")
    assert "Persona" in concepts and not any(w.lower() == "request" for w in concepts)


def test_the_draft_leads_with_the_field():
    concepts, _ = draft("CreatePersonaRequest", "nickname@Size.max", "20")
    assert concepts[0] == "nickname"


def test_the_draft_statement_carries_the_value():
    _, stmt = draft("X", "MAX_NOTICE_CONTENT_LENGTH", "255")
    assert "255" in stmt


# ── 숫자만 겹친 자리를 가른다 ────────────────────────────────────────────────

def test_a_line_that_names_the_constant_counts():
    from scripts.claim_candidates import names_symbol
    assert names_symbol("| `vdj.playlist.self_update.cooldown_seconds` | (예: 1800) |",
                        "SelfUpdateConfig", "DEFAULT_COOLDOWN_SECONDS") is False
    assert names_symbol("MAX_NOTICE_CONTENT_LENGTH 는 255 이다",
                        "PartyroomData", "MAX_NOTICE_CONTENT_LENGTH")


def test_a_coincidental_digit_match_does_not_count():
    """⭐ 이것이 실제 결함이다 — 임베딩 지연 128ms 가 @Size.max 128 의 근거로 실렸다."""
    from scripts.claim_candidates import names_symbol
    assert not names_symbol("임베딩(p50 74 → 128 ms)이고, 이 사이드카는",
                            "AdminLoginRequest", "password@Size.max")


def test_the_field_name_alone_is_enough():
    from scripts.claim_candidates import names_symbol
    assert names_symbol("noticeContent 는 최대 255자", "PartyroomData", "noticeContent@Size.max")


def test_a_short_symbol_is_not_matched_loosely():
    """세 글자 이하는 아무 데나 걸린다 — 이름 대조가 오히려 잡음이 된다."""
    from scripts.claim_candidates import names_symbol
    assert not names_symbol("abc 어쩌고 30", "X", "ttl")


def test_the_quote_prefers_the_line_that_names_the_symbol():
    from scripts.claim_candidates import quote_line
    body = "지연은 128 ms 다\nAdminLoginRequest 의 password 는 128 자"
    assert "password" in quote_line(body, "128", "AdminLoginRequest", "password@Size.max")


def test_the_quote_still_returns_something_when_no_line_names_it():
    """근거가 약하다는 것과 근거가 없다는 것은 다르다 — 사람이 보게 남긴다."""
    from scripts.claim_candidates import quote_line
    assert quote_line("지연은 128 ms 다", "128", "X", "password@Size.max")
