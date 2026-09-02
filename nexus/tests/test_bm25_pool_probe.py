"""BM25 후보 풀 프로브의 **판정 규칙** — `docs/BM25_POOL_PREREGISTRATION.md` §5.

규칙이 코드에만 있고 검사가 없으면 결과를 본 뒤에 조용히 바뀐다. 여기 검사는 §5 의 일곱 조항을
하나씩 걸고, **막아야 할 것이 막히는지**를 같이 건다.

⭐ 이 판에서 새로 생긴 조항은 §5.2 **기제 대조군**이다. 앞 사전 등록은 *동률*을 "기제가 아니다"
로 읽었는데 동률은 *안 돎*과 *돌지만 쓸모없음*을 한꺼번에 뜻했다. 여기서는 정답 청크가 그
실험군의 BM25 풀에 **실제로 들어왔는가**를 직접 본다.
"""

from __future__ import annotations

from scripts.bm25_pool_probe import COST_CEILING, cost_delta, determinism, totals, verdict


def _arm(name, pool, multihop, policy, chars=1000, ms=200, entered=True):
    return {"arm": name, "bm25_top_k": pool, "median_chars": chars, "median_ms": ms,
            "chunk_entered_pool": entered,
            "multihop": {"covered": multihop, "n": 4}, "policy": {"covered": policy, "n": 8}}


def _arms(*rest):
    return [_arm("base", 20, 2, 8, entered=False), *rest]


# ── §5.1 결정론 대조군 ───────────────────────────────────────────────────────

def test_a_drifting_base_stops_before_any_verdict():
    v = verdict(_arms(_arm("pool-25", 25, 4, 8)), ["m01"], 5.0)
    assert v["stopped_at"].startswith("§5.1") and v["adopt"] is None


def test_determinism_names_only_the_queries_that_moved():
    a = {"rows": [{"qid": "m01", "text_sha256": "x"}, {"qid": "m02", "text_sha256": "y"}]}
    b = {"rows": [{"qid": "m01", "text_sha256": "x"}, {"qid": "m02", "text_sha256": "Z"}]}
    assert determinism(a, b) == ["m02"]
    assert determinism(a, {"rows": []}) == ["m01", "m02"]


# ── §5.2 기제 대조군 (이 판의 새 조항) ───────────────────────────────────────

def test_an_arm_that_improves_without_the_chunk_entering_is_not_a_candidate():
    """좋아졌는데 청크가 풀에 안 들어왔으면 값이 다른 데서 온 것이다 — 설명 못 하는 이득이다."""
    v = verdict(_arms(_arm("pool-25", 25, 4, 8, entered=False)), [], 5.0)
    assert v["adopt"] is None
    assert v["improved_without_the_mechanism"] == ["pool-25"]


def test_that_arm_is_recorded_rather_than_silently_dropped():
    """조용히 버리면 다음 사람이 같은 실험군을 다시 돌린다. 이름을 남긴다."""
    v = verdict(_arms(_arm("pool-25", 25, 4, 8, entered=False)), [], 5.0)
    assert "improved_without_the_mechanism" in v


def test_an_arm_with_the_mechanism_is_a_candidate():
    v = verdict(_arms(_arm("pool-25", 25, 3, 8, entered=True)), [], 5.0)
    assert v["adopt"] == "pool-25"


# ── §5.3 후보 조건 ───────────────────────────────────────────────────────────

def test_an_arm_that_only_ties_on_multihop_is_not_a_candidate():
    assert verdict(_arms(_arm("pool-25", 25, 2, 8)), [], 5.0)["adopt"] is None


def test_a_multihop_gain_that_costs_a_policy_query_is_not_a_candidate():
    assert verdict(_arms(_arm("pool-25", 25, 4, 7)), [], 5.0)["adopt"] is None


# ── §5.4·§5.5 두 상한 ────────────────────────────────────────────────────────

def test_an_arm_over_the_evidence_ceiling_is_refused():
    over = 1000 * COST_CEILING + 1
    assert verdict(_arms(_arm("pool-25", 25, 4, 8, chars=over)), [], 5.0)["adopt"] is None


def test_an_arm_over_the_latency_ceiling_is_refused_however_good_it_looks():
    """4/4 라도 두 배 느리면 안 받는다. 두 상한은 **따로** 걸린다."""
    slow = 200 * COST_CEILING + 1
    assert verdict(_arms(_arm("pool-25", 25, 4, 8, ms=slow)), [], 5.0)["adopt"] is None


def test_the_two_ceilings_are_the_same_number_as_the_previous_preregistration():
    """측정마다 상한이 달라지면 상한이 아니다."""
    assert COST_CEILING == 1.50


def test_latency_inside_the_noise_band_is_reported_as_unmeasurable():
    """잡음 폭 안의 차이를 대가라고 부르면, 없는 비용으로 실험군을 떨어뜨리게 된다."""
    v = verdict(_arms(_arm("pool-25", 25, 4, 8, ms=203)), [], noise_band=5.0)
    assert v["candidates"][0]["latency_is_measurable"] is False


def test_latency_outside_the_noise_band_is_reported_as_a_cost():
    v = verdict(_arms(_arm("pool-25", 25, 4, 8, ms=240)), [], noise_band=5.0)
    assert v["candidates"][0]["latency_is_measurable"] is True


# ── §5.6 여럿이면 풀이 가장 작은 것 ──────────────────────────────────────────

def test_the_smallest_pool_wins_not_the_highest_scoring_one():
    """§0 때문이다 — 풀이 커질수록 지문 분절과 기록된 평가 조건과의 어긋남이 커진다."""
    v = verdict(_arms(_arm("pool-40", 40, 4, 8), _arm("pool-25", 25, 3, 8)), [], 5.0)
    assert v["adopt"] == "pool-25"
    assert [c["arm"] for c in v["candidates"]] == ["pool-25", "pool-40"]


# ── §5.7 후보 없음도 결과다 ──────────────────────────────────────────────────

def test_no_candidate_is_a_result_not_an_error():
    v = verdict(_arms(_arm("pool-25", 25, 2, 8), _arm("pool-40", 40, 1, 8)), [], 5.0)
    assert v["adopt"] is None and v["stopped_at"] is None and "§5.7" in v["reason"]


def test_base_is_never_its_own_candidate():
    v = verdict(_arms(_arm("pool-25", 25, 3, 8)), [], 5.0)
    assert {c["arm"] for c in v["candidates"]} == {"pool-25"}


# ── 표가 반대를 말하지 않는가 ────────────────────────────────────────────────

def test_the_cost_column_reads_as_a_change_not_a_ratio():
    assert cost_delta(200, 200) == "+0%"
    assert cost_delta(140, 200) == "-30%"
    assert cost_delta(260, 200) == "+30%"
    assert cost_delta(100, 0) == "?"


def test_totals_carries_both_costs():
    rows = [{"group": "multihop", "covered": True, "chars": 10, "median_ms": 100},
            {"group": "policy", "covered": False, "chars": 30, "median_ms": 300}]
    t = totals(rows)
    assert t["median_chars"] == 20 and t["median_ms"] == 200
    assert t["multihop"] == {"covered": 1, "n": 1}
