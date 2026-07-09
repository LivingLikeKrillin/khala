"""재조정 계획을 포착하고, 확정 시 지문을 대조한다 (SPEC-nexus-notion-source-console §4.4).

`make_reconcile_fn` 은 개수만 돌려준다. 웹 미리보기는 **무엇을** 지우는지 보여줘야 하고,
확정은 그때 본 계획과 지금 계획이 같은지 확인해야 한다. 그 두 가지를 여기서 한다.

`expected_plan_hash` 가 주어지면(=확정 요청) 재계산한 지문과 대조하고, 다르면 **아무것도
적용하지 않고** stale 로 표시한다. 미리보기가 "2건"이었는데 확정 순간 200건이 되어 있는
상황을 막는 유일한 장치다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nexus.ingest.sources.notion_reconcile import (
    ReconcileOutcome,
    backfill_source_roots,
    fetch_notion_scope,
    plan_reconcile,
)
from nexus.sources.plan_hash import compute_plan_hash


@dataclass
class Planner:
    tenant: str
    dry_run: bool
    force: bool
    threshold: float
    expected_plan_hash: str | None

    walked_roots: list[str] = field(default_factory=list)
    prune_entries: list[tuple[str, str]] = field(default_factory=list)
    revive_entries: list[tuple[str, str]] = field(default_factory=list)
    plan_payload: dict = field(default_factory=dict)
    stale: bool = False

    async def reconcile_fn(
        self, tenant: str, walked_roots: set[str], live_by_rid: dict[str, list[str]]
    ) -> ReconcileOutcome:
        await backfill_source_roots(tenant, walked_roots, live_by_rid)
        self.walked_roots = sorted(walked_roots)

        scope = await fetch_notion_scope(tenant, walked_roots)
        by_rid = {r.rid: r for r in scope}
        plan = plan_reconcile(scope, set(live_by_rid), threshold=self.threshold, force=self.force)

        self.prune_entries = [(rid, by_rid[rid].content_hash) for rid in plan.prune]
        self.revive_entries = [(rid, by_rid[rid].content_hash) for rid in plan.revive]
        self.plan_payload = {
            "prune": [{"rid": rid, "title": by_rid[rid].title} for rid in plan.prune],
            "revive": [{"rid": rid, "title": by_rid[rid].title} for rid in plan.revive],
        }

        if plan.refused:
            return ReconcileOutcome(refused=True, reason=plan.reason)

        if self.expected_plan_hash is not None:
            current = compute_plan_hash(self.walked_roots, self.prune_entries, self.revive_entries)
            if current != self.expected_plan_hash:
                self.stale = True
                return ReconcileOutcome(reason="plan_stale")

        if self.dry_run:
            return ReconcileOutcome(
                pruned=len(plan.prune), revived=len(plan.revive),
                reason="dry-run: 적용하지 않음",
            )

        from nexus.lifecycle import revive, soft_delete

        pruned = 0
        for rid in plan.prune:
            if await soft_delete(rid, tenant) == "soft_deleted":
                pruned += 1
        revived = 0
        for rid in plan.revive:
            if await revive(rid, tenant) == "revived":
                revived += 1
        return ReconcileOutcome(pruned=pruned, revived=revived)


def make_planner(*, tenant: str, dry_run: bool, force: bool, threshold: float,
                 expected_plan_hash: str | None) -> Planner:
    return Planner(tenant=tenant, dry_run=dry_run, force=force, threshold=threshold,
                   expected_plan_hash=expected_plan_hash)
