"""`source_kind_for` — 유도 규칙 자체. DB 없이 돈다."""

from __future__ import annotations

import pytest

from nexus.documents.filters import ORIGIN_FILTERS
from nexus.documents.origin import source_kind_for


@pytest.mark.parametrize("uri,kind", [
    ("default:ext-notion-742fb34f-38a5-4d5c-bdeb-7d754774a61f.md", "wiki"),
    ("default:ext-notion-not-a-uuid.md", "wiki"),   # id 가 깨져도 출처는 Notion 이다
    ("default:uploads/policy.pdf.md", "file"),
    ("default:docs/API_CONTRACT.md", "git"),
    ("API_CONTRACT.md", "git"),                      # 테넌트 접두가 없어도
])
def test_the_uri_already_says_where_it_came_from(uri, kind):
    assert source_kind_for(uri) == kind


def test_every_origin_has_a_kind():
    """`derive_origin` 에 갈래가 늘면 여기가 **KeyError 로** 터져야 한다 — 조용히 'git' 이
    되면 새 출처가 리포 파일로 위장한다."""
    from nexus.documents.origin import _KIND_BY_ORIGIN

    assert set(_KIND_BY_ORIGIN) == set(ORIGIN_FILTERS), (
        "저장하는 어휘와 콘솔이 거르는 어휘가 갈라졌다")
