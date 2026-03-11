"""설계-관측 Diff Engine.

설계 edge(문서에서 추출)와 관측 edge(OTel에서 집계)를 비교하여
불일치를 탐지하고 quality_flags를 태깅한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

from khala import db
from khala.repositories.graph import DiffItem, PostgresGraphRepository

logger = structlog.get_logger(__name__)


@dataclass
class DiffReport:
    """Diff 보고서."""
    total_designed: int = 0
    total_observed: int = 0
    diffs: list[DiffItem] = field(default_factory=list)
    generated_at: str = ""


async def run_diff(
    tenant: str = "default",
    flag_filter: str | None = None,
) -> DiffReport:
    """설계-관측 diff 실행.

    1. v_edge_diff 뷰 조회
    2. quality_flags 태깅
    3. 보고서 생성

    Args:
        tenant: 테넌트 ID
        flag_filter: doc_only | observed_only | conflict (None이면 전체)

    Returns:
        DiffReport
    """
    report = DiffReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    # 통계
    report.total_designed = await db.fetch_val(
        "SELECT COUNT(*) FROM edges WHERE status = 'active' AND tenant = $1",
        tenant,
    ) or 0

    report.total_observed = await db.fetch_val(
        "SELECT COUNT(*) FROM observed_edges WHERE status = 'active' AND tenant = $1",
        tenant,
    ) or 0

    # Diff 조회 (v_edge_diff 뷰)
    pool = await db.get_pool()
    graph_repo = PostgresGraphRepository(pool)
    all_diffs = await graph_repo.get_diff(tenant)

    # 필터 적용
    if flag_filter:
        report.diffs = [d for d in all_diffs if d.flag == flag_filter]
    else:
        report.diffs = all_diffs

    # quality_flags 태깅
    await _tag_quality_flags(all_diffs, tenant)

    logger.info("diff_complete",
                designed=report.total_designed,
                observed=report.total_observed,
                diffs=len(report.diffs))

    return report


async def _tag_quality_flags(diffs: list[DiffItem], tenant: str) -> None:
    """Diff 결과에 따라 edge/observed_edge의 quality_flags 갱신."""
    for diff in diffs:
        now = datetime.now(timezone.utc)

        if diff.flag == "doc_only" and diff.edge_rid:
            await db.execute(
                """
                UPDATE edges
                SET quality_flags = array_append(
                    array_remove(quality_flags, 'doc_only'), 'doc_only'
                ),
                updated_at = $1
                WHERE rid = $2
                """,
                now, diff.edge_rid,
            )

        elif diff.flag == "observed_only" and diff.observed_edge_rid:
            await db.execute(
                """
                UPDATE observed_edges
                SET quality_flags = array_append(
                    array_remove(quality_flags, 'observed_only'), 'observed_only'
                ),
                updated_at = $1
                WHERE rid = $2
                """,
                now, diff.observed_edge_rid,
            )
