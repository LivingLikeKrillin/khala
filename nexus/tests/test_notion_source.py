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
                                "plain_text": "Basic 정책",
                                "annotations": {},
                                "text": {"content": "Basic 정책"},
                            }
                        ]
                    },
                }
            ],
            "has_more": False,
            "next_cursor": None,
        }


class FakeTreeClient:
    """roots 하위 트리: page p_root → child_page p_child + child_database db1(행 r1)."""

    def __init__(self):
        self.blocks = type("B", (), {"children": self})()
        self.pages = type("P", (), {"retrieve": self._retrieve})()
        self.databases = type("D", (), {"query": self._query})()
        self._tree = {
            "p_root": [
                {"type": "child_page", "id": "p_child"},
                {"type": "child_database", "id": "db1"},
            ],
            "p_child": [],
        }

    def list(self, block_id, start_cursor=None):  # blocks.children.list
        return {"results": self._tree.get(block_id, []), "has_more": False, "next_cursor": None}

    def _retrieve(self, page_id):
        return {"id": page_id, "url": f"https://notion.so/{page_id}",
                "last_edited_time": "2026-06-25T00:00:00Z"}

    def _query(self, database_id, start_cursor=None):
        return {"results": [{"id": "r1"}], "has_more": False, "next_cursor": None}


def test_live_ids_enumerates_root_children_and_db_rows():
    src = NotionSource(client=FakeTreeClient(), roots=["p_root"], tenant="default")
    # db 컨테이너(db1) 자체는 페이지 아님 — 행 r1만 페이지로 수집.
    assert src.live_ids() == {"p_root", "p_child", "r1"}


def test_page_ref_builds_from_retrieve():
    src = NotionSource(client=FakeTreeClient(), roots=[], tenant="default")
    ref = src.page_ref("p_root")
    assert ref.id == "p_root"
    assert ref.url == "https://notion.so/p_root"
    assert ref.last_edited == "2026-06-25T00:00:00Z"


def test_fetch_markdown_builds_frontmatter_and_counts():
    src = NotionSource(
        client=FakeClient(), roots=[], tenant="default",
        classification="INTERNAL", owner="@planner",
    )
    ref = PageRef(id="pid1", url="https://notion.so/pid1", last_edited="2026-06-06T00:00:00Z")
    cd = src.fetch_markdown(ref)
    assert "# Basic 정책" in cd.markdown
    fm = cd.frontmatter
    assert fm["source_kind"] == "wiki"
    assert fm["origin_url"] == "https://notion.so/pid1"
    assert fm["origin_last_edited"] == "2026-06-06T00:00:00Z"
    assert fm["owner"] == "@planner"
    assert fm["classification"] == "INTERNAL"
    assert fm["doc_type"]
    assert "image_count" in fm
    assert fm["title"] == "Basic 정책"
