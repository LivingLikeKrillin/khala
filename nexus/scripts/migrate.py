"""경량 순차 DB 마이그레이션 — migrations/*.sql 를 정렬 순서로 적용.

init.sql 은 빈 DB 최초 1회 베이스라인(`/docker-entrypoint-initdb.d`). 이후 스키마 델타는
migrations/NNN_*.sql 로 누적한다. 적용분은 schema_migrations 에 기록되고, 이미 기록된
버전은 건너뛴다(멱등). 각 파일은 자체 트랜잭션. alembic 없이 가볍게(1-사용자 적정).

각 마이그레이션 SQL 은 멱등 DDL(ADD COLUMN IF NOT EXISTS, CREATE ... IF NOT EXISTS)을
권장 — 빈 DB(init.sql 직후)·기존 DB 양쪽에서 안전하도록.

    docker exec nexus-app python -m scripts.migrate            # 적용
    docker exec nexus-app python -m scripts.migrate --status   # 현황만
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from nexus import db

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def migration_version(path: Path) -> str:
    """파일명을 버전 키로 사용(예: 001_add_x.sql)."""
    return path.name


def pending_migrations(all_files: list[Path], applied: set[str]) -> list[Path]:
    """아직 적용되지 않은 마이그레이션을 파일명 정렬 순으로 반환."""
    return [
        f for f in sorted(all_files, key=lambda p: p.name)
        if migration_version(f) not in applied
    ]


async def _ensure_table_and_applied(conn) -> set[str]:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version text PRIMARY KEY,
            applied_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    rows = await conn.fetch("SELECT version FROM schema_migrations")
    return {r["version"] for r in rows}


async def migrate(migrations_dir: Path = MIGRATIONS_DIR, status_only: bool = False) -> int:
    """대기 중 마이그레이션을 적용. 적용한 개수를 반환."""
    files = list(migrations_dir.glob("*.sql")) if migrations_dir.is_dir() else []
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        applied = await _ensure_table_and_applied(conn)
        pend = pending_migrations(files, applied)

        if status_only:
            print(f"applied={len(applied)} pending={len(pend)}")
            for f in pend:
                print("  pending:", f.name)
            return 0

        for f in pend:
            sql = f.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO schema_migrations (version) VALUES ($1)",
                    migration_version(f),
                )
            print("applied:", f.name)
        print(f"up to date — {len(pend)} new applied, {len(applied) + len(pend)} total")
    return len(pend)


if __name__ == "__main__":
    asyncio.run(migrate(status_only="--status" in sys.argv))
