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

TENANT = "default"
CLEARANCE = "INTERNAL"


def _norm(s: str) -> str:
    """공백·쉼표를 지운다 — `4,000` 과 `4000`, `최대 1` 과 `최대1` 이 같아야 한다."""
    return re.sub(r"[\s,]+", "", s or "")


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    labels = yaml.safe_load(Path(args.labels).read_text(encoding="utf-8"))
    queries = labels["queries"]

    await db.get_pool()
    try:
        from nexus.api import _load_config
        from nexus.llm.answer import generate_answer
        from nexus.providers.embedding import embedding_service_from_config
        from nexus.providers.llm import LLMService
        from nexus.search import hybrid
        from nexus.search.evidence_packet import assemble_packet

        svc, cfg = embedding_service_from_config(), _load_config()
        rows = []
        for q in queries:
            r = await hybrid.hybrid_search(q["query"], tenant=TENANT, clearance=CLEARANCE,
                                           top_k=10, embedding_svc=svc, config=cfg)
            packet = await assemble_packet(r.hits, r.graph, tenant=TENANT, fill=r.fill)
            ans = await generate_answer(q["query"], packet, LLMService(),
                                        confidence=r.confidence)
            text = getattr(ans, "answer", None) or getattr(ans, "text", "") or str(ans)
            nt = _norm(text)
            ok = any(_norm(e) in nt for e in (q.get("expect") or []))
            dis = [d for d in (q.get("distractor") or []) if _norm(d) in nt]
            rows.append({"id": q["id"], "pass": ok, "distractor_seen": dis,
                         "chars": len(text)})
            print(f"  {q['id']:4} {'통과' if ok else '실패'}"
                  f"{'  (낡은 값 언급: ' + ','.join(dis) + ')' if dis else ''}", flush=True)

        n = len(rows)
        p = sum(r["pass"] for r in rows)
        print(f"\n  답변 사실 정확도 **{p}/{n} = {p/n:.3f}**")
        print(f"  낡은 값이 언급된 답변 {sum(1 for r in rows if r['distractor_seen'])}건 "
              "(판정에 안 들어감 — 좋은 답도 기각하며 언급한다)")
        if args.out:
            Path(args.out).write_text(json.dumps(
                {"n": n, "passed": p, "rows": rows}, ensure_ascii=False, indent=2),
                encoding="utf-8")
            print(f"  기록: {args.out}")
    finally:
        await db.close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
