"""평가용 벡터 다리 — 정확 스캔·스테일 가드·음성 대조군
(SPEC-nexus-korean-embedding-comparison §4.1~§4.2, §6).

**"같은 모델 두 번 돌리면 같은 결과" 는 결정성만 증명한다.** 그건 이 하니스가 모델 차이를
잡아낼 수 있는지에 대해 아무 말도 하지 않는다 — ADR-0008 §2.6 이 이름 붙인 바로 그 구멍이다.
그래서 진짜 대조군은 **벡터를 청크 사이에서 뒤섞는 것**이다: 뒤섞은 실험군이 여전히 점수를 내면
이 다리는 아무것도 재고 있지 않다.

임베딩은 여기서 가짜다(결정적 해시 기반). 실제 모델은 Unit 3 이고, 이 파일이 지키는 것은
**배관과 가드**다 — 스테일 arm 이 조용히 채점되는 것을 막는 쪽이 모델보다 먼저다.
"""

from __future__ import annotations

import hashlib
import math
import os
import random

import pytest

from scripts.ko_eval_harness import collapse_to_documents, score_query
from scripts.ko_eval_vector import (
    MODELS,
    EmbedRow,
    ensure_table,
    input_hash,
    replace_arm,
    vector_search,
    verify_arm,
)

pytestmark = [
    pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요"),
]

_TENANT = "ko_eval_vec"
_PACK = "test-pack"
_MODEL = "nomic-embed-text"
_DIM = MODELS[_MODEL]["dim"]

#: fixture 는 **조회 창보다 훨씬 커야 한다.** 처음엔 5문서로 짰다가 음성 대조군이 실패했다 —
#: 5문서/창10 이면 정답이 항상 창 안에 있어 벡터를 아무리 뒤섞어도 만점이 나온다. 옛 리콜
#: 스위트를 무의미하게 만든 바로 그 결함(코퍼스 < 조회 창)을 fixture 에서 반복할 뻔했다.
_DOCS = {f"doc{i:02d}.md": f"{i}번 주제에 대한 설명 문서. 서로 다른 내용을 담는다." for i in range(40)}
_NAMED = {"pod.md": "파드는 배치의 최소 단위다", "node.md": "노드는 파드를 실행하는 머신이다"}
_DOCS.update(_NAMED)


