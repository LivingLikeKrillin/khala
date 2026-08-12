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
    delivered_text,
    grid,
    is_abstention,
    leads_with_refusal,
    refuses,
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


def test_a_fact_that_only_appears_inside_the_refusal_was_not_delivered():
    """**옛 자의 실제 결함.** 거절 문장은 질문의 어휘를 되풀이하므로 `must_contain` 이 거저
    통과한다. 2026-08-10 에 `pb-part-07` 이 "태스크와 디제잉 포인트의 관계를 확인할 수
    없습니다" 로 거절하면서 `태스크`·`다른` 을 둘 다 담아 사실검사를 통과했다.

    옛 자는 그것을 **기권이 사실검사를 이긴다**는 우선순위로 막았다. 그 우선순위가 §1.1 의
    반대편 오탐(부분 기권을 전체 기권으로 읽는 것)을 낳았으므로, 이제는 우선순위가 아니라
    **배달**로 막는다: 사실은 거절 세그먼트 **밖**에 있어야 센다.
    """
    answer = ("제공된 근거에서 **태스크**와 **디제잉 포인트**의 관계를 확인할 수 없습니다. "
              "두 시스템이 같은지 다른지 근거 기반으로 답변하는 것이 불가능합니다.")
    s = score_answer("q", answer, [], set(), [["별개", "다른", "별도"], ["태스크"]])
    assert s.has_facts is False, "거절 안에서 되풀이된 어휘가 사실 배달로 세어졌다"
    assert s.outcome == "abstained", "거절이 정답으로 세어졌다"


# ── 거절의 범위: 어느 문장인가, 그리고 어디에 섰는가 (SPEC-nexus-answer-quality-ruler §3.1) ──

#: 2026-08-11 실행에서 나온 실제 답변의 **여는 문장**이다. 둘 다 범위를 좁히는 단서일 뿐,
#: 질문을 거절한 것이 아니다 — 그리고 옛 자는 둘 다 기권으로 셌다.
REAL_HEDGES = [
    ("제공된 문서에 재시도 **횟수·간격·백오프 공식** 등 구체적인 정책 수치는 명시되어 있지 않습니다.\n\n"
     "낙관적 락은 커밋 시점에 version 필드로 충돌을 감지하며, 영향 행 수가 0이면 재시도가 필요합니다.",
     [["재시도"]]),
    ("근거에서 k6와 Locust에 대한 언급은 한 곳뿐이며, 구체적인 시나리오 목록은 제공되지 않습니다.\n\n"
     "k6 · Locust · JMeter 는 핫스팟 예방 단계에서 사전 시뮬레이션 수단으로 언급됩니다.",
     [["시뮬레이션"]]),
]

#: 같은 날 실행의 **닫는 문장**이다. 답을 다 하고 근거의 등급을 밝힌 것이라, 거절이지만 선두가
#: 아니다. 배달된 본문은 다른 조직의 정책 내용이라 여기서는 중립 문장으로 세운다.
REAL_TRAILING_CAVEAT = (
    "요약 흐름은 위 표와 같습니다. 각 단계는 근거의 화면 정의에서 그대로 옮겼습니다.\n\n"
    "> ⚠ **근거 출처 유의**: 근거 1·2는 그림에서 기계가 읽은 내용(vision 추출)입니다. "
    "설계 문서 기반 정보이며, 실제 구현 관측 데이터는 제공된 근거에 없습니다."
)

#: 답변불가 5건(대조군)의 실제 여는 문장. 중복을 뺀 셋이다.
REAL_CONTROL_OPENINGS = [
    "제공된 문서에서 쿠버네티스 파드 오토스케일링 임계값을 **구체적으로 설정하는 방법**은 다루고 있지 않습니다.",
    "제공된 문서에서 해당 정보를 찾을 수 없습니다.",
    "제공된 근거에서 임베딩 모델 교체의 **전체 배포 순서**를 직접 서술한 문서는 없습니다.",
]


def test_a_hedge_that_still_delivers_the_answer_is_not_an_abstention():
    """§1.1 의 결함. 옛 자는 여는 문장만 보고 `pb-space-01`·`pb-mix-08` 을 기권으로 셌다."""
    for text, must in REAL_HEDGES:
        s = score_answer("q", text, [], set(), must)
        assert s.has_facts is True, text[:40]
        assert s.abstained is False, text[:40]


