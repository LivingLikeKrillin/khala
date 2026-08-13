"""만료된 질문 텍스트를 **스스로** 지운다 (SPEC-nexus-query-text-retention §3.3).

`purge` 는 있었지만 아무도 안 불렀다. 그리고 **안 도는 purge 는 증상이 없다** — 보관 중이라는
사실도, 만료를 넘겼다는 사실도 아무 데도 안 나타난다. 공지에 "90일" 이라고 적는 순간 그것은
지켜야 하는 약속이 되는데, 그 약속이 사람의 기억에 걸려 있었다.

**왜 cron 컨테이너가 아닌가.** 이 배포는 사람 PC 위의 로컬 도커다. 정해진 시각에 도는 cron 은
그 시각에 PC 가 꺼져 있으면 그냥 건너뛰고, 다음 날 같은 시각까지 아무 일도 없다. 대신 여기서는
**기동할 때 한 번 + 도는 동안 주기적으로** 돈다 — "PC 가 켜지면 정리된다" 가 이 환경에서
지킬 수 있는 약속이다.

**중복 실행은 advisory lock 으로 막는다**(`nexus/sources/sync_job.py` 와 같은 관례). 인스턴스가
둘이어도 한 번만 돌고, 못 잡은 쪽은 조용히 넘어간다 — 다음 주기가 있다.
"""

from __future__ import annotations

import asyncio
import os

import structlog

from nexus import db

logger = structlog.get_logger(__name__)

#: 주기(시간). `0` 이면 스케줄러를 아예 켜지 않는다 — 끄는 방법이 없는 자동화는 사고다.
DEFAULT_INTERVAL_HOURS = 24.0

#: 기동 직후 곧바로 돌지 않고 이만큼 기다린다. 부팅 경로에 DB 삭제를 얹으면 기동이 느려지고,
#: 무엇보다 마이그레이션이 아직 안 끝난 배포에서 첫 질의를 이 작업이 밀어낸다.
STARTUP_DELAY_S = 30.0

_LOCK_KEY = "nexus:query_retention:purge"


def interval_hours() -> float:
    """`NEXUS_RETENTION_PURGE_HOURS`. 잘못된 값이면 기본값으로 — 오타가 자동화를 끄면 안 된다."""
    raw = os.getenv("NEXUS_RETENTION_PURGE_HOURS")
    if raw is None or raw.strip() == "":
        return DEFAULT_INTERVAL_HOURS
    try:
        value = float(raw)
    except ValueError:
        logger.warning("purge_interval_invalid", value=raw, using=DEFAULT_INTERVAL_HOURS)
        return DEFAULT_INTERVAL_HOURS
    return max(0.0, value)


async def run_once() -> dict[str, int]:
    """한 번 돈다. 락을 못 잡으면 `{}` — 다른 인스턴스가 돌고 있다는 뜻이다.

    **어떤 실패에서도 raise 하지 않는다.** 정리 작업이 서버를 죽이면 그것은 정리가 아니다.
    """
    try:
        pool = await db.get_pool()
        async with pool.acquire() as con:
            got = await con.fetchval(
                "SELECT pg_try_advisory_lock(hashtext($1)::bigint)", _LOCK_KEY)
            if not got:
                logger.info("purge_skipped_locked")
                return {}
            try:
                from nexus.search.query_retention import purge

                deleted = await purge()
                # 지운 게 없으면 조용히 — 상시 로그는 진짜 신호를 묻는다.
                if deleted:
                    logger.info("purge_ran", deleted=deleted)
                return deleted
            finally:
                await con.execute(
                    "SELECT pg_advisory_unlock(hashtext($1)::bigint)", _LOCK_KEY)
    except Exception as e:  # noqa: BLE001
        logger.warning("purge_failed", error=str(e)[:200])
        return {}


async def loop(interval_s: float, *, startup_delay_s: float = STARTUP_DELAY_S) -> None:
    """기동 후 한 번, 그 뒤 주기적으로. 취소될 때까지."""
    try:
        await asyncio.sleep(startup_delay_s)
        while True:
            await run_once()
            await asyncio.sleep(interval_s)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 — 루프가 죽으면 약속도 같이 죽는다
        logger.error("purge_loop_died", error=str(e)[:200])


def start(*, startup_delay_s: float = STARTUP_DELAY_S) -> asyncio.Task | None:
    """스케줄러를 켠다. 꺼져 있으면(`0`) `None`.

    호출자는 반환된 task 의 참조를 들고 있어야 한다 — 안 그러면 GC 가 가져간다.
    """
    hours = interval_hours()
    if hours <= 0:
        logger.info("purge_scheduler_off", reason="NEXUS_RETENTION_PURGE_HOURS=0")
        return None
    logger.info("purge_scheduler_on", interval_hours=hours)
    return asyncio.create_task(loop(hours * 3600.0, startup_delay_s=startup_delay_s))
