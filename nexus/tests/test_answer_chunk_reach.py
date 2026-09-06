"""답 청크에 **길이 있는가**를 세는 측정기의 순수 부분 (`OPEN.md` A86).

⛔ **이 측정기가 답하지 않는 것**을 검사로 박아 둔다. 내는 것은 *풀에 들어갈 수 있는가* 이지
*상위에 오는가* 가 아니고, 판정도 문턱도 없다. 그 성질이 흐려지면 이 수가 등급으로 인용된다 —
이 리포는 지어낸 수에 이미 여러 번 데였다.
"""

from __future__ import annotations

import re

from scripts.answer_chunk_reach import (
    group_verdict, hangul_ratio, report_lines, required_groups,
)


# ── 묶음 판정 ────────────────────────────────────────────────────────────────
#
# ⛔ **첫 판은 이 조합이 DB 함수 안에 있었고, 벡터 판정을 통째로 지워도 검사가 전부 초록이었다.**
# 크기를 2배로 부풀리는 파손이 안 잡혔다는 뜻이다 — 그래서 순수 함수로 뺐다.

def test_no_chunk_holding_the_answer_is_absent_not_a_retrieval_failure():
    """코퍼스에 답이 없는 것은 이 측정의 대상이 아니다 — 겨냥 문제이거나 FP1 이다."""
    assert group_verdict(0, None, None) == "absent"


def test_bm25_seeing_it_is_reachable_whatever_the_vector_leg_does():
    assert group_verdict(1, True, False) == "reachable"
    assert group_verdict(1, True, True) == "reachable"


def test_vector_only_is_latent_not_biting():
    """⭐ 이 갈래가 크기를 절반으로 바꿨다 — 실측에서 BM25 사각 2개 중 1개가 여기였다."""
    assert group_verdict(1, False, True) == "bm25_blind"


def test_neither_leg_is_the_state_that_actually_lost_the_answer():
    assert group_verdict(1, False, False) == "unreachable"


def test_hangul_ratio_is_a_ratio_of_characters_not_words():
    assert hangul_ratio("가나다") == 1.0
    assert hangul_ratio("abc") == 0.0
    assert round(hangul_ratio("가a나b"), 2) == 0.5


def test_hangul_ratio_of_nothing_is_zero_not_a_crash():
    assert hangul_ratio("") == 0.0
    assert hangul_ratio(None) == 0.0


def test_both_label_schemas_read_as_the_same_shape():
    """⛔ 두 계열을 따로 읽으면 한쪽만 고쳐지고 나머지가 조용히 다른 것을 센다."""
    assert required_groups({"must_contain": [["a", "A"], ["b"]]}) == [["a", "A"], ["b"]]
    assert required_groups({"expect_all": [["a", "A"], "b"]}) == [["a", "A"], ["b"]]
    assert required_groups({"expect": ["4,000", "4000"]}) == [["4,000", "4000"]]
    assert required_groups({}) == []


def test_must_contain_wins_when_a_label_somehow_carries_both():
    """Pack B 계열을 먼저 읽는다 — 그쪽이 채점에 실제로 쓰이는 칸이다."""
    assert required_groups({"must_contain": [["m"]], "expect": ["e"]}) == [["m"]]


def _scan(rows, name="x.yaml", tenant="default"):
    return {"labels": name, "tenant": tenant, "note": "", "rows": rows}


def _row(qid, groups=1, blind=0, dead=0, absent=0, qh=0.7, mh=0.0):
    return {"id": qid, "query_hangul": qh, "groups": groups, "absent": absent,
            "invisible_to_bm25": blind, "reachable": groups - blind,
            "unreachable_by_either": dead, "min_hangul_of_answer_chunks": mh}


def test_the_report_never_prints_a_ratio_or_a_grade():
    """**판정하지 않는다.** 분수 하나가 이 측정기를 점수판으로 만든다."""
    text = "\n".join(report_lines([_scan([_row("A", blind=1, dead=1), _row("B")])]))
    # 금지하는 것은 **분수**다. 퍼센트는 한글 비율 설명에 쓰이므로 여기서 막지 않는다.
    assert re.search(r"\d\s*/\s*\d", text) is None, text
    for word in ("통과", "실패", "합격", "점수"):
        assert word not in text, word


def test_a_label_blind_to_bm25_but_reachable_by_vector_is_marked_as_such():
    """⭐ 이 구분이 크기를 **절반으로** 바꿨다 — BM25 만 보면 2건, 두 레그를 보면 1건이다."""
    text = "\n".join(report_lines([_scan([_row("latent", blind=1, dead=0)])]))
    assert "벡터는 넣는다" in text
    assert "**벡터도 못 넣는다**" not in text

    text2 = "\n".join(report_lines([_scan([_row("biting", blind=1, dead=1)])]))
    assert "**벡터도 못 넣는다**" in text2


def test_the_totals_add_up_across_label_sets():
    lines = report_lines([_scan([_row("a", groups=2, blind=1, dead=1)], "one.yaml"),
                          _scan([_row("b", groups=3, blind=1, dead=0)], "two.yaml")])
    total = next(ln for ln in lines if ln.startswith("합계"))
    assert "라벨 2건" in total
    assert "요구 묶음 5개" in total
    assert "BM25 사각 2개" in total
    assert "두 레그 모두 사각 1개" in total


def test_the_limits_are_printed_every_time():
    """⚠ 한계는 옵션이 아니다 — 이 수를 인용하는 사람이 같은 화면에서 봐야 한다."""
    text = "\n".join(report_lines([_scan([_row("a")])]))
    assert "상위에 오는가가 아니다" in text
    assert "설명 변수이지 판정이 아니다" in text
    assert "gold 문서가 아니다" in text
