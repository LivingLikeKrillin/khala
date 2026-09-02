"""Canonical Resource Model (CRM) — Nexus의 모든 데이터 객체의 기반.

documents, chunks, entities, edges, observed_edges, evidence 모두 이 클래스를 상속한다.
정책 필터, GC, quarantine 로직은 이 인터페이스에 대해 작성된다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class NexusResource:
    """모든 Nexus 리소스의 공통 필드 (CRM)."""

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
# ⛔ **등급 순서표는 여기 없다.** 2026-09-02 까지 이 파일에 두 번째 사본
# (`CLASSIFICATION_LEVELS`)과 그것으로 접근 통제를 구현한 `is_accessible()` 이 있었고,
# 그 docstring 이 *"모든 검색/조회에 이 함수를 적용한다"* 고 지시했다. **프로덕션 호출자는
# 0이었다** — 실제 통제는 SQL 의 네 절이 한다. 그런데 정본(`auth/clearance.py`)에는 SQL enum
# 동등성 검사가 있고 사본에는 없어서, enum 에 등급이 추가되면 정본만 걸리고 사본은 조용히
# 뒤처지는 구조였다(외부 평가 F1).
#
# 함께 있던 `base_filter_sql()` 도 지웠다 — psycopg 스타일(`%(tenant)s`)인데 이 코드베이스는
# asyncpg 이고, `claims/repository.py` 가 이미 "미사용" 이라 적어 두고 있었다.
#
# **사본은 고치지 않고 없앤다.** 이 리포가 등급 목록을 두 번 적었다가 곧바로 갈린 전례가 있다.
# 순서표가 필요하면 `nexus.auth.clearance.ORDER` 하나뿐이다.