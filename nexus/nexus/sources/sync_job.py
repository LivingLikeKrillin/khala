"""동기화 백그라운드 잡 (SPEC-nexus-notion-source-console §4.2 · §4.4).

앱 프로세스의 asyncio 태스크다. 잡 러너를 새로 들이지 않는다(단일 프로세스 전제, §4.2).

tenant advisory lock 을 **전용 커넥션**으로 잡고 도는 동안 유지한다. 프로세스가 죽으면
커넥션이 끊기며 lock 이 풀리고, 부팅 시 스윕(runs_store.sweep_orphaned_runs)이 그 행을
interrupted 로 정리한다 — lock 을 잡을 수 있는 행만.

Notion 소스 생성은 주입 가능하다(`source_factory`). 테스트가 실제 Notion 을 치지 않는다.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from nexus import db
from nexus.sources import runs_store
from nexus.sources.plan_hash import compute_plan_hash

logger = logging.getLogger(__name__)

#: (roots, tenant) -> DocumentSource. 프로덕션은 NotionSource.
SourceFactory = Callable[[list[str], str], Any]

_tasks: set[asyncio.Task] = set()


def _default_source_factory(roots: list[str], tenant: str):
    from nexus.ingest.sources.notion import NotionSource

    return NotionSource(roots=roots, tenant=tenant)


def spawn_sync(*, run_id: str, tenant: str, roots: list[str], reconcile: bool, dry_run: bool,
               force: bool, since: str, threshold: float = 0.5, confirm_run: str | None = None,
               source_factory: SourceFactory | None = None) -> asyncio.Task:
    """즉시 반환한다. 진행 상황은 notion_sync_runs 에 쓰인다."""
    task = asyncio.create_task(
        _run_sync(run_id=run_id, tenant=tenant, roots=roots, reconcile=reconcile,
                  dry_run=dry_run, force=force, since=since, threshold=threshold,
                  confirm_run=confirm_run,
                  source_factory=source_factory or _default_source_factory)
    )
    _tasks.add(task)                      # 태스크가 GC 되어 조용히 사라지지 않도록 강참조 유지
    task.add_done_callback(_tasks.discard)
    return task


async def _run_sync(*, run_id: str, tenant: str, roots: list[str], reconcile: bool, dry_run: bool,
                    force: bool, since: str, threshold: float, confirm_run: str | None,
                    source_factory: SourceFactory) -> None:
    pool = await db.get_pool()
    lock_conn = await pool.acquire()
    try:
        got = await lock_conn.fetchval(
            "SELECT pg_try_advisory_lock(hashtext($1)::bigint)", runs_store.advisory_key(tenant)
        )
        if not got:
            await runs_store.finish_run(run_id, status="failed", reason="lock_unavailable")
            return

        try:
            await _walk_and_apply(
                run_id=run_id, tenant=tenant, roots=roots, reconcile=reconcile, dry_run=dry_run,
                force=force, since=since, threshold=threshold, confirm_run=confirm_run,
                source_factory=source_factory,
            )
        except Exception as e:  # noqa: BLE001 — 어떤 실패든 run 에 기록하고 죽는다(조용한 실패 금지)
            logger.exception("notion sync failed", extra={"run_id": run_id})
            await runs_store.finish_run(run_id, status="failed", reason=str(e)[:500])
        finally:
            await lock_conn.execute(
                "SELECT pg_advisory_unlock(hashtext($1)::bigint)", runs_store.advisory_key(tenant)
            )
    finally:
        await pool.release(lock_conn)


async def _walk_and_apply(*, run_id: str, tenant: str, roots: list[str], reconcile: bool,
                          dry_run: bool, force: bool, since: str, threshold: float,
                          confirm_run: str | None, source_factory: SourceFactory) -> None:
    from nexus.a2a.server import _default_external_ingest_fn
    from nexus.ingest.sources.notion_importer import import_notion

    from .reconcile_planner import make_planner

    source = source_factory(roots, tenant)

    expected_hash = None
    if confirm_run is not None:
        prior = await runs_store.get_run(confirm_run)
        expected_hash = prior["plan_hash"]      # 확정: 미리보기 당시의 지문과 대조한다
        dry_run = False

    planner = make_planner(
        tenant=tenant, dry_run=dry_run, force=force, threshold=threshold,
        expected_plan_hash=expected_hash,
    )

    report = await import_notion(
        source, tenant, _default_external_ingest_fn,
        since=since or None,
        reconcile_fn=planner.reconcile_fn if reconcile else None,
    )

    counts = {
        "ingested": report.ingested, "idempotent": report.idempotent,
        "empty": report.empty, "skipped": report.skipped,
        "pruned": report.pruned, "revived": report.revived,
    }
    plan = planner.plan_payload
    plan_hash = (
        compute_plan_hash(planner.walked_roots, planner.prune_entries, planner.revive_entries)
        if reconcile else ""
    )

    if planner.stale:
        await runs_store.finish_run(run_id, status="failed", counts=counts, reason="plan_stale")
        return
    if report.refused:
        await runs_store.finish_run(
            run_id, status="refused", counts=counts, plan=plan, plan_hash=plan_hash,
            reason=report.reason, walked_roots=planner.walked_roots,
        )
        return

    await runs_store.finish_run(
        run_id, status="succeeded", counts=counts, plan=plan, plan_hash=plan_hash,
        walked_roots=planner.walked_roots,
    )
