"""Pure coverage aggregation: derive vouched/total + weakness map from the ledger.

Artifacts carry their current content_hash (the caller computes them via
registry.current_hash). This module is pure — no IO, no LLM. State is derived per
artifact via `schedule.rebuild`, then `vouch.is_vouched`. The weakness map is the
lifetime per-question failure count from the rebuilt ReviewState.
"""

from __future__ import annotations

from ken.models import Attempt, ArtifactRef, CoverageReport, Question, WeaknessItem
from ken.schedule import rebuild
from ken.vouch import is_vouched


def compute_coverage_v1(
    artifacts: list[ArtifactRef],
    questions_by_artifact: dict[str, tuple[str | None, list[Question]]],
    attempts: list[Attempt],
) -> CoverageReport:
    """An artifact is covered iff it has >=1 current question and is_vouched over them.

    Questions whose stored store-hash != the artifact's current hash are stale (not
    bound to current content) -> the artifact is an orphan. The weakness map
    aggregates lifetime fail_count per current-hash question.
    """
    covered_ids: list[str] = []
    orphans: list[str] = []
    weakness: list[WeaknessItem] = []

    for art in artifacts:
        store_hash, questions = questions_by_artifact.get(art.artifact_id, (None, []))
        stale = store_hash != art.content_hash

        if not questions or stale:
            # no questions, or questions bound to stale content -> debt unrepaid
            orphans.append(art.artifact_id)
            continue

        current_hashes = {q.id: art.content_hash for q in questions}
        states = rebuild(attempts, current_hashes=current_hashes)

        for q in questions:
            st = states.get(q.id)
            if st is not None and st.fail_count > 0:
                weakness.append(
                    WeaknessItem(
                        question_id=q.id,
                        artifact_id=art.artifact_id,
                        fail_count=st.fail_count,
                    )
                )

        if is_vouched(questions, states):
            covered_ids.append(art.artifact_id)
        else:
            orphans.append(art.artifact_id)

    total = len(artifacts)
    covered = len(covered_ids)
    ratio = covered / total if total else 0.0
    return CoverageReport(
        total=total, covered=covered, ratio=ratio, orphans=orphans, weakness=weakness
    )
