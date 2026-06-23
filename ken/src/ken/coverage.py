"""Pure coverage aggregation: manifest refs + vouches -> CoverageReport.

Artifacts already carry their current content_hash (the caller computes them via
registry.current_hash); this module is pure — no IO, no LLM.
"""

from __future__ import annotations

from ken.models import ArtifactRef, CoverageReport, Vouch
from ken.vouch import is_fresh


def compute_coverage(
    artifacts: list[ArtifactRef],
    vouches: list[Vouch],
    *,
    now: str,
    ttl_days: int,
) -> CoverageReport:
    """An artifact is covered iff it has >=1 fresh vouch. Orphans are the rest."""
    covered_ids: list[str] = []
    orphans: list[str] = []
    for art in artifacts:
        fresh = any(
            v.artifact_id == art.artifact_id
            and is_fresh(v, current_hash=art.content_hash, now=now, ttl_days=ttl_days)
            for v in vouches
        )
        if fresh:
            covered_ids.append(art.artifact_id)
        else:
            orphans.append(art.artifact_id)

    total = len(artifacts)
    covered = len(covered_ids)
    ratio = covered / total if total else 0.0
    return CoverageReport(total=total, covered=covered, ratio=ratio, orphans=orphans)
