"""동기화 실행 기록 (SPEC-nexus-notion-source-console §4.2).

상태가 DB 에 있으므로 브라우저를 닫아도, 앱을 재시작해도, cron 이 물어봐도 같은 답을 준다.

**tenant 당 running 은 최대 하나.** 두 겹으로 지킨다:
  1. advisory lock — 잡이 도는 동안 전용 커넥션이 쥔다 (sync_job.py).
  2. `uq_notion_sync_running` 부분 유니크 인덱스 — lock 을 우회하는 버그가 생겨도 여기서 막힌다.

크래시 스윕은 **lock 을 잡을 수 있는 행만** 정리한다. lock 이 잡힌다는 것은 그 tenant 에서
아무도 돌고 있지 않다는 뜻이다. 무조건 running 을 failed 로 바꾸면 다른 커넥션/레플리카에서
멀쩡히 도는 잡을 죽인다.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from nexus import db


def advisory_key(tenant: str) -> str:
    return f"notion_sync:{tenant}"


async def create_run(
    tenant: str,
    *,
    reconcile: bool,
    dry_run: bool,
    force: bool = False,
    since: str = "",
    walked_roots: list[str] | None = None,
) -> str:
    """running 행을 만들고 run_id(uuid4 hex)를 돌려준다.

    이미 running 인 run 이 있으면 asyncpg.UniqueViolationError 가 나온다 — 호출자가 잡아
    SyncInProgress 로 옮긴다.
    """
    run_id = uuid.uuid4().hex
    await db.execute(
        "INSERT INTO notion_sync_runs "
        "(run_id, tenant, reconcile, dry_run, force, since, walked_roots) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7)",
        run_id, tenant, reconcile, dry_run, force, since, list(walked_roots or []),
    )
    return run_id


async def finish_run(
    run_id: str,
    *,
    status: str,
    counts: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
    plan_hash: str = "",
    reason: str = "",
    walked_roots: list[str] | None = None,
) -> None:
    await db.execute(
        "UPDATE notion_sync_runs SET status = $2::sync_status, finished_at = now(), "
        "counts = $3::jsonb, plan = $4::jsonb, plan_hash = $5, reason = $6, "
        "walked_roots = COALESCE($7, walked_roots) "
        "WHERE run_id = $1",
        run_id, status, json.dumps(counts or {}), json.dumps(plan or {}),
        plan_hash, reason, list(walked_roots) if walked_roots is not None else None,
    )


async def get_run(run_id: str) -> dict | None:
    row = await db.fetch_one(
        "SELECT run_id, tenant, started_at, finished_at, status::text AS status, dry_run, "
        "reconcile, force, since, walked_roots, counts, plan, plan_hash, reason "
        "FROM notion_sync_runs WHERE run_id = $1",
        run_id,
    )
    return dict(row) if row else None


async def latest_run(tenant: str) -> dict | None:
    row = await db.fetch_one(
        "SELECT run_id, tenant, started_at, finished_at, status::text AS status, dry_run, "
        "reconcile, force, since, walked_roots, counts, plan, plan_hash, reason "
        "FROM notion_sync_runs WHERE tenant = $1 ORDER BY started_at DESC LIMIT 1",
        tenant,
    )
    return dict(row) if row else None


async def running_run_id(tenant: str) -> str | None:
    return await db.fetch_val(
        "SELECT run_id FROM notion_sync_runs WHERE tenant = $1 AND status = 'running'", tenant
    )


async def sweep_orphaned_runs() -> list[str]:
    """부팅 시 1회. 죽은 프로세스가 남긴 running 행만 failed(interrupted) 로 바꾼다.

    판별법: 그 tenant 의 advisory lock 을 **잡아본다**. 잡히면 아무도 안 돌고 있다는 뜻이므로
    고아다. 못 잡으면 살아있는 잡이 쥐고 있는 것이므로 손대지 않는다.
    """
    rows = await db.fetch_all("SELECT run_id, tenant FROM notion_sync_runs WHERE status = 'running'")
    swept: list[str] = []
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        for row in rows:
            got = await conn.fetchval(
                "SELECT pg_try_advisory_lock(hashtext($1)::bigint)", advisory_key(row["tenant"])
            )
            if not got:
                continue  # 살아있는 잡 — 건드리지 않는다
            try:
                await conn.execute(
                    "UPDATE notion_sync_runs SET status = 'failed', finished_at = now(), "
                    "reason = 'interrupted' WHERE run_id = $1 AND status = 'running'",
                    row["run_id"],
                )
                swept.append(row["run_id"])
            finally:
                await conn.execute(
                    "SELECT pg_advisory_unlock(hashtext($1)::bigint)", advisory_key(row["tenant"])
                )
    return swept
