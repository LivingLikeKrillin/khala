"""A13 — 문서 제목을 검색 텍스트에 넣으면 키워드 다리가 좋아지는가. **재보는 평가 하니스, 제품 아님.**

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

두 실험군은 같은 청크·같은 토크나이저·같은 질의다. 다른 것은 접두사 하나뿐이다:

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

#: 기본은 2026-08-15 1회차와 같다 — 그 판정을 재현할 수 있어야 하므로 바꾸지 않는다.
#: 2회차(2026-08-26)는 `--source default --labels <파일>` 로 **다른 코퍼스·다른 라벨**에 같은
#: 평가 하니스를 댄다. 사본을 만들지 않는 이유: 두 벌이 되는 순간 규칙이 갈라지고, 어느 쪽 숫자인지가
#: 실행 기록 밖에 남는다.
SOURCE = "ko_eval_packb"
ARMS = {"a13_a": None, "a13_b": "title"}
LABELS = Path("/app/tests/eval/local/packb-labels.yaml")


def _arg(flag: str, default):
    """`--flag 값`. argparse 를 안 쓰는 것은 기존 `--vector` 플래그 관례를 그대로 두기 위해서다."""
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def prefix_for(title: str, section_path: str) -> str:
    """B 실험군의 접두사. **제목이 이미 있으면 두 번 넣지 않는다** — 중복은 그 자체로 신호를 흐린다."""
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
        # **다리는 `(순위목록, 1위 원점수)` 를 돌려준다** — PR #292 가 원점수를 되살리면서
        # 모양이 바뀌었고, 그 뒤로 이 하니스를 아무도 안 돌려서 조용히 썩어 있었다.
        hits, _top = await hybrid._bm25_search(q["query"], arm, "INTERNAL", 20)
        res.scores.append(score_query(q["id"], collapse_to_documents(hits, chunk_doc), q["gold"]))
    return res


async def embed_arm(arm: str) -> int:
    """이 실험군의 청크를 **설정된 세대**로 임베딩한다. 인덱스는 안 만든다 — 289행이면 전수 스캔이고,
    ANN 근사가 두 실험군에 서로 다른 잡음을 얹는 것이 이 측정에서 제일 나쁜 일이다."""
    from nexus.index.embed import index_chunks_embedding
    from nexus.index.vector_index import configured_column
    from nexus.providers.embedding import embedding_service_from_config

    col = configured_column()
    rows = await db.fetch_all(
        f"SELECT rid, chunk_text, section_path, context_prefix FROM chunks "
        f"WHERE tenant=$1 AND {col} IS NULL", arm)

    class _C:
        def __init__(self, r):
            self.chunk_text = r["chunk_text"]
            self.section_path = r["section_path"]
            self.context_prefix = r["context_prefix"]

    svc = embedding_service_from_config()
    return await index_chunks_embedding([(r["rid"], _C(r)) for r in rows], svc, column=col)


async def vector_leg(labels: dict, arm: str, chunk_doc: dict[str, str]) -> LegResult:
    """**컬럼을 명시해서 부른다.** 안 넘기면 기본 768 컬럼을 읽고, 이 실험군은 1024 에 있다 —
    같은 실수로 "벡터 다리가 죽었다" 를 보고할 뻔한 적이 있다."""
    from nexus.index.vector_index import configured_column
    from nexus.providers.embedding import embedding_service_from_config
    from nexus.search import hybrid

    col, svc = configured_column(), embedding_service_from_config()
    res = LegResult(leg=f"{arm}:vector")
    for q in labels["queries"]:
        if not q.get("answerable"):
            continue
        hits, _top = await hybrid._vector_search(q["query"], svc, arm, "INTERNAL", 20, column=col)
        res.scores.append(score_query(q["id"], collapse_to_documents(hits, chunk_doc), q["gold"]))
    return res


def compare(a: LegResult, b: LegResult, label: str) -> None:
    """a(후보) vs b(현직). 규칙은 하니스 것 그대로 — 숫자를 보기 전에 정해져 있다."""
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
    print(f"\n  [{label}] 승 {v.wins} · 패 {v.losses} · 무 {v.ties}")
    print(f"  판정: {v.decision}")


async def main() -> int:
    global SOURCE
    SOURCE = _arg("--source", SOURCE)
    labels_path = Path(_arg("--labels", str(LABELS)))
    labels = yaml.safe_load(labels_path.read_text(encoding="utf-8"))
    want_vector = "--vector" in sys.argv
    print(f"원본 {SOURCE} · 라벨 {labels_path.name} "
          f"({sum(1 for q in labels['queries'] if q.get('answerable'))}문항)", flush=True)
    await db.get_pool()
    try:
        results, vec_results = {}, {}
        for arm, mode in ARMS.items():
            cd = await build(arm, mode)
            results[arm] = await leg(labels, arm, cd)
            r = results[arm]
            print(f"  {arm:6s} n={r.n}  Recall@10 {r.recall:.3f}  MRR@10 {r.mrr:.3f}  "
                  f"미스 {sum(1 for s in r.scores if not s.recall)}", flush=True)
            if want_vector:
                n = await embed_arm(arm)
                print(f"  {arm:6s} 임베딩 {n}청크", flush=True)
                vec_results[arm] = await vector_leg(labels, arm, cd)
                vr = vec_results[arm]
                print(f"  {arm:6s} [벡터] Recall@10 {vr.recall:.3f}  MRR@10 {vr.mrr:.3f}  "
                      f"미스 {sum(1 for s in vr.scores if not s.recall)}",
                      flush=True)

        # **종류별로 따로 센다** (2회차 README 규칙 3). 처치가 겨누는 곳(`fragment`)과
        # 이미 잘 되는 곳(`control`)을 합쳐 세면, 한쪽의 이득이 다른 쪽의 손해를 덮는다.
        kinds: dict[str, str] = {q["id"]: q.get("kind", "all") for q in labels["queries"]}

        def _subset(res: LegResult, kind: str) -> LegResult:
            out = LegResult(leg=f"{res.leg}:{kind}")
            out.scores = [s for s in res.scores if kinds.get(s.qid) == kind]
            return out

        groups = sorted({k for k in kinds.values() if k != "all"})
        for label, ra, rb in ([("벡터", vec_results["a13_b"], vec_results["a13_a"])] if want_vector
                              else []) + [("키워드", results["a13_b"], results["a13_a"])]:
            compare(ra, rb, f"{label} · 전체")
            for kind in groups:
                sa, sb = _subset(ra, kind), _subset(rb, kind)
                if sa.scores:
                    print(f"    ({kind}: 후보 Recall@10 {sa.recall:.3f} / 현직 {sb.recall:.3f})")
                    compare(sa, sb, f"{label} · {kind}")
    finally:
        for arm in ARMS:
            await db.execute("DELETE FROM chunks WHERE tenant=$1", arm)
            await db.execute("DELETE FROM documents WHERE tenant=$1", arm)
        await db.close_pool()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
