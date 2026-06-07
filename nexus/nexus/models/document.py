"""Document 도메인 모델."""

from __future__ import annotations

from dataclasses import dataclass, field

from nexus.models.resource import NexusResource


@dataclass
class Document(NexusResource):
    """인덱싱된 문서. 원본은 Git에, 여기엔 메타데이터만."""

    title: str = ""
    doc_type: str = "markdown"
    language: str = "ko"
    content_hash: str = ""

    def __post_init__(self) -> None:
        self.rtype = "document"
