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


def one_leg_only(holder: dict) -> bool:
    """이 청크가 **한 경로에만** 잡혔는가.

    융합(RRF)은 순위만 쓰므로 두 경로가 합의한 청크가 유리하다. 한 경로에서 8위인 청크가 융합
    뒤 15위로 내려가는 것이 그래서다 — 조립 실패를 '랭킹이 나쁘다' 로 뭉뚱그리면 이 구별이
    사라진다. `SPEC-nexus-bm25-length-normalization` §2 가 같은 기제를 이미 이름 붙여 두었다.
    """
    return (holder.get("bm25_rank") is None) != (holder.get("vector_rank") is None)


async def leg_ranks(query: str, rid: str, tenant: list[str], cfg, svc) -> dict:
    """이 청크가 **각 경로의 후보 풀 안에** 있는가. 융합(RRF)은 순위만 쓴다.

    한 경로에만 있는 청크는 두 경로가 합의한 청크에 밀린다 — 그래서 "경로 하나에서 8위" 가
    "융합 뒤 15위" 가 된다. 이 값이 없으면 조립 실패가 *어느 경로의 문제인지* 못 가른다.
    `SPEC-nexus-bm25-length-normalization` §2 가 같은 기제를 이미 이름 붙여 두었다.
    """
    from nexus.index.vector_index import configured_column
    from nexus.search import hybrid

    s = cfg.get("search") or {}
    bm, _ = await hybrid._bm25_search(query, tenant, "INTERNAL", s.get("bm25_top_k", 20))
    vec, _ = await hybrid._vector_search(query, svc, tenant, "INTERNAL",
                                         s.get("vector_top_k", 20),
                                         column=configured_column(cfg))
    return {"bm25_pool": len(bm), "vector_pool": len(vec),
            "bm25_rank": next((r for x, r in bm if x == rid), None),
            "vector_rank": next((r for x, r in vec if x == rid), None)}


async def explain(q: dict, present: list[bool], tenant: list[str], cfg, svc, search, con) -> dict:
    """이 질의의 요구가 왜 안 왔는가 — **관측만** 한다. 판정도 처방도 없다.

    조립 실패를 "채움 설정값이 낮다" 로 뭉뚱그리면 서로 다른 실패가 한 이름으로 묶인다.
    실측 2026-09-02: 같은 문자열이 빠진 두 질의가 **다른 이유**로 빠졌다 — 하나는 문서가 포화에
    하나 모자랐고(상한을 내리면 들어온다), 다른 하나는 그 문서가 상위 10 에 **둘밖에** 못 올려
    어떤 상한으로도 포화하지 않는다. 처방이 갈리므로 이름도 갈려야 한다.
    """
    missing = [g for g, ok in zip(q.get("must_contain") or [], present) if not ok]
    out: dict = {"qid": q["id"], "missing_groups": len(missing), "holders": []}
    if not missing:
        return out

    from nexus.search import section_fill

    cap = (cfg.get("search") or {}).get("diversity_per_doc_cap", 5)
    result = await search(q["query"], tenant=tenant, clearance="INTERNAL", top_k=10,
                          embedding_svc=svc, config=cfg)
    counts: dict[str, int] = {}
    for h in result.hits:
        counts[h.doc_rid] = counts.get(h.doc_rid, 0) + 1
    sections = {s for _, s in section_fill.hit_sections(result.hits)}

    for group in missing:
        # 요구의 후보 중 **아무거나 하나**를 담은 활성 청크. 후보는 같은 사실의 다른 표기이므로
        # 어느 것이 걸리든 그 사실이 사는 자리는 같다.
        rows = await con.fetch(
            "SELECT c.rid, c.doc_rid, c.section_path, d.title, "
            "       (SELECT count(*) FROM chunks x WHERE x.tenant = c.tenant "
            "          AND x.doc_rid = c.doc_rid AND x.status = 'active' "
            "          AND x.is_quarantined = false) AS doc_chunks "
            "FROM chunks c JOIN documents d ON d.rid = c.doc_rid AND d.tenant = c.tenant "
            "WHERE c.tenant = ANY($1) AND c.status = 'active' AND c.is_quarantined = false "
            "  AND c.chunk_text LIKE ANY($2) LIMIT 4",
            list(tenant), [f"%{alt}%" for alt in group])
        for r in rows:
            hits = counts.get(r["doc_rid"], 0)
            out["holders"].append({
                "requirement": " | ".join(group), "doc": r["title"],
                "doc_hits_in_top10": hits, "cap": cap,
                "saturated": hits >= cap,
                "cap_that_would_saturate": hits if hits else None,
                "doc_chunks": r["doc_chunks"],
                "over_max_doc_chunks": r["doc_chunks"] > section_fill.MAX_DOC_CHUNKS,
                "section_is_a_hit_section": r["section_path"] in sections,
                **await leg_ranks(q["query"], r["rid"], tenant, cfg, svc),
            })
    return out


