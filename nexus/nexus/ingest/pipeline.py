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

from nexus import db
from nexus.documents.origin import source_kind_for
from nexus.ingest.classifier import ClassificationResult, classify
from nexus.ingest.chunker import ChunkData, chunk_document
from nexus.ingest.collector import CollectedFile, collect_files
from nexus.ingest.title import derive_title
from nexus.rid import chunk_rid, doc_rid

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
    #: 적재 뒤 이 테넌트의 커버리지 (SPEC-nexus-index-completeness §3.4). `None` 은 "못 쟀다".
    #: **이것은 편의이지 보장이 아니다** — 프로세스가 죽으면 여기까지 오지 못한다. 보장은
    #: `nexus status` 에 있다 (§2.5). 그래서 "0 건 남았다" 와 "안 쟀다" 를 구분해 둔다.
    coverage: dict | None = None
    #: 구멍의 **이유** (`embed_refusals` 집계). `None` 은 "못 쟀다".
    #: 커버리지가 크기를 말하고 이것이 처방을 말한다 — 수만 보여 주면 읽는 사람이 할 수 있는 것은
    #: 같은 실패를 다시 부르는 것뿐이다.
    refusals: dict | None = None


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
    approved_hash: str = "",
) -> str:
    """문서 메타데이터를 DB에 저장. rid 반환.

    ``approved_hash``는 상위 거버넌스 도구(Arbiter)의 accountable-review 스탬프로,
    nexus 자체의 변경 감지 해시(content_hash)와 구분된다. 일반 문서는 ''.
    """
    rid = doc_rid(collected.canonical_uri)
    now = datetime.now(timezone.utc)

    # 재수집 감지: upsert 전 기존 content_hash를 조회해 둔다(상태 무관 — 이미 active인 행).
    prev = await db.fetch_one(
        "SELECT content_hash FROM documents WHERE rid = $1", rid,
    )

    await db.execute(
        """
        INSERT INTO documents (
            rid, rtype, tenant, classification, owner,
            source_uri, source_kind, hash, content_hash,
            is_quarantined, quality_flags, status,
            created_at, updated_at,
            title, doc_type, language, approved_hash, n_images
        ) VALUES (
            $1, 'document', $2, $3::classification_level, 'indexer',
            $4, $14::source_kind, $5, $5,
            $6, $7, 'active',
            $8, $8,
            $9, $10, $11, $12, $13
        )
        ON CONFLICT (rid) DO UPDATE SET
            hash = EXCLUDED.hash,
            content_hash = EXCLUDED.content_hash,
            classification = EXCLUDED.classification,
            is_quarantined = EXCLUDED.is_quarantined,
            quality_flags = EXCLUDED.quality_flags,
            updated_at = EXCLUDED.updated_at,
            -- title 이 빠져 있었다. doc_type·language 는 갱신하면서 제목만 최초 삽입값에
            -- 영원히 갇혔다 — 원본에서 페이지 이름을 고쳐도, 재수집해도, --force 를 줘도.
            title = EXCLUDED.title,
            doc_type = EXCLUDED.doc_type,
            language = EXCLUDED.language,
            approved_hash = EXCLUDED.approved_hash,
            -- 그림 수는 신호원이다 (ADR-0002 게이트 형식, migration 011). 컨버터가 이미 세고
            -- 있었는데 frontmatter 에만 있어서 질의할 수 없었다.
            n_images = EXCLUDED.n_images,
            -- 갱신 목록에 없으면 **재적재로도 고쳐지지 않는다.** 이미 들어앉은 108건이 그랬다.
            source_kind = EXCLUDED.source_kind
        """,
        rid, tenant, classification.classification,
        collected.canonical_uri, collected.content_hash,
        classification.is_quarantined,
        classification.pii_types if classification.is_quarantined else [],
        now,
        derive_title(collected.frontmatter, collected.content, collected.relative_path),
        classification.doc_type, classification.language, approved_hash,
        # 컨버터가 세어 frontmatter 에 넣어 둔 값. 없으면 0 — 파일 적재처럼 그림 개념이
        # 없는 경로가 그렇고, 0 은 "그림 없음" 으로 참이다.
        int(collected.frontmatter.get("image_count") or 0),
        source_kind_for(collected.canonical_uri),
    )

    # content_hash가 바뀐 재수집(덮어쓰기)이면 이벤트 1건 기록 → v_entropy_signals 신호원.
    if prev is not None and prev["content_hash"] != collected.content_hash:
        await db.execute(
            "INSERT INTO doc_reingest_events (rid, tenant, old_content_hash, new_content_hash) "
            "VALUES ($1, $2, $3, $4)",
            rid, tenant, prev["content_hash"], collected.content_hash,
        )

    return rid


