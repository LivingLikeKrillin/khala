"""멀티턴 검색 평가 하니스 — 후속 질문이 검색을 어디서 잃는지 측정한다 (SPEC-nexus-multi-turn-retrieval §3.4).

**절대점수를 측정하지 않는다.** 두 코퍼스가 답변 품질 천장에 닿았으므로(memory:
khala-answer-quality-harness) 그 수는 아무것도 말하지 않는다. 여기서 측정하는 것은 **같은 정보
요구의 두 표현 사이 격차**이고, 상한은 라벨의 원 질의가 이미 정해 준다.

실험군 넷을 항상 같이 돌린다:

    standalone     라벨의 원 질의 그대로        — 대조군·상한 (이 실행이 믿을 만한가)
    elliptical     같은 요구의 2턴째 말투        — 오늘의 서버가 실제로 받는 것
    concat         turn1 + turn2 를 그냥 붙임    — LLM 없이 공짜로 되는 싸구려 하한
    drift_concat   앞에 다른 화제 한 턴 + 위     — 그 하한이 무너지는 조건 (판정 실험군)

**LLM 을 부르지 않는다.** 검색만 본다 — 문서 단위 Recall@10 과 MRR. 그래서 돈이 안 들고,
결정적이며(2회 실행 바이트 동일), 답변 품질 평가 하니스의 천장에 걸리지 않는다.

    docker exec nexus-app python scripts/ko_eval_multiturn.py --tenant ko_eval_packa
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.llm.dev_spend import Spend, paid_flag_help, require_free  # noqa: E402
from nexus.search.rewrite import W_ORIGINAL, W_REWRITTEN, rewrite  # noqa: E402
from scripts.ko_eval_labels import ManifestPack, check, expired, load  # noqa: E402
from scripts.ko_eval_packb import tenant_bodies  # noqa: E402

KO_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "ko"
DEFAULT_THREADS = KO_DIR / "multiturn-threads.yaml"
DEFAULT_LABELS = KO_DIR / "answer-labels.yaml"
DEFAULT_MANIFEST = KO_DIR / "answer-manifest.json"

#: 실험군 이름 → 사람이 읽는 이름. 순서가 곧 보고 순서다.
ARMS = {
    "standalone": "독립형(대조군·상한)",
    "elliptical": "생략형(오늘의 서버)",
    "concat": "두 턴 이어붙임(싸구려 하한)",
    "drift_concat": "앞 화제 깔린 이어붙임(판정 실험군)",
}

#: 재작성 실험군은 **옵트인**이다(`--rewrite`). LLM 을 부르므로 돈이 들고, 같은 입력에 같은 출력이
#: 안 나온다 — 그래서 SPEC §5.1 은 U3 의 **첫 실행을 성능이 아니라 잡음 측정**으로 못박았다.
REWRITE_ARMS = {
    "rewritten": "재작성 단독",
    "rewritten_fused": "재작성+원문 가중융합(U3)",
}


def doc_key(source_uri: str) -> str:
    """`git://repo:path` → `path`. 실행기(`ko_eval_answer_run.py`)와 같은 규칙."""
    parts = source_uri.split(":")
    return parts[1] if len(parts) > 1 else source_uri


def arm_queries(thread: dict, query: str, drift: str) -> dict[str, str]:
    """이 스레드에 대한 팔별 검색어. **한 곳에서만 조립한다** — 실험군 정의가 갈라지면 비교가 아니다."""
    t1, t2 = thread["turn1"], thread["turn2"]
    return {
        "standalone": query,
        "elliptical": t2,
        "concat": f"{t1} {t2}",
        "drift_concat": f"{drift} {t1} {t2}",
    }


def gate_reasons(threads: dict, labels: dict) -> list[str]:
    """스레드 파일이 자기 라벨과 맞물리는가. 비어 있어야 실행이 결과가 된다.

    관문이 뒤에 있으면 숫자를 보고 평가 하니스를 고치게 된다(`ko_eval_answer_run.py` 와 같은 이유).
    """
    reasons: list[str] = []
    by_id = {q["id"]: q for q in labels.get("queries") or []}
    if threads.get("labels_revision") != labels.get("revision"):
        reasons.append(
            f"스레드는 라벨 revision {threads.get('labels_revision')} 에 지어졌는데 "
            f"라벨은 revision {labels.get('revision')} 이다 — gold 가 그 사이 바뀌었을 수 있다")
    seen: set[str] = set()
    for t in threads.get("threads") or []:
        qid = t.get("qid")
        if qid in seen:
            reasons.append(f"{qid}: 스레드가 중복이다")
        seen.add(qid)
        q = by_id.get(qid)
        if q is None:
            reasons.append(f"{qid}: 라벨에 없는 qid")
            continue
        if not q.get("answerable"):
            reasons.append(f"{qid}: 답변불가 질의에는 후속 질문을 달 수 없다")
        if not q.get("gold"):
            reasons.append(f"{qid}: gold 가 없다 — 채점할 것이 없다")
        for field in ("turn1", "turn2"):
            if not (t.get(field) or "").strip():
                reasons.append(f"{qid}: {field} 가 비었다")
    if not threads.get("drift_turn", "").strip():
        reasons.append("drift_turn 이 비었다 — 판정 실험군이 사라진다")
    return reasons


async def run_arm(query: str, gold: set[str], svc, *, tenant: str, clearance: str,
                  route: str, top_k: int, channels=None) -> tuple[int, int | None]:
    """(gold 적중 문서 수, 첫 gold 의 문서 순위 | None).

    **순위까지 측정하는 이유**: Recall@10 은 굵은 자다. gold 를 10위 안에 붙들어 두면서 9위로
    밀어냈다면 Recall 로는 무승부지만 근거 패킷은 순위로 잘린다.
    """
    from nexus.search import hybrid

    r = await hybrid.hybrid_search(query, tenant=tenant, clearance=clearance,
                                   top_k=top_k, embedding_svc=svc, route=route,
                                   channels=channels)
    if r.degraded:
        raise SystemExit(f"✗ 경로가 죽었다({r.degraded}) — 이 상태의 숫자는 결과가 아니다")
    seen: list[str] = []
    for h in r.hits:
        k = doc_key(h.source_uri)
        if k not in seen:
            seen.append(k)
    first = next((i + 1 for i, k in enumerate(seen) if k in gold), None)
    return len(gold & set(seen)), first


def arms_present(rows: list[dict]) -> dict[str, str]:
    """이 실행에 실제로 있는 실험군만 집계·보고한다 — 없는 실험군을 0 으로 채우면 거짓 수가 된다."""
    out = dict(ARMS)
    for arm, name in REWRITE_ARMS.items():
        if rows and arm in rows[0]:
            out[arm] = name
    return out


def summarise(rows: list[dict]) -> dict:
    """팔별 (gold 를 하나라도 올린 질의 수, MRR).

    MRR 은 **못 찾은 질의를 0 으로 넣어** 평균 낸다. 찾은 것만 평균 내면 적게 찾을수록 좋아 보인다.
    """
    n = len(rows) or 1
    out = {}
    for arm in arms_present(rows):
        found = sum(1 for r in rows if r[arm]["hits"] > 0)
        mrr = sum(1 / r[arm]["rank"] if r[arm]["rank"] else 0.0 for r in rows) / n
        out[arm] = {"found": found, "mrr": round(mrr, 3)}
    return out


def control_failures(summary: dict, baseline: dict, n: int) -> list[str]:
    """**독립형 실험군이 이 실행의 대조군이다.** 상한을 재현 못 하면 다른 숫자는 결과가 아니다.

    계측기를 먼저 의심하라 — 이 리포는 계측기가 틀린 숫자를 의사결정 근거로 올린 적이 여러 번
    있다(memory: suspect-the-instrument-first). 실험군 넷은 LLM 이 없어 결정적이므로, 독립형이
    베이스라인과 다르면 코퍼스·임베딩 세대·등급 중 하나가 달라진 것이다.
    """
    want = (baseline or {}).get("standalone") or {}
    got = summary["standalone"]
    bad = []
    if want.get("found") is not None and got["found"] != want["found"]:
        bad.append(f"독립형 적중 {got['found']}/{n} — 베이스라인은 {want['found']}")
    if want.get("mrr") is not None and abs(got["mrr"] - want["mrr"]) > 0.001:
        bad.append(f"독립형 MRR {got['mrr']} — 베이스라인은 {want['mrr']}")
    return bad


async def _run(args) -> int:
    from nexus import db
    from nexus.providers.embedding import embedding_service_from_config

    threads = yaml.safe_load(args.threads.read_text(encoding="utf-8"))
    labels = load(args.labels)

    # ── 관문 1: 라벨이 자기 코퍼스에 대해 성립하는가 ────────────────────────────
    if problems := check(labels, ManifestPack(args.manifest), require_corpus_binding=True):
        print("✗ 라벨 게이트 실패 — 측정 이전에 평가 하니스가 틀렸다:", *problems[:4], sep="\n  ")
        return 1
    # ── 관문 2: 스레드가 그 라벨과 맞물리는가 ──────────────────────────────────
    if problems := gate_reasons(threads, labels):
        print("✗ 스레드 게이트 실패:", *problems[:6], sep="\n  ")
        return 1

    signed_tenant = (labels.get("corpus") or {}).get("tenant")
    if signed_tenant != args.tenant:
        print(f"✗ 라벨은 테넌트 {signed_tenant!r} 에 서명됐는데 측정하는 것은 {args.tenant!r} 이다")
        return 1

    by_id = {q["id"]: q for q in labels["queries"]}
    drift = threads["drift_turn"]
    llm, spend = None, Spend()
    if args.rewrite:
        from nexus.providers.llm import LLMService
        llm = LLMService()
        # 유료 백엔드면 여기서 멈춘다 — 잊는 쪽이 비싸다 (nexus/llm/dev_spend.py).
        require_free(llm, allow_paid=args.paid, what="재작성 실험군")
        print("  재작성 실험군 켬 — LLM 호출이 스레드당 1회 붙는다")
    base = threads.get("baseline") or {}
    svc = embedding_service_from_config()
    rows: list[dict] = []

    try:
        pool = await db.get_pool()
        async with pool.acquire() as con:
            live = await tenant_bodies(con, args.tenant)
        # 라벨이 서명된 본문과 지금 측정하는 본문이 같은가. 다르면 그 질의의 gold 는 사라진
        # 텍스트에 대한 주장이다.
        if stale := expired(labels, {k: v["sha"] for k, v in live.items()}):
            print(f"✗ 만료된 라벨 {len(stale)}건 — 사람이 다시 읽고 서명해야 한다: "
                  f"{', '.join(sorted(stale)[:8])}")
            return 1

        for t in threads["threads"][:args.limit]:
            q = by_id[t["qid"]]
            gold = set(q["gold"])
            row: dict = {"qid": t["qid"], "n_gold": len(gold),
                         "turn1": t["turn1"], "turn2": t["turn2"]}
            for arm, text in arm_queries(t, q["query"], drift).items():
                hits, rank = await run_arm(text, gold, svc, tenant=args.tenant,
                                           clearance=args.clearance, route=args.route,
                                           top_k=args.top_k)
                row[arm] = {"hits": hits, "rank": rank}

            if llm is not None:
                # **판정 조건은 흘러간 스레드다** (SPEC §5.2): 앞 화제 한 턴이 깔린 이력에서
                # 재작성이 싸구려 하한(이어붙임)을 이기는가. 붙어 있는 스레드는 공짜 해법이
                # 이미 잘하는 조건이라 변별력이 없다.
                history = [{"role": "user", "content": drift},
                           {"role": "assistant", "content": "네, 도움이 됐다니 다행입니다."},
                           {"role": "user", "content": t["turn1"]},
                           {"role": "assistant", "content": "네, 그 부분을 설명드렸습니다."}]
                rw = await rewrite(t["turn2"], history, llm)
                spend.add(rw.usage, kind="rewrite")
                rq = rw.query
                row["rewritten_query"] = rq
                hits, rank = await run_arm(rq, gold, svc, tenant=args.tenant,
                                           clearance=args.clearance, route=args.route,
                                           top_k=args.top_k)
                row["rewritten"] = {"hits": hits, "rank": rank}
                # U3 그대로: 재작성 + 원문 두 채널. 재작성이 원문과 같으면 채널을 늘리지
                # 않는다 — 같은 문자열은 순서를 안 바꾸고 점수만 팽창시킨다 (§3.3).
                ch = None if rq == t["turn2"] else [(rq, W_REWRITTEN), (t["turn2"], W_ORIGINAL)]
                hits, rank = await run_arm(rq, gold, svc, tenant=args.tenant,
                                           clearance=args.clearance, route=args.route,
                                           top_k=args.top_k, channels=ch)
                row["rewritten_fused"] = {"hits": hits, "rank": rank}
            rows.append(row)
            print("  ".join([f"{t['qid']:6s}"] + [
                f"{a[:2]}{row[a]['hits']}/{len(gold)}@{row[a]['rank'] or '-'}" for a in ARMS]))
    finally:
        await db.close_pool()

    n = len(rows)
    summary = summarise(rows)
    #: 부분 실행은 대조군을 판정할 수 없다 — 베이스라인은 24건 전체에 대한 수다. 그것을 5건과
    #: 비교하면 멀쩡한 디버깅 실행이 매번 "대조군 실패" 로 찍히고, 곧 아무도 그 경고를 안 읽는다.
    #: 대신 **총점이라고 부르지 않는다**: 배너와 리포트의 `partial` 이 그 자리를 대신한다.
    partial = n != len(threads["threads"])

    # ── 대조군은 총점보다 **먼저** 판정한다 ────────────────────────────────────
    if partial:
        print(f"\n⚠ 부분 실행({n}/{len(threads['threads'])}건) — **대조군을 판정할 수 없다.**")
        print("  아래 수는 진단 재료이지 이 평가 하니스의 값이 아니다. 값을 얻으려면 --limit 없이 돌려라.")
    elif failures := control_failures(summary, base, n):
        print("\n✗ **대조군이 베이스라인을 재현하지 못했다** — 이 실행의 숫자는 결과가 아니다.")
        for f in failures:
            print(f"    {f}")
        print("  실험군 넷은 LLM 이 없어 결정적이다. 그러니 달라진 것은 시스템이 아니라 조건이다:")
        print("  코퍼스 적재본 · 임베딩 세대(nexus generation show) · clearance 를 먼저 보라.")
        return 1

    print(f"\n  (n={n})                             gold 올림   MRR(문서)")
    for arm, name in arms_present(rows).items():
        s = summary[arm]
        print(f"    {name:32s} {s['found']:2d}/{n}      {s['mrr']:.3f}")
    gap = summary["standalone"]["found"] - summary["elliptical"]["found"]
    print(f"\n  결함 = {gap}/{n} (독립형 − 생략형) — 멀티턴 배관이 되찾을 몫의 상한")
    print(f"  이어붙임이 남긴 몫 = {summary['standalone']['found'] - summary['concat']['found']}/{n}"
          f" · 앞 화제가 깔리면 "
          f"{summary['standalone']['found'] - summary['drift_concat']['found']}/{n}")
    if gap <= 0:
        print("  ‼ 격차가 없다. 이 코퍼스에서 멀티턴 배관은 얻을 것이 없다.")

    out = args.report or (KO_DIR / "multiturn-retrieval.json")
    out.write_text(json.dumps({
        "ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "threads_revision": threads["revision"], "labels_revision": labels["revision"],
        "tenant": args.tenant, "clearance": args.clearance, "route": args.route,
        "top_k": args.top_k, "drift_turn": drift, "partial": partial,
        "summary": summary, "spend": spend.as_dict(), "queries": rows,
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if args.rewrite:
        print(f"\n  {spend.summary()}")
    print(f"\n기록: {out}  (공개 코퍼스 위의 결과 — 커밋 가능)")
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--threads", type=Path, default=DEFAULT_THREADS)
    ap.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--tenant", default="ko_eval_packa",
                    help="측정하는 테넌트(라벨의 서명 테넌트와 같아야 한다)")
    ap.add_argument("--clearance", default="INTERNAL")
    ap.add_argument("--route", default="hybrid_only")
    ap.add_argument("--top-k", type=int, default=10, dest="top_k")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--paid", action="store_true", help=paid_flag_help())
    ap.add_argument("--rewrite", action="store_true",
                    help="재작성 실험군을 켠다 (LLM 호출·비용). SPEC §5.1: 첫 실행은 성능이 아니라 "
                         "잡음 측정이다 — 같은 조건 5회를 돌려 폭을 먼저 보고하라")
    args = ap.parse_args(argv)
    import os
    if not os.getenv("DATABASE_URL"):
        print("✗ DATABASE_URL 이 없다")
        return 1
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
