"""Chunk 도메인 모델."""

from __future__ import annotations

from dataclasses import dataclass, field

from khala.models.resource import KhalaResource


@dataclass
class Chunk(KhalaResource):
    """문서에서 분할된 청크. 검색/임베딩의 기본 단위."""

    doc_rid: str = ""
    section_path: str = ""
    chunk_text: str = ""
    context_prefix: str | None = None
    chunk_index: int = 0
    embedding: list[float] | None = None
    embed_model: str = "multilingual-e5-base"
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.rtype = "chunk"
