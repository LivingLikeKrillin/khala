"""생애주기 스키마를 세운다 — DDL 정본은 migrations/003_document_lifecycle.sql 하나뿐이다.

프로덕션은 `python -m scripts.migrate` 가 적용한다. 테스트는 같은 파일을 읽어 적용한다.
DDL 을 두 군데 적어두면 반드시 한쪽이 낡는다.
"""

from __future__ import annotations

from pathlib import Path

_MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "003_document_lifecycle.sql"


async def ensure_lifecycle_schema(conn) -> None:
    """멱등."""
    await conn.execute(_MIGRATION.read_text(encoding="utf-8"))