def test_a_trailing_caveat_does_not_turn_an_answer_into_an_abstention():
    """이 규칙의 첫 판(세그먼트만 보고 배달 여부로 판정)이 만든 **새 오탐**이다. 새 45건 표본이
    바로 반증했고, 그래서 '선두' 조건이 붙었다. 기록해 두지 않으면 다음 판에서 되돌아온다."""
    assert refuses(REAL_TRAILING_CAVEAT) is True, "거절 세그먼트 자체는 있다"
    assert leads_with_refusal(REAL_TRAILING_CAVEAT) is False
    s = score_answer("q", REAL_TRAILING_CAVEAT, [], set(), [["요약"]])
    assert s.abstained is False


def test_every_control_opening_refuses_and_abstains():
    """대조군 = 코퍼스가 답을 못 가진 질의. 5/5 가 실제로 거절했고, 자는 그것을 기권으로 세야 한다.

    `must_contain` 이 비면 **배달할 것이 없다** → 배달 실패다. `all([]) == True` 에 맡기면
    반대로 읽히므로 여기서 못 박는다.
    """
    for text in REAL_CONTROL_OPENINGS:
        assert refuses(text) and leads_with_refusal(text), text[:40]
        s = score_answer("un", text, [], set(), [])
        assert s.has_facts is False and s.abstained is True, text[:40]


def test_delivered_text_drops_the_refusal_and_keeps_the_rest():
    text, _ = REAL_HEDGES[0]
    delivered = delivered_text(text)
    assert "명시되어 있지 않습니다" not in delivered
    assert "충돌을 감지하며" in delivered


# ── 판정되지 않은 문서는 틀린 문서가 아니다 (SPEC-nexus-answer-quality-ruler §3.2) ──

#: 테넌트에 실재하는 문서 제목들. 실행기는 이것을 DB 에서 읽어 넘긴다.
TENANT = {"정답 문서", "같은 사실을 적은 다른 문서", "판정 끝난 무관한 문서"}


def _cited(title, verified=True):
    return {"title": title, "verified": verified}


def test_a_correct_answer_citing_an_unjudged_document_is_not_incorrect():
    """`pb-part-02` 의 모양. 사실도 맞고 인용도 해소되는데 라벨이 그 문서를 판정한 적이 없다.
    자는 그 문서가 답을 담는지 **모른다** — 모르는 것을 오답이라 부르면 안 된다."""
    s = score_answer("q", "최대 100 곡입니다 [출처: 같은 사실을 적은 다른 문서]",
                     [_cited("같은 사실을 적은 다른 문서")], {"정답 문서"}, [["100"]],
                     known_titles=TENANT)
    assert s.outcome == "unadjudicated"
    assert s.unjudged == ["같은 사실을 적은 다른 문서"]
    assert s.ok is False, "미판정은 만점이 아니다 — 사람이 읽어야 닫힌다"


def test_an_answer_whose_citation_did_not_verify_is_not_correct():
    """`rev6-r1` 의 모양: 사실 40/40, 정답문서 40/40, 그런데 grounded 39 — 미검증 인용 2건.

    콘솔은 `정답 40 오답 0` 을 찍고 같은 실행의 누적 로그는 `all_three 39` 를 적었다. 한 리포트가
    두 개의 '정답' 을 담았고, 사람 눈에 먼저 닿는 쪽이 후한 값이었다.
    """
    # gold 는 검증됐고 **다른 인용 하나가 검증에 실패했다** — 실제 rev6-r1 의 모양이다.
    # (`cites_gold` 는 검증된 인용만 세므로, 인용이 하나뿐인데 미검증이면 애초에 False 다.)
    s = score_answer("q", "최대 100 곡입니다 [출처: 정답 문서]",
                     [_cited("정답 문서"), _cited("확인 안 되는 문서", verified=False)],
                     {"정답 문서"}, [["100"]], known_titles=TENANT)
    assert s.cites_gold is True and s.has_facts is True
    assert s.grounded is False, "미검증 인용이 하나라도 있으면 근거가 확인된 답이 아니다"
    assert s.outcome != "correct", "근거가 확인되지 않은 답을 맞았다고 세면 ADR-0002 가 무너진다"


