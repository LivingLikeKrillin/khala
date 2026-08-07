"""답변 품질 채점기에 이가 있는가.

채점기가 무엇이든 통과시키면 "답변 품질 100%" 라는 숫자가 나오고, 그 숫자는 아무것도 안 지킨다.
그래서 여기서 재는 것은 대부분 **통과하면 안 되는 입력**이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.ko_eval_answer_quality import aggregate, score_answer  # noqa: E402

GOLD = {"플레이리스트 정책"}


def _cite(title, verified=True):
    return {"title": title, "section": "", "verified": verified}


def test_a_good_answer_passes_all_three():
    s = score_answer("q", "한 플레이리스트에는 최대 100 곡까지 담을 수 있습니다 [출처: 플레이리스트 정책]",
                     [_cite("플레이리스트 정책")], GOLD, [["100"], ["곡", "트랙"]])
    assert (s.grounded, s.cites_gold, s.has_facts, s.ok) == (True, True, True, True)


def test_an_answer_with_no_citation_is_not_grounded():
    """**가장 중요한 대조군.** 미검증 인용 수만 보면 0 이라 통과한다 — 아무것도 인용하지 않는 것이
    가장 쉬운 만점이 된다. ADR-0002 가 막으려던 형태다."""
    s = score_answer("q", "최대 100 곡입니다.", [], GOLD, [["100"]])
    assert s.grounded is False and s.n_citations == 0
    assert s.ok is False


def test_a_fabricated_source_fails_grounding():
    s = score_answer("q", "…[출처: 있지도 않은 문서]", [_cite("있지도 않은 문서", verified=False)],
                     GOLD, [["100"]])
    assert s.grounded is False and s.unverified == 1


def test_citing_the_wrong_document_is_grounded_but_not_gold():
    """출처를 지어내지는 않았지만 엉뚱한 문서로 답한 경우 — 둘은 다른 실패다."""
    s = score_answer("q", "…[출처: 로그인 정책]", [_cite("로그인 정책")], GOLD, [["100"]])
    assert s.grounded is True and s.cites_gold is False


def test_retrieval_can_be_right_while_the_answer_is_wrong():
    """정답 문서를 인용하고도 숫자를 틀리는 경우 — 검색만 재면 안 보이는 실패다."""
    s = score_answer("q", "최대 50 곡까지 담을 수 있습니다 [출처: 플레이리스트 정책]",
                     [_cite("플레이리스트 정책")], GOLD, [["100"]])
    assert (s.grounded, s.cites_gold) == (True, True)
    assert s.has_facts is False and s.ok is False


def test_a_fact_may_be_written_more_than_one_way():
    """항목 안은 후보 중 하나면 된다 — 아니면 답변의 표현을 재게 된다."""
    for surface in ("100곡", "100 곡", "100개의 트랙"):
        s = score_answer("q", f"{surface} [출처: 플레이리스트 정책]",
                         [_cite("플레이리스트 정책")], GOLD, [["100"], ["곡", "트랙"]])
        assert s.has_facts, surface


def test_every_fact_must_appear_not_just_one():
    s = score_answer("q", "100 이라고만 적힌 답 [출처: 플레이리스트 정책]",
                     [_cite("플레이리스트 정책")], GOLD, [["100"], ["지갑연동"]])
    assert s.facts == [True, False] and s.has_facts is False


def test_whitespace_differences_do_not_hide_a_fact():
    s = score_answer("q", "최대   100\n곡 [출처: 플레이리스트 정책]",
                     [_cite("플레이리스트 정책")], GOLD, [["100 곡"]])
    assert s.has_facts is True


def test_an_english_identifier_keeps_its_case():
    """소문자화하면 `NexusResponse` 와 `nexusresponse` 가 같아진다 — 식별자는 대소문자가 뜻이다."""
    ok = score_answer("q", "응답은 NexusResponse 로 감쌉니다 [출처: t]", [_cite("t")], {"t"},
                      [["NexusResponse"]])
    bad = score_answer("q", "응답은 nexusresponse 로 감쌉니다 [출처: t]", [_cite("t")], {"t"},
                       [["NexusResponse"]])
    assert ok.has_facts is True and bad.has_facts is False


def test_an_unmeasurable_query_is_not_counted_as_passing():
    """`must_contain` 이 없으면 '통과' 가 아니라 **잴 것이 없다** — 집계가 그 둘을 나눠야 한다."""
    s = score_answer("q", "무언가 [출처: 플레이리스트 정책]", [_cite("플레이리스트 정책")], GOLD, [])
    assert s.has_facts is False, "빈 조건을 all() 이 참으로 만들면 안 잰 질의가 만점이 된다"
    a = aggregate([s])
    assert a["facts_measurable"] == 0 and a["facts_present"] == 0


def test_the_aggregate_separates_the_three_failures():
    scores = [
        score_answer("a", "100 [출처: 플레이리스트 정책]", [_cite("플레이리스트 정책")], GOLD, [["100"]]),
        score_answer("b", "100", [], GOLD, [["100"]]),                       # 인용 없음
        score_answer("c", "100 [출처: 로그인 정책]", [_cite("로그인 정책")], GOLD, [["100"]]),  # 오답 문서
        score_answer("d", "50 [출처: 플레이리스트 정책]", [_cite("플레이리스트 정책")], GOLD, [["100"]]),
    ]
    a = aggregate(scores)
    assert a["queries"] == 4
    assert a["grounded"] == 3 and a["no_citation_at_all"] == 1
    assert a["cites_gold"] == 2
    assert a["facts_present"] == 3          # d 만 사실 실패
    assert a["all_three"] == 1
    assert a["failed"] == ["b", "c", "d"]
