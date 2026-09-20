"""가르는 낱말 하나에 **자기 채널**을 준다 (사전 등록 T2).

⛔ **왜 생겼나 (실측 2026-09-20, 소비자 실행 열 건).** 사건 번들 질의에서 맞는 절차 문서만
근거에 안 왔다. 기록을 읽으니 기제가 셋이었다 — 융합이 한 경로짜리를 떨어뜨리고, 벡터가
여섯 절차 문서를 안 가르고, 키워드는 **걸었는데 묻힌다**:

    'failureClass=LOCALIZATION_LOST' → ['failureclass','localization','lost']  (OR)

`lost` 는 여섯 적용 범위 표에 전부 있고, 2,000글자 질의면 가르는 항 하나가 수백 중 하나다.
⭐ 같은 토큰을 **단독으로** 던지면 맞는 문서가 5~6위로 온다 — 끊긴 곳이 없고 묻힐 뿐이다.

⚠ **이것은 처치이고 판정이 아니다.** 켜고 끈 두 실험군을 소비자가 자기 골든셋으로 돌려야
값이 나온다 (`docs/PROCEDURE_RETRIEVAL_PREREGISTRATION.md`). 이 파일이 지키는 것은 **처치가
켜질 때만 켜지고, 꺼졌을 때 오늘과 같은 것**뿐이다.
"""

from __future__ import annotations

import pytest

from nexus.search.identifiers import (
    MAX_IDENTIFIERS,
    extract_identifiers,
    identifier_query,
)


# ── 순수: 무엇을 식별자로 보나 ────────────────────────────────────────────────

def test_it_takes_the_class_tokens_an_incident_bundle_carries():
    q = ("작업 단위 U-4417 이 failureClass=PAYLOAD_LOST 로 종료되었고 "
         "observedHold=HOLD_KIND_EMPTY 이며 expectedHold=HOLD_KIND_PART 였다.")
    assert extract_identifiers(q) == ("PAYLOAD_LOST", "HOLD_KIND_EMPTY", "HOLD_KIND_PART")


def test_a_bare_acronym_is_not_an_identifier():
    """⛔ 밑줄을 요구하는 것이 이 규칙의 전부다.

    약어까지 받으면 산문에 흔한 대문자 낱말이 전부 들어와, 이 채널이 *"대문자가 있는가"* 를
    묻게 된다 — 그러면 가르는 힘이 사라지고 원문을 두 번 묻는 것과 같아진다.
    """
    assert extract_identifiers("API 와 SOP 와 HTTP 를 쓴다") == ()
    assert extract_identifiers("UNVERIFIED 상태") == ()


def test_order_is_first_seen_and_duplicates_collapse():
    """정렬하지 않는다 — 이 값이 그대로 응답에 나가는데, 정렬하면 보낸 것과 쓴 것이 달라 보인다."""
    q = "PAYLOAD_LOST 뒤에 HOLD_KIND_EMPTY 가 오고 다시 PAYLOAD_LOST 가 온다"
    assert extract_identifiers(q) == ("PAYLOAD_LOST", "HOLD_KIND_EMPTY")


def test_digits_belong_to_an_identifier():
    """`X_FIXTURE_E4412` 같은 정지 코드도 같은 모양이다."""
    assert extract_identifiers("코드 X_FIXTURE_E4412 가 떴다") == ("X_FIXTURE_E4412",)


def test_a_very_long_list_is_cut():
    q = " ".join(f"AAA_{i}" for i in range(MAX_IDENTIFIERS + 8))
    assert len(extract_identifiers(q)) == MAX_IDENTIFIERS


@pytest.mark.parametrize("q", ["", "   ", "식별자가 없는 한국어 질문입니다", "lower_case_words"])
def test_a_query_without_identifiers_yields_an_empty_second_query(q):
    """⛔ **빈 문자열이지 원문이 아니다.**

    원문을 돌려주면 같은 질의를 두 채널로 묻게 되고, 가중 합산은 모든 문서에 같은 배수를
    곱할 뿐 순서를 안 바꾼다 — 경로만 두 배로 돌고 절대 점수가 팽창한다.
    """
    assert extract_identifiers(q) == ()
    assert identifier_query(q) == ""


def test_the_second_query_is_only_the_identifiers():
    q = "작업 단위가 failureClass=PAYLOAD_LOST 로 끝났고 운영자가 무엇을 해야 하는가"
    assert identifier_query(q) == "PAYLOAD_LOST"


# ── 채널 이름 — 이 변경이 건드린 회귀 자리 ────────────────────────────────────

def test_the_legacy_pair_keeps_the_names_already_in_the_record():
    """⚠ 튜플 둘로 오던 옛 계약의 라벨은 **글자 그대로** 보존한다.

    그 이름이 이미 `search_span.channel` 에 쌓여 있다. 여기서 바꾸면 지나간 기록과 앞으로의
    기록이 같은 이름으로 다른 것을 가리킨다.
    """
    from nexus.search.hybrid import normalize_channels

    got = normalize_channels([("다시 쓴 질의", 1.3), ("원문", 0.5)], "원문")
    assert [c.name for c in got] == ["rewritten", "original"]
    assert [c.weight for c in got] == [1.3, 0.5]


def test_no_channels_means_one_unnamed_channel_as_today():
    from nexus.search.hybrid import normalize_channels

    got = normalize_channels(None, "질의")
    assert len(got) == 1 and got[0].text == "질의" and got[0].name == ""


