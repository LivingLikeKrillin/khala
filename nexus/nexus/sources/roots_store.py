"""등록된 Notion root 목록 (SPEC-nexus-notion-source-console §4.1).

정본은 DB 다 — 브라우저가 고쳐야 하므로 config.yaml 일 수 없다.
저장 전에 반드시 canonical page id 로 정규화한다.
"""

from __future__ import annotations

import asyncpg

from nexus import db
from nexus.sources.errors import DuplicateRoot
from nexus.sources.notion_sources import parse_notion_ref


DEFAULT_TOKEN_ENV = "NOTION_TOKEN"


async def add_root(tenant: str, url_or_id: str, label: str = "",
                   token_env: str = DEFAULT_TOKEN_ENV) -> str:
    """URL 이든 id 든 받아 canonical id 로 저장한다. 이미 있으면 DuplicateRoot.

    `token_env` 는 이 루트를 읽을 integration 토큰이 담긴 **환경변수 이름**이다. Notion 의
    integration 은 워크스페이스에 속하므로, 다른 조직의 문서를 미러하려면 그쪽 토큰이 따로
    필요하고 기존 것과 동시에 들려야 한다. 시크릿은 여기 저장하지 않는다.
    """
    root_id = parse_notion_ref(url_or_id)
    try:
        await db.execute(
            "INSERT INTO notion_sources (tenant, root_id, label, token_env) "
            "VALUES ($1, $2, $3, $4)",
            tenant, root_id, label, token_env or DEFAULT_TOKEN_ENV,
        )
    except asyncpg.UniqueViolationError as e:
        raise DuplicateRoot(root_id) from e
    return root_id


async def list_roots(tenant: str) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT root_id, label, added_at, token_env FROM notion_sources "
        "WHERE tenant = $1 ORDER BY added_at, root_id",
        tenant,
    )
    return [dict(r) for r in rows]


def group_by_token(roots: list[dict]) -> dict[str, list[str]]:
    """`{token_env: [root_id, ...]}` — 걷기는 토큰 단위로 갈라야 한다.

    한 클라이언트로 두 워크스페이스의 루트를 함께 걸으면, 그 토큰이 못 보는 쪽이 **빈 걸음**으로
    나온다. 그리고 빈 걸음은 `--reconcile` 에서 '사라진 문서' 와 구분되지 않는다.
    """
    out: dict[str, list[str]] = {}
    for r in roots:
        out.setdefault(r.get("token_env") or DEFAULT_TOKEN_ENV, []).append(r["root_id"])
    return out


async def remove_root(tenant: str, root_id: str) -> bool:
    """등록만 해제한다 — 문서는 지우지 않는다. 반환: 실제로 지웠으면 True (멱등)."""
    result = await db.execute(
        "DELETE FROM notion_sources WHERE tenant = $1 AND root_id = $2",
        tenant, parse_notion_ref(root_id),
    )
    return result != "DELETE 0"
