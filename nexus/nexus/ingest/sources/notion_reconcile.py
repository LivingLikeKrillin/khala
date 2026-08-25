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


def notion_doc_uri(tenant: str, page_id: str) -> str:
    """page_id → 적재된 문서의 canonical uri.

    rid 를 만드는 것과 **같은 문자열**이다. 그림 추출 행이 이고 갈 `source_uri` 도 이것이어야
    문서와 조인된다 (SPEC-nexus-vision-source-ref §2.1) — 두 곳에서 따로 조립하면 조용히 갈린다.
    """
    return _URI_TEMPLATE.format(tenant=tenant, page_id=page_id)


def notion_doc_rid(tenant: str, page_id: str) -> str:
    """page_id → 적재된 문서의 rid. sink 의 매핑을 그대로 재현한다."""
    return doc_rid(notion_doc_uri(tenant, page_id))


@dataclass
class ScopeRow:
    """재조정 범위에 든 문서 한 건 (prov_inputs ⊆ walked_roots 인 것만).

    content_hash·title 은 계획 지문(plan_hash)과 사람이 읽을 미리보기에 쓴다.
    """

    rid: str
    status: str
    content_hash: str = ""
    title: str = ""


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

    **hold=true 인 문서는 제외한다.** 사람이 손으로 숨긴 문서이므로 재조정의 관할이 아니다.
    빼지 않으면, 페이지가 여전히 live 라는 이유로 다음 동기화가 그 문서를 조용히 되살린다
    (SPEC-nexus-document-lifecycle §4.1).
    """
    rows = await db.fetch_all(
        """
        SELECT rid, status::text AS status, content_hash, title
        FROM documents
        WHERE tenant = $1
          AND source_uri LIKE $2
          AND prov_inputs <> '{}'
          AND prov_inputs <@ $3::text[]
          AND hold = false
        ORDER BY rid
        """,
        tenant, notion_uri_pattern(tenant), sorted(walked_roots),
    )
    return [
        ScopeRow(rid=r["rid"], status=r["status"],
                 content_hash=r["content_hash"], title=r["title"])
        for r in rows
    ]


@dataclass
class ReconcileOutcome:
    """실제로 적용된 결과(계획이 아니라). dry_run/refused 면 0 이다."""

    pruned: int = 0
    revived: int = 0
    refused: bool = False
    reason: str = ""


async def write_source_roots(
    rid: str, tenant: str, reached: list[str], walked: list[str]
) -> None:
    """documents.prov_inputs 를 갱신한다 — **이번에 걸은 root 에 대해서만** (SPEC §3.1).

        prov_inputs := (기존 − walked) ∪ reached

    통째로 덮어쓰면(replace) rootA 만 걷는 실행이 "이 페이지는 rootB 에도 걸려 있다"는 기록을
    지워버린다. 그러면 다음 실행에서 `prov_inputs <@ {rootA}` 가 성립해, rootB 밑에 멀쩡히
    살아있는 페이지가 prune 된다. 반대로 무조건 append 하면 더 이상 닿지 않는 root 가 영원히
    남아 그 문서는 절대 prune 되지 않는다. 걸은 root 만 갱신하는 것이 유일하게 옳다.

    quarantined 행에는 절대 쓰지 않는다(sink 의 label/doc_type 가드와 동일 규칙).
    멱등 히트에도 호출되어야 백필이 성립한다.
    """
    walked_set = set(walked)
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT prov_inputs, is_quarantined FROM documents "
                "WHERE rid = $1 AND tenant = $2 FOR UPDATE",
                rid, tenant,
            )
            if row is None or row["is_quarantined"]:
                return
            kept = [r for r in (row["prov_inputs"] or []) if r not in walked_set]
            merged = sorted(set(kept) | set(reached))
            await conn.execute(
                "UPDATE documents SET prov_inputs = $3 WHERE rid = $1 AND tenant = $2",
                rid, tenant, merged,
            )


async def backfill_source_roots(tenant: str, walked_roots: set[str], live_by_rid: dict[str, list[str]]) -> None:
    """살아있는 **모든** 페이지의 root 귀속을 갱신한다 (SPEC-nexus-notion-source-console §4.5).

    예전에는 적재 sink 만 prov_inputs 를 썼다. `--since` 는 변경 없는 페이지의 적재를 건너뛰므로
    그 페이지들은 영영 귀속을 못 얻었고, 재조정이 조용히 아무 일도 하지 않았다. 런북은 그걸
    경고로 적었다 — 경고는 수정이 아니다.

    열거(live_index)는 since 와 무관하게 전체를 걷는다. 그러니 여기서 직접 쓴다.
    dry-run 에서도 쓴다: 낡은 귀속 위에서 계산한 미리보기는 거짓말이다. 문서의 **상태**는
    건드리지 않으므로 "dry-run 은 아무것도 적용하지 않는다"는 여전히 참이다.
    """
    for rid, reached in live_by_rid.items():
        await write_source_roots(rid, tenant, reached=reached, walked=sorted(walked_roots))


def make_reconcile_fn(
    threshold: float = 0.5, force: bool = False, dry_run: bool = False
):
    """import_notion 에 주입할 프로덕션 reconcile_fn 을 만든다(합성 루트는 CLI)."""

    async def _reconcile(
        tenant: str, walked_roots: set[str], live_by_rid: dict[str, list[str]]
    ) -> ReconcileOutcome:
        if not dry_run:
            # `backfill_source_roots` 는 **쓴다**(prov_inputs 갱신). dry-run 이 DB 를 건드리지
            # 않는다고 적혀 있으므로 여기도 지난다.
            await backfill_source_roots(tenant, walked_roots, live_by_rid)
        live_rids = set(live_by_rid)
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
