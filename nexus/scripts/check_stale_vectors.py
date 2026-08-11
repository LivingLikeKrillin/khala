"""저장된 벡터가 **지금 텍스트의 벡터인가** — 재계산해서 비교한다.

**알려진 원인은 고쳐졌다** (SPEC-nexus-generation-of-record §3.4): `_save_chunks` 의 ON CONFLICT 가
텍스트 변경 시 `embedding`(768)과 `tsvector_ko` 만 NULL 로 되돌리고 `embedding_1024` 는 그대로
뒀었다. 재임베딩 큐가 `WHERE <컬럼> IS NULL` 이라 그런 청크는 큐에 영영 안 들어갔고, **옛 텍스트의
벡터**로 검색됐다 — 실측 8건, 최저 코사인 0.593. 이제 레지스트리의 모든 벡터 컬럼을 무효화한다.

이 자가 남아 있는 이유는 **모르는 원인** 때문이다. 벡터가 NULL 이 아니면 커버리지는 "채워짐" 으로
세므로, *있는데 틀린* 상태를 볼 수 있는 것은 재계산뿐이다. 값싸지 않다(334청크 ≈ 35분) — 그래서
상시 검사가 아니라 손으로 부르는 자다.

**대조군을 먼저 읽어라** (계측기를 먼저 의심하라): `reembed run` 으로 방금 다시 채운 청크들은
정의상 현재 텍스트의 벡터다. 그것들이 1.0 이 안 나오면 자가 고장난 것이고, 나머지 수치는 못 쓴다.

읽기 전용. 코퍼스를 건드리지 않는다.

    docker exec nexus-app python -u scripts/check_stale_vectors.py [--tenant default]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus import db  # noqa: E402
from nexus.index.vector_index import configured_column  # noqa: E402
from nexus.providers.embedding import embedding_service_from_config  # noqa: E402
from nexus.utils import get_search_text  # noqa: E402

LOCAL = Path(__file__).resolve().parents[1] / "tests" / "eval" / "local"
CACHE_FILE = LOCAL / "stale-vectors-cache.json"

#: 같은 입력이면 같은 벡터가 나와야 한다. 부동소수 잡음만 허용한다 — 문턱을 관대하게 잡으면
#: "조금 다른 텍스트" 를 신선하다고 세게 된다. 대조군이 이 문턱을 검증한다.
FRESH_COSINE = 0.9999

BATCH = 16


class _Chunk:
    """`get_search_text()` 가 기대하는 모양. 검색 텍스트 규칙을 여기서 다시 쓰지 않는다."""

    def __init__(self, section_path: str, chunk_text: str, context_prefix: str | None):
        self.section_path = section_path
        self.chunk_text = chunk_text
        self.context_prefix = context_prefix


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _load_cache() -> dict:
    return json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tenant", default="default")
    ap.add_argument("--max-batches", type=int, default=0, help="0 이면 끝까지")
    args = ap.parse_args()

    await db.get_pool()
    try:
        col = configured_column()
        rows = [dict(r) for r in await db.fetch_all(
            f"SELECT c.rid, c.section_path, c.chunk_text, c.context_prefix, c.embed_model, "
            f"       c.provenance_tier, c.updated_at, c.{col}::text AS vec "
            f"FROM chunks c JOIN documents d ON d.rid = c.doc_rid "
            f"WHERE c.tenant = $1 AND c.status = 'active' AND d.status = 'active' "
            f"  AND c.is_quarantined = false AND c.{col} IS NOT NULL "
            f"ORDER BY c.rid", args.tenant)]

        svc = embedding_service_from_config()
        print(f"  {args.tenant} · {col} · 청크 {len(rows)}개 · {svc.model}", flush=True)

        cache = _load_cache()
        todo = [r for r in rows if r["rid"] not in cache]
        budget = args.max_batches or 10 ** 9
        for i in range(0, len(todo), BATCH):
            if budget <= 0:
                print(f"  예산 소진 — {len(cache)}/{len(rows)} 까지 계산됨. 다시 부르면 이어서 한다",
                      flush=True)
                break
            batch = todo[i:i + BATCH]
            texts = [get_search_text(_Chunk(r["section_path"], r["chunk_text"],
                                            r["context_prefix"])) for r in batch]
            for r, fresh_vec in zip(batch, await svc.embed_documents(texts)):
                stored = [float(x) for x in r["vec"].strip("[]").split(",")]
                cache[r["rid"]] = round(_cos(stored, fresh_vec), 6)
            CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
            budget -= 1
            print(f"  {min(len(cache), len(rows))}/{len(rows)}", flush=True)
    finally:
        await db.close_pool()

    done = [r for r in rows if r["rid"] in cache]
    if len(done) < len(rows):
        print(f"\n  아직 {len(rows) - len(done)}개 남았다 — 다시 호출하라")
        return 75

    stale = [r for r in done if cache[r["rid"]] < FRESH_COSINE]

    # 대조군 먼저. 이것이 안 맞으면 아래 숫자는 전부 못 쓴다.
    control = [r for r in done if r["updated_at"].date().isoformat() == "2026-08-10"
               and r["embed_model"] == "KURE-v1" and r["provenance_tier"] == "machine_read"]
    if control:
        worst = min(cache[r["rid"]] for r in control)
        print(f"\n  대조군(오늘 reembed 로 다시 채운 machine_read {len(control)}개) 최저 코사인 {worst:.6f}")
        if worst < FRESH_COSINE:
            print("  ⚠ 대조군이 문턱을 못 넘었다 — 자가 고장난 것이다. 아래 숫자를 쓰지 마라.")

    print(f"\n  낡은 벡터 {len(stale)}/{len(done)}")
    by_label: dict[str, list[int]] = {}
    for r in done:
        k = r["embed_model"]
        b = by_label.setdefault(k, [0, 0])
        b[0] += 1
        b[1] += 1 if cache[r["rid"]] < FRESH_COSINE else 0
    print("\n  라벨별            전체   낡음")
    for k, (n, s) in sorted(by_label.items()):
        print(f"    {k:18s} {n:5d} {s:6d}")

    if stale:
        print("\n  가장 많이 어긋난 것들(코사인 낮은 순)")
        for r in sorted(stale, key=lambda x: cache[x["rid"]])[:8]:
            print(f"    {cache[r['rid']]:.4f}  {r['embed_model']:16s} {r['rid']}")

    out = LOCAL / "stale-vectors.json"
    out.write_text(json.dumps(
        {"tenant": args.tenant, "column": col, "threshold": FRESH_COSINE,
         "total": len(done), "stale": len(stale),
         "by_label": {k: {"total": n, "stale": s} for k, (n, s) in by_label.items()}},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n기록: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
