"""임베딩 비교 실행 — 적재 → 팔별 임베딩 → 판정 (SPEC-nexus-korean-embedding-comparison).

**세 단계로 나눈 이유는 컨테이너가 다르기 때문이다.** 팩 적재와 키워드 다리는 mecab 이 있는
프로덕션 이미지에서, KURE 임베딩은 torch 가 있는 하니스 이미지에서 돈다. 나눠 두면 각 단계가
자기 전제(mecab / torch / ollama)만 요구한다.

    python -m scripts.ko_eval_embed_compare load                      # nexus 이미지 (mecab)
    python -m scripts.ko_eval_embed_compare embed --model nomic-embed-text   # nexus 이미지 + ollama
    python -m scripts.ko_eval_embed_compare embed --model KURE-v1     # kure 이미지 (torch)
    python -m scripts.ko_eval_embed_compare run --dump-pool p.json    # nexus 이미지
    python -m scripts.ko_eval_embed_compare run --report --adjudicated

`load` 가 만든 청크 위에서만 임베딩이 유효하다 — 다시 적재하면 팔도 다시 만들어야 하고,
`verify_arm` 이 그걸 강제한다(살아 있는 청크 조인 · 개수 · 입력 해시).
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
    leg_top_documents,
    load_pack,
    outcomes,
    render_report,
    run_legs,
    verdict,
)
from scripts.ko_eval_labels import DEFAULT_LABELS, check, load
from scripts.ko_eval_pack import DEFAULT_PACK_DIR
from scripts.ko_eval_pack import verify as verify_pack
from scripts.ko_eval_vector import (
    MODELS,
    ensure_table,
    input_hash,
    replace_arm,
    vector_search,
    verify_arm,
)

TENANT = "ko_eval_embed"
REPORTS_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "reports"


async def _chunk_inputs(con, tenant: str) -> dict[str, str]:
    """`{chunk_rid: 임베딩할 문자열}` — 프로덕션 `get_search_text` 조합 그대로, 한 곳에서만 만든다."""
    from nexus.utils import get_search_text

    class _C:
        def __init__(self, row):
            self.chunk_text = row["chunk_text"]
            self.section_path = row["section_path"]
            self.context_prefix = None

    rows = await con.fetch(
        "SELECT rid, chunk_text, section_path FROM chunks WHERE tenant=$1 ORDER BY rid", tenant)
    return {r["rid"]: get_search_text(_C(r)) for r in rows}


def _make_arm(model: str):
    from scripts.ko_eval_embed import OllamaArm, SentenceTransformerArm

    if model == "nomic-embed-text":
        return OllamaArm()
    if model == "KURE-v1":
        return SentenceTransformerArm()
    raise ValueError(f"알 수 없는 모델: {model} (레지스트리: {sorted(MODELS)})")


async def cmd_load(_args) -> int:
    from nexus import db

    if problems := verify_pack(DEFAULT_PACK_DIR):
        print("✗ 팩 검증 실패:", *problems[:3], sep="\n  ")
        return 1
    pool = await db.get_pool()
    try:
        async with pool.acquire() as con:
            await con.execute("DELETE FROM ko_eval_embeddings WHERE tenant=$1", TENANT)
            await con.execute("DELETE FROM chunks WHERE tenant=$1", TENANT)
            await con.execute("DELETE FROM documents WHERE tenant=$1", TENANT)
            chunk_doc = await load_pack(DEFAULT_PACK_DIR, TENANT, con)
        print(f"적재: 문서 {len(set(chunk_doc.values()))} · 청크 {len(chunk_doc)} (테넌트 {TENANT})")
        print("팔은 이 적재본 위에서만 유효하다 — 다시 적재하면 임베딩도 다시 만들어야 한다.")
        return 0
    finally:
        await db.close_pool()


async def cmd_embed(args) -> int:
    from scripts.ko_eval_embed import embed_pack

    from nexus import db

    labels = load(DEFAULT_LABELS)
    arm = _make_arm(args.model)
    pool = await db.get_pool()
    try:
        async with pool.acquire() as con:
            await ensure_table(con)
            inputs = await _chunk_inputs(con, TENANT)
            if not inputs:
                print(f"✗ 테넌트 {TENANT} 에 청크가 없다 — 먼저 `load` 를 돌려라")
                return 1
            print(f"{args.model}: 청크 {len(inputs)}건 임베딩 중…")
            rows = await embed_pack(arm, inputs)
            await replace_arm(con, args.model, TENANT, labels["pack"], rows)
            problems = await verify_arm(con, args.model, TENANT,
                                        {rid: h for rid, h, _ in rows})
        if problems:
            print("✗ arm 검증 실패:", *[str(p) for p in problems], sep="\n  ")
            return 1
        prov = arm.prov.as_dict()
        (REPORTS_DIR / "arms").mkdir(parents=True, exist_ok=True)
        (REPORTS_DIR / "arms" / f"{args.model}.json").write_text(
            json.dumps(prov, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"✓ {args.model}: {len(rows)}행 · 차원 {prov.get('observed_dim')} · "
              f"최장 입력 {prov.get('max_input_tokens', '?')} 토큰")
        return 0
    finally:
        await db.close_pool()


async def cmd_run(args) -> int:
    from nexus import db

    labels = load(DEFAULT_LABELS)
    if problems := check(labels, DEFAULT_PACK_DIR):
        print("✗ 라벨 게이트 실패:", *problems[:3], sep="\n  ")
        return 1

    pool = await db.get_pool()
    try:
        con = await pool.acquire()
        try:
            inputs = await _chunk_inputs(con, TENANT)
            chunk_doc = {}
            rows = await con.fetch("SELECT rid, source_uri FROM chunks WHERE tenant=$1", TENANT)
            for r in rows:
                chunk_doc[r["rid"]] = r["source_uri"].split(":", 1)[1]

            expected = {rid: input_hash(text) for rid, text in inputs.items()}
            arms = {}
            for model in ("nomic-embed-text", "KURE-v1"):
                problems = await verify_arm(con, model, TENANT, expected)
                if problems:
                    print(f"✗ {model} arm 을 채점할 수 없다:", *[str(p) for p in problems], sep="\n  ")
                    return 1
                arm = _make_arm(model)

                async def _search(query: str, _model=model, _arm=arm):
                    vec = await _arm.embed_query(query)
                    return await vector_search(con, _model, TENANT, vec, top_k=20)

                arms[model] = {"legs": await run_legs(labels, TENANT, chunk_doc, _search),
                               "tops": await leg_top_documents(labels, TENANT, chunk_doc, _search)}
                legs = arms[model]["legs"]
                print(f"{model}: vector Recall@10 {legs['vector'].recall:.3f} · "
                      f"fused {legs['fused'].recall:.3f} · keyword {legs['keyword'].recall:.3f}")

            a, b = arms["KURE-v1"]["legs"], arms["nomic-embed-text"]["legs"]
            v_vec = verdict(*outcomes(a["vector"].scores, b["vector"].scores),
                            name_a="KURE-v1", name_b="nomic-embed-text")
            v_fused = verdict(*outcomes(a["fused"].scores, b["fused"].scores),
                              name_a="KURE-v1", name_b="nomic-embed-text")
            print(f"벡터 판정: {v_vec.decision}")
            print(f"융합 판정: {v_fused.decision}")

            if args.dump_pool:
                _dump_blind_pool(labels, arms, Path(args.dump_pool))

            if args.report:
                _write_report(labels, arms, v_vec, v_fused, args)
            return 0
        finally:
            await pool.release(con)
    finally:
        await db.close_pool()


def _dump_blind_pool(labels: dict, arms: dict, out: Path) -> None:
    """**팔 정보를 지우고 순서를 섞어** 내보낸다 (§4.5).

    판정 대상은 정확히 두 팔을 가르는 문서들이고, 판정자는 어느 모델이 이겨야 하는지에 대한
    가설을 들고 있다. 어느 팔이 올린 후보인지 보이면 그 가설이 gold 에 들어간다.
    """
    import hashlib

    gold = {q["id"]: set(q["gold"]) for q in labels["queries"] if q.get("answerable")}
    payload = []
    for q in labels["queries"]:
        if not q.get("answerable"):
            continue
        cands: set[str] = set()
        for arm in arms.values():
            for leg_tops in arm["tops"].values():
                cands |= set(leg_tops.get(q["id"], []))
        cands -= gold[q["id"]]
        # 결정적 셔플: 질의 id 로 시드해 순서에서 팔을 못 읽게 한다
        ordered = sorted(cands, key=lambda c: hashlib.sha256((q["id"] + c).encode()).hexdigest())
        payload.append({"id": q["id"], "query": q["query"], "stratum": q["stratum"],
                        "gold": q["gold"], "candidates": ordered})
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"풀 후보 {sum(len(p['candidates']) for p in payload)}건 → {out} (팔 정보 제거·셔플)")


def _write_report(labels: dict, arms: dict, v_vec, v_fused, args) -> None:
    strata = {q["id"]: q["stratum"] for q in labels["queries"]}
    provs = {}
    for model in arms:
        f = REPORTS_DIR / "arms" / f"{model}.json"
        provs[model] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}

    meta = {
        "실행 시각": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "팩": labels["pack"],
        "라벨 리비전": labels["revision"],
        "질의": f"답변가능 {arms['KURE-v1']['legs']['vector'].n}",
        "벡터 다리": "정확 스캔 (ko_eval_embeddings, ivfflat 아님 — SPEC §4.2)",
        "융합": "프로덕션 `_rrf_fusion` 그대로 (k=60)",
        "nomic 팔": provs.get("nomic-embed-text", {}),
        "KURE 팔": provs.get("KURE-v1", {}),
        "풀 구성원": "keyword · vector×2 · fused×2 (모든 다리 top-10)",
        "판정(융합)": v_fused.decision,
    }
    legs = [arms["nomic-embed-text"]["legs"]["vector"], arms["KURE-v1"]["legs"]["vector"],
            arms["nomic-embed-text"]["legs"]["fused"], arms["KURE-v1"]["legs"]["fused"]]
    for leg, name in zip(legs, ["vector/nomic", "vector/KURE-v1", "fused/nomic", "fused/KURE-v1"],
                         strict=True):
        leg.leg = name

    report = render_report(meta, legs, strata, v_vec)
    report += (
        "\n> 판정의 결정 다리는 **벡터**다(모델이 바꾸는 다리). 융합은 사용자가 겪는 결과로 함께 적는다.\n"
        "> 벡터에서 유의하고 융합에서 아니면, 결론은 '모델이 바꾸는 다리에서는 우세, 사용자가 보는\n"
        "> 표면에서는 미입증' 두 문장 모두다 (SPEC §4.7).\n"
        "> 이 실행의 벡터 다리는 정확 스캔이라 프로덕션(ivfflat)보다 후하게 나온다 — 절대값이 아니라\n"
        "> 두 모델의 차이를 읽는 자다.\n")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    out = args.out or REPORTS_DIR / f"{datetime.now(timezone.utc):%Y-%m-%d}-nomic-vs-kure.md"
    Path(out).write_text(report, encoding="utf-8", newline="\n")
    print(report)
    print(f"→ {out}")


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description="임베딩 비교 (nomic vs KURE-v1)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("load")
    e = sub.add_parser("embed")
    e.add_argument("--model", required=True, choices=sorted(MODELS))
    r = sub.add_parser("run")
    r.add_argument("--dump-pool", type=Path, default=None)
    r.add_argument("--report", action="store_true")
    r.add_argument("--adjudicated", action="store_true")
    r.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if not os.getenv("DATABASE_URL"):
        print("✗ DATABASE_URL 이 없다")
        return 1
    return asyncio.run({"load": cmd_load, "embed": cmd_embed, "run": cmd_run}[args.cmd](args))


if __name__ == "__main__":
    sys.exit(main())
