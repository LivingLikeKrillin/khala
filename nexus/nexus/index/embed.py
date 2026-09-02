"""Embedding 인덱싱 — EmbeddingService → pgvector.

get_search_text()를 경유하여 텍스트를 생성하고,
EmbeddingService를 통해 임베딩을 생성한 후 pgvector에 저장한다.
Ollama를 직접 호출하지 않는다.
"""

from __future__ import annotations

import structlog

from nexus import db
from nexus.index import provenance
from nexus.index.vector_index import configured_column, resolve_column
from nexus.providers.embedding import EmbeddingService
from nexus.utils import get_search_text

logger = structlog.get_logger(__name__)


async def record_refusal(chunk_rid: str, column: str, embedding_svc, reason: str,
                         chars: int = 0) -> None:
    """거부를 **행으로 남긴다.** 삼키면 그 청크는 벡터 경로에서 영구히 사라지고 아무도 모른다.

    `embed_waivers` 와 섞지 않는다 — 그건 사람이 이름을 걸고 포기한 **결정**이고, 이건 기계가 낸
    **사실**이다. 백엔드 메시지는 요약하지 않고 그대로 남긴다: "왜 안 되는지" 가 곧 처방이다
    (`413 max_seq_length(8192)` 는 청킹을 고치라는 말이고, 인코딩 오류는 다른 처방이다).

    기록 자체가 실패해도 색인은 계속한다 — 진단이 진단 대상을 죽이면 안 된다.
    """
    try:
        model = embedding_svc.get_model_name() if embedding_svc is not None else ""
    except Exception:  # noqa: BLE001
        model = ""
    try:
        await db.execute(
            """
            INSERT INTO embed_refusals (chunk_rid, column_name, model, reason, chars, refused_at)
            VALUES ($1, $2, $3, $4, $5, now())
            ON CONFLICT (chunk_rid, column_name) DO UPDATE
               SET reason = EXCLUDED.reason, model = EXCLUDED.model,
                   chars = EXCLUDED.chars, refused_at = now()
            """,
            chunk_rid, column, model, reason[:2000], chars,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("embed_refusal_record_failed", chunk_rid=chunk_rid, error=str(e))


async def clear_refusal(chunk_rid: str, column: str) -> None:
    """재시도가 성공하면 지운다. 남겨두면 고쳐진 청크가 계속 병들어 보인다."""
    try:
        await db.execute(
            "DELETE FROM embed_refusals WHERE chunk_rid = $1 AND column_name = $2",
            chunk_rid, column)
    except Exception as e:  # noqa: BLE001
        logger.warning("embed_refusal_clear_failed", chunk_rid=chunk_rid, error=str(e))


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
    search_text = ""
    try:
        search_text = get_search_text(chunk)
        vectors = await embedding_svc.embed_documents([search_text])
        if not vectors:
            await record_refusal(chunk_rid, col, embedding_svc, "백엔드가 벡터를 돌려주지 않았다",
                                 len(search_text))
            return False

        embedding = vectors[0]
        # pgvector format: [0.1, 0.2, ...]
        vec_str = "[" + ",".join(str(v) for v in embedding) + "]"

        await db.execute(
            f"""
            UPDATE chunks
            SET {col} = $1::vector,
                updated_at = now()
            WHERE rid = $2
            """,
            vec_str, chunk_rid,
        )
        # 출처는 **컬럼별**로 (SPEC-nexus-embedding-provenance-grain §3.1). 단건·배치 **둘 다**
        # 남겨야 한다 — 한쪽만 고치면 그 경로로 쓰인 벡터가 조용히 미상이 된다.
        # 행 라벨(`chunks.embed_model`)은 더 쓰지 않는다 (027) — 한 칸이 컬럼 둘을 설명할 수
        # 없어서 거짓이었고, 여기가 그 거짓을 만들던 자리다.
        await provenance.record(chunk_rid=chunk_rid, column_name=col,
                                model=embedding_svc.get_model_name())
        # 성공하면 이전 거부 기록을 지운다 — 낡은 거부가 남으면 멀쩡한 청크가 병들어 보인다.
        await clear_refusal(chunk_rid, col)
        return True

    except Exception as e:
        logger.error("embedding_index_failed", chunk_rid=chunk_rid, error=str(e))
        await record_refusal(chunk_rid, col, embedding_svc, str(e), len(search_text))
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
                        updated_at = now()
                    WHERE rid = $2
                    """,
                    vec_str, rid,
                )
                # 출처는 **컬럼별**로 남긴다 — 옛 행 라벨(`embed_model`)은 행당 한 칸이라 다른
                # 컬럼을 설명하지 못했고, 그래서 더 쓰지 않는다 (027).
                # (SPEC-nexus-embedding-provenance-grain §3.1)
                await provenance.record(chunk_rid=rid, column_name=col,
                                        model=embedding_svc.get_model_name())
                # **배치 경로도 거부 기록을 지운다.** 단건 경로만 지우고 있었고, 적재는 배치를
                # 탄다 — 그래서 고쳐진 청크가 계속 병들어 보였다. 2026-08-08 에 실물에서 그랬다:
                # 18,854자 청크를 잘라 임베딩까지 성공했는데 `embed_refusals` 행이 그대로 남아
                # 코퍼스 뷰가 없는 문제를 보고했다.
                await clear_refusal(rid, col)
                success += 1

        except Exception as e:
            logger.error("embedding_batch_failed", batch_start=i, error=str(e))
            # 배치 실패 시 개별 처리 시도
            for rid, chunk in batch:
                if await index_chunk_embedding(rid, chunk, embedding_svc, column=col):
                    success += 1

    logger.info("embedding_batch_indexed", total=total, success=success)
    return success
