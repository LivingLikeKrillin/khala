"""Ingestion Orchestrator.

collect → classify → quarantine gate → chunk → DB 저장 → BM25 → Vector → Graph.
통합 파이프라인: API와 CLI 모두 이 함수를 호출하면 전체 인덱싱이 완료된다.
개별 문서 실패 시 skip하고 나머지 계속 처리.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog
import yaml

from khala import db
from khala.ingest.classifier import ClassificationResult, classify
from khala.ingest.chunker import ChunkData, chunk_document
from khala.ingest.collector import CollectedFile, collect_files
from khala.rid import chunk_rid, doc_rid

logger = structlog.get_logger(__name__)


@dataclass
class IngestResult:
    """인제스트 결과 요약."""
    total_files: int = 0
    indexed: int = 0
    skipped: int = 0
    quarantined: int = 0
    failed: int = 0
    errors: list[dict] = field(default_factory=list)
    bm25_indexed: int = 0
    vector_indexed: int = 0
    edges_created: int = 0


def _load_config(config_path: str = "config.yaml") -> dict:
    """config.yaml 로드."""
    from pathlib import Path
    p = Path(config_path)
    if not p.exists():
        logger.warning("config_not_found", path=config_path)
        return {}
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


async def _save_document(
    collected: CollectedFile,
    classification: ClassificationResult,
    tenant: str,
) -> str:
    """문서 메타데이터를 DB에 저장. rid 반환."""
    rid = doc_rid(collected.canonical_uri)
    now = datetime.now(timezone.utc)

    await db.execute(
        """
        INSERT INTO documents (
            rid, rtype, tenant, classification, owner,
            source_uri, source_kind, hash, content_hash,
            is_quarantined, quality_flags, status,
            created_at, updated_at,
            title, doc_type, language
        ) VALUES (
            $1, 'document', $2, $3::classification_level, 'indexer',
            $4, 'git', $5, $5,
            $6, $7, 'active',
            $8, $8,
            $9, $10, $11
        )
        ON CONFLICT (rid) DO UPDATE SET
            hash = EXCLUDED.hash,
            content_hash = EXCLUDED.content_hash,
            classification = EXCLUDED.classification,
            is_quarantined = EXCLUDED.is_quarantined,
            quality_flags = EXCLUDED.quality_flags,
            updated_at = EXCLUDED.updated_at,
            doc_type = EXCLUDED.doc_type,
            language = EXCLUDED.language
        """,
        rid, tenant, classification.classification,
        collected.canonical_uri, collected.content_hash,
        classification.is_quarantined,
        classification.pii_types if classification.is_quarantined else [],
        now,
        collected.frontmatter.get("title", collected.relative_path),
        classification.doc_type, classification.language,
    )
    return rid


async def _save_chunks(
    chunks: list[ChunkData],
    parent_rid: str,
    collected: CollectedFile,
    classification: ClassificationResult,
    tenant: str,
) -> int:
    """청크를 DB에 저장. 기존 청크 soft_delete 후 새로 삽입."""
    # 기존 청크 soft_delete
    await db.execute(
        "UPDATE chunks SET status = 'superseded', updated_at = $1 WHERE doc_rid = $2 AND status = 'active'",
        datetime.now(timezone.utc), parent_rid,
    )

    saved = 0
    for chunk in chunks:
        rid = chunk_rid(parent_rid, chunk.section_path, chunk.chunk_index)
        now = datetime.now(timezone.utc)

        await db.execute(
            """
            INSERT INTO chunks (
                rid, rtype, tenant, classification, owner,
                source_uri, source_kind, hash,
                is_quarantined, status,
                created_at, updated_at,
                doc_rid, section_path, chunk_text,
                chunk_index, prov_pipeline, prov_inputs
            ) VALUES (
                $1, 'chunk', $2, $3::classification_level, 'indexer',
                $4, 'git', $5,
                false, 'active',
                $6, $6,
                $7, $8, $9,
                $10, 'indexer-v1', $11
            )
            ON CONFLICT (rid) DO UPDATE SET
                chunk_text = EXCLUDED.chunk_text,
                classification = EXCLUDED.classification,
                updated_at = EXCLUDED.updated_at,
                status = 'active'
            """,
            rid, tenant, classification.classification,
            collected.canonical_uri, collected.content_hash,
            now,
            parent_rid, chunk.section_path, chunk.chunk_text,
            chunk.chunk_index, [parent_rid],
        )
        saved += 1

    return saved


async def _run_bm25_indexing(tenant: str) -> int:
    """저장된 청크에 BM25 인덱스 생성."""
    from khala.index.bm25 import index_chunk_bm25
    from khala.models.chunk import Chunk

    rows = await db.fetch_all(
        """
        SELECT rid, section_path, chunk_text, context_prefix
        FROM chunks
        WHERE status = 'active' AND tenant = $1 AND tsvector_ko IS NULL
        """,
        tenant,
    )

    count = 0
    for r in rows:
        chunk = Chunk(
            rid=r["rid"], rtype="chunk",
            section_path=r["section_path"],
            chunk_text=r["chunk_text"],
            context_prefix=r["context_prefix"],
        )
        if await index_chunk_bm25(r["rid"], chunk):
            count += 1

    return count


async def _run_vector_indexing(tenant: str) -> int:
    """저장된 청크에 Vector 임베딩 생성."""
    from khala.index.embed import index_chunks_embedding
    from khala.models.chunk import Chunk
    from khala.providers.embedding import EmbeddingService

    rows = await db.fetch_all(
        """
        SELECT rid, section_path, chunk_text, context_prefix
        FROM chunks
        WHERE status = 'active' AND tenant = $1 AND embedding IS NULL
        """,
        tenant,
    )

    if not rows:
        return 0

    chunks = []
    for r in rows:
        chunk = Chunk(
            rid=r["rid"], rtype="chunk",
            section_path=r["section_path"],
            chunk_text=r["chunk_text"],
            context_prefix=r["context_prefix"],
        )
        chunks.append((r["rid"], chunk))

    try:
        svc = EmbeddingService()
        return await index_chunks_embedding(chunks, svc)
    except Exception as e:
        logger.error("vector_indexing_failed", error=str(e))
        return 0


async def _run_graph_extraction(tenant: str, config_path: str) -> int:
    """저장된 청크에서 Graph 관계 추출."""
    from khala.index.graph_extractor import extract_and_save_graph

    rows = await db.fetch_all(
        "SELECT rid, chunk_text FROM chunks WHERE status = 'active' AND tenant = $1",
        tenant,
    )

    if not rows:
        return 0

    chunk_pairs = [(r["rid"], r["chunk_text"]) for r in rows]
    return await extract_and_save_graph(chunk_pairs, tenant, config_path)


async def run_ingest(
    docs_path: str,
    force: bool = False,
    tenant: str = "default",
    config_path: str = "config.yaml",
    skip_index: bool = False,
    skip_graph: bool = False,
) -> IngestResult:
    """통합 Ingestion 파이프라인.

    Collect → Classify → Quarantine Gate → Chunk → DB 저장
    → BM25 인덱싱 → Vector 인덱싱 → Graph 추출

    Args:
        docs_path: 문서 폴더 경로
        force: True면 hash 무시, 전체 재인덱싱
        tenant: 테넌트 ID
        config_path: 설정 파일 경로
        skip_index: True면 BM25/Vector 인덱싱 건너뜀
        skip_graph: True면 Graph 추출 건너뜀

    Returns:
        IngestResult with summary
    """
    config = _load_config(config_path)
    result = IngestResult()

    # 1. Collect
    glob_pattern = config.get("sources", {}).get("glob_pattern", "**/*.md")
    collected_files = await collect_files(docs_path, glob_pattern, force, tenant)
    result.total_files = len(collected_files)

    if not collected_files:
        logger.info("no_files_to_ingest")
        return result

    # 2. Classify + Quarantine Gate + Chunk + Save
    for collected in collected_files:
        try:
            # Classify
            classification = classify(
                collected.relative_path,
                collected.content,
                collected.frontmatter,
                config,
            )

            # Save document metadata
            parent_rid = await _save_document(collected, classification, tenant)

            # Quarantine Gate
            if classification.is_quarantined:
                result.quarantined += 1
                logger.warning("document_quarantined",
                               path=collected.relative_path,
                               reason=classification.quarantine_reason)
                continue

            # Chunk
            chunks = chunk_document(collected.content, classification.language, config)
            if not chunks:
                result.skipped += 1
                continue

            # Save chunks
            saved = await _save_chunks(chunks, parent_rid, collected, classification, tenant)
            result.indexed += 1
            logger.info("document_indexed",
                        path=collected.relative_path,
                        chunks=saved)

        except Exception as e:
            result.failed += 1
            stage = "classify" if "classif" in str(e).lower() else "chunk" if "chunk" in str(e).lower() else "save"
            error_info = {
                "file_path": collected.relative_path,
                "error": str(e),
                "stage": stage,
            }
            result.errors.append(error_info)
            logger.error("document_ingest_failed", **error_info)

    # 3. BM25 + Vector 인덱싱 (인덱싱된 문서가 있을 때만)
    if result.indexed > 0 and not skip_index:
        try:
            result.bm25_indexed = await _run_bm25_indexing(tenant)
            logger.info("bm25_indexing_complete", count=result.bm25_indexed)
        except Exception as e:
            result.errors.append({"file_path": "*", "error": str(e), "stage": "bm25"})
            logger.error("bm25_indexing_failed", error=str(e))

        try:
            result.vector_indexed = await _run_vector_indexing(tenant)
            logger.info("vector_indexing_complete", count=result.vector_indexed)
        except Exception as e:
            result.errors.append({"file_path": "*", "error": str(e), "stage": "embed"})
            logger.error("vector_indexing_failed", error=str(e))

    # 4. Graph 추출
    if result.indexed > 0 and not skip_graph:
        try:
            result.edges_created = await _run_graph_extraction(tenant, config_path)
            logger.info("graph_extraction_complete", edges=result.edges_created)
        except Exception as e:
            result.errors.append({"file_path": "*", "error": str(e), "stage": "graph"})
            logger.error("graph_extraction_failed", error=str(e))

    logger.info("ingest_complete",
                total=result.total_files,
                indexed=result.indexed,
                quarantined=result.quarantined,
                failed=result.failed,
                bm25=result.bm25_indexed,
                vector=result.vector_indexed,
                edges=result.edges_created)
    return result
