"""앵커 상태 집합 쿼리를 **진짜 Postgres 에** 대고 돌린다.

단위 시험은 `db.fetch_all` 을 가짜로 바꿔 놓고 판정 규칙만 잰다 — 그러면 SQL 자체는
한 번도 실행되지 않는다. 이 리포는 '테스트 초록인데 동작 안 함' 을 네 형태로 겪었고,
그중 하나가 정확히 이것이었다(사본이 정본 그물 밖). 여기서 실행되는 것:

- `LEFT JOIN` + `count(*) FILTER` 가 네 상태를 실제로 구별하는가
- 앵커가 없는 테넌트에서 조용히 빈 결과인가 (평가 팩 경로)
- 쿼리 **한 번**으로 여러 청크의 앵커가 각자 자기 청크로 돌아오는가
"""

from __future__ import annotations

import os

import pytest

from nexus.index.anchors import AMBIGUOUS_NOW, CHANGED, FRESH, ORPHANED
from nexus.search.anchor_status import statuses_for_chunks

pytestmark = [
    pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요"),
]

_TENANT = "anchor_status_test"
_REPO = "sample-app"


@pytest.fixture
async def corpus(db_pool):
    """청크 둘 · 심볼 셋 · 앵커 넷 — 네 상태가 한 번에 나오도록 짠 것.

    ⚠ 이름은 전부 지어낸 것이다. 대상 저장소의 이름을 픽스처로 쓰지 않는다.
    """
    from nexus import db
    from nexus.rid import chunk_rid, doc_rid

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM code_symbols WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)

        uri = f"{_TENANT}:design.md"
        drid = doc_rid(uri)
        await con.execute(
            "INSERT INTO documents (rid,tenant,source_uri,hash,content_hash,title,status) "
            "VALUES ($1,$2,$3,'h','h','설계 노트','active')", drid, _TENANT, uri)
        rids = {}
        for i, name in enumerate(("c1", "c2")):
            crid = chunk_rid(drid, "root", i)
            await con.execute(
                "INSERT INTO chunks (rid,tenant,source_uri,doc_rid,chunk_text,section_path,"
                "chunk_index,status,hash) VALUES ($1,$2,$3,$4,'본문','root',$5,'active','h')",
                crid, _TENANT, uri, drid, i)
            rids[name] = crid

        # 현재 코드에 있는 심볼들. `Gamma` 는 없고, `Delta` 는 둘로 늘었다.
        for path, name, digest, line in [
            ("Alpha.java", "Alpha", "hash-alpha", 1),
            ("Beta.java", "Beta", "hash-beta-NEW", 1),
            ("A/Delta.java", "Delta", "hash-delta", 1),
            ("B/Delta.java", "Delta", "hash-delta-other", 1),
        ]:
            await con.execute(
                "INSERT INTO code_symbols (tenant,repo,file_path,symbol_kind,symbol_name,"
                "start_line,end_line,span_hash,scan_commit) "
                "VALUES ($1,$2,$3,'class',$4,$5,$5,$6,'c0ffee')",
                _TENANT, _REPO, path, name, line, digest)

        # 문서가 바인딩해 둔 것 — `Beta` 는 그때의 해시가 다르고 `Gamma` 는 사라졌다.
        for chunk, cand, digest in [
            (rids["c1"], "Alpha", "hash-alpha"),
            (rids["c1"], "Beta", "hash-beta-OLD"),
            (rids["c1"], "Gamma", "hash-gamma"),
            (rids["c2"], "Delta", "hash-delta"),
        ]:
            await con.execute(
                "INSERT INTO doc_code_anchors (chunk_rid,tenant,repo,candidate,symbol_name,"
                "file_path,span_hash,scan_commit) VALUES ($1,$2,$3,$4,$4,'x.java',$5,'c0ffee')",
                chunk, _TENANT, _REPO, cand, digest)
    yield rids
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM code_symbols WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    db._pool = None


async def test_the_set_query_tells_the_four_states_apart(corpus):
    out = await statuses_for_chunks(_TENANT, list(corpus.values()))

    assert {a.name: a.status for a in out[corpus["c1"]]} == {
        "Alpha": FRESH,        # 같은 이름 · 같은 텍스트
        "Beta": CHANGED,       # 같은 이름 · 다른 텍스트
        "Gamma": ORPHANED,     # 이름이 사라졌다
    }
    assert {a.name: a.status for a in out[corpus["c2"]]} == {
        "Delta": AMBIGUOUS_NOW,   # 바인딩 뒤 동명이 생겼다 — 다시 겨누지 않는다
    }


async def test_a_chunk_without_anchors_is_absent_not_empty(corpus):
    """호출부가 `.get(rid, [])` 로 읽는다. 없는 것과 0개인 것을 굳이 구별하지 않는다."""
    out = await statuses_for_chunks(_TENANT, ["chunk:없는것"])

    assert out == {}


async def test_another_tenants_anchors_do_not_leak(corpus):
    out = await statuses_for_chunks("someone_else", list(corpus.values()))

    assert out == {}
