"""NotionSource — Notion 페이지를 Nexus 적재용 Markdown+frontmatter로 변환.

fetch_markdown은 토큰 없이 단위테스트 가능(client 주입). list_changed/live_ids는
실제 Notion API를 쓰므로 통합 단계에서 구현한다.
"""

from __future__ import annotations

import os

from nexus.ingest.sources.base import ConvertedDoc, PageRef
from nexus.ingest.sources.notion_convert import blocks_to_markdown, properties_to_markdown
from nexus.ingest.sources.notion_ids import canonical_page_id


def _title_from_properties(props: dict) -> str:
    """제목 속성이 비었을 때, **식별에 쓸 만한 다른 속성**으로 이름을 만든다.

    정책 DB 의 행 중에는 `정책 상세`(제목 속성)가 비어 있는 것들이 있다. 그대로 두면 문서 제목이
    `04a79e48-…` 가 되고, 인용에 UUID 가 뜬다 — 사용자는 자기가 본 적 없는 이름을 보게 된다.
    같은 행이 `정책`·`wht` 같은 select 값으로는 충분히 식별되므로 그것을 이어 붙인다.

    id 를 쓰는 것보다 나은 이름이 없을 때만 id 로 떨어진다.
    """
    parts: list[str] = []
    for name, v in (props or {}).items():
        if v.get("type") == "select" and (v.get("select") or {}).get("name"):
            parts.append(v["select"]["name"])
        elif v.get("type") == "status" and (v.get("status") or {}).get("name"):
            parts.append(v["status"]["name"])
    return " / ".join(parts[:3])


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
        # 자식 블록을 한 겹 더 펼칠 수 있게 넘긴다 — 표·토글·동기화 블록의 내용은 자식에 있다.
        # 그림 참조를 순회 중에 챙긴다 — 서명 링크는 한 시간이면 죽으므로 여기서만 잡을 수
        # 있다. 본문에는 자리 표식만 남고, 추출은 2패스가 동시에 한다.
        images: list[dict] = []
        md, image_count = blocks_to_markdown(
            self._all_blocks(ref.id), self._all_blocks, image_sink=images)

        # **속성도 본문이다.** 데이터베이스 행은 블록이 0개이고 내용이 전부 속성에 있는 경우가
        # 흔하다(개정 이력의 한 행 = 개정 내용·날짜·Epic·바로가기). 블록만 읽으면 그런 행이
        # 빈 문서로 판정돼 통째로 빠진다.
        page = self.client.pages.retrieve(page_id=ref.id)
        prop_md = properties_to_markdown(page.get("properties", {}))
        if prop_md:
            body = (md.strip() + "\n\n" + prop_md) if md.strip() else prop_md
            md = body.strip() + "\n"

        # 제목은 **페이지 이름**이다. 예전엔 마크다운 첫 헤딩을 썼고, 그래서 Notion 의 `Index`
        # 페이지가 코퍼스에 `Access 방식` 으로 들어갔다 — 사용자는 인용에서 자기가 열어 본 적
        # 없는 이름을 본다. 이름 없는 페이지(빈 제목 속성)만 첫 헤딩으로, 그것도 없으면 id 로.
        # 첫 줄을 무조건 헤딩으로 보던 규칙은 본문이 블록뿐일 때만 맞았다. 속성을 본문에 붙이면서
        # `- **비로그인**: ☑️` 같은 속성 줄이 제목이 된다 — **진짜 헤딩일 때만** 쓴다.
        first = md.splitlines()[0] if md.strip() else ""
        heading = ""
        for prefix in ("### ", "## ", "# "):
            if first.startswith(prefix):
                heading = first[len(prefix):].strip()
                break
        if len(heading) < 2 or heading.isdigit():
            heading = ""
        title = ((ref.title or "").strip() or heading
                 or _title_from_properties(page.get("properties", {})) or ref.id)
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
            page_id=ref.id, markdown=md, frontmatter=fm, image_count=image_count,
            images=images,
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

    def _data_source_ids(self, database_id: str) -> list[str]:
        """DB 하나가 갖는 data source 들. 2025-09 개편 전에는 이 층이 없었다."""
        db = self.client.databases.retrieve(database_id=database_id)
        return [d["id"] for d in db.get("data_sources", []) if d.get("id")]

    def _db_rows(self, database_id: str) -> list[dict]:
        """DB 행 = 페이지. **data source 를 거쳐 조회한다.**

        Notion 2025-09 API 개편에서 데이터베이스가 `database` 와 그 아래 `data_source` 로 갈렸고,
        `notion-client` 3.x 는 `databases.query` 를 없앴다(`data_sources.query` 로 이동). 우리
        코드는 옛 경로를 부르고 있었고, 그래서 **데이터베이스가 있는 트리는 통째로 못 걸었다** —
        `AttributeError` 로 걷기가 중단됐다.

        기존 루트에는 DB 가 없어서 드러나지 않았다. 정책 문서처럼 DB 로 조직된 코퍼스가 오면
        그때 전부가 안 들어온다. 미리보기가 0건이 아니라 **오류를 보고**해서 잡혔다.
        """
        rows: list[dict] = []
        for ds_id in self._data_source_ids(database_id):
            cursor = None
            while True:
                resp = self.client.data_sources.query(data_source_id=ds_id, start_cursor=cursor)
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
