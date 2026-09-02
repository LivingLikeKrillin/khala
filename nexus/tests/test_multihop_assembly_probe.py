"""멀티홉 조립 프로브의 **판정 규칙** — `docs/MULTIHOP_ASSEMBLY_PREREGISTRATION.md` §5.

사전 등록의 값은 규칙이 결과보다 먼저 있다는 것 하나다. 그런데 규칙이 코드에만 있고 검사가 없으면
결과를 본 뒤에 조용히 바뀌고, 바뀌었다는 사실이 어디에도 안 남는다. 그래서 여기 검사는 §5 의 여섯
조항을 **하나씩** 건다 — 통과만이 아니라 **막아야 할 것이 막히는지**를 같이 건다.
"""

from __future__ import annotations

from scripts.multihop_assembly_probe import COST_CEILING, determinism, totals, verdict


def _arm(name, multihop, policy, chars, n_mh=4, n_pol=8):
    return {"arm": name, "median_chars": chars,
            "multihop": {"covered": multihop, "n": n_mh},
            "policy": {"covered": policy, "n": n_pol}}


def _arms(**kw):
    """base 2/4·8/8·1000자 를 바닥으로, 이름 붙인 실험군을 얹는다."""
    out = [_arm("base", 2, 8, 1000), _arm("fill-off", 1, 8, 800)]
    out += [_arm(name, *rest) for name, rest in kw.items()]
    return out


# ── §5.1 결정론 대조군 ───────────────────────────────────────────────────────

def test_a_drifting_base_stops_before_any_verdict():
    """회차가 갈리면 '실험군당 1회' 라는 전제가 거짓이다 — 그 위의 판정은 판정이 아니다."""
    v = verdict(_arms(), ["m01", "p03"])
    assert v["stopped_at"].startswith("§5.1")
    assert v["adopt"] is None and v["candidates"] == []


def test_determinism_names_only_the_queries_that_moved():
    a = {"rows": [{"qid": "m01", "text_sha256": "x"}, {"qid": "m02", "text_sha256": "y"}]}
    b = {"rows": [{"qid": "m01", "text_sha256": "x"}, {"qid": "m02", "text_sha256": "CHANGED"}]}
    assert determinism(a, b) == ["m02"]
    assert determinism(a, a) == []


def test_a_query_missing_from_the_second_round_counts_as_drift():
    """빠진 질의를 '같다' 로 세면 결정론 대조군이 통과하는 척한다."""
    a = {"rows": [{"qid": "m01", "text_sha256": "x"}]}
    assert determinism(a, {"rows": []}) == ["m01"]


# ── §5.2 음성 대조군 ─────────────────────────────────────────────────────────

def test_fill_off_matching_base_falsifies_the_mechanism():
    """절 채움을 꺼도 같으면 §1 의 기제 서술이 틀린 것이다 — 후보를 고를 자리가 아니다."""
    arms = [_arm("base", 2, 8, 1000), _arm("fill-off", 2, 8, 800),
            _arm("hits-5", 4, 8, 1100)]
    v = verdict(arms, [])
    assert v["stopped_at"].startswith("§5.2") and v["adopt"] is None


def test_fill_off_below_base_lets_the_verdict_proceed():
    v = verdict(_arms(**{"hits-5": (3, 8, 1100)}), [])
    assert v["stopped_at"] is None and v["adopt"] == "hits-5"


# ── §5.3 후보 조건 ───────────────────────────────────────────────────────────

def test_an_arm_that_only_ties_on_multihop_is_not_a_candidate():
    """'엄격히 크다' 를 '크거나 같다' 로 읽으면 아무것도 안 고친 실험군이 채택된다."""
    assert verdict(_arms(**{"hits-5": (2, 8, 1000)}), [])["adopt"] is None


def test_a_multihop_gain_that_costs_a_policy_query_is_not_a_candidate():
    """회귀 검사는 부등호가 반대다 — 단일홉이 하나라도 떨어지면 거래가 아니다."""
    assert verdict(_arms(**{"hits-5": (4, 7, 1100)}), [])["adopt"] is None


def test_a_policy_gain_alongside_the_multihop_gain_is_fine():
    assert verdict(_arms(**{"hits-5": (3, 8, 1100)}), [])["adopt"] == "hits-5"


# ── §5.5 값의 상한 ───────────────────────────────────────────────────────────

def test_an_arm_over_the_cost_ceiling_is_refused_however_good_it_looks():
    """4/4 라도 근거가 두 배면 안 받는다. 상한은 결과를 보기 전에 박혔다."""
    over = 1000 * COST_CEILING + 1
    assert verdict(_arms(**{"hits-10": (4, 8, over)}), [])["adopt"] is None


def test_an_arm_exactly_at_the_ceiling_is_still_a_candidate():
    """경계는 포함이다 — 부등호가 미끄러지면 상한이 하는 말이 달라진다."""
    assert verdict(_arms(**{"hits-10": (4, 8, 1000 * COST_CEILING)}), [])["adopt"] == "hits-10"


# ── §5.4 여럿이면 가장 싼 것 ─────────────────────────────────────────────────

def test_the_cheapest_candidate_wins_not_the_highest_scoring_one():
    """더 많이 맞히는 실험군이 아니라 **근거가 덜 느는** 실험군을 고른다고 미리 적었다."""
    v = verdict(_arms(**{"hits-10": (4, 8, 1400), "hits-5": (3, 8, 1050)}), [])
    assert v["adopt"] == "hits-5"
    assert [c["arm"] for c in v["candidates"]] == ["hits-5", "hits-10"]


