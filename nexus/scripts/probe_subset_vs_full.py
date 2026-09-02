"""부분 실행과 전체 실행이 **검색에서** 갈리는가 (A31).

⛔ `--only A-9` 는 2판 4/8, 전체 15개는 10/10 — 재현되는 차이인데 원인을 모른다. 하니스의
필터는 질의 목록만 거르고 브리지는 세션을 안 남긴다. 그러면 남는 후보는 **검색**이다.

이 프로브는 답변을 만들지 않는다. **같은 프로세스에서 질의를 순서대로 돌리며 상위 k 청크
rid 를 찍는다.** 부분 실행(그 질의 하나)과 전체 실행(앞에 8개를 돌린 뒤)의 rid 집합이 같으면
검색은 결정론이고 차이는 LLM 쪽이다. 다르면 검색이다.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io

import yaml

from nexus import db


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--target", required=True, help="관심 라벨 id")
    ap.add_argument("--warmup", type=int, default=0, help="앞에 먼저 돌릴 질의 수")
    ap.add_argument("--tenant", default="default")
    ap.add_argument("--top-k", type=int, default=20)
    args = ap.parse_args()

    from nexus.api import _load_config
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.search import hybrid

    cfg = _load_config()
    svc = embedding_service_from_config(cfg)
    queries = yaml.safe_load(io.open(args.labels, encoding="utf-8").read())["queries"]
    target = next(q for q in queries if q["id"] == args.target)
    warm = [q for q in queries if q["id"] != args.target][: args.warmup]

    # 하니스와 같은 방식으로 범위를 쪼갠다 — 문자열 하나를 그대로 넘기면
    # `tenant = 'default,design_docs'` 리터럴이 되어 0건이 나온다.
    scope = [t.strip() for t in args.tenant.split(',') if t.strip()]
    await db.get_pool()
    try:
        for q in warm:
            await hybrid.hybrid_search(q["query"], tenant=scope, clearance="INTERNAL",
                                       top_k=args.top_k, embedding_svc=svc, config=cfg)
        r = await hybrid.hybrid_search(target["query"], tenant=scope,
                                       clearance="INTERNAL", top_k=args.top_k,
                                       embedding_svc=svc, config=cfg)
        rids = [h.rid for h in r.hits]
        digest = hashlib.sha256("|".join(rids).encode()).hexdigest()[:12]
        print(f"warmup={args.warmup} hits={len(rids)} 순서포함해시={digest}")

        # 검색이 같아도 **프롬프트**가 다를 수 있다 — 근거 조립(절 채움·정정 패스·짝 확장·
        # 코드 값)이 붙는 것들이 프로세스 상태에 걸려 있으면 거기서 갈린다.
        from nexus.llm.prompts import build_prompts
        from nexus.search.evidence_packet import format_for_llm
        from nexus.search.reconcile import packet_for_answer
        packet = await packet_for_answer(r, scope, "INTERNAL", config=cfg,
                                         search=hybrid.hybrid_search, embedding_svc=svc,
                                         question=target["query"], pool=await db.get_pool())
        ev = format_for_llm(packet)
        _, user = build_prompts(target["query"], ev)
        print(f"  근거 {len(packet.snippets)}개 · 프롬프트 {len(user)}자 · "
              f"해시={hashlib.sha256(user.encode()).hexdigest()[:12]}")
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
