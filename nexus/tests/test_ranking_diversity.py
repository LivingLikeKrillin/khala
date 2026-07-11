"""문서 다양성(per-doc cap) — SPEC-nexus-ranking-precision §6.

_diversify 는 순수 함수: RRF 순서의 hits 를 문서별 상한으로 재정렬하되, 문서가 부족하면 채워서
항상 min(top_k, len(hits)) 개를 돌려준다(recall 안전). LLM·DB 없이 검증한다.
"""

from __future__ import annotations

from nexus.search.hybrid import SearchHit, _diversify


def _h(rid, doc, score=0.0):
    return SearchHit(rid=rid, doc_rid=doc, score=score)


def _rids(hits):
    return [h.rid for h in hits]


def test_single_document_returns_first_top_k_in_order():
    hits = [_h(f"c{i}", "docA") for i in range(5)]
    out = _diversify(hits, top_k=3, per_doc_cap=3)
    assert _rids(out) == ["c0", "c1", "c2"]           # 순서 보존, top_k 컷


def test_one_document_does_not_flood_when_others_exist():
    # RRF 순서: A 가 앞을 도배, 뒤에 B·C
    hits = [_h("a0", "A"), _h("a1", "A"), _h("a2", "A"), _h("a3", "A"),
            _h("b0", "B"), _h("c0", "C")]
    out = _diversify(hits, top_k=4, per_doc_cap=2)
    docs = [h.doc_rid for h in out]
    assert docs.count("A") <= 2                        # 상한 준수
    assert "B" in docs and "C" in docs                 # 다른 문서가 자리 확보
    assert len(out) == 4


def test_fill_path_restores_count_when_few_docs():
    # 문서 2개뿐 → cap 으로는 top_k 를 못 채움 → 채워서 count 복구
    hits = [_h("a0", "A"), _h("a1", "A"), _h("a2", "A"), _h("b0", "B")]
    out = _diversify(hits, top_k=4, per_doc_cap=2)
    assert len(out) == 4                               # under-fill 아님
    assert _rids(out) == ["a0", "a1", "b0", "a2"]      # cap 후 skip된 a2 를 뒤에 채움


def test_within_document_order_preserved():
    hits = [_h("a0", "A"), _h("b0", "B"), _h("a1", "A"), _h("a2", "A")]
    out = _diversify(hits, top_k=4, per_doc_cap=3)
    a_order = [h.rid for h in out if h.doc_rid == "A"]
    assert a_order == ["a0", "a1", "a2"]               # 문서 내부는 RRF 순서 유지


def test_never_more_than_available_and_never_empty_nonempty():
    hits = [_h("a0", "A"), _h("b0", "B")]
    out = _diversify(hits, top_k=10, per_doc_cap=1)
    assert len(out) == 2                               # min(top_k, len(hits))
    assert _diversify([], top_k=5, per_doc_cap=3) == []
