"""구동식 재임베딩 · waiver · 컷오버 전제 조건
(SPEC-nexus-kure-embedding-swap §4.4, §4.5, §6).

**이 유닛이 존재하는 이유는 창발적 재임베딩이 마이그레이션에 못 쓰이기 때문이다.** 프로덕션은
텍스트가 바뀌면 벡터를 NULL 로 만들고 다음 적재가 채운다 — 언제 끝나는지도, 무엇이 실패했는지도
아무도 모른다. 실제로 이 작업이 찾아낸 결함 하나가 그것이었다(실패가 NULL 로 남고 미집계).

그래서 여기서 지키는 것:

- 실패는 **요약에 남는다** — 조용한 NULL 은 없다
- 중단해도 이어서 돈다 — 큐가 NULL 컬럼이라 재개 상태를 따로 안 든다
- 컷오버는 네 조건이 **모두** 서야 하고, 안 서면 무엇이 막는지 말한다
- waiver 는 **사람이 서명**해야 생긴다 — 자동으로 만들어지면 그건 조용히 사라지는 것과 같다
"""

from __future__ import annotations

import os

import pytest

from nexus.index.reembed import (
    ReembedSummary,
    counts,
    create_index,
    cutover_blockers,
    index_exists,
    pending_rids,
    reembed,
    waive,
    waived_rows,
)

pytestmark = [
    pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요"),
]

_TENANT = "reembed_test"
_COLUMN = "embedding_1024"
_DIM = 1024


class _Svc:
    """실패를 주문할 수 있는 가짜 임베딩 서비스."""

    def __init__(self, fail_on: set[str] | None = None, dim: int = _DIM):
        self.fail_on, self.dim, self.calls = fail_on or set(), dim, 0

    def get_model_name(self) -> str:
        return "KURE-v1"

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        out = []
        for text in texts:
            if any(mark in text for mark in self.fail_on):
                raise RuntimeError(f"임베딩 거부: {text[:20]}")
            out.append([0.01] * self.dim)
        return out


@pytest.fixture
async def corpus(db_pool):
    """청크 5건 — 하나는 임베딩이 실패하도록 표시해 둔다."""
    from nexus import db
    from nexus.rid import chunk_rid, doc_rid

    db._pool = db_pool
    async with db_pool.acquire() as con:
        # ivfflat 인덱스는 **테이블 전역**이라 테넌트로 격리되지 않는다. 앞 테스트가 만든 것이
        # 남아 있으면 "인덱스가 없으면 컷오버가 막힌다" 를 검증할 수 없다.
        await con.execute("DROP INDEX IF EXISTS idx_chunk_vector_1024")
        await con.execute("DELETE FROM embed_waivers WHERE chunk_rid LIKE 'chunk_%'")
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
        rids = {}
        for name, text in [("a", "파드 개요"), ("b", "노드 개요"), ("c", "볼륨 개요"),
                           ("d", "시크릿 개요"), ("bad", "깨진 문서 POISON")]:
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
        await con.execute("DROP INDEX IF EXISTS idx_chunk_vector_1024")
        await con.execute("DELETE FROM embed_waivers WHERE chunk_rid = ANY($1::text[])",
                          list(rids.values()))
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    db._pool = None


# ── 실행 ─────────────────────────────────────────────────────────────────────


async def test_it_fills_the_null_column_and_records_the_generation(corpus):
    from nexus import db

    summary = await reembed(_Svc(), _COLUMN, batch_size=2)
    assert summary.embedded == 5 and summary.ok

    n = await db.fetch_val(
        f"SELECT count(*) FROM chunks WHERE tenant=$1 AND {_COLUMN} IS NOT NULL", _TENANT)
    models = await db.fetch_val(
        "SELECT count(DISTINCT embed_model) FROM chunks WHERE tenant=$1", _TENANT)
    assert n == 5
    assert models == 1, "세대가 섞이면 컷오버 조건이 잡는다"


async def test_a_failure_is_counted_and_named_not_left_as_a_silent_null(corpus):
    """이 작업이 찾아낸 결함의 형태 그대로 — 실패가 NULL 로만 남으면 아무도 모른다."""
    summary = await reembed(_Svc(fail_on={"POISON"}), _COLUMN, batch_size=5)

    assert summary.embedded == 4
    assert len(summary.failed) == 1
    assert summary.failed[0].chunk_rid == corpus["bad"]
    assert "거부" in summary.failed[0].reason
    assert not summary.ok
    assert "실패 1건" in summary.render()


