"""평가 지표와 판정 규칙 — DB 없이 (SPEC-nexus-korean-retrieval-eval §4.3, §6).

**검정이 결론을 낼 수 없는 상태를 '차이 없음' 이라고 적으면, 지표가 자기 둔감함을 세탁한다.**
그래서 여기서 가장 중요한 테스트는 통과하는 경우가 아니라 `underpowered` 가 뜨는 경우다.
"""

from __future__ import annotations

import pytest

from scripts.ko_eval_harness import (
    ALPHA,
    METRIC_K,
    MIN_DISCORDANT,
    LegResult,
    QueryScore,
    collapse_to_documents,
    outcomes,
    score_query,
    sign_test_p,
    verdict,
)

# ── 청크 → 문서 접기 ─────────────────────────────────────────────────────────


def test_a_document_is_credited_by_its_best_chunk():
    chunk_doc = {"c1": "a.md", "c2": "a.md", "c3": "b.md"}
    assert collapse_to_documents([("c2", 2), ("c1", 1), ("c3", 3)], chunk_doc) == ["a.md", "b.md"]


def test_ten_documents_not_ten_chunks():
    """한 문서가 청크를 여러 개 올려도 창은 문서 10개다 — 두 읽기가 크게 갈리는 자리."""
    chunk_doc = {f"c{i}": ("a.md" if i < 15 else f"d{i}.md") for i in range(30)}
    docs = collapse_to_documents([(f"c{i}", i + 1) for i in range(30)], chunk_doc)
    assert len(docs) == METRIC_K
    assert docs[0] == "a.md"


def test_unknown_chunks_are_ignored():
    assert collapse_to_documents([("ghost", 1), ("c1", 2)], {"c1": "a.md"}) == ["a.md"]


# ── 질의 점수 ────────────────────────────────────────────────────────────────


def test_top_one_scores_full_recall_and_rr():
    s = score_query("q1", ["a.md", "b.md"], ["a.md"])
    assert s.recall == 1.0
    assert s.rr == 1.0
    assert not s.miss


def test_rank_three_gives_one_third_rr():
    s = score_query("q1", ["x.md", "y.md", "a.md"], ["a.md"])
    assert s.rr == pytest.approx(1 / 3)


def test_multi_gold_recall_is_a_fraction():
    s = score_query("q1", ["a.md", "x.md"], ["a.md", "b.md"])
    assert s.recall == 0.5
    assert s.rr == 1.0


def test_nothing_found_is_a_miss():
    s = score_query("q1", ["x.md"], ["a.md"])
    assert s.recall == 0.0
    assert s.miss


def test_a_gold_document_below_the_window_is_a_miss():
    docs = [f"x{i}.md" for i in range(METRIC_K)] + ["a.md"]
    assert score_query("q1", docs, ["a.md"]).miss


def test_an_empty_gold_is_refused_rather_than_scored():
    """답변불가 질의는 분모에 들어가지 않는다 — 0으로 나누거나 미스로 세면 분모가 45가 된다."""
    with pytest.raises(ValueError):
        score_query("q41", ["a.md"], [])


# ── 집계 ─────────────────────────────────────────────────────────────────────


def test_leg_aggregates_are_macro_means():
    leg = LegResult("keyword", [QueryScore("q1", 1.0, 1.0), QueryScore("q2", 0.0, 0.0)])
    assert leg.n == 2
    assert leg.recall == 0.5
    assert leg.mrr == 0.5
    assert leg.misses == 1


def test_stratum_breakdown_counts_within_each_stratum():
    leg = LegResult("keyword", [QueryScore("q1", 1.0, 1.0), QueryScore("q2", 0.0, 0.0),
                                QueryScore("q3", 1.0, 0.5)])
    by = leg.by_stratum({"q1": "loanword", "q2": "loanword", "q3": "spacing"})
    assert by["loanword"]["n"] == 2
    assert by["loanword"]["recall"] == 0.5
    assert by["spacing"]["mrr"] == 0.5


# ── 승패 판정 ────────────────────────────────────────────────────────────────


def test_recall_decides_first():
    a = [QueryScore("q1", 1.0, 0.2)]
    b = [QueryScore("q1", 0.5, 1.0)]
    assert outcomes(a, b) == (1, 0, 0)


def test_mrr_breaks_a_recall_tie():
    """265문서에서 Recall 은 대부분 동점이다. 동점을 버리면 분해가 옮기는 정보를 버린다."""
    a = [QueryScore("q1", 1.0, 1.0)]
    b = [QueryScore("q1", 1.0, 0.25)]
    assert outcomes(a, b) == (1, 0, 0)


def test_an_exact_tie_on_both_is_a_tie():
    a = [QueryScore("q1", 1.0, 0.5)]
    b = [QueryScore("q1", 1.0, 0.5)]
    assert outcomes(a, b) == (0, 0, 1)


# ── 검정 ─────────────────────────────────────────────────────────────────────


def test_six_zero_is_the_smallest_conclusive_split():
    assert sign_test_p(6, 0) == pytest.approx(0.03125, abs=1e-6)
    assert sign_test_p(5, 0) == pytest.approx(0.0625, abs=1e-6)
    assert MIN_DISCORDANT == 6


def test_a_balanced_split_is_not_significant():
    assert sign_test_p(10, 10) == 1.0


def test_too_few_discordant_pairs_reports_underpowered_and_no_p_value():
    v = verdict(4, 1, 35, name_a="nori", name_b="mecab")
    assert v.underpowered
    assert v.p is None
    assert "검정력 부족" in v.decision
    assert "차이 없음" not in v.decision.split("이것은")[0]


def test_an_inconclusive_run_says_so_and_keeps_the_incumbent():
    v = verdict(5, 5, 30, name_a="nori", name_b="mecab")
    assert not v.underpowered
    assert v.p is not None and v.p >= ALPHA
    assert "차이 없음" in v.decision
    assert "mecab" in v.decision


def test_a_clear_win_names_the_winner():
    v = verdict(9, 1, 30, name_a="nori", name_b="mecab")
    assert not v.underpowered
    assert v.p < ALPHA
    assert "nori" in v.decision


def test_a_clear_loss_names_the_incumbent_as_ahead():
    v = verdict(1, 9, 30, name_a="nori", name_b="mecab")
    assert v.p < ALPHA
    assert "mecab 우세" in v.decision
