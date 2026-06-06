from specledger.frontmatter import split, render


def test_split_extracts_meta_and_body():
    text = "---\nid: ADR-0001\nstatus: proposed\n---\n# Body\ntext\n"
    meta, body = split(text)
    assert meta["id"] == "ADR-0001"
    assert meta["status"] == "proposed"
    assert body == "# Body\ntext\n"


def test_split_no_frontmatter_returns_empty_meta():
    meta, body = split("no frontmatter here")
    assert meta == {}
    assert body == "no frontmatter here"


def test_render_roundtrips():
    meta = {"id": "SPEC-x", "status": "draft"}
    body = "# Title\n\ncontent\n"
    meta2, body2 = split(render(meta, body))
    assert meta2 == meta
    assert body2.strip() == body.strip()


def test_render_preserves_key_order():
    meta = {"id": "ADR-0001", "title": "t", "status": "accepted"}
    out = render(meta, "b")
    assert out.index("id:") < out.index("title:") < out.index("status:")
