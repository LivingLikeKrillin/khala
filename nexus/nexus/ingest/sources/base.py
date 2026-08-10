"""소스-무관 문서 어댑터 인터페이스.

NotionSource(이번)·ConfluenceSource(후속)가 이 Protocol을 구현한다.
모든 소스는 동일한 ConvertedDoc(markdown + frontmatter)로 수렴해 기존 run_ingest를 재사용한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class PageRef:
    id: str
    url: str
    last_edited: str
    #: 원본이 부르는 이름. 없을 수도 있다(제목 속성이 빈 페이지, DB 행).
    title: str = ""


@dataclass
class ConvertedDoc:
    page_id: str
    markdown: str
    frontmatter: dict = field(default_factory=dict)
    image_count: int = 0
    #: 순회 중에 잡은 그림 참조 `{block_id, url, caption}`. **URL 은 여기서만 유효하다** —
    #: Notion 의 서명 링크는 한 시간이면 죽는다.
    images: list = field(default_factory=list)
    #: 이 본문의 비전 마커를 우리가 썼는가. 청커가 마커를 신뢰할지 결정한다 (ADR-0010 §3).
    vision_extracted: bool = False


@runtime_checkable
class DocumentSource(Protocol):
    def list_changed(self, since: str | None) -> list[PageRef]: ...

    def fetch_markdown(self, ref: PageRef) -> ConvertedDoc: ...

    def live_ids(self) -> set[str]: ...

    def live_index(self) -> dict[str, set[str]]:
        """page_id → 그 페이지에 도달하는 root 들의 집합. 재조정의 containment 술어가 쓴다."""
        ...
