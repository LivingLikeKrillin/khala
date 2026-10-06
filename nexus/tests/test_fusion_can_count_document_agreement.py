"""융합이 **문서 일치**를 셀 수 있다 — 사전 등록 F1, 요청 필드 `fusion_doc_agreement`(기본 비활성화).

⛔ **왜 (2026-10-01).** R01(`search_log` 1823)에서 SOP-01 은 네 경로 중 **셋**이 찾았는데 짚은
절이 갈렸다(원문 벡터 §5 9위 · 식별자 BM25 §2 22위 · 식별자 벡터 §6 8위). RRF 는 **청크 단위**로
합하므로 셋의 기여가 한 청크에 모이지 않았고, 가장 높은 §5 가 26위에서 컷오프 20 에 잘렸다
(`docs/FUSION_DOCUMENT_AGREEMENT_PREREGISTRATION.md` §1). 같은 메커니즘이 09-20 사례 D 에도 있었다.

F1 의 정의(사전 등록 §2 그대로):

    문서 점수 = Σ_경로 w · 1/(k + 그 경로에서 그 문서의 가장 높은 청크 순위 + 1)
    청크 최종 점수 = 청크 RRF + 그 청크의 문서 점수

경로마다 **문서의 최고 청크 하나만** 센다 — 청크가 많은 긴 문서가 청크 수로 오르지 않게.

⚠ **이것은 처치이고 판정이 아니다.** 이 파일이 지키는 것은 켜질 때만 켜지고, 꺼졌을 때 오늘과
**비트까지** 같은 것, 그리고 켰다는 사실이 결과 · 응답 · 기록까지 가는 것이다. 값이 좋은지는
소비자의 골든셋과 이쪽 회귀가 정한다(사전 등록 §4).
"""

from __future__ import annotations

import pathlib

import pytest

from nexus.search import hybrid
from nexus.search.hybrid import ChannelResults, LegHit, QueryChannel, SearchHit, fuse_channels

K = 60


def _rrf(w: float, rank: int) -> float:
    """이 리포의 RRF 항 — `fuse_channels` 와 같은 꼴(순위는 1부터, 분모에 +1)."""
    return w * (1.0 / (K + rank + 1))


#: R01 의 모양 그대로(사전 등록 §1 표). x1 은 한 경로가 1위로 찾은 **다른 문서**다.
R01 = [
    ChannelResults(bm25=[("x1", 1)], vector=[("a5", 9), ("a1", 19)], weight=1.0, name="original"),
    ChannelResults(bm25=[("a2", 22)], vector=[("a6", 8), ("a2", 17)], weight=0.5,
                   name="identifier"),
]
DOC = {"x1": "doc_x", "a1": "doc_sop", "a2": "doc_sop", "a5": "doc_sop", "a6": "doc_sop"}


def _scores(fused) -> dict[str, float]:
    return {f["rid"]: f["score"] for f in fused}


# ── 순수: 점수 ────────────────────────────────────────────────────────────────

def test_off_the_scores_are_today_s_to_the_bit():
    """⭐ **대조군.** 안 주면 오늘의 가중 RRF 다 — 값이 비트까지 같아야 T0 가 T0 다."""
    today = _scores(fuse_channels(R01, K))

    assert today == _scores(fuse_channels(R01, K, doc_of=None))
    assert today["a5"] == _rrf(1.0, 9)
    assert today["a2"] == _rrf(0.5, 22) + _rrf(0.5, 17)
    assert today["x1"] == _rrf(1.0, 1)


def test_a_chunk_gets_its_own_rrf_plus_its_document_s_agreement():
    on = _scores(fuse_channels(R01, K, doc_of=DOC))

    # 문서 SOP: 원문 BM25 없음 · 원문 벡터 최고 9(a5) · 식별자 BM25 최고 22(a2) · 식별자 벡터 최고 8(a6)
    sop = _rrf(1.0, 9) + _rrf(0.5, 22) + _rrf(0.5, 8)
    assert on["a5"] == pytest.approx(_rrf(1.0, 9) + sop, abs=1e-15)
    assert on["a2"] == pytest.approx(_rrf(0.5, 22) + _rrf(0.5, 17) + sop, abs=1e-15)
    assert on["x1"] == pytest.approx(_rrf(1.0, 1) + _rrf(1.0, 1), abs=1e-15)


def test_a_document_counts_once_per_path_not_once_per_chunk():
    """청크가 다섯인 문서가 한 경로에서 다섯 번 세면 긴 문서가 청크 수로 이긴다."""
    one_leg = [ChannelResults(bm25=[(f"c{i}", i) for i in range(1, 6)], weight=1.0)]
    on = _scores(fuse_channels(one_leg, K, doc_of={f"c{i}": "doc_c" for i in range(1, 6)}))

    assert on["c3"] == pytest.approx(_rrf(1.0, 3) + _rrf(1.0, 1), abs=1e-15)


def test_the_r01_shape_turns_over():
    """세 경로가 다른 절로 짚은 문서가 한 경로가 1위로 짚은 문서를 넘는다 — 메커니즘이 겨누는 자리."""
    today = [f["rid"] for f in fuse_channels(R01, K)]
    on = [f["rid"] for f in fuse_channels(R01, K, doc_of=DOC)]

    assert today.index("x1") < today.index("a5"), "대조군이 R01 모양이 아니다"
    assert on.index("a5") < on.index("x1")


