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
    assert imgs == 1 and "y.png" in md


def test_code_block():
    blocks = [{"type": "code", "code": {"language": "java", "rich_text": [_rt("int x = 5;")]}}]
    md, _ = blocks_to_markdown(blocks)
    assert "```" in md and "int x = 5;" in md


# ── 캡션은 본문이다 (PFPlay 정책 문서 적재 준비) ─────────────────────────────


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
    assert "https://x/y.png" in md, "URL(출처)은 유지한다"


def test_an_image_without_a_caption_still_renders_and_counts():
    md, images = _md([{"type": "image", "image": {"file": {"url": "https://x/z.png"}}}])
    assert images == 1
    assert md.strip() == "![image](https://x/z.png)"


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
