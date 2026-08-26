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


async def reembed_here(*args, **kwargs):
    """**항상 이 테스트의 테넌트로만** 재임베딩한다.

    범위 없이 부르면 같은 DB 의 다른 테넌트까지 상수 벡터로 덮어쓴다 — 실제로 그렇게 평가 코퍼스
    1,906건이 날아갔고, 그 위에서 돌린 ANN 측정이 잘못된 결론을 냈다(2026-08-04).
    """
    kwargs.setdefault("tenant", _TENANT)
    return await reembed(*args, **kwargs)

_TENANT = "reembed_test"
_COLUMN = "embedding_1024"
_DIM = 1024


def _vec_for(text: str, dim: int = _DIM) -> list[float]:
    """텍스트마다 **다른** 벡터. 상수 벡터를 돌려주는 가짜는 정렬 어긋남을 원리적으로 못 잡는다 —
    실제로 못 잡아서 뒤섞인 벡터가 프로덕션 컬럼에 들어갔다(2026-08-04)."""
    import hashlib
    import math
    import random

    rng = random.Random(hashlib.sha256(text.encode("utf-8")).digest())
    v = [rng.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / norm for x in v]


class _Svc:
    """실패를 주문할 수 있는 가짜 임베딩 서비스. **벡터는 텍스트에서 결정된다.**"""

    def __init__(self, fail_on: set[str] | None = None, dim: int = _DIM, shuffle: bool = False):
        self.fail_on, self.dim, self.calls = fail_on or set(), dim, 0
        self.shuffle = shuffle          # 정렬 어긋남을 일부러 만들어 테스트가 잡는지 본다

    def get_model_name(self) -> str:
        return "KURE-v1"

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        out = []
        for text in texts:
            if any(mark in text for mark in self.fail_on):
                raise RuntimeError(f"임베딩 거부: {text[:20]}")
            out.append(_vec_for(text, self.dim))
        if self.shuffle and len(out) > 1:
            out = out[1:] + out[:1]
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

    summary = await reembed_here(_Svc(), _COLUMN, batch_size=2)
    assert summary.embedded == 5 and summary.ok

    n = await db.fetch_val(
        f"SELECT count(*) FROM chunks WHERE tenant=$1 AND {_COLUMN} IS NOT NULL", _TENANT)
    # 세대는 **이 컬럼의 출처**에서 센다. 옛 행 라벨(`chunks.embed_model`)로 세면 다른 컬럼에
    # 쓴 모델이 이 판정에 섞여 든다 — 그 라벨은 행당 한 칸이었다 (027 에서 쓰기를 끊었다).
    models = await db.fetch_val(
        "SELECT count(DISTINCT p.model) FROM chunk_vector_provenance p "
        "JOIN chunks c ON c.rid = p.chunk_rid "
        "WHERE c.tenant = $1 AND p.column_name = $2", _TENANT, _COLUMN)
    assert n == 5
    assert models == 1, "세대가 섞이면 컷오버 조건이 잡는다"


async def test_each_chunk_gets_the_vector_of_its_own_text(corpus):
    """**정렬이 어긋나면 검색은 조용히 무의미해진다.** 상수 벡터를 돌려주는 가짜로는 못 잡는다 —
    실제로 못 잡아서 뒤섞인 벡터가 컬럼에 들어갔고, ANN 측정이 그 뒤섞임을 인덱스 탓으로 읽었다.
    """
    from nexus import db
    from nexus.utils import get_search_text

    await reembed_here(_Svc(), _COLUMN, batch_size=3)

    class _C:
        def __init__(self, text, section):
            self.chunk_text, self.section_path, self.context_prefix = text, section, None

    rows = await db.fetch_all(
        f"SELECT rid, chunk_text, section_path, {_COLUMN}::text AS vec "
        "FROM chunks WHERE tenant=$1", _TENANT)
    for r in rows:
        expected = _vec_for(get_search_text(_C(r["chunk_text"], r["section_path"])))
        stored = [float(x) for x in r["vec"].strip("[]").split(",")]
        assert max(abs(a - b) for a, b in zip(expected, stored, strict=True)) < 1e-6, (
            f"{r['rid']} 에 다른 텍스트의 벡터가 들어갔다")


