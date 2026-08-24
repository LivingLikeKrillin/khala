"""도구 선택 층 드라이런 — *"어느 도구가 필요한가"* 를 검색으로 풀 수 있는가.

**도구를 부르지 않는다.** 실행 층(MCP 클라이언트·인용·등급)은 0줄이고, 이 실험은 그 앞
단계만 잰다. 전문은 `tests/eval/toolmap/README.md` — 판정 규칙은 **측정 전에** 거기 박혔다.

    docker exec nexus-app python scripts/toolmap_probe.py --build
    docker exec nexus-app python scripts/toolmap_probe.py --run
    docker exec nexus-app python scripts/toolmap_probe.py --drop

LLM 을 부르지 않는다(검색만) — 지출 0.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

DOCS_TENANT = "default"          # 팀이 실제로 묻는 코퍼스
PROBE_TENANT = "tool_probe"      # 도구 지도만 사는 곳. 라이브와 섞지 않는다.
CLEARANCE = "INTERNAL"           # 봇과 같은 등급
HERE = Path(__file__).resolve().parents[1] / "tests" / "eval" / "toolmap"


def _questions() -> list[dict]:
    data = yaml.safe_load((HERE / "questions.yaml").read_text(encoding="utf-8"))
    return data["questions"]


def _tool_of(hit) -> str:
    """지도 문서 → 도구 **이름**.

    ⚠ 첫 판은 `doc_title` 을 그대로 돌려줬다. 제목은 *사람 말*(「지금 무엇이 떠 있나 — 배포
    상태 조회」)이고 기대값은 *도구 이름*(`deploy-status`)이라, **기대값과 산출값이 같아질 수
    없는 비교**였다 — 맞게 고른 질문도 전부 불일치로 찍혔다(2026-08-24 1회차). 신원은 파일명
    에서 온다. **문턱도 기대값도 건드리지 않았다.**
    """
    return (hit.source_uri or "").split(":")[-1].removesuffix(".md")


async def build() -> int:
    """지도를 실험 테넌트에 적재한다. 라이브는 건드리지 않는다."""
    from nexus.ingest.pipeline import run_ingest

    result = await run_ingest(docs_path=str(HERE / "tools"), tenant=PROBE_TENANT,
                              config_path="config.yaml")
    print(f"적재: 문서 {result.indexed} · 실패 {result.failed} · 격리 {result.quarantined}")
    return 0 if result.failed == 0 else 1


async def drop() -> int:
    from nexus import db

    pool = await db.get_pool()
    async with pool.acquire() as con:
        for table in ("chunks", "documents"):
            n = await con.execute(f"DELETE FROM {table} WHERE tenant=$1", PROBE_TENANT)
            print(f"  {table}: {n}")
    await db.close_pool()
    return 0


async def run(top_k: int = 10) -> int:
    """두 다리를 각각 재고, 사전등록된 규칙으로 고른다."""
    from nexus import db
    from nexus.api import _load_config
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.search import hybrid

    svc = embedding_service_from_config()
    cfg = _load_config()
    await db.get_pool()

    rows = []
    for q in _questions():
        arms = {}
        for name, tenant in (("docs", DOCS_TENANT), ("tools", PROBE_TENANT)):
            r = await hybrid.hybrid_search(q["q"], tenant=tenant, clearance=CLEARANCE,
                                           top_k=top_k, embedding_svc=svc, config=cfg)
            if r.degraded:
                print(f"✗ 다리가 죽었다({r.degraded}) — 이 상태의 숫자는 결과가 아니다")
                return 1
            arms[name] = r

        docs_weak = arms["docs"].confidence.weak
        tools_weak = arms["tools"].confidence.weak
        top_hit = arms["tools"].hits[0] if arms["tools"].hits else None

        # 사전등록된 규칙 그대로. 여기서 새 문턱을 만들지 않는다.
        if not docs_weak:
            chose = "docs"
        elif not tools_weak and top_hit:
            chose = f"tool:{_tool_of(top_hit)}"
        else:
            chose = "none"

        ok = chose == q["expect"]
        # 오선택 = 문서가 답해야 하는데 도구를 고른 것. 미선택과 **다르게** 센다.
        misfire = q["expect"] == "docs" and chose.startswith("tool:")
        rows.append({"id": q["id"], "expect": q["expect"], "chose": chose, "ok": ok,
                     "misfire": misfire,
                     "docs": [arms["docs"].confidence.top_distance,
                              arms["docs"].confidence.top_bm25],
                     "tools": [arms["tools"].confidence.top_distance,
                               arms["tools"].confidence.top_bm25]})
        mark = "OK  " if ok else ("✗MIS" if misfire else "    ")
        print(f"{mark} {q['id']:3s} 기대 {q['expect']:22s} 선택 {chose:22s} "
              f"문서(d={_f(arms['docs'].confidence.top_distance)},b={_f(arms['docs'].confidence.top_bm25)}) "
              f"도구(d={_f(arms['tools'].confidence.top_distance)},b={_f(arms['tools'].confidence.top_bm25)})")

    n_ok = sum(r["ok"] for r in rows)
    n_mis = sum(r["misfire"] for r in rows)
    print(f"\n  일치 {n_ok}/{len(rows)}  ·  오선택 {n_mis}  "
          f"(오선택 1건 이상이면 이 형태 그대로는 방아쇠로 못 쓴다 — 사전등록 규칙 1)")
    out = HERE / "result.json"
    out.write_text(json.dumps({"rows": rows, "ok": n_ok, "misfire": n_mis},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"기록: {out}")
    await db.close_pool()
    return 0


def _f(v) -> str:
    return "–" if v is None else f"{v:.3f}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true", help="지도를 실험 테넌트에 적재")
    ap.add_argument("--run", action="store_true", help="판정 (LLM 0회)")
    ap.add_argument("--drop", action="store_true", help="실험 테넌트 삭제")
    ap.add_argument("--top-k", type=int, default=10)
    args = ap.parse_args(argv)

    if args.build:
        return asyncio.run(build())
    if args.drop:
        return asyncio.run(drop())
    if args.run:
        return asyncio.run(run(args.top_k))
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
