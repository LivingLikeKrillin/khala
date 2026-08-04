"""벡터 컬럼 seam 과 ivfflat 사이징 (SPEC-nexus-kure-embedding-swap §4.2, §6).

컷오버도 롤백도 **설정 한 줄**이다. 그 한 줄이 SQL 에 들어가므로, 화이트리스트가 실제로 막는지와
오타가 조용히 기본값으로 삼켜지지 않는지를 여기서 지킨다 — 어느 임베딩 세대를 읽고 있는지 모르는
상태가 이 마이그레이션에서 가장 위험한 상태다.
"""

from __future__ import annotations

import math

import pytest

from nexus.index.vector_index import (
    DEFAULT_COLUMN,
    INDEX_NAMES,
    VECTOR_COLUMNS,
    UnknownVectorColumn,
    compute_lists,
    count_indexable_sql,
    create_index_sql,
    dimensions_of,
    resolve_column,
)

# ── 컬럼 화이트리스트 ────────────────────────────────────────────────────────


def test_the_default_is_the_current_generation():
    assert resolve_column(None) == DEFAULT_COLUMN == "embedding"
    assert dimensions_of("embedding") == 768
    assert dimensions_of("embedding_1024") == 1024


@pytest.mark.parametrize("bad", ["chunk_text", "embedding; DROP TABLE chunks", "", "  ", "embeddings"])
def test_anything_outside_the_whitelist_is_refused(bad):
    """설정 파일을 통한 SQL 주입 경로이자, 오타를 조용히 삼키는 경로다."""
    with pytest.raises(UnknownVectorColumn):
        resolve_column(bad)


def test_every_column_has_an_index_name():
    assert set(INDEX_NAMES) == set(VECTOR_COLUMNS)


def test_generated_sql_only_ever_names_a_whitelisted_column():
    for col in VECTOR_COLUMNS:
        sql = create_index_sql(col, 42)
        assert f"({col} vector_cosine_ops)" in sql
        assert "lists = 42" in sql
        # 부분 술어가 검색 쿼리의 필터와 같아야 인덱스가 실제로 쓰인다
        assert "status = 'active'" in sql and "is_quarantined = false" in sql
        assert f"{col} IS NOT NULL" in sql
    with pytest.raises(UnknownVectorColumn):
        create_index_sql("embedding; --", 42)


def test_the_row_count_query_matches_the_index_predicate():
    """다른 조건으로 세면 인덱스가 존재하지 않는 코퍼스에 맞춰진다."""
    for col in VECTOR_COLUMNS:
        counting = count_indexable_sql(col)
        for fragment in ("status = 'active'", "is_quarantined = false", f"{col} IS NOT NULL"):
            assert fragment in counting


# ── lists 사이징 ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("rows", "expected"), [
    (0, 1),                 # 빈 코퍼스에도 유효한 인덱스를 만들 수 있어야 한다
    (1, 1),
    (999, 1),               # 바닥값이 없으면 lists=0 이 되어 인덱스 생성이 실패한다
    (1_000, 1),
    (1_906, 1),             # 평가 팩 규모
    (250_000, 250),
    (1_000_000, 1_000),
])
def test_lists_below_a_million_is_rows_over_a_thousand_with_a_floor(rows, expected):
    assert compute_lists(rows) == expected


def test_lists_above_a_million_switches_to_sqrt():
    assert compute_lists(4_000_000) == round(math.sqrt(4_000_000))
    assert compute_lists(2_000_000) == round(math.sqrt(2_000_000))


def test_lists_is_capped_so_a_huge_corpus_does_not_produce_an_absurd_index():
    assert compute_lists(999_999) <= 2_000


def test_a_negative_row_count_is_a_bug_not_a_zero():
    with pytest.raises(ValueError):
        compute_lists(-1)


# ── seam 이 실제로 컬럼을 바꾸는가 ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_the_configured_column_is_the_one_queried(monkeypatch):
    """설정을 되읽어 확인하지 않는다 — **SQL 에 무엇이 들어갔는지**로 확인한다."""
    from nexus import db
    from nexus.search import hybrid

    seen = {}

    async def fake_fetch_all(sql, *args):
        seen["sql"] = sql
        return []

    class _Svc:
        async def embed_query(self, _q):
            return [0.1] * 768

    monkeypatch.setattr(db, "fetch_all", fake_fetch_all)

    await hybrid._vector_search("질의", _Svc(), "t", "INTERNAL", 20, column="embedding_1024")
    assert "c.embedding_1024 <=>" in seen["sql"]
    assert "c.embedding <=>" not in seen["sql"]

    await hybrid._vector_search("질의", _Svc(), "t", "INTERNAL", 20, column=None)
    assert "c.embedding <=>" in seen["sql"]


@pytest.mark.asyncio
async def test_a_bad_column_in_config_fails_the_query_rather_than_reading_the_wrong_one(monkeypatch):
    from nexus.search import hybrid

    class _Svc:
        async def embed_query(self, _q):
            return [0.1] * 768

    with pytest.raises(UnknownVectorColumn):
        await hybrid._vector_search("질의", _Svc(), "t", "INTERNAL", 20, column="embeddings")