async def test_the_alignment_check_can_fail(corpus):
    """위 단언이 실제로 무는지 — 백엔드가 순서를 한 칸 밀면 잡혀야 한다."""
    from nexus import db
    from nexus.utils import get_search_text

    await reembed_here(_Svc(shuffle=True), _COLUMN, batch_size=5)

    class _C:
        def __init__(self, text, section):
            self.chunk_text, self.section_path, self.context_prefix = text, section, None

    rows = await db.fetch_all(
        f"SELECT rid, chunk_text, section_path, {_COLUMN}::text AS vec "
        "FROM chunks WHERE tenant=$1", _TENANT)
    mismatches = 0
    for r in rows:
        expected = _vec_for(get_search_text(_C(r["chunk_text"], r["section_path"])))
        stored = [float(x) for x in r["vec"].strip("[]").split(",")]
        if max(abs(a - b) for a, b in zip(expected, stored, strict=True)) >= 1e-6:
            mismatches += 1
    assert mismatches > 0, "정렬 어긋남을 만들었는데 검사가 통과한다면 그 검사는 이빨이 없다"


async def test_a_failure_is_counted_and_named_not_left_as_a_silent_null(corpus):
    """이 작업이 찾아낸 결함의 형태 그대로 — 실패가 NULL 로만 남으면 아무도 모른다."""
    summary = await reembed_here(_Svc(fail_on={"POISON"}), _COLUMN, batch_size=5)

    assert summary.embedded == 4
    assert len(summary.failed) == 1
    assert summary.failed[0].chunk_rid == corpus["bad"]
    assert "거부" in summary.failed[0].reason
    assert not summary.ok
    assert "실패 1건" in summary.render()


async def test_one_bad_chunk_does_not_block_the_rest_of_its_batch(corpus):
    """배치가 통째로 실패하면 개별로 다시 시도한다 — 한 청크가 나머지를 막으면 안 된다."""
    summary = await reembed_here(_Svc(fail_on={"POISON"}), _COLUMN, batch_size=5)
    assert summary.embedded == 4, "같은 배치의 나머지 4건이 저장돼야 한다"


async def test_it_resumes_where_it_stopped(corpus):
    """큐가 NULL 컬럼이라 재개 상태를 따로 들지 않는다."""
    first = await reembed_here(_Svc(), _COLUMN, batch_size=2)
    assert first.embedded == 5

    again = await reembed_here(_Svc(), _COLUMN, batch_size=2)
    assert again.embedded == 0, "이미 채워진 것을 다시 임베딩하면 재개가 아니라 낭비다"


async def test_a_wrong_dimension_is_refused_rather_than_stored(corpus):
    summary = await reembed_here(_Svc(dim=768), _COLUMN, batch_size=5)
    assert summary.embedded == 0
    assert all("차원" in f.reason for f in summary.failed)


async def test_a_scoped_run_never_touches_another_tenant(corpus, db_pool):
    """**이 테스트가 없어서 평가 코퍼스가 날아갔다.**

    범위 없는 재임베딩이 같은 DB 의 다른 테넌트를 상수 벡터로 덮어썼고, 그 위에서 돌린 ANN 측정이
    인덱스를 탓하는 잘못된 결론을 냈다(2026-08-04). 파괴 범위가 선언되지 않으면 언젠가 넘친다 —
    `_disposable_test_db` 가 지키는 것과 같은 종류의 경계다.
    """
    from nexus import db
    from nexus.rid import chunk_rid, doc_rid

    other = "reembed_bystander"
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", other)
        await con.execute("DELETE FROM documents WHERE tenant=$1", other)
        uri = f"{other}:x.md"
        drid = doc_rid(uri)
        await con.execute(
            "INSERT INTO documents (rid,tenant,source_uri,hash,content_hash,title,status) "
            "VALUES ($1,$2,$3,'h','h','x','active')", drid, other, uri)
        await con.execute(
            "INSERT INTO chunks (rid,tenant,source_uri,doc_rid,chunk_text,section_path,"
            "chunk_index,status,hash) VALUES ($1,$2,$3,$4,'남의 테넌트 본문','root',0,'active','h')",
            chunk_rid(drid, "root", 0), other, uri, drid)

    await reembed_here(_Svc(), _COLUMN, batch_size=5)          # 이 테스트의 테넌트로만

    n = await db.fetch_val(
        f"SELECT count(*) FROM chunks WHERE tenant=$1 AND {_COLUMN} IS NOT NULL", other)
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", other)
        await con.execute("DELETE FROM documents WHERE tenant=$1", other)
    assert n == 0, "범위를 준 실행이 다른 테넌트의 벡터를 건드렸다"