def _vec(text: str, dim: int = _DIM) -> list[float]:
    """텍스트 → 결정적 단위 벡터. 같은 텍스트는 같은 벡터, 다른 텍스트는 거의 직교."""
    rng = random.Random(hashlib.sha256(text.encode("utf-8")).digest())
    v = [rng.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


@pytest.fixture
async def arm(db_pool):
    """청크 42건(조회 창 10보다 훨씬 크게)을 적재하고 그 위에 임베딩 arm 을 만든다."""
    from nexus import db
    from nexus.rid import chunk_rid, doc_rid

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await ensure_table(con)
        await con.execute("DELETE FROM ko_eval_embeddings WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)

        rows, rid_of, inputs = [], {}, {}
        for name, text in _DOCS.items():
            uri = f"{_TENANT}:{name}"
            drid = doc_rid(uri)
            await con.execute(
                "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title, status) "
                "VALUES ($1,$2,$3,'h','h',$4,'active')", drid, _TENANT, uri, name)
            crid = chunk_rid(drid, "root", 0)
            await con.execute(
                "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, chunk_text, section_path, "
                "chunk_index, status, hash) VALUES ($1,$2,$3,$4,$5,'root',0,'active','h')",
                crid, _TENANT, uri, drid, text)
            rid_of[name] = crid
            inputs[crid] = (input_hash(text), input_hash(text))
            rows.append(EmbedRow(chunk_rid=crid, input_sha256=input_hash(text),
                                 payload_sha256=input_hash(text), embedding=_vec(text)))

        await replace_arm(con, _MODEL, _TENANT, _PACK, rows)

    yield {"rid_of": rid_of, "inputs": inputs, "chunk_doc": {v: k for k, v in rid_of.items()}}

    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM ko_eval_embeddings WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    db._pool = None


# ── 정확 스캔 ────────────────────────────────────────────────────────────────


async def test_the_exact_scan_finds_the_document_its_own_vector_came_from(db_pool, arm):
    async with db_pool.acquire() as con:
        for name, text in _DOCS.items():
            hits = await vector_search(con, _MODEL, _TENANT, _PACK, _vec(text), top_k=20)
            docs = collapse_to_documents(hits, arm["chunk_doc"])
            assert docs[0] == name, f"'{name}' 의 벡터로 질의했는데 1위가 {docs[0]}"


async def test_the_scan_is_stable_across_repeated_queries(db_pool, arm):
    async with db_pool.acquire() as con:
        q = _vec(_DOCS["pod.md"])
        runs = [await vector_search(con, _MODEL, _TENANT, _PACK, q, top_k=20) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]


async def test_the_arm_is_isolated_from_the_production_column(db_pool, arm):
    """평가용 임베딩은 `chunks.embedding` 을 절대 건드리지 않는다 — 조용한 코퍼스 오염이 실패 유형."""
    from nexus import db

    n = await db.fetch_val(
        "SELECT count(*) FROM chunks WHERE tenant=$1 AND embedding IS NOT NULL", _TENANT)
    assert n == 0


# ── 스테일 arm 가드 ──────────────────────────────────────────────────────────


async def test_a_fresh_arm_verifies(db_pool, arm):
    async with db_pool.acquire() as con:
        assert await verify_arm(con, _MODEL, _TENANT, _PACK, arm["inputs"]) == []


async def test_an_arm_pointing_at_dead_chunks_fails(db_pool, arm):
    """청크를 지웠다 다시 넣으면 rid 는 같지만, 다른 테넌트/적재본의 잔재는 이렇게 잡힌다."""
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        problems = await verify_arm(con, _MODEL, _TENANT, _PACK, arm["inputs"])
    assert any("살아 있는 청크가 없는" in p.reason for p in problems)


async def test_an_arm_missing_a_chunk_fails(db_pool, arm):
    async with db_pool.acquire() as con:
        await con.execute(
            "DELETE FROM ko_eval_embeddings WHERE model=$1 AND tenant=$2 AND chunk_rid=$3",
            _MODEL, _TENANT, arm["rid_of"]["pod.md"])
        problems = await verify_arm(con, _MODEL, _TENANT, _PACK, arm["inputs"])
    assert any("임베딩도 거부도 없는 청크" in p.reason for p in problems)
    assert any("≠ 팩의 현재 청크" in p.reason for p in problems)


async def test_an_arm_embedded_from_different_text_fails(db_pool, arm):
    """청크 텍스트가 바뀌었는데 임베딩이 그대로면, 개수는 맞고 내용은 거짓말이다."""
    changed = dict(arm["inputs"])
    changed[arm["rid_of"]["pod.md"]] = (input_hash("완전히 다른 본문"), input_hash("완전히 다른 본문"))
    async with db_pool.acquire() as con:
        problems = await verify_arm(con, _MODEL, _TENANT, _PACK, changed)
    assert any("지금 만들 문자열과 다르다" in p.reason for p in problems)


async def test_a_dimension_mismatch_is_refused_rather_than_padded(db_pool, arm):
    async with db_pool.acquire() as con:
        with pytest.raises(ValueError, match="차원"):
            await replace_arm(con, _MODEL, _TENANT, _PACK,
                              [EmbedRow(chunk_rid=arm["rid_of"]["pod.md"], input_sha256="h",
                                        payload_sha256="h", embedding=[0.1] * (_DIM - 1))])


async def test_replacing_an_arm_does_not_merge_generations(db_pool, arm):
    """세대 혼재는 병합에서 온다. 통째 교체면 원리적으로 못 생긴다."""
    async with db_pool.acquire() as con:
        await replace_arm(con, _MODEL, _TENANT, _PACK,
                          [EmbedRow(chunk_rid=arm["rid_of"]["pod.md"],
                                    input_sha256=input_hash(_DOCS["pod.md"]),
                                    payload_sha256=input_hash(_DOCS["pod.md"]),
                                    embedding=_vec(_DOCS["pod.md"]))])
        n = await con.fetchval(
            "SELECT count(*) FROM ko_eval_embeddings WHERE model=$1 AND tenant=$2", _MODEL, _TENANT)
    assert n == 1, "이전 세대 행이 남았다"


# ── 음성 대조군: 이 다리가 나쁜 모델을 잡아낼 수 있는가 ─────────────────────


async def test_shuffled_vectors_collapse_the_vector_leg(db_pool, arm):
    """**뒤섞은 실험군이 여전히 점수를 내면 이 다리는 아무것도 재고 있지 않다.**

    각 문서를 자기 벡터로 질의하는 판이라 온전한 실험군은 만점이어야 하고, 벡터를 청크 사이에서
    돌리면 무너져야 한다. '같은 모델 두 번' 류의 자명한 확인과 달리 이건 실패할 수 있다 —
    실제로 처음 작성한 5문서 fixture 에서 실패했고, 그 실패가 fixture 가 창보다 작다는 것을
    알려줬다(코퍼스 42 · 창 10).
    """
    names = list(_DOCS)
    gold = {n: [n] for n in names}

    async with db_pool.acquire() as con:
        intact = []
        for name, text in _DOCS.items():
            hits = await vector_search(con, _MODEL, _TENANT, _PACK, _vec(text), top_k=20)
            intact.append(score_query(name, collapse_to_documents(hits, arm["chunk_doc"]), gold[name]))

        # 벡터를 한 칸씩 밀어 청크-벡터 대응을 깨뜨린다 (텍스트·해시·개수는 그대로)
        rotated = names[1:] + names[:1]
        await replace_arm(con, _MODEL, _TENANT, _PACK,
                          [EmbedRow(chunk_rid=arm["rid_of"][n], input_sha256=input_hash(_DOCS[n]),
                                    payload_sha256=input_hash(_DOCS[n]),
                                    embedding=_vec(_DOCS[other]))
                           for n, other in zip(names, rotated, strict=True)])

        shuffled = []
        for name, text in _DOCS.items():
            hits = await vector_search(con, _MODEL, _TENANT, _PACK, _vec(text), top_k=20)
            shuffled.append(score_query(name, collapse_to_documents(hits, arm["chunk_doc"]), gold[name]))

    intact_recall = sum(s.recall for s in intact) / len(intact)
    shuffled_recall = sum(s.recall for s in shuffled) / len(shuffled)
    assert intact_recall == 1.0, f"온전한 실험군이 만점이 아니다 ({intact_recall:.2f}) — 배관이 틀렸다"
    assert shuffled_recall < intact_recall * 0.5, (
        f"뒤섞은 실험군의 재현율이 {shuffled_recall:.2f} (온전 {intact_recall:.2f}) — "
        "이 벡터 다리는 나쁜 임베딩을 잡아내지 못한다")
