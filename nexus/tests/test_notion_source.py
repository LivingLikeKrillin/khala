from nexus.ingest.sources.base import PageRef
from nexus.ingest.sources.notion import NotionSource


class FakeClient:
    """client.blocks.children.list(block_id=..., start_cursor=...) 형태를 흉내."""

    def __init__(self):
        self.blocks = type("B", (), {"children": self})()

    def list(self, block_id, start_cursor=None):
        return {
            "results": [
                {
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [
                            {
                                "plain_text": "준회원 정책",
                                "annotations": {},
                                "text": {"content": "준회원 정책"},
                            }
                        ]
                    },
                }
            ],
            "has_more": False,
            "next_cursor": None,
        }


def test_fetch_markdown_builds_frontmatter_and_counts():
    src = NotionSource(
        client=FakeClient(), roots=[], tenant="default",
        classification="INTERNAL", owner="@planner",
    )
    ref = PageRef(id="pid1", url="https://notion.so/pid1", last_edited="2026-06-06T00:00:00Z")
    cd = src.fetch_markdown(ref)
    assert "# 준회원 정책" in cd.markdown
    fm = cd.frontmatter
    assert fm["source_kind"] == "wiki"
    assert fm["origin_url"] == "https://notion.so/pid1"
    assert fm["origin_last_edited"] == "2026-06-06T00:00:00Z"
    assert fm["owner"] == "@planner"
    assert fm["classification"] == "INTERNAL"
    assert fm["doc_type"]
    assert "image_count" in fm
    assert fm["title"] == "준회원 정책"
