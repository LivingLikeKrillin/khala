"""단계 span — **등록된 문**. 이 시험 하나가 이 단위 전체의 통과 기준이다.

`test_spans_store_db.py`/`test_spans_purge_db.py` 는 `SpanSet` 을 손으로 만들어 저장 계층만
본다. 이 시험은 그 아래 — `hybrid_search` 가 실제로 두 다리를 **돌려서** 만든 `SpanSet` 을
그대로 저장하고, 저장된 행을 다시 읽어 계약을 확인한다.

**두 다리 다 돈다. 순위로 흉내내지 않는다.**

- **벡터 쪽은 스텁 임베더다.** 벡터는 픽스처 데이터이지 모델 호출이 아니다. 실제 모델을 쓰면
  기대 순위가 "모델의 성질"이 되어, 모델이나 차원이 바뀌면 이 시험이 조용히 깨진다.
- **BM25 쪽은 구조적으로 빈다.** 정답 청크는 질의 어휘를 **하나도** 담지 않는다 — 그래서 BM25
  풀에 아예 들어올 수 없다. `ts_rank_cd` 로 밀어내는 방식은 쓰지 않는다: 풀 안 순위는
  `ts_rank_cd`·한국어 tsvector 설정·`bm25_top_k` 라는 진짜 코드의 성질이라 토크나이저나 사전이
  바뀌면 흔들린다. 그 불안정함이 정확히 벡터 쪽을 스텁으로 둔 이유다.

세 청크로 두 다리의 순서가 **서로 다르게** 나오도록 설계했다 — 그래야 "융합이 두 다리를 각자
읽어 합친다" 는 것이 우연이 아니라 구성으로 보인다:

    청크          BM25 풀 순위        벡터 풀 순위(코사인 거리)
    bm25_strong   1위 (밀도 최고)      3위 (거리 최대)
    bm25_weak     2위 (widget 1회)     1위 (거리 최소)
    gold          없음(어휘 0 개 겹침)  2위 (알려진 순위)

LLM 은 부르지 않는다 — 검색만, 그래서 값싸고 결정적이다.
"""
from __future__ import annotations

import os

import pytest

from nexus import db
from nexus.index.bm25 import index_chunk_bm25
from nexus.rid import chunk_rid, doc_rid
from nexus.search.hybrid import hybrid_search
from nexus.search.signals import extract_signals, record_search

pytestmark = pytest.mark.asyncio

_DB = os.getenv("NEXUS_TEST_DB_URL")
_TENANT = "spans_gate_ut1"
_PATH = "test_spans_gate"
_QUERY = "widget calibration alpha"
_DIM = 768

#: 청크 본문. `gold` 는 질의 어휘(widget/calibration/alpha)와 **글자 하나 겹치지 않는다** —
#: 그래야 BM25 부재가 순위 다툼이 아니라 애초에 못 들어온 것임이 구성만으로 보장된다.
_DOCS = {
    "bm25_strong": "widget calibration alpha widget calibration widget alpha steps procedure",
    "bm25_weak": "widget summary notes overview",
    "gold": "coffee brewing kettle temperature notes",
}

#: (dim0, dim1) — 나머지는 0. pgvector 의 `<=>` 는 코사인 거리라 내적/노름으로 정규화되므로
#: 벡터를 단위 길이로 맞출 필요가 없다. 질의 벡터 (1,0) 기준 코사인 거리를 손으로 계산해
#: 순위를 미리 안다: near(0.00496) < gold(0.10557) < far(0.55279).
_QUERY_VEC = (1.0, 0.0)
_VECTORS = {
    "bm25_weak": (1.0, 0.1),    # 가장 가깝다 → 벡터 풀 1위
    "gold": (1.0, 0.5),         # → 벡터 풀 2위 — 이 값이 "알려진 순위" 다
    "bm25_strong": (1.0, 2.0),  # 가장 멀다 → 벡터 풀 3위
}


def _vec(a: float, b: float) -> str:
    return "[" + ",".join(str(v) for v in [a, b] + [0.0] * (_DIM - 2)) + "]"


class _StubEmbedder:
    """벡터는 모델 호출이 아니라 고정 픽스처다 — 머리말 참조."""

    async def embed_query(self, _text: str) -> list[float]:
        a, b = _QUERY_VEC
        return [a, b] + [0.0] * (_DIM - 2)


class _Chunk:
    def __init__(self, text: str):
        self.chunk_text, self.section_path, self.context_prefix = text, "root", None


@pytest.fixture(autouse=True)
async def _db_pool():
    """`test_spans_store_db.py` 와 같은 관례 — `nexus.db` 전역 풀을 직접 연다."""
    os.environ["DATABASE_URL"] = _DB or ""
    await db.get_pool()
    yield
    await db.close_pool()