async def test_one_bad_chunk_does_not_block_the_rest_of_its_batch(corpus):
    """배치가 통째로 실패하면 개별로 다시 시도한다 — 한 청크가 나머지를 막으면 안 된다."""
    summary = await reembed(_Svc(fail_on={"POISON"}), _COLUMN, batch_size=5)
    assert summary.embedded == 4, "같은 배치의 나머지 4건이 저장돼야 한다"


async def test_it_resumes_where_it_stopped(corpus):
    """큐가 NULL 컬럼이라 재개 상태를 따로 들지 않는다."""
    first = await reembed(_Svc(), _COLUMN, batch_size=2)
    assert first.embedded == 5

    again = await reembed(_Svc(), _COLUMN, batch_size=2)
    assert again.embedded == 0, "이미 채워진 것을 다시 임베딩하면 재개가 아니라 낭비다"


async def test_a_wrong_dimension_is_refused_rather_than_stored(corpus):
    summary = await reembed(_Svc(dim=768), _COLUMN, batch_size=5)
    assert summary.embedded == 0
    assert all("차원" in f.reason for f in summary.failed)


# ── waiver ───────────────────────────────────────────────────────────────────


async def test_the_reembed_path_never_creates_a_waiver(corpus):
    """자동으로 빼면 그건 '조용히 사라짐' 이다. 사람이 서명해야 생긴다 (§4.5)."""
    await reembed(_Svc(fail_on={"POISON"}), _COLUMN, batch_size=5)
    assert await waived_rows() == []


async def test_a_waiver_needs_a_reason_and_a_signature(corpus):
    with pytest.raises(ValueError):
        await waive(corpus["bad"], "KURE-v1", "", "someone")
    with pytest.raises(ValueError):
        await waive(corpus["bad"], "KURE-v1", "영구 실패", "   ")


async def test_a_waived_chunk_leaves_the_queue_but_stays_on_the_record(corpus):
    await reembed(_Svc(fail_on={"POISON"}), _COLUMN, batch_size=5)
    await waive(corpus["bad"], "KURE-v1", "8k 토큰 초과, 분할 불가", "LivingLikeKrillin")

    assert corpus["bad"] not in [r for r, _, _ in await pending_rids(_COLUMN, 100)]
    c = await counts(_COLUMN)
    assert c["waived"] == 1 and c["pending"] == 0
    row = (await waived_rows())[0]
    assert row["waived_by"] == "LivingLikeKrillin" and "8k" in row["reason"]


# ── 컷오버 전제 조건 ─────────────────────────────────────────────────────────


async def test_pending_chunks_block_the_cutover(corpus):
    blockers = await cutover_blockers(_COLUMN)
    assert any("임베딩도 waiver 도 없는" in b for b in blockers)


async def test_a_missing_index_blocks_the_cutover(corpus):
    await reembed(_Svc(), _COLUMN, batch_size=5)
    blockers = await cutover_blockers(_COLUMN)
    assert any("인덱스가 없다" in b for b in blockers)


async def test_unwaived_failures_block_the_cutover(corpus):
    await reembed(_Svc(fail_on={"POISON"}), _COLUMN, batch_size=5)
    blockers = await cutover_blockers(_COLUMN, summary_failures=1)
    assert any("waive 되지 않은 실패" in b for b in blockers)


async def test_the_index_is_sized_from_the_row_count_at_creation_time(corpus, db_pool):
    """반쯤 찬 컬럼으로 사이징하면 존재한 적 없는 코퍼스에 맞춰진다 (§4.2)."""
    await reembed(_Svc(), _COLUMN, batch_size=5)
    rows, lists = await create_index(_COLUMN)
    assert rows >= 5
    assert lists == max(1, min(rows // 1000, 2000))
    assert await index_exists(_COLUMN)


def test_the_summary_says_what_to_do_about_failures():
    from nexus.index.reembed import Failure

    s = ReembedSummary(column=_COLUMN, model="KURE-v1", embedded=3)
    s.failed.append(Failure("c1", "터짐"))
    assert "waive" in s.render(), "무엇을 해야 하는지 말하지 않는 실패 보고는 반쪽이다"
