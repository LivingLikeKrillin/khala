"""테스트 DB 가 스스로 '버려도 되는 DB' 라고 선언했는지 확인한다.

스위트는 TRUNCATE 를 한다. 그 대상이 개발/운영 DB 면 코퍼스가 사라지고, 테스트는 초록으로
끝난다 — 실제로 그렇게 한 번 날렸다. 그래서 URL 을 믿지 않는다(포트·DB 이름은 환경마다
다르고, CI 는 5432 를 쓴다). DB 안에 있는 선언만 믿는다.
"""

from __future__ import annotations

MARKER = "_disposable_test_db"


class NotDisposable(Exception):
    """대상 DB 가 버려도 된다고 선언하지 않았다."""


async def assert_disposable(db_url: str) -> None:
    """마커 테이블이 없으면 NotDisposable. 있으면 조용히 통과."""
    import asyncpg

    conn = await asyncpg.connect(db_url)
    try:
        exists = await conn.fetchval(f"SELECT to_regclass('public.{MARKER}')")
        dbname = await conn.fetchval("SELECT current_database()")
    finally:
        await conn.close()

    if exists is None:
        raise NotDisposable(
            f"DB '{dbname}' 는 버려도 되는 테스트 DB 라고 선언하지 않았습니다. "
            f"이 스위트는 테이블을 TRUNCATE 합니다.\n"
            f"  · 테스트 DB 를 띄우려면: docker compose -f docker-compose.test.yml up -d\n"
            f"  · 이미 있는 빈 DB 를 쓰려면: psql -f tests/disposable_db.sql\n"
            f"    (그 파일은 마커 테이블 {MARKER} 하나를 만듭니다)"
        )
