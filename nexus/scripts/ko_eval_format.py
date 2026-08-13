"""형식 요청 준수를 잰다 (SPEC-nexus-multi-turn-narration §5, U1).

사용자가 "세 줄로" 라고 했을 때 답이 세 줄인가. 판정은 전부 문자열 연산이고
(`nexus/search/format_compliance.py`) LLM 판정자를 쓰지 않는다 — 판정자가 흔들리면 자가 흔들린다.

**첫 실행은 성능이 아니라 잡음 측정이다** (§5.1). 답변 생성은 LLM 이라 같은 입력에 같은 출력이
안 나온다. 같은 조건 10회를 돌려 폭을 먼저 보고, 그 폭보다 작은 차이는 승리로 세지 않는다.
검색 SPEC 은 5회로 시작했다가 폭을 과소평가했다(5회 0.021 vs 10회 0.061).

    docker exec nexus-app python scripts/ko_eval_format.py --runs 10
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.search.format_compliance import check  # noqa: E402

KO_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "ko"
DEFAULT_CASES = KO_DIR / "format-requests.yaml"


async def answer(query: str, history, *, tenant: str, clearance: str, svc, llm) -> str:
    """오늘의 답변 경로 그대로. **자가 프로덕션 경로를 재구현하지 않는다.**"""
    from nexus.llm.answer import generate_answer
    from nexus.search import hybrid
    from nexus.search.evidence_packet import assemble_packet
    from nexus.search.rewrite import W_ORIGINAL, W_REWRITTEN, rewrite

    rw = await rewrite(query, history, llm)
    channels = None if not rw.changed else [(rw.query, W_REWRITTEN), (query, W_ORIGINAL)]
    r = await hybrid.hybrid_search(rw.query, tenant=tenant, clearance=clearance, top_k=10,
                                   embedding_svc=svc, route="hybrid_only", channels=channels)
    if r.degraded:
        raise SystemExit(f"✗ 다리가 죽었다({r.degraded}) — 이 상태의 숫자는 결과가 아니다")
    result = await generate_answer(rw.query, assemble_packet(r.hits, r.graph), llm_svc=llm)
    if result.llm_failed:
        raise SystemExit(f"✗ LLM 실패({result.llm_failure_reason}) — 이 숫자는 결과가 아니다")
    return result.answer


async def one_run(cases: dict, *, tenant: str, clearance: str, svc, llm) -> dict:
    """한 회차. 형식 준수 여부 + 대조군 답변을 돌려준다."""
    out: dict = {"format": {}, "control": {}}
    for case in cases["cases"]:
        first = await answer(case["first"], [], tenant=tenant, clearance=clearance,
                             svc=svc, llm=llm)
        history = [{"role": "user", "content": case["first"]},
                   {"role": "assistant", "content": first}]
        second = await answer(case["followup"], history, tenant=tenant, clearance=clearance,
                              svc=svc, llm=llm)
        if case.get("control"):
            # 대조군은 형식을 안 잰다. 오늘과 같은 답이 나오는지를 본다 — 길이로 근사한다.
            out["control"][case["id"]] = len(second)
            print(f"  {case['id']:5s} 대조군  {len(second)}자")
        else:
            ok = check(case["check"], second, first)
            out["format"][case["id"]] = ok
            print(f"  {case['id']:5s} {case['check']:16s} {'통과' if ok else '실패'}"
                  f"  ({len(first)}자 → {len(second)}자)")
    return out


async def _run(args) -> int:
    from nexus import db
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.providers.llm import LLMService

    cases = yaml.safe_load(args.cases.read_text(encoding="utf-8"))
    n_fmt = sum(1 for c in cases["cases"] if not c.get("control"))
    print(f"형식 요청 {n_fmt}건 · 대조군 {len(cases['cases']) - n_fmt}건 · {args.runs}회\n")

    svc, llm = embedding_service_from_config(), LLMService()
    runs = []
    try:
        for i in range(args.runs):
            print(f"── run {i + 1}/{args.runs} " + "─" * 40)
            runs.append(await one_run(cases, tenant=args.tenant, clearance=args.clearance,
                                      svc=svc, llm=llm))
    finally:
        await db.close_pool()

    rates = [sum(r["format"].values()) / (n_fmt or 1) for r in runs]
    print(f"\n  형식 준수율  {[f'{x:.2f}' for x in rates]}")
    print(f"  중앙 {statistics.median(rates):.3f} · 최소 {min(rates):.3f} · 최대 {max(rates):.3f}"
          f" · **폭 {max(rates) - min(rates):.3f}**")
    print("\n  이 폭보다 작은 차이는 승리로 세지 않는다 (SPEC §5.1).")

    # 어떤 유형이 지속적으로 실패하는가 — 총점보다 진단적이다.
    print("\n  질의별 통과 횟수")
    for case in cases["cases"]:
        if case.get("control"):
            continue
        hits = sum(1 for r in runs if r["format"].get(case["id"]))
        print(f"    {case['id']:5s} {case['check']:16s} {hits}/{len(runs)}")

    out = args.report or (KO_DIR / "format-compliance.json")
    out.write_text(json.dumps({
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "revision": cases["revision"], "tenant": args.tenant, "runs": args.runs,
        "rates": rates, "spread": max(rates) - min(rates),
        "median": statistics.median(rates), "detail": runs,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n기록: {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--tenant", default="ko_eval_packa")
    ap.add_argument("--clearance", default="INTERNAL")
    ap.add_argument("--runs", type=int, default=10,
                    help="SPEC §5.1: 첫 실행은 성능이 아니라 잡음 측정이다")
    ap.add_argument("--report", type=Path, default=None)
    args = ap.parse_args(argv)
    import os
    if not os.getenv("DATABASE_URL"):
        print("✗ DATABASE_URL 이 없다")
        return 1
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
