"""Entity/Relation 추출 + Evidence Binding.

entities.yaml(gazetteer)에 정의된 엔티티와
config.yaml의 extraction_triggers를 사용하여
청크에서 관계를 추출한다. LLM이 아닌 규칙 기반 추출.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog
import yaml

from khala import db
from khala.rid import (
    canonicalize_entity_name,
    edge_rid,
    entity_rid,
    evidence_rid,
)

logger = structlog.get_logger(__name__)


@dataclass
class EntityMatch:
    """텍스트에서 발견된 엔티티."""
    name: str  # canonical name
    entity_type: str
    position: int  # 텍스트 내 위치


@dataclass
class EdgeCandidate:
    """추출된 관계 후보."""
    edge_type: str  # CALLS | PUBLISHES | SUBSCRIBES
    from_entity: str  # canonical name
    to_entity: str  # canonical name
    from_type: str
    to_type: str
    source_chunk_rid: str
    confidence: float
    trigger_text: str


def _load_gazetteer(gazetteer_path: str = "entities.yaml") -> list[dict]:
    """entities.yaml 로드."""
    from pathlib import Path
    p = Path(gazetteer_path)
    if not p.exists():
        logger.warning("gazetteer_not_found", path=gazetteer_path)
        return []
    with open(p, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("entities", [])


def _build_entity_patterns(entities: list[dict]) -> list[tuple[re.Pattern, dict]]:
    """엔티티 목록에서 정규식 패턴 생성.

    이름 + aliases를 모두 패턴으로 등록. 긴 것부터 매칭 (greedy).
    """
    patterns: list[tuple[re.Pattern, dict]] = []

    for ent in entities:
        names = [ent["name"]] + ent.get("aliases", [])
        for name in names:
            # 정규식 특수문자 이스케이프, 대소문자 무시
            escaped = re.escape(name)
            pattern = re.compile(escaped, re.IGNORECASE)
            patterns.append((pattern, ent))

    # 긴 패턴을 먼저 매칭 (partial match 방지)
    patterns.sort(key=lambda x: len(x[0].pattern), reverse=True)
    return patterns


def find_entities_in_text(
    text: str,
    entity_patterns: list[tuple[re.Pattern, dict]],
) -> list[EntityMatch]:
    """텍스트에서 gazetteer에 정의된 엔티티를 찾는다."""
    found: list[EntityMatch] = []
    seen_names: set[str] = set()

    for pattern, ent in entity_patterns:
        for match in pattern.finditer(text):
            canonical = canonicalize_entity_name(ent["name"], ent["type"])
            if canonical not in seen_names:
                found.append(EntityMatch(
                    name=canonical,
                    entity_type=ent["type"],
                    position=match.start(),
                ))
                seen_names.add(canonical)

    return found


def _check_negation(text: str, trigger_pos: int) -> bool:
    """트리거 주변에 부정 표현이 있는지 확인."""
    negation_ko = ["않는다", "않는", "않음", "않고", "하지 않", "안 하"]
    negation_en = ["does not", "doesn't", "do not", "don't", "not "]

    # 트리거 앞뒤 30자 범위 확인
    start = max(0, trigger_pos - 30)
    end = min(len(text), trigger_pos + 30)
    context = text[start:end]

    for neg in negation_ko + negation_en:
        if neg in context:
            return True
    return False


def extract_relations(
    chunk_text: str,
    chunk_rid_val: str,
    entity_patterns: list[tuple[re.Pattern, dict]],
    triggers: dict,
) -> list[EdgeCandidate]:
    """청크에서 관계를 추출한다.

    규칙:
    - 같은 문장 또는 3문장 이내에 2개 엔티티 + 트리거 존재 → 관계
    - 부정 표현 필터: "호출하지 않는다" → skip
    - 양쪽 엔티티 모두 gazetteer에 있어야 함

    Args:
        chunk_text: 청크 텍스트
        chunk_rid_val: 청크의 rid
        entity_patterns: 엔티티 정규식 패턴
        triggers: config.yaml의 extraction_triggers

    Returns:
        EdgeCandidate 리스트
    """
    # 문장 분할 (한국어/영어 혼합)
    sentences = re.split(r'[.!?。]\s*|\n', chunk_text)
    candidates: list[EdgeCandidate] = []
    seen: set[tuple[str, str, str]] = set()  # (edge_type, from, to) 중복 방지

    # 3문장 윈도우로 관계 탐색
    for i, sent in enumerate(sentences):
        # 윈도우: 현재 문장 + 앞뒤 1문장
        window_start = max(0, i - 1)
        window_end = min(len(sentences), i + 2)
        window_text = " ".join(sentences[window_start:window_end])

        # 윈도우에서 엔티티 검색
        entities = find_entities_in_text(window_text, entity_patterns)
        if len(entities) < 2:
            continue

        # 각 트리거 유형별 확인
        for edge_type, trigger_langs in triggers.items():
            all_triggers = trigger_langs.get("ko", []) + trigger_langs.get("en", [])

            for trigger in all_triggers:
                trigger_lower = trigger.lower()
                window_lower = window_text.lower()

                if trigger_lower not in window_lower:
                    continue

                trigger_pos = window_lower.find(trigger_lower)

                # 부정 표현 확인
                if _check_negation(window_text, trigger_pos):
                    continue

                # 위치 기반으로 from/to 결정 (트리거 앞 = from, 뒤 = to)
                for j, from_ent in enumerate(entities):
                    for to_ent in entities[j + 1:]:
                        key = (edge_type, from_ent.name, to_ent.name)
                        if key in seen:
                            continue
                        seen.add(key)

                        candidates.append(EdgeCandidate(
                            edge_type=edge_type,
                            from_entity=from_ent.name,
                            to_entity=to_ent.name,
                            from_type=from_ent.entity_type,
                            to_type=to_ent.entity_type,
                            source_chunk_rid=chunk_rid_val,
                            confidence=0.6,  # 규칙 기반 추출 기본 confidence
                            trigger_text=trigger,
                        ))

    return candidates


async def ensure_entity_exists(
    tenant: str,
    name: str,
    entity_type: str,
    source_kind: str = "manual",
    description: str = "",
    aliases: list[str] | None = None,
) -> str:
    """엔티티가 DB에 존재하는지 확인하고, 없으면 생성. rid 반환."""
    canonical = canonicalize_entity_name(name, entity_type)
    rid = entity_rid(tenant, entity_type, canonical)
    now = datetime.now(timezone.utc)

    await db.execute(
        """
        INSERT INTO entities (
            rid, rtype, tenant, classification, owner,
            source_kind, status, created_at, updated_at,
            entity_type, name, aliases, description
        ) VALUES (
            $1, 'entity', $2, 'INTERNAL', 'indexer',
            $3::source_kind, 'active', $4, $4,
            $5, $6, $7, $8
        )
        ON CONFLICT (tenant, entity_type, name) DO NOTHING
        """,
        rid, tenant, source_kind, now,
        entity_type, canonical, aliases or [], description,
    )
    return rid


async def save_edge_with_evidence(
    candidate: EdgeCandidate,
    tenant: str,
) -> str | None:
    """추출된 관계를 edge + evidence로 저장.

    Evidence 없는 edge 금지 원칙을 준수한다.
    """
    try:
        # 양쪽 엔티티 rid 확보
        from_rid = await ensure_entity_exists(
            tenant, candidate.from_entity, candidate.from_type)
        to_rid = await ensure_entity_exists(
            tenant, candidate.to_entity, candidate.to_type)

        # Edge 저장
        e_rid = edge_rid(tenant, candidate.edge_type, from_rid, to_rid)
        now = datetime.now(timezone.utc)

        await db.execute(
            """
            INSERT INTO edges (
                rid, rtype, tenant, classification, owner,
                source_kind, status, created_at, updated_at,
                edge_type, from_rid, to_rid, confidence, source_category,
                prov_pipeline, prov_inputs
            ) VALUES (
                $1, 'edge', $2, 'INTERNAL', 'indexer',
                'git', 'active', $3, $3,
                $4, $5, $6, $7, 'DESIGNED',
                'graph-extractor-v1', $8
            )
            ON CONFLICT (rid) DO UPDATE SET
                confidence = GREATEST(edges.confidence, EXCLUDED.confidence),
                updated_at = EXCLUDED.updated_at
            """,
            e_rid, tenant, now,
            candidate.edge_type, from_rid, to_rid, candidate.confidence,
            [candidate.source_chunk_rid],
        )

        # Evidence 저장 (edge ↔ chunk 연결)
        evi_rid = evidence_rid(e_rid, candidate.source_chunk_rid)
        await db.execute(
            """
            INSERT INTO evidence (
                rid, rtype, tenant, classification, owner,
                source_kind, status, created_at, updated_at,
                subject_rid, evidence_rid, kind, weight, note
            ) VALUES (
                $1, 'evidence', $2, 'INTERNAL', 'indexer',
                'git', 'active', $3, $3,
                $4, $5, 'text_snippet', 0.15, $6
            )
            ON CONFLICT (rid) DO NOTHING
            """,
            evi_rid, tenant, now,
            e_rid, candidate.source_chunk_rid,
            f"trigger: {candidate.trigger_text}",
        )

        return e_rid

    except Exception as e:
        logger.error("edge_save_failed",
                     edge_type=candidate.edge_type,
                     from_entity=candidate.from_entity,
                     to_entity=candidate.to_entity,
                     error=str(e))
        return None


async def extract_and_save_graph(
    chunks: list[tuple[str, str]],  # (chunk_rid, chunk_text)
    tenant: str = "default",
    config_path: str = "config.yaml",
    gazetteer_path: str = "entities.yaml",
) -> int:
    """청크들에서 관계를 추출하고 DB에 저장.

    Returns:
        생성/갱신된 edge 수
    """
    from pathlib import Path
    config_file = Path(config_path)
    config: dict = {}
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}

    triggers = config.get("extraction_triggers", {})
    if not triggers:
        logger.warning("no_extraction_triggers_configured")
        return 0

    gazetteer = _load_gazetteer(gazetteer_path)
    if not gazetteer:
        logger.warning("empty_gazetteer")
        return 0

    # gazetteer의 엔티티를 미리 DB에 등록
    for ent in gazetteer:
        await ensure_entity_exists(
            tenant,
            ent["name"],
            ent["type"],
            description=ent.get("description", ""),
            aliases=ent.get("aliases", []),
        )

    entity_patterns = _build_entity_patterns(gazetteer)
    total_edges = 0

    for chunk_rid_val, chunk_text in chunks:
        candidates = extract_relations(chunk_text, chunk_rid_val, entity_patterns, triggers)
        for candidate in candidates:
            result = await save_edge_with_evidence(candidate, tenant)
            if result:
                total_edges += 1

    logger.info("graph_extraction_complete", edges_created=total_edges)
    return total_edges