def cost_delta(arm_chars: float, base_chars: float) -> str:
    """근거 분량의 **변화율**. `base` 는 `+0%`, 3할 줄면 `-29%`.

    첫 판은 비율을 그대로 백분율로 찍었다 — 0.706 이 `+71%` 로, 1.00 이 `+100%` 로 나왔고
    거기에 문자열 치환을 덧대 `+00%` 를 만들고 있었다. 근거가 **3할 줄어든 실험군이 7할
    늘어난 것처럼** 읽혔다. 판정은 원래 값으로 계산하므로 결과는 안 틀렸지만, 사람이 읽는
    표가 반대를 말하면 그 표를 근거로 다음 결정이 난다.
    """
    if not base_chars:
        return "?"
    return f"{arm_chars / base_chars - 1:+.0%}"


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

    # ── 왜 안 왔는가 (관측) ──────────────────────────────────────────────────
    # 판정과 **따로** 돈다. 판정이 §5 에서 멈춰도 이 관측은 남아야 한다 — 멈춘 자리에서 다음
    # 단위를 정하는 재료가 정확히 이것이다.
    explanations = []
    if args.diagnose:
        from nexus.api import _load_config
        from nexus.providers.embedding import embedding_service_from_config
        from nexus.search import hybrid

        cfg, svc = _load_config(), embedding_service_from_config()
        pool = await db.get_pool()
        try:
            async with pool.acquire() as con:
                by_qid = {r["qid"]: r for r in arms[0]["rows"]}
                for q in groups["multihop"]:
                    row = by_qid.get(q["id"])
                    if row and not row["covered"]:
                        explanations.append(await explain(
                            q, row["requirements"], tenant, cfg, svc,
                            hybrid.hybrid_search, con))
        finally:
            await db.close_pool()

    print("\n| 실험군 | 멀티홉 | 정책 | 근거 중앙값 | vs base |")
    print("|---|---|---|---|---|")
    base_chars = arms[0]["median_chars"]
    for a in arms:
        print(f"| {a['arm']} | {a['multihop']['covered']}/{a['multihop']['n']} | "
              f"{a['policy']['covered']}/{a['policy']['n']} | {a['median_chars']:.0f} | "
              f"{cost_delta(a['median_chars'], base_chars)} |")
    print(f"\n  결정론 대조군: {'통과' if not drift else '실패 — ' + ', '.join(drift)}")
    for e in explanations:
        print(f"\n  {e['qid']} 가 못 받은 요구 {e['missing_groups']}건 — 왜:")
        for h in e["holders"]:
            print(f"    그 사실은 「{h['doc']}」 에 있고, 상위 10 에 이 문서의 히트는 "
                  f"{h['doc_hits_in_top10']}개다 (상한 {h['cap']} · 포화 "
                  f"{'예' if h['saturated'] else '아니오'})")
            print(f"      문서 청크 {h['doc_chunks']}"
                  + (" — MAX_DOC_CHUNKS 초과라 문서 채움이 통째로 건너뛴다"
                     if h["over_max_doc_chunks"] else "")
                  + " · 그 절이 상위 히트의 절인가: "
                  + ("예" if h["section_is_a_hit_section"] else "아니오"))
            print(f"      경로별 후보 풀 — BM25 {h['bm25_rank'] or '밖'}/{h['bm25_pool']} · "
                  f"벡터 {h['vector_rank'] or '밖'}/{h['vector_pool']}"
                  + ("  ⇒ **한 경로에만 있다** — 융합이 두 경로 합의를 이기지 못한다"
                     if one_leg_only(h) else ""))
    print(f"  판정: {v['reason']}")
    if v["candidates"]:
        print(f"  후보: {v['candidates']}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "preregistration": "docs/MULTIHOP_ASSEMBLY_PREREGISTRATION.md",
         "tenant": tenant, "clearance": CLEARANCE, "cost_ceiling": COST_CEILING,
         "determinism_drift": drift, "verdict": v,
         "why_uncovered": explanations, "arms": arms},
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
    # 관측이지 판정이 아니다 — 그래서 사전 등록 §5 와 무관하게 켜고 끌 수 있고, 판정이 §5 에서
    # 멈춰도 이 관측은 남는다. 멈춘 자리에서 다음 단위를 정하는 재료가 정확히 이것이다.
    p.add_argument("--diagnose", action="store_true",
                   help="못 받은 요구마다 **왜** 안 왔는지 관측한다 — 그 사실이 어느 문서에 "
                        "있고, 그 문서가 상위 10 에 몇 개를 올렸고, 포화·절 조건에 걸리는가")
    p.add_argument("--out", type=Path, required=True,
                   help="결과 파일. 조직 문서의 사실이 요구에 들어 있으므로 gitignore 된 곳에")
    return asyncio.run(_run(p.parse_args(argv)))


if __name__ == "__main__":
    sys.exit(main())
