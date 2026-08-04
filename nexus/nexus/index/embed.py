"""Embedding 인덱싱 — EmbeddingService → pgvector.

get_search_text()를 경유하여 텍스트를 생성하고,
EmbeddingService를 통해 임베딩을 생성한 후 pgvector에 저장한다.
Ollama를 직접 호출하지 않는다.
"""

from __future__ import annotations

import structlog

from nexus import db
from nexus.index.vector_index import configured_column, resolve_column
from nexus.providers.embedding import EmbeddingService
from nexus.utils import get_search_text

logger = structlog.get_logger(__name__)


async def index_chunk_embedding(
    chunk_rid: str,
    chunk,
    embedding_svc: EmbeddingService,
    column: str | None = None,
) -> bool:
    """단일 청크의 embedding을 생성하여 **설정된 세대의 컬럼**에 저장.

    컬럼이 하드코딩돼 있으면 컷오버 뒤 새로 적재된 청크가 옛 컬럼만 채우고 새 컬럼은 NULL 로
    남는다 — 벡터 검색에서 조용히 사라지고, 아무것도 예외를 내지 않는다
    (SPEC-nexus-embedding-cutover-seam §1.5, §4.3).

    Args:
        chunk_rid: 청크의 rid
        chunk: Chunk 객체
        embedding_svc: EmbeddingService 인스턴스
        column: 쓸 벡터 컬럼. None 이면 이 프로세스의 설정된 세대

    Returns:
        성공 여부. 실패 시 해당 컬럼 null 로 남음 (BM25로만 검색)
    """
    col = resolve_column(column) if column else configured_column()
    try:
        search_text = get_search_text(chunk)
        vectors = await embedding_svc.embed_documents([search_text])
        if not vectors:
            return False

        embedding = vectors[0]
        # pgvector format: [0.1, 0.2, ...]
        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

        await db.execute(
            f"""
            UPDATE chunks
            SET {col} = $1::vector,
                embed_model = $2,
                updated_at = now()
            WHERE rid = $3
            """,
            vec_str, embedding_svc.get_model_name(), chunk_rid,
        )
        return True

    except Exception as e:
        logger.error("embedding_index_failed", chunk_rid=chunk_rid, error=str(e))
        return False


async def index_chunks_embedding(
    chunk_rids_and_chunks: list[tuple[str, object]],
    embedding_svc: EmbeddingService,
    batch_size: int = 10,
    column: str | None = None,
) -> int:
    """복수 청크의 embedding을 배치로 생성.

    Args:
        chunk_rids_and_chunks: (rid, chunk) 튜플 리스트
        embedding_svc: EmbeddingService 인스턴스
        batch_size: Ollama 배치 크기

    Returns:
        성공한 청크 수
    """
    col = resolve_column(column) if column else configured_column()
    success = 0
    total = len(chunk_rids_and_chunks)

    # 배치 단위로 처리
    for i in range(0, total, batch_size):
        batch = chunk_rids_and_chunks[i:i + batch_size]
        texts = [get_search_text(chunk) for _, chunk in batch]

        try:
            vectors = await embedding_svc.embed_documents(texts)

            for j, (rid, _) in enumerate(batch):
                if j >= len(vectors):
                    break
                vec_str = "[" + ",".join(str(v) for v in vectors[j]) + "]"
                await db.execute(
                    f"""
                    UPDATE chunks
                    SET {col} = $1::vector,
                        embed_model = $2,
                        updated_at = now()
                    WHERE rid = $3
                    """,
                    vec_str, embedding_svc.get_model_name(), rid,
                )
                success += 1

        except Exception as e:
            logger.error("embedding_batch_failed", batch_start=i, error=str(e))
            # 배치 실패 시 개별 처리 시도
            for rid, chunk in batch:
                if await index_chunk_embedding(rid, chunk, embedding_svc, column=col):
                    success += 1

    logger.info("embedding_batch_indexed", total=total, success=success)
    return success
