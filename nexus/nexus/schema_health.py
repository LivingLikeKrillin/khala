"""스키마가 코드보다 낡았는가 — 그리고 그 사실이 **보이는가**.

2026-08-13 에 이 배포는 마이그레이션 018 이 빠진 채로 돌고 있었다. 증상은 하나뿐이었다:
`query_retention.py` 가 없는 컬럼을 SELECT 하고, 그 예외는 설계대로 삼켜지고
(*"동의 범위의 곁가지 기록이 답변을 못 내리게 하면 안 된다"*), 아무도 안 읽는 로그에 경고 한 줄이
남았다. 그동안 **질문 보존은 조용히 죽어 있었다** — 파일럿에서 가장 값진 산출물인 실사용
질문이 한 건도 쌓이지 않았을 것이다.

`task up` 은 마이그레이션을 돌린다. 문제는 그것을 **안 거치고도 앱이 멀쩡히 뜬다**는 것이다.
`docker compose up -d nexus-app` 한 번이면 낡은 스키마 위에서 하루가 간다.

**부팅을 거부하지 않는다.** 스키마 드리프트를 장애로 바꾸면, 컬럼 하나 빠진 배포가 답을 아예
못 내게 된다 — 인덱스 커버리지에서 같은 판단을 했다(감지기는 있었고 실패한 것은 전달이었다).
그래서 하는 일은 **크게 말하는 것**이다: 기동 로그에 error, 그리고 `/status` 에 목록.
"""

from __future__ import annotations

from pathlib import Path

import structlog

from nexus import db

logger = structlog.get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


async def pending() -> list[str]:
    """아직 적용되지 않은 마이그레이션 파일명. 알 수 없으면 빈 목록.

    판정 규칙은 **마이그레이션 러너의 것을 그대로 쓴다**(`scripts.migrate.pending_migrations`).
    여기서 다시 구현하면 두 판정이 갈라지고, 갈라진 순간 이 진단은 거짓말을 시작한다.
    """
    try:
        from scripts.migrate import pending_migrations

        files = list(MIGRATIONS_DIR.glob("*.sql"))
        rows = await db.fetch_all("SELECT version FROM schema_migrations")
        applied = {r["version"] for r in rows}
        return [p.name for p in pending_migrations(files, applied)]
    except Exception as e:  # noqa: BLE001 — 진단이 부팅이나 /status 를 죽일 수 없다
        # 테이블 자체가 없는 배포(마이그레이션을 한 번도 안 돌린 곳)도 여기로 온다.
        logger.warning("schema_health_unavailable", error=str(e)[:200])
        return []


async def log_pending() -> None:
    """기동 시 한 번. 밀린 것이 있으면 **error 로** 남긴다 — warning 은 묻힌다."""
    names = await pending()
    if not names:
        return
    logger.error(
        "pending_migrations",
        count=len(names),
        versions=names,
        fix="task up (또는 docker compose exec -T nexus-app python -m scripts.migrate)",
        note="낡은 스키마 위에서도 앱은 뜬다. 018 이 빠졌을 때 질문 보존이 조용히 죽어 있었다.",
    )
