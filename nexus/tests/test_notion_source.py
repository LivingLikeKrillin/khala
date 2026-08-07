from nexus.ingest.sources.base import PageRef
from nexus.ingest.sources.notion import NotionSource


class FakeClient:
    """client.blocks.children.list(block_id=..., start_cursor=...) 형태를 흉내."""

    def __init__(self, properties: dict | None = None):
        self.blocks = type("B", (), {"children": self})()
        # 실물에는 `pages.retrieve` 가 있고, fetch_markdown 은 **속성도 본문으로** 읽는다.
        # 가짜가 그것을 안 갖고 있으면 테스트만 통과하고 프로덕션은 AttributeError 로 죽는다.
        self._properties = properties or {}
        self.pages = type("P", (), {"retrieve": lambda _self, page_id: {
            "id": page_id, "properties": self._properties}})()

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
        # 실물(notion-client 3.x)에는 `databases.query` 가 **없다**. 가짜가 그걸 갖고 있으면
        # 테스트는 통과하는데 프로덕션은 AttributeError 로 죽는다 — 실제로 그렇게 죽었다.
        self.databases = type("D", (), {"retrieve": self._retrieve_db})()
        self.data_sources = type("DS", (), {"query": self._query_ds})()
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

    def _retrieve_db(self, database_id):
        return {"object": "database", "id": database_id,
                "data_sources": [{"id": f"{database_id}-ds", "name": "rows"}]}

    def _query_ds(self, data_source_id, start_cursor=None, **kw):
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


# ── 데이터베이스는 data source 를 거쳐 조회한다 (2025-09 API 개편) ────────────


class _DSClient:
    """`notion-client` 3.x 의 모양: `databases.query` 는 **없다**."""

    def __init__(self, rows_by_ds: dict[str, list[dict]], data_sources: dict[str, list[dict]]):
        outer = self

        class _Databases:
            def retrieve(self, database_id):
                return {"object": "database", "id": database_id,
                        "data_sources": data_sources.get(database_id, [])}

        class _DataSources:
            def query(self, data_source_id, start_cursor=None, **kw):
                rows = rows_by_ds[data_source_id]
                outer.queried.append(data_source_id)
                return {"results": rows, "has_more": False}

        self.databases = _Databases()
        self.data_sources = _DataSources()
        self.queried: list[str] = []


def test_database_rows_are_read_through_data_sources():
    """`databases.query` 는 3.x 에서 사라졌다. 옛 경로를 부르면 AttributeError 로 걷기가 통째로
    멈추고, DB 로 조직된 코퍼스는 **한 건도** 안 들어온다."""
    from nexus.ingest.sources.notion import NotionSource

    client = _DSClient(
        rows_by_ds={"ds-1": [{"id": "row-a"}, {"id": "row-b"}]},
        data_sources={"db-1": [{"id": "ds-1", "name": "정책 모음"}]},
    )
    src = NotionSource(client=client, roots=[])
    assert [r["id"] for r in src._db_rows("db-1")] == ["row-a", "row-b"]
    assert client.queried == ["ds-1"]


def test_every_data_source_of_a_database_is_queried():
    """개편 후 DB 하나가 여러 data source 를 가질 수 있다 — 하나만 읽으면 조용히 일부만 들어온다."""
    from nexus.ingest.sources.notion import NotionSource

    client = _DSClient(
        rows_by_ds={"ds-1": [{"id": "a"}], "ds-2": [{"id": "b"}]},
        data_sources={"db-1": [{"id": "ds-1"}, {"id": "ds-2"}]},
    )
    src = NotionSource(client=client, roots=[])
    assert {r["id"] for r in src._db_rows("db-1")} == {"a", "b"}
    assert client.queried == ["ds-1", "ds-2"]


def test_a_database_with_no_data_sources_yields_nothing_rather_than_failing():
    from nexus.ingest.sources.notion import NotionSource

    client = _DSClient(rows_by_ds={}, data_sources={"db-1": []})
    assert NotionSource(client=client, roots=[])._db_rows("db-1") == []
