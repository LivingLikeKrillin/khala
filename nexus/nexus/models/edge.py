"""Edge 도메인 모델 (설계 기반 관계)."""

from __future__ import annotations

from dataclasses import dataclass

from nexus.models.resource import NexusResource


@dataclass
class Edge(NexusResource):
    """문서에서 추출된 설계 기반 관계 (CALLS, PUBLISHES, SUBSCRIBES)."""

    edge_type: str = ""
    from_rid: str = ""
    to_rid: str = ""
    confidence: float = 0.5
    source_category: str = "DESIGNED"

    def __post_init__(self) -> None:
        self.rtype = "edge"
