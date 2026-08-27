"""상위 10을 무엇이 차지하고 있는가 — 랭킹 결함을 고치기 **전에** 재는 평가 하니스.

2026-08-11: 답변 품질 격자에서 `insufficient`(검색이 답에 필요한 근거를 못 줌)가 40건 중 6건으로
나왔다. 원인 후보는 **극소 문서**다 — Notion 데이터베이스 행 하나가 문서 하나로 적재되고
(`- **디제잉 포인트**: 60`), 극히 짧아 BM25 길이 정규화에서 유리하며, 질의어를 그대로 담는다.
`디제잉포인트는 언제 합산되나` 에서 상위 20 중 12개가 그런 문서였고 정답 문장은 18위였다.

여기서 재는 것은 그 관찰이 **40건 전체에서도 성립하는가**이다. 고치기 전에 재지 않으면 고친 뒤에
무엇이 좋아졌는지 말할 수 없다.

읽기 전용. 코퍼스를 건드리지 않는다.

    docker exec nexus-app python scripts/ko_eval_rank_crowding.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus import db  # noqa: E402
from nexus.providers.embedding import embedding_service_from_config  # noqa: E402
from nexus.search import hybrid  # noqa: E402
from scripts.ko_eval_labels import load  # noqa: E402
from scripts.ko_eval_packb import MANIFEST  # noqa: E402

LOCAL = Path(__file__).resolve().parents[1] / "tests" / "eval" / "local"
TENANT = "default"

#: **극소 문서**의 문턱. 코퍼스 실측(2026-08-11): 116개 중 39개가 150자 미만, 96개가 300자 미만.
#: 150 을 쓰는 이유는 그 아래가 "한 줄짜리 DB 행" 이고 300 근처부터는 짧은 노트가 섞이기
#: 때문이다 — 문턱을 관찰 뒤에 고르지 않도록 여기 적어 두고, 바꾸면 그 사실이 보이게 한다.
TINY_CHARS = 150


async def _doc_sizes() -> dict[str, int]:
    rows = await db.fetch_all(
        "SELECT d.rid, sum(length(c.chunk_text))::int AS chars "
        "FROM documents d JOIN chunks c ON c.doc_rid = d.rid AND c.status = 'active' "
        "WHERE d.tenant = $1 AND d.status = 'active' GROUP BY d.rid", TENANT)
    return {r["rid"]: r["chars"] for r in rows}


async def main() -> int:
    labels = load(LOCAL / "packb-labels.yaml")["queries"]
    man = json.loads((LOCAL / MANIFEST).read_text(encoding="utf-8"))
    titles = {d["key"]: d["title"] for d in man["docs"]}

    svc = embedding_service_from_config()
    await db.get_pool()
    sizes = await _doc_sizes()
    rows = []
    try:
        for q in labels:
            if not q.get("answerable"):
                continue
            r = await hybrid.hybrid_search(q["query"], tenant=TENANT, clearance="INTERNAL",
                                           top_k=40, embedding_svc=svc)
            gold = {titles[g] for g in q["gold"]}
            top10 = r.hits[:10]
            tiny10 = sum(1 for h in top10 if sizes.get(h.doc_rid, 0) < TINY_CHARS)
            gold_rank = next((i for i, h in enumerate(r.hits, 1) if h.doc_title in gold), None)
            rows.append({"qid": q["id"], "tiny_in_top10": tiny10,
                         "gold_rank": gold_rank,
                         "gold_in_top10": bool(gold_rank and gold_rank <= 10)})
    finally:
        await db.close_pool()

    n = len(rows)
    tiny = sum(r["tiny_in_top10"] for r in rows)
    missed = [r for r in rows if not r["gold_in_top10"]]
    print(f"\n  질의 {n}건 · 상위 10 슬롯 {n * 10}개")
    print(f"  극소 문서(<{TINY_CHARS}자)가 차지한 슬롯  {tiny}  ({tiny / (n * 10):.0%})")
    print(f"  정답 문서가 상위 10에 없는 질의        {len(missed)}")
    for r in sorted(missed, key=lambda x: (x["gold_rank"] or 999)):
        rank = r["gold_rank"] or "40위 밖"
        print(f"    {r['qid']:12s} 정답 {rank!s:8s} 상위10 중 극소 {r['tiny_in_top10']}")

    heavy = [r for r in rows if r["tiny_in_top10"] >= 5]
    print(f"\n  상위 10의 절반 이상이 극소 문서인 질의  {len(heavy)}/{n}")
    print(f"    그중 정답을 놓친 것  {sum(1 for r in heavy if not r['gold_in_top10'])}")
    light = [r for r in rows if r["tiny_in_top10"] < 5]
    print(f"  나머지 질의                            {len(light)}/{n}")
    print(f"    그중 정답을 놓친 것  {sum(1 for r in light if not r['gold_in_top10'])}")

    (LOCAL / "rank-crowding.json").write_text(
        json.dumps({"tiny_chars": TINY_CHARS, "rows": rows}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    print(f"\n기록: {LOCAL / 'rank-crowding.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
