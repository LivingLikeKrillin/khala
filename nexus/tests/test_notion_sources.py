"""소스 콘솔의 순수 로직 — DB/네트워크 없음.

SPEC-nexus-notion-source-console §4.1(URL→id) · §4.4(plan_hash).
"""

from __future__ import annotations

import pytest

from nexus.sources.notion_sources import parse_notion_ref
from nexus.sources.plan_hash import compute_plan_hash


# ── §4.1 URL / id 정규화 ──────────────────────────────────────────────────────

_DASHED = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
_BARE = "1a2b3c4d5e6f4a7b8c9d0e1f2a3b4c5d"


@pytest.mark.parametrize(
    "ref",
    [
        _DASHED,
        _BARE,
        _BARE.upper(),
        f"https://www.notion.so/{_BARE}",
        f"https://www.notion.so/My-Team-Page-{_BARE}",
        f"https://notion.so/workspace/{_BARE}?pvs=4",
        f"  https://www.notion.so/{_DASHED}  ",
    ],
)
def test_every_way_a_human_pastes_a_notion_page_yields_the_same_id(ref):
    assert parse_notion_ref(ref) == _DASHED


@pytest.mark.parametrize("ref", ["", "   ", "https://www.notion.so/", "not-a-page", "https://example.com/x"])
def test_unparseable_refs_are_rejected(ref):
    with pytest.raises(ValueError):
        parse_notion_ref(ref)


# ── §4.4 plan_hash ────────────────────────────────────────────────────────────

def _plan(prune=(), revive=(), roots=("rootA",)):
    return compute_plan_hash(walked_roots=list(roots), prune=list(prune), revive=list(revive))


def test_plan_hash_is_order_independent():
    a = _plan(prune=[("d1", "h1"), ("d2", "h2")])
    b = _plan(prune=[("d2", "h2"), ("d1", "h1")])
    assert a == b


def test_plan_hash_changes_when_walked_roots_change():
    """같은 rid 집합이라도 걸은 root 가 다르면 다른 계획이다 (I-003)."""
    assert _plan(prune=[("d1", "h1")], roots=("rootA",)) != _plan(prune=[("d1", "h1")], roots=("rootA", "rootB"))


def test_plan_hash_changes_when_a_document_content_changes():
    """rid 는 그대로인데 본문이 바뀌었다면 미리보기 당시의 계획이 아니다 (I-003)."""
    assert _plan(prune=[("d1", "h1")]) != _plan(prune=[("d1", "h2")])


def test_plan_hash_distinguishes_prune_from_revive():
    """같은 문서를 지우는 계획과 되살리는 계획이 같은 해시를 가지면 안 된다."""
    assert _plan(prune=[("d1", "h1")]) != _plan(revive=[("d1", "h1")])


def test_empty_plan_has_a_stable_hash():
    assert _plan() == _plan()
    assert _plan() != _plan(prune=[("d1", "h1")])
