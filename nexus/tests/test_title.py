"""문서 제목 파생: frontmatter title → 본문 첫 헤딩 → 파일명 폴백.

라이브 실증: notion deposit 문서들이 frontmatter title·선두 H1 없이 적재돼 제목이
`ext-notion-<uuid>.md`(파일명)로 떨어졌다 — 검색답변 인용·근거패널 가독성 저하.
본문 첫 헤딩은 UUID보다 훨씬 읽을 만한 제목 프록시다. System decides: 결정론 파싱.
"""

from __future__ import annotations

from nexus.ingest.title import derive_title, first_heading


def test_frontmatter_title_wins():
    assert derive_title({"title": "진짜 제목"}, "# 헤딩\n본문", "file.md") == "진짜 제목"


def test_blank_frontmatter_title_ignored():
    assert derive_title({"title": "   "}, "## 섹션 A\n본문", "file.md") == "섹션 A"


def test_first_heading_used_when_no_frontmatter_title():
    assert (
        derive_title({}, "## 1. Entity 란 무엇인가?\n본문", "ext-notion-x.md")
        == "1. Entity 란 무엇인가?"
    )


def test_first_heading_skips_leading_blank_lines():
    assert first_heading("\n\n# Top\nrest") == "Top"


def test_first_heading_any_level():
    assert first_heading("### deep heading") == "deep heading"


def test_first_heading_strips_trailing_hashes():
    assert first_heading("## 닫힘형 헤딩 ##") == "닫힘형 헤딩"


def test_first_heading_strips_inline_markdown():
    assert first_heading("# 1) 트래픽 처리 **마인드맵**") == "1) 트래픽 처리 마인드맵"


def test_first_heading_unwraps_link():
    assert first_heading("## [엔티티 개념](https://x/y) 정리") == "엔티티 개념 정리"


def test_no_heading_falls_back_to_filename():
    assert derive_title({}, "헤딩 없는 그냥 문단입니다.", "ext-notion-x.md") == "ext-notion-x.md"


def test_first_heading_none_when_absent():
    assert first_heading("no heading here\njust text") is None
