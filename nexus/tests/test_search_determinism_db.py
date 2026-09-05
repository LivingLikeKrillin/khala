"""검색 결정성 — 같은 코퍼스·같은 질의면 같은 답 (SPEC-nexus-deterministic-retrieval-order §6).

이 결함은 **한국어 평가셋이 잡았다.** 같은 팩을 두 번 적재하면 tsvector 집계 md5 가 같은데도
Recall@10 이 0.700~0.775 로 갈렸다. 원인은 `ORDER BY rank_score DESC` 에 전순서 키가 없어서
동점 안 순서가 물리적 행 순서를 따라간 것이다.

여기 테스트는 **같은 테넌트에 세 번 재적재**한다. 테넌트를 바꾸면 rid 가 테넌트를 품고 있어
순서가 **정당하게** 달라지므로, 두 테넌트 비교는 이 결함을 측정하는 평가 하니스가 못 된다.

경험적 절반(재적재 일치)은 결함을 잡은 바로 그 방식이고, 구조적 절반(ORDER BY 가 기본키로 끝난다)
은 흔들릴 수 없는 쪽이다. 둘 다 둔다.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요"),
]

_TENANT = "determinism"
_RELOADS = 3

_DOCS = {
    "alpha": "## 파드 배치\n\n노드에 파드를 배치할 때는 어피니티와 테인트를 함께 본다.",
    "bravo": "## 파드 배치 규칙\n\n노드 셀렉터와 어피니티로 파드 배치를 제어한다.",
    "charlie": "## 노드 관리\n\n노드를 드레인하면 파드가 다른 노드로 옮겨간다.",
    "delta": "## 테인트\n\n노드에 테인트를 걸면 톨러레이션 없는 파드는 배치되지 않는다.",
    "echo": "## 파드\n\n파드는 배치의 최소 단위다. 노드 위에서 돈다.",
}
_QUERIES = ["노드에 파드를 배치하는 규칙", "테인트와 톨러레이션", "파드가 옮겨가는 경우"]


async def _load(con, tenant: str) -> None:
    """같은 테넌트에 통째로 다시 적재한다 — 삭제 후 삽입이라 물리적 행 순서가 바뀐다."""
    from nexus.index.bm25 import index_chunk_bm25
    from nexus.rid import chunk_rid, doc_rid

    await con.execute("DELETE FROM chunks WHERE tenant=$1", tenant)
    await con.execute("DELETE FROM documents WHERE tenant=$1", tenant)

    class _C:
        def __init__(self, text):
            self.chunk_text, self.section_path, self.context_prefix = text, "root", None

    for key, text in _DOCS.items():
        uri = f"{tenant}:{key}.md"
        drid = doc_rid(uri)
        await con.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title, status) "
            "VALUES ($1,$2,$3,'h','h',$4,'active')", drid, tenant, uri, key)
        crid = chunk_rid(drid, "root", 0)
        await con.execute(
            "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, chunk_text, section_path, "
            "chunk_index, status, hash) VALUES ($1,$2,$3,$4,$5,'root',0,'active','h')",
            crid, tenant, uri, drid, text)
        await index_chunk_bm25(crid, _C(text))


@pytest.fixture
async def reloads(db_pool):
    """세 번 재적재하면서 매번 키워드 경로 결과를 받아 둔다."""
    from nexus import db
    from nexus.search import hybrid

    db._pool = db_pool
    runs = []
    for _ in range(_RELOADS):
        async with db_pool.acquire() as con:
            await _load(con, _TENANT)
        runs.append({q: (await hybrid._bm25_search(q, _TENANT, "INTERNAL", 20))[0] for q in _QUERIES})

    yield runs

    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    db._pool = None


async def test_the_keyword_leg_returns_the_same_order_after_every_reload(reloads):
    """결함을 잡은 그 비교. 적재본이 달라도 답은 같아야 한다."""
    first = reloads[0]
    for q in _QUERIES:
        assert first[q], f"'{q}' 가 아무것도 반환하지 않았다 — 빈 결과는 결정성을 증명하지 못한다"
    for i, run in enumerate(reloads[1:], start=2):
        for q in _QUERIES:
            assert run[q] == first[q], f"{i}번째 적재에서 '{q}' 의 순서가 달라졌다"


async def test_the_hits_a_user_sees_are_stable_across_reloads(db_pool):
    """경로가 아니라 **사용자가 보는 층**(융합·다양화·final_top_k 이후)에서 확인한다."""
    from nexus import db
    from nexus.search import hybrid

    db._pool = db_pool
    orders = []
    for _ in range(_RELOADS):
        async with db_pool.acquire() as con:
            await _load(con, _TENANT)
        res = await hybrid.hybrid_search("노드에 파드를 배치하는 규칙", tenant=_TENANT, top_k=5,
                                         embedding_svc=None, route="keyword_only")
        orders.append([h.rid for h in res.hits])
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    db._pool = None

    assert orders[0], "빈 결과로는 결정성을 증명하지 못한다"
    assert orders[0] == orders[1] == orders[2], f"사용자가 보는 순서가 적재본마다 달라진다: {orders}"


async def test_the_scored_match_set_is_unchanged_by_the_tie_break(reloads):
    """이 SPEC 은 동점 순서만 바꾼다 — **한계 아래의** (rid, score) 집합은 그대로여야 한다.

    잘린 집합은 불변이 아니다(동점이 LIMIT 경계를 걸치면 살아남는 쪽이 바뀐다). 그래서 한계를
    매칭 행 수보다 크게 두고 측정한다 — 실제로 성립하는 불변식만 단언한다.
    """
    from nexus import db
    from nexus.index.bm25 import active_tokenizer, tokens_to_tsquery

    for q in _QUERIES:
        tsq = tokens_to_tsquery(active_tokenizer().tokenize(q))
        rows = await db.fetch_all(
            "SELECT c.rid, ts_rank_cd(c.tsvector_ko, to_tsquery('simple',$1)) s FROM chunks c "
            "WHERE c.tsvector_ko @@ to_tsquery('simple',$1) AND c.tenant=$2 AND c.status='active' "
            "ORDER BY s DESC, c.rid ASC LIMIT 1000", tsq, _TENANT)
        with_tie = {(r["rid"], round(float(r["s"]), 9)) for r in rows}
        rows = await db.fetch_all(
            "SELECT c.rid, ts_rank_cd(c.tsvector_ko, to_tsquery('simple',$1)) s FROM chunks c "
            "WHERE c.tsvector_ko @@ to_tsquery('simple',$1) AND c.tenant=$2 AND c.status='active' "
            "ORDER BY s DESC LIMIT 1000", tsq, _TENANT)
        without_tie = {(r["rid"], round(float(r["s"]), 9)) for r in rows}
        assert with_tie == without_tie, f"'{q}' — 동점 키가 점수/매칭을 바꿨다"


async def test_the_vector_leg_reload_behaviour_is_measured_not_assumed(db_pool):
    """벡터 경로는 ivfflat(ANN) 이라 **후보 집합**이 흔들릴 수 있다 (SPEC §4.3).

    임베딩을 심어 두 적재본을 비교하고, 어긋나면 '정렬 키가 깨졌다' 가 아니라 '후보 집합이
    흔들렸다' 로 읽히도록 메시지를 붙인다.
    """
    from nexus import db
    from nexus.search import hybrid

    db._pool = db_pool

    class _Fixed:
        async def embed_query(self, _text):
            return [0.1] * 768

    orders = []
    for _ in range(_RELOADS):
        async with db_pool.acquire() as con:
            await _load(con, _TENANT)
            await con.execute(
                "UPDATE chunks SET embedding = $1::vector WHERE tenant=$2",
                "[" + ",".join(["0.1"] * 768) + "]", _TENANT)
        orders.append((await hybrid._vector_search("파드", _Fixed(), _TENANT, "INTERNAL", 20))[0])

    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    db._pool = None

    assert orders[0] == orders[1] == orders[2], (
        "벡터 경로가 적재본마다 다른 결과를 냈다. 동점 키는 걸려 있으므로 원인은 "
        "**ivfflat 후보 집합**일 가능성이 높다 (SPEC-nexus-deterministic-retrieval-order §4.3) — "
        f"정렬 키 문제로 읽지 말 것. 결과: {[[h.rid for h in o] for o in orders]}")


# ── 흔들릴 수 없는 절반 ──────────────────────────────────────────────────────


def test_both_legs_order_by_the_primary_key_last():
    """경험적 재적재 비교는 우연히 통과할 수 있다. 이 단언은 그럴 수 없다."""
    src = (Path(__file__).resolve().parents[1] / "nexus" / "search" / "hybrid.py").read_text(
        encoding="utf-8")
    orders = re.findall(r"ORDER BY ([^\n]+)", src)
    assert orders, "ORDER BY 절을 못 찾았다 — 이 테스트가 겨누는 코드가 사라졌는지 확인하라"
    for clause in orders:
        assert clause.rstrip().endswith("c.rid ASC"), f"전순서가 아니다: ORDER BY {clause}"


def test_the_fusion_sort_key_is_explicit_not_inherited():
    """안정 정렬에 기대면 리팩터 한 번에 비결정성이 조용히 돌아온다 (SPEC §4.1)."""
    from nexus.search.hybrid import _rrf_fusion

    a = _rrf_fusion([("c_z", 1), ("c_a", 1)], [], k=60)
    b = _rrf_fusion([("c_a", 1), ("c_z", 1)], [], k=60)
    assert [x["rid"] for x in a] == [x["rid"] for x in b] == ["c_a", "c_z"], (
        "같은 점수의 입력 순서만 바꿨는데 융합 결과 순서가 달라진다")
