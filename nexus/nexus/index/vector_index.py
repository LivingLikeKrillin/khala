"""벡터 컬럼과 ivfflat 인덱스 — 어느 컬럼을 읽고, `lists` 를 어떻게 정하나
(SPEC-nexus-kure-embedding-swap §4.2).

**컬럼 이름은 화이트리스트로만 SQL 에 들어간다.** 설정값을 그대로 문자열 조립에 넣으면 그건
설정 파일을 통한 SQL 주입이다. 컬럼은 두 개뿐이고, 그 사실을 코드가 강제한다.

**`lists` 는 베끼지 않고 센다.** 지금 인덱스는 코퍼스가 더 작던 시절에 만들어졌고, 잘못 사이징된
ivfflat 은 조용한 재현율 손실이다 — 이 작업이 계속 찾아낸 부류의 결함이다.
"""

from __future__ import annotations

import math

#: 읽을 수 있는 벡터 컬럼과 그 차원. 여기 없는 이름은 SQL 에 닿지 못한다.
VECTOR_COLUMNS: dict[str, int] = {
    "embedding": 768,             # nomic-embed-text (현행)
    "embedding_1024": 1024,       # KURE-v1
}

DEFAULT_COLUMN = "embedding"

#: ivfflat 인덱스 이름 — 컬럼마다 하나. 컷오버는 인덱스를 바꿔 다는 게 아니라 읽는 컬럼을 바꾼다.
INDEX_NAMES: dict[str, str] = {
    "embedding": "idx_chunk_vector",
    "embedding_1024": "idx_chunk_vector_1024",
}


class UnknownVectorColumn(ValueError):
    """설정이 모르는 컬럼을 가리켰다. 조용히 기본값으로 돌아가면 어느 세대를 읽는지 알 수 없다."""


def resolve_column(name: str | None) -> str:
    """설정값 → 실제 컬럼명. 화이트리스트 밖이면 거부한다.

    **키가 없는 것(None)과 빈 값으로 지정된 것은 다르다.** 전자는 기본값이고, 후자는 오타이거나
    지우다 만 설정이다 — 빈 값을 기본값으로 삼키면 "어느 세대를 읽는지 모른다" 는 상태가 조용히
    만들어진다. 지시문 프리픽스가 같은 규칙을 쓴다 (providers/embedding.py).
    """
    if name is None:
        return DEFAULT_COLUMN
    column = name.strip()
    if column not in VECTOR_COLUMNS:
        raise UnknownVectorColumn(
            f"{column!r} 은 벡터 컬럼이 아니다 (가능: {', '.join(sorted(VECTOR_COLUMNS))}). "
            "설정 오타를 기본값으로 삼키면 어느 임베딩 세대를 읽고 있는지 아무도 모른다.")
    return column


def dimensions_of(column: str) -> int:
    return VECTOR_COLUMNS[resolve_column(column)]


def compute_lists(rows: int) -> int:
    """ivfflat `lists` — pgvector 의 두 구간을 그대로 따른다 (§4.2).

    - `rows ≤ 1,000,000` → `rows / 1000`, 최소 1, 상한 2000
    - 그 위 → `sqrt(rows)`

    `rows` 는 **인덱스의 부분 술어가 매칭하는 행 수**여야 하고, **재임베딩이 끝난 뒤** 세어야 한다.
    채워지는 중인 컬럼으로 세면 존재한 적 없는 코퍼스에 맞춘 인덱스가 나온다.
    """
    if rows < 0:
        raise ValueError(f"행 수가 음수다: {rows}")
    if rows <= 1_000_000:
        return max(1, min(rows // 1000, 2000))
    return round(math.sqrt(rows))


def create_index_sql(column: str, lists: int) -> str:
    """부분 술어는 기존 인덱스와 같은 모양을 유지한다 — 검색 쿼리의 필터와 일치해야 쓰인다."""
    col = resolve_column(column)
    return (
        f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {INDEX_NAMES[col]} ON chunks "
        f"USING ivfflat ({col} vector_cosine_ops) WITH (lists = {int(lists)}) "
        f"WHERE status = 'active' AND is_quarantined = false AND {col} IS NOT NULL"
    )


def count_indexable_sql(column: str) -> str:
    """`lists` 를 정할 때 세는 행 — 인덱스의 부분 술어와 **같은** 조건이어야 한다."""
    col = resolve_column(column)
    return (
        "SELECT count(*) FROM chunks "
        f"WHERE status = 'active' AND is_quarantined = false AND {col} IS NOT NULL"
    )
