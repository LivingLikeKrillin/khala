from nexus.ingest.sources.notion_convert import blocks_to_markdown


def _rt(text, **ann):
    return {
        "type": "text",
        "text": {"content": text},
        "annotations": {"bold": False, "italic": False, "code": False, **ann},
        "plain_text": text,
        "href": None,
    }


def test_heading_paragraph_list():
    blocks = [
        {"type": "heading_1", "heading_1": {"rich_text": [_rt("제목")]}},
        {"type": "paragraph", "paragraph": {"rich_text": [_rt("본문 ")]}},
        {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [_rt("항목")]}},
    ]
    md, imgs = blocks_to_markdown(blocks)
    assert "# 제목" in md and "- 항목" in md and imgs == 0


def test_bold_and_code_annotations():
    blocks = [{"type": "paragraph", "paragraph": {"rich_text": [_rt("강조", bold=True)]}}]
    md, _ = blocks_to_markdown(blocks)
    assert "**강조**" in md


def test_image_is_counted_and_placeholdered():
    blocks = [
        {"type": "image", "image": {"type": "external", "external": {"url": "http://x/y.png"}}}
    ]
    md, imgs = blocks_to_markdown(blocks)
    # URL 은 더 이상 본문에 안 들어간다 — 1시간 만료 링크이고 청킹을 망가뜨렸다.
    assert imgs == 1 and "y.png" not in md and "![" in md


def test_code_block():
    blocks = [{"type": "code", "code": {"language": "java", "rich_text": [_rt("int x = 5;")]}}]
    md, _ = blocks_to_markdown(blocks)
    assert "```" in md and "int x = 5;" in md


# ── 캡션은 본문이다 (정책 문서 적재 준비) ─────────────────────────────


def _md(blocks):
    from nexus.ingest.sources.notion_convert import blocks_to_markdown
    return blocks_to_markdown(blocks)


def _rich(text):
    return [{"plain_text": text, "annotations": {}}]


def test_an_image_caption_becomes_searchable_text():
    """정책 문서의 표는 흔히 스크린샷이고, 그 문서가 쓰는 어휘는 캡션에 있다.

    예전엔 alt 를 `image` 로 고정해 캡션을 버렸다 — 그러면 그림뿐인 페이지가 **검색 텍스트 0** 인
    얇은 문서가 되고, 얇은 건지 그림뿐인 건지 아무도 모른다.
    """
    md, images = _md([{"type": "image", "image": {
        "external": {"url": "https://x/y.png"},
        "caption": _rich("그림 3. 환불 승인 흐름")}}])
    assert images == 1
    assert "그림 3. 환불 승인 흐름" in md
    assert "https://x/y.png" not in md, (
        "URL 은 버린다 — Notion 이 주는 것은 1시간 만료 서명 링크라 저장해도 죽은 값이고, "
        "공백이 없어 청킹 상한을 통째로 무력화했다(2026-08-08 실측: 한 청크의 99%)")


def test_an_image_without_a_caption_still_renders_and_counts():
    md, images = _md([{"type": "image", "image": {"file": {"url": "https://x/z.png"}}}])
    assert images == 1
    assert md.strip() == "![]()"          # 캡션 없음 + URL 제거


def test_a_file_or_pdf_block_keeps_its_caption():
    """이 블록들은 `rich_text` 가 없고 글이 `caption` 에 담긴다 — rich_text 만 보면 사라진다."""
    for bt in ("file", "pdf", "video", "embed", "bookmark"):
        md, _ = _md([{"type": bt, bt: {"caption": _rich(f"{bt} 캡션 내용")}}])
        assert f"{bt} 캡션 내용" in md, bt


def test_a_block_with_neither_text_nor_caption_is_still_dropped():
    """무손실 원칙은 '텍스트가 있으면 살린다' 이지 '빈 블록도 남긴다' 가 아니다."""
    md, _ = _md([{"type": "unsupported_thing", "unsupported_thing": {}}])
    assert md.strip() == ""


def test_rich_text_wins_over_caption_when_both_exist():
    md, _ = _md([{"type": "callout", "callout": {
        "rich_text": _rich("본문"), "caption": _rich("캡션")}}])
    assert "본문" in md and "캡션" not in md


# ── 정책 문서의 본문은 표·속성에도 있다 ─────────────────────────────────────


def test_a_table_becomes_a_markdown_table():
    """정책 문서는 표가 본문이다. 못 읽으면 규칙이 통째로 사라지는데 문서는 얇아 보일 뿐이다."""
    from nexus.ingest.sources.notion_convert import blocks_to_markdown

    children = {"t1": [
        {"type": "table_row", "table_row": {"cells": [_rich("구분"), _rich("허용")]}},
        {"type": "table_row", "table_row": {"cells": [_rich("비로그인"), _rich("입장 불가")]}},
    ]}
    md, _ = blocks_to_markdown([{"type": "table", "id": "t1", "table": {}}],
                               lambda bid: children[bid])
    assert "| 구분 | 허용 |" in md
    assert "| 비로그인 | 입장 불가 |" in md
    assert "| --- | --- |" in md.replace(" ---  |", " --- |")


