"""짝 문서 확장 — 설계와 구현 계획을 파일 이름으로 잇는다.

⛔ 지켜야 할 성질 둘: **짝을 정확히 잇는다**, 그리고 **무리를 통째로 싣지 않는다.**
둘째가 없으면 같은 슬러그에 문서가 셋 붙는 날 근거가 문서 더미가 된다.
"""

from __future__ import annotations

from nexus.search.pairs import mates_from, slug_of


def test_a_design_and_its_plan_share_a_slug():
    spec = "design_docs:superpowers/specs/2026-05-09-crew-grade-host-invariant-design.md"
    plan = "design_docs:superpowers/plans/2026-05-09-crew-grade-host-invariant.md"
    assert slug_of(spec) == slug_of(plan) == "2026-05-09-crew-grade-host-invariant"


def test_documents_outside_the_two_folders_keep_their_own_slug():
    """`archive/` 나 루트 문서는 짝 규칙의 대상이 아니다 — 슬러그가 겹치면 안 된다."""
    assert slug_of("design_docs:archive/ERD_DATA_LAYER_CHANGELOG.md") != slug_of(
        "design_docs:superpowers/plans/ERD_DATA_LAYER_CHANGELOG.md")


def test_a_pair_is_linked_both_ways():
    rows = [{"rid": "a", "source_uri": "t:superpowers/specs/2026-01-01-x-design.md"},
            {"rid": "b", "source_uri": "t:superpowers/plans/2026-01-01-x.md"}]
    assert mates_from(rows) == {"a": ["b"], "b": ["a"]}


def test_a_lone_document_has_no_mate():
    rows = [{"rid": "a", "source_uri": "t:superpowers/specs/2026-01-01-x-design.md"}]
    assert mates_from(rows) == {}


def test_three_documents_on_one_slug_are_not_a_pair():
    """⛔ 대조군. 셋이면 그것은 짝이 아니라 무리이고, 무리를 통째로 실으면 근거가 부푼다."""
    rows = [{"rid": "a", "source_uri": "t:superpowers/specs/2026-01-01-x-design.md"},
            {"rid": "b", "source_uri": "t:superpowers/plans/2026-01-01-x.md"},
            {"rid": "c", "source_uri": "t:superpowers/plans/2026-01-01-x.md"}]
    assert mates_from(rows) == {}
