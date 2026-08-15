"""A13 — 문서 제목을 검색 텍스트에 넣으면 키워드 다리가 좋아지는가. **재보는 자, 제품 아님.**

라이브 코퍼스 실측(2026-08-15, `default` 활성 309청크):

    section_path='root' 인 청크          95
      └ 그중 제목이 본문에도 없는 것     90     ← 색인 텍스트에 문서 신원이 **하나도 없다**
    제목이 section_path 에 없는 청크    228/309 (74%)

`get_search_text()` 는 `context_prefix or "[section_path]"` 다. `context_prefix` 는 코퍼스
전체에서 NULL 이고, `section_path` 가 'root' 면 접두사는 `[root]` — 정보가 0이다.

Pack A 로는 이걸 못 잰다: 그 코퍼스는 H1 이 곧 문서 제목이라 `section_path` 가 이미
"노드 > 노드 상태" 로 제목을 품는다. 그래서 **Pack B**(실물 스냅샷)로 잰다.

**판정 규칙은 숫자를 보기 전에 못박는다** — 하니스가 이미 가진 규칙 그대로
(`ko_eval_harness.verdict`): 질의별 승패는 키워드 **Recall@10**, 동점이면 **MRR@10**,
양측 부호검정 α=0.05, **불일치쌍 6건 미만이면 "검정력 부족"**(차이 없음이 아니다).

두 팔은 같은 청크·같은 토크나이저·같은 질의다. 다른 것은 접두사 하나뿐이다:

    A(현직)  [section_path]                      · 오늘 배포된 그대로
    B(후보)  [제목 > section_path] / [제목]       · section_path 가 root 면 제목만

읽기 전용이 아니다 — 버릴 테넌트 둘을 만들고 끝나면 지운다. 원본 `ko_eval_packb` 는
**건드리지 않는다**.

    docker compose exec -T nexus-app python -m scripts.a13_context_prefix
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

from nexus import db  # noqa: E402
from scripts.ko_eval_harness import (  # noqa: E402
    LegResult, collapse_to_documents, score_query, verdict,
)

SOURCE = "ko_eval_packb"
ARMS = {"a13_a": None, "a13_b": "title"}
LABELS = Path("/app/tests/eval/local/packb-labels.yaml")


def prefix_for(title: str, section_path: str) -> str:
    """B 팔의 접두사. **제목이 이미 있으면 두 번 넣지 않는다** — 중복은 그 자체로 신호를 흐린다."""
    section = (section_path or "root").strip()
    if section == "root" or not section:
        return f"[{title}]"
    if title and title in section:
        return f"[{section}]"
    return f"[{title} > {section}]"


async def build(arm: str, mode: str | None) -> dict[str, str]:
    """원본 테넌트를 복사한다. 반환 = {chunk_rid: 문서키} — 채점이 문서로 접을 때 쓴다."""
    from nexus.index.bm25 import index_chunk_bm25

    await db.execute("DELETE FROM chunks WHERE tenant=$1", arm)
    await db.execute("DELETE FROM documents WHERE tenant=$1", arm)

    docs = await db.fetch_all(
        "SELECT rid, source_uri, title, hash, content_hash FROM documents "
        "WHERE tenant=$1 AND status='active'", SOURCE)
    rid_map: dict[str, str] = {}
    for d in docs:
        uri = f"{arm}:{d['source_uri']}"
        from nexus.rid import doc_rid
        new = doc_rid(uri)
        rid_map[d["rid"]] = new
        await db.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title, status) "
            "VALUES ($1,$2,$3,$4,$5,$6,'active')",
            new, arm, uri, d["hash"], d["content_hash"], d["title"])

    rows = await db.fetch_all(
        "SELECT c.rid, c.doc_rid, c.chunk_text, c.section_path, c.chunk_index, c.source_uri, "
        "       d.title FROM chunks c JOIN documents d ON d.rid=c.doc_rid "
        "WHERE c.tenant=$1 AND c.status='active' AND c.is_quarantined=false", SOURCE)

    from nexus.rid import chunk_rid
    chunk_doc: dict[str, str] = {}
    for r in rows:
        drid = rid_map[r["doc_rid"]]
        crid = chunk_rid(drid, r["section_path"] or "root", r["chunk_index"])
        cp = prefix_for(r["title"], r["section_path"]) if mode == "title" else None
        await db.execute(
            "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, chunk_text, section_path, "
            "chunk_index, context_prefix, status, hash) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'active','h') ON CONFLICT (rid) DO NOTHING",
            crid, arm, f"{arm}:{r['source_uri']}", drid, r["chunk_text"],
            r["section_path"] or "root", r["chunk_index"], cp)

        class _C:
            chunk_text = r["chunk_text"]
            section_path = r["section_path"] or "root"
            context_prefix = cp

        await index_chunk_bm25(crid, _C())
        # 문서키 = 원본 source_uri (라벨의 gold 가 그 이름이다)
        chunk_doc[crid] = r["source_uri"].split(":", 1)[-1]
    return chunk_doc


async def leg(labels: dict, arm: str, chunk_doc: dict[str, str]) -> LegResult:
    from nexus.search import hybrid

    res = LegResult(leg=arm)
    for q in labels["queries"]:
        if not q.get("answerable"):
            continue
        hits = await hybrid._bm25_search(q["query"], arm, "INTERNAL", 20)
        res.scores.append(score_query(q["id"], collapse_to_documents(hits, chunk_doc), q["gold"]))
    return res


async def main() -> int:
    labels = yaml.safe_load(LABELS.read_text(encoding="utf-8"))
    await db.get_pool()
    try:
        results = {}
        for arm, mode in ARMS.items():
            cd = await build(arm, mode)
            results[arm] = await leg(labels, arm, cd)
            r = results[arm]
            print(f"  {arm:6s} n={r.n}  Recall@10 {r.recall:.3f}  MRR@10 {r.mrr:.3f}  "
                  f"미스 {sum(1 for s in r.scores if not s.recall)}")

        a, b = results["a13_b"], results["a13_a"]      # a = 후보(제목), b = 현직
        wins = losses = ties = 0
        by_id = {s.qid: s for s in b.scores}
        for sa in a.scores:
            sb = by_id[sa.qid]
            if sa.recall != sb.recall:
                wins, losses = (wins + 1, losses) if sa.recall > sb.recall else (wins, losses + 1)
            elif sa.rr != sb.rr:
                wins, losses = (wins + 1, losses) if sa.rr > sb.rr else (wins, losses + 1)
            else:
                ties += 1
        v = verdict(wins, losses, ties, name_a="제목접두사", name_b="현직")
        print(f"\n  승 {v.wins} · 패 {v.losses} · 무 {v.ties}")
        print(f"  판정: {v.decision}")
    finally:
        for arm in ARMS:
            await db.execute("DELETE FROM chunks WHERE tenant=$1", arm)
            await db.execute("DELETE FROM documents WHERE tenant=$1", arm)
        await db.close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
