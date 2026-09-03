"""근거 창의 얼마가 우리 자기 문서인가 (`OPEN.md` A57).

⛔ 이 검사가 지키는 것 하나: **세는 단위가 문서가 아니라 청크여야 한다.** 실측 2026-09-03 에
khala 리포 문서는 14건뿐인데 그 14건이 청크 197 · 14만 자를 싣고, 조직 문서 112건이 청크 269 ·
11만 자를 싣는다. 문서로 세면 "우리가 소수" 로 읽히고 정반대 결론이 나온다.
"""

from __future__ import annotations

from scripts.self_document_crowding import crowding, doc_key, population, verdict_rows

#: 합성 키다. **실제 페이지 ID 를 추적 파일에 넣지 않는다** — 공개 리포이고
#: `scripts/fingerprint_scan.py` 가 막는다(2026-09-03 에 실제로 걸렸다: 진짜 ID 를 넣었다가
#: CI 두 개가 떨어졌다). 판정은 접두사만 보므로 ID 모양일 필요가 없다.
ORG = "ext-notion-synthetic-doc.md"
OURS = "KOREAN_SEARCH_QUALITY.md"


def test_a_notion_document_is_the_organisations():
    assert population(ORG) == "org"


def test_a_repo_document_is_ours():
    assert population(OURS) == "repo"
    assert population("PIPELINE_SPEC.md") == "repo"


def test_the_tenant_prefix_is_stripped_but_the_rest_is_not():
    """키에 콜론이 또 있어도 첫 것만 뗀다 — 더 떼면 다른 문서가 된다."""
    assert doc_key("default:" + ORG) == ORG
    assert doc_key("default:a:b.md") == "a:b.md"
    assert doc_key("") == ""


# ── 창 비율 ──────────────────────────────────────────────────────────────────

def test_a_window_of_only_our_documents_is_one():
    assert crowding([OURS, "PIPELINE_SPEC.md"]) == 1.0


def test_a_window_with_none_of_ours_is_zero():
    assert crowding([ORG, ORG]) == 0.0


def test_a_mixed_window_is_the_fraction():
    assert crowding([OURS, ORG, ORG, ORG]) == 0.25


def test_an_empty_window_does_not_divide():
    """0으로 나누면 탐침이 죽고, 죽은 탐침은 '문제 없음' 과 구별이 안 된다."""
    assert crowding([]) == 0.0


# ── 요약 ─────────────────────────────────────────────────────────────────────

def _r(qid, crowd, gold_pop="org", in_window=True):
    return {"id": qid, "crowding": crowd, "gold_pop": gold_pop, "gold_in_window": in_window}


def test_a_full_window_is_counted_separately_from_a_majority_one():
    """10/10 과 6/10 을 한 칸에 담으면 이 항목의 실제 모양이 사라진다."""
    v = verdict_rows([_r("a", 1.0), _r("b", 0.6), _r("c", 0.2)])
    assert v["full_windows"] == 1 and v["majority_windows"] == 2


def test_a_full_window_also_counts_as_a_majority():
    assert verdict_rows([_r("a", 1.0)])["majority_windows"] == 1


def test_exactly_half_is_not_a_majority():
    """경계는 한쪽으로 정해 둔다 — 정하지 않으면 실행마다 다르게 읽힌다."""
    assert verdict_rows([_r("a", 0.5)])["majority_windows"] == 0


def test_a_clean_window_is_counted():
    assert verdict_rows([_r("a", 0.0)])["clean_windows"] == 1


def test_only_org_gold_queries_are_asked_whether_the_gold_survived():
    """gold 가 우리 문서인 질의에서 창이 우리 문서로 차는 것은 당연하다 — 섞으면 수가 부푼다."""
    v = verdict_rows([_r("a", 1.0, "repo", False), _r("b", 1.0, "org", False)])
    assert v["org_gold"] == 1 and v["org_gold_missed"] == 1


def test_the_crowded_and_missed_pair_is_counted_together():
    """⭐ 이 항목이 실제로 주장하는 것은 이 교집합이다 — 창이 우리 것으로 차면서 gold 를 밀어냈다."""
    v = verdict_rows([_r("a", 1.0, "org", False),   # 찼고 밀어냈다
                      _r("b", 0.2, "org", False),   # 밀어냈지만 안 찼다
                      _r("c", 1.0, "org", True)])   # 찼지만 gold 는 살아 있다
    assert v["org_gold_missed"] == 2 and v["org_gold_missed_and_crowded"] == 1
