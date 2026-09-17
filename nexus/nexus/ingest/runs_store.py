"""적재 실행 기록 — **돌았다는 사실 자체**를 남긴다 (migration 042).

⛔ **왜 별도의 표인가.** 기존 신호는 전부 *변경*을 기록한다. 코퍼스가 안 바뀐 주에는
아무것도 안 남고, 그래서 **잡이 죽은 것**과 **바뀐 게 없는 것**이 같은 모양이 된다.
여기서는 실행 한 건당 한 행이고, `counts` 가 0 이어도 행은 앉는다.

⚠ **쓰기는 best-effort 다.** 이 표에 못 써도 적재는 계속한다 — 기록하려고 적재를 죽이면
기록이 적재를 망가뜨린 것이다. 대신 조용히 죽지는 않는다: 실패를 로그에 남기고,
`nexus persistence-health` 가 *"마지막 실행이 언제였나"* 를 사람 앞에 낸다. 그 표가
갑자기 조용해지면 그것이 이 모듈이 죽었다는 신호다 (`health/persistence.py` 가 만들어진
이유가 바로 그 사고다).
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import structlog

from nexus import db

logger = structlog.get_logger(__name__)


async def start(tenant: str, source: str) -> str | None:
    """`running` 행을 앉히고 run_id 를 준다. 못 쓰면 ``None`` — 호출자는 그냥 계속한다."""
    run_id = uuid.uuid4().hex
    try:
        await db.execute(
            "INSERT INTO ingest_runs (run_id, tenant, source) VALUES ($1, $2, $3)",
            run_id, tenant, source,
        )
    except Exception as e:                        # noqa: BLE001 — 적재를 죽이지 않는다
        logger.warning("ingest_run_start_unrecorded", tenant=tenant, error=str(e))
        return None
    return run_id


async def finish(
    run_id: str | None,
    *,
    status: str,
    counts: dict[str, Any] | None = None,
    reason: str = "",
) -> None:
    """실행을 닫는다. ``run_id`` 가 ``None`` 이면(시작을 못 남겼으면) 아무것도 안 한다."""
    if run_id is None:
        return
    try:
        await db.execute(
            "UPDATE ingest_runs SET status = $2::sync_status, finished_at = now(), "
            "counts = $3::jsonb, reason = $4 WHERE run_id = $1",
            run_id, status, json.dumps(counts or {}), reason[:500],
        )
    except Exception as e:                        # noqa: BLE001
        logger.warning("ingest_run_finish_unrecorded", run_id=run_id, error=str(e))


def summarize(result: Any) -> dict[str, int]:
    """`IngestResult` 에서 남길 수들.

    ⛔ **`found` 와 `changed` 와 `unchanged` 를 다 남긴다.** 하나로 덮으면 *"못 봤다"* 와
    *"안 바뀌었다"* 가 같은 수가 되고, 이 리포는 2026-08-28 에 그 줄 하나로 없는 결함을
    보고한 적이 있다. 주기 잡에서는 `unchanged` 가 보통값이라 더 중요하다 — 그 수가
    갑자기 0 이 되면 원본이 안 보이는 것이다.
    """
    return {
        "found": result.found_files,
        "changed": result.total_files,
        "unchanged": result.unchanged_files,
        "indexed": result.indexed,
        "bm25": result.bm25_indexed,
        "vector": result.vector_indexed,
        "quarantined": result.quarantined,
        "refused_vendor": result.refused_vendor,
        "failed": result.failed,
    }
