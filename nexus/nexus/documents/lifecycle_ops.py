"""사람이 하는 숨김/되돌리기 (SPEC-nexus-document-lifecycle §4.1).

`hold` 는 "사람이 이 문서는 검색에 있으면 안 된다고 결정했다" 는 표시다. status 와 직교한다.

  hide    : soft_delete + hold=true
  restore : revive + hold=false

**재조정은 hold=true 인 문서를 되살리지 않는다.** 이게 없으면 사람이 손으로 숨긴 Notion 문서를
다음 동기화가 조용히 되살린다 — 그 페이지는 여전히 live 이기 때문이다. 두 기능이 서로 싸운다.

반면 재조정이 내린 문서(prune)는 hold=false 이므로, 페이지가 돌아오면 여전히 되살아난다.
같은 행, 다른 원인, 다른 문장.
"""

from __future__ import annotations

from nexus import db
from nexus.lifecycle import revive, soft_delete


class AlreadySuperseded(Exception):
    """superseded 문서는 이미 검색 밖이다. hold 를 세우면 정의되지 않은 상태가 된다."""


class UseUnsupersede(Exception):
    """superseded 문서를 되살리는 것은 다른 결정이다 — unsupersede 를 쓰라."""


async def _status(rid: str, tenant: str) -> str | None:
    return await db.fetch_val(
        "SELECT status::text FROM documents WHERE rid=$1 AND tenant=$2", rid, tenant)


async def hide_document(rid: str, tenant: str) -> str:
    """검색에서 내리고, 재조정이 되살리지 못하게 붙든다. 반환: 'hidden' | 'noop'."""
    status = await _status(rid, tenant)
    if status is None:
        return "noop"
    if status == "superseded":
        raise AlreadySuperseded(rid)

    result = await soft_delete(rid, tenant)
    # 이미 soft_deleted(=prune 당함)여도 hold 는 세운다: 사람의 결정이 재조정을 이긴다.
    already_held = await db.fetch_val(
        "SELECT hold FROM documents WHERE rid=$1 AND tenant=$2", rid, tenant)
    if result == "noop" and already_held:
        return "noop"
    await db.execute(
        "UPDATE documents SET hold=true, updated_at=now() WHERE rid=$1 AND tenant=$2", rid, tenant)
    return "hidden"


async def restore_document(rid: str, tenant: str) -> str:
    """되살리고 hold 를 푼다. 반환: 'restored' | 'noop'."""
    status = await _status(rid, tenant)
    if status is None:
        return "noop"
    if status == "superseded":
        raise UseUnsupersede(rid)
    if status == "active":
        await db.execute(
            "UPDATE documents SET hold=false WHERE rid=$1 AND tenant=$2", rid, tenant)
        return "noop"

    await revive(rid, tenant)
    await db.execute(
        "UPDATE documents SET hold=false, updated_at=now() WHERE rid=$1 AND tenant=$2", rid, tenant)
    return "restored"
