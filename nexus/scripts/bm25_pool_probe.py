"""BM25 후보 풀 크기 — 사전 등록된 측정. LLM 을 안 부른다.

규칙은 `docs/BM25_POOL_PREREGISTRATION.md` 이고 **이 파일보다 먼저 커밋된다.** 여기 있는 것은
그 문서 §2·§4·§5 를 옮긴 것이고, 규칙을 고치려면 그 문서를 먼저 고쳐야 한다.

앞 판(`multihop_assembly_probe.py`)과 갈리는 곳 둘:

  · **기제를 직접 관측한다.** 앞 판의 음성 대조군은 *동률*을 "기제가 아니다" 로 읽었는데, 동률은
    *안 돎*과 *돌지만 쓸모없음*을 한꺼번에 뜻했다. 여기서는 정답 청크가 그 실험군에서 **BM25 풀에
    실제로 들어왔는가**를 본다.
  · **지연을 측정한다.** 그 축은 결정론이 아니므로 질의당 여러 회차를 돌리고, **문턱을 ms 로 미리
    박지 않는다** — 잡음 폭을 같은 실행에서 만든다(`base` vs `base-again`).

    docker exec nexus-app python -m scripts.bm25_pool_probe \\
        --labels /app/tests/eval/local/policy-multihop-labels.yaml \\
        --control /app/tests/eval/local/policy-labels.yaml \\
        --out /app/tests/eval/local/bm25-pool.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ko_eval_answer_quality import facts_present  # noqa: E402
from scripts.ko_eval_labels import answerable, load  # noqa: E402

CLEARANCE = "INTERNAL"

#: 사전 등록 §4. `base` 가 맨 앞이어야 한다 — 나머지가 그것과 비교된다.
#: `vector_top_k` 는 건드리지 않는다: 둘을 같이 올리면 어느 쪽이 값을 냈는지 못 가른다.
ARMS: list[tuple[str, int]] = [("base", 20), ("pool-25", 25), ("pool-30", 30), ("pool-40", 40)]

#: 사전 등록 §3. 지연은 결정론이 아니라 반복이 필요하다. 10 의 근거는 검정력이 아니라 **비용이
#: 제약이 아니라는 것**이다 — 12질의 × 10회 × 실험군 = 몇 분이고 LLM 이 없어 지출이 0 이다.
LATENCY_REPEATS = 10

#: 사전 등록 §5.4·§5.5. 앞 사전 등록과 **같은 값**이다 — 측정마다 상한이 달라지면 상한이 아니다.
COST_CEILING = 1.50


def cost_delta(arm_value: float, base_value: float) -> str:
    """변화율. `base` 는 `+0%`, 3할 줄면 `-29%`. (앞 판에서 비율을 그대로 찍어 표가 반대를 말했다.)"""
    if not base_value:
        return "?"
    return f"{arm_value / base_value - 1:+.0%}"


def verdict(arms: list[dict], drift: list[str], noise_band: float) -> dict:
    """사전 등록 §5 를 **순서대로**. 규칙은 여기서 고치지 않는다."""
    if drift:
        return {"stopped_at": "§5.1 결정론 대조군", "candidates": [], "adopt": None,
                "reason": f"base 두 회차가 {len(drift)}질의에서 갈렸다: {', '.join(drift[:6])}"}

    base = arms[0]
    candidates, noted = [], []
    for a in arms[1:]:
        if a["multihop"]["covered"] <= base["multihop"]["covered"]:
            continue
        if a["policy"]["covered"] < base["policy"]["covered"]:
            continue
        # §5.2 기제 대조군 — 좋아졌는데 청크가 풀에 안 들어왔으면 값이 다른 데서 온 것이다.
        if not a.get("chunk_entered_pool"):
            noted.append(a["arm"])
            continue
        grew = a["median_chars"] / base["median_chars"] if base["median_chars"] else float("inf")
        slower = a["median_ms"] / base["median_ms"] if base["median_ms"] else float("inf")
        if grew > COST_CEILING or slower > COST_CEILING:
            continue
        candidates.append({
            "arm": a["arm"], "bm25_top_k": a["bm25_top_k"],
            "multihop": a["multihop"]["covered"], "policy": a["policy"]["covered"],
            "chars_ratio": round(grew, 3), "latency_ratio": round(slower, 3),
            # 잡음 폭 안이면 대가라고 부르지 않는다(§5.5).
            "latency_is_measurable": abs(a["median_ms"] - base["median_ms"]) > noise_band,
        })
    # §5.6 — 풀 증가가 가장 작은 것. 커버리지도 근거 분량도 아니다(이유는 사전 등록 §0).
    candidates.sort(key=lambda c: c["bm25_top_k"])
    return {"stopped_at": None, "candidates": candidates,
            "improved_without_the_mechanism": noted,
            "adopt": candidates[0]["arm"] if candidates else None,
            "reason": ("§5.7 — 풀을 키워도 조립 실패가 안 사라진다" if not candidates
                       else "§5.6 — 풀 증가가 가장 작은 후보")}


def determinism(a: dict, b: dict) -> list[str]:
    """§5.1 — `base` 두 회차가 글자까지 같은가."""
    second = {r["qid"]: r["text_sha256"] for r in b["rows"]}
    return [r["qid"] for r in a["rows"] if second.get(r["qid"]) != r["text_sha256"]]


def totals(rows: list[dict]) -> dict:
    out: dict = {
        "median_chars": statistics.median([r["chars"] for r in rows]) if rows else 0,
        "median_ms": statistics.median([r["median_ms"] for r in rows]) if rows else 0,
    }
    for group in sorted({r["group"] for r in rows}):
        sub = [r for r in rows if r["group"] == group]
        out[group] = {"covered": sum(r["covered"] for r in sub), "n": len(sub)}
    return out


async def run_arm(name: str, pool: int, groups: dict[str, list[dict]], tenant: list[str],
                  holder_rid: str | None, repeats: int) -> dict:
    from nexus import db
    from nexus.api import _load_config
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.search import hybrid
    from nexus.search.evidence_packet import format_for_llm
    from nexus.search.reconcile import packet_for_answer

    cfg = _load_config()
    cfg.setdefault("search", {})["bm25_top_k"] = pool
    svc, conn_pool = embedding_service_from_config(), await db.get_pool()
    rows, entered = [], False

    for group, queries in groups.items():
        for q in queries:
            # ⚠ 범위는 **목록**으로 넘긴다 — 2026-09-02 에 문자열을 넘긴 호출부에서 절 채움과
            # 짝 확장이 조용히 죽었고 검사 열셋이 전부 초록이었다.
            timings = []
            for _ in range(repeats):
                t0 = time.perf_counter()
                result = await hybrid.hybrid_search(q["query"], tenant=tenant,
                                                    clearance=CLEARANCE, top_k=10,
                                                    embedding_svc=svc, config=cfg)
                timings.append((time.perf_counter() - t0) * 1000)
            packet = await packet_for_answer(result, tenant, CLEARANCE, config=cfg,
                                             search=hybrid.hybrid_search, embedding_svc=svc,
                                             question=q["query"], pool=conn_pool)
            text = format_for_llm(packet)
            present = facts_present(q.get("must_contain"), text)

            # §5.2 기제 관측 — 정답 청크가 **이 실험군의 BM25 풀에** 들어왔는가.
            if holder_rid and group == "multihop":
                bm, _ = await hybrid._bm25_search(q["query"], tenant, CLEARANCE, pool)
                if any(x == holder_rid for x, _ in bm):
                    entered = True

            rows.append({
                "group": group, "qid": q["id"],
                "covered": bool(present) and all(present), "requirements": present,
                "chars": len(text), "median_ms": statistics.median(timings),
                # 원문은 안 남긴다 — 다른 조직의 정책 본문이다.
                "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            })
            print(f"  {name:9s} {q['id']:6s} {'✓' if rows[-1]['covered'] else '✗'} "
                  f"{sum(present)}/{len(present)} 요구 · {len(text):6d}자 · "
                  f"{rows[-1]['median_ms']:6.1f}ms", flush=True)

    return {"arm": name, "bm25_top_k": pool, "chunk_entered_pool": entered,
            "rows": rows, **totals(rows)}


async def _run(args) -> int:
    from nexus import db

    groups = {"multihop": answerable(load(args.labels)),
              "policy": answerable(load(args.control))}
    tenant = [t.strip() for t in args.tenant.split(",") if t.strip()]

    conn = await db.get_pool()
    async with conn.acquire() as con:
        holder = await con.fetchrow(
            "SELECT c.rid FROM chunks c WHERE c.tenant = ANY($1) AND c.status = 'active' "
            "  AND c.is_quarantined = false AND c.chunk_text LIKE $2 LIMIT 1",
            tenant, f"%{args.fact}%") if args.fact else None
    holder_rid = holder["rid"] if holder else None
    print(f"멀티홉 {len(groups['multihop'])}건 · 정책 {len(groups['policy'])}건 · 테넌트 {tenant}")
    print(f"기제 관측 대상 청크: {'있음' if holder_rid else '없음(--fact 를 주면 켜진다)'} · "
          f"지연 반복 {args.repeats}회 · LLM 0회\n")

    arms = []
    try:
        for name, pool in ARMS:
            arms.append(await run_arm(name, pool, groups, tenant, holder_rid, args.repeats))
        print("\n  결정론·잡음 대조군 — base 를 한 번 더\n")
        again = await run_arm("base-again", ARMS[0][1], groups, tenant, holder_rid, args.repeats)
    finally:
        await db.close_pool()

    drift = determinism(arms[0], again)
    noise_band = abs(arms[0]["median_ms"] - again["median_ms"])
    v = verdict(arms, drift, noise_band)

    print("\n| 실험군 | pool | 멀티홉 | 정책 | 풀 진입 | 근거 중앙값 | vs base | 지연 | vs base |")
    print("|---|---|---|---|---|---|---|---|---|")
    b = arms[0]
    for a in arms:
        print(f"| {a['arm']} | {a['bm25_top_k']} | {a['multihop']['covered']}/{a['multihop']['n']}"
              f" | {a['policy']['covered']}/{a['policy']['n']}"
              f" | {'예' if a['chunk_entered_pool'] else '아니오'} | {a['median_chars']:.0f}"
              f" | {cost_delta(a['median_chars'], b['median_chars'])}"
              f" | {a['median_ms']:.0f}ms | {cost_delta(a['median_ms'], b['median_ms'])} |")
    print(f"\n  결정론 대조군: {'통과' if not drift else '실패 — ' + ', '.join(drift)}")
    print(f"  지연 잡음 폭(base vs base-again): {noise_band:.1f}ms "
          f"— 이보다 작은 차이는 대가라고 부르지 않는다")
    print(f"  판정: {v['reason']}")
    if v.get("improved_without_the_mechanism"):
        print(f"  ⚠ 좋아졌는데 청크가 풀에 안 들어온 실험군: {v['improved_without_the_mechanism']}"
              " — 값이 다른 데서 왔고 이 사전 등록은 그것을 설명하지 못한다")
    if v["candidates"]:
        print(f"  후보: {v['candidates']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "preregistration": "docs/BM25_POOL_PREREGISTRATION.md",
         "tenant": tenant, "clearance": CLEARANCE, "repeats": args.repeats,
         "cost_ceiling": COST_CEILING, "latency_noise_band_ms": noise_band,
         "determinism_drift": drift, "verdict": v, "arms": arms},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n기록: {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--labels", type=Path, required=True, help="멀티홉 라벨 (처치군)")
    p.add_argument("--control", type=Path, required=True, help="단일홉 라벨 (회귀 검사)")
    p.add_argument("--tenant", default="default", help="쉼표로 여러 개")
    # 기제 관측 대상. 조직 문서의 값이라 리포에 못 적는다 — 실행할 때 준다.
    p.add_argument("--fact", default="", help="정답 청크를 찾을 문자열 (기제 대조군을 켠다)")
    p.add_argument("--repeats", type=int, default=LATENCY_REPEATS, help="질의당 지연 반복")
    p.add_argument("--out", type=Path, required=True, help="결과 파일. gitignore 된 곳에")
    return asyncio.run(_run(p.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
