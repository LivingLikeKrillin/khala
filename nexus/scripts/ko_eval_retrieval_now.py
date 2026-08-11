"""검색만 재는 자 — LLM 을 한 번도 부르지 않는다.

답변 하니스(`ko_eval_answer_run.py`)는 질의당 한 번 LLM 을 부르고, 그 키가 없으면 아무 숫자도
못 낸다. 그런데 오늘 코퍼스를 바꾼 것들(재적재·벡터 무효화·청크 텍스트 변경)이 부술 수 있는 것은
**검색 쪽**이고, 그 절반은 키 없이 잴 수 있다.

**이것은 답변 품질이 아니다.** 검색이 정답 문서를 올려도 답이 틀릴 수 있고, 그 구간은 이 리포가
이미 한 번 놓쳤다 — 문서 단위 Recall@10 이 1.000 인데 846자 표가 앞 300자만 프롬프트에 실려
모델이 답을 못 한 적이 있다. 그러니 여기서 초록이 나와도 답변 하니스를 대체하지 않는다.

같은 라벨·같은 gold·같은 테넌트를 쓴다. 판정은 **문서 단위**: gold 문서가 상위 k 에 있는가.

    docker exec nexus-app python scripts/ko_eval_retrieval_now.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ko_eval_labels import ManifestPack, check, load  # noqa: E402
from scripts.ko_eval_packb import MANIFEST  # noqa: E402

LOCAL_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "local"
LABELS = LOCAL_DIR / "packb-labels.yaml"
REPORT = LOCAL_DIR / "retrieval-now.json"
TENANT = "default"


async def _run(args) -> int:
    from nexus import db
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.search import hybrid

    labels = load(LABELS)
    if problems := check(labels, ManifestPack(MANIFEST)):
        print("✗ 라벨 게이트 실패 — 측정 이전에 자가 틀렸다:", *problems[:4], sep="\n  ")
        return 1

    titles = {d["key"]: d["title"] for d in json.loads(MANIFEST.read_text(encoding="utf-8"))["docs"]}
    queries = [q for q in labels["queries"] if q.get("answerable")][:args.limit]
    print(f"✓ 관문 통과 — 라벨 revision {labels['revision']} · 질의 {len(queries)}건 "
          f"(테넌트 {TENANT}, LLM 미사용)\n")

    svc = embedding_service_from_config()
    await db.get_pool()
    rows, ranks = [], []
    try:
        for q in queries:
            result = await hybrid.hybrid_search(q["query"], tenant=TENANT, clearance="INTERNAL",
                                                top_k=args.top_k, embedding_svc=svc)
            if result.degraded:
                print(f"✗ 다리가 죽었다({result.degraded}) — 이 상태의 숫자는 결과가 아니다")
                return 1
            gold = {titles[g] for g in q["gold"]}
            rank = next((i + 1 for i, h in enumerate(result.hits) if h.doc_title in gold), None)
            ranks.append(rank)
            tiers = {h.provenance_tier for h in result.hits}
            rows.append({"qid": q["id"], "rank": rank, "hits": len(result.hits),
                         "machine_read_in_top10": sum(
                             1 for h in result.hits if h.provenance_tier == "machine_read"),
                         "top1": result.hits[0].doc_title if result.hits else None})
            mark = "OK " if rank else "MISS"
            print(f"{mark} {q['id']:14s} 순위 {str(rank or '-'):>3}  "
                  f"등급 {'+'.join(sorted(tiers)) or '-'}")
    finally:
        await db.close_pool()

    hit = [r for r in ranks if r]
    n = len(ranks)
    recall = len(hit) / n if n else 0.0
    mrr = sum(1 / r for r in hit) / n if n else 0.0
    top1 = sum(1 for r in hit if r == 1) / n if n else 0.0
    print(f"\n  Recall@{args.top_k} {len(hit)}/{n} = {recall:.3f}"
          f"   MRR {mrr:.3f}   Top-1 {top1:.3f}")
    misses = [r["qid"] for r in rows if not r["rank"]]
    if misses:
        print(f"  놓친 질의: {', '.join(misses)}")

    REPORT.write_text(json.dumps(
        {"ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "labels_revision": labels["revision"], "tenant": TENANT, "top_k": args.top_k,
         "recall": recall, "mrr": mrr, "top1": top1, "queries": rows},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--top-k", type=int, default=10)
    return asyncio.run(_run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
