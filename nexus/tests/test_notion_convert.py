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
