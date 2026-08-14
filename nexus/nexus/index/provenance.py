"""벡터 출처를 **컬럼별로** 적는다 (SPEC-nexus-embedding-provenance-grain U1, approved).

`chunks.embed_model` 은 행당 한 칸인데 벡터는 컬럼 둘에 산다. 쓰기 경로가 `{col}` 은 바꾸면서
라벨은 같은 칸에 쓰므로 **라벨은 마지막에 쓴 컬럼의 것**이고 다른 컬럼에 대해서는 거짓이다.
2026-08-14 실측(정책 필터): `default` 309행 중 111행이 768 모델 라벨을 단 채 1024 벡터를 갖고
있었다 — nomic 은 1024 를 만들 수 없다.

**미상(`model IS NULL`)은 위반이 아니다.** 마이그레이션이 남긴 기존 벡터가 전부 미상이고,
모르는 것을 혼합으로 세면 경보가 상시화된다 — 그러면 아무도 안 본다. 이 리포는 이미 그렇게
데였다(진짜 `pending=51` 한 줄이 상시 거짓 경보 739줄에 묻혔다).
"""

from __future__ import annotations

import structlog

from nexus import db

log = structlog.get_logger(__name__)


async def record(*, chunk_rid: str, column_name: str, model: str) -> None:
    """이 (청크, 컬럼) 의 벡터를 이 모델이 썼다. **다른 컬럼의 출처는 건드리지 않는다.**

    쓰기 경로에서 불린다. **실패해도 예외를 올리지 않는다** — 출처 기록이 적재를 죽이면
    안 되고, 실패한 자리는 미상으로 남아 §3.3 의 그 칸에 합류한다. 다만 조용히 넘기지 않고
    센다: 미상이 **왜** 미상인지(옛 행 vs 쓰기 실패) 구별할 수 있어야 한다.
    """
    try:
        await db.execute(
            """
            INSERT INTO chunk_vector_provenance (chunk_rid, column_name, model, written_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (chunk_rid, column_name)
            DO UPDATE SET model = EXCLUDED.model, written_at = EXCLUDED.written_at
            """,
            chunk_rid, column_name, model)
    except Exception as exc:  # noqa: BLE001 — 출처 기록이 적재를 죽이면 안 된다
        counters["write_failed"] += 1
        log.warning("provenance_write_failed", column=column_name, error=str(exc)[:200])


#: 미상이 **왜** 미상인가. 옛 행(마이그레이션)과 쓰기 실패는 표에서 똑같이 NULL 로 보인다 —
#: 이 카운터가 그 둘을 가르는 유일한 신호다.
counters: dict[str, int] = {"write_failed": 0}


async def for_chunk(chunk_rid: str) -> dict[str, str | None]:
    """{컬럼: 모델}. 검사와 진단용."""
    rows = await db.fetch_all(
        "SELECT column_name, model FROM chunk_vector_provenance WHERE chunk_rid = $1", chunk_rid)
    return {r["column_name"]: r["model"] for r in rows}


async def fetch_distribution(column_name: str) -> list[tuple[str | None, int]]:
    """그 컬럼의 (모델, 개수) 분포. **미상도 한 줄로 나온다** — 숨기면 안 보인다."""
    rows = await db.fetch_all(
        """
        SELECT p.model, count(*) AS n
          FROM chunk_vector_provenance p
          JOIN chunks c ON c.rid = p.chunk_rid
         WHERE p.column_name = $1
           AND c.status = 'active' AND c.is_quarantined = false
         GROUP BY p.model
        """,
        column_name)
    return [(r["model"], r["n"]) for r in rows]


def summarize(distribution: list[tuple[str | None, int]]) -> dict:
    """분포 → 세대 리포트. 순수·결정론.

    **`mixed` 는 아는 모델이 둘 이상일 때다.** 미상은 세지 않는다 — 옛 설계는 행 라벨로
    group by 해서 균일한 컬럼을 혼합이라 불렀고(111행이 거짓 라벨), 그 거짓 경보를 그대로
    미상으로 옮기면 고친 것이 아니다.

    **`unknown` 은 따로 돌려준다.** 숨기면 "모른다" 와 "괜찮다" 가 같아 보인다 — 미상이 많으면
    이 감지기의 감도가 낮다는 사실 자체가 보여야 한다.
    """
    known = sorted(((m, n) for m, n in distribution if m is not None),
                   key=lambda t: (-t[1], t[0]))
    unknown = sum(n for m, n in distribution if m is None)
    return {
        "generations": [{"model": m, "count": n} for m, n in known],
        "mixed": len(known) > 1,
        "dominant": known[0][0] if known else None,
        "unknown": unknown,
    }
