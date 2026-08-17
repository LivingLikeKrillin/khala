"""Evidence Packet 조립.

검색 결과(hits)와 graph findings를 결합하여
LLM에 전달할 evidence packet을 구성한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import structlog

from nexus.repositories.graph import SubGraph
from nexus.search.doc_debt import DocDebt, debts_for_docs
from nexus.search.anchor_status import (
    AnchorStatus,
    DeletedMention,
    describe,
    statuses_for_chunks,
)
from nexus.search.hybrid import SearchHit
from nexus.search.provenance import PROMPT_NOTE, needs_note

logger = structlog.get_logger(__name__)


@dataclass
class EvidenceSnippet:
    """LLM에 전달할 개별 근거 조각."""
    chunk_rid: str
    doc_rid: str
    doc_title: str
    section_path: str
    source_uri: str
    #: 사람 표면이 읽는 짧은 조각(API 응답의 evidence_snippets[].text 그대로).
    text: str
    score: float
    classification: str
    doc_type: str = ""
    updated_at: datetime | None = None  # 신선도 판정용(SPEC-nexus-answer-staleness-warning)
    #: LLM 프롬프트에 들어가는 전문. 비면 `text` 로 떨어진다(옛 호출부 호환).
    full_text: str = ""
    #: 이 근거가 어떻게 존재하게 됐는가 (ADR-0010). 프롬프트까지 따라간다 — 답을 쓰는 모델이
    #: 저자가 쓴 문장과 기계가 그림에서 읽은 문장을 구별할 수 있어야 한다.
    provenance_tier: str = "authored"
    #: 이 문단이 부른 코드 이름들의 **현재 상태**(SPEC-nexus-doc-code-anchors §3.4).
    #: 앵커가 없는 코퍼스에서는 비어 있고, 그때 프롬프트는 오늘과 바이트 단위로 같다.
    code_anchors: list[AnchorStatus] = field(default_factory=list)
    #: 이 문단이 부르는데 **코드에서 지워진** 이름들(마이그레이션 029). 앵커와 나란히 두되
    #: 섞지 않는다 — 하나는 걸린 참조, 하나는 걸 곳이 사라진 참조다.
    code_deleted: list[DeletedMention] = field(default_factory=list)


@dataclass
class Provenance:
    """출처 정보."""
    doc_rid: str
    source_uri: str
    source_version: str = ""
    approved_hash: str = ""  # accountable-review stamp (SPEC §5.4)
    doc_title: str = ""  # 사람이 읽는 제목(인용·출처 표시용). source_uri 는 추적 포인터.


@dataclass
class EvidencePacket:
    """LLM에 전달할 evidence 패킷."""
    snippets: list[EvidenceSnippet] = field(default_factory=list)
    graph: SubGraph | None = None
    provenance: list[Provenance] = field(default_factory=list)
    #: 근거 문서에 붙은 **결정론적** 갱신 부채(supersede·제목 중복). 의미적 모순은 여기 없다 —
    #: 그건 답변자가 서술할 뿐 시스템이 보증하지 않는다 (`search/doc_debt.py`).
    debts: list[DocDebt] = field(default_factory=list)


async def assemble_packet(
    hits: list[SearchHit],
    graph: SubGraph | None = None,
    tenant: str = "",
    fill: list[SearchHit] | None = None,
) -> EvidencePacket:
    """검색 결과에서 evidence packet 조립.

    **네 표면(web API ×2 · A2A · CLI)이 전부 이 함수를 부른다.** 근거에 따라붙는 것은 여기서
    붙인다 — 표면마다 사본을 만들면 어느 하나가 조용히 빠지고, 사람과 에이전트가 다른 답을
    받는다.

    Args:
        hits: Hybrid 검색 결과
        graph: Graph 조회 결과 (optional)
        tenant: 앵커 상태 조회 범위. 비면 조회하지 않는다 — 앵커를 안 쓰는 호출부
            (테스트 픽스처·평가 하니스)가 DB 없이 패킷을 만들 수 있어야 한다.
        fill: 상한을 채운 문서의 남은 절(`SearchResult.fill`). **순위가 아니라 근거**다 —
            뒤에 문서 순서로 붙는다. 안 주면 오늘과 바이트 단위로 같은 패킷이 나온다.

    Returns:
        EvidencePacket
    """
    packet = EvidencePacket(graph=graph)
    seen_docs: set[str] = set()
    # 채운 절도 근거이므로 앵커·부채·출처를 **같은 규율로** 받는다. 여기서 갈라 두면 어떤
    # 근거에는 코드 앵커가 붙고 어떤 근거에는 안 붙는 상태가 되고, 그 차이는 화면에 안 보인다.
    ordered = list(hits) + [f for f in (fill or []) if f.rid not in {h.rid for h in hits}]
    # 쿼리 한 번으로 이번 결과 **전체**의 앵커 상태를 받는다. 스니펫마다 조회하면 그게 바로
    # `nexus code drift` 를 10분 걸리게 한 N+1 이다.
    anchors = await statuses_for_chunks(tenant, [h.rid for h in ordered])
    # 문서 부채도 같은 규율로 — 쿼리 하나, 없으면 조용하다.
    debts = await debts_for_docs(tenant, sorted({h.doc_rid for h in ordered}))
    packet.debts = [debts[r] for r in sorted(debts)]

    for hit in ordered:
        reading = anchors.get(hit.rid)
        packet.snippets.append(EvidenceSnippet(
            chunk_rid=hit.rid,
            doc_rid=hit.doc_rid,
            doc_title=hit.doc_title,
            section_path=hit.section_path,
            source_uri=hit.source_uri,
            text=hit.snippet,
            full_text=getattr(hit, "chunk_text", "") or hit.snippet,
            score=hit.score,
            classification=hit.classification,
            doc_type=hit.doc_type,
            updated_at=hit.updated_at,
            provenance_tier=getattr(hit, "provenance_tier", "authored"),
            code_anchors=reading.anchors if reading else [],
            code_deleted=reading.deleted if reading else [],
        ))

        if hit.doc_rid not in seen_docs:
            seen_docs.add(hit.doc_rid)
            packet.provenance.append(Provenance(
                doc_rid=hit.doc_rid,
                source_uri=hit.source_uri,
                source_version=hit.source_version,
                approved_hash=hit.approved_hash,
                doc_title=hit.doc_title,
            ))

    return packet


def format_for_llm(packet: EvidencePacket) -> str:
    """Evidence packet을 LLM 프롬프트용 텍스트로 변환."""
    parts: list[str] = []

    # Evidence snippets
    parts.append("## 검색된 근거 (Evidence)")
    for i, s in enumerate(packet.snippets, 1):
        # 인용 핸들 = 읽는 제목(대괄호). source_uri(UUID)는 per-snippet 에 노출하지
        # 않는다 — LLM 이 그걸 인용해 가독성을 해치므로. 추적용 uri 는 아래 출처 목록에만.
        parts.append(f"\n### 근거 {i} [{s.doc_title}] ({s.section_path})")
        parts.append(f"분류: {s.classification}")
        if s.doc_type:
            parts.append(f"타입: {s.doc_type}")
        # 등급은 **프롬프트에 보인다**. 여기서 빠지면 답을 쓰는 모델이 기계가 읽은 표와 저자가
        # 쓴 문장을 같은 것으로 다루고, 인용은 그 구별을 약속하지 못한다 (ADR-0010 hop 3).
        if needs_note(getattr(s, "provenance_tier", "authored")):
            parts.append(PROMPT_NOTE)
        # 문서가 부른 코드 이름이 지금도 있는가. **결정론으로 판정한 사실**이고, 모델은 그것을
        # 서술하기만 한다 — 낡음 여부를 모델에게 추측시키는 순간 그 판정은 근거를 잃는다.
        # 앵커가 없으면 빈 문자열이라 프롬프트는 오늘과 같다 (평가 팩과의 비교가 안 끊긴다).
        anchor_line = describe(getattr(s, "code_anchors", []),
                               getattr(s, "code_deleted", []))
        if anchor_line:
            parts.append(anchor_line)
        # **프롬프트에는 전문**, 화면에는 `text`(짧은 미리보기). 둘을 한 값으로 묶어 뒀더니
        # 846자 표가 앞 300자만 넘어가 모델이 답을 못 했다 (2026-08-08).
        #
        # `getattr` 인 이유: packet 을 손으로 만드는 호출부(테스트 픽스처, 다른 조립 경로)가
        # 이 필드를 모를 수 있다. 없으면 짧은 쪽으로 떨어진다 — 프롬프트가 비는 것보다 낫다.
        parts.append(f"\n{getattr(s, 'full_text', '') or s.text}")

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
        # 제목 우선(인용에 이 이름을 쓰도록), 추적 포인터(source_uri)는 괄호로 보조.
        label = p.doc_title or p.doc_rid
        parts.append(f"- {label} ({p.source_uri})")

    return "\n".join(parts)
