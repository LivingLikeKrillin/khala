"""임베딩 비교 실행 — 적재 → 팔별 임베딩 → 판정 (SPEC-nexus-korean-embedding-comparison).

**세 단계로 나눈 이유는 컨테이너가 다르기 때문이다.** 팩 적재와 키워드 다리는 mecab 이 있는
프로덕션 이미지에서, KURE 임베딩은 torch 가 있는 하니스 이미지에서 돈다. 나눠 두면 각 단계가
자기 전제(mecab / torch / ollama)만 요구한다.

    python -m scripts.ko_eval_embed_compare load                      # nexus 이미지 (mecab)
    python -m scripts.ko_eval_embed_compare embed --model nomic-embed-text   # nexus 이미지 + ollama
    python -m scripts.ko_eval_embed_compare embed --model KURE-v1     # kure 이미지 (torch)
    python -m scripts.ko_eval_embed_compare embed-queries --model ...  # 실험군이 있는 이미지에서
    python -m scripts.ko_eval_embed_compare run --dump-pool p.json    # nexus 이미지 (모델 불필요)
    python -m scripts.ko_eval_embed_compare run --report --adjudicated

`load` 가 만든 청크 위에서만 임베딩이 유효하다 — 다시 적재하면 실험군도 다시 만들어야 하고,
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
    arms_saw_the_same_inputs,
    coverage,
    ensure_table,
    refused_chunks,
    replace_arm,
    sha256,
    vector_search,
    verify_arm,
)

TENANT = "ko_eval_embed"
REPORTS_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "reports"
QUERY_VECTORS = Path(__file__).resolve().parents[1] / "tests" / "eval" / "query-vectors"


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
        print("실험군은 이 적재본 위에서만 유효하다 — 다시 적재하면 임베딩도 다시 만들어야 한다.")
        return 0
    finally:
        await db.close_pool()


async def cmd_restore_chunks(_args) -> int:
    """청크/문서만 다시 적재한다 — **임베딩 저장소는 보존**한다.

    `clean_db` 가 `chunks`/`documents` 를 TRUNCATE 하면 `ko_eval_embeddings` 는 살아남되 참조가
    끊긴 고아가 된다. `load` 는 이 상황의 도구가 아니다 — 저장소부터 지우기 때문에, 조인 테이블을
    복구하려다 몇 시간짜리 임베딩을 버리게 된다.

    복구가 옳았는지는 rid 집합이 아니라 **내용**이 정한다: 팩이 다른 커밋으로 드리프트하면 파일
    동일성이 유지되는 한 rid 는 그대로이고 본문만 달라진다. 그래서 `verify_arm` 을 그대로 불러
    `input_sha256` / `payload_sha256` 까지 대조하고, 어긋나면 되돌리지 않고 거부한다.
    """
    from nexus import db

    if problems := verify_pack(DEFAULT_PACK_DIR):
        print("✗ 팩 검증 실패:", *problems[:3], sep="\n  ")
        return 1

    pool = await db.get_pool()
    try:
        async with pool.acquire() as con:
            store = {r["chunk_rid"] for r in await con.fetch(
                "SELECT DISTINCT chunk_rid FROM ko_eval_embeddings WHERE tenant=$1", TENANT)}
            if not store:
                print("✗ 보존할 임베딩이 없다 — 복구가 아니라 최초 적재다. `load` 를 써라.")
                return 1
            print(f"보존 대상 임베딩 청크: {len(store)}건")

            await con.execute("DELETE FROM chunks WHERE tenant=$1", TENANT)
            await con.execute("DELETE FROM documents WHERE tenant=$1", TENANT)
            chunk_doc = await load_pack(DEFAULT_PACK_DIR, TENANT, con)
            print(f"재적재: 문서 {len(set(chunk_doc.values()))} · 청크 {len(chunk_doc)}")

            missing, extra = store - set(chunk_doc), set(chunk_doc) - store
            if missing or extra:
                print(f"✗ rid 집합 불일치 — 저장소에만 {len(missing)}건, 재적재본에만 {len(extra)}건. "
                      "이 저장소는 이 팩의 것이 아니다.")
                return 1

            labels = load(DEFAULT_LABELS)
            inputs = await _chunk_inputs(con, TENANT)
            failed = False
            for model in MODELS:
                expected = {rid: (sha256(text), sha256(MODELS[model]["document_prefix"] + text))
                            for rid, text in inputs.items()}
                if problems := await verify_arm(con, model, TENANT, labels["pack"], expected):
                    failed = True
                    print(f"✗ {model}:", *[str(p) for p in problems], sep="\n  ")
            if failed:
                print("✗ rid 는 맞지만 내용이 어긋난다 — 팩이 드리프트했다. 저장소를 신뢰하지 마라.")
                return 1
            print("✓ rid 집합과 입력 해시가 모두 일치한다 — 저장소는 이 적재본의 것이다.")
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
            cov = await replace_arm(con, args.model, TENANT, labels["pack"], rows)
            problems = await verify_arm(
                con, args.model, TENANT, labels["pack"],
                {r.chunk_rid: (r.input_sha256, r.payload_sha256) for r in rows})
        if problems:
            print("✗ arm 검증 실패:", *[str(p) for p in problems], sep="\n  ")
            return 1
        prov = arm.prov.as_dict()
        (REPORTS_DIR / "arms").mkdir(parents=True, exist_ok=True)
        (REPORTS_DIR / "arms" / f"{args.model}.json").write_text(
            json.dumps(prov, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print(f"✓ {args.model}: 커버리지 {cov} · 차원 {prov.get('observed_dim')}")
        if cov.refused:
            example = next(r.refusal_reason for r in rows if r.refusal_reason)
            print(f"  거부 {cov.refused}건 — 백엔드 메시지: {example}")
        return 0
    finally:
        await db.close_pool()


async def cmd_embed_queries(args) -> int:
    """질의를 이 실험군로 임베딩해 파일로 남긴다 — 채점기가 모델 없이 돌 수 있게."""
    labels = load(DEFAULT_LABELS)
    arm = _make_arm(args.model)
    payload = {}
    for q in labels["queries"]:
        if not q.get("answerable"):
            continue
        prefixed = arm.prefixed(q["query"], "query")
        payload[q["id"]] = {
            "query": q["query"],                       # 프리픽스 이전 — 실험군 간 동일해야 한다
            "payload_sha256": sha256(prefixed),        # 이 실험군이 실제 보낸 것
            "vector": await arm.embed_query(q["query"]),
        }
    QUERY_VECTORS.mkdir(parents=True, exist_ok=True)
    out = QUERY_VECTORS / f"{args.model}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"✓ {args.model}: 질의 {len(payload)}건 → {out}")
    return 0


def _load_query_vectors(model: str) -> dict:
    f = QUERY_VECTORS / f"{model}.json"
    if not f.exists():
        raise SystemExit(f"✗ 질의 벡터가 없다: {f} — 먼저 `embed-queries --model {model}` 를 돌려라")
    return json.loads(f.read_text(encoding="utf-8"))


def _queries_match_across_arms(per_model: dict) -> list[str]:
    """두 실험군이 **같은 질의 텍스트**를 봤는지 (§4.3). 프리픽스는 달라도 원문은 같아야 한다."""
    models = sorted(per_model)
    problems = []
    for other in models[1:]:
        a = {qid: v["query"] for qid, v in per_model[models[0]].items()}
        b = {qid: v["query"] for qid, v in per_model[other].items()}
        if a != b:
            problems.append(f"{models[0]} 과 {other} 가 다른 질의를 임베딩했다")
    return problems


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

            pack = labels["pack"]
            if diffs := await arms_saw_the_same_inputs(con, TENANT, pack):
                print("✗ 두 실험군이 다른 입력을 봤다 — 모델 비교가 아니다:")
                for d in diffs:
                    print(f"  {d}")
                return 1

            arms, query_vectors = {}, {}
            for model in ("nomic-embed-text", "KURE-v1"):
                expected = {rid: (sha256(text),
                                  sha256(MODELS[model]["document_prefix"] + text))
                            for rid, text in inputs.items()}
                cov = await coverage(con, model, TENANT, pack)
                print(f"커버리지 — {cov}")
                problems = await verify_arm(con, model, TENANT, pack, expected)
                if problems:
                    print(f"✗ {model} arm 을 채점할 수 없다:", *[str(p) for p in problems], sep="\n  ")
                    return 1
                qvecs = _load_query_vectors(model)
                query_vectors[model] = qvecs
                by_text = {v["query"]: v["vector"] for v in qvecs.values()}

                async def _search(query: str, _model=model, _pack=pack, _by_text=by_text):
                    if query not in _by_text:
                        raise SystemExit(f"✗ 질의 벡터 없음({_model}): {query!r} — 라벨이 바뀌었으면 "
                                         "`embed-queries` 를 다시 돌려라")
                    return await vector_search(con, _model, TENANT, _pack, _by_text[query], top_k=20)

                arms[model] = {"legs": await run_legs(labels, TENANT, chunk_doc, _search),
                               "tops": await leg_top_documents(labels, TENANT, chunk_doc, _search)}
                legs = arms[model]["legs"]
                print(f"{model}: vector Recall@10 {legs['vector'].recall:.3f} · "
                      f"fused {legs['fused'].recall:.3f} · keyword {legs['keyword'].recall:.3f}")

            # 비교가능 부분집합 (§4.7) — nomic 이 못 먹은 청크를 가진 gold 문서가 하나라도
            # 걸린 질의는 빼고 본다. 그러지 않으면 창 크기를 모델 품질이라고 부르게 된다.
            narrowed = await _narrowed_documents(con, TENANT, pack, chunk_doc)
            comparable = [q["id"] for q in labels["queries"]
                          if q.get("answerable") and not (set(q["gold"]) & narrowed)]
            print(f"비교가능 부분집합: {len(comparable)}/{arms['KURE-v1']['legs']['vector'].n} 질의 "
                  f"(창에 걸린 gold 문서 {len(narrowed)}건 제외)")

            if diffs := _queries_match_across_arms(query_vectors):
                print("✗ 팔들이 다른 질의를 봤다:")
                for d in diffs:
                    print(f"  {d}")
                return 1

            a, b = arms["KURE-v1"]["legs"], arms["nomic-embed-text"]["legs"]

            def _subset(scores):
                return [s for s in scores if s.qid in comparable]

            v_conf = verdict(*outcomes(_subset(a["vector"].scores), _subset(b["vector"].scores)),
                             name_a="KURE-v1", name_b="nomic-embed-text")
            v_vec = verdict(*outcomes(a["vector"].scores, b["vector"].scores),
                            name_a="KURE-v1", name_b="nomic-embed-text")
            v_fused = verdict(*outcomes(a["fused"].scores, b["fused"].scores),
                              name_a="KURE-v1", name_b="nomic-embed-text")
            print(f"확증(비교가능 부분집합·벡터): {v_conf.decision}")
            print(f"기술(전체 질의·벡터): {v_vec.decision}")
            print(f"기술(전체 질의·융합): {v_fused.decision}")

            if args.dump_pool:
                _dump_blind_pool(labels, arms, Path(args.dump_pool))

            if args.report:
                _write_report(labels, arms, v_conf, v_vec, v_fused, comparable, args,
                              covs={m: await coverage(con, m, TENANT, pack) for m in arms})
            return 0
        finally:
            await pool.release(con)
    finally:
        await db.close_pool()


async def _narrowed_documents(con, tenant: str, pack: str,
                              chunk_doc: dict[str, str]) -> set[str]:
    """어느 한 팔이라도 거부한 청크를 가진 문서들 — 이 문서가 gold 인 질의는 비교가능하지 않다."""
    narrowed: set[str] = set()
    for model in MODELS:
        for rid in await refused_chunks(con, model, tenant, pack):
            if rid in chunk_doc:
                narrowed.add(chunk_doc[rid])
    return narrowed


def _dump_blind_pool(labels: dict, arms: dict, out: Path) -> None:
    """**실험군 정보를 지우고 순서를 섞어** 내보낸다 (§4.5).

    판정 대상은 정확히 두 실험군을 가르는 문서들이고, 판정자는 어느 모델이 이겨야 하는지에 대한
    가설을 들고 있다. 어느 실험군이 올린 후보인지 보이면 그 가설이 gold 에 들어간다.
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
        # 결정적 셔플: 질의 id 로 시드해 순서에서 실험군을 못 읽게 한다
        ordered = sorted(cands, key=lambda c: hashlib.sha256((q["id"] + c).encode()).hexdigest())
        payload.append({"id": q["id"], "query": q["query"], "stratum": q["stratum"],
                        "gold": q["gold"], "candidates": ordered})
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"풀 후보 {sum(len(p['candidates']) for p in payload)}건 → {out} (실험군 정보 제거·셔플)")


