"""공용 유틸리티 함수.

get_search_text()는 검색/임베딩 텍스트 생성의 단일 경유점이다.
chunk_text를 직접 embedding이나 tsvector에 사용하지 말 것.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from khala.models.chunk import Chunk


def get_search_text(chunk: "Chunk") -> str:
    """청크의 검색/임베딩용 텍스트 생성.

    1.0: section_path 접두사를 붙여 context를 제공.
    2.0: context_prefix에 LLM Contextual Enrichment 결과를 넣으면
         이 함수 수정 없이 품질 향상.

    이 함수는 다음 2곳에서 사용된다:
    - index/bm25.py: tsvector 생성 시
    - index/embed.py: embedding 생성 시

    DB의 search_text GENERATED 컬럼도 동일한 로직:
    COALESCE(context_prefix, '[' || section_path || ']') || ' ' || chunk_text

    Args:
        chunk: Chunk 객체 (chunk_text, section_path, context_prefix 필요)

    Returns:
        검색/임베딩에 사용할 가공된 텍스트
    """
    prefix = chunk.context_prefix or f"[{chunk.section_path}]"
    return f"{prefix} {chunk.chunk_text}"
