"""BM25 질의 조립 — SPEC-nexus-search-recall §4.1, §5, §6 (DB·mecab 없이 도는 부분).

`AND` 는 질의의 **모든** 어휘를 한 청크 안에서 요구했다. mecab 이 `엔티티` 를 `엔`+`티티` 로
쪼개므로, `Entity 식별` 이라 적힌 문서는 `'엔' & '티티' & '식별'` 에 걸리지 않는다.
14개 질의 중 **11개에서 키워드 다리가 아무것도 반환하지 않았다.**
"""

from __future__ import annotations

import pytest

from nexus.index.bm25 import tokens_to_tsquery


def test_tokens_are_joined_with_or_not_and():
    assert tokens_to_tsquery(["엔", "티티", "식별"]) == "'엔' | '티티' | '식별'"


def test_and_would_demand_every_lexeme_in_one_chunk():
    """조인자가 `&` 로 돌아가면 이 테스트가 깨진다.

    그 한 글자가 14개 질의 중 11개의 키워드 재현율을 0 으로 만든다
    (SPEC-nexus-search-recall §3.1, 2026-07-10 측정).
    """
    q = tokens_to_tsquery(["데이터베이스", "인덱스", "접근"])
    assert " & " not in q, "AND 로 되돌아갔다 — 다중어 한국어 질의의 재현율이 무너진다"
    assert q.count("|") == 2


@pytest.mark.parametrize("tokens", [[], [""], ["  ", "\n"]])
def test_no_usable_tokens_yields_no_query(tokens):
    assert tokens_to_tsquery(tokens) == ""


def test_a_single_token_needs_no_operator():
    assert tokens_to_tsquery(["식별"]) == "'식별'"


def test_a_quote_in_a_token_is_still_doubled():
    """mecab 은 따옴표를 내놓지 않는다(§5). 그래도 이스케이프는 남긴다 — 토크나이저가 바뀔 수 있다."""
    assert tokens_to_tsquery(["a'b"]) == "'a''b'"
