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
            # append-only 원장 — 상태 변경과 같은 트랜잭션. 되돌림(unsupersede)만 기록하고
            # 이쪽을 빼면 원장이 반쪽이 된다 (SPEC-nexus-document-lifecycle §4.2).
            from nexus.lifecycle import _record_supersession_event

            await _record_supersession_event(conn, old_rid, tenant, "superseded", new_rid)
    return "superseded"


async def resolve_active_doc(ref: str, tenant: str) -> str:
    """ref(rid | source_uri | basename)를 **active** 문서 rid 로 확정. 위반 시 ValueError. 스펙 §4.1.

    구현은 `nexus.documents.resolve.resolve_doc(active_only=True)` 에 있다. 생애주기 명령들
    (hide/restore/unsupersede)은 상태를 가리지 않는 같은 해석기를 쓴다 — 두 벌의 SQL 이
    갈라지면 '이 경로가 어느 문서냐' 는 답이 명령마다 달라진다.

    주의: rid 패스스루는 status 무관(superseded/soft_deleted 포함) — 하위호환·자동화용.
    코어 supersede() 가 상태를 재검증하므로 안전. 이 패스스루를 'active 만'으로 좁히지 말 것.
    """
    from nexus.documents.resolve import resolve_doc

    return await resolve_doc(ref, tenant, active_only=True)
