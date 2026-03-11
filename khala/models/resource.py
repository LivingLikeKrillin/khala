"""Canonical Resource Model (CRM) — Khala의 모든 데이터 객체의 기반.

documents, chunks, entities, edges, observed_edges, evidence 모두 이 클래스를 상속한다.
정책 필터, GC, quarantine 로직은 이 인터페이스에 대해 작성된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class KhalaResource:
    """모든 Khala 리소스의 공통 필드 (CRM)."""

    # ── Identity ──
    rid: str
    rtype: str  # document|chunk|entity|edge|observed_edge|evidence

    # ── Governance ──
    tenant: str = "default"
    classification: str = "INTERNAL"
    owner: str = "unknown"
    is_quarantined: bool = False

    # ── Source ──
    source_uri: str = ""
    source_version: str = ""
    source_kind: str = "git"

    # ── Content ──
    hash: str = ""
    labels: list[str] = field(default_factory=list)
    quality_flags: list[str] = field(default_factory=list)
    status: str = "active"

    # ── Lifecycle ──
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ── Provenance ──
    prov_pipeline: str = ""
    prov_inputs: list[str] = field(default_factory=list)
    prov_transform: str = ""


# ── Classification 순서 ──
CLASSIFICATION_LEVELS = {"PUBLIC": 0, "INTERNAL": 1, "RESTRICTED": 2}


def is_accessible(resource: KhalaResource, user_clearance: str, user_tenant: str) -> bool:
    """CRM 기반 접근 통제. 모든 검색/조회에 이 함수를 적용한다."""
    if resource.is_quarantined:
        return False
    if resource.status != "active":
        return False
    if resource.tenant != user_tenant:
        return False
    user_level = CLASSIFICATION_LEVELS.get(user_clearance, 0)
    resource_level = CLASSIFICATION_LEVELS.get(resource.classification, 2)
    return user_level >= resource_level


def base_filter_sql() -> str:
    """모든 DB SELECT에 적용할 공통 WHERE 절. 예외 없음."""
    return """
        AND tenant = %(tenant)s
        AND classification <= %(clearance)s::classification_level
        AND is_quarantined = false
        AND status = 'active'
    """
