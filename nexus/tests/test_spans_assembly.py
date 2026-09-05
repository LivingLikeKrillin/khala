"""단계 span 조립 — DB 없이 도는 순수 함수만."""
import pytest

from nexus.search.spans import Candidate, SpanSet


def test_leg_span_carries_its_pool_and_names_its_metric():
    spans = SpanSet(max_candidates=100)
    spans.add_leg(
        channel="original", leg="bm25",
        candidates=[Candidate(rank=1, chunk_rid="c1", doc_rid="d1", raw_score=4.7),
                    Candidate(rank=2, chunk_rid="c2", doc_rid="d1", raw_score=0.4)],
    )
    (span,) = spans.spans
    assert span.stage == "leg"
    assert span.score_kind == "ts_rank_cd"      # 경로 이름이 아니라 **지표** 이름
    assert span.n_in is None                    # 질의에는 의미 있는 입력 개수가 없다
    assert span.n_out == 2
    assert span.candidates_expected == 2
    assert span.seq == 1


def test_seq_is_dense_and_a_stage_that_did_not_run_still_writes_a_row():
    spans = SpanSet(max_candidates=100)
    spans.add_leg(channel="original", leg="bm25", candidates=[])
    spans.add_leg(channel="original", leg="vector", candidates=[])
    spans.add_fusion(candidates=[], rrf_k=60, n_channels=1)
    spans.add_diversify(candidates=[], top_k=10, per_doc_cap=5, fired=False)
    assert [s.seq for s in spans.spans] == [1, 2, 3, 4]
    assert spans.spans[-1].fired is False        # 안 돌아도 행은 남는다


def test_truncation_keeps_the_head_and_still_reports_the_full_expectation():
    spans = SpanSet(max_candidates=2)
    spans.add_leg(channel="original", leg="vector",
                  candidates=[Candidate(rank=i, chunk_rid=f"c{i}", doc_rid="d1",
                                        raw_score=float(i)) for i in range(1, 6)])
    (span,) = spans.spans
    assert [c.rank for c in span.candidates] == [1, 2]   # 머리를 남기고 꼬리를 버린다
    assert span.candidates_expected == 5                 # 잘렸다는 사실이 보인다
    assert span.candidates_cap == 2                       # 그때의 상한을 행에 박는다
    assert span.n_out == 5                                # 전체 풀 크기 — candidates 는 잘려도 이건 안 잘린다


def test_misordered_ranks_are_rejected_before_truncation():
    spans = SpanSet(max_candidates=2)
    with pytest.raises(ValueError, match="rank"):
        spans.add_leg(
            channel="original", leg="vector",
            candidates=[Candidate(rank=2, chunk_rid="c2", doc_rid="d1", raw_score=2.0),
                        Candidate(rank=1, chunk_rid="c1", doc_rid="d1", raw_score=1.0)],
        )


def test_gapped_ranks_are_rejected_before_truncation():
    spans = SpanSet(max_candidates=2)
    with pytest.raises(ValueError, match="rank"):
        spans.add_leg(
            channel="original", leg="vector",
            candidates=[Candidate(rank=1, chunk_rid="c1", doc_rid="d1", raw_score=1.0),
                        Candidate(rank=3, chunk_rid="c3", doc_rid="d1", raw_score=3.0)],
        )


def test_diversify_is_exempt_from_the_cap_because_its_cut_rows_are_the_payload():
    spans = SpanSet(max_candidates=2)
    spans.add_diversify(
        candidates=[Candidate(rank=i, chunk_rid=f"c{i}", doc_rid="d1",
                              raw_score=None, dropped=(i > 3)) for i in range(1, 6)],
        top_k=3, per_doc_cap=5,
    )
    (span,) = spans.spans
    assert len(span.candidates) == 5
    assert span.candidates_cap is None
    assert span.n_in == 5
    assert span.n_out == 3          # dropped 가 아닌 것만 나간다


def test_the_answer_stage_has_no_children_and_no_cap():
    spans = SpanSet(max_candidates=100)
    spans.add_answer(n_in=7, n_citations=2, unverified_citations=0,
                     unverified_numbers=0, abstained=False, llm_failed=False)
    (span,) = spans.spans
    assert span.candidates == []
    assert span.candidates_expected == 0
    assert span.candidates_cap is None          # 후보가 없는 단계에 상한은 뜻이 없다
    assert span.n_out is None


def test_detail_rejects_a_non_scalar_before_it_reaches_the_database():
    spans = SpanSet(max_candidates=100)
    with pytest.raises(ValueError, match="scalar"):
        spans.add_packet(candidates=[], n_snippets=0, n_graph_edges=[1, 2])
