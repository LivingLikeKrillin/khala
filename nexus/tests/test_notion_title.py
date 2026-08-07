"""Notion 문서의 제목은 **페이지 이름**이다 — 본문 첫 헤딩이 아니다.

`fetch_markdown` 은 마크다운의 첫 줄에서 `#` 을 벗겨 제목으로 삼았다. 그래서 라이브 코퍼스에서
6건 중 **0건**이 실제 페이지 이름과 일치했다 (2026-07-10 관측):

    Notion `Index`        → DB `Access 방식`
    Notion `Join`         → DB `Table Join 종류 (논리적인 조인 유형)`
    Notion `복합 인덱스`    → DB `선두 컬럼과 후속 컬럼 모두 범위 조건으로 조회하고자 할 때 제약 사항`

`pages.retrieve` 가 진짜 제목을 주는데 버렸다. 사용자는 인용에서 자기가 열어 본 적 없는 이름을 본다.
"""

from __future__ import annotations

from nexus.ingest.sources.base import PageRef
from nexus.ingest.sources.notion import NotionSource


def _blocks_client(blocks, properties=None):
    """실물의 표면을 갖춘 가짜. `pages.retrieve` 가 없으면 테스트만 통과하고 프로덕션은 죽는다 —
    `fetch_markdown` 은 속성도 본문으로 읽기 때문이다."""
    class _C:
        def __init__(self):
            self.blocks = type("B", (), {"children": self})()
            self.pages = type("P", (), {"retrieve": lambda _s, page_id: {
                "id": page_id, "properties": properties or {}}})()

        def list(self, block_id, start_cursor=None):
            return {"results": blocks, "has_more": False, "next_cursor": None}

    return _C()


def _heading(text):
    return {"type": "heading_2",
            "heading_2": {"rich_text": [{"plain_text": text, "annotations": {},
                                         "text": {"content": text}}]}}


def test_the_title_is_the_notion_page_name_not_the_first_heading():
    src = NotionSource(client=_blocks_client([_heading("Access 방식")]))
    ref = PageRef(id="p1", url="https://notion.so/p1", last_edited="", title="Index")

    doc = src.fetch_markdown(ref)

    assert doc.frontmatter["title"] == "Index"


def test_a_page_without_a_name_falls_back_to_the_first_heading():
    """제목 없는 페이지(데이터베이스 행 등)까지 rid 로 부르게 하지는 않는다."""
    src = NotionSource(client=_blocks_client([_heading("Access 방식")]))
    ref = PageRef(id="p1", url="", last_edited="", title="")

    assert src.fetch_markdown(ref).frontmatter["title"] == "Access 방식"


def test_a_page_with_neither_a_name_nor_a_heading_falls_back_to_its_id():
    src = NotionSource(client=_blocks_client([]))
    ref = PageRef(id="p1", url="", last_edited="", title="")

    assert src.fetch_markdown(ref).frontmatter["title"] == "p1"


def test_page_ref_carries_the_title_from_the_notion_api():
    class _C:
        def __init__(self):
            self.pages = type("P", (), {"retrieve": self._retrieve})()

        def _retrieve(self, page_id):
            return {"url": "https://notion.so/x", "last_edited_time": "2026-07-10T00:00:00Z",
                    "properties": {"Name": {"type": "title",
                                            "title": [{"plain_text": "Entity 식별"}]}}}

    ref = NotionSource(client=_C()).page_ref("p1")
    assert ref.title == "Entity 식별"


def test_a_database_row_title_is_read_from_its_own_title_property():
    """데이터베이스 행은 title 속성 이름이 임의다. 타입으로 찾는다."""
    class _C:
        def __init__(self):
            self.pages = type("P", (), {"retrieve": self._retrieve})()

        def _retrieve(self, page_id):
            return {"properties": {"과제명": {"type": "title",
                                           "title": [{"plain_text": "락 개념 정리"}]},
                                   "상태": {"type": "select", "select": {"name": "done"}}}}

    assert NotionSource(client=_C()).page_ref("p1").title == "락 개념 정리"


# ── 제목이 빈 DB 행: UUID 대신 식별 가능한 이름 ──────────────────────────────


def test_a_row_with_no_title_is_named_by_its_select_values():
    """정책 DB 의 일부 행은 제목 속성이 비어 있다. 그대로 두면 인용에 UUID 가 뜬다."""
    from nexus.ingest.sources.notion import _title_from_properties

    got = _title_from_properties({
        "정책 상세": {"type": "title", "title": []},
        "정책": {"type": "select", "select": {"name": "파티룸 Entity"}},
        "wht": {"type": "select", "select": {"name": "파티 룸 입장"}},
        "비로그인": {"type": "rich_text", "rich_text": []},
    })
    assert got == "파티룸 Entity / 파티 룸 입장"


def test_nothing_identifying_yields_empty_so_the_caller_can_fall_back():
    from nexus.ingest.sources.notion import _title_from_properties

    assert _title_from_properties({"메모": {"type": "rich_text", "rich_text": []}}) == ""
    assert _title_from_properties({}) == ""


def test_a_property_line_never_becomes_the_title():
    """속성을 본문에 붙이면서 첫 줄이 헤딩이 아닐 수 있게 됐다. `- **비로그인**: ☑️` 가 문서
    제목이 되면 인용이 읽을 수 없어진다."""
    from nexus.ingest.sources.notion import NotionSource
    from nexus.ingest.sources.base import PageRef

    props = {
        "정책 상세": {"type": "title", "title": []},
        "비로그인": {"type": "rich_text", "rich_text": [
            {"plain_text": "☑️", "annotations": {}}]},
        "정책": {"type": "select", "select": {"name": "파티룸 Entity"}},
    }
    src = NotionSource(client=_blocks_client([], properties=props))
    got = src.fetch_markdown(PageRef(id="p1", url="", last_edited="", title="")).frontmatter["title"]
    assert got == "파티룸 Entity", got


def test_a_real_heading_is_still_used_when_there_is_no_name():
    from nexus.ingest.sources.notion import NotionSource
    from nexus.ingest.sources.base import PageRef

    src = NotionSource(client=_blocks_client([_heading("Access 방식")]))
    ref = PageRef(id="p1", url="", last_edited="", title="")
    assert src.fetch_markdown(ref).frontmatter["title"] == "Access 방식"
