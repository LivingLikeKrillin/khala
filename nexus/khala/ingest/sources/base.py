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


@dataclass
class ConvertedDoc:
    page_id: str
    markdown: str
    frontmatter: dict = field(default_factory=dict)
    image_count: int = 0


@runtime_checkable
class DocumentSource(Protocol):
    def list_changed(self, since: str | None) -> list[PageRef]: ...

    def fetch_markdown(self, ref: PageRef) -> ConvertedDoc: ...

    def live_ids(self) -> set[str]: ...
