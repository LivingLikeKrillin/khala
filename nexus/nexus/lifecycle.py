"""문서 생애주기 프리미티브 — soft_delete / revive (명시적·멱등·자동감지 없음).

`supersede()`(supersede.py)가 "A 를 B 가 대체한다"를 다룬다면, 여기는 대체 문서가 없는
소멸/부활을 다룬다. 정본에서 사라진 페이지에는 후속 문서가 없으므로 supersede 로 표현할 수 없다.

SPEC-nexus-notion-reconciliation §3.4.

두 함수 모두 **상태 가드**를 건다:
  · soft_delete 는 active 에서만 출발한다 → superseded 문서를 뒤엎지 않는다.
  · revive 는 soft_deleted 에서만 출발한다 → 의도적으로 대체된 문서를 되살리지 않는다.
"""

from __future__ import annotations

from nexus import db


async def soft_delete(rid: str, tenant: str) -> str:
    """문서를 검색에서 내린다. 반환: 'soft_deleted' | 'noop'.

    청크는 **active 인 것만** 함께 내린다. 이미 superseded 인 낡은 세대는 그대로 둔다
    (되살릴 때 죽은 텍스트가 함께 돌아오지 않도록).
    """
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            updated = await conn.execute(
                "UPDATE documents SET status='soft_deleted', updated_at=now() "
                "WHERE rid=$1 AND tenant=$2 AND status='active'",
                rid, tenant,
            )
            if updated == "UPDATE 0":
                return "noop"
            await conn.execute(
                "UPDATE chunks SET status='soft_deleted', updated_at=now() "
                "WHERE doc_rid=$1 AND status='active'",
                rid,
            )
    return "soft_deleted"


async def revive(rid: str, tenant: str) -> str:
    """soft_deleted 문서를 되살린다. 반환: 'revived' | 'noop'.

    청크는 **현재 세대만** 되살린다. 세대 식별자는 `chunks.hash` = `documents.content_hash`
    (pipeline.py 가 같은 값으로 둘 다 쓴다). 낡은 세대는 superseded 인 채로 남는다.
    """
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            updated = await conn.execute(
                "UPDATE documents SET status='active', updated_at=now() "
                "WHERE rid=$1 AND tenant=$2 AND status='soft_deleted'",
                rid, tenant,
            )
            if updated == "UPDATE 0":
                return "noop"
            await conn.execute(
                "UPDATE chunks SET status='active', updated_at=now() "
                "WHERE doc_rid=$1 AND status <> 'active' "
                "  AND hash = (SELECT content_hash FROM documents WHERE rid=$1)",
                rid,
            )
    return "revived"
