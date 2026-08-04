"""임베딩 세대 건전성 — SPEC-nexus-embed-generation-drift.

부분 재임베딩(코퍼스가 2개 이상 embed_model 세대에 걸침 = 조용한 드리프트 1위)을 감지하는
가벼운 안전판. 기존 chunks.embed_model 컬럼을 읽는다. 판정은 순수, 조회는 벡터 인덱스의 부분
술어(idx_chunk_vector)와 동일한 WHERE 로 '인덱스에 실재하는 벡터'만 센다.
"""

from __future__ import annotations

from nexus import db


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
