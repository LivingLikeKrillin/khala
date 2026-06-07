"""ObservedEdge 도메인 모델 (OTel 관측 기반 관계)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from khala.models.resource import KhalaResource


@dataclass
class ObservedEdge(KhalaResource):
    """OTel trace에서 관측된 실제 서비스 간 호출 관계."""

    edge_type: str = "CALLS_OBSERVED"
    from_rid: str = ""
    to_rid: str = ""
    call_count: int = 0
    error_rate: float = 0.0
    latency_p50: float | None = None
    latency_p95: float | None = None
    latency_p99: float | None = None
    protocol: str = ""
    interaction_style: str = ""
    sample_trace_ids: list[str] = field(default_factory=list)
    trace_query_ref: str = ""
    resolved_via: str = ""
    window_start: datetime | None = None
    window_end: datetime | None = None
    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        self.rtype = "observed_edge"