async def test_an_unscoped_run_reaches_every_tenant_and_that_is_a_choice(corpus, db_pool):
    """전 테넌트 실행은 **마이그레이션의 정상 사용**이다. 다만 그것이 선택임을 여기서 못박는다."""
    from nexus import db
    from nexus.rid import chunk_rid, doc_rid

    other = "reembed_bystander2"
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", other)
        await con.execute("DELETE FROM documents WHERE tenant=$1", other)
        uri = f"{other}:x.md"
        drid = doc_rid(uri)
        await con.execute(
            "INSERT INTO documents (rid,tenant,source_uri,hash,content_hash,title,status) "
            "VALUES ($1,$2,$3,'h','h','x','active')", drid, other, uri)
        await con.execute(
            "INSERT INTO chunks (rid,tenant,source_uri,doc_rid,chunk_text,section_path,"
            "chunk_index,status,hash) VALUES ($1,$2,$3,$4,'남의 테넌트 본문','root',0,'active','h')",
            chunk_rid(drid, "root", 0), other, uri, drid)

    await reembed(_Svc(), _COLUMN, batch_size=5, tenant=other)   # 명시적으로 그 테넌트

    n = await db.fetch_val(
        f"SELECT count(*) FROM chunks WHERE tenant=$1 AND {_COLUMN} IS NOT NULL", other)
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", other)
        await con.execute("DELETE FROM documents WHERE tenant=$1", other)
    assert n == 1


# ── waiver ───────────────────────────────────────────────────────────────────


async def test_the_reembed_path_never_creates_a_waiver(corpus):
    """자동으로 빼면 그건 '조용히 사라짐' 이다. 사람이 서명해야 생긴다 (§4.5)."""
    await reembed_here(_Svc(fail_on={"POISON"}), _COLUMN, batch_size=5)
    assert await waived_rows() == []


async def test_a_waiver_needs_a_reason_and_a_signature(corpus):
    with pytest.raises(ValueError):
        await waive(corpus["bad"], "KURE-v1", "", "someone")
    with pytest.raises(ValueError):
        await waive(corpus["bad"], "KURE-v1", "영구 실패", "   ")


async def test_a_waived_chunk_leaves_the_queue_but_stays_on_the_record(corpus):
    await reembed_here(_Svc(fail_on={"POISON"}), _COLUMN, batch_size=5)
    await waive(corpus["bad"], "KURE-v1", "8k 토큰 초과, 분할 불가", "LivingLikeKrillin")

    assert corpus["bad"] not in [r for r, _, _, _ in await pending_rids(_COLUMN, 100, tenant=_TENANT)]
    c = await counts(_COLUMN, _TENANT)
    assert c["waived"] == 1 and c["pending"] == 0
    row = (await waived_rows())[0]
    assert row["waived_by"] == "LivingLikeKrillin" and "8k" in row["reason"]


# ── 컷오버 전제 조건 ─────────────────────────────────────────────────────────


async def test_pending_chunks_block_the_cutover(corpus):
    blockers = await cutover_blockers(_COLUMN, tenant=_TENANT)
    assert any("임베딩도 waiver 도 없는" in b for b in blockers)


async def test_a_missing_index_blocks_the_cutover(corpus):
    await reembed_here(_Svc(), _COLUMN, batch_size=5)
    blockers = await cutover_blockers(_COLUMN, tenant=_TENANT)
    assert any("인덱스가 없다" in b for b in blockers)


async def test_unwaived_failures_block_the_cutover(corpus):
    await reembed_here(_Svc(fail_on={"POISON"}), _COLUMN, batch_size=5)
    blockers = await cutover_blockers(_COLUMN, summary_failures=1, tenant=_TENANT)
    assert any("waive 되지 않은 실패" in b for b in blockers)