async def _seed() -> dict[str, str]:
    """세 문서/청크를 심고 chunk key → chunk_rid 를 돌려준다."""
    rids: dict[str, str] = {}
    for key, text in _DOCS.items():
        uri = f"{_TENANT}:{key}.md"
        drid = doc_rid(uri)
        await db.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title, status) "
            "VALUES ($1,$2,$3,'h','h',$4,'active')", drid, _TENANT, uri, key)
        crid = chunk_rid(drid, "root", 0)
        await db.execute(
            "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, chunk_text, section_path, "
            "chunk_index, status, hash) VALUES ($1,$2,$3,$4,$5,'root',0,'active','h')",
            crid, _TENANT, uri, drid, text)
        await index_chunk_bm25(crid, _Chunk(text))
        a, b = _VECTORS[key]
        await db.execute("UPDATE chunks SET embedding = $1::vector WHERE rid = $2", _vec(a, b), crid)
        rids[key] = crid
    return rids


async def _leg_rows(log_id: int, leg: str) -> list:
    return await db.fetch_all(
        """SELECT c.rank, c.chunk_rid, c.doc_rid, c.raw_score
           FROM search_span s JOIN search_span_candidate c ON c.span_id = s.id
           WHERE s.search_log_id = $1 AND s.stage = 'leg' AND s.leg = $2
           ORDER BY c.rank""", log_id, leg)


@pytest.mark.integration
async def test_both_legs_built_gold_absent_from_bm25_ranked_in_vector(clean_db):
    rids = await _seed()
    try:
        result = await hybrid_search(
            _QUERY, tenant=_TENANT, clearance="INTERNAL", top_k=10,
            embedding_svc=_StubEmbedder(), route="hybrid_only",
            config={"spans": {"enabled": True, "max_candidates_per_span": 100}, "search": {}},
        )
        assert result.spans is not None, "spans.enabled=True 인데 SpanSet 이 안 만들어졌다"

        sig = extract_signals(
            result, None, path=_PATH, tenant=_TENANT, clearance="INTERNAL",
            query=_QUERY, latency_ms=1)
        await record_search(sig, await_persist=True, spans=result.spans)

        row = await db.fetch_one(
            "SELECT id, spans_expected FROM search_log WHERE path = $1 "
            "ORDER BY id DESC LIMIT 1", _PATH)
        log_id = row["id"]

        bm25_rows = await _leg_rows(log_id, "bm25")
        vector_rows = await _leg_rows(log_id, "vector")
        fusion_rows = await db.fetch_all(
            """SELECT c.rank, c.chunk_rid FROM search_span s
               JOIN search_span_candidate c ON c.span_id = s.id
               WHERE s.search_log_id = $1 AND s.stage = 'fusion'
               ORDER BY c.rank""", log_id)

        # (1) 정답 청크는 BM25 풀에 아예 없다 — 어느 자리에서도 잘리지 않았다, 애초에 못 들어왔다.
        bm25_rids = {r["chunk_rid"] for r in bm25_rows}
        assert rids["gold"] not in bm25_rids
        assert bm25_rids == {rids["bm25_strong"], rids["bm25_weak"]}

        # (2) 정답 청크는 벡터 풀에 있고, 그 순위는 손으로 계산해 미리 안 값이다(머리말 참조).
        vector_by_rid = {r["chunk_rid"]: r for r in vector_rows}
        assert rids["gold"] in vector_by_rid
        assert vector_by_rid[rids["gold"]]["rank"] == 2

        # (3) 정답 청크는 fusion span 에도 있다 — 벡터 다리 하나만으로 융합에 들어왔다는 뜻이다.
        assert rids["gold"] in {r["chunk_rid"] for r in fusion_rows}

        # (4) seq 는 1부터 조밀하고, search_log.spans_expected 는 실제로 쓰인 행 수와 같다.
        seqs = [r["seq"] for r in await db.fetch_all(
            "SELECT seq FROM search_span WHERE search_log_id = $1 ORDER BY seq", log_id)]
        assert seqs == list(range(1, len(seqs) + 1))
        actual_span_rows = await db.fetch_val(
            "SELECT count(*) FROM search_span WHERE search_log_id = $1", log_id)
        assert row["spans_expected"] == actual_span_rows == len(seqs)

        # (5) 후보 행은 raw_score 를 담고, 다리별 극성대로 정렬돼 있다(저장 왕복 후에도).
        assert all(r["raw_score"] is not None for r in bm25_rows)
        bm25_scores = [r["raw_score"] for r in bm25_rows]
        assert bm25_scores == sorted(bm25_scores, reverse=True)
        assert bm25_scores[0] > bm25_scores[-1], "두 점수가 같으면 내림차순 계약이 시험되지 않는다"

        assert all(r["raw_score"] is not None for r in vector_rows)
        vector_dists = [r["raw_score"] for r in vector_rows]
        assert vector_dists == sorted(vector_dists)
        assert vector_dists[0] < vector_dists[-1], "두 거리가 같으면 오름차순 계약이 시험되지 않는다"
    finally:
        await db.execute("DELETE FROM search_log WHERE path = $1", _PATH)
        await db.execute("DELETE FROM documents WHERE tenant = $1", _TENANT)
