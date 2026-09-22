"""사전 등록 §4 부 변수 1 — **회귀**. `default`·`design_docs` 의 기존 라벨 집합.

`PROCEDURE_RETRIEVAL_PREREGISTRATION.md` §5.2 는 *"회귀 변수가 하나라도 떨어지면 기각"* 이라
했다. 주 변수는 소비자(설명 층)가 자기 골든셋으로 측정했고 이쪽 라벨은 그들이 못 돌린다 —
그래서 판정의 나머지 절반이 이 파일이다.

⛔ **판정 규칙을 결과를 보기 전에 적는다.** 아래 두 줄이 이 실행의 사전 등록이다.

1. **회귀 변수 = 골든 문서가 상위 k 에 오는가**(문서 단위). 실험군별로 센다. LLM 을 안 부른다 —
   처치는 검색만 건드리고, 답변 층은 검색이 준 것 위에서만 움직인다.
2. **검색 출력이 두 실험군에서 글자 그대로 같으면 답변 층을 안 돌린다.** 같은 조각이 같은
   순서로 오면 답변 점수가 움직일 자리는 브리지 잡음뿐이고, 그 잡음을 처치의 효과로 적는
   것이 이 리포가 막으려는 바로 그것이다. **하나라도 다르면 그 라벨만 답변까지 돌린다.**

⭐ **음성 대조군을 같이 낸다**(§5.5). 「차이 없음」은 *처치가 무해했다* 와 *스위치가 조용히
무시됐다* 를 구별하지 못한다. 그래서 질의마다 **채널이 무엇으로 발화했는가**를 같이 적는다.

⛔ **채널을 손으로 조립하지 않는다.** 두 실험군 다 `api._search_channels` 를 지난다 — 라이브
요청이 지나는 그 함수다. 여기서 베끼면 이 평가 하니스는 **아무도 안 지나는 경로**를 측정한다
(이 리포가 2026-08-29 에 실제로 그랬다). 두 실험군의 차이는 그 함수의 인자 하나뿐이다.

    docker exec nexus-app python -m scripts.identifier_channel_regression_probe
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from scripts.ko_eval_labels import expired  # noqa: E402
from scripts.ko_eval_packb import MANIFEST, tenant_bodies  # noqa: E402

LOCAL_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "local"
REPORT = LOCAL_DIR / "identifier-channel-regression.json"
#: 이 처치의 소비자가 아닌 코퍼스. 회귀가 보이는 자리는 여기다.
SCOPE = {"default", "design_docs"}


def label_files() -> list[Path]:
    """`corpus.tenant` 로 **자기 코퍼스를 선언한** 라벨만. 기본값으로 고르지 않는다.

    ⛔ 말없이 고른 `default` 가 2026-09-05 사고의 재료였다(`ko_eval_corpus_reach` 머리말).
    선언이 없는 파일은 이 실행의 대상이 아니고, 그 사실을 리포트에 적는다.
    """
    out = []
    for p in sorted(LOCAL_DIR.glob("*.yaml")):
        try:
            d = yaml.safe_load(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(d, dict) or not d.get("queries"):
            continue
        raw = ((d.get("corpus") or {}).get("tenant") or "").strip()
        if raw and {t.strip() for t in raw.split(",") if t.strip()} <= SCOPE:
            out.append(p)
    return out


async def _run(args) -> int:
    from nexus import db
    from nexus.api import _search_channels
    from nexus.cli import _load_config
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.search import hybrid

    titles = {d["key"]: d["title"]
              for d in json.loads(MANIFEST.read_text(encoding="utf-8"))["docs"]}
    svc, cfg = embedding_service_from_config(), _load_config()
    pool = await db.get_pool()

    files = label_files()
    if not files:
        print("⛔ 코퍼스를 선언한 라벨이 없다 — 측정할 것이 없다")
        return 2
    print(f"라벨 파일 {len(files)}건 · top-k {args.top_k} · LLM 미사용\n")

    report: dict = {"ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "top_k": args.top_k, "files": []}
    fired_total = differed_total = 0
    try:
        for path in files:
            labels = yaml.safe_load(path.read_text(encoding="utf-8"))
            scope = [t.strip() for t in labels["corpus"]["tenant"].split(",") if t.strip()]
            queries = [q for q in labels["queries"] if q.get("answerable", True)]
            # **서명된 본문이 움직였으면 절대 점수를 안 찍는다.** 실험군 비교는 같은 날
            # 같은 코퍼스라 그대로 서지만, 만료된 라벨의 총점은 성적이 아니다.
            stale: dict = {}
            if (labels.get("corpus") or {}).get("bodies"):
                async with pool.acquire() as con:
                    live = {k: v["sha"] for k, v in (await tenant_bodies(con, scope[0])).items()}
                stale = expired(labels, live)
            gold_ok = all(g in titles for q in queries for g in (q.get("gold") or []))

            rows = []
            for q in queries:
                ns = SimpleNamespace(query=q["query"], history=None)
                arms, elapsed = {}, {}
                for arm, ident in (("T0", False), ("T2", True)):
                    sq, channels, _ = await _search_channels(ns, None, identifiers=ident)
                    t0 = time.perf_counter()
                    r = await hybrid.hybrid_search(
                        sq, tenant=scope, clearance="INTERNAL", top_k=args.top_k,
                        embedding_svc=svc, config=cfg, channels=channels,
                        # ⛔ **결과 객체가 「켰는가」를 들고 다녀야 한다.** 여기서 안 넘기면
                        # 「켰는데 발화 안 함」이 「안 켰음」으로 기록되고, §5.5 의 두 칸이
                        # 한 칸으로 뭉친다 — 2026-09-20 첫 판이 실제로 그랬다.
                        identifier_channel_asked=ident)
                    elapsed[arm] = (time.perf_counter() - t0) * 1000
                    if r.degraded:
                        print(f"✗ 경로가 죽었다({r.degraded}) — 이 상태의 숫자는 결과가 아니다")
                        return 1
                    arms[arm] = r
                same = [h.rid for h in arms["T0"].hits] == [h.rid for h in arms["T2"].hits]
                fired = arms["T2"].identifier_channel
                fired_total += bool(fired)
                differed_total += (not same)

                row = {"qid": q["id"], "file": path.name, "same_hits": same,
                       "fired": list(fired), "asked": arms["T2"].identifier_channel_asked,
                       "ms_T0": round(elapsed["T0"], 1), "ms_T2": round(elapsed["T2"], 1)}
                if q.get("gold") and gold_ok:
                    want = {titles[g] for g in q["gold"]}
                    for arm in ("T0", "T2"):
                        row[f"rank_{arm}"] = next(
                            (i + 1 for i, h in enumerate(arms[arm].hits) if h.doc_title in want),
                            None)
                rows.append(row)
                mark = "=" if same else "!"
                rk = (f"  골든 {row.get('rank_T0') or '-'}→{row.get('rank_T2') or '-'}"
                      if "rank_T0" in row else "")
                fire_txt = "+".join(fired) or "없음"
                print(f"{mark} {q['id']:16s} 발화 {fire_txt:22s}{rk}")

            scored = [r for r in rows if "rank_T0" in r]
            summary = {"file": path.name, "tenant": scope, "queries": len(rows),
                       "identical_hits": sum(1 for r in rows if r["same_hits"]),
                       "fired": sum(1 for r in rows if r["fired"]),
                       "expired": sorted(stale), "gold_keys_resolved": gold_ok,
                       "rows": rows}
            if scored and not stale:
                for arm in ("T0", "T2"):
                    hit = [r for r in scored if r[f"rank_{arm}"]]
                    summary[f"recall_{arm}"] = len(hit) / len(scored)
                    summary[f"hits_{arm}"] = f"{len(hit)}/{len(scored)}"
                    summary[f"mrr_{arm}"] = sum(1 / r[f"rank_{arm}"] for r in hit) / len(scored)
            report["files"].append(summary)

            head = f"\n  {path.name}  질의 {len(rows)}  동일 {summary['identical_hits']}"
            if "recall_T0" in summary:
                print(f"{head}  Recall@{args.top_k} "
                      f"T0 {summary['hits_T0']} = {summary['recall_T0']:.3f} · "
                      f"T2 {summary['hits_T2']} = {summary['recall_T2']:.3f}\n")
            elif stale:
                print(f"{head}  ✗ 만료 {len(stale)}건 — 총점 없음\n")
            else:
                print(f"{head}  (골든 없음 — 출력 동일성만)\n")
    finally:
        await db.close_pool()

    total = sum(f["queries"] for f in report["files"])
    rows = [r for f in report["files"] for r in f["rows"]]
    asked = sum(1 for r in rows if r["asked"])
    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else 0.0  # noqa: E731
    report["totals"] = {"queries": total, "asked": asked, "fired": fired_total,
                        "differed": differed_total,
                        "median_ms_T0": med([r["ms_T0"] for r in rows]),
                        "median_ms_T2": med([r["ms_T2"] for r in rows])}
    print(f"전체 {total}건 · 요청 {asked}건 · 식별자 채널 발화 {fired_total}건 · "
          f"검색 출력이 갈린 질의 {differed_total}건")
    print(f"  검색 구간 중앙값  T0 {report['totals']['median_ms_T0']:.0f}ms · "
          f"T2 {report['totals']['median_ms_T2']:.0f}ms")
    # ⛔ **한 번도 요청이 안 갔으면 이 실행은 음성 대조군이 아니다.** 「발화 0」이 처치가
    # 발화할 자리가 없어서인지 스위치가 안 닿아서인지 구별되지 않는다.
    if asked != total:
        print(f"  ⛔ T2 실험군이 {total - asked}건에서 처치를 **요청하지 않았다** — "
              "이 판은 §5.5 를 못 채운다")
        return 1
    if differed_total:
        print("  ⇒ 갈린 라벨은 답변 층까지 돌려야 한다 (머리말 사전 등록 2).")
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"  리포트: {REPORT}")
    return 0


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-k", type=int, default=10)
    return asyncio.run(_run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
