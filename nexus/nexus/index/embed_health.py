"""임베딩 세대 건전성 — SPEC-nexus-embed-generation-drift.

부분 재임베딩(코퍼스가 2개 이상 embed_model 세대에 걸침 = 조용한 드리프트 1위)을 감지하는
가벼운 안전판. 기존 chunks.embed_model 컬럼을 읽는다. 판정은 순수, 조회는 벡터 인덱스의 부분
술어(idx_chunk_vector)와 동일한 WHERE 로 '인덱스에 실재하는 벡터'만 센다.
"""

from __future__ import annotations

import structlog

from nexus import db

logger = structlog.get_logger(__name__)


def embed_generation_report(rows: list[tuple[str, int]]) -> dict:
    """(embed_model, count) 분포 → 세대 리포트. 순수·결정론.

    정렬은 (count desc, model asc) — count 동률을 model 이름으로 깨 결정론 보장.
    mixed = 세대(distinct embed_model) 가 2개 이상. dominant = 정렬 첫 세대(없으면 None).
    임계값 없음: 어떤 두 번째 세대든 mixed. 비율은 generations 카운트로 자명하다.
    """
    ordered = sorted(rows, key=lambda r: (-r[1], r[0]))
    generations = [{"model": m, "count": c} for m, c in ordered]
    return {
        "generations": generations,
        "distinct": len(generations),
        "total": sum(c for _, c in ordered),
        "mixed": len(generations) > 1,
        "dominant": generations[0]["model"] if generations else None,
    }


async def fetch_embed_generations(column: str | None = None) -> list[tuple[str, int]]:
    """인덱스에 실재하는 벡터의 embed_model 분포. WHERE 는 해당 컬럼의 인덱스 부분술어와 동일.

    `column` 은 어느 세대를 보느냐다 (SPEC-nexus-kure-embedding-swap §4.5). 마이그레이션 중에는
    컬럼이 둘이고, 새 컬럼의 세대를 물었는데 **교체 대상인 옛 컬럼을 보고하면** 컷오버 조건이
    엉뚱한 것을 통과시킨다.
    """
    from nexus.index.vector_index import resolve_column

    col = resolve_column(column)
    rows = await db.fetch_all(
        f"""
        SELECT embed_model, count(*) AS n
        FROM chunks
        WHERE status = 'active' AND is_quarantined = false AND {col} IS NOT NULL
        GROUP BY embed_model
        """
    )
    return [(r["embed_model"], r["n"]) for r in rows]


async def fetch_waived_count() -> int:
    """임베딩을 포기한 청크 수 — 검색에서 빠진 내용의 양이다 (§4.5)."""
    return int(await db.fetch_val("SELECT count(*) FROM embed_waivers") or 0)


async def fetch_coverage_by_tenant() -> list[dict]:
    """테넌트별 · 컬럼별 커버리지 (SPEC-nexus-embedding-cutover-seam §4.2).

    **집계 쿼리 하나**로 두 컬럼을 함께 센다 — `/status` 가 테넌트마다 쿼리를 날리기 시작하면
    "필드 하나 더" 가 조용히 팬아웃이 된다. 여기서 지키는 경계다.

    커버리지가 보고돼야 하는 이유는 하나다: 컬럼이 비어 있으면 벡터 다리가 **예외 없이** 0행을
    내고, 그 배포는 키워드 전용으로 답하면서 건강해 보인다.
    """
    rows = await db.fetch_all(
        """
        SELECT tenant,
               count(*) FILTER (WHERE status = 'active' AND is_quarantined = false) AS active,
               count(*) FILTER (WHERE status = 'active' AND is_quarantined = false
                                  AND embedding IS NOT NULL) AS embedding,
               count(*) FILTER (WHERE status = 'active' AND is_quarantined = false
                                  AND embedding_1024 IS NOT NULL) AS embedding_1024
        FROM chunks
        GROUP BY tenant
        ORDER BY tenant
        """
    )
    return [
        {
            "tenant": r["tenant"],
            "active": r["active"],
            "embedding": r["embedding"],
            "embedding_1024": r["embedding_1024"],
        }
        for r in rows
    ]


async def log_embedding_coverage(column: str) -> list[dict]:
    """설정된 세대의 커버리지를 기동 시점에 한 번 남긴다. **거부하지 않는다.**

    빈 컬럼을 부팅 거부로 막는 설계는 검토에서 기각됐다: NULL 벡터는 평범한 과도상태(적재 직후,
    죽은 적재, 웨이버 대기 중인 413)이고, 새 테넌트의 첫 적재는 정상적으로 커버리지 0 이다.
    그걸 거부로 만들면 평범한 적재 사고가 **배포 전체 장애**가 된다. 강제는 컷오버 조건이 있는
    자리에서 한다 — 결정이 붙어 있는 검사만이 거부할 자격이 있다 (§4.2).
    """
    coverage = await fetch_coverage_by_tenant()
    for row in coverage:
        active, embedded = row["active"], row[column]
        if not active:
            continue
        if embedded == 0:
            logger.error("embedding_column_empty", tenant=row["tenant"], column=column,
                         active=active,
                         hint="이 세대로 flip 했는데 재임베딩을 안 했을 때의 모양이다 — "
                              "벡터 다리는 조용히 0행을 낸다")
        elif embedded < active:
            logger.warning("embedding_coverage_partial", tenant=row["tenant"], column=column,
                           active=active, embedded=embedded, pending=active - embedded)
    return coverage
