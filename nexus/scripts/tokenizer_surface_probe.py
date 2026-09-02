"""표면형을 같이 색인하면 조각난 고유명사가 되살아나는가. **재임베딩 없음, 지출 0.**

규칙은 측정 전에 `tests/eval/tokenizer-surface/README.md` 에 박혔다.

**두 실험군은 벡터가 완전히 같다.** 토크나이저는 `tsvector` 에만 쓰이고 임베딩은 원문을 쓰므로,
라이브 청크를 **임베딩째 복사**해서 BM25 색인만 다르게 건다. 그래서 이 측정은 제품 경로
(`hybrid_search`)를 볼 수 있으면서도 한 시간짜리 재임베딩이 없다.

색인과 질의는 **같은 토크나이저**로 돈다(`use_tokenizer`). 한쪽만 바꾼 실행은 그럴듯한 숫자를
내고 아무 뜻이 없다 (SPEC-nexus-korean-retrieval-eval §4.4).

    docker exec nexus-app python -m scripts.tokenizer_surface_probe \
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

SOURCE = "default"
CLEARANCE = "INTERNAL"


async def build(arm: str) -> None:
    """라이브 청크를 **임베딩째** 복사한다. rid 는 그대로 두면 충돌하므로 접두사를 붙인다."""
    from nexus.index.vector_index import configured_column

    col = configured_column()
    await db.execute("DELETE FROM chunks WHERE tenant=$1", arm)
    await db.execute("DELETE FROM documents WHERE tenant=$1", arm)
    await db.execute(
        "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title, status) "
        "SELECT $1 || rid, $1, source_uri, hash, content_hash, title, 'active' "
        "FROM documents WHERE tenant=$2 AND status='active'", arm, SOURCE)
    await db.execute(
        f"INSERT INTO chunks (rid, tenant, source_uri, doc_rid, section_path, chunk_text, "
        f"chunk_index, context_prefix, status, hash, {col}) "
        f"SELECT $1 || rid, $1, source_uri, $1 || doc_rid, section_path, chunk_text, "
        f"chunk_index, context_prefix, 'active', hash, {col} "
        f"FROM chunks WHERE tenant=$2 AND status='active'", arm, SOURCE)


async def index_bm25(arm: str) -> int:
    from nexus.index.bm25 import index_chunk_bm25

    rows = await db.fetch_all(
        "SELECT rid, section_path, chunk_text, context_prefix FROM chunks "
        "WHERE tenant=$1 AND status='active'", arm)

    class _C:
        def __init__(self, r):
            self.chunk_text = r["chunk_text"]
            self.section_path = r["section_path"]
            self.context_prefix = r["context_prefix"]

    n = 0
    for r in rows:
        if await index_chunk_bm25(r["rid"], _C(r)):
            n += 1
    return n


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--labels", required=True)
    args = ap.parse_args()

    from scripts.ko_eval_harness import collapse_to_documents, score_query, verdict

    labels = yaml.safe_load(Path(args.labels).read_text(encoding="utf-8"))
    queries = [q for q in labels["queries"] if q.get("answerable")]
    kinds = {q["id"]: q.get("kind", "all") for q in queries}

    await db.get_pool()
    try:
        from nexus.api import _load_config
        from nexus.index.bm25 import MecabTokenizer, SurfaceFormTokenizer, use_tokenizer
        from nexus.providers.embedding import embedding_service_from_config
        from nexus.search import hybrid

        svc, cfg = embedding_service_from_config(), _load_config()
        arms = {"tok_a": MecabTokenizer(), "tok_b": SurfaceFormTokenizer()}
        print(f"질문 {len(queries)}건 · 실험군 {list(arms)} · 임베딩 복사(재계산 없음) · LLM 0회")

        results: dict[str, dict] = {}
        try:
            for arm, tok in arms.items():
                await build(arm)
                cd = {r["rid"]: r["source_uri"].split(":", 1)[-1] for r in await db.fetch_all(
                    "SELECT rid, source_uri FROM chunks WHERE tenant=$1", arm)}
                with use_tokenizer(tok):
                    n = await index_bm25(arm)
                    leg, hyb = [], []
                    for q in queries:
                        hits, _ = await hybrid._bm25_search(q["query"], arm, CLEARANCE, 20)
                        leg.append(score_query(q["id"],
                                               collapse_to_documents(hits, cd), q["gold"]))
                        r = await hybrid.hybrid_search(q["query"], tenant=arm,
                                                       clearance=CLEARANCE, top_k=10,
                                                       embedding_svc=svc, config=cfg)
                        docs = list(dict.fromkeys(
                            h.source_uri.split(":", 1)[-1] for h in r.hits))
                        hyb.append(score_query(q["id"], docs, q["gold"]))
                results[arm] = {"leg": leg, "hyb": hyb}

                def _r(scores, kind=None):
                    sel = [s for s in scores if kind is None or kinds[s.qid] == kind]
                    return sum(s.recall for s in sel) / len(sel) if sel else 0.0
                print(f"  {arm} ({tok.id}) BM25 색인 {n} · hybrid R@10 전체 {_r(hyb):.3f} · "
                      f"파편 {_r(hyb,'fragment'):.3f} · 대조군 {_r(hyb,'control'):.3f}"
                      f"   (경로 {_r(leg):.3f})", flush=True)

            def rec(scores, kind):
                sel = [s for s in scores if kinds[s.qid] == kind]
                return sum(s.recall for s in sel) / len(sel) if sel else 0.0

            a, b = results["tok_a"]["hyb"], results["tok_b"]["hyb"]
            wins = loss = tie = 0
            by = {s.qid: s for s in a}
            for s in b:
                base = by[s.qid]
                if s.recall != base.recall:
                    wins, loss = ((wins + 1, loss) if s.recall > base.recall
                                  else (wins, loss + 1))
                elif s.rr != base.rr:
                    wins, loss = (wins + 1, loss) if s.rr > base.rr else (wins, loss + 1)
                else:
                    tie += 1
            v = verdict(wins, loss, tie, name_a="표면형", name_b="현직")
            up = (rec(b, "fragment") > rec(a, "fragment")
                  or sum(s.recall for s in b) > sum(s.recall for s in a))
            keep = rec(b, "control") >= rec(a, "control")
            print(f"\n  승 {wins} · 패 {loss} · 무 {tie} — {v.decision}")
            print(f"  규칙 2: ①이득 {'O' if up else 'X'} · ②대조군 무손실 "
                  f"{'O' if keep else 'X'} → {'채택 후보' if (up and keep) else '기각'}")
        finally:
            for arm in arms:
                await db.execute("DELETE FROM chunks WHERE tenant=$1", arm)
                await db.execute("DELETE FROM documents WHERE tenant=$1", arm)
    finally:
        await db.close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
