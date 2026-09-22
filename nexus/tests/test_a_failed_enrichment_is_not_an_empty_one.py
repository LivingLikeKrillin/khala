"""보강이 **터진 것**과 **채울 것이 없던 것**이 다른 값으로 나온다.

⛔ **왜 생겼나 (2026-09-22).** 보강 패스 셋(`section_fill` · `corrections` · `pairs`)이 전부
실패를 삼키고 **빈 목록**을 돌려줬다. 정책은 맞다 — 보강이 죽었다고 검색 결과까지 버리면
있던 답도 못 준다. 틀린 것은 그 뒤다: **그 다음부터 「터졌다」와 「없었다」가 같은 값**이었다.
응답에도, 단계 기록에도, 부른 쪽에도.

⭐ **같은 파일이 같은 구분을 이미 하고 있었다.** `_vector_leg` 머리말은 *"빈 결과와 죽은
경로를 구분해서 돌려준다"* 이고 실제로 3-튜플을 돌려준다. `add_section_fill` 의 `fired` 는
*"이 단계가 아예 꺼져 있었다"* 와 *"켜져 있었는데 후보가 0 이었다"* 를 가른다.
**셋째 경우(켜졌고 터졌다)만 빠져 있었다.**

⚠ **이 부류는 조용하다.** 값이 안 나오는 것이 아니라 **그럴듯한 값**이 나온다. 그래서 검사는
「실패했을 때 무엇이 나오는가」를 직접 단언해야 하고, 그 단언은 **실패를 일부러 만들어서만**
쓸 수 있다.
"""

from __future__ import annotations

import pytest

from nexus.search import hybrid, pairs, reconcile
from nexus.search.spans import SpanSet


def _boom(*a, **k):
    raise RuntimeError("보강 쪽 DB 가 죽었다")


# ── ① section_fill ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_dead_section_fill_does_not_look_like_an_empty_one(monkeypatch):
    """⛔ 둘 다 빈 목록이다. 가르는 것은 **둘째 값**이다.

    실패를 **DB 조회 자리**에서 낸다 — 그것이 이 패스가 실제로 죽는 자리다.
    """
    import nexus.search.section_fill as sf

    monkeypatch.setattr(sf, "saturated_docs", lambda hits, cap: ["doc_1"])

    async def empty_fill(*a, **k):
        return []

    monkeypatch.setattr(sf, "fill_for_docs", empty_fill)
    monkeypatch.setattr(sf, "hit_sections", lambda hits: [])
    hits, failed = await hybrid._fill_sections([], "t", "INTERNAL", 5)
    assert (hits, failed) == ([], False), "채울 것이 없었는데 터졌다고 한다"

    monkeypatch.setattr(sf, "fill_for_docs", _boom)
    hits, failed = await hybrid._fill_sections([], "t", "INTERNAL", 5)
    assert hits == [] and failed is True, "터졌는데 「없었다」와 같은 값이 나온다"


@pytest.mark.asyncio
async def test_the_search_result_carries_the_failure(monkeypatch):
    """부른 쪽이 **결과 객체만 보고** 알 수 있어야 한다 — 로그는 부른 쪽이 아니다."""
    async def spy_bm25(query, *a, **k):
        return [], None

    async def no_enrich(fused, tenant, max_snippet_chars=300):
        return []

    async def dead_fill(*a, **k):
        return [], True

    monkeypatch.setattr(hybrid, "_bm25_search", spy_bm25)
    monkeypatch.setattr(hybrid, "_enrich_hits", no_enrich)
    monkeypatch.setattr(hybrid, "_fill_sections", dead_fill)

    r = await hybrid.hybrid_search("질의", tenant="t", clearance="INTERNAL",
                                   route="keyword_only",
                                   config={"search": {"section_fill": True}})
    assert r.enrichment_failed == ["section_fill"], \
        "보강이 터진 것이 결과 객체에 안 실린다"
    assert r.degraded == [], \
        "보강 실패를 경로 degrade 로 적었다 — `LEGS` 가 그 칸의 정본이다"


@pytest.mark.asyncio
async def test_the_stage_record_tells_all_three_cases(monkeypatch):
    """⭐ `fired` 가 둘을, `detail.failed` 가 셋째를 가른다."""
    async def spy_bm25(query, *a, **k):
        return [], None

    async def no_enrich(fused, tenant, max_snippet_chars=300):
        return []

    monkeypatch.setattr(hybrid, "_bm25_search", spy_bm25)
    monkeypatch.setattr(hybrid, "_enrich_hits", no_enrich)

    def _fill_span(spans: SpanSet):
        return next(s for s in spans.spans if s.stage == "section_fill")

    cfg_on = {"search": {"section_fill": True}, "spans": {"enabled": True}}
    cfg_off = {"search": {"section_fill": False}, "spans": {"enabled": True}}

    r = await hybrid.hybrid_search("질의", tenant="t", clearance="INTERNAL",
                                   route="keyword_only", config=cfg_off)
    off = _fill_span(r.spans)

    async def quiet_fill(*a, **k):
        return [], False

    monkeypatch.setattr(hybrid, "_fill_sections", quiet_fill)
    r = await hybrid.hybrid_search("질의", tenant="t", clearance="INTERNAL",
                                   route="keyword_only", config=cfg_on)
    nothing = _fill_span(r.spans)

    async def dead_fill(*a, **k):
        return [], True

    monkeypatch.setattr(hybrid, "_fill_sections", dead_fill)
    r = await hybrid.hybrid_search("질의", tenant="t", clearance="INTERNAL",
                                   route="keyword_only", config=cfg_on)
    boom = _fill_span(r.spans)

    assert off.fired is False
    assert nothing.fired is True and nothing.detail["failed"] is False
    assert boom.fired is True and boom.detail["failed"] is True
    # 세 경우가 **후보 수로는 전부 같다** — 그것이 이 칸이 필요한 이유다.
    assert off.n_out == nothing.n_out == boom.n_out == 0


