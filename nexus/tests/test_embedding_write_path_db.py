"""적재는 **설정된 세대의 컬럼**에 쓴다 (SPEC-nexus-embedding-cutover-seam §4.3, §6).

컬럼이 하드코딩돼 있으면 컷오버 뒤 새로 적재된 청크가 옛 컬럼만 채우고 새 컬럼은 NULL 로 남는다.
아무것도 예외를 내지 않고, 그 청크는 벡터 검색에서 조용히 사라진다 — 이 스위트가 막는 것이 그
모양이다. 그리고 그 반대편, 즉 **롤백이 남기는 구멍**도 여기서 숫자로 확인한다: flip 이후 적재된
청크는 옛 컬럼이 NULL 이므로, 롤백하면 그만큼이 키워드 전용이 된다.
"""

from __future__ import annotations

import os

import pytest

from nexus.index.embed import index_chunk_embedding, index_chunks_embedding

pytestmark = [
    pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요"),
]

_TENANT = "write_path_test"


def _vec(text: str, dim: int) -> list[float]:
    """텍스트에서 결정되는 벡터 — 상수를 돌려주는 가짜는 정렬 어긋남을 원리적으로 통과시킨다."""
    import hashlib
    import math
    import random

    rng = random.Random(hashlib.sha256(f"{text}:{dim}".encode()).digest())
    v = [rng.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class _Svc:
    def __init__(self, model: str, dim: int):
        self.model, self.dim = model, dim

    def get_model_name(self) -> str:
        return self.model

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_vec(t, self.dim) for t in texts]


class _Chunk:
    def __init__(self, text: str):
        self.chunk_text, self.section_path, self.context_prefix = text, "root", ""


@pytest.fixture
async def corpus(db_pool):
    from nexus import db
    from nexus.rid import chunk_rid, doc_rid

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
        rids = {}
        for name, text in [("a", "파드 개요"), ("b", "노드 개요")]:
            uri = f"{_TENANT}:{name}.md"
            drid = doc_rid(uri)
            await con.execute(
                "INSERT INTO documents (rid,tenant,source_uri,hash,content_hash,title,status) "
                "VALUES ($1,$2,$3,'h','h',$4,'active')", drid, _TENANT, uri, name)
            crid = chunk_rid(drid, "root", 0)
            await con.execute(
                "INSERT INTO chunks (rid,tenant,source_uri,doc_rid,chunk_text,section_path,"
                "chunk_index,status,hash) VALUES ($1,$2,$3,$4,$5,'root',0,'active','h')",
                crid, _TENANT, uri, drid, text)
            rids[name] = crid
    yield rids
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    db._pool = None


async def _columns_of(rid: str) -> tuple[bool, bool]:
    """(옛 컬럼이 찼는가, 새 컬럼이 찼는가). **설정이 아니라 컬럼을 읽어서** 판정한다."""
    from nexus import db

    row = await db.fetch_all(
        "SELECT embedding IS NOT NULL AS old, embedding_1024 IS NOT NULL AS new "
        "FROM chunks WHERE rid = $1", rid)
    return bool(row[0]["old"]), bool(row[0]["new"])


@pytest.mark.parametrize("column,model,dim,expected", [
    ("embedding", "nomic-embed-text", 768, (True, False)),
    ("embedding_1024", "KURE-v1", 1024, (False, True)),
])
async def test_the_write_lands_in_the_configured_column(corpus, column, model, dim, expected):
    ok = await index_chunk_embedding(corpus["a"], _Chunk("파드 개요"), _Svc(model, dim),
                                     column=column)
    assert ok is True
    assert await _columns_of(corpus["a"]) == expected


@pytest.mark.parametrize("column,model,dim,expected", [
    ("embedding", "nomic-embed-text", 768, (True, False)),
    ("embedding_1024", "KURE-v1", 1024, (False, True)),
])
async def test_the_batch_write_lands_in_the_configured_column(corpus, column, model, dim,
                                                              expected):
    n = await index_chunks_embedding(
        [(corpus["a"], _Chunk("파드 개요")), (corpus["b"], _Chunk("노드 개요"))],
        _Svc(model, dim), column=column)
    assert n == 2
    for name in ("a", "b"):
        assert await _columns_of(corpus[name]) == expected


async def test_the_env_decides_when_the_caller_does_not(corpus, monkeypatch):
    """적재 경로가 설정을 안 받고 불릴 수도 있다. 그때 기본값이 옛 컬럼이면 컷오버가 무너진다."""
    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", "embedding_1024")
    await index_chunk_embedding(corpus["a"], _Chunk("파드 개요"), _Svc("KURE-v1", 1024))
    assert await _columns_of(corpus["a"]) == (False, True)


async def test_a_chunk_ingested_after_the_flip_is_counted_by_the_rollback_gap(corpus):
    """§4.3 이 이름 붙인 구멍이 **측정 가능한 숫자**인지 — 롤백 판단이 여기에 걸려 있다."""
    from nexus.index.reembed import counts

    await index_chunks_embedding(
        [(corpus["a"], _Chunk("파드 개요")), (corpus["b"], _Chunk("노드 개요"))],
        _Svc("KURE-v1", 1024), column="embedding_1024")

    old = await counts("embedding", _TENANT)
    assert old["pending"] == 2, (
        "flip 이후 적재된 청크는 옛 컬럼이 비어 있다 — 롤백하면 그만큼이 키워드 전용이 된다. "
        "운영자는 이 숫자를 보고 롤백을 판단한다")
