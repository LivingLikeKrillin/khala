"""근거 문서에 붙은 **갱신 부채**를 읽는 순간에 알린다 (2026-08-18).

라이브 정책 코퍼스를 처음 측정하던 날, 답변 8건 중 2건의 실패 원인이 시스템이 아니라 **문서**였다:
한 문서가 "이용약관은 아직 기획되지 않음" 이라고 적으면서 같은 문서에 실제 약관 본문을 담고
있었다. 읽는 사람은 그 사실을 알 방법이 없었다.

**여기 오는 것은 결정론으로 확인되는 부채뿐이다.** 의미적 모순 판정은 심판 모델이 필요하고
그 길은 근거를 들어 기각됐다(DocPrism: 98% 플래그, 정확도 14%). 모순은 답변자가 서술할 수
있고, 시스템은 그것을 보증하지 않는다.
"""

from __future__ import annotations

from nexus.search.doc_debt import DocDebt, describe, summarize


def test_a_clean_document_produces_no_line():
    """기본은 조용하다 — 전부에 배지를 달면 아무것도 구별하지 못한다."""
    assert describe([]) == ""
    assert summarize([]) is None


def test_a_superseded_document_says_what_replaced_it():
    line = describe([DocDebt("d1", "옛 정책", superseded_by_title="새 정책", same_title_docs=1)])

    assert "옛 정책" in line and "새 정책" in line


def test_a_duplicated_title_says_the_citation_cannot_point():
    """인용은 `[출처: 제목]` 이라, 같은 제목이 둘이면 어느 것인지 가리키지 못한다."""
    line = describe([DocDebt("d2", "플레이리스트 정책", same_title_docs=3)])

    assert "플레이리스트 정책" in line
    assert "3" in line


def test_the_summary_carries_both_kinds_for_the_surface():
    out = summarize([DocDebt("d1", "옛 정책", "새 정책", 1), DocDebt("d2", "겹친 제목", "", 2)])

    assert [d["title"] for d in out] == ["옛 정책", "겹친 제목"]
    assert out[0]["superseded_by"] == "새 정책"
    assert out[1]["same_title_docs"] == 2


async def test_no_documents_touches_no_database(monkeypatch):
    from nexus.search import doc_debt

    async def _boom(*a, **k):
        raise AssertionError("빈 입력에 쿼리를 날렸다")

    monkeypatch.setattr(doc_debt.db, "fetch_all", _boom)
    assert await doc_debt.debts_for_docs("t", []) == {}


async def test_a_failed_lookup_does_not_take_the_answer_down(monkeypatch):
    from nexus.search import doc_debt

    async def _boom(*a, **k):
        raise RuntimeError("relation does not exist")

    monkeypatch.setattr(doc_debt.db, "fetch_all", _boom)
    assert await doc_debt.debts_for_docs("t", ["d1"]) == {}


async def test_one_query_regardless_of_how_many_documents(monkeypatch):
    from nexus.search import doc_debt

    calls = {"n": 0}

    async def _count(*a, **k):
        calls["n"] += 1
        return [{"rid": f"d{i}", "title": f"문서{i}", "superseded_by_title": "", "same_title": 2}
                for i in range(20)]

    monkeypatch.setattr(doc_debt.db, "fetch_all", _count)
    out = await doc_debt.debts_for_docs("t", [f"d{i}" for i in range(20)])

    assert calls["n"] == 1
    assert len(out) == 20


async def test_an_empty_string_means_not_superseded(monkeypatch):
    """이 리포의 관례는 NULL 이 아니라 빈 문자열이다(`lifecycle.py` 의 unsupersede).
    `IS NOT NULL` 로 읽으면 **모든 문서가 대체된 것으로** 보인다 — 실제로 그렇게 잘못 읽었다."""
    from nexus.search import doc_debt

    async def _rows(*a, **k):
        return [{"rid": "d1", "title": "멀쩡한 문서", "superseded_by_title": "", "same_title": 1}]

    monkeypatch.setattr(doc_debt.db, "fetch_all", _rows)
    assert await doc_debt.debts_for_docs("t", ["d1"]) == {}


def test_the_same_title_is_not_repeated_once_per_document():
    """제목이 겹치는 문서가 근거에 여럿 들어오는 것이 **그 부채의 정의**다. 접지 않으면
    부채를 알리는 줄이 그 자체로 소음이 된다 — 라이브에서 같은 문장이 세 번 나왔다."""
    line = describe([DocDebt(f"d{i}", "겹친 제목", "", 8) for i in range(3)])

    assert line.count("겹친 제목") == 1


async def test_a_row_of_the_wrong_shape_does_not_take_the_answer_down(monkeypatch):
    """조회는 성공했는데 모양이 다른 경우. 보강이 답변을 죽이지 않는다는 약속은 쿼리에만
    걸린 것이 아니다 — 행 파싱에서 터지면 결과는 같다(답이 사라진다)."""
    from nexus.search import doc_debt

    async def _wrong_shape(*a, **k):
        return [{"chunk_rid": "c1", "candidate": "Alpha"}]      # 다른 층의 행

    monkeypatch.setattr(doc_debt.db, "fetch_all", _wrong_shape)
    assert await doc_debt.debts_for_docs("t", ["d1"]) == {}
