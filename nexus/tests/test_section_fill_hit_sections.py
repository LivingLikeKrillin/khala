"""히트가 앉은 **절**을 완성한다 — 정답이 와도 그것을 해석할 문장이 안 오던 자리.

**왜 (2026-08-26 라이브).** 어떤 표가 낡았다고 알리는 문단이 그 표와 **같은 절**에 있었는데
근거에 못 들어왔다. 문서 단위 채움의 트리거가 *포화*(다양성 상한을 꽉 채움)인데 그 문서는
히트가 3개(상한 5)라 미달이었다. 결과: 답변이 낡은 숫자를 정본으로 읽었고, 다음 판에서는
*"근거만으로는 확정할 수 없다"* 로 물러섰다.

**Recall@10 은 정답 문서가 왔는지만 측정한다.** 그것을 해석할 문장이 함께 왔는지는 안 측정한다 —
오늘 같은 모양을 세 번째로 만났다(절·요약·정정).
"""

from __future__ import annotations

from nexus.search.section_fill import FILL_TOP_HITS, MAX_SECTION_CHUNKS, hit_sections


class _H:
    def __init__(self, doc_rid, section_path):
        self.doc_rid, self.section_path = doc_rid, section_path


def test_sections_come_from_the_hits_not_from_a_choice():
    """절을 **고르지 않는다** — 히트가 앉은 절을 그대로 쓴다.

    `fill_for_docs` 는 "어느 절을 고를지가 이 코드가 못 하는 일" 이라 적고 큰 문서를 통째로
    뺀다. 그 판정은 여전히 옳고, 여기서도 고르지 않는다: 선택은 랭킹이 이미 했다.
    """
    hits = [_H("doc_a", "1. 개요"), _H("doc_a", "1. 개요"), _H("doc_b", "root")]
    assert hit_sections(hits) == [("doc_a", "1. 개요"), ("doc_b", "root")]


def test_only_the_top_hits_get_their_section_completed():
    """상위 몇 개만. 전부 완성하면 근거가 두 배가 된다(33문항 실측 +102% → +38%).

    자르는 자리는 **랭킹 순서**이고 숫자 하나로 드러나 있다 — 또 고르는 것이 아니다.
    """
    hits = [_H(f"doc_{i}", f"sec_{i}") for i in range(10)]
    got = hit_sections(hits)
    assert len(got) == FILL_TOP_HITS
    assert got[0] == ("doc_0", "sec_0")


def test_empty_section_path_is_treated_as_root():
    """`section_path` 가 비면 `root` 다 — DB 기본값과 같아야 조회가 안 빗나간다."""
    assert hit_sections([_H("doc_a", "")]) == [("doc_a", "root")]


def test_the_caps_are_declared():
    """상한이 상수로 드러나 있어야 한다 — 값을 바꾸려는 다음 사람이 코드를 뒤지지 않도록."""
    assert MAX_SECTION_CHUNKS >= 1
    assert FILL_TOP_HITS >= 1
