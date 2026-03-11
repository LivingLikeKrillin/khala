"""Evidence Packet 조립.

검색 결과(hits)와 graph findings를 결합하여
LLM에 전달할 evidence packet을 구성한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from khala import db
from khala.repositories.graph import SubGraph
from khala.search.hybrid import SearchHit

logger = structlog.get_logger(__name__)


@dataclass
class EvidenceSnippet:
    """LLM에 전달할 개별 근거 조각."""
    chunk_rid: str
    doc_rid: str
    doc_title: str
    section_path: str
    source_uri: str
    text: str
    score: float
    classification: str


@dataclass
class Provenance:
    """출처 정보."""
    doc_rid: str
    source_uri: str
    source_version: str = ""


@dataclass
class EvidencePacket:
    """LLM에 전달할 evidence 패킷."""
    snippets: list[EvidenceSnippet] = field(default_factory=list)
    graph: SubGraph | None = None
    provenance: list[Provenance] = field(default_factory=list)


def assemble_packet(
    hits: list[SearchHit],
    graph: SubGraph | None = None,
) -> EvidencePacket:
    """검색 결과에서 evidence packet 조립.

    Args:
        hits: Hybrid 검색 결과
        graph: Graph 조회 결과 (optional)

    Returns:
        EvidencePacket
    """
    packet = EvidencePacket(graph=graph)
    seen_docs: set[str] = set()

    for hit in hits:
        packet.snippets.append(EvidenceSnippet(
            chunk_rid=hit.rid,
            doc_rid=hit.doc_rid,
            doc_title=hit.doc_title,
            section_path=hit.section_path,
            source_uri=hit.source_uri,
            text=hit.snippet,
            score=hit.score,
            classification=hit.classification,
        ))

        if hit.doc_rid not in seen_docs:
            seen_docs.add(hit.doc_rid)
            packet.provenance.append(Provenance(
                doc_rid=hit.doc_rid,
                source_uri=hit.source_uri,
                source_version=hit.source_version,
            ))

    return packet


def format_for_llm(packet: EvidencePacket) -> str:
    """Evidence packet을 LLM 프롬프트용 텍스트로 변환."""
    parts: list[str] = []

    # Evidence snippets
    parts.append("## 검색된 근거 (Evidence)")
    for i, s in enumerate(packet.snippets, 1):
        parts.append(f"\n### 근거 {i} [{s.doc_title}] ({s.section_path})")
        parts.append(f"출처: {s.source_uri}")
        parts.append(f"분류: {s.classification}")
        parts.append(f"\n{s.text}")

    # Graph findings
    if packet.graph:
        parts.append("\n## 그래프 관계 (Graph)")
        parts.append(f"중심 엔티티: {packet.graph.center_name}")

        if packet.graph.edges:
            parts.append("\n### 설계 기반 관계 (Designed)")
            for e in packet.graph.edges:
                parts.append(f"- [{e.edge_type}] {e.from_name} → {e.to_name} (confidence: {e.confidence:.2f})")

        if packet.graph.observed_edges:
            parts.append("\n### 관측 기반 관계 (Observed)")
            for o in packet.graph.observed_edges:
                parts.append(
                    f"- [{o.edge_type}] {o.from_name} → {o.to_name} "
                    f"(calls: {o.call_count}, error_rate: {o.error_rate:.2%}, p95: {o.latency_p95}ms)"
                )

    # Provenance
    parts.append("\n## 출처 목록")
    for p in packet.provenance:
        parts.append(f"- {p.doc_rid}: {p.source_uri}")

    return "\n".join(parts)
