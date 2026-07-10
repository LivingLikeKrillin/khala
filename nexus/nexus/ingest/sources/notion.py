"""NotionSource — Notion 페이지를 Nexus 적재용 Markdown+frontmatter로 변환.

fetch_markdown은 토큰 없이 단위테스트 가능(client 주입). list_changed/live_ids는
실제 Notion API를 쓰므로 통합 단계에서 구현한다.
"""

from __future__ import annotations

import os

from nexus.ingest.sources.base import ConvertedDoc, PageRef
from nexus.ingest.sources.notion_convert import blocks_to_markdown
from nexus.ingest.sources.notion_ids import canonical_page_id


class NotionSource:
    def __init__(
        self,
        client=None,
        token_env: str = "NOTION_TOKEN",
        roots: list[str] | None = None,
        tenant: str = "default",
        classification: str = "INTERNAL",
        owner: str = "unknown",
    ):
        if client is None:
            from notion_client import Client  # 지연 임포트 — 단위테스트는 client 주입

            client = Client(auth=os.environ[token_env])
        self.client = client
        # URL 에서 복사한 대시 없는 id 도 API 표기로 맞춘다 — 중복 적재/귀속 불일치 방지.
        self.roots = [canonical_page_id(r) for r in (roots or [])]
        self.tenant = tenant
        self.classification = classification
        self.owner = owner

    def _all_blocks(self, page_id: str) -> list[dict]:
        blocks: list[dict] = []
        cursor = None
        while True:
            resp = self.client.blocks.children.list(block_id=page_id, start_cursor=cursor)
            blocks.extend(resp.get("results", []))
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
        return blocks

    def fetch_markdown(self, ref: PageRef) -> ConvertedDoc:
        md, image_count = blocks_to_markdown(self._all_blocks(ref.id))

        # 제목은 **페이지 이름**이다. 예전엔 마크다운 첫 헤딩을 썼고, 그래서 Notion 의 `Index`
        # 페이지가 코퍼스에 `Access 방식` 으로 들어갔다 — 사용자는 인용에서 자기가 열어 본 적
        # 없는 이름을 본다. 이름 없는 페이지(빈 제목 속성)만 첫 헤딩으로, 그것도 없으면 id 로.
        first = md.splitlines()[0] if md.strip() else ""
        heading = first.removeprefix("### ").removeprefix("## ").removeprefix("# ").strip()
        title = (ref.title or "").strip() or heading or ref.id
        fm = {
            "title": title,
            "doc_type": "wiki",  # classifier 경로판정 무력화 보완
            "origin_url": ref.url,
            "origin_last_edited": ref.last_edited,
            "source_kind": "wiki",
            "owner": self.owner,
            "classification": self.classification,
            "image_count": image_count,
        }
        return ConvertedDoc(
            page_id=ref.id, markdown=md, frontmatter=fm, image_count=image_count
        )

    @staticmethod
    def _title_of(page: dict) -> str:
        """제목 속성을 **타입으로** 찾는다. 이름은 임의다 — DB 행에서는 `과제명` 일 수도 있다."""
        for prop in (page.get("properties") or {}).values():
            if prop.get("type") == "title":
                return "".join(t.get("plain_text", "") for t in prop.get("title") or [])
        return ""

    def page_ref(self, page_id: str) -> PageRef:
        """page id → PageRef(id/url/last_edited/title). client.pages.retrieve 사용."""
        p = self.client.pages.retrieve(page_id=page_id)
        return PageRef(
            id=page_id,
            url=p.get("url", f"https://notion.so/{page_id}"),
            last_edited=p.get("last_edited_time", ""),
            title=self._title_of(p),
        )

    def _db_rows(self, database_id: str) -> list[dict]:
        rows: list[dict] = []
        cursor = None
        while True:
            resp = self.client.databases.query(database_id=database_id, start_cursor=cursor)
            rows.extend(resp.get("results", []))
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
        return rows

    def _collect(self, page_id: str, ids: set[str]) -> None:
        page_id = canonical_page_id(page_id)
        if page_id in ids:
            return
        ids.add(page_id)
        for block in self._all_blocks(page_id):
            t = block.get("type")
            if t == "child_page":
                self._collect(block["id"], ids)
            elif t == "child_database":
                for row in self._db_rows(block["id"]):
                    self._collect(row["id"], ids)

    def live_ids(self) -> set[str]:
        """roots(page id) 하위에 도달 가능한 page id 집합(child_page 재귀 + child_database 행)."""
        return set(self.live_index())

    def live_index(self) -> dict[str, set[str]]:
        """page_id → 그 페이지에 도달하는 root 들의 집합.

        root 별로 따로 걸어야 공유 서브트리의 출처가 보존된다(한 번만 걸으면 먼저 도달한
        root 에만 귀속되어, containment prune 술어가 무너진다 — SPEC §3.2).
        열거 중 예외는 삼키지 않는다: 부분 집합이 '삭제된 페이지'로 오독되면 안 된다.
        """
        index: dict[str, set[str]] = {}
        for root in self.roots:
            reached: set[str] = set()
            self._collect(root, reached)
            for page_id in reached:
                index.setdefault(page_id, set()).add(root)
        return index

    def list_changed(self, since: str | None) -> list[PageRef]:
        raise NotImplementedError  # 증분 sync 는 S4 비범위(후속)
