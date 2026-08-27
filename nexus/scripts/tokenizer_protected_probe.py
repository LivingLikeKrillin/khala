"""코퍼스가 자기 이름으로 쓰는 낱말만 보호하면 순위가 오르는가. **재임베딩 없음, 지출 0.**

규칙은 측정 전에 `tests/eval/tokenizer-protected-terms/README.md` 에 박혔다.

지표가 다르다: **`broken` 부분집합의 MRR@10 · Recall@3**. Recall@10 은 대조군이 이미 1.000 이라
천장에 붙어 아무것도 못 본다 — 앞 측정이 그래서 아무 차이도 못 냈다.

**두 실험군은 벡터가 완전히 같다.** 토크나이저는 `tsvector` 에만 쓰이고 임베딩은 원문을 쓰므로,
라이브 청크를 **임베딩째 복사**해서 BM25 색인만 다르게 건다. 그래서 이 측정은 제품 경로
(`hybrid_search`)를 볼 수 있으면서도 한 시간짜리 재임베딩이 없다.

색인과 질의는 **같은 토크나이저**로 돈다(`use_tokenizer`). 한쪽만 바꾼 실행은 그럴듯한 숫자를
내고 아무 뜻이 없다 (SPEC-nexus-korean-retrieval-eval §4.4).

    docker exec nexus-app python -m scripts.tokenizer_protected_probe \
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

    from scripts.ko_eval_harness import score_query, verdict

    labels = yaml.safe_load(Path(args.labels).read_text(encoding="utf-8"))
    queries = [q for q in labels["queries"] if q.get("answerable")]

    await db.get_pool()
    try:
        from nexus.api import _load_config
        from nexus.index.bm25 import (MecabTokenizer, ProtectedTermTokenizer,
                              SurfaceFormTokenizer, use_tokenizer)
        from nexus.providers.embedding import embedding_service_from_config
        from nexus.search import hybrid

        svc, cfg = embedding_service_from_config(), _load_config()

        # 보호 목록을 **코퍼스에서 유도한다** — 문서 제목 + 섹션 경로.
        from nexus.index.bm25 import compound_names
        names = await db.fetch_all(
            "SELECT DISTINCT d.title AS t FROM documents d WHERE d.tenant=$1 AND d.status='active' "
            "UNION SELECT DISTINCT c.section_path FROM chunks c WHERE c.tenant=$1 "
            "AND c.status='active'", SOURCE)
        terms = sorted({w for r in names for w in compound_names(r["t"] or "")})
        print(f"유도된 보호 용어 {len(terms)}개: {terms[:14]}{' …' if len(terms) > 14 else ''}")

        # 규칙 1: 처치가 닿는 부분집합 = 질의에 그 낱말이 실제로 든 질문.
        broken_ids = {q["id"] for q in queries
                      if any(t in q["query"].lower() for t in terms)}
        print(f"`broken` 부분집합 {len(broken_ids)}/{len(queries)}문항: {sorted(broken_ids)}")

        arms = {"tok_a": MecabTokenizer(),
                "tok_b": ProtectedTermTokenizer(terms),
                "tok_c": SurfaceFormTokenizer()}
        results: dict[str, list] = {}
        try:
            for arm, tok in arms.items():
                await build(arm)
                with use_tokenizer(tok):
                    n = await index_bm25(arm)
                    hyb = []
                    for q in queries:
                        r = await hybrid.hybrid_search(q["query"], tenant=arm,
                                                       clearance=CLEARANCE, top_k=10,
                                                       embedding_svc=svc, config=cfg)
                        docs = list(dict.fromkeys(
                            h.source_uri.split(":", 1)[-1] for h in r.hits))
                        hyb.append(score_query(q["id"], docs, q["gold"]))
                results[arm] = hyb

                def agg(scores, ids=None, k=None):
                    sel = [s for s in scores if ids is None or s.qid in ids]
                    if not sel:
                        return 0.0, 0.0
                    mrr = sum(s.rr for s in sel) / len(sel)
                    rec = sum(s.recall for s in sel) / len(sel)
                    return rec, mrr
                r_all, _ = agg(hyb)
                r_b, m_b = agg(hyb, broken_ids)
                print(f"  {arm} ({tok.id:20}) 색인 {n} · 전체 R@10 {r_all:.3f} · "
                      f"broken MRR@10 {m_b:.3f} · broken R@10 {r_b:.3f}", flush=True)

            base = results["tok_a"]
            def mrr(scores, ids):
                sel = [s for s in scores if s.qid in ids]
                return sum(s.rr for s in sel) / len(sel) if sel else 0.0
            def rec_all(scores):
                return sum(s.recall for s in scores) / len(scores)
            print(chr(10) + "사전등록 규칙 3 대조:")
            for arm in ("tok_b", "tok_c"):
                h = results[arm]
                up = mrr(h, broken_ids) > mrr(base, broken_ids)
                keep = rec_all(h) >= rec_all(base)
                wins = loss = tie = 0
                by = {s.qid: s for s in base}
                for s in h:
                    b0 = by[s.qid]
                    if s.recall != b0.recall:
                        wins, loss = ((wins + 1, loss) if s.recall > b0.recall
                                      else (wins, loss + 1))
                    elif s.rr != b0.rr:
                        wins, loss = (wins + 1, loss) if s.rr > b0.rr else (wins, loss + 1)
                    else:
                        tie += 1
                v = verdict(wins, loss, tie, name_a=arm, name_b="현직")
                print(f"  {arm}: ①broken MRR 상승 {'O' if up else 'X'} · "
                      f"②전체 Recall 무손실 {'O' if keep else 'X'} → "
                      f"{'채택 후보' if (up and keep) else '기각'}"
                      f"   (승 {wins} · 패 {loss} · 무 {tie} — {v.decision})")
        finally:
            for arm in arms:
                await db.execute("DELETE FROM chunks WHERE tenant=$1", arm)
                await db.execute("DELETE FROM documents WHERE tenant=$1", arm)
    finally:
        await db.close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
