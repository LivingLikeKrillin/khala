"""근거 창의 얼마가 **우리 자기 문서**인가 — 결정론, LLM 0회.

⛔ **왜 있나 (`OPEN.md` A57, 실측 2026-09-03).** `pb-space-07` 이 팀의 배포 기준을 물었는데 답이
khala 자기 런북에서 나왔고, 상위 10 이 10/10 우리 문서였다. 처방 후보는 비싸다(자기 문서를 다른
테넌트로 가르는 것). **표본 1건으로 그런 결정을 하면 안 된다** — 이 리포는 기법 추가로 7전 7패했고
오른 것은 전부 결함 제거였다. 그러니 고르기 전에 **크기를 잰다.**

⭐ **문서 수 문제가 아니다** (실측): khala 리포 문서는 **14**건인데 그 14건이 청크 197 · 14만 자를
싣고, 조직 문서 **112**건이 청크 269 · 11만 자를 싣는다. 검색은 문서가 아니라 **청크**를 매기므로
14건이 검색 대상 텍스트의 절반을 넘게 차지한다. 세는 단위를 문서로 잡으면 정반대로 읽힌다.

여기서 내는 것은 판정이 아니라 **분포**다. 어느 질의에서 창이 우리 문서로 얼마나 차는지, 그리고
gold 가 조직 문서인 질의에서 그것이 gold 를 밀어냈는지.

    docker exec nexus-app python -m scripts.self_document_crowding \\
        --labels /app/tests/eval/local/packb-labels.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ko_eval_labels import load  # noqa: E402

#: Notion 에서 들어온 문서의 키 접두사. 그 밖은 이 리포가 쓴 문서다.
#:
#: ⚠ **이 판정의 한계를 적어 둔다**: 조직이 Notion 이 아닌 곳에 쓴 문서나, 우리가 Notion 에 쓴
#: 문서는 반대로 찍힌다. 지금 이 배포에서는 두 무리가 실제로 갈려 있어서 맞지만, 출처가 늘면
#: 이 함수부터 고쳐야 한다 — 조용히 틀리지 않게 이름을 붙여 둔다.
ORG_PREFIX = "ext-notion-"


def population(key: str) -> str:
    """`org`(조직이 쓴 문서) 또는 `repo`(이 리포가 쓴 문서)."""
    return "org" if key.startswith(ORG_PREFIX) else "repo"


def doc_key(source_uri: str) -> str:
    """`default:FOO.md` → `FOO.md`. 테넌트 접두사만 떼고 나머지는 그대로 둔다."""
    return (source_uri or "").split(":", 1)[-1]


def crowding(keys: list[str]) -> float:
    """창에서 우리 문서가 차지한 비율. 빈 창은 0.0 — 나눗셈을 하지 않는다."""
    return sum(population(k) == "repo" for k in keys) / len(keys) if keys else 0.0


def verdict_rows(rows: list[dict]) -> dict:
    """분포를 요약한다. **평균만 내지 않는다** — 평균은 10/10 을 절반이 아니라 한 점으로 만든다."""
    org = [r for r in rows if r["gold_pop"] == "org"]
    return {
        "queries": len(rows),
        "org_gold": len(org),
        "full_windows": sum(1 for r in rows if r["crowding"] == 1.0),
        "majority_windows": sum(1 for r in rows if r["crowding"] > 0.5),
        "clean_windows": sum(1 for r in rows if r["crowding"] == 0.0),
        "org_gold_missed": sum(1 for r in org if not r["gold_in_window"]),
        "org_gold_missed_and_crowded": sum(
            1 for r in org if not r["gold_in_window"] and r["crowding"] > 0.5),
    }


async def _run(args) -> int:
    from nexus import db
    from nexus.api import _load_config
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.search import hybrid

    labels = load(args.labels)
    queries = [q for q in labels["queries"] if q.get("answerable")]
    svc, cfg = embedding_service_from_config(), _load_config()
    await db.get_pool()

    rows = []
    for q in queries:
        res = await hybrid.hybrid_search(q["query"], tenant=args.tenant, clearance=args.clearance,
                                         top_k=args.top_k, embedding_svc=svc, config=cfg)
        if res.degraded:
            print(f"✗ 경로가 죽었다({res.degraded}) — 이 상태의 수는 결과가 아니다")
            return 1
        keys = [doc_key(h.source_uri) for h in res.hits]
        golds = q.get("gold") or []
        rows.append({
            "id": q["id"], "crowding": crowding(keys),
            "gold_pop": "org" if all(population(g) == "org" for g in golds) else "repo",
            "gold_in_window": any(k in golds for k in keys),
        })

    await db.close_pool()

    rows.sort(key=lambda r: (-r["crowding"], r["id"]))
    print(f"창 크기 {args.top_k} · 질의 {len(rows)} · 테넌트 {args.tenant}\n")
    print("  질의            창의 우리 문서   gold 출처   gold 창 안")
    for r in rows:
        bar = "#" * round(r["crowding"] * 10)
        print(f"  {r['id']:14s} {r['crowding']:5.0%} {bar:<10s}  {r['gold_pop']:4s}"
              f"        {'예' if r['gold_in_window'] else '**아니오**'}")

    v = verdict_rows(rows)
    print(f"\n  창이 전부 우리 문서       {v['full_windows']:3d} / {v['queries']}")
    print(f"  창의 절반 넘게 우리 문서  {v['majority_windows']:3d} / {v['queries']}")
    print(f"  우리 문서가 하나도 없음   {v['clean_windows']:3d} / {v['queries']}")
    print(f"\n  gold 가 조직 문서인 질의  {v['org_gold']:3d}")
    print(f"    그중 gold 가 창 밖      {v['org_gold_missed']:3d}"
          f"  (그리고 창이 절반 넘게 우리 문서: {v['org_gold_missed_and_crowded']})")
    print("\n  ⚠ 이것은 분포이지 판정이 아니다. 창이 우리 문서로 찬 것과 그것이 답을 망친 것은"
          " 다른 말이다 — 답이 맞았는지는 답변 하니스가 잰다.")
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--labels", type=Path, required=True)
    p.add_argument("--tenant", default="default")
    p.add_argument("--clearance", default="INTERNAL")
    p.add_argument("--top-k", type=int, default=10, help="근거 창의 크기")
    return asyncio.run(_run(p.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
