"""Evidence 도메인 모델."""

from __future__ import annotations

from dataclasses import dataclass

from khala.models.resource import KhalaResource


@dataclass
class Evidence(KhalaResource):
    """Edge/관계의 근거. Evidence 없는 edge는 존재하지 않는다."""

    subject_rid: str = ""      # 근거 대상 (edge, observed_edge 등)
    evidence_rid: str = ""     # 근거 소스 (chunk, trace ref 등)
    kind: str = "text_snippet"  # text_snippet | trace_ref | config_ref
    weight: float = 0.15
    note: str = ""

    def __post_init__(self) -> None:
        self.rtype = "evidence"
