"""멀티홉 조립 프로브 — **요구된 사실이 근거 묶음에 도착했는가.** LLM 을 안 부른다.

사전 등록은 `docs/MULTIHOP_ASSEMBLY_PREREGISTRATION.md` 이고 **이 파일보다 먼저 커밋된다.**
여기 있는 것은 그 문서의 §2·§4·§5 를 그대로 옮긴 것이고, 규칙을 고치려면 그 문서를 먼저 고쳐야
한다. 판정 규칙이 코드에만 있으면 결과를 본 뒤에 조용히 바뀐다.

**답이 옳은지를 보지 않는다.** 조립(assembly)과 생성(generation)은 다른 실패이고, 외부 평가의
멀티홉 0/3 은 **조립 2 · 생성 1** 이었다. 이 프로브는 앞의 둘만 본다 — 그래서 생성이 필요 없고,
그래서 결정론이고, 그래서 지출이 0 이다.

    docker exec nexus-app python -m scripts.multihop_assembly_probe \\
        --labels /app/tests/eval/local/policy-multihop-labels.yaml \\
        --control /app/tests/eval/local/policy-labels.yaml \\
        --out /app/tests/eval/local/multihop-assembly.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ko_eval_answer_quality import facts_present  # noqa: E402
from scripts.ko_eval_labels import answerable, load  # noqa: E402

CLEARANCE = "INTERNAL"

#: 사전 등록 §4. `base` 가 맨 앞이어야 한다 — 뒤 실험군들이 그것과 비교된다.
#: `per_doc_cap`/`fill_top_hits` 가 None 이면 배포 설정 그대로.
ARMS: list[tuple[str, dict]] = [
    ("base", {}),
    ("fill-off", {"section_fill": False}),
    ("hits-5", {"fill_top_hits": 5}),
    ("hits-10", {"fill_top_hits": 10}),
    ("cap-3", {"per_doc_cap": 3}),
    ("cap-10", {"per_doc_cap": 10}),
]

#: 사전 등록 §5.5. 근거 문자수 중앙값이 `base` 의 이 배를 넘으면 커버리지와 무관하게 탈락.
#: 근거는 `section_fill.FILL_TOP_HITS` 의 주석이다 — 그 저자가 +102% 를 "그 거래의 값이 아니다"
#: 라고 이미 적었고, 여기 박는 값은 그 절반이다.
COST_CEILING = 1.50


async def assemble(q: dict, tenant: list[str], cfg, svc, search, packet_for_answer,
                   format_for_llm, pool) -> tuple[str, bool, list[bool]]:
    """한 질의의 근거 묶음 텍스트와 요구 성립 여부.

    ⚠ **범위는 목록으로 넘긴다.** 2026-09-02 에 범위가 튜플이 된 뒤 문자열을 넘긴 호출부에서
    절 채움과 짝 확장이 조용히 죽었고, 검사 열셋이 전부 문자열만 넘겨 이틀 동안 초록이었다.
    """
    result = await search(q["query"], tenant=tenant, clearance=CLEARANCE, top_k=10,
                          embedding_svc=svc, config=cfg)
    packet = await packet_for_answer(result, tenant, CLEARANCE, config=cfg, search=search,
                                     embedding_svc=svc, question=q["query"], pool=pool)
    text = format_for_llm(packet)
    present = facts_present(q.get("must_contain"), text)
    return text, bool(present) and all(present), present


async def run_arm(name: str, overrides: dict, groups: dict[str, list[dict]],
                  tenant: list[str]) -> dict:
    """한 실험군을 12질의에 돌린다. 설정은 **이 실행 안에서만** 바뀐다."""
    from nexus import db
    from nexus.api import _load_config
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.search import hybrid, section_fill
    from nexus.search.evidence_packet import format_for_llm
    from nexus.search.reconcile import packet_for_answer

    cfg = _load_config()
    search_cfg = cfg.setdefault("search", {})
    if "section_fill" in overrides:
        search_cfg["section_fill"] = overrides["section_fill"]
    if "per_doc_cap" in overrides:
        search_cfg["diversity_per_doc_cap"] = overrides["per_doc_cap"]

    # 모듈 상수는 설정으로 못 올린다(사전 등록 §4). 실행 중에만 바꾸고 반드시 되돌린다 —
    # 안 되돌리면 다음 실험군이 앞 실험군의 값으로 돈다.
    original_hits = section_fill.FILL_TOP_HITS
    if "fill_top_hits" in overrides:
        section_fill.FILL_TOP_HITS = overrides["fill_top_hits"]
    try:
        svc, pool = embedding_service_from_config(), await db.get_pool()
        rows = []
        for group, queries in groups.items():
            for q in queries:
                text, ok, present = await assemble(
                    q, tenant, cfg, svc, hybrid.hybrid_search, packet_for_answer,
                    format_for_llm, pool)
                rows.append({
                    "group": group, "qid": q["id"], "covered": ok,
                    "requirements": present, "chars": len(text),
                    # 원문은 안 남긴다 — 다른 조직의 정책 본문이다. 결정론 대조군에는 해시면 된다.
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                })
                print(f"  {name:9s} {q['id']:6s} {'✓' if ok else '✗'} "
                      f"{sum(present)}/{len(present)} 요구 · {len(text):6d}자", flush=True)
    finally:
        section_fill.FILL_TOP_HITS = original_hits

    return {"arm": name, "overrides": overrides, "rows": rows, **totals(rows)}


def totals(rows: list[dict]) -> dict:
    """실험군 요약 — 사전 등록 §2 의 세 결과 변수."""
    out: dict = {"median_chars": statistics.median([r["chars"] for r in rows]) if rows else 0}
    for group in sorted({r["group"] for r in rows}):
        sub = [r for r in rows if r["group"] == group]
        out[group] = {"covered": sum(r["covered"] for r in sub), "n": len(sub)}
    return out


def determinism(a: dict, b: dict) -> list[str]:
    """사전 등록 §5.1 — `base` 두 회차가 글자까지 같은가. 다른 질의 id 를 돌려준다."""
    second = {r["qid"]: r["text_sha256"] for r in b["rows"]}
    return [r["qid"] for r in a["rows"] if second.get(r["qid"]) != r["text_sha256"]]


def verdict(arms: list[dict], drift: list[str]) -> dict:
    """사전 등록 §5 를 **순서대로** 적용한다. 규칙은 여기서 고치지 않는다."""
    if drift:
        return {"stopped_at": "§5.1 결정론 대조군",
                "reason": f"base 두 회차가 {len(drift)}질의에서 갈렸다: {', '.join(drift[:6])}",
                "candidates": [], "adopt": None}

    by = {a["arm"]: a for a in arms}
    base, off = by["base"], by.get("fill-off")
    mh, pol = "multihop", "policy"
    if off and off[mh]["covered"] >= base[mh]["covered"]:
        return {"stopped_at": "§5.2 음성 대조군",
                "reason": (f"fill-off 가 base 이상이다 ({off[mh]['covered']} ≥ "
                           f"{base[mh]['covered']}) — 절 채움이 기제가 아니다"),
                "candidates": [], "adopt": None}

    candidates = []
    for a in arms:
        if a["arm"] in ("base", "fill-off"):
            continue
        grew = a["median_chars"] / base["median_chars"] if base["median_chars"] else float("inf")
        if (a[mh]["covered"] > base[mh]["covered"]
                and a[pol]["covered"] >= base[pol]["covered"]
                and grew <= COST_CEILING):
            candidates.append({"arm": a["arm"], "multihop": a[mh]["covered"],
                               "policy": a[pol]["covered"], "cost_ratio": round(grew, 3)})
    candidates.sort(key=lambda c: c["cost_ratio"])
    return {"stopped_at": None, "candidates": candidates,
            "adopt": candidates[0]["arm"] if candidates else None,
            "reason": ("§5.6 — 있는 설정값으로는 조립 실패가 안 사라진다"
                       if not candidates else "§5.4 — 근거 증가가 가장 작은 후보")}


async def _run(args) -> int:
    from nexus import db

    groups = {"multihop": answerable(load(args.labels)),
              "policy": answerable(load(args.control))}
    tenant = [t.strip() for t in args.tenant.split(",") if t.strip()]
    print(f"멀티홉 {len(groups['multihop'])}건 · 정책 {len(groups['policy'])}건 · "
          f"테넌트 {tenant} · LLM 0회\n")

    arms = []
    try:
        for name, overrides in ARMS:
            arms.append(await run_arm(name, overrides, groups, tenant))
        print("\n  결정론 대조군 — base 를 한 번 더\n")
        base_again = await run_arm("base-again", {}, groups, tenant)
    finally:
        await db.close_pool()

    drift = determinism(arms[0], base_again)
    v = verdict(arms, drift)

    print("\n| 실험군 | 멀티홉 | 정책 | 근거 중앙값 | vs base |")
    print("|---|---|---|---|---|")
    base_chars = arms[0]["median_chars"]
    for a in arms:
        ratio = a["median_chars"] / base_chars if base_chars else 0
        print(f"| {a['arm']} | {a['multihop']['covered']}/{a['multihop']['n']} | "
              f"{a['policy']['covered']}/{a['policy']['n']} | {a['median_chars']:.0f} | "
              f"{ratio:+.0%}".replace("+1", "+").rstrip() + " |")
    print(f"\n  결정론 대조군: {'통과' if not drift else '실패 — ' + ', '.join(drift)}")
    print(f"  판정: {v['reason']}")
    if v["candidates"]:
        print(f"  후보: {v['candidates']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "preregistration": "docs/MULTIHOP_ASSEMBLY_PREREGISTRATION.md",
         "tenant": tenant, "clearance": CLEARANCE, "cost_ceiling": COST_CEILING,
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
    p.add_argument("--out", type=Path, required=True,
                   help="결과 파일. 조직 문서의 사실이 요구에 들어 있으므로 gitignore 된 곳에")
    return asyncio.run(_run(p.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
