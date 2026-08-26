"""답변 사실 채점 — **답이 옳은가**를 잰다. Recall 이 못 보는 자리.

규칙은 측정 전에 `tests/eval/answer-facts/README.md` 에 박혔다.

검색 자(`Recall@10`)는 *정답 문서가 왔는가* 만 잰다. 2026-08-26 에 그 한계가 끝까지 드러났다 —
Recall 이 **오르는 동안 답변이 나빠졌다**(정답 숫자는 왔는데 낡은 숫자를 무효화하는 문장이 안
와서, 답변이 낡은 값을 정본으로 읽었다). 여기서는 답변 텍스트에 **그 값이 나오는가**를 본다.

**LLM 심판을 쓰지 않는다.** 판정은 정규화 부분일치이고, 그래서 무르다 — 오탐이 아니라 **누락**을
잡는 자로 쓴다. 기권도 실패로 센다: 코퍼스가 답을 갖고 있는데 못 낸 것이다.

    docker exec nexus-app python -m scripts.answer_fact_probe \
        --labels /app/tests/eval/local/answer-facts.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from nexus import db  # noqa: E402
from scripts.ko_eval_answer_quality import asserts_value, facts_present  # noqa: E402

TENANT = "default"
CLEARANCE = "INTERNAL"


def _norm(s: str) -> str:
    """공백·쉼표를 지운다 — `4,000` 과 `4000`, `최대 1` 과 `최대1` 이 같아야 한다."""
    return re.sub(r"[\s,]+", "", s or "")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--only", default="", help="쉼표로 구분한 id — 그것만 돈다")
    ap.add_argument("--fill", choices=("on", "off"), default="",
                    help="절 채움(`search.section_fill`) 강제. 비우면 config 그대로")
    ap.add_argument("--save-answers", default="",
                    help="답변 **원문**을 적을 파일. 조직 문서의 사실이므로 gitignore 된 곳에만")
    args = ap.parse_args()

    labels = yaml.safe_load(Path(args.labels).read_text(encoding="utf-8"))
    queries = labels["queries"]
    if args.only:
        want = {q.strip() for q in args.only.split(",") if q.strip()}
        queries = [q for q in queries if q["id"] in want]

    await db.get_pool()
    try:
        from nexus.api import _load_config
        from nexus.llm.answer import generate_answer
        from nexus.providers.embedding import embedding_service_from_config
        from nexus.providers.llm import LLMService
        from nexus.search import hybrid
        from nexus.search.evidence_packet import assemble_packet

        svc, cfg = embedding_service_from_config(), _load_config()
        if args.fill:
            cfg.setdefault("search", {})["section_fill"] = (args.fill == "on")
        print(f"  절 채움: {cfg.get('search', {}).get('section_fill')}", flush=True)
        rows, answers = [], []
        for q in queries:
            r = await hybrid.hybrid_search(q["query"], tenant=TENANT, clearance=CLEARANCE,
                                           top_k=10, embedding_svc=svc, config=cfg)
            packet = await assemble_packet(r.hits, r.graph, tenant=TENANT, fill=r.fill)
            ans = await generate_answer(q["query"], packet, LLMService(),
                                        confidence=r.confidence)
            text = getattr(ans, "answer", None) or getattr(ans, "text", "") or str(ans)
            nt = _norm(text)
            expect = q.get("expect") or []
            ok = any(_norm(e) in nt for e in expect)
            # 2판 — **주장했는가**. 같은 값을 담고도 결론을 안 낸 답변을 1판은 통과시킨다.
            said = asserts_value(expect, text)
            # 두 정규화(쉼표 제거 vs 공백 축약)가 갈리는 자리를 드러내 둔다.
            mentioned = all(facts_present([expect], text)) if expect else False
            dis = [d for d in (q.get("distractor") or []) if _norm(d) in nt]
            rows.append({"id": q["id"], "pass": ok, "asserted": said,
                         "mentioned": mentioned, "distractor_seen": dis,
                         "chars": len(text)})
            answers.append({"id": q["id"], "query": q["query"], "answer": text,
                            "expect": q.get("expect") or [],
                            "abstained": bool(getattr(ans, "abstained", False)),
                            "weak_evidence": bool(getattr(ans, "weak_evidence", False))})
            print(f"  {q['id']:4} 언급={'통과' if ok else '실패'} 주장={'통과' if said else '실패'}"
                  f"{'  (낡은 값 언급: ' + ','.join(dis) + ')' if dis else ''}", flush=True)

        n = len(rows)
        p = sum(r["pass"] for r in rows)
        a = sum(r["asserted"] for r in rows)
        mismatch = [r["id"] for r in rows if r["pass"] != r["mentioned"]]
        print(f"\n  1판 언급(부분일치) **{p}/{n} = {p/n:.3f}**")
        print(f"  2판 주장(선두·결론)  **{a}/{n} = {a/n:.3f}**"
              f"   — 값은 담고도 결론을 안 낸 답변 {p - a}건")
        if mismatch:
            print(f"  ⚠ 두 정규화가 갈린 질의: {mismatch}")
        print(f"  낡은 값이 언급된 답변 {sum(1 for r in rows if r['distractor_seen'])}건 "
              "(판정에 안 들어감 — 좋은 답도 기각하며 언급한다)")
        if args.out:
            Path(args.out).write_text(json.dumps(
                {"n": n, "passed": p, "asserted": a, "rows": rows},
                ensure_ascii=False, indent=2),
                encoding="utf-8")
            print(f"  기록: {args.out}")
        if args.save_answers:
            Path(args.save_answers).write_text(json.dumps(
                {"fill": cfg.get("search", {}).get("section_fill"), "answers": answers},
                ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  답변 원문: {args.save_answers}")
    finally:
        await db.close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
