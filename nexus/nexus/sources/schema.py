"""소스 콘솔 스키마를 세운다 — DDL 의 정본은 migrations/002_notion_sources.sql 하나뿐이다.

프로덕션은 `python -m scripts.migrate` 가 그 파일을 적용한다. 테스트는 여기서 같은 파일을
읽어 적용한다. DDL 을 두 군데 적어두면 반드시 한쪽이 낡는다.
"""

from __future__ import annotations

from pathlib import Path

_MIGRATION = Path(__file__).resolve().parents[2] / "migrations" / "002_notion_sources.sql"


async def ensure_schema(conn) -> None:
    """멱등. 이미 있으면 아무 일도 하지 않는다."""
    await conn.execute(_MIGRATION.read_text(encoding="utf-8"))
