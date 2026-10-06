"""사전 등록 F1 부 변수 1 — **회귀**. `default`·`design_docs` 의 기존 라벨 집합(T2 회귀와 같은 80건).

`docs/FUSION_DOCUMENT_AGREEMENT_PREREGISTRATION.md` §3·§4 는 *"회귀 변수가 하나라도 떨어지면 기각"*
이라 했다. 주 변수는 소비자가 자기 골든셋으로 측정하고 이쪽 라벨은 그들이 못 돌린다 — 판정의 나머지
절반이 이 파일이다.

⛔ **판정 규칙을 결과를 보기 전에 적는다.** 아래가 이 실행의 사전 등록이다(2026-10-01, 첫 실행 전).

1. **실험군 둘** — T0(`fusion_doc_agreement=False`) / F1(`True`). 질의마다 한 프로세스 안에서 연달아
   돌려 코퍼스를 글자 그대로 같게 둔다. 두 실험군 다 `api._search_channels` 를 지난다(라이브 그 함수).
2. **골든 문서가 있는 라벨** — 골든 문서가 **상위 10**(문서 단위)에 오는가. `top_k` 10 은 T2 회귀와
   같은 값이다(그 표와 나란히 읽게). 라벨 집합마다 Recall@10(건수)과 MRR 을 적는다.
3. **골든이 없는 라벨**(`expect` 사실) — 답변 경로와 같은 검색(`top_k` 20)과 같은 근거 묶음
   (`packet_for_answer`)을 만들고, 기대 사실이 그 근거 묶음의 글(`format_for_llm`, 모델이 보는 문자열)에
   있는가. 판정은 `answer_fact_probe` 의 것을 그대로 쓴다(`required_groups` · 그 파일의 `_norm`).
   **LLM 을 안 부른다** — 처치는 검색만 건드리고, 생성의 변동성을 처치의 효과로 적지 않는다.
4. **판정** — 라벨 집합 **하나라도** F1 의 Recall@10 건수 · MRR · 사실 건수가 T0 보다 **낮으면 기각**.
   같거나 높으면 그 집합은 회귀 없음. 유의성은 주장하지 않는다(사전 등록 §4.3).
5. **음성 대조군** — F1 실험군의 결과 객체가 `fusion_doc_agreement=True` 를 들고 오지 않은 질의가
   하나라도 있으면 이 버전은 **무효**다(스위치가 안 닿은 것). T0 쪽이 True 여도 무효.
6. **부 변수(기술만, 판정에 안 씀)** — 검색 구간 지연 중앙값 · 상위 10 의 한 문서 쏠림(가장 많은
   문서의 청크 비율) 평균 · 출력이 갈린 질의 수.
7. 경로가 죽으면(`degraded`) 그 상태의 수는 결과가 아니다 — 멈춘다. 만료된 라벨은 **실험군 비교에는
   넣고**(같은 날 같은 코퍼스라 비교는 선다) 표시한다.

    docker exec nexus-app python -m scripts.fusion_doc_agreement_regression_probe
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from scripts.answer_fact_probe import _norm, required_groups  # noqa: E402
from scripts.identifier_channel_regression_probe import label_files  # noqa: E402
from scripts.ko_eval_labels import expired  # noqa: E402
from scripts.ko_eval_packb import MANIFEST, tenant_bodies  # noqa: E402

LOCAL_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "local"
REPORT = LOCAL_DIR / "fusion-doc-agreement-regression.json"
ARMS = (("T0", False), ("F1", True))
CLEARANCE = "INTERNAL"
GOLD_TOP_K = 10      # T2 회귀와 같은 값
ANSWER_TOP_K = 20    # 답변 경로의 값(`AnswerRequest.top_k`)


def _max_doc_share(hits) -> float | None:
    """상위 목록에서 가장 많은 문서가 차지한 비율 — 부 변수 5(한 문서 쏠림)."""
    if not hits:
        return None
    return max(Counter(h.doc_rid for h in hits).values()) / len(hits)


def _median(xs: list[float]) -> float:
    return sorted(xs)[len(xs) // 2] if xs else 0.0


async def _run(args) -> int:
    from nexus import db
    from nexus.api import _search_channels
    from nexus.cli import _load_config
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.search import hybrid
    from nexus.search.evidence_packet import format_for_llm
    from nexus.search.reconcile import packet_for_answer

    titles = {d["key"]: d["title"]
              for d in json.loads(MANIFEST.read_text(encoding="utf-8"))["docs"]}
    svc, cfg = embedding_service_from_config(), _load_config()
    pool = await db.get_pool()

    files = label_files()
    if not files:
        print("⛔ 코퍼스를 선언한 라벨이 없다 — 측정할 것이 없다")
        return 2
    print(f"라벨 파일 {len(files)}건 · 골든 top-{GOLD_TOP_K} · 사실 top-{ANSWER_TOP_K}+묶음 · LLM 미사용\n")

    report: dict = {"ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "gold_top_k": GOLD_TOP_K, "answer_top_k": ANSWER_TOP_K, "files": []}
    try:
        for path in files:
            labels = yaml.safe_load(path.read_text(encoding="utf-8"))
            scope = [t.strip() for t in labels["corpus"]["tenant"].split(",") if t.strip()]
            queries = [q for q in labels["queries"] if q.get("answerable", True)]
            stale: dict = {}
            if (labels.get("corpus") or {}).get("bodies"):
                async with pool.acquire() as con:
                    live = {k: v["sha"] for k, v in (await tenant_bodies(con, scope[0])).items()}
                stale = expired(labels, live)
            gold_ok = all(g in titles for q in queries for g in (q.get("gold") or []))

            rows = []
            for q in queries:
                ns = SimpleNamespace(query=q["query"], history=None)
                sq, channels, _ = await _search_channels(ns, None, identifiers=False)
                golden = bool(q.get("gold")) and gold_ok
                row: dict = {"qid": q["id"], "file": path.name, "stale": q["id"] in stale}
                results = {}
                for arm, on in ARMS:
                    t0 = time.perf_counter()
                    r = await hybrid.hybrid_search(
                        sq, tenant=scope, clearance=CLEARANCE,
                        top_k=GOLD_TOP_K if golden else ANSWER_TOP_K,
                        embedding_svc=svc, config=cfg, channels=channels,
                        fusion_doc_agreement=on)
                    row[f"ms_{arm}"] = round((time.perf_counter() - t0) * 1000, 1)
                    if r.degraded:
                        print(f"✗ 경로가 죽었다({r.degraded}) — 이 상태의 수는 결과가 아니다")
                        return 1
                    # 사전 등록 5 — 결과 객체가 「켰는가」를 들고 와야 이 버전이 선다.
                    row[f"applied_{arm}"] = r.fusion_doc_agreement
                    row[f"share_{arm}"] = _max_doc_share(r.hits[:GOLD_TOP_K])
                    results[arm] = r
                    if golden:
                        want = {titles[g] for g in q["gold"]}
                        row[f"rank_{arm}"] = next(
                            (i + 1 for i, h in enumerate(r.hits) if h.doc_title in want), None)
                    else:
                        groups = required_groups(q)
                        if groups:
                            packet = await packet_for_answer(
                                r, scope, CLEARANCE, config=cfg, search=hybrid.hybrid_search,
                                embedding_svc=svc, question=q["query"], pool=pool)
                            text = _norm(format_for_llm(packet))
                            row[f"facts_{arm}"] = all(
                                any(_norm(x) in text for x in g) for g in groups)
                row["same_hits"] = ([h.rid for h in results["T0"].hits]
                                    == [h.rid for h in results["F1"].hits])
                rows.append(row)
                if golden:
                    detail = f"골든 {row['rank_T0'] or '-'}→{row['rank_F1'] or '-'}"
                elif "facts_T0" in row:
                    detail = f"사실 {'O' if row['facts_T0'] else 'X'}→{'O' if row['facts_F1'] else 'X'}"
                else:
                    detail = "(판정 재료 없음)"
                mark = "=" if row["same_hits"] else "!"
                print(f"{mark} {q['id']:16s} {detail}{'  [만료]' if row['stale'] else ''}",
                      flush=True)

            summary: dict = {"file": path.name, "tenant": scope, "queries": len(rows),
                             "identical_hits": sum(1 for r in rows if r["same_hits"]),
                             "expired": sorted(stale), "gold_keys_resolved": gold_ok,
                             "rows": rows}
            gold_rows = [r for r in rows if "rank_T0" in r]
            fact_rows = [r for r in rows if "facts_T0" in r]
            for arm, _ in ARMS:
                if gold_rows:
                    hit = [r for r in gold_rows if r[f"rank_{arm}"]]
                    summary[f"hits_{arm}"] = len(hit)
                    summary[f"mrr_{arm}"] = sum(1 / r[f"rank_{arm}"] for r in hit) / len(gold_rows)
                if fact_rows:
                    summary[f"facts_{arm}"] = sum(1 for r in fact_rows if r[f"facts_{arm}"])
            summary["n_gold"], summary["n_facts"] = len(gold_rows), len(fact_rows)
            # 사전 등록 4 — 하나라도 낮으면 기각.
            dropped = [k for k in ("hits", "mrr", "facts")
                       if f"{k}_T0" in summary and summary[f"{k}_F1"] < summary[f"{k}_T0"]]
            summary["dropped"] = dropped
            report["files"].append(summary)

            line = f"\n  {path.name}  질의 {len(rows)}  출력 동일 {summary['identical_hits']}"
            if gold_rows:
                line += (f"  Recall@{GOLD_TOP_K} T0 {summary['hits_T0']}/{len(gold_rows)} · "
                         f"F1 {summary['hits_F1']}/{len(gold_rows)}  MRR "
                         f"{summary['mrr_T0']:.3f} / {summary['mrr_F1']:.3f}")
            if fact_rows:
                line += (f"  사실 T0 {summary['facts_T0']}/{len(fact_rows)} · "
                         f"F1 {summary['facts_F1']}/{len(fact_rows)}")
            print(line + (f"  ⛔ 떨어짐: {dropped}" if dropped else "") + "\n", flush=True)
    finally:
        await db.close_pool()

    rows = [r for f in report["files"] for r in f["rows"]]
    shares = {arm: [r[f"share_{arm}"] for r in rows if r[f"share_{arm}"] is not None]
              for arm, _ in ARMS}
    report["totals"] = {
        "queries": len(rows),
        "applied_F1": sum(1 for r in rows if r["applied_F1"]),
        "applied_T0": sum(1 for r in rows if r["applied_T0"]),
        "differed": sum(1 for r in rows if not r["same_hits"]),
        "median_ms_T0": _median([r["ms_T0"] for r in rows]),
        "median_ms_F1": _median([r["ms_F1"] for r in rows]),
        "mean_max_doc_share_T0": sum(shares["T0"]) / len(shares["T0"]) if shares["T0"] else None,
        "mean_max_doc_share_F1": sum(shares["F1"]) / len(shares["F1"]) if shares["F1"] else None,
        "rejected_by": [f["file"] for f in report["files"] if f["dropped"]],
    }
    t = report["totals"]
    print(f"전체 {t['queries']}건 · F1 적용 {t['applied_F1']}건 · T0 적용 {t['applied_T0']}건 · "
          f"출력이 갈린 질의 {t['differed']}건")
    print(f"  검색 구간 중앙값  T0 {t['median_ms_T0']:.0f}ms · F1 {t['median_ms_F1']:.0f}ms")
    if t["mean_max_doc_share_T0"] is not None:
        print(f"  한 문서 쏠림 평균  T0 {t['mean_max_doc_share_T0']:.3f} · "
              f"F1 {t['mean_max_doc_share_F1']:.3f}")
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"  리포트: {REPORT}")
    # 사전 등록 5 — 스위치가 안 닿았으면 이 버전은 무효다.
    if t["applied_F1"] != t["queries"] or t["applied_T0"]:
        print("  ⛔ 처치가 결과 객체에 안 닿았다(또는 대조군에 닿았다) — 이 판은 무효다")
        return 1
    if t["rejected_by"]:
        print(f"  ⇒ 기각(사전 등록 §4.2): 회귀 변수가 떨어진 집합 {t['rejected_by']}")
    else:
        print("  ⇒ 회귀 없음 — 어느 집합도 떨어지지 않았다")
    return 0


def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser()
    return asyncio.run(_run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
