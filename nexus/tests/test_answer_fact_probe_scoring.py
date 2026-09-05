"""채점기가 **모순 라벨을 볼 수 있는가.**

⛔ **왜 이 파일이 있나 (2026-08-31, 첫 서명 회차).** 소유자가 서명한 직후 점수를 냈더니
A-10(닉네임 모순 라벨)이 `언급=실패 · 주장=통과` 로 찍혔다. **2판은 1판의 부분집합**이어야
하므로 그 조합은 성립할 수 없고, 그것이 결함을 드러냈다.

결함은 둘이었다.

1. `type: conflict` 갈래가 `ok` 를 다시 계산하지 않았다. 모순 라벨은 `expect` 가 비고
   `expect_all` 만 갖는데 `ok` 는 위에서 `expect` 로만 계산돼 `any([])` = False 였다 —
   **답이 무엇이든 1판 실패.**
2. `mentioned` 가 `expect` 없는 라벨에서 무조건 False 였다. 그래서 요약이 `1판 14/15` 를
   냈는데, 빠진 하나는 답이 나빠서가 아니라 **1판이 그 라벨을 볼 수 없어서**였다.

분모에 넣고 항상 떨어뜨리는 것은 측정이 아니다. 그리고 이 파일에는 검사가 하나도 없었다.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "answer_fact_probe",
    Path(__file__).resolve().parents[1] / "scripts" / "answer_fact_probe.py")
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)

CONFLICT = [["12자", "12 자"], ["8자", "8 자"]]


def test_a_conflict_label_can_pass_at_all():
    """⛔ 이것이 False 로 굳어 있어서 모순 라벨은 어떤 답으로도 통과하지 못했다."""
    text = "문서 둘이 다릅니다: 한글·영문 포함 12자, 그리고 한글 8자 / 영문 16자."
    assert probe._all_groups_present(CONFLICT, probe._norm(text)) is True


def test_a_conflict_label_still_fails_when_a_value_is_missing():
    """⛔ 대조군. 통과시키려고 고친 것이 아니라 **볼 수 있게** 고친 것이다."""
    text = "닉네임은 12자 제한입니다."
    assert probe._all_groups_present(CONFLICT, probe._norm(text)) is False


def test_any_surface_form_in_a_group_counts():
    """묶음 안은 같은 값의 표기 후보다 — 하나만 맞으면 된다."""
    assert probe._all_groups_present([["30자", "30 자"]], probe._norm("최대 30 자")) is True


def test_a_plain_string_group_is_treated_as_one_surface():
    """`expect_all` 은 문자열과 묶음을 섞어 쓴다 (설계 라벨이 그렇다)."""
    assert probe._all_groups_present(["DjChangeType"], probe._norm("DjChangeType 이 온다")) is True
    assert probe._all_groups_present(["DjChangeType"], probe._norm("아무것도")) is False


def test_normalisation_ignores_spaces_and_commas():
    """`4,000` 과 `4000`, `최대 1` 과 `최대1` 은 같은 값이다."""
    assert probe._all_groups_present([["4000"]], probe._norm("4,000 건")) is True


def test_the_summary_does_not_make_a_ratio_before_signature():
    """⛔ 대조군 — 서명 전에 분수가 나오면 점수를 보고 라벨을 고칠 수 있다."""
    import re
    rows = [{"id": "X", "pass": True, "asserted": True, "mentioned": True,
             "distractor_seen": [], "chars": 10}]
    out = chr(10).join(probe.summary_lines(rows, for_signature=True))
    # 분수만 막는다 — 안내문의 `(1)`·`(2)` 같은 번호는 점수가 아니다.
    assert not re.search(r"\d+\s*/\s*\d+", out), out


# ── 실패 귀속 (감사 B3) ─────────────────────────────────────────────────────
#
# ⛔ **왜 이 묶음이 있나.** 이 채점기는 "요구한 사실이 답에 없다" 까지만 말했고, 그 하나의
# 신호가 셋을 뭉쳤다 — 검색이 못 물어온 것 · 물어왔는데 안 뽑은 것(FP4) · 반만 뽑은
# 것(FP7). 실패를 보고도 **검색을 고칠지 서술을 고칠지 알 수 없었다.**
#
# 여기 검사는 전부 순수 함수에 건다. 판정 규칙은 DB 도 LLM 도 필요 없고, 필요하게 만들면
# 이 규칙이 통합 실행 안에서만 확인되어 아무도 안 돌리게 된다.

TWO = [["12자", "12 자"], ["8자", "8 자"]]


def test_pass_when_every_required_fact_is_in_the_answer():
    a = probe.attribute(TWO, probe._norm("근거: 12자 그리고 8자"),
                        probe._norm("12자 이고 8자 입니다"))
    assert a["verdict"] == "pass"
    assert (a["n_required"], a["n_in_answer"]) == (2, 2)


def test_upstream_when_the_missing_fact_was_not_in_the_evidence_either():
    """검색이 못 물어온 것을 서술 실패로 세면 고칠 곳을 잘못 짚는다."""
    a = probe.attribute(TWO, probe._norm("근거에는 12자 만 있다"),
                        probe._norm("12자 입니다"))
    assert a["verdict"] == "upstream"
    assert a["missing"] == ["8자"]


def test_fp4_when_everything_was_in_the_evidence_and_nothing_came_out():
    a = probe.attribute(TWO, probe._norm("근거: 12자 그리고 8자"),
                        probe._norm("문서에서 확인하기 어렵습니다"))
    assert a["verdict"] == "fp4"
    assert (a["n_in_evidence"], a["n_in_answer"]) == (2, 0)


def test_fp7_when_everything_was_in_the_evidence_and_half_came_out():
    a = probe.attribute(TWO, probe._norm("근거: 12자 그리고 8자"),
                        probe._norm("12자 입니다"))
    assert a["verdict"] == "fp7"


def test_mixed_is_not_forced_into_one_bucket():
    """⛔ 한쪽으로 몰아 세는 순간 이 판정이 거짓말을 한다."""
    three = TWO + [["16자"]]
    a = probe.attribute(three, probe._norm("근거: 12자 그리고 8자"),
                        probe._norm("12자 입니다"))          # 8자=근거O·답X, 16자=근거X·답X
    assert a["verdict"] == "mixed"


def test_a_label_with_no_required_facts_is_not_scored():
    """분모에 넣고 항상 떨어뜨리는 것은 측정이 아니다 — 이 파일 머리말의 그 규칙이다."""
    assert probe.attribute([], "근거", "답")["verdict"] == "no_groups"


def test_required_groups_reads_both_label_shapes_the_way_scoring_does():
    """⛔ 귀속이 자기 규칙을 새로 만들면 점수와 **다른 것**을 세게 된다."""
    assert probe.required_groups({"expect_all": TWO}) == TWO
    assert probe.required_groups({"expect": ["4,000", "4000"]}) == [["4,000", "4000"]]
    assert probe.required_groups({}) == []


def test_the_pass_verdict_agrees_with_the_probe_s_own_first_judgement():
    """⭐ 이 검사가 "점수는 하나도 안 바뀌었다" 를 지킨다.

    귀속의 `pass` 는 1판과 **같은 규칙**이어야 한다 — `expect_all` 은 모든 묶음,
    `expect` 는 표기 후보 중 하나. 둘이 갈리면 실행 중 경고가 뜨지만, 그 경고를 보기 전에
    여기서 걸린다.
    """
    cases = [
        ({"expect_all": TWO}, "12자 이고 8자"),
        ({"expect_all": TWO}, "12자 뿐"),
        ({"expect": ["4,000", "4000"]}, "상한은 4,000 입니다"),
        ({"expect": ["4,000", "4000"]}, "상한을 찾지 못했습니다"),
    ]
    for q, text in cases:
        nt = probe._norm(text)
        if q.get("expect_all"):
            first = probe._all_groups_present(q["expect_all"], nt)
        else:
            first = any(probe._norm(e) in nt for e in q["expect"])
        verdict = probe.attribute(probe.required_groups(q), nt, nt)["verdict"]
        assert (verdict == "pass") is bool(first), (q, text, verdict, first)


def test_a_differently_worded_evidence_reads_as_upstream_not_fp4():
    """⚠ **알고 있는 기울기를 검사로 박아 둔다.**

    부분일치는 무르다. 같은 사실이 근거에 다른 말로 적혀 있으면 여기서는 "근거에 없음" 이
    되고, 그러면 FP4 가 적게·검색 쪽이 많게 세어진다. 그 방향을 모른 채 수를 읽으면
    서술 결함을 검색 결함으로 오진한다. 그래서 FP4/FP7 은 하한, 검색 쪽은 상한이다.
    """
    a = probe.attribute([["8자"]], probe._norm("최대 여덟 글자까지"), probe._norm("모르겠습니다"))
    assert a["verdict"] == "upstream"


def test_the_breakdown_never_prints_a_ratio():
    """서명 전 총점 금지와 같은 규칙 — 한 번 찍힌 수는 인용된다."""
    rows = [{"id": "A-1", "verdict": "fp4"}, {"id": "A-2", "verdict": "pass"}]
    text = "\n".join(probe.attribution_lines(rows))
    assert "A-1" in text and "FP4" in text
    # 금지하는 것은 **분수**이지 빗금이 아니다 — 안내 문장에 `FP4/FP7` 이 들어간다.
    assert re.search(r"\d\s*/\s*\d", text) is None, text
    assert "%" not in text


def test_the_breakdown_says_nothing_when_nothing_was_attributed():
    assert probe.attribution_lines([{"id": "A-1"}]) == []