def _write_report(labels: dict, arms: dict, v_conf, v_vec, v_fused, comparable, args,
                  covs: dict) -> None:
    strata = {q["id"]: q["stratum"] for q in labels["queries"]}
    provs = {}
    for model in arms:
        f = REPORTS_DIR / "arms" / f"{model}.json"
        provs[model] = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}

    meta = {
        "커버리지 (판정보다 먼저 읽는다)": " · ".join(str(c) for c in covs.values()),
        "실행 시각": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "팩": labels["pack"],
        "라벨 리비전": labels["revision"],
        "질의": f"답변가능 {arms['KURE-v1']['legs']['vector'].n}",
        "벡터 다리": "정확 스캔 (ko_eval_embeddings, ivfflat 아님 — SPEC §4.2)",
        "융합": "프로덕션 `_rrf_fusion` 그대로 (k=60)",
        "nomic 실험군": provs.get("nomic-embed-text", {}),
        "KURE 실험군": provs.get("KURE-v1", {}),
        "풀 구성원": "keyword/mecab · keyword/nori · vector×2 · fused×2 (모든 다리 top-10)",
        "확증 분석": f"비교가능 부분집합 {len(comparable)}/{arms['KURE-v1']['legs']['vector'].n}질의 (벡터 다리)",
        "수치의 성격": "**전부 하한(lower bound)** — 풀 판정 보류, 미판정 문서는 비관련으로 세어진다",
        "기술 분석": "전체 답변가능 질의 (벡터·융합)",
    }
    legs = [arms["nomic-embed-text"]["legs"]["vector"], arms["KURE-v1"]["legs"]["vector"],
            arms["nomic-embed-text"]["legs"]["fused"], arms["KURE-v1"]["legs"]["fused"]]
    for leg, name in zip(legs, ["vector/nomic", "vector/KURE-v1", "fused/nomic", "fused/KURE-v1"],
                         strict=True):
        leg.leg = name

    report = render_report(meta, legs, strata, v_conf)
    tail = [
        "",
        "## 기술 분석 (α 를 쓰지 않는다)",
        "",
        f"- 전체 질의·벡터: {v_vec.decision}",
        f"- 전체 질의·융합: {v_fused.decision}",
        "",
        "> 위 '판정' 은 **비교가능 부분집합**의 확증 결과다(벡터 다리). 전체 질의 분석은",
        "> 커버리지 격차를 포함한 사용자 관점의 기술이며, 모델 품질 주장으로 인용해서는 안 된다.",
        "> 벡터 다리는 정확 스캔이라 프로덕션(ivfflat)보다 후하게 나온다 — 절대값이 아니라 두",
        "> 모델의 차이를 읽는 자다. 그리고 Pack A 는 khala 자신의 코퍼스가 아니다 (SPEC §4.7).",
        "> **모든 수치는 하한이다** — 풀 판정을 보류했으므로 미판정 문서가 비관련으로 세어진다.",
        "> 그 페널티는 새 문서를 더 많이 건져 올린 실험군이 더 많이 받는다: 결론 방향에 보수적이다.",
        "> 이 실행의 결과는 **교체를 허가하지 않는다** — 정확 스캔이라 프로덕션(ivfflat)을 예측하지",
        "> 못하고, 차원 변경(768→1024)이 ANN 거동을 또 바꾼다. 교체 SPEC 이 자기 측정을 져야 한다.",
        "",
    ]
    report += "\n".join(tail) + "\n"
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
    sub.add_parser("restore-chunks")
    e = sub.add_parser("embed")
    e.add_argument("--model", required=True, choices=sorted(MODELS))
    eq = sub.add_parser("embed-queries")
    eq.add_argument("--model", required=True, choices=sorted(MODELS))
    r = sub.add_parser("run")
    r.add_argument("--dump-pool", type=Path, default=None)
    r.add_argument("--report", action="store_true")
    r.add_argument("--adjudicated", action="store_true")
    r.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if not os.getenv("DATABASE_URL"):
        print("✗ DATABASE_URL 이 없다")
        return 1
    handlers = {"load": cmd_load, "restore-chunks": cmd_restore_chunks, "embed": cmd_embed,
                "embed-queries": cmd_embed_queries, "run": cmd_run}
    return asyncio.run(handlers[args.cmd](args))


if __name__ == "__main__":
    sys.exit(main())
