"""답변 품질을 실제로 재는 실행기 — 검색이 아니라 **답**을 본다.

이 리포는 검색을 엄격하게 재 왔고 답변은 한 번도 안 쟀다. 이것이 그 첫 실행이다.

**관문을 먼저 통과해야 결과로 친다** (`ko_eval_packb_run.py` 와 같은 이유): 라벨 게이트가
막으면 숫자를 내지 않는다. 관문이 뒤에 있으면 숫자를 보고 자를 고치게 된다.

**LLM 을 부른다 — 돈이 든다.** 질의 하나에 한 번, 기본 40건. `--limit` 로 줄일 수 있고, 무엇을
부를지는 `NEXUS_LLM_PROVIDER` 가 정한다(키 없이 도는 claude-code 브리지 포함).

리포트는 `tests/eval/local/` 에만 쓴다 — 답변 본문이 다른 조직의 정책 내용을 담는다.

    docker exec nexus-app python scripts/ko_eval_answer_run.py --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ko_eval_answer_quality import aggregate, score_answer  # noqa: E402
from scripts.ko_eval_labels import ManifestPack, check, load  # noqa: E402
from scripts.ko_eval_packb import MANIFEST  # noqa: E402

LOCAL_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "local"
LABELS = LOCAL_DIR / "packb-labels.yaml"
REPORT = LOCAL_DIR / "packb-answer-quality.json"
TENANT = "default"


async def _run(args) -> int:
    from nexus import db
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.providers.llm import LLMService
    from nexus.search import hybrid
    from nexus.search.evidence_packet import assemble_packet
    from nexus.llm.answer import generate_answer

    labels = load(LABELS)
    if problems := check(labels, ManifestPack(MANIFEST)):
        print("✗ 라벨 게이트 실패 — 측정 이전에 자가 틀렸다:", *problems[:4], sep="\n  ")
        return 1

    titles = {d["key"]: d["title"] for d in json.loads(MANIFEST.read_text(encoding="utf-8"))["docs"]}
    queries = [q for q in labels["queries"] if q.get("answerable")][:args.limit]
    print(f"✓ 관문 통과 — 라벨 revision {labels['revision']} · 질의 {len(queries)}건\n")

    svc, llm = embedding_service_from_config(), LLMService()
    await db.get_pool()
    scores, rows = [], []
    try:
        for q in queries:
            result = await hybrid.hybrid_search(q["query"], tenant=TENANT, clearance="INTERNAL",
                                                top_k=10, embedding_svc=svc)
            if result.degraded:
                print(f"✗ 다리가 죽었다({result.degraded}) — 이 상태의 숫자는 결과가 아니다")
                return 1
            packet = assemble_packet(result.hits, result.graph)
            ans = await generate_answer(q["query"], packet, llm_svc=llm)
            # **첫 실패에서 멈춘다.** 계속 돌면 실패한 실행의 집계가 리포트로 남고, 그것을 나중에
            # '답변 품질' 로 읽게 된다 — 실제로 3건 중 2건이 근거 덤프 덕에 '사실 통과' 로 찍혔다.
            if ans.llm_failed:
                print(f"✗ {q['id']}: LLM 호출이 실패했다 — 이 상태의 숫자는 결과가 아니다.")
                print("  답변 자리에는 근거 원문이 들어가므로 사실 검사가 거저 통과한다.")
                print(f"  받은 것: {ans.answer[:80]}…")
                return 1
            s = score_answer(q["id"], ans.answer, ans.citations,
                             {titles[g] for g in q["gold"]}, q.get("must_contain") or [],
                             abstained=ans.abstained, llm_failed=ans.llm_failed)
            scores.append(s)
            rows.append({"qid": q["id"], "grounded": s.grounded, "cites_gold": s.cites_gold,
                         "facts": s.facts, "answer": ans.answer})
            mark = "OK " if s.ok else "   "
            print(f"{mark} {q['id']:12s} 근거{'✓' if s.grounded else '✗'} "
                  f"정답문서{'✓' if s.cites_gold else '✗'} 사실{'✓' if s.has_facts else '✗'}"
                  f"  인용 {s.n_citations}")
    finally:
        await db.close_pool()

    a = aggregate(scores)
    print(f"\n  근거 있음      {a['grounded']}/{a['queries']}   (인용 0개: {a['no_citation_at_all']})")
    print(f"  정답 문서 인용  {a['cites_gold']}/{a['queries']}")
    print(f"  사실 포함      {a['facts_present']}/{a['facts_measurable']}")
    print(f"  셋 다          {a['all_three']}/{a['queries']}")
    if a["failed"]:
        print(f"  실패: {', '.join(a['failed'])}")

    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(
        {"ran_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "labels_revision": labels["revision"], "tenant": TENANT,
         "llm_model": getattr(llm, "model", None), "summary": a, "queries": rows},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\n기록: {REPORT}  (답변 본문을 담는다 — 커밋하지 않는다)")
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=40, help="LLM 을 부르는 횟수 — 돈이 든다")
    args = ap.parse_args(argv)
    if not os.getenv("DATABASE_URL"):
        print("✗ DATABASE_URL 이 없다")
        return 1
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