def test_a_table_is_skipped_when_children_cannot_be_fetched():
    """호출자가 API 를 안 들고 있으면 얕게 훑는다 — 죽지는 않는다."""
    from nexus.ingest.sources.notion_convert import blocks_to_markdown

    md, _ = blocks_to_markdown([{"type": "table", "id": "t1", "table": {}}])
    assert md.strip() == ""


def test_a_toggle_keeps_what_is_folded_inside_it():
    from nexus.ingest.sources.notion_convert import blocks_to_markdown

    children = {"g1": [{"type": "paragraph", "paragraph": {"rich_text": _rich("접힌 규칙")}}]}
    md, _ = blocks_to_markdown(
        [{"type": "toggle", "id": "g1", "toggle": {"rich_text": _rich("자세히")}}],
        lambda bid: children[bid])
    assert "자세히" in md and "접힌 규칙" in md


def test_database_row_properties_become_the_body():
    """DB 행은 블록이 0개인 경우가 흔하다 — 내용이 전부 속성에 있다."""
    from nexus.ingest.sources.notion_convert import properties_to_markdown

    md = properties_to_markdown({
        "개정 내용": {"type": "title", "title": _rich("영화관 모드 추가")},
        "날짜": {"type": "date", "date": {"start": "2025-01-23"}},
        "Epic": {"type": "multi_select", "multi_select": [{"name": "[파티룸] 전광판"}]},
        "바로가기": {"type": "rich_text", "rich_text": _rich("4-7. 영화관/전체 모드")},
        "담당자": {"type": "people", "people": []},
    })
    assert "**날짜**: 2025-01-23" in md
    assert "**Epic**: [파티룸] 전광판" in md
    assert "4-7. 영화관/전체 모드" in md
    assert "영화관 모드 추가" not in md, "제목은 문서 제목으로 쓰이므로 본문에 중복시키지 않는다"
    assert "담당자" not in md, "빈 값은 줄을 만들지 않는다"


def test_checkbox_and_select_properties_are_readable_words():
    """정책 값이 ☑️/체크박스로 들어간다 — '예/아니오' 로 적어야 검색에 걸린다."""
    from nexus.ingest.sources.notion_convert import properties_to_markdown

    md = properties_to_markdown({
        "비로그인": {"type": "checkbox", "checkbox": False},
        "상태": {"type": "status", "status": {"name": "적용중"}},
        "정책": {"type": "select", "select": {"name": "파티룸 Entity"}},
    })
    assert "**비로그인**: 아니오" in md
    assert "**상태**: 적용중" in md
    assert "**정책**: 파티룸 Entity" in md


# ── 이미지 URL 은 본문이 아니다 (2026-08-08) ─────────────────────────────────
#
# Notion 이 주는 이미지 URL 은 1시간 뒤 만료되는 S3 서명 링크다. 저장해도 죽은 값이면서, 공백이
# 없어서 청킹을 망가뜨린다. 실측: 가장 큰 청크 18,839자 중 18,623자(99%)가 이미지 URL 11개였고,
# 토큰 추정기가 그것을 144토큰으로 세어 상한(1100)이 안 걸렸다.

_LONG_URL = ("https://prod-files-secure.s3.us-west-2.amazonaws.com/525a6ac1/"
             + "X-Amz-Signature=" + "a" * 1600)


def _image(caption=None, url=_LONG_URL):
    b = {"type": "image", "image": {"file": {"url": url}}}
    if caption is not None:
        b["image"]["caption"] = [{"type": "text", "text": {"content": caption},
                                  "plain_text": caption, "annotations": {}}]
    return b


def test_the_image_url_never_reaches_the_body():
    md, n = blocks_to_markdown([_image("그림 3. 환불 승인 흐름")])
    assert n == 1
    assert "amazonaws" not in md and "X-Amz" not in md
    assert len(md) < 200, f"URL 이 남아 있다: {len(md)}자"


def test_the_caption_is_still_kept():
    md, _ = blocks_to_markdown([_image("그림 3. 환불 승인 흐름")])
    assert "그림 3. 환불 승인 흐름" in md


def test_an_image_without_a_caption_still_leaves_a_mark():
    """캡션이 없어도 그림이 있었다는 사실은 남는다 — 얇은 문서 판정이 그것을 본다."""
    md, n = blocks_to_markdown([_image(None)])
    assert n == 1 and "![" in md


def test_a_page_of_screenshots_becomes_short_rather_than_huge():
    """이것이 청킹을 망가뜨리던 모양이다 — URL 열한 개짜리 페이지."""
    md, n = blocks_to_markdown([_image(f"캡션 {i}") for i in range(11)])
    assert n == 11
    assert len(md) < 500, f"{len(md)}자 — URL 이 아직 본문에 있다"
