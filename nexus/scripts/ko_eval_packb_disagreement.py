"""라벨 없이, 두 토크나이저가 이 코퍼스에서 **애초에 다른 답을 내놓는지** 잰다.

왜 이것이 먼저인가. Pack B 트리거에 "실질 문서 ≥ 60" 을 넣으면서 근거로 든 것은 측정이 아니라
추론이었다: *gold 후보가 19건뿐이면 두 팔이 같은 소수 문서를 두고 겨뤄 무승부가 쌓이고, 불일치쌍
6 미만 → "검정력 부족" 이 나온다.* 그럴듯하지만 재보지 않았고, 그 추론 하나로 라벨 45건을 세웠다.

**gold 없이도 잴 수 있는 부분이 있다.** 판정에는 정답이 필요하지만, "두 팔이 다른 문서를
돌려주는가" 에는 필요 없다. 그리고 그것이 불일치쌍의 필요조건이다:

    상위 10문서가 같다  →  두 팔의 Recall·MRR 이 같다  →  무승부  →  불일치쌍 0

즉 여기서 차이가 거의 없으면 **라벨을 아무리 잘 써도 검정력 부족**이고, 차이가 넉넉하면 내
"무승부가 쌓인다" 는 주장이 반증된다. 어느 쪽이든 라벨 노동 이전에 알 수 있다.

같이 재는 것 하나 더 — **상위 10에 한 번이라도 뜬 서로 다른 문서 수**. 내 주장의 핵심이
"같은 소수 문서를 두고 겨룬다" 였으므로, 그 소수가 실제로 몇인지가 곧 그 주장의 검증이다.

질의는 `tests/eval/local/` 에서 읽는다. 다른 조직의 정책 문서를 겨눈 질의라 **커밋하지 않는다**
(SPEC-nexus-korean-retrieval-eval §4.1 과 같은 이유).

    docker exec nexus-app python scripts/ko_eval_packb_disagreement.py \
        --nori-url http://host.docker.internal:19200
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.ko_eval_harness import collapse_to_documents  # noqa: E402
from scripts.ko_eval_packb import SNAPSHOT_TENANT, _doc_key  # noqa: E402

LOCAL_DIR = Path(__file__).resolve().parents[1] / "tests" / "eval" / "local"
QUERIES = LOCAL_DIR / "packb-probe-queries.json"

#: 채점 창과 같아야 한다. 다른 깊이로 비교하면 여기서 본 차이가 판정의 차이와 무관해진다.
WINDOW = 10


class _Indexable:
    def __init__(self, text, section):
        self.chunk_text, self.section_path, self.context_prefix = text, section, None


async def _snapshot_rows(con) -> list[dict]:
    rows = await con.fetch(
        "SELECT d.source_uri, c.section_path, c.chunk_index, c.chunk_text "
        "FROM documents d JOIN chunks c ON c.doc_rid = d.rid AND c.tenant = d.tenant "
        "WHERE d.tenant = $1 AND d.status = 'active' AND c.status = 'active' "
        "ORDER BY d.source_uri, c.chunk_index", SNAPSHOT_TENANT)
    return [dict(r) for r in rows]


async def run_arm(tokenizer, rows, queries, pool, tenant: str) -> dict[str, list[str]]:
    """한 팔: 그 토크나이저로 색인하고 **그 토크나이저로** 질의한다.

    색인과 질의가 어긋나면 그럴듯한 숫자가 나오고 아무 의미도 없다 — 그래서 한 컨텍스트 안에서
    한 번만 갈아끼운다 (SPEC-nexus-korean-retrieval-eval §4.3).
    """
    from nexus.index.bm25 import index_chunk_bm25, use_tokenizer
    from nexus.rid import chunk_rid, doc_rid
    from nexus.search import hybrid

    chunk_doc: dict[str, str] = {}
    with use_tokenizer(tokenizer):
        async with pool.acquire() as con:
            await con.execute("DELETE FROM chunks WHERE tenant=$1", tenant)
            await con.execute("DELETE FROM documents WHERE tenant=$1", tenant)
            seen: set[str] = set()
            for r in rows:
                key = _doc_key(r["source_uri"])
                uri = f"{tenant}:{key}"
                drid = doc_rid(uri)
                if key not in seen:
                    await con.execute(
                        "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, "
                        "title, status) VALUES ($1,$2,$3,'h','h',$4,'active')",
                        drid, tenant, uri, key)
                    seen.add(key)
                section = r["section_path"] or "root"
                crid = chunk_rid(drid, section, r["chunk_index"])
                await con.execute(
                    "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, chunk_text, "
                    "section_path, chunk_index, status, hash) VALUES ($1,$2,$3,$4,$5,$6,$7,"
                    "'active','h')",
                    crid, tenant, uri, drid, r["chunk_text"], section, r["chunk_index"])
                await index_chunk_bm25(crid, _Indexable(r["chunk_text"], section))
                chunk_doc[crid] = key

        tops: dict[str, list[str]] = {}
        for q in queries:
            hits = await hybrid._bm25_search(q["query"], tenant, "INTERNAL", WINDOW * 3)
            # 손으로 접지 않는다. 하니스의 접기는 **고아 저장소 가드**를 품고 있다 — 매핑이 빈
            # 채로 접으면 두 팔이 나란히 0 을 내고, 2026-08-05 에 실제로 그 숫자가 나왔다.
            tops[q["id"]] = collapse_to_documents(hits, chunk_doc, limit=WINDOW)
    return tops


def _first_difference_rank(qa: list[str], qb: list[str]) -> int | None:
    """두 순위표가 **처음 갈리는 자리**. 같으면 None.

    이것이 집합 차이보다 판정에 가깝다. 판정은 `Recall@10`(MRR 동점처리)이라, gold 가 그
    갈리는 자리 **이후**에 있어야 승패가 갈린다. 9~10위에서만 갈리는 차이는 gold 가 정확히
    거기 있어야 하고, 그럴 확률은 낮다 — 그런 차이가 아무리 많아도 무승부가 쌓인다.
    """
    for i in range(max(len(qa), len(qb))):
        x = qa[i] if i < len(qa) else None
        y = qb[i] if i < len(qb) else None
        if x != y:
            return i + 1
    return None


def compare(a: dict[str, list[str]], b: dict[str, list[str]], queries) -> dict:
    both_empty = differ = rank1 = 0
    jacc: list[float] = []
    surfaced: set[str] = set()
    examples: list[str] = []
    first_diff: list[int] = []
    for q in queries:
        qa, qb = a.get(q["id"], []), b.get(q["id"], [])
        surfaced.update(qa)
        surfaced.update(qb)
        if not qa and not qb:
            both_empty += 1
            continue
        sa, sb = set(qa), set(qb)
        inter, union = len(sa & sb), len(sa | sb)
        jacc.append(inter / union if union else 1.0)
        if sa != sb:
            differ += 1
            if len(examples) < 5:
                examples.append(f"{q['id']}: 한쪽만 {sorted(sa ^ sb)[:3]}")
        if (qa[:1] or [None]) != (qb[:1] or [None]):
            rank1 += 1
        if (fd := _first_difference_rank(qa, qb)) is not None:
            first_diff.append(fd)
    n = len(queries)
    # 순위표가 갈리는 자리의 분포. 얕을수록(작을수록) 승패로 이어질 여지가 크다.
    hist: dict[str, int] = {}
    for fd in first_diff:
        band = "1-3" if fd <= 3 else "4-6" if fd <= 6 else "7-10"
        hist[band] = hist.get(band, 0) + 1
    return {
        "queries": n,
        "both_empty": both_empty,
        "set_differs": differ,
        "rank1_differs": rank1,
        "order_differs": len(first_diff),
        "first_difference_rank_histogram": hist,
        "first_difference_ranks": sorted(first_diff),
        "mean_jaccard": sum(jacc) / len(jacc) if jacc else 1.0,
        "distinct_documents_surfaced": len(surfaced),
        "examples": examples,
    }


async def _run(args) -> int:
    from nexus import db
    from nexus.index.bm25 import MecabTokenizer, _get_mecab

    from scripts.ko_eval_nori import NoriTokenizer

    if not QUERIES.exists():
        print(f"✗ 탐침 질의가 없다: {QUERIES}")
        return 1
    queries = json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]
    if _get_mecab() is None:
        print("✗ mecab-ko 없음 — 이미지 안에서 실행하라")
        return 1

    mecab, nori = MecabTokenizer(), NoriTokenizer(args.nori_url)
    pool = await db.get_pool()
    try:
        async with pool.acquire() as con:
            rows = await _snapshot_rows(con)
        if not rows:
            print(f"✗ {SNAPSHOT_TENANT} 이 비었다 — 먼저 ko_eval_packb.py freeze")
            return 1
        docs = len({_doc_key(r["source_uri"]) for r in rows})
        print(f"Pack B: 문서 {docs} · 청크 {len(rows)} · 탐침 질의 {len(queries)}")

        # 두 팔은 같은 테넌트를 순서대로 쓴다 — rid 가 테넌트를 품어서, 테넌트가 다르면 동점
        # 정렬 키까지 달라지고 토크나이저와 무관한 차이가 섞인다.
        arm = "ko_eval_arm"
        mecab_tops = await run_arm(mecab, rows, queries, pool, arm)
        nori_tops = await run_arm(nori, rows, queries, pool, arm)
    finally:
        await db.close_pool()

    r = compare(mecab_tops, nori_tops, queries)
    print()
    print(f"  상위{WINDOW} 문서집합이 다른 질의 : {r['set_differs']} / {r['queries']}")
    print(f"  1위 문서가 다른 질의        : {r['rank1_differs']} / {r['queries']}")
    print(f"  평균 자카드 유사도          : {r['mean_jaccard']:.3f}  (1.000 = 완전 동일)")
    print(f"  양쪽 다 빈 결과             : {r['both_empty']}")
    print(f"  상위{WINDOW}에 한 번이라도 뜬 문서 : {r['distinct_documents_surfaced']} / {docs}")
    print(f"  순위표가 갈리는 질의        : {r['order_differs']} / {r['queries']}")
    print(f"    처음 갈리는 자리 분포     : {r['first_difference_rank_histogram']}")
    for e in r["examples"]:
        print(f"    {e}")
    print()
    # **이것이 판정에 가장 가까운 숫자다.** 판정은 Recall@10(MRR 동점처리)이라, gold 가 갈리는
    # 자리 이후에 있어야 승패가 생긴다. 얕게 갈릴수록 그럴 여지가 크다.
    shallow = r["first_difference_rank_histogram"].get("1-3", 0)
    print(f"  → 상위 3위 안에서 갈리는 질의 {shallow}건.")
    if shallow >= 6:
        print("     승패가 생길 자리가 있다 — '무승부만 쌓인다' 는 추론은 지지되지 않는다.")
    else:
        print("     차이가 대부분 꼬리에 있다. gold 가 하필 그 자리에 있어야 승패가 갈리므로,")
        print("     라벨을 써도 무승부가 쌓일 공산이 크다.")
    print("     (어느 쪽이든 필요조건일 뿐이다 — 둘 다 gold 를 잡으면 자리에 무관하게 무승부다)")

    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    out = LOCAL_DIR / "packb-disagreement.json"
    out.write_text(json.dumps({"window": WINDOW, "documents": docs, **r},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"  기록: {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--nori-url", default="http://host.docker.internal:19200")
    args = ap.parse_args(argv)
    if not os.getenv("DATABASE_URL"):
        print("✗ DATABASE_URL 이 없다")
        return 1
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
