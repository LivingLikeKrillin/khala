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
        # **아는** 모델의 수다. 미상은 세대가 아니라 공백이므로 여기 안 들어간다.
        "distinct": len(known),
        "dominant": known[0][0] if known else None,
        "unknown": unknown,
        # 선언 대조는 테넌트가 있어야 세므로 여기선 자리만 둔다 (`fetch_mismatch`).
        "mismatch": None,
    }


async def fetch_mismatch(column_name: str, *, tenant: str) -> int:
    """선언된 세대와 **다른 모델**로 쓰인 벡터 수 (SPEC §3.2).

    혼합(같은 컬럼에 아는 모델 둘)과 다른 신호다 — 컬럼이 균일해도 그 하나가 선언과 다르면
    검색은 선언되지 않은 공간에서 돌고 있다. 그쪽이 실제로 위험하다.

    **미상은 안 센다.** 모르는 것은 "다르다" 가 아니고, 섞으면 옛 거짓 경보가 이름만 바꿔
    돌아온다. `index_generation_events` 는 append-only 이므로 최신 한 건이 선언이다.
    """
    row = await db.fetch_one(
        """
        WITH declared AS (
            SELECT model FROM index_generation_events
             WHERE tenant = $1 AND column_name = $2
             ORDER BY id DESC LIMIT 1
        )
        SELECT count(*) AS n
          FROM chunk_vector_provenance p
          JOIN chunks c ON c.rid = p.chunk_rid
         WHERE p.column_name = $2 AND c.tenant = $1
           AND c.status = 'active' AND c.is_quarantined = false
           AND p.model IS NOT NULL
           AND p.model IS DISTINCT FROM (SELECT model FROM declared)
           AND EXISTS (SELECT 1 FROM declared)
        """,
        tenant, column_name)
    return int(row["n"]) if row else 0


# ── 시간 축 — 벡터가 그 행보다 나중에 쓰였는가 ────────────────────────────────


async def fetch_freshness(column_name: str, *, tenant: str | None = None) -> dict:
    """`written_at` 을 읽어 **낡을 수 있는 것과 없는 것**을 가른다.

    ⛔ **왜 있나.** 이 리포는 같은 계열의 결함을 두 번 겪었다 — 텍스트가 바뀌었는데 파생 벡터가
    NULL 로 안 돌아갔고, 재임베딩 큐가 `WHERE <컬럼> IS NULL` 이라 **큐에 영영 안 들어갔다.**
    커버리지는 그것을 "채워짐" 으로 세므로 아무 수도 이상해 보이지 않는다. 있는데 틀린 상태를
    보는 방법은 지금까지 **전수 재계산**뿐이었다(`scripts/check_stale_vectors.py`, 손으로 부르는
    수십 분짜리).

    ⭐ **그런데 그 판정에 쓸 도장이 이미 있었다.** `chunk_vector_provenance.written_at` 은
    2026-08-14 부터 쓰이고 있었고 **읽는 코드가 하나도 없었다.** 이 리포가 이미 한 번 적은
    모양이다 — *감지기는 있었고 전달이 없었다.*

    ⭐ **값은 부정 쪽에 있다.** `written_at >= updated_at` 인 행은 마지막 행 갱신 **뒤에** 벡터가
    쓰였으므로 **낡을 수 없다.** 그래서 이 함수의 산출물은 *"낡았다"* 가 아니라
    **"낡을 수 있는 것은 이만큼뿐이다"** 이고, 재계산 범위가 그만큼 줄어든다.

    ⛔ **`candidates` 를 낡은 벡터 수로 읽지 마라.** `updated_at` 은 **내용이 안 바뀐 재적재에도**
    움직이는데 그때는 무효화가 안 걸린다(걸릴 이유가 없다). 즉 이 수는 **상한**이지 개수가
    아니다. 개수를 원하면 그 상한만 재계산하면 된다 — 그것이 이 함수의 용도다.

    ⚠ **`unstamped` 는 셋째 상태다.** 벡터는 있는데 출처 행이 없는 것(025 백필 이전 · 출처 쓰기
    실패)이고, 시간을 모르므로 **신선하다고도 낡았다고도 말할 수 없다.** 숨기면 "모른다" 와
    "괜찮다" 가 같아 보인다 — `summarize` 가 `unknown` 을 따로 내는 것과 같은 이유다.
    """
    # 컬럼명은 화이트리스트를 통과한 것만 SQL 에 닿는다 — 설정값이 문자열로 조립되는 경로가
    # 아니다(`_invalidate_derived` 와 같은 규칙). 그리고 **벡터가 실제로 있는 행만** 센다:
    # NULL 인 행은 재임베딩 큐가 이미 보고 있으므로 이 감지기의 대상이 아니다.
    from nexus.index.vector_index import resolve_column
    col = resolve_column(column_name)
    row = await db.fetch_one(
        f"""
        SELECT
          count(*) AS filled,
          count(*) FILTER (WHERE p.written_at >= c.updated_at) AS provably_fresh,
          count(*) FILTER (WHERE p.written_at <  c.updated_at) AS candidates,
          count(*) FILTER (WHERE p.written_at IS NULL)         AS unstamped
          FROM chunks c
          LEFT JOIN chunk_vector_provenance p
                 ON p.chunk_rid = c.rid AND p.column_name = $1
         WHERE c.status = 'active' AND c.is_quarantined = false
           AND c.{col} IS NOT NULL
           AND ($2::text IS NULL OR c.tenant = $2)
           AND EXISTS (SELECT 1 FROM documents d
                       WHERE d.rid = c.doc_rid AND d.status = 'active')
        """,
        col, tenant)
    return {k: int(row[k] or 0) for k in ("filled", "provably_fresh", "candidates", "unstamped")}


def summarize_freshness(counts: dict) -> dict:
    """분포 → 재계산 범위. 순수·결정론.

    ⛔ **판정하지 않는다.** 여기서 나오는 것은 *무엇이 낡았나* 가 아니라 *무엇을 확인해야
    하는가* 다. 문턱도 비율도 없다 — 이 리포는 비율을 신호가 쌓이기 전에 내지 않는다.
    """
    return {
        **counts,
        # 재계산해야 하는 집합. 후보(시간이 어긋남) + 미상(시간을 모름).
        "must_recheck": counts["candidates"] + counts["unstamped"],
        # 재계산이 **필요 없다고 증명된** 집합. 감지기의 실제 산출물이다.
        "ruled_out": counts["provably_fresh"],
        # 도장이 하나도 없으면 이 감지기는 아무 말도 못 한다. 그 사실이 보여야 한다.
        "blind": counts["filled"] > 0 and counts["provably_fresh"] + counts["candidates"] == 0,
    }
