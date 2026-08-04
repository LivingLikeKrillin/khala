"""구동식 재임베딩 — 큐는 NULL 컬럼, 실패는 세고, 컷오버는 조건이 선다
(SPEC-nexus-kure-embedding-swap §4.4, §4.5).

**프로덕션의 재임베딩은 창발적이다**: 텍스트가 바뀌면 `embedding` 이 NULL 이 되고, 다음 적재가
NULL 인 것을 채운다. 그 방식은 "언젠가 채워진다" 는 말과 같고, 마이그레이션에는 못 쓴다 — 언제
끝나는지도, 무엇이 실패했는지도 아무도 모른다. 실제로 이 작업이 찾아낸 결함 중 하나가 정확히
그것이었다(실패한 임베딩이 NULL 로 남고 어디에도 집계되지 않음).

그래서 여기서는 **몰아서 돌리고, 세고, 남긴다.**

- 큐는 여전히 NULL 컬럼이다 → 중단해도 이어서 돈다(재개 상태를 따로 저장하지 않는다).
- 실패는 사유와 함께 요약에 남는다. 조용한 NULL 은 없다.
- 영구 실패는 사람이 `waive` 로 서명해 뺀다 — 이 모듈은 후보만 보고한다 (§4.5).
- 컷오버는 네 조건이 **모두** 설 때만 허용된다. 하나라도 안 서면 무엇이 안 섰는지 말한다.
- **범위는 선언한다.** `tenant=None` 은 "전 테넌트" 라는 명시적 선택이고, 기본값이 아니다.
  처음엔 필터 자체가 없었고, 그래서 DB 테스트가 자기 테넌트를 재임베딩하면서 **같은 DB 의 평가
  코퍼스 1,906건을 상수 벡터로 덮어썼다.** 그 위에서 돌린 ANN 측정이 인덱스를 탓하는 결론을
  냈다(2026-08-04, 정정됨). 파괴 범위가 선언되지 않으면 언젠가 넘친다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nexus import db
from nexus.index.vector_index import (
    INDEX_NAMES,
    compute_lists,
    count_indexable_sql,
    create_index_sql,
    dimensions_of,
    resolve_column,
)


@dataclass
class Failure:
    chunk_rid: str
    reason: str


@dataclass
class ReembedSummary:
    """한 번의 실행 결과. **"돌고 있다" 는 상태가 아니다** — 끝났을 때 무엇이 남았는지가 상태다."""
    column: str
    model: str
    embedded: int = 0
    failed: list[Failure] = field(default_factory=list)
    remaining: int = 0

    @property
    def ok(self) -> bool:
        return not self.failed

    def render(self) -> str:
        lines = [f"재임베딩 [{self.model} → {self.column}] 완료 {self.embedded}건 · "
                 f"실패 {len(self.failed)}건 · 남은 {self.remaining}건"]
        for f in self.failed[:10]:
            lines.append(f"  ✗ {f.chunk_rid}: {f.reason[:160]}")
        if len(self.failed) > 10:
            lines.append(f"  … 외 {len(self.failed) - 10}건")
        if self.failed:
            lines.append("  영구 실패면 `nexus reembed waive <rid> --reason … --by …` 로 "
                         "서명해 빼야 컷오버가 선다 (SPEC §4.5).")
        return "\n".join(lines)


# ── 조회 (부분 술어는 인덱스와 같은 모양) ────────────────────────────────────

async def pending_rids(column: str, limit: int, exclude: set[str] | None = None,
                       tenant: str | None = None) -> list[tuple[str, str, str]]:
    """아직 이 세대의 벡터가 없는 활성 청크. waiver 로 빠진 것은 큐에서 제외한다.

    `exclude` 는 **이번 실행에서 이미 실패한 rid** 다. 실패해도 컬럼은 NULL 로 남으므로 다음
    조회에 또 잡히고, 그러면 같은 실패가 요약에 여러 번 쌓인다(실측으로 확인). DB 에 실패 표식을
    남기지 않는 이유는 그게 waiver 의 자리이기 때문이다 — 실패는 실행의 사실이고, 포기는 사람의
    결정이다.
    """
    col = resolve_column(column)
    rows = await db.fetch_all(
        f"""
        SELECT c.rid, c.chunk_text, c.section_path
        FROM chunks c
        LEFT JOIN embed_waivers w ON w.chunk_rid = c.rid
        WHERE c.status = 'active' AND c.is_quarantined = false
          AND c.{col} IS NULL AND w.chunk_rid IS NULL
          AND NOT (c.rid = ANY($2::text[]))
          AND ($3::text IS NULL OR c.tenant = $3)
        ORDER BY c.rid
        LIMIT $1
        """, limit, list(exclude or ()), tenant)
    return [(r["rid"], r["chunk_text"], r["section_path"]) for r in rows]


async def counts(column: str, tenant: str | None = None) -> dict:
    """컷오버 판정과 진행 보고가 함께 쓰는 숫자. 범위는 재임베딩과 **같아야** 한다."""
    col = resolve_column(column)
    row = await db.fetch_one(
        f"""
        SELECT
          count(*) FILTER (WHERE c.status='active' AND c.is_quarantined=false) AS active,
          count(*) FILTER (WHERE c.status='active' AND c.is_quarantined=false
                             AND c.{col} IS NOT NULL) AS embedded,
          count(*) FILTER (WHERE c.status='active' AND c.is_quarantined=false
                             AND c.{col} IS NULL AND w.chunk_rid IS NOT NULL) AS waived,
          count(*) FILTER (WHERE c.status='active' AND c.is_quarantined=false
                             AND c.{col} IS NULL AND w.chunk_rid IS NULL) AS pending
        FROM chunks c LEFT JOIN embed_waivers w ON w.chunk_rid = c.rid
        WHERE ($1::text IS NULL OR c.tenant = $1)
        """, tenant)
    return dict(row)


# ── 실행 ─────────────────────────────────────────────────────────────────────

async def reembed(embedding_svc, column: str, batch_size: int = 16,
                  progress=None, tenant: str | None = None) -> ReembedSummary:
    """NULL 인 것을 채운다. 실패해도 계속 가되, **세어서 남긴다.**

    `tenant=None` 은 전 테넌트다 — 마이그레이션의 정상 사용이지만, **범위를 좁히고 싶을 때
    좁힐 수 있어야** 한다. 그 수단이 없어서 테스트가 평가 코퍼스를 덮어쓴 적이 있다.
    """
    from nexus.utils import get_search_text

    col = resolve_column(column)
    model = embedding_svc.get_model_name()
    expected_dim = dimensions_of(col)
    summary = ReembedSummary(column=col, model=model)

    class _C:
        def __init__(self, text, section):
            self.chunk_text, self.section_path, self.context_prefix = text, section, None

    failed_rids: set[str] = set()
    while True:
        batch = await pending_rids(col, batch_size, exclude=failed_rids, tenant=tenant)
        if not batch:
            break
        texts = [get_search_text(_C(text, section)) for _, text, section in batch]
        rids = [rid for rid, _, _ in batch]
        try:
            vectors = await embedding_svc.embed_documents(texts)
        except Exception as e:                      # noqa: BLE001 — 배치가 통째로 실패할 수도 있다
            # 배치 실패를 개별 실패로 나눠 다시 시도한다. 한 청크가 나머지를 막으면 안 된다.
            vectors = []
            for rid, text in zip(rids, texts, strict=True):
                try:
                    vectors.append((await embedding_svc.embed_documents([text]))[0])
                except Exception as inner:          # noqa: BLE001
                    summary.failed.append(Failure(rid, f"{type(inner).__name__}: {inner}"))
                    failed_rids.add(rid)
                    vectors.append(None)
            del e

        for rid, vec in zip(rids, vectors, strict=True):
            if vec is None:
                continue
            if len(vec) != expected_dim:
                summary.failed.append(Failure(rid, f"차원 {len(vec)} ≠ {expected_dim}"))
                failed_rids.add(rid)
                continue
            await db.execute(
                f"UPDATE chunks SET {col} = $1::vector, embed_model = $2, updated_at = now() "
                "WHERE rid = $3",
                "[" + ",".join(repr(float(v)) for v in vec) + "]", model, rid)
            summary.embedded += 1

        if progress:
            progress(summary)

    summary.remaining = (await counts(col, tenant))["pending"]
    return summary


async def waive(chunk_rid: str, model: str, reason: str, waived_by: str) -> None:
    """사람이 서명해 뺀다. **CLI 의 재임베딩 경로는 이 함수를 부르지 않는다** (§4.5)."""
    if not reason.strip() or not waived_by.strip():
        raise ValueError("waiver 에는 사유와 서명이 필요하다 — 둘 없이 빠진 내용은 사라진 내용이다")
    await db.execute(
        "INSERT INTO embed_waivers (chunk_rid, model, reason, waived_by) VALUES ($1,$2,$3,$4) "
        "ON CONFLICT (chunk_rid) DO NOTHING", chunk_rid, model, reason.strip(), waived_by.strip())


async def waived_rows() -> list[dict]:
    rows = await db.fetch_all(
        "SELECT chunk_rid, model, reason, waived_by, waived_at FROM embed_waivers ORDER BY waived_at")
    return [dict(r) for r in rows]


# ── 인덱스 (재임베딩이 끝난 뒤에) ────────────────────────────────────────────

async def create_index(column: str) -> tuple[int, int]:
    """`lists` 를 **지금 세어서** 만든다. (rows, lists) 반환.

    채워지는 중에 만들면 존재한 적 없는 코퍼스에 맞춰진다 — 그래서 마이그레이션이 아니라 여기 있다.
    """
    col = resolve_column(column)
    rows = await db.fetch_val(count_indexable_sql(col))
    lists = compute_lists(rows)
    await db.execute(create_index_sql(col, lists))
    return rows, lists


async def index_exists(column: str) -> bool:
    col = resolve_column(column)
    return bool(await db.fetch_val(
        "SELECT 1 FROM pg_indexes WHERE tablename='chunks' AND indexname=$1", INDEX_NAMES[col]))


# ── 컷오버 전제 조건 (§4.5) ──────────────────────────────────────────────────

async def cutover_blockers(column: str, summary_failures: int = 0,
                           tenant: str | None = None) -> list[str]:
    """컷오버를 막는 이유들. 비면 가도 된다.

    조건을 **하나라도 말없이 통과시키지 않는다** — 부분 스왑은 코퍼스가 조용히 작아진 상태다.
    """
    col = resolve_column(column)
    blockers: list[str] = []
    c = await counts(col, tenant)

    if c["pending"]:
        blockers.append(
            f"임베딩도 waiver 도 없는 활성 청크 {c['pending']}건 — 부분 스왑은 코퍼스가 조용히 "
            "작아진 것이다")
    if summary_failures:
        blockers.append(f"waive 되지 않은 실패 {summary_failures}건")

    from nexus.index.embed_health import embed_generation_report, fetch_embed_generations
    report = embed_generation_report(await fetch_embed_generations(column=col))
    if report["mixed"]:
        gens = ", ".join(f"{g['model']}({g['count']})" for g in report["generations"])
        blockers.append(f"{col} 에 세대가 섞여 있다: {gens}")

    if not await index_exists(col):
        blockers.append(f"{INDEX_NAMES[col]} 인덱스가 없다 — `reembed create-index` 를 먼저")

    return blockers
