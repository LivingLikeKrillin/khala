"""Notion 재조정(reconciliation)의 순수 로직 — DB/네트워크 의존 없음.

SPEC-nexus-notion-reconciliation §3.2·§3.3·§3.5.

여기서 결정하고, DB 반영은 nexus.lifecycle 의 프리미티브가 한다("System decides").
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from nexus import db
from nexus.rid import doc_rid

# sink(_default_external_ingest_fn)가 만드는 canonical uri 와 반드시 일치해야 한다:
#   CSF id 'ext-notion-{page_id}' → 파일명 '{id}.md' → canonical uri '{tenant}:{파일명}'
_URI_TEMPLATE = "{tenant}:ext-notion-{page_id}.md"

#: scope 조회용 LIKE 패턴 (tenant 접두 + ext-notion- 접두)
def notion_uri_pattern(tenant: str) -> str:
    return f"{tenant}:ext-notion-%"


def notion_doc_rid(tenant: str, page_id: str) -> str:
    """page_id → 적재된 문서의 rid. sink 의 매핑을 그대로 재현한다."""
    return doc_rid(_URI_TEMPLATE.format(tenant=tenant, page_id=page_id))


@dataclass
class ScopeRow:
    """재조정 범위에 든 문서 한 건 (prov_inputs ⊆ walked_roots 인 것만)."""

    rid: str
    status: str


@dataclass
class ReconcilePlan:
    prune: list[str] = field(default_factory=list)
    revive: list[str] = field(default_factory=list)
    refused: bool = False
    reason: str = ""


async def fetch_notion_scope(tenant: str, walked_roots: set[str]) -> list[ScopeRow]:
    """이번 실행이 **책임질 수 있는** Notion 문서들만 고른다 (SPEC §3.2).

    containment: `prov_inputs <@ walked_roots` — 문서의 출처 root 가 전부 이번에 걸린
    경우에만 판정 대상이다. rootA·rootB 양쪽에서 닿는 페이지를 rootA 만 걷고 지우는 사고를
    막는다. prov_inputs 가 비어 있는 행(백필 전 레거시)은 영원히 후보에서 제외된다.

    soft_deleted·superseded 도 함께 반환한다 — revive 후보 판정은 plan_reconcile 의 몫이다.
    """
    rows = await db.fetch_all(
        """
        SELECT rid, status::text AS status
        FROM documents
        WHERE tenant = $1
          AND source_uri LIKE $2
          AND prov_inputs <> '{}'
          AND prov_inputs <@ $3::text[]
        ORDER BY rid
        """,
        tenant, notion_uri_pattern(tenant), sorted(walked_roots),
    )
    return [ScopeRow(rid=r["rid"], status=r["status"]) for r in rows]


@dataclass
class ReconcileOutcome:
    """실제로 적용된 결과(계획이 아니라). dry_run/refused 면 0 이다."""

    pruned: int = 0
    revived: int = 0
    refused: bool = False
    reason: str = ""


async def write_source_roots(rid: str, tenant: str, roots: list[str]) -> None:
    """documents.prov_inputs 를 walked roots 로 **갈아끼운다**(append 아님 — SPEC §3.1).

    quarantined 행에는 절대 쓰지 않는다(sink 의 label/doc_type 가드와 동일 규칙).
    멱등 히트에도 호출되어야 백필이 성립한다.
    """
    await db.execute(
        "UPDATE documents SET prov_inputs = $3 "
        "WHERE rid = $1 AND tenant = $2 AND is_quarantined = false",
        rid, tenant, roots,
    )


def make_reconcile_fn(
    threshold: float = 0.5, force: bool = False, dry_run: bool = False
):
    """import_notion 에 주입할 프로덕션 reconcile_fn 을 만든다(합성 루트는 CLI)."""

    async def _reconcile(tenant: str, walked_roots: set[str], live_rids: set[str]) -> ReconcileOutcome:
        scope = await fetch_notion_scope(tenant, walked_roots)
        plan = plan_reconcile(scope, live_rids, threshold=threshold, force=force)

        if plan.refused:
            return ReconcileOutcome(refused=True, reason=plan.reason)
        if dry_run:
            # 계획만 보고한다 — DB 는 건드리지 않는다.
            return ReconcileOutcome(pruned=len(plan.prune), revived=len(plan.revive),
                                    reason="dry-run: 적용하지 않음")

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

    return _reconcile


def plan_reconcile(
    scope: Iterable[ScopeRow],
    live_rids: set[str],
    threshold: float = 0.5,
    force: bool = False,
) -> ReconcilePlan:
    """scope 와 live 집합의 차이를 prune/revive 로 가른다.

    · prune  = active 인데 live 에 없음        → soft_delete 대상
    · revive = soft_deleted 인데 live 에 있음  → 되살림 대상
    · superseded 는 어느 쪽에도 들지 않는다(의도적 대체는 재조정의 관할이 아니다).

    prune 비율이 threshold 를 **초과**하면 refused=True (계획은 보고하되 적용 금지).
    --roots 오타/축소 실행이 코퍼스를 통째로 지우는 사고를 막는 마지막 방어선이다.
    """
    rows = list(scope)
    active = [r for r in rows if r.status == "active"]
    prune = [r.rid for r in active if r.rid not in live_rids]
    revive = [r.rid for r in rows if r.status == "soft_deleted" and r.rid in live_rids]

    plan = ReconcilePlan(prune=prune, revive=revive)

    # scope 가 비면 비율은 정의되지 않는다 — 0/0 을 100% 로 읽어 거부하면 안 된다.
    if active and not force:
        ratio = len(prune) / len(active)
        if ratio > threshold:
            plan.refused = True
            plan.reason = (
                f"prune 비율 {ratio:.0%} ({len(prune)}/{len(active)}) 가 임계치 "
                f"{threshold:.0%} 를 초과합니다. --roots 를 확인하세요. "
                f"의도한 것이면 --force 를 주십시오."
            )
    return plan
