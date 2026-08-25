"""A13 컷오버 — 색인 접두사에 문서 제목을 넣는다, 그리고 **파생물을 같이 무효화한다.**

측정은 `tests/eval/a13-round2/README.md` 에 있다(벡터 fragment Recall@10 0.444 → 0.889,
p=0.016 · 대조군 24문항 Recall 무손상). 여기서 지키는 것은 그 측정이 **배포된 코드와 같은
규칙 위에서 나왔는가**, 그리고 접두사가 바뀐 청크가 재임베딩 큐에 들어가는가다.

⚠ 두 번째가 이 파일의 중심이다. `_invalidate_derived()` 는 오랫동안 `chunk_text` 변경만
감시했고, 그 함수의 주석은 컬럼이 하나 더 생겼을 때 같은 버그가 어떻게 돌아왔는지를 적고 있다
(실측 8건, 최저 코사인 0.593). 접두사는 `search_text` 의 **두 번째 입력**이므로 같은 함정이
그대로 재현될 수 있었다.
"""

from __future__ import annotations

import os

import pytest

from nexus.utils import context_prefix_for, get_search_text

DB_URL = os.getenv("NEXUS_TEST_DB_URL")


# ── 규칙 자체 ────────────────────────────────────────────────────────────────

def test_root_section_uses_the_title_alone():
    """섹션이 `root` 면 접두사는 제목이다 — 예전엔 `[root]`, 정보가 0이었다."""
    assert context_prefix_for("디제잉 아바타 10", "root") == "[디제잉 아바타 10]"


def test_title_already_in_section_is_not_repeated():
    """제목이 섹션에 이미 있으면 두 번 넣지 않는다. 중복은 그 자체로 신호를 흐린다."""
    assert context_prefix_for("로그인 정책", "로그인 정책") == "[로그인 정책]"


def test_title_and_section_are_joined():
    assert (context_prefix_for("플레이리스트 정책", "2. 노래 순서 이동")
            == "[플레이리스트 정책 > 2. 노래 순서 이동]")


def test_empty_title_falls_back_to_the_old_behaviour():
    """제목이 없으면 `None` — 그때는 `[section_path]` 가 그대로 맞다.

    `None` 대신 `[]` 같은 것을 넣으면 빈 대괄호가 색인 토큰이 된다.
    """
    assert context_prefix_for("", "root") is None
    assert context_prefix_for("   ", "어떤 절") is None


def test_search_text_uses_the_prefix():
    """`get_search_text` 가 실제로 그 접두사를 쓴다 — 규칙만 맞고 경로가 안 닿으면 값이 0이다."""
    class _C:
        chunk_text = "- **디제잉 포인트**: 4000"
        section_path = "root"
        context_prefix = context_prefix_for("디제잉 아바타 10", "root")

    text = get_search_text(_C())
    assert text.startswith("[디제잉 아바타 10] ")
    assert "아바타" in text          # 예전 색인 텍스트에는 이 낱말이 없었다


# ── 파생물 무효화 (이 파일의 중심) ────────────────────────────────────────────

def test_invalidation_predicate_watches_the_prefix():
    """`_invalidate_derived()` 가 **접두사 변경도** 감시해야 한다.

    감시하지 않으면 접두사만 바뀐 청크는 `WHERE <컬럼> IS NULL` 큐에 영영 안 들어가고,
    옛 접두사로 만든 벡터로 검색된다. 이 단언은 SQL 문자열을 보는 검사라 무르지만, 이
    한 줄이 빠지는 것이 정확히 과거에 일어난 일이었다.
    """
    from nexus.ingest.pipeline import _invalidate_derived
    from nexus.index.vector_index import VECTOR_COLUMNS

    sql = _invalidate_derived()
    assert "context_prefix IS DISTINCT FROM EXCLUDED.context_prefix" in sql
    # 모든 벡터 컬럼이 여전히 나열된다 — 세대가 늘어도 이 검사가 잡는다.
    for col in VECTOR_COLUMNS:
        assert f"{col} = CASE WHEN" in sql
    assert "tsvector_ko = CASE WHEN" in sql


@pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요")
def test_prefix_change_nulls_the_vector_on_reingest():
    """행동으로 확인한다: 접두사만 달라진 upsert 가 벡터를 NULL 로 되돌리는가.

    SQL 문자열 검사만 두면 술어가 맞아도 `ON CONFLICT` 절에 안 실려 있을 수 있다.
    """
    import asyncio
    import sys

    from nexus import db

    loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()

    async def inner():
        import asyncpg
        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=2)
        db._pool = pool
        try:
            async with pool.acquire() as con:
                await con.execute("TRUNCATE documents, chunks CASCADE")
                await con.execute(
                    "INSERT INTO documents (rid, tenant, source_uri, hash, title, status) "
                    "VALUES ('doc_p','acme','seed:p.md','h','정책 문서','active')")
                await con.execute(
                    "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, section_path, "
                    "chunk_text, context_prefix, embedding_1024) "
                    "VALUES ('chunk_p','acme','seed:p.md','doc_p','root','본문', NULL, $1)",
                    "[" + ",".join(["0.1"] * 1024) + "]")
                assert await con.fetchval(
                    "SELECT embedding_1024 IS NOT NULL FROM chunks WHERE rid='chunk_p'")

                # 같은 본문, 다른 접두사 — 오직 이것만 바뀐다.
                from nexus.ingest.pipeline import _invalidate_derived
                await con.execute(
                    "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, section_path, "
                    "chunk_text, context_prefix) "
                    "VALUES ('chunk_p','acme','seed:p.md','doc_p','root','본문','[정책 문서]') "
                    f"ON CONFLICT (rid) DO UPDATE SET chunk_text = EXCLUDED.chunk_text, "
                    f"context_prefix = EXCLUDED.context_prefix, {_invalidate_derived()}")

                assert await con.fetchval(
                    "SELECT context_prefix FROM chunks WHERE rid='chunk_p'") == "[정책 문서]"
                assert await con.fetchval(
                    "SELECT embedding_1024 IS NULL FROM chunks WHERE rid='chunk_p'"), \
                    "접두사가 바뀌었는데 벡터가 살아남았다 — 옛 텍스트의 벡터로 검색된다"
        finally:
            await pool.close()
            db._pool = None

    try:
        loop.run_until_complete(inner())
    finally:
        loop.close()


# ── 고정 평가 팩 보호 ────────────────────────────────────────────────────────

def test_backfill_refuses_pinned_eval_packs():
    """`ko_eval_*` 는 과거 측정이 재현돼야 하는 스냅샷이다 — 기본으로 거부한다."""
    from scripts.backfill_context_prefix import main

    assert main(["--tenant", "ko_eval_packb", "--apply"]) == 2
