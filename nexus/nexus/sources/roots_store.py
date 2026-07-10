"""등록된 Notion root 목록 (SPEC-nexus-notion-source-console §4.1).

정본은 DB 다 — 브라우저가 고쳐야 하므로 config.yaml 일 수 없다.
저장 전에 반드시 canonical page id 로 정규화한다.
"""

from __future__ import annotations

import asyncpg

from nexus import db
from nexus.sources.errors import DuplicateRoot
from nexus.sources.notion_sources import parse_notion_ref


async def add_root(tenant: str, url_or_id: str, label: str = "") -> str:
    """URL 이든 id 든 받아 canonical id 로 저장한다. 이미 있으면 DuplicateRoot."""
    root_id = parse_notion_ref(url_or_id)
    try:
        await db.execute(
            "INSERT INTO notion_sources (tenant, root_id, label) VALUES ($1, $2, $3)",
            tenant, root_id, label,
        )
    except asyncpg.UniqueViolationError as e:
        raise DuplicateRoot(root_id) from e
    return root_id


async def list_roots(tenant: str) -> list[dict]:
    rows = await db.fetch_all(
        "SELECT root_id, label, added_at FROM notion_sources "
        "WHERE tenant = $1 ORDER BY added_at, root_id",
        tenant,
    )
    return [dict(r) for r in rows]


async def remove_root(tenant: str, root_id: str) -> bool:
    """등록만 해제한다 — 문서는 지우지 않는다. 반환: 실제로 지웠으면 True (멱등)."""
    result = await db.execute(
        "DELETE FROM notion_sources WHERE tenant = $1 AND root_id = $2",
        tenant, parse_notion_ref(root_id),
    )
    return result != "DELETE 0"
