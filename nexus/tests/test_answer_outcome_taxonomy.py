"""오답과 기권을 가르는 자 — `scripts/ko_eval_answer_quality`.

옛 자는 `grounded AND cites_gold AND has_facts` 하나로만 셌다. 셋 중 무엇이 어긋나든 같은
`failed` 칸에 들어가므로, **정직한 기권**(검색이 근거를 못 줘서 답변자가 없다고 밝힘)과
**오답**(근거를 받고도 틀림)이 구별되지 않는다. 2026-08-10 에 그 뭉침 때문에 "답변 품질이
내려갔다" 를 잘못 읽었다 — 실제로는 검색 결함이 대부분이었고 답변자는 그때마다 정직했다.

세분도는 Google 의 *Sufficient Context*(arXiv:2411.06037)가 쓴 **근거 충분성 × 결과** 2축에
맞췄다. 더 잘게 쪼개지 않는 이유는 칸마다 **다른 곳을 고치라고 말해야** 뜻이 있고, 40건을
16칸으로 나누면 어느 칸도 유의하지 않기 때문이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ko_eval_answer_quality import (  # noqa: E402
    AnswerScore,
    aggregate,
    grid,
    is_abstention,
    score_answer,
)

#: 2026-08-10 실행에서 실제로 나온 문구다. 지어내지 않았다 — 어휘 규칙은 표현이 바뀌면 놓치므로,
#: 무엇을 보고 만든 규칙인지 여기 고정해 둔다.
REAL_ABSTENTIONS = [
    "제공된 근거에서 **태스크**와 **디제잉 포인트**의 관계를 확인할 수 없습니다.",
    "제공된 근거에서 디제잉 포인트가 **언제 합산되는지**에 대한 정보는 찾을 수 없습니다.",
    '제공된 근거에서 **"재생목록 이동"**에 특화된 한도 수치는 확인되지 않습니다.',
]

#: 같은 실행에서 나온 **답변**이다. 하위 항목 하나가 없다고 덧붙였을 뿐 질문에는 답했다.
REAL_ANSWERS_THAT_MENTION_ABSENCE = [
    "## Asterisk → AI 파이프라인 전달 구간\n\n[출처: AI 음성 콜 서비스]에 따르면 미디어는 "
    "RTP 로 전달됩니다. 다만 세부 수치는 확인되지 않습니다.",
    "제공된 근거에 따르면, 롤백 조건은 **카나리 비율(%)** 및 실험 토글 표준과 함께 정합니다. "
    "일부 항목은 근거에 없습니다.",
]


def test_a_refusal_at_the_top_is_an_abstention():
    for text in REAL_ABSTENTIONS:
        assert is_abstention(text), text[:40]


def test_an_answer_that_merely_mentions_a_gap_is_not_an_abstention():
    """40건 중 2건이 이 모양이었다. 문구를 아무 데서나 찾으면 답변이 기권으로 세어진다."""
    for text in REAL_ANSWERS_THAT_MENTION_ABSENCE:
        assert not is_abstention(text), text[:40]


def test_markdown_heading_before_the_refusal_still_counts():
    assert is_abstention("## 결론\n\n제공된 근거에서 확인할 수 없습니다.")


def test_abstention_outranks_the_fact_check():
    """**옛 자의 실제 결함.** 거절 문장은 질문의 어휘를 되풀이하므로 `must_contain` 이 거저
    통과한다. 2026-08-10 에 `pb-part-07` 이 "태스크와 디제잉 포인트의 관계를 확인할 수
    없습니다" 로 거절하면서 `태스크`·`다른` 을 둘 다 담아 사실검사를 통과했다.
    """
    answer = ("제공된 근거에서 **태스크**와 **디제잉 포인트**의 관계를 확인할 수 없습니다. "
              "두 시스템이 같은지 다른지 근거 기반으로 답변하는 것이 불가능합니다.")
    s = score_answer("q", answer, [], set(), [["별개", "다른", "별도"], ["태스크"]])
    assert s.has_facts is True, "사실검사 자체는 통과한다 — 그것이 문제의 전제다"
    assert s.outcome == "abstained", "거절이 정답으로 세어졌다"


def test_a_wrong_answer_with_the_gold_document_is_incorrect():
    s = AnswerScore(qid="q", grounded=True, cites_gold=True, facts=[False])
    assert s.outcome == "incorrect"


def test_a_right_answer_citing_the_wrong_document_is_incorrect():
    """정답 문서를 못 가리키면 그 답이 맞았다는 것을 이 자는 확인할 수 없다."""
    s = AnswerScore(qid="q", grounded=True, cites_gold=False, facts=[True])
    assert s.outcome == "incorrect"


def test_a_failed_llm_call_is_unmeasurable_not_incorrect():
    """실패한 호출은 결과가 아니다. 답변 자리에 근거 덤프가 들어가 사실검사가 거저 통과한다."""
    s = AnswerScore(qid="q", grounded=True, cites_gold=True, facts=[True], llm_failed=True)
    assert s.outcome == "unmeasurable" and s.ok is False


def test_the_aggregate_separates_abstention_from_incorrect():
    scores = [
        AnswerScore(qid="a", grounded=True, cites_gold=True, facts=[True]),
        AnswerScore(qid="b", grounded=True, cites_gold=True, facts=[False]),
        AnswerScore(qid="c", grounded=False, cites_gold=False, facts=[False], abstained=True),
    ]
    a = aggregate(scores)
    assert a["outcomes"] == {"correct": 1, "incorrect": 1, "abstained": 1, "unmeasurable": 0}
    assert a["abstained_qids"] == ["c"] and a["incorrect_qids"] == ["b"]
    # 옛 지표는 그대로 살아 있다 — 과거 실행과 비교할 수 있어야 한다.
    assert a["all_three"] == 1


# ── 격자: 칸마다 다른 곳을 고치라고 말하는가 ──────────────────────────────────

def _score(qid, **kw):
    return AnswerScore(qid=qid, **kw)


def test_the_grid_names_what_each_cell_means():
    scores = [
        _score("ok", grounded=True, cites_gold=True, facts=[True]),
        _score("gen", grounded=True, cites_gold=True, facts=[False]),
        _score("halluc", grounded=True, cites_gold=True, facts=[False]),
        _score("honest", abstained=True),
        _score("over", abstained=True),
    ]
    suff = {"ok": "sufficient", "gen": "sufficient", "halluc": "insufficient",
            "honest": "insufficient", "over": "sufficient"}
    g = grid(scores, suff)
    assert "환각" in g["insufficient/incorrect"]["means"]
    assert "검색을 고쳐라" in g["insufficient/abstained"]["means"]
    assert "과잉 기권" in g["sufficient/abstained"]["means"]
    assert "생성 결함" in g["sufficient/incorrect"]["means"]


def test_the_grid_refuses_to_guess_when_sufficiency_is_missing():
    """절반만 아는 격자는 칸의 뜻을 잃는다 — 충분성 없는 질의는 격자에 넣지 않는다."""
    scores = [_score("a", grounded=True, cites_gold=True, facts=[True]),
              _score("b", grounded=True, cites_gold=True, facts=[True])]
    g = grid(scores, {"a": "sufficient"})
    assert sum(c["n"] for c in g.values()) == 1


def test_unmeasurable_runs_stay_out_of_the_grid():
    scores = [_score("x", grounded=True, cites_gold=True, facts=[True], llm_failed=True)]
    assert grid(scores, {"x": "sufficient"}) == {}


# ── 인용이 등급 문구에 오염되면 멀쩡한 답이 환각이 된다 ─────────────────────

def test_a_tier_note_swallowed_into_a_citation_is_the_shape_that_misled_us():
    """2026-08-10 실측에서 나온 실제 답변 조각이다. 프롬프트의 등급 라벨이 `출처 종류:` 로
    시작한 탓에 모델이 그것을 인용 문자열 안으로 흡수했고, 인용 검증기가 제목을 못 찾아
    `grounded=False` 가 되면서 **근거에 실재하는 답이 환각 칸으로 분류**됐다.

    등급 표시가 `출처` 를 안 쓰게 고쳤으므로 이 모양은 더 나오지 않아야 한다. 그래도 자 쪽에
    남겨 두는 이유는, 같은 사고가 다른 라벨로 재발하면 **여기서 먼저 보이게** 하기 위해서다.
    """
    from nexus.search.provenance import PROMPT_NOTE

    polluted = "[출처: 파티 목록/개설 정책 — Flow 2, 그림에서 기계가 읽은 텍스트]"
    # 오염된 인용은 제목 대조를 통과할 수 없다 — 그것이 grounded 를 무너뜨린 경로다.
    assert "그림에서 기계가 읽" in polluted

    # 프롬프트 라벨이 인용 문법과 겹치지 않으면 이 흡수가 애초에 일어나지 않는다.
    assert "출처" not in PROMPT_NOTE


def test_the_rule_catches_a_phrasing_the_first_version_missed():
    """**목록은 바로 다음 실행에서 뚫렸다.** 첫 판은 관찰한 문구 3개를 나열했고, 다음 실행에서
    네 번째 표현이 나왔다 — 그리고 기권이 오답으로, 다시 **환각으로** 세어졌다.

    그래서 문구가 아니라 구조로 잡는다: 거절은 *근거를 지목하며* 부정한다.
    """
    assert is_abstention("제공된 근거로는 해당 질문에 답변하기 어렵습니다.")
    assert is_abstention("검색된 자료에서는 해당 수치를 찾을 수 없습니다.")


def test_an_answer_whose_content_is_negative_is_not_an_abstention():
    """내용이 부정인 **답변**은 근거를 지목하지 않는다 — 그것이 구조 규칙의 근거다.
    2026-08-10 실행에서 실제로 나온 문장들이다."""
    for text in ("차감되지 않습니다. 해금 형태로 오픈됩니다.",
                 "토큰 없이 호출하면 401로 실패합니다.",
                 "단일 핫키는 일반 파티셔닝으로 해결되지 않습니다."):
        assert not is_abstention(text), text