# ── §5.6 후보 없음도 결과다 ──────────────────────────────────────────────────

def test_no_candidate_is_a_result_not_an_error():
    v = verdict(_arms(**{"hits-5": (2, 8, 1100), "cap-10": (1, 8, 1200)}), [])
    assert v["adopt"] is None and v["stopped_at"] is None
    assert "§5.6" in v["reason"]


def test_base_and_fill_off_are_never_themselves_candidates():
    """바닥과 음성 대조군은 비교 대상이지 채택 대상이 아니다."""
    v = verdict(_arms(**{"hits-5": (3, 8, 1100)}), [])
    assert {c["arm"] for c in v["candidates"]} == {"hits-5"}


# ── 요약 집계 ────────────────────────────────────────────────────────────────

def test_totals_counts_each_group_separately():
    rows = [{"group": "multihop", "covered": True, "chars": 10},
            {"group": "multihop", "covered": False, "chars": 20},
            {"group": "policy", "covered": True, "chars": 30}]
    t = totals(rows)
    assert t["multihop"] == {"covered": 1, "n": 2}
    assert t["policy"] == {"covered": 1, "n": 1}
    assert t["median_chars"] == 20


# ── 사람이 읽는 표가 반대를 말하지 않는가 ────────────────────────────────────
#
# 첫 판은 비율을 그대로 백분율로 찍었다: 0.706 → `+71%`, 1.00 → `+100%`, 거기에 문자열 치환을
# 덧대 `+00%` 를 만들었다. **근거가 3할 줄어든 실험군이 7할 늘어난 것처럼** 보였다. 판정은 원래
# 값으로 계산하므로 결과는 안 틀렸지만, 표가 반대를 말하면 그 표를 근거로 다음 결정이 난다.

from scripts.multihop_assembly_probe import cost_delta  # noqa: E402


def test_the_base_arm_shows_no_change():
    assert cost_delta(15292, 15292) == "+0%"


def test_a_smaller_arm_reads_as_a_decrease():
    assert cost_delta(10796, 15292) == "-29%"


def test_a_bigger_arm_reads_as_an_increase():
    assert cost_delta(19533, 15292) == "+28%"


def test_the_ceiling_reads_as_the_number_it_was_registered_as():
    """+50% 로 박아 둔 상한이 표에서도 +50% 로 읽혀야 한다."""
    assert cost_delta(1000 * COST_CEILING, 1000) == "+50%"


def test_a_zero_base_says_so_instead_of_dividing():
    assert cost_delta(100, 0) == "?"


# ── 진단은 판정이 아니다 ─────────────────────────────────────────────────────

async def test_a_covered_query_needs_no_database_to_explain():
    """다 받은 질의는 설명할 것이 없다 — DB 도, 검색도 부르지 않고 곧장 돌아와야 한다.

    이 검사가 도는 것 자체가 그 성질의 증거다: `con`·`search` 자리에 `None` 을 넣었으므로
    조기 반환이 없으면 여기서 터진다.
    """
    from scripts.multihop_assembly_probe import explain

    q = {"id": "m03", "must_contain": [["가"], ["나"]]}
    out = await explain(q, [True, True], ["default"], {}, None, None, None)
    assert out == {"qid": "m03", "missing_groups": 0, "holders": []}


async def test_a_query_with_no_requirements_is_not_a_failure():
    """요구가 없으면 못 받은 것도 없다 — `must_contain` 이 빈 라벨에서 터지면 안 된다."""
    from scripts.multihop_assembly_probe import explain

    out = await explain({"id": "x"}, [], ["default"], {}, None, None, None)
    assert out["missing_groups"] == 0


# ── 한 경로에만 잡힌 청크 (2026-09-02) ───────────────────────────────────────
#
# 실측: 정답 청크가 벡터 경로에서 **8위**인데 융합 뒤 **15위**였다. BM25 후보 풀(20) 밖이라
# 한 경로에서만 들어왔고, 융합은 두 경로가 합의한 청크를 위로 올린다. m01 은 BM25 전체 순위
# **21위** — 풀을 **한 자리** 차이로 놓쳤다(점수 0.30696 vs 20위 0.31138).

from scripts.multihop_assembly_probe import one_leg_only  # noqa: E402


def test_a_chunk_in_both_pools_is_not_one_leg_only():
    assert not one_leg_only({"bm25_rank": 3, "vector_rank": 8})


def test_a_chunk_only_the_vector_leg_found_is_flagged():
    """m01 이 정확히 이 모양이다 — 벡터 8위, BM25 풀 밖."""
    assert one_leg_only({"bm25_rank": None, "vector_rank": 8})


def test_a_chunk_only_the_keyword_leg_found_is_flagged_too():
    """반대 방향도 같은 결함이다 — 한쪽만 보면 벡터 세대 사고를 놓친다."""
    assert one_leg_only({"bm25_rank": 4, "vector_rank": None})


def test_a_chunk_neither_leg_found_is_not_a_fusion_problem():
    """양쪽 다 못 잡았으면 융합 탓이 아니다 — 처방이 다르므로 같은 이름으로 부르면 안 된다."""
    assert not one_leg_only({"bm25_rank": None, "vector_rank": None})


def test_missing_keys_do_not_crash_the_diagnosis():
    assert not one_leg_only({})