# ── ② corrections ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_dead_correction_pass_is_named():
    """정정을 **못 물어본 것**과 정정이 **없는 것**은 답변에 정반대 뜻이다."""
    class _Hit:
        rid = "chunk_1"
        chunk_text = "MemberService 의 정원 규칙은 이 문서에 적혀 있다"

    async def dead_search(*a, **k):
        raise RuntimeError("중첩 검색이 죽었다")

    failed: list = []
    out = await reconcile.corrections_for([_Hit()], "t", "INTERNAL",
                                          search=dead_search, failed=failed)
    assert out == []
    assert failed == ["corrections"], "터진 정정 패스가 이름을 안 남긴다"

    quiet: list = []
    await reconcile.corrections_for([], "t", "INTERNAL", search=dead_search, failed=quiet)
    assert quiet == [], "부를 일이 없었는데 터졌다고 적었다"


# ── ③ pairs ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_dead_pair_expansion_is_named(monkeypatch):
    """`[]` 하나로 「짝이 없다」와 「짝을 못 봤다」를 둘 다 말하지 않는다."""
    class _Hit:
        rid = "chunk_1"
        doc_rid = "doc_1"

    monkeypatch.setattr(pairs.db, "fetch_all", _boom)
    failed: list = []
    out = await pairs.paired_chunks([_Hit()], "t", "INTERNAL", failed=failed)
    assert out == []
    assert failed == ["pairs"], "터진 짝 확장이 이름을 안 남긴다"


# ── 배선: 답변 경로가 그 자리를 실제로 넘기는가 ───────────────────────────────

#: 이 이음매가 부르는 보강 함수들. **새것을 더하면 여기 이름을 적는다.**
#:
#: ⛔ **앞 판은 `== 2` 라는 상수로 셌다 (고침 2026-09-23).** 보강이 셋이 되자 그 검사가
#: 빨개졌고, **고치는 방법이 「수를 3 으로 올린다」**였다 — 그러면 검사가 확인이 아니라
#: **갱신**이 된다. 다음 사람은 보지도 않고 올린다. 이름을 적게 하면 **적으면서 보게 된다.**
SEAM_ENRICHMENTS = ("corrections_for", "paired_chunks", "referenced_chunks")


def test_the_answer_seam_hands_them_the_result_slot():
    """⛔ **함수가 옳은 것과 부르는 쪽이 넘기는 것은 다른 사실이다.**

    `failed=` 를 안 넘기면 그 패스는 오늘과 똑같이 조용하다. 그리고 그 자리는 `result` 여야
    한다 — 표면마다 따로 받으면 하나가 잊고, 그 조합은 검사가 초록인 채로 틀린다
    (`packet_for_answer` 가 제외 목록을 인자로 안 받는 것과 같은 이유).
    """
    import inspect

    src = inspect.getsource(reconcile.packet_for_answer)

    for name in SEAM_ENRICHMENTS:
        assert f"{name}(" in src, f"{name} 이 이 이음매에서 안 불린다 — 목록이 낡았다"
    assert src.count("failed=result.enrichment_failed") == len(SEAM_ENRICHMENTS), \
        "보강 패스 중 하나가 터진 것을 못 남긴다"


def test_every_enrichment_the_seam_calls_is_on_the_list():
    """⛔ **목록이 진짜 대조가 되려면 반대쪽도 봐야 한다.**

    이름을 적는 규칙은 **안 적으면 그만**이다. 이 단언이 그 구멍을 막는다 — 이음매가
    `search.*` 에서 끌어다 쓰는 보강 함수는 전부 위 목록에 있어야 한다.
    """
    import inspect
    import re

    src = inspect.getsource(reconcile.packet_for_answer)
    imported = set(re.findall(r"from nexus\.search\.\w+ import (\w+)", src))
    # `assemble_packet` 은 보강이 아니라 조립이고, `code_values_for` 는 이 모듈 것이다.
    enrichments = imported - {"assemble_packet", "SearchHit", "_truncate_snippet"}

    assert enrichments <= set(SEAM_ENRICHMENTS), \
        f"목록에 없는 보강이 이음매에 있다: {sorted(enrichments - set(SEAM_ENRICHMENTS))}"
