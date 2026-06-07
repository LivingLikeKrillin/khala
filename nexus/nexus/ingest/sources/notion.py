"""NotionSource — Notion 페이지를 Nexus 적재용 Markdown+frontmatter로 변환.

fetch_markdown은 토큰 없이 단위테스트 가능(client 주입). list_changed/live_ids는
실제 Notion API를 쓰므로 통합 단계에서 구현한다.
"""

from __future__ import annotations

import os

from nexus.ingest.sources.base import ConvertedDoc, PageRef
from nexus.ingest.sources.notion_convert import blocks_to_markdown


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
        self.roots = roots or []
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
        first = md.splitlines()[0] if md.strip() else ""
        title = (
            first.removeprefix("### ").removeprefix("## ").removeprefix("# ").strip() or ref.id
        )
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

    def list_changed(self, since: str | None) -> list[PageRef]:
        raise NotImplementedError  # 통합 단계(Task 6): root object type 분기 + last_edited_time

    def live_ids(self) -> set[str]:
        raise NotImplementedError  # 통합 단계(Task 6): roots 전체 열거