def test_the_two_definitions_of_correct_are_one():
    """`outcome == 'correct'` 와 `ok` 가 갈라지면 리포트가 자기와 모순된다 — 양쪽에서 건다."""
    cases = [
        ([_cited("정답 문서")], {"정답 문서"}, [["100"]]),                    # 정상
        ([_cited("정답 문서", verified=False)], {"정답 문서"}, [["100"]]),    # 미검증
        ([], {"정답 문서"}, [["100"]]),                                       # 인용 0개
        ([_cited("다른 문서")], {"정답 문서"}, [["100"]]),                    # gold 아님
        ([_cited("정답 문서")], {"정답 문서"}, [["없는말"]]),                 # 사실 불충족
    ]
    for citations, gold, must in cases:
        s = score_answer("q", "최대 100 곡입니다 [출처: 문서]", citations, gold, must,
                         known_titles=TENANT)
        assert (s.outcome == "correct") == s.ok, f"{citations} → {s.outcome} vs ok={s.ok}"


def test_a_document_already_judged_not_gold_is_incorrect():
    """판정의 **음성 절반**이 없으면 같은 건이 매 실행 되살아나 게이트가 절대 안 닫힌다."""
    s = score_answer("q", "최대 100 곡입니다 [출처: 판정 끝난 무관한 문서]",
                     [_cited("판정 끝난 무관한 문서")], {"정답 문서"}, [["100"]],
                     not_gold_titles={"판정 끝난 무관한 문서"}, known_titles=TENANT)
    assert s.outcome == "incorrect" and s.unjudged == []


def test_a_citation_that_resolves_to_nothing_stays_incorrect():
    """테넌트에 없는 제목은 판정할 대상이 없다 — 지어낸 출처와 구별되지 않는다."""
    s = score_answer("q", "최대 100 곡입니다 [출처: 세상에 없는 문서]",
                     [_cited("세상에 없는 문서")], {"정답 문서"}, [["100"]], known_titles=TENANT)
    assert s.outcome == "incorrect"


def test_an_unverified_citation_is_never_adjudicable():
    s = score_answer("q", "최대 100 곡입니다 [출처: 같은 사실을 적은 다른 문서]",
                     [_cited("같은 사실을 적은 다른 문서", verified=False)],
                     {"정답 문서"}, [["100"]], known_titles=TENANT)
    assert s.grounded is False and s.outcome == "incorrect"


def test_an_unjudged_document_is_surfaced_even_when_the_answer_is_correct():
    """정답 문서와 미판정 문서를 함께 인용한 답변은 `correct` 지만, 미판정 목록은 남아야 한다.
    안 그러면 미판정 풀이 조용히 자라고 '게이트가 정직함을 지킨다' 는 방어가 거짓이 된다."""
    s = score_answer("q", "최대 100 곡입니다 [출처: 정답 문서][출처: 같은 사실을 적은 다른 문서]",
                     [_cited("정답 문서"), _cited("같은 사실을 적은 다른 문서")],
                     {"정답 문서"}, [["100"]], known_titles=TENANT)
    assert s.outcome == "correct"
    assert s.unjudged == ["같은 사실을 적은 다른 문서"]


def test_the_aggregate_keeps_unadjudicated_out_of_incorrect():
    scores = [
        score_answer("a", "100 [출처: 정답 문서]", [_cited("정답 문서")], {"정답 문서"}, [["100"]],
                     known_titles=TENANT),
        score_answer("b", "100 [출처: 같은 사실을 적은 다른 문서]",
                     [_cited("같은 사실을 적은 다른 문서")], {"정답 문서"}, [["100"]],
                     known_titles=TENANT),
    ]
    a = aggregate(scores)
    assert a["outcomes"]["unadjudicated"] == 1 and a["outcomes"]["incorrect"] == 0
    assert a["unadjudicated_qids"] == ["b"]
    assert a["adjudication_candidates"] == {"b": ["같은 사실을 적은 다른 문서"]}


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
    assert a["outcomes"] == {"correct": 1, "incorrect": 1, "abstained": 1,
                             "unadjudicated": 0, "unmeasurable": 0}
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