def test_a_chunk_without_a_document_is_an_error_not_a_silent_zero():
    """⛔ 모르면 0 을 더하는 것은 「합의 없음」과 같은 값이다 — 터진 것을 빈 것으로 두지 않는다."""
    with pytest.raises(KeyError):
        fuse_channels(R01, K, doc_of={"x1": "doc_x"})


# ── 검색 함수: 켜야 켜지고, 결과가 그 사실을 들고 나온다 ───────────────────────

_LEGS = {
    # 원문: 다른 문서 B 가 1위, 문서 A 의 a5 가 2위
    "질의": [LegHit("b1", 1, "doc_b", 3.0), LegHit("a5", 2, "doc_a", 2.0)],
    # 식별자: 문서 A 의 **다른 청크** 둘
    "ID_TOKEN": [LegHit("a2", 1, "doc_a", 1.5), LegHit("a6", 2, "doc_a", 1.0)],
}
_DOC_OF = {h.rid: h.doc_rid for hits in _LEGS.values() for h in hits}


@pytest.fixture
def stub_legs(monkeypatch):
    async def bm25(query, *a, **k):
        return list(_LEGS[query]), None

    async def enrich(fused, tenant, max_snippet_chars=300):
        return [SearchHit(rid=f["rid"], doc_rid=_DOC_OF[f["rid"]], score=f["score"])
                for f in fused]

    monkeypatch.setattr(hybrid, "_bm25_search", bm25)
    monkeypatch.setattr(hybrid, "_enrich_hits", enrich)


async def _search(**kw):
    return await hybrid.hybrid_search(
        "질의", tenant="t", clearance="INTERNAL", route="keyword_only", top_k=1,
        config={"search": {"diversity_per_doc_cap": 5}, "spans": {"enabled": True}},
        channels=[QueryChannel("질의", 1.0, "original"),
                  QueryChannel("ID_TOKEN", hybrid.IDENTIFIER_CHANNEL_WEIGHT, "identifier")],
        **kw)


def _fusion_detail(result) -> dict:
    (span,) = [s for s in result.spans.spans if s.stage == "fusion"]
    return span.detail


@pytest.mark.asyncio
async def test_off_by_default_the_search_is_today_s(stub_legs):
    default = await _search()
    asked_off = await _search(fusion_doc_agreement=False)

    assert [(h.rid, h.score) for h in default.hits] == [(h.rid, h.score) for h in asked_off.hits]
    assert [h.rid for h in default.hits] == ["b1"], "대조군: 오늘은 한 경로 1위 문서가 이긴다"
    assert default.fusion_doc_agreement is False
    assert _fusion_detail(default)["doc_agreement"] is False


@pytest.mark.asyncio
async def test_on_the_document_two_paths_agree_on_wins_and_the_result_says_so(stub_legs):
    """⛔ **켰다는 사실이 결과 객체에 실려야 한다** — 평가 하네스 · span 기록은 요청을 못 본다.

    `identifier_channel_asked` 가 선언만 된 채 회귀 측정에 쓰여 80건이 「안 켰음」으로
    적힌 적이 있다(2026-09-20). 그래서 제품을 돌리고 결과 객체를 읽는다.
    """
    on = await _search(fusion_doc_agreement=True)

    assert [h.rid for h in on.hits] == ["a5"]
    assert on.fusion_doc_agreement is True
    assert _fusion_detail(on)["doc_agreement"] is True


# ── 와이어링: 요청 필드 → 검색 → 응답 · 기록 ───────────────────────────────────────

def test_the_flag_is_an_answer_request_field_and_off_by_default():
    from nexus.api import AnswerRequest, SearchRequest

    assert AnswerRequest(query="q").fusion_doc_agreement is False
    assert "fusion_doc_agreement" not in SearchRequest.model_fields


def test_the_answer_paths_hand_the_flag_to_the_search_and_echo_it():
    """답변 경로 둘이 같은 식으로 넘기고 같은 식으로 돌려준다 — 둘이 갈릴 자리가 없게.

    `identifier_channel` 과 같은 규칙이다(`test_identifier_channel.py` 끝의 검사 참조).
    """
    from nexus import api

    src = pathlib.Path(api.__file__).read_text(encoding="utf-8")
    assert src.count("fusion_doc_agreement=req.fusion_doc_agreement") == 2, \
        "답변 경로 둘이 검색에 「켰는가」를 안 넘긴다 — 결과 객체가 조용히 `False` 가 된다"
    assert src.count('"fusion_doc_agreement": req.fusion_doc_agreement,') == 2, \
        "응답 둘이 같은 식을 안 읽는다"


def test_the_record_carries_what_the_search_did():
    """기록에는 **결과가 한 것**을 남긴다. 필드가 없는 결과(옛 대역)는 None — 모른다이지 꺼짐이 아니다."""
    from nexus.search.hybrid import SearchResult
    from nexus.search.signals import extract_signals

    def _sig(result):
        return extract_signals(result, None, path="search_answer", tenant="t",
                               clearance="INTERNAL", query="q")

    on, off = SearchResult(), SearchResult()
    on.fusion_doc_agreement = True

    class _OldDouble:
        hits, graph, route_used = [], None, ""

    assert _sig(on).fusion_doc_agreement is True
    assert _sig(off).fusion_doc_agreement is False
    assert _sig(_OldDouble()).fusion_doc_agreement is None
