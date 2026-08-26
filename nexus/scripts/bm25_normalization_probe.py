"""키워드 다리의 길이 보정 — `ts_rank_cd` 정규화 인자 비교. **읽기 전용, 지출 0.**

규칙은 측정 전에 `tests/eval/bm25-normalization/README.md` 에 박혔다.

**제품 경로를 1차 지표로 쓴다.** A13 자는 다리별로 쟀는데 제품은 RRF 융합 + 다양화 + top_k
컷을 쓴다 — 그래서 "재서 이겼는데 답이 안 바뀌는" 자리가 나왔다. 여기서는 `hybrid_search()`
의 Recall@10 이 판정이고 다리 점수는 참고다.

`_bm25_search` 를 **감싸서** 인자를 주입한다(프로덕션 SQL 을 고치지 않는다 — 재는 동안 배포
코드가 바뀌면 무엇을 쟀는지가 흐려진다).

    docker exec nexus-app python -m scripts.bm25_normalization_probe \
        --labels /app/tests/eval/local/a13-round2b-labels.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from nexus import db  # noqa: E402

#: 사전등록된 팔. 0 = 현직.
FLAGS = [0, 1, 2, 16, 32]
TENANT = "default"
CLEARANCE = "INTERNAL"


async def _chunk_doc() -> dict[str, str]:
    """chunk_rid → gold 키(`source_uri` 의 테넌트 접두사를 뗀 것)."""
    rows = await db.fetch_all(
        "SELECT rid, source_uri FROM chunks WHERE tenant=$1 AND status='active'", TENANT)
    return {r["rid"]: r["source_uri"].split(":", 1)[-1] for r in rows}


def _patched_bm25(norm: int):
    """`ts_rank_cd` 에 정규화 인자를 넣은 판. 나머지 SQL 은 프로덕션과 같은 모양이다."""
    from nexus.index.bm25 import active_tokenizer, tokens_to_tsquery

    async def _bm25(query, tenant, clearance, top_k=20):
        tsquery = tokens_to_tsquery(active_tokenizer().tokenize(query))
        if not tsquery:
            return [], None
        rows = await db.fetch_all(
            """
            SELECT c.rid, ts_rank_cd(c.tsvector_ko, to_tsquery('simple', $1), $5) AS rank_score
            FROM chunks c
            WHERE c.tsvector_ko @@ to_tsquery('simple', $1)
              AND c.tenant = $2 AND c.classification <= $3::classification_level
              AND c.is_quarantined = false AND c.status = 'active'
              AND EXISTS (SELECT 1 FROM documents d
                          WHERE d.rid = c.doc_rid AND d.status = 'active')
            ORDER BY rank_score DESC, c.rid ASC
            LIMIT $4
            """,
            tsquery, tenant, clearance, top_k, norm)
        return ([(r["rid"], i + 1) for i, r in enumerate(rows)],
                float(rows[0]["rank_score"]) if rows else 0.0)

    return _bm25


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", required=True)
    args = ap.parse_args()

    from scripts.ko_eval_harness import collapse_to_documents, score_query

    labels = yaml.safe_load(Path(args.labels).read_text(encoding="utf-8"))
    queries = [q for q in labels["queries"] if q.get("answerable")]
    kinds = {q["id"]: q.get("kind", "all") for q in queries}
    print(f"질문 {len(queries)}건 · 팔 {FLAGS} · 라이브 {TENANT} 읽기 전용 · LLM 0회")

    await db.get_pool()
    try:
        from nexus.api import _load_config
        from nexus.providers.embedding import embedding_service_from_config
        from nexus.search import hybrid

        cd = await _chunk_doc()
        svc, cfg = embedding_service_from_config(), _load_config()
        original = hybrid._bm25_search
        table: dict[int, dict] = {}
        try:
            for norm in FLAGS:
                hybrid._bm25_search = _patched_bm25(norm)
                leg, hyb = [], []
                for q in queries:
                    hits, _ = await hybrid._bm25_search(q["query"], TENANT, CLEARANCE, 20)
                    leg.append(score_query(q["id"], collapse_to_documents(hits, cd), q["gold"]))
                    r = await hybrid.hybrid_search(q["query"], tenant=TENANT,
                                                   clearance=CLEARANCE, top_k=10,
                                                   embedding_svc=svc, config=cfg)
                    # **문서로 접는다.** hybrid 히트는 청크 단위라, 한 문서가 상위 10에
                    # 네 청크를 올리면 `score_query` 의 `len(hit)/len(gold)` 가 4.0 이 된다 —
                    # 첫 실행에서 실제로 Recall 3.5 가 찍혔고, 1을 넘을 수 없는 값이라 잡혔다.
                    docs = list(dict.fromkeys(
                        h.source_uri.split(":", 1)[-1] for h in r.hits))
                    hyb.append(score_query(q["id"], docs, q["gold"]))
                table[norm] = {"leg": leg, "hyb": hyb}
                def _r(scores, kind=None):
                    sel = [s for s in scores if kind is None or kinds[s.qid] == kind]
                    return sum(s.recall for s in sel) / len(sel) if sel else 0.0
                print(f"  norm={norm:<3} hybrid R@10 전체 {_r(hyb):.3f} · "
                      f"파편 {_r(hyb,'fragment'):.3f} · 대조군 {_r(hyb,'control'):.3f}"
                      f"   (다리 {_r(leg):.3f})", flush=True)
        finally:
            hybrid._bm25_search = original

        # 사전등록 규칙 2: 파편이 오르고 대조군이 안 떨어지는 것만 후보.
        from scripts.ko_eval_harness import verdict
        base = table[0]["hyb"]
        def rec(scores, kind):
            sel = [s for s in scores if kinds[s.qid] == kind]
            return sum(s.recall for s in sel) / len(sel) if sel else 0.0
        print("\n사전등록 규칙 2 대조 (1차 지표 = hybrid):")
        ok = []
        for norm in FLAGS:
            if norm == 0:
                continue
            h = table[norm]["hyb"]
            up = rec(h, "fragment") > rec(base, "fragment")
            keep = rec(h, "control") >= rec(base, "control")
            mark = "채택 후보" if (up and keep) else ("대조군 손해" if not keep else "파편 이득 없음")
            wins = loss = tie = 0
            by = {s.qid: s for s in base}
            for s in h:
                b = by[s.qid]
                if s.recall != b.recall:
                    wins, loss = ((wins + 1, loss) if s.recall > b.recall
                                  else (wins, loss + 1))
                elif s.rr != b.rr:
                    wins, loss = ((wins + 1, loss) if s.rr > b.rr
                                  else (wins, loss + 1))
                else:
                    tie += 1
            v = verdict(wins, loss, tie, name_a=f"norm={norm}", name_b="현직")
            print(f"  norm={norm:<3} {mark:10} 승 {wins} · 패 {loss} · 무 {tie} — {v.decision}")
            if up and keep:
                ok.append(norm)
        print(f"\n조건 충족: {ok or '없음 → 현직(0) 유지 (규칙 3)'}")
        if ok:
            print(f"규칙 3(가장 단순한 것) → **norm={min(ok, key=lambda n: bin(n).count('1'))}**")
    finally:
        await db.close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
