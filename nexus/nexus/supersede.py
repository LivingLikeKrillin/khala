"""문서 supersession 선언 프리미티브(명시적·멱등, 자동감지 없음). 스펙 §5.3."""

from __future__ import annotations

from nexus import db


async def supersede(old_rid: str, new_rid: str, tenant: str) -> str:
    """old 를 new 로 대체. 반환: 'superseded' | 'noop'. 위반 시 ValueError.

    결정규칙(순서 고정): 자기참조 → new 검증 → old 존재 → old 상태.
    """
    if old_rid == new_rid:
        raise ValueError("self-supersession not allowed")

    new_row = await db.fetch_one(
        "SELECT status FROM documents WHERE rid = $1 AND tenant = $2", new_rid, tenant)
    if new_row is None or new_row["status"] != "active":
        raise ValueError(f"new_rid not found or not active: {new_rid}")

    old_row = await db.fetch_one(
        "SELECT status FROM documents WHERE rid = $1 AND tenant = $2", old_rid, tenant)
    if old_row is None:
        raise ValueError(f"old_rid not found: {old_rid}")
    if old_row["status"] != "active":
        return "noop"  # superseded(정리 완료) 또는 soft_deleted(범위 밖) — 적용 안 함

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE documents SET status='superseded', superseded_by=$1, updated_at=now() "
                "WHERE rid=$2 AND tenant=$3 AND status='active'", new_rid, old_rid, tenant)
            await conn.execute(
                "UPDATE chunks SET status='superseded', updated_at=now() WHERE doc_rid=$1", old_rid)
    return "superseded"
