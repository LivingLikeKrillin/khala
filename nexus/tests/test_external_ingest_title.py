"""외부 ingest sink 는 CSF 의 `title` 을 버렸다 — 본문만 임시 파일로 쓴다.

그래서 Notion 페이지 이름을 제대로 읽어 CSF 에 실어도(`build_csf` 는 싣는다), `run_ingest` 는
그 파일의 **첫 헤딩**에서 제목을 다시 만들었다. `Index` 페이지가 `Access 방식` 으로 들어간 이유다.

`derive_title` 은 이미 frontmatter title 을 첫 헤딩보다 우선한다. sink 가 frontmatter 를
써 주기만 하면 된다.
"""

from __future__ import annotations

import pytest

from nexus.a2a.server import _csf_to_markdown_file


def test_the_body_is_written_with_a_frontmatter_title():
    text = _csf_to_markdown_file({"title": "Index", "body": "## Access 방식\n\n본문"})

    assert text.startswith("---\n")
    assert "title: Index" in text
    assert text.rstrip().endswith("본문")


def test_a_title_containing_yaml_metacharacters_survives():
    """`선두 컬럼: 제약 사항` 처럼 콜론이 든 제목이 YAML 을 깨뜨리면 안 된다."""
    import yaml

    text = _csf_to_markdown_file({"title": "선두 컬럼: 제약 #1", "body": "본문"})
    fm = text.split("---\n")[1]

    assert yaml.safe_load(fm)["title"] == "선두 컬럼: 제약 #1"


def test_no_title_writes_no_frontmatter():
    """제목이 없으면 예전처럼 본문만 쓴다 — 첫 헤딩 폴백이 살아 있어야 한다."""
    assert _csf_to_markdown_file({"body": "## 제목\n\n본문"}) == "## 제목\n\n본문"


@pytest.mark.parametrize("body", ["", "   "])
def test_an_empty_body_still_produces_the_frontmatter(body):
    text = _csf_to_markdown_file({"title": "T", "body": body})
    assert "title: T" in text


def test_derive_title_prefers_the_frontmatter_over_the_first_heading():
    from nexus.ingest.title import derive_title

    assert derive_title({"title": "Index"}, "## Access 방식", "fallback") == "Index"