def test_a_named_channel_keeps_its_own_name():
    """⛔ **이 검사가 없었으면 이번 변경이 기록을 오염시켰다.**

    예전에는 이름이 위치로 붙었다 — `["rewritten","original"] if len(active) > 1`. 재작성이
    없는데 채널 하나가 더 붙으면 **사용자 질의가 `rewritten` 으로, 새 채널이 `original` 로**
    기록됐을 것이다.
    """
    from nexus.search.hybrid import QueryChannel, normalize_channels

    got = normalize_channels(
        [QueryChannel("원문", 1.0, "original"), QueryChannel("PAYLOAD_LOST", 0.5, "identifier")],
        "원문")
    assert [c.name for c in got] == ["original", "identifier"], \
        "채널이 자기 이름을 못 들고 간다 — 진단 기록이 엉뚱한 이름으로 쌓인다"


def test_a_third_channel_does_not_steal_the_first_two_names():
    from nexus.search.hybrid import QueryChannel, normalize_channels

    got = normalize_channels([QueryChannel("A", 1.3, "rewritten"),
                              QueryChannel("B", 0.5, "original"),
                              QueryChannel("C", 0.5, "identifier")], "A")
    assert [c.name for c in got] == ["rewritten", "original", "identifier"]


# ── 배선: 켜야 켜지고, 꺼지면 오늘과 같다 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_off_by_default_runs_exactly_one_channel(monkeypatch):
    """⭐ **대조군.** 안 켜면 채널이 하나다 — 오늘과 같은 경로, 같은 SQL."""
    from nexus.search import hybrid

    seen: list[str] = []

    async def spy_bm25(query, *a, **k):
        seen.append(query)
        return [], None

    async def no_enrich(fused, tenant, max_snippet_chars=300):
        return []

    monkeypatch.setattr(hybrid, "_bm25_search", spy_bm25)
    monkeypatch.setattr(hybrid, "_enrich_hits", no_enrich)

    r = await hybrid.hybrid_search("failureClass=PAYLOAD_LOST 무엇을 하나",
                                   tenant="t", clearance="INTERNAL", route="keyword_only")
    assert seen == ["failureClass=PAYLOAD_LOST 무엇을 하나"], \
        f"안 켰는데 채널이 늘었다: {seen}"
    assert r.identifier_channel == []


@pytest.mark.asyncio
async def test_asked_but_no_identifier_does_not_fire(monkeypatch):
    """⛔ **음성 대조군** (사전 등록 §5.5).

    식별자가 없는 질의에서 이 채널이 발화하면, 그것은 *"식별자를 따로 묻는다"* 가 아니라
    *"같은 질의를 두 번 묻는다"* 다. 발화 여부를 안 보고 「차이 없음」을 적으면 스위치가
    조용히 무시된 것과 구별되지 않는다 — 이 리포가 이미 한 번 겪었다.
    """
    from nexus.search.hybrid import IDENTIFIER_CHANNEL_WEIGHT, QueryChannel
    from nexus.search.identifiers import identifier_query

    assert identifier_query("식별자가 없는 한국어 질문") == ""
    # 채널을 만드는 쪽(api._search_channels)의 규칙을 그대로 적는다: 빈 문자열이면 안 붙인다.
    ident = identifier_query("식별자가 없는 한국어 질문")
    chans = [QueryChannel("질의", 1.0, "original")]
    if ident:
        chans.append(QueryChannel(ident, IDENTIFIER_CHANNEL_WEIGHT, "identifier"))
    assert len(chans) == 1, "식별자가 없는데 둘째 채널이 붙었다"


@pytest.mark.asyncio
async def test_when_it_fires_the_second_channel_carries_only_identifiers(monkeypatch):
    """켜지면 둘째 채널의 질의는 **식별자만**이고, 결과가 그 사실을 들고 나온다."""
    from nexus.search import hybrid

    seen: list[str] = []

    async def spy_bm25(query, *a, **k):
        seen.append(query)
        return [], None

    async def no_enrich(fused, tenant, max_snippet_chars=300):
        return []

    monkeypatch.setattr(hybrid, "_bm25_search", spy_bm25)
    monkeypatch.setattr(hybrid, "_enrich_hits", no_enrich)

    q = "failureClass=PAYLOAD_LOST 이고 observedHold=HOLD_KIND_EMPTY 다. 무엇을 하나"
    r = await hybrid.hybrid_search(
        q, tenant="t", clearance="INTERNAL", route="keyword_only",
        channels=[hybrid.QueryChannel(q, 1.0, "original"),
                  hybrid.QueryChannel("PAYLOAD_LOST HOLD_KIND_EMPTY",
                                      hybrid.IDENTIFIER_CHANNEL_WEIGHT, "identifier")])
    assert seen == [q, "PAYLOAD_LOST HOLD_KIND_EMPTY"], f"채널 질의가 다르다: {seen}"
    assert r.identifier_channel == ["PAYLOAD_LOST", "HOLD_KIND_EMPTY"], \
        "발화한 것을 호출자가 못 본다"


def test_the_weight_is_below_the_original_channel():
    """⛔ 이 채널은 정밀도가 높고 재현율이 낮다. 원문과 같은 가중을 주면 분류 이름을 나열한
    목차 성격의 문서가 융합을 지배한다."""
    from nexus.search.hybrid import IDENTIFIER_CHANNEL_WEIGHT

    assert 0 < IDENTIFIER_CHANNEL_WEIGHT < 1.0
