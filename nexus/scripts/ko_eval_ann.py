"""ANN 측면 측정 — 비교가 갚지 못한 빚 (SPEC-nexus-kure-embedding-swap §4.6).

임베딩 비교의 벡터 다리는 **정확 스캔**이었고, 그 SPEC 이 문서로 "프로덕션(ivfflat)을 예측하지
못한다" 고 적었다. 여기서 그 문장을 숫자로 바꾼다: 같은 팩·같은 라벨을 **프로덕션 경로**
(`hybrid_search`, ivfflat 포함)로 다시 재고, 각 실험군이 정확 스캔 대비 얼마를 잃는지 본다.

**1차 판독은 실험군 대 실험군이 아니라 실험군 대 자기 자신이다** (§4.6). 검색 경로를 바꾸면 판정된 적 없는
문서가 새로 올라오고 그건 두 실험군에 비대칭으로 불리하다 — 그래서 교차 비교는 기술용으로만 적고,
컷오버 조건은 **자기 델타**(exact → ANN)에 건다.

두 인덱스는 **같은 방식으로 사이징한 상태에서** 비교한다. 새 컬럼만 잘 맞춘 인덱스를 주면 모델이
아니라 인덱스를 칭찬하게 된다. 옛 인덱스 재빌드는 **이 측정용 DB 에서만** 한다 — ivfflat 은
테이블 전역이라 프로덕션에서 하면 라이브 랭킹이 바뀌고 롤백이 복원이 아니게 된다 (§4.2).

    python -m scripts.ko_eval_ann --report
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.ko_eval_harness import LegResult, collapse_to_documents, score_query
from scripts.ko_eval_labels import DEFAULT_LABELS, load
from scripts.ko_eval_vector import MODELS

TENANT = "ko_eval_embed"
REPORTS_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "reports"
QUERY_VECTORS = Path(__file__).resolve().parents[1] / "tests" / "eval" / "query-vectors"

#: (모델, 청크 컬럼). 옛 세대는 평가 저장소에만 있으므로 측정 전에 chunks 로 옮겨 심는다.
ARMS = [("nomic-embed-text", "embedding"), ("KURE-v1", "embedding_1024")]

#: 앞선 정확 스캔 결과 (2026-08-04 리포트). 자기 델타의 기준선이다.
EXACT_BASELINE = {"nomic-embed-text": {"vector": 0.402, "fused": 0.777},
                  "KURE-v1": {"vector": 0.975, "fused": 0.988}}


class _Fixed:
    """질의 벡터를 파일에서 읽어 주는 스텁 — 측정에 모델 서버를 요구하지 않는다."""

    def __init__(self, model: str):
        data = json.loads((QUERY_VECTORS / f"{model}.json").read_text(encoding="utf-8"))
        self.by_text = {v["query"]: v["vector"] for v in data.values()}
        self.model = model

    def get_model_name(self) -> str:
        return self.model

    async def embed_query(self, text: str) -> list[float]:
        if text not in self.by_text:
            raise SystemExit(f"질의 벡터 없음({self.model}): {text!r}")
        return self.by_text[text]


async def _seed_old_column(con) -> int:
    """옛 세대(nomic) 벡터를 평가 저장소에서 `chunks.embedding` 으로 옮긴다.

    비교가 두 실험군을 `ko_eval_embeddings` 에 담아 뒀는데, 프로덕션 경로는 `chunks` 를 읽는다.
    같은 벡터를 그대로 옮기는 것이므로 측정 대상이 달라지지 않는다.
    """
    return int((await con.execute(
        """
        UPDATE chunks c SET embedding = e.embedding::vector(768)
        FROM ko_eval_embeddings e
        WHERE e.model = 'nomic-embed-text' AND e.tenant = $1 AND e.status = 'embedded'
          AND e.chunk_rid = c.rid AND c.embedding IS NULL
        """, TENANT)).split()[-1])


async def _rebuild_index(con, column: str, lists: int) -> None:
    """**측정용 DB 에서만.** 두 인덱스를 같은 방식으로 사이징해야 모델을 비교하는 게 된다."""
    from nexus.index.vector_index import INDEX_NAMES, create_index_sql

    await con.execute(f"DROP INDEX IF EXISTS {INDEX_NAMES[column]}")
    await con.execute(create_index_sql(column, lists).replace("CONCURRENTLY ", ""))


async def _run(args) -> int:
    from nexus import db
    from nexus.index.vector_index import compute_lists, count_indexable_sql
    from nexus.search import hybrid

    labels = load(DEFAULT_LABELS)
    answerable = [q for q in labels["queries"] if q.get("answerable")]

    pool = await db.get_pool()
    try:
        async with pool.acquire() as con:
            seeded = await _seed_old_column(con)
            print(f"옛 세대 벡터 이식: {seeded}행")
            rows = await con.fetchval(count_indexable_sql("embedding_1024"))
            lists = compute_lists(rows)
            for _, column in ARMS:
                await _rebuild_index(con, column, lists)
            print(f"두 인덱스 재빌드 (측정용 DB 한정) · 행 {rows} → lists={lists}")

        chunk_doc = {}
        for r in await db.fetch_all("SELECT rid, source_uri FROM chunks WHERE tenant=$1", TENANT):
            chunk_doc[r["rid"]] = r["source_uri"].split(":", 1)[1]

        results = {}
        for model, column in ARMS:
            svc = _Fixed(model)
            leg = LegResult(leg=f"fused/{model} (ivfflat)")
            for q in answerable:
                res = await hybrid.hybrid_search(
                    q["query"], tenant=TENANT, top_k=50, embedding_svc=svc,
                    route="hybrid_only",
                    config={"search": {"embedding_column": column, "diversity_per_doc_cap": 50}})
                docs = collapse_to_documents(
                    [(h.rid, i + 1) for i, h in enumerate(res.hits)], chunk_doc)
                leg.scores.append(score_query(q["id"], docs, q["gold"]))
            results[model] = leg
            base = EXACT_BASELINE[model]["fused"]
            print(f"{model:18} fused(ANN) Recall@10 {leg.recall:.3f} · MRR {leg.mrr:.3f} · "
                  f"미스 {leg.misses}  |  정확 스캔 {base:.3f} → 델타 {leg.recall - base:+.3f}")

        if args.report:
            _write(results, rows, lists, len(answerable))
        return 0
    finally:
        await db.close_pool()


def _write(results: dict, rows: int, lists: int, n: int) -> None:
    lines = [
        "# ANN 측면 측정 — 정확 스캔이 예측하지 못하는 부분",
        "",
        f"- **실행 시각**: {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}",
        "- **경로**: `hybrid_search` (프로덕션 경로, ivfflat 포함) · route=hybrid_only",
        f"- **인덱스**: 두 컬럼 모두 `lists={lists}` (행 {rows}) — 측정용 DB 에서만 재빌드",
        f"- **질의**: 답변가능 {n}건 · 라벨 revision 2 · 팩 ko-k8s-2026-08-01",
        "- **수치의 성격**: 앞선 비교와 같이 **하한** (풀 판정 보류)",
        "",
        "## 1차 판독 — 각 실험군의 자기 델타 (exact → ANN)",
        "",
        "| 실험군 | fused 정확 스캔 | fused ANN | 델타 |",
        "|---|---:|---:|---:|",
    ]
    for model, leg in results.items():
        base = EXACT_BASELINE[model]["fused"]
        lines.append(f"| {model} | {base:.3f} | {leg.recall:.3f} | {leg.recall - base:+.3f} |")
    lines += [
        "",
        "> 이 비교가 1차인 이유: 같은 gold 로 같은 실험군의 양쪽을 재므로, 판정 안 된 문서가 **양쪽에서**",
        "> 똑같이 빠진다. 실험군 대 실험군 비교는 검색 경로가 바뀌며 새로 올라온 미판정 문서 때문에 비대칭이라",
        "> 기술용으로만 읽는다 (SPEC §4.6).",
        "",
        "## 기술 — 실험군 대 실험군 (ANN 경로)",
        "",
        "| 실험군 | Recall@10 | MRR@10 | 미스 |",
        "|---|---:|---:|---:|",
    ]
    for model, leg in results.items():
        lines.append(f"| {model} | {leg.recall:.3f} | {leg.mrr:.3f} | {leg.misses} |")
    lines += [
        "",
        "> Pack A 는 khala 자신의 코퍼스가 아니다. 그리고 이 측정은 **교체를 허가하지 않는다** —",
        "> 허가하는 것은 컷오버 조건(§4.5)이고, 이 리포트는 그 조건 중 하나다.",
        "",
    ]
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / f"{datetime.now(timezone.utc):%Y-%m-%d}-ann-vs-exact.md"
    out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print("\n".join(lines))
    print(f"→ {out}")


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="ANN 측면 측정 (SPEC-nexus-kure-embedding-swap §4.6)")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)
    if not os.getenv("DATABASE_URL"):
        print("✗ DATABASE_URL 이 없다")
        return 1
    if set(MODELS) != {m for m, _ in ARMS}:
        print("✗ 레지스트리와 실험군 목록이 어긋난다")
        return 1
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