def _invalidate_derived() -> str:
    """텍스트가 바뀌면 그 텍스트에서 파생된 **모든 것**을 무효화하는 SET 절
    (SPEC-nexus-generation-of-record §3.4).

    예전엔 `embedding` 과 `tsvector_ko` 만 NULL 로 되돌렸다. 컬럼이 하나이던 시절엔 그게 전부였고,
    ADR-0006 은 그 수정을 두고 *"killing stale-vector retrieval drift"* 라고 적었다. 두 번째 벡터
    컬럼이 생기면서 그 문장이 거짓이 됐다 — 재임베딩 큐가 `WHERE <컬럼> IS NULL` 이라, 안 지워진
    컬럼은 큐에 영영 안 들어가고 **옛 텍스트의 벡터로 검색된다**. 실측 8건(최저 코사인 0.593).

    그래서 컬럼을 손으로 나열하지 않고 **레지스트리에서 꺼낸다.** 세 번째 세대가 추가될 때
    누군가 이 함수를 잊는 것이 이 버그가 돌아오는 유일한 길이었다.

    컬럼명은 화이트리스트(`VECTOR_COLUMNS`)에서만 오므로 문자열 조립이 안전하다 — 설정값이
    SQL 에 닿는 경로가 아니다.
    """
    from nexus.index.vector_index import VECTOR_COLUMNS

    changed = "chunks.chunk_text IS DISTINCT FROM EXCLUDED.chunk_text"
    parts = [f"{col} = CASE WHEN {changed} THEN NULL ELSE chunks.{col} END"
             for col in sorted(VECTOR_COLUMNS)]
    parts.append(f"tsvector_ko = CASE WHEN {changed} THEN NULL ELSE chunks.tsvector_ko END")
    return ",\n                ".join(parts)


async def _bind_code_anchors(chunks, parent_rid: str, tenant: str, config: dict) -> None:
    """문서가 백틱으로 부른 심볼을 코드 인덱스에 붙인다 (SPEC-nexus-doc-code-anchors §3.3).

    **적재를 절대 실패시키지 않는다.** 앵커는 부가 신호이고, 신호가 본체를 죽이면 안 된다.
    스캔 기록이 없으면 후보는 전부 `unresolved` 거부로 남고 §3.6 재바인딩이 나중에 줍는다 —
    그래서 스캔보다 먼저 적재해도 영구 미앵커가 되지 않는다.
    """
    repo_path = (config.get("code_source") or {}).get("repo_path", "")
    if not repo_path:
        return

    from pathlib import Path

    from nexus.index import anchor_store
    from nexus.index.anchors import bind, extract_candidates
    from nexus.rid import chunk_rid

    repo = Path(repo_path).name
    try:
        scan = await anchor_store.last_scan(tenant, repo)
        commit = scan.scan_commit if scan else ""

        for chunk in chunks:
            candidates = extract_candidates(chunk.chunk_text)
            if not candidates:
                continue
            rid = chunk_rid(parent_rid, chunk.section_path, chunk.chunk_index)

            resolved = {c: await anchor_store.resolve_symbol(tenant, repo, c)
                        for c in candidates}
            outcome = bind(candidates, lambda c: resolved[c])

            await anchor_store.save_bindings(
                tenant, repo, rid, outcome.anchors, outcome.refusals, commit)
    except Exception as e:  # noqa: BLE001 — 앵커 실패가 적재를 막으면 안 된다
        logger.warning("code_anchor_bind_failed", doc_rid=parent_rid,
                       error=type(e).__name__)


