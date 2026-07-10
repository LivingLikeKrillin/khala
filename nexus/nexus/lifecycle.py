"""문서 생애주기 프리미티브 — soft_delete / revive (명시적·멱등·자동감지 없음).

`supersede()`(supersede.py)가 "A 를 B 가 대체한다"를 다룬다면, 여기는 대체 문서가 없는
소멸/부활을 다룬다. 정본에서 사라진 페이지에는 후속 문서가 없으므로 supersede 로 표현할 수 없다.

SPEC-nexus-notion-reconciliation §3.4.

`unsupersede()` 는 supersede 의 역이다 (SPEC-nexus-document-lifecycle §4.2).

모든 함수가 **상태 가드**를 건다:
  · soft_delete 는 active 에서만 출발한다 → superseded 문서를 뒤엎지 않는다.
  · revive 는 soft_deleted 에서만 출발한다 → 의도적으로 대체된 문서를 되살리지 않는다.
  · unsupersede 는 superseded 에서만 출발하고, **체인이 끊기면 거부한다**.
"""

from __future__ import annotations

from nexus import db


class ChainBroken(Exception):
    """이 문서를 대체한 문서가 그 자신도 대체당했다 — 되살리면 최신본과 공존한다."""

    def __init__(self, rid: str, blocker: str):
        super().__init__(
            f"{rid} 를 대체한 {blocker} 가 그 자신도 superseded 입니다. "
            f"{blocker} 를 먼저 unsupersede 하세요 — 체인은 역순으로만 풀립니다."
        )
        self.rid = rid
        self.blocker = blocker


async def _record_supersession_event(conn, rid: str, tenant: str, action: str,
                                     superseded_by: str, reason: str = "") -> None:
    """상태 변경과 **같은 트랜잭션**에서 원장에 남긴다. 롤백되면 기록도 사라진다."""
    await conn.execute(
        "INSERT INTO doc_supersession_events (rid, tenant, action, superseded_by, reason) "
        "VALUES ($1, $2, $3, $4, $5)",
        rid, tenant, action, superseded_by, reason,
    )


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


async def unsupersede(rid: str, tenant: str, *, reason: str) -> str:
    """supersede 를 되돌린다. 반환: 'unsuperseded' | 'noop'.

    되돌리면 문서가 다시 검색에 나타난다 — ADR-0006 이 엔트로피 1순위로 지목한 **공존**을
    만드는 행위다. 그래서:

      · 사유(reason)가 없으면 아무것도 쓰지 않고 ValueError. (실수를 고치는 명령이지
        무심코 누르는 버튼이 아니다.)
      · **체인 가드**: 이 문서를 대체한 문서가 그 자신도 superseded 면 ChainBroken.
        v2→v1, v3→v2 인 상태에서 v1 을 되살리면 v1 이 최신본 v3 와 나란히 검색에 뜬다.
      · 청크는 revive 와 같은 규칙 — 현재 세대(hash = documents.content_hash)만.
      · 원장(doc_supersession_events)에 한 줄, 상태 변경과 같은 트랜잭션에서.

    막지는 않는다. 잘못 대체한 사람은 고칠 수 있어야 한다. 다만 조용하지 않다.
    """
    if not (reason or "").strip():
        raise ValueError("unsupersede 에는 사유가 필요합니다 (reason)")

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT status::text AS status, superseded_by FROM documents "
                "WHERE rid=$1 AND tenant=$2 FOR UPDATE",
                rid, tenant,
            )
            if row is None or row["status"] != "superseded":
                return "noop"

            blocker = row["superseded_by"]
            if blocker:
                blocker_status = await conn.fetchval(
                    "SELECT status::text FROM documents WHERE rid=$1 AND tenant=$2", blocker, tenant
                )
                # 대체한 문서가 살아있지 않으면 되살릴 수 없다 — 최신본과 공존하게 된다.
                if blocker_status is not None and blocker_status != "active":
                    raise ChainBroken(rid, blocker)

            await conn.execute(
                "UPDATE documents SET status='active', superseded_by='', updated_at=now() "
                "WHERE rid=$1 AND tenant=$2 AND status='superseded'",
                rid, tenant,
            )
            await conn.execute(
                "UPDATE chunks SET status='active', updated_at=now() "
                "WHERE doc_rid=$1 AND status <> 'active' "
                "  AND hash = (SELECT content_hash FROM documents WHERE rid=$1)",
                rid,
            )
            await _record_supersession_event(conn, rid, tenant, "unsuperseded", blocker, reason.strip())
    return "unsuperseded"