async def test_the_index_is_sized_from_the_row_count_at_creation_time(corpus, db_pool):
    """반쯤 찬 컬럼으로 사이징하면 존재한 적 없는 코퍼스에 맞춰진다 (§4.2)."""
    await reembed_here(_Svc(), _COLUMN, batch_size=5)
    rows, lists = await create_index(_COLUMN)
    assert rows >= 5
    assert lists == max(1, min(rows // 1000, 2000))
    assert await index_exists(_COLUMN)


def test_the_summary_says_what_to_do_about_failures():
    from nexus.index.reembed import Failure

    s = ReembedSummary(column=_COLUMN, model="KURE-v1", embedded=3)
    s.failed.append(Failure("c1", "터짐"))
    assert "waive" in s.render(), "무엇을 해야 하는지 말하지 않는 실패 보고는 반쪽이다"


# ── 큐 순서 (배치 안의 길이 편차 = 순수 낭비) ────────────────────────────────


@pytest.fixture
async def varied_lengths(db_pool):
    """길이가 크게 다른 청크들. 삽입 순서는 길이순이 **아니다**."""
    from nexus import db
    from nexus.rid import chunk_rid, doc_rid

    db._pool = db_pool
    tenant = "reembed_len_test"
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", tenant)
        await con.execute("DELETE FROM documents WHERE tenant=$1", tenant)
        for name, text in [("mid", "가" * 500), ("huge", "나" * 5000),
                           ("tiny", "다" * 10), ("small", "라" * 100)]:
            uri = f"{tenant}:{name}.md"
            drid = doc_rid(uri)
            await con.execute(
                "INSERT INTO documents (rid,tenant,source_uri,hash,content_hash,title,status) "
                "VALUES ($1,$2,$3,'h','h',$4,'active')", drid, tenant, uri, name)
            await con.execute(
                "INSERT INTO chunks (rid,tenant,source_uri,doc_rid,chunk_text,section_path,"
                "chunk_index,status,hash) VALUES ($1,$2,$3,$4,$5,'root',0,'active','h')",
                chunk_rid(drid, "root", 0), tenant, uri, drid, text)
    yield tenant
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", tenant)
        await con.execute("DELETE FROM documents WHERE tenant=$1", tenant)
    db._pool = None


async def test_the_queue_comes_out_shortest_first(varied_lengths):
    """**배치는 제일 긴 글에 맞춰 패딩된다.** 큐가 길이순이 아니면 짧은 글들이 긴 글 하나에
    끌려가 그만큼을 빈칸으로 계산한다 — 라이브 코퍼스에서 잰 낭비가 60%였다(계산량 287만자 →
    718만자). 순서만 바꿔도 효율이 40%→99% 로 오른다. 순서는 공짜다.
    """
    rows = await pending_rids(_COLUMN, 100, tenant=varied_lengths)
    lengths = [len(text) for _, text, _, _ in rows]

    assert lengths == sorted(lengths), f"큐가 길이순이 아니다: {lengths}"


async def test_a_batch_holds_texts_of_similar_length(varied_lengths):
    """큐 순서의 목적은 정렬 자체가 아니라 **한 배치 안의 편차**를 없애는 것이다."""
    first = await pending_rids(_COLUMN, 2, tenant=varied_lengths)
    lengths = [len(text) for _, text, _, _ in first]

    assert max(lengths) <= 500, f"첫 배치에 긴 글이 섞였다: {lengths}"


async def test_reembed_uses_the_same_text_the_index_path_would(db_pool):
    """재임베딩은 **색인 경로와 같은 텍스트**로 벡터를 만들어야 한다.

    ⚠ 2026-08-26 라이브에서 어긋났다. `_C` 가 `context_prefix = None` 을 박아 뒀고, 코퍼스
    전체가 NULL 이던 동안에는 우연히 맞았다. A13 컷오버가 접두사를 채우자 그 가정이 거짓이 되어
    **BM25 에는 제목이 있고 벡터에는 없는** 반쪽 상태가 됐다 — 같은 코퍼스에서 벡터 다리 파편
    Recall 이 실험(0.889)과 라이브(0.444)로 갈려서 잡혔다.

    큐가 접두사를 실어 오는지를 여기서 못박는다. 접두사가 색인 텍스트의 **두 번째 입력**이므로,
    한쪽만 아는 경로가 있으면 그 경로는 조용히 옛 텍스트의 벡터를 만든다.
    """
    from nexus import db
    from nexus.utils import get_search_text

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
        await con.execute(
            "INSERT INTO documents (rid, tenant, source_uri, hash, title, status) "
            "VALUES ('doc_pfx', $1, 'seed:pfx.md', 'h', '접두사 문서', 'active')", _TENANT)
        await con.execute(
            "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, section_path, chunk_text, "
            "context_prefix, status) VALUES ('chunk_pfx', $1, 'seed:pfx.md', 'doc_pfx', 'root', "
            "'본문', '[접두사 문서]', 'active')", _TENANT)

    rows = await pending_rids(_COLUMN, 100, tenant=_TENANT)
    row = next(r for r in rows if r[0] == "chunk_pfx")
    assert len(row) == 4, "큐가 접두사를 안 실어 온다"
    _rid, text, section, prefix = row
    assert prefix == "[접두사 문서]"

    class _C:
        chunk_text, section_path, context_prefix = text, section, prefix

    assert get_search_text(_C()).startswith("[접두사 문서] "), \
        "재임베딩 텍스트가 색인 텍스트와 다르다 — 옛 벡터가 만들어진다"
