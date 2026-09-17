"""시각 범위로 좁힐 때 **모르는 것을 밖으로 내몰지 않는가.**

이 파일이 지키는 것은 사실상 두 낱말이다 — 술어마다 붙는 `IS NULL OR`. 그것이 빠지면 시각을
안 싣는 적재 경로의 문서가 좁히는 순간 통째로 사라지고, 화면에는 *"없습니다"* 가 뜬다. 있는데
안 보인 것과 없는 것을 그 화면에서 가를 방법은 없다.

**실측 2026-09-18 (라이브):** `origin_updated_at` 채움 비율이 `default` 248건 중 112건이고
`design_docs` 243건 중 **0건**이다. 즉 이 두 낱말이 빠졌다면 설계 문서 코퍼스 전체가 이 필터
아래에서 보이지 않았을 것이다 — 가설이 아니라 지금 코퍼스의 수다.

세지 않는 것도 같이 지킨다: 범위를 **안 물었으면** 미상 건수가 `0` 이 아니라 `None` 이다.
0 은 "물었고 전부 안다" 는 뜻이라, 안 물은 요청과 같은 값으로 내보내면 둘을 못 가른다.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from nexus.search.time_window import (
    OriginWindow,
    count_unknown,
    origin_window_predicate,
)

_T0 = datetime(2026, 9, 17, tzinfo=timezone.utc)
_T1 = datetime(2026, 9, 18, tzinfo=timezone.utc)
COL = "d.origin_updated_at"


# ── 술어 ───────────────────────────────────────────────────────────────────

def test_no_window_is_no_predicate():
    """안 물으면 SQL 이 한 글자도 안 바뀐다 — 기존 질의 계획을 흔들지 않는다."""
    sql, vals = origin_window_predicate(COL, 6, OriginWindow())
    assert sql == "" and vals == []


@pytest.mark.parametrize("window,n", [
    (OriginWindow(since=_T0), 1),
    (OriginWindow(until=_T1), 1),
    (OriginWindow(since=_T0, until=_T1), 2),
])
def test_each_bound_adds_one_binding(window, n):
    sql, vals = origin_window_predicate(COL, 6, window)
    assert len(vals) == n
    assert sql.count("AND (") == n


def test_every_bound_keeps_unknown_rows():
    """⛔ **이 파일의 이유.** 경계마다 `IS NULL OR` 가 붙어야 한다.

    빠지면 시각 미상 문서가 범위 밖으로 취급돼 사라진다. 라이브에서 그 문서가
    `design_docs` 의 100% 다(모듈 머리말의 실측)."""
    sql, _ = origin_window_predicate(COL, 6, OriginWindow(since=_T0, until=_T1))
    assert sql.count(f"{COL} IS NULL OR") == 2, sql


def test_bindings_are_numbered_from_the_given_index():
    """다리마다 앞에 쓰는 바인딩 수가 달라서(키워드 5 · 벡터 4) 번호를 호출부가 준다.
    여기서 어긋나면 한 다리만 조용히 틀린 값으로 거른다."""
    sql, _ = origin_window_predicate(COL, 6, OriginWindow(since=_T0, until=_T1))
    assert "$6" in sql and "$7" in sql and "$5" not in sql


def test_the_values_come_back_in_predicate_order():
    _, vals = origin_window_predicate(COL, 6, OriginWindow(since=_T0, until=_T1))
    assert vals == [_T0, _T1]


def test_only_the_given_bound_is_emitted():
    sql, vals = origin_window_predicate(COL, 3, OriginWindow(until=_T1))
    assert "<=" in sql and ">=" not in sql and vals == [_T1]


# ── 미상 건수 ──────────────────────────────────────────────────────────────

def test_not_asked_is_none_not_zero():
    """⛔ 0 으로 내보내면 "물었고 전부 안다" 와 구별되지 않는다."""
    assert count_unknown([None, _T0, None], OriginWindow()) is None


def test_asked_counts_the_unknowns():
    assert count_unknown([None, _T0, None], OriginWindow(since=_T0)) == 2


def test_asked_with_all_known_is_zero_not_none():
    """대조군. 물었는데 전부 아는 경우는 **측정해서 0** 이다."""
    assert count_unknown([_T0, _T1], OriginWindow(until=_T1)) == 0


def test_asked_is_true_for_either_bound():
    assert OriginWindow(since=_T0).asked
    assert OriginWindow(until=_T1).asked
    assert not OriginWindow().asked


# ── 검색 경로가 실제로 그 술어를 들고 가는가 ─────────────────────────────────

def test_both_legs_bind_the_window_after_their_own_parameters():
    """⛔ 술어가 옳아도 **부르는 쪽이 값을 안 넘기면** 아무 일도 안 일어난다.

    키워드 경로는 바인딩 다섯을 먼저 쓰고 벡터 경로는 넷을 쓴다. 두 숫자가 소스에 그대로
    적혀 있으므로, 앞쪽 바인딩이 늘어나면 여기서 깨져야 한다."""
    import inspect

    from nexus.search import hybrid

    src = inspect.getsource(hybrid)
    assert 'origin_window_predicate("d.origin_updated_at", 6, window)' in src
    assert 'origin_window_predicate("d.origin_updated_at", 5, window)' in src
    assert "BM25_LENGTH_NORMALIZATION, *win_vals," in src
    assert "top_k, *win_vals," in src
