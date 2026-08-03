"""mecab-ko vs nori — 같은 엔진·같은 인덱스 구조·같은 스코러·같은 품사 정책으로
(SPEC-nexus-korean-retrieval-eval §4.3~§4.5).

두 팔은 **각자의 토크나이저로 색인하고 각자의 토크나이저로 질의한다.** 한 실행 안에서 한 번만
갈아끼우므로 색인/질의가 어긋날 수 없다. 어긋난 실행은 그럴듯한 숫자를 내고 아무 의미도 없다.

    python -m scripts.ko_eval_compare --dump-pool pool.json       # 풀 후보 덤프(판정 전)
    python -m scripts.ko_eval_compare --report                    # 리포트 작성

풀 판정(§4.2)은 이 스크립트가 대신해 주지 않는다. 후보를 덤프하면 사람이 읽고 gold 에 추가한다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.ko_eval_harness import (
    METRIC_K,
    LegResult,
    collapse_to_documents,
    load_pack,
    outcomes,
    render_report,
    score_query,
    verdict,
)
from scripts.ko_eval_labels import DEFAULT_LABELS, check, load
from scripts.ko_eval_nori import DEFAULT_URL, NoriTokenizer
from scripts.ko_eval_pack import DEFAULT_PACK_DIR
from scripts.ko_eval_pack import verify as verify_pack

REPORTS_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "reports"
POOL_DEPTH = METRIC_K       # 풀 깊이 = 지표 깊이. 얕으면 6~10위가 무판정으로 비관련 처리된다.


async def run_arm(tokenizer, labels: dict, pool, tenant: str) -> tuple[LegResult, dict[str, list[str]]]:
    """한 팔: 팩 적재(그 토크나이저로) → 질의(같은 토크나이저로) → 점수 + 질의별 상위 문서."""
    from nexus.index.bm25 import use_tokenizer
    from nexus.search import hybrid

    with use_tokenizer(tokenizer):
        async with pool.acquire() as con:
            await con.execute("DELETE FROM chunks WHERE tenant=$1", tenant)
            await con.execute("DELETE FROM documents WHERE tenant=$1", tenant)
            chunk_doc = await load_pack(DEFAULT_PACK_DIR, tenant, con)

        leg, tops = LegResult(leg=f"keyword/{tokenizer.id}"), {}
        for q in labels["queries"]:
            if not q.get("answerable"):
                continue
            hits = await hybrid._bm25_search(q["query"], tenant, "INTERNAL", 20)
            docs = collapse_to_documents(hits, chunk_doc, limit=POOL_DEPTH)
            tops[q["id"]] = docs
            leg.scores.append(score_query(q["id"], docs, q["gold"]))
    return leg, tops


async def _run(args) -> int:
    from nexus import db
    from nexus.index.bm25 import MecabTokenizer, _get_mecab

    if problems := verify_pack(DEFAULT_PACK_DIR):
        print("✗ 팩 검증 실패:", *problems[:5], sep="\n  ")
        return 1
    labels = load(DEFAULT_LABELS)
    if problems := check(labels, DEFAULT_PACK_DIR):
        print("✗ 라벨 게이트 실패 — 측정 이전에 자가 틀렸다:", *problems[:5], sep="\n  ")
        return 1
    if _get_mecab() is None:
        print("✗ mecab-ko 없음 — 이미지 안에서 실행하라")
        return 1

    mecab, nori = MecabTokenizer(), NoriTokenizer(args.nori_url)
    engine = nori.health()
    print(f"nori: {engine}")

    pool = await db.get_pool()
    try:
        # **두 팔은 같은 테넌트를 순서대로 쓴다.** rid 가 테넌트를 품고 있어서, 테넌트가 다르면
        # 동점 정렬 키(rid)도 달라진다 — 토크나이저와 무관한 차이가 승패에 섞인다.
        arm_tenant = "ko_eval_arm"
        mecab_leg, mecab_tops = await run_arm(mecab, labels, pool, arm_tenant)
        print(f"mecab: Recall@10 {mecab_leg.recall:.3f} · MRR {mecab_leg.mrr:.3f} · 미스 {mecab_leg.misses}")
        nori_leg, nori_tops = await run_arm(nori, labels, pool, arm_tenant)
        print(f"nori : Recall@10 {nori_leg.recall:.3f} · MRR {nori_leg.mrr:.3f} · 미스 {nori_leg.misses}")

        wins, losses, ties = outcomes(nori_leg.scores, mecab_leg.scores)
        v = verdict(wins, losses, ties, name_a="nori", name_b="mecab-ko")
        print(f"승패(nori 기준): {wins}승 {losses}패 {ties}무 → {v.decision}")

        gold = {q["id"]: set(q["gold"]) for q in labels["queries"] if q.get("answerable")}
        pooled = {qid: sorted(set(mecab_tops.get(qid, [])) | set(nori_tops.get(qid, [])) - gold[qid])
                  for qid in gold}
        unjudged = sum(len(v_) for v_ in pooled.values())

        if args.dump_pool:
            payload = [{"id": q["id"], "query": q["query"], "stratum": q["stratum"],
                        "gold": q["gold"],
                        "mecab_top": mecab_tops.get(q["id"], []), "nori_top": nori_tops.get(q["id"], []),
                        "candidates": pooled[q["id"]]}
                       for q in labels["queries"] if q.get("answerable")]
            Path(args.dump_pool).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                                            encoding="utf-8", newline="\n")
            print(f"풀 후보 {unjudged}건 → {args.dump_pool}")

        if args.report:
            strata = {q["id"]: q["stratum"] for q in labels["queries"]}
            meta = {
                "실행 시각": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                "팩": labels["pack"],
                "라벨 리비전": labels["revision"],
                "질의": f"답변가능 {mecab_leg.n} · 답변불가 "
                        f"{sum(1 for q in labels['queries'] if not q['answerable'])}(집계 제외)",
                "엔진": "Postgres to_tsquery + ts_rank_cd (양 팔 동일)",
                "nori 분석기": f"{engine}, decompound_mode={nori.decompound_mode}, user_dictionary=none",
                "mecab 정책": mecab.policy,
                "nori 정책": nori.policy,
                "allow-list 밖 nori 태그": dict(sorted(nori.unknown_tags.items(),
                                                      key=lambda kv: -kv[1])[:8]) or "없음",
                "풀 구성원": "mecab-ko, nori (둘 다 top-10)",
                "미판정 후보": (f"{unjudged}건 — 판정 전에는 비관련으로 세어진다"
                             if args.dump_pool or not args.adjudicated else "판정 완료"),
            }
            report = render_report(meta, [mecab_leg, nori_leg], strata, v)
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            out = args.out or REPORTS_DIR / f"{datetime.now(timezone.utc):%Y-%m-%d}-mecab-vs-nori.md"
            Path(out).write_text(report, encoding="utf-8", newline="\n")
            print(report)
            print(f"→ {out}")

        if not args.keep:
            async with pool.acquire() as con:
                await con.execute("DELETE FROM chunks WHERE tenant=$1", arm_tenant)
                await con.execute("DELETE FROM documents WHERE tenant=$1", arm_tenant)
        return 0
    finally:
        await db.close_pool()


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="mecab vs nori — 같은 엔진에서")
    ap.add_argument("--nori-url", default=os.getenv("NORI_URL", DEFAULT_URL))
    ap.add_argument("--dump-pool", type=Path, default=None)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--adjudicated", action="store_true", help="풀 판정이 끝난 라벨로 도는 실행")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args(argv)
    if not os.getenv("DATABASE_URL"):
        print("✗ DATABASE_URL 이 없다")
        return 1
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