async def _save_chunks(
    chunks: list[ChunkData],
    parent_rid: str,
    collected: CollectedFile,
    classification: ClassificationResult,
    tenant: str,
) -> int:
    """청크를 DB에 저장. 기존 청크 soft_delete 후 새로 삽입.

    청크 상태는 저장 시점의 부모 문서 상태를 따른다: 문서가 active면 청크도 active,
    문서가 non-active(superseded/soft_deleted)면 청크도 superseded로 기록한다.
    이로써 이미 superseded된 문서의 소스를 재수집(편집/``--force``)해도 청크가
    active로 되살아나 '죽은 문서 아래 살아있는 청크'라는 엔트로피 분열을 만들지 않는다.
    """
    # 부모 문서가 active가 아니면 새/upsert 청크도 살리지 않는다.
    parent = await db.fetch_one("SELECT status FROM documents WHERE rid = $1", parent_rid)
    chunk_status = "active" if (parent is not None and parent["status"] == "active") else "superseded"

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
            f"""
            INSERT INTO chunks (
                rid, rtype, tenant, classification, owner,
                source_uri, source_kind, hash,
                is_quarantined, status,
                created_at, updated_at,
                doc_rid, section_path, chunk_text,
                chunk_index, prov_pipeline, prov_inputs,
                provenance_tier
            ) VALUES (
                $1, 'chunk', $2, $3::classification_level, 'indexer',
                $4, $14::source_kind, $5,
                false, $12,
                $6, $6,
                $7, $8, $9,
                $10, 'indexer-v1', $11,
                $13::provenance_tier
            )
            ON CONFLICT (rid) DO UPDATE SET
                chunk_text = EXCLUDED.chunk_text,
                -- 등급은 텍스트를 따라간다. 재적재로 저자 텍스트가 들어온 자리에 옛 등급이
                -- 남으면 그 chunk 는 자기 내용에 대해 거짓말을 한다.
                provenance_tier = EXCLUDED.provenance_tier,
                classification = EXCLUDED.classification,
                updated_at = EXCLUDED.updated_at,
                status = $12,
                source_kind = EXCLUDED.source_kind,
                {_invalidate_derived()}
            """,
            rid, tenant, classification.classification,
            collected.canonical_uri, collected.content_hash,
            now,
            parent_rid, chunk.section_path, chunk.chunk_text,
            chunk.chunk_index, [parent_rid], chunk_status,
            getattr(chunk, "provenance_tier", "authored"),
            source_kind_for(collected.canonical_uri),
        )
        saved += 1

    return saved


async def _run_bm25_indexing(tenant: str) -> int:
    """저장된 청크에 BM25 인덱스 생성."""
    from nexus.index.bm25 import index_chunk_bm25
    from nexus.models.chunk import Chunk

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


