"""못 낸 사실이 **근거에 있었는가** — 검색 결함과 서술 결함을 가른다 (감사 B3).

`must_contain` 라벨을 도는 러너(`ko_eval_answer_run.py`)에는 이 판정이 없었다. "사실이 답에
없다" 하나로는 **검색을 고칠지 서술을 고칠지 모른다.**

⛔ **왜 어제 이 자리를 못 봤나 (2026-09-05 정정).** `OPEN.md` A78 에 *"FP7 을 탈 수 있는 라벨이
하나도 없다"* 고 적었다. 근거는 `answer-facts.yaml` 15건이 전부 요구 사실 하나짜리라는 실측이고
그 실측은 맞다 — **그 집합 하나만 본 것이 틀렸다.** 실제로는 `must_contain` 이 둘 이상인 라벨이
Pack B 26 · 정책 8 · 멀티홉 4 · synthesis 3 으로 **41건** 있었다. 라벨이 없던 것이 아니라
귀속이 그 라벨을 안 보는 러너에 있었다.

⭐ **정규화가 갈리는 것이 이 자리의 진짜 위험이다** (`OPEN.md` A22: 같은 라벨에서 1판과 2판이
반대로 나온 적이 있다). 두 러너는 정규화가 다르다 —

    answer_fact_probe   쉼표·공백을 **지운다**   (`최대 1` == `최대1`)
    ko_eval_answer_run  공백을 **하나로 줄인다** (`최대 1` != `최대1`)

그래서 공용으로 뺀 것은 조합 규칙(`attribute_facts`)뿐이고, **존재 판정은 부르는 쪽이
자기 규칙으로 끝낸다.** 인자가 불리언 목록이라 잘못된 정규화를 들고 올 방법이 없다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ko_eval_answer_quality import (  # noqa: E402
    VERDICTS, aggregate, attribute_facts, delivered_text, facts_present, score_answer,
)

TWO = [["버전"], ["충돌", "경합"]]


# ── 조합 규칙 ────────────────────────────────────────────────────────────────

def test_pass_needs_every_group_in_the_answer():
    assert attribute_facts([True, True], [True, True])["verdict"] == "pass"


def test_upstream_when_what_was_missed_was_never_in_the_evidence():
    """검색이 못 물어온 것을 서술 실패로 세면 고칠 곳을 잘못 짚는다."""
    a = attribute_facts([True, False], [True, False])
    assert a["verdict"] == "upstream"
    assert (a["n_in_evidence"], a["n_in_answer"]) == (1, 1)


def test_fp4_is_everything_present_and_nothing_delivered():
    assert attribute_facts([True, True], [False, False])["verdict"] == "fp4"


def test_fp7_is_everything_present_and_half_delivered():
    assert attribute_facts([True, True], [True, False])["verdict"] == "fp7"


def test_mixed_is_not_forced_into_one_bucket():
    """⛔ 한쪽으로 몰아 세는 순간 이 판정이 거짓말을 한다."""
    assert attribute_facts([True, False, True], [False, False, True])["verdict"] == "mixed"


def test_no_groups_when_the_label_requires_nothing():
    assert attribute_facts([], [])["verdict"] == "no_groups"


def test_mismatched_lengths_are_a_bug_not_a_verdict():
    """묶음 수가 다르면 **같은 라벨로 두 번 판정한 것이 아니다.** 조용히 zip 되면 안 된다."""
    with pytest.raises(ValueError):
        attribute_facts([True], [True, False])


def test_every_verdict_name_is_declared():
    for pair in ([[], []], [[True], [True]], [[True], [False]], [[False], [False]],
                 [[True, True], [True, False]], [[True, False], [False, False]]):
        assert attribute_facts(*pair)["verdict"] in VERDICTS


# ── 채점기 배선 ──────────────────────────────────────────────────────────────

def test_without_evidence_nothing_is_attributed():
    """⭐ 기존 호출부는 한 줄도 안 바뀐다 — 근거를 안 주면 **판정 안 함**이다."""
    s = score_answer("q", "버전 필드가 필요합니다", [], set(), TWO)
    assert s.verdict == ""
    assert s.facts_in_evidence == []


def test_the_scorer_attributes_a_half_delivered_answer_as_fp7():
    s = score_answer("q", "버전 필드가 필요합니다", [], set(), TWO,
                     evidence_text="버전 필드는 충돌을 잡는다")
    assert s.verdict == "fp7"
    assert s.facts == [True, False]
    assert s.facts_in_evidence == [True, True]


def test_the_scorer_sends_a_missing_fact_upstream_when_the_evidence_lacked_it():
    s = score_answer("q", "버전 필드가 필요합니다", [], set(), TWO,
                     evidence_text="버전 필드에 대한 설명만 있다")
    assert s.verdict == "upstream"


def test_a_failed_generation_is_never_attributed():
    """⛔ LLM 이 실패하면 답변 자리에 **근거 원문 덤프**가 들어간다.

    두 쪽이 같은 문자열이 되므로 그 비교는 아무 뜻이 없다 — `has_facts` 가 같은 이유로
    무조건 거짓인 그 자리다. 2026-08-08 에 3건 중 2건이 그렇게 '통과' 했다.
    """
    dump = "버전 필드는 충돌을 잡는다"
    s = score_answer("q", dump, [], set(), TWO, llm_failed=True, evidence_text=dump)
    assert s.verdict == ""
    assert s.facts_in_evidence == []


def test_the_evidence_side_uses_this_runner_s_normaliser_not_the_other_one():
    """⭐ **A22 를 재생산하지 않는다.**

    `최대1` 은 이 러너의 규칙에서 `최대 1` 과 **다른 문자열**이다(공백을 줄일 뿐 지우지 않는다).
    다른 러너의 정규화를 들고 왔다면 여기서 `fp4` 가 나온다 — 지운 공백 덕에 근거에 있다고
    읽히기 때문이다. 나와야 하는 것은 `upstream` 이다.
    """
    s = score_answer("q", "모르겠습니다", [], set(), [["최대1"]],
                     evidence_text="최대 1 명까지 가능하다")
    assert s.verdict == "upstream", s.facts_in_evidence
    assert s.facts_in_evidence == facts_present([["최대1"]], "최대 1 명까지 가능하다")


def test_a_refusal_shaped_sentence_in_the_evidence_still_counts_as_evidence():
    """⛔ `delivered_text` 는 근거에 걸지 않는다.

    그 규칙은 *답변자가 무엇을 배달했는가* 를 보는 것이고, 근거는 배달된 것이 아니라
    **주어진 것**이다. 게다가 `format_for_llm` 의 머리글이 "## 검색된 근거" 라서, 근거에
    그 규칙을 걸면 근거 첫 덩어리가 통째로 사라질 수 있다.

    ⚠ **첫 판의 이 검사는 아무것도 안 지켰다.** 고의로 `delivered_text` 를 근거에 걸어 보니
    그대로 통과했다 — 요구한 사실 둘이 **거절 세그먼트 밖**에 있어서 걷어내도 판정이 안 바뀌는
    문자열을 골랐기 때문이다. 지금 것은 못 낸 쪽 사실(`버전`)이 거절 세그먼트 **안에만** 있다.
    """
    evidence = "제공된 근거에서 버전 필드는 확인되지 않습니다. 충돌은 잡는다."
    assert delivered_text(evidence).strip() == "충돌은 잡는다."      # 걷어내면 `버전` 이 사라진다
    s = score_answer("q", "충돌을 잡습니다", [], set(), TWO, evidence_text=evidence)
    assert s.facts == [False, True]
    assert s.facts_in_evidence == [True, True]
    assert s.verdict == "fp7"      # 근거에 걸었다면 `upstream` 이 나온다


# ── 집계 ─────────────────────────────────────────────────────────────────────

def test_unattributed_rows_are_counted_apart_from_failures():
    """**측정할 수 없었던 것과 실패한 것을 섞지 않는다** — 이 모듈의 집계 규칙 그대로다."""
    scored = [
        score_answer("a", "버전 필드가 필요합니다", [], set(), TWO,
                     evidence_text="버전 필드는 충돌을 잡는다"),      # fp7
        score_answer("b", "버전 필드가 필요합니다", [], set(), TWO),  # 판정 안 함
    ]
    agg = aggregate(scored)
    assert agg["attribution"]["fp7"] == 1
    assert agg["attribution_unjudged"] == 1
    assert sum(agg["attribution"].values()) == 1      # 판정 안 한 줄은 어느 칸에도 없다
    assert agg["fp7_qids"] == ["a"]