async def _run_vector_indexing(tenant: str, config: dict | None = None) -> int:
    """저장된 청크에 Vector 임베딩 생성.

    세대(모델·백엔드·컬럼)는 팩토리가 정한다 — 여기서 `EmbeddingService()` 를 직접 만들면 적재만
    다른 세대를 쓰게 된다 (SPEC-nexus-embedding-cutover-seam §4.1).
    """
    from nexus.index.embed import index_chunks_embedding
    from nexus.index.vector_index import configured_column
    from nexus.models.chunk import Chunk
    from nexus.providers.embedding import embedding_service_from_config

    # 큐도 **설정된 세대의 컬럼**이어야 한다. 옛 컬럼의 NULL 을 세면 컷오버 뒤에는 채워야 할
    # 청크를 하나도 못 찾는다 (§4.3).
    col = configured_column(config)
    rows = await db.fetch_all(
        f"""
        SELECT rid, section_path, chunk_text, context_prefix
        FROM chunks
        WHERE status = 'active' AND tenant = $1 AND {col} IS NULL
        -- 배치는 제일 긴 글에 맞춰 패딩된다. 길이순으로 뽑아야 한 배치가 고르게 차고, 짧은
        -- 글들이 긴 글 하나에 끌려가 빈칸으로 계산되지 않는다 (`reembed.pending_rids` 와 같은
        -- 이유 · 같은 순서). 설계문서 코퍼스에서 잰 낭비가 60% 였다.
        ORDER BY length(chunk_text), rid
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
        svc = embedding_service_from_config(config)
        return await index_chunks_embedding(chunks, svc, column=col)
    except Exception as e:
        logger.error("vector_indexing_failed", error=str(e))
        return 0


async def _run_graph_extraction(tenant: str, config_path: str) -> int:
    """저장된 청크에서 Graph 관계 추출."""
    from nexus.index.graph_extractor import extract_and_save_graph

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
    approved_hash: str = "",
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
        approved_hash: 이 실행의 문서에 부여할 거버넌스 스탬프(Arbiter content_hash).
            단일 거버넌스 문서 ingest(예: A2A ingest_governed_doc 브리지)용. 기본 ''.

    Returns:
        IngestResult with summary
    """
    config = _load_config(config_path)
    result = IngestResult()

    # 0. 이 프로세스가 해석한 세대가 코퍼스의 선언과 같은가 (SPEC-nexus-generation-of-record §3.2).
    # **collect 보다도 먼저** 본다: "아무것도 쓰기 전에 거부한다" 는 문서 한 행도 안 남긴다는 뜻이다.
    # 모든 쓰기 경로(CLI·HTTP·A2A·ingest-notion)가 이 함수로 모이므로 검사는 여기 한 곳이면 된다.
    if not skip_index:
        from nexus.index.generation import assert_writable
        from nexus.index.vector_index import configured_column
        from nexus.providers.embedding import embedding_service_from_config

        svc = embedding_service_from_config(config)
        await assert_writable(tenant, configured_column(config), svc.get_model_name(),
                              what="ingest")

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

            # Save document metadata (approved_hash: governance stamp for this run's docs)
            parent_rid = await _save_document(collected, classification, tenant, approved_hash)

            # Quarantine Gate
            if classification.is_quarantined:
                result.quarantined += 1
                logger.warning("document_quarantined",
                               path=collected.relative_path,
                               reason=classification.quarantine_reason)
                continue

            # Chunk
            # 마커 신뢰는 **수집 경로가 선언**한다. 파일시스템 문서와 외부 spec 페이로드는
            # Notion 컨버터를 거치지 않으므로, 컨버터에서만 정화하면 그 경로의 저자 산문이
            # machine_read 로 찍힌다 — 모함이 반대 방향으로 일어난다.
            chunks = chunk_document(
                collected.content, classification.language, config,
                trust_vision_markers=getattr(collected, "vision_extracted", False))
            if not chunks:
                result.skipped += 1
                continue

            # Save chunks
            saved = await _save_chunks(chunks, parent_rid, collected, classification, tenant)
            await _bind_code_anchors(chunks, parent_rid, tenant, config)
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
            result.vector_indexed = await _run_vector_indexing(tenant, config)
            logger.info("vector_indexing_complete", count=result.vector_indexed)
        except Exception as e:
            result.errors.append({"file_path": "*", "error": str(e), "stage": "embed"})
            logger.error("vector_indexing_failed", error=str(e))

        # 3b. 이 적재가 무엇을 남겼는가 (SPEC-nexus-index-completeness §3.4).
        # 인덱싱 단계가 **예외를 냈든 아니든** 잰다 — 삼켜진 실패의 흔적은 결과가 아니라 상태에
        # 남기 때문이다. 여기서 거부하지는 않는다(§2.4).
        try:
            from nexus.index.embed_health import fetch_coverage_by_tenant, fetch_refusals
            from nexus.index.vector_index import configured_column

            col = configured_column(config)
            row = next((c for c in await fetch_coverage_by_tenant()
                        if c["tenant"] == tenant), None)
            # 이유는 구멍이 있든 없든 잰다 — 0 이어야 정상이고, 0 인 것을 본 것과 안 본 것은 다르다.
            result.refusals = await fetch_refusals(col, tenant=tenant)
            if row is not None:
                result.coverage = row
                gap = row["active"] - row[col]
                if gap:
                    logger.warning("ingest_left_chunks_unindexed", tenant=tenant, column=col,
                                   active=row["active"], embedded=row[col], pending=gap,
                                   refused=result.refusals["total"],
                                   # **이유가 처방이다.** 이 줄이 없으면 안내받은 재시도가 같은
                                   # 자리에서 같은 이유로 다시 실패한다.
                                   reasons=[r for r, _ in result.refusals["reasons"]],
                                   recover=f"nexus reembed run --tenant {tenant}")
        except Exception as e:      # noqa: BLE001 — 커버리지 조회 실패가 적재를 무르지 않는다
            logger.warning("ingest_coverage_unavailable", error=str(e))

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
