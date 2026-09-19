"""호출자가 **이번 질의에서는 안 보고 싶다**고 말한 문서 종류를 후보에서 뺀다.

⛔ **왜 생겼나 (설명 층 보고 2026-09-19 · 우리 실측 2026-09-20).** 설명 층이 사건 아홉에
대해 본문 인용 72건을 세어 보니 3,506줄짜리 설계 일지 한 편이 **29%** 를 차지했고, 그
문서는 답의 청중을 운영자가 아니라 개발자로 만든다. 우리 쪽 실측도 같은 방향이었다 —
같은 코퍼스에 사건 분류 질의를 여섯 모양으로 돌리니 그 한 편이 **상위 20 중 5~7 자리**를
매번 차지했다.

⚠ **이 필터는 랭킹을 고치지 않는다.** 자리를 비우는 것과 맞는 문서를 올리는 것은 다른
일이고, 설명 층이 그 구분을 먼저 적었다. 여기서 지키는 것은 **자리를 비우는 쪽**뿐이다.
"""

from __future__ import annotations

import os

import pytest

from nexus.search.doc_type_filter import (
    MAX_EXCLUDED,
    doc_type_exclusion_predicate,
    normalize_doc_types,
)


# ── 순수: 정규화 ──────────────────────────────────────────────────────────────

def test_nothing_asked_is_an_empty_tuple():
    assert normalize_doc_types(None) == ()
    assert normalize_doc_types([]) == ()


def test_it_keeps_the_order_the_caller_sent():
    """⛔ 정렬하지 않는다. 이 값이 그대로 응답과 기록에 나가는데, 정렬하면 호출자가 보낸
    것과 우리가 적은 것이 달라 보인다."""
    assert normalize_doc_types(["spec", "design_doc", "api_spec"]) == \
        ("spec", "design_doc", "api_spec")


def test_duplicates_and_whitespace_collapse():
    assert normalize_doc_types([" spec ", "spec", "", "   ", "design_doc"]) == \
        ("spec", "design_doc")


def test_a_non_string_is_skipped_not_fatal():
    """질의 하나를 죽이는 것보다 그 원소를 버리는 편이 낫다."""
    assert normalize_doc_types(["spec", None, 17, ["a"], "design_doc"]) == \
        ("spec", "design_doc")


def test_a_very_long_list_is_cut():
    """종류 어휘는 손에 꼽는다. 그보다 긴 목록은 호출자가 종류가 아닌 것을 넣고 있는 것이다."""
    got = normalize_doc_types([f"t{i}" for i in range(MAX_EXCLUDED + 10)])
    assert len(got) == MAX_EXCLUDED


# ── 순수: SQL 조각 ────────────────────────────────────────────────────────────

def test_asking_for_nothing_changes_no_sql():
    """⭐ **대조군.** 빈 목록은 오늘과 **글자 그대로 같은** SQL 을 내야 한다 — 이 기능이
    꺼져 있는 배포에서 계획이 바뀌면 그것만으로 회귀다."""
    assert doc_type_exclusion_predicate("d.doc_type", 7, []) == ("", [])
    assert doc_type_exclusion_predicate("d.doc_type", 7, None) == ("", [])


def test_the_fragment_starts_with_and_and_binds_one_value():
    frag, vals = doc_type_exclusion_predicate("d.doc_type", 7, ["spec", "design_doc"])
    assert frag.startswith("AND ")
    assert "$7" in frag
    assert vals == [["spec", "design_doc"]]


def test_a_document_of_unknown_type_would_survive_the_filter():
    """종류를 모르는 문서는 *어느 종류도 아닌 것*이지 *빼라고 한 종류*가 아니다.

    `<> ALL` 만 쓰면 NULL 비교가 `NULL` 이 되어 그 행이 조용히 사라진다 — 시각 범위가
    `IS NULL OR` 를 쓰는 것과 같은 이유이고, 그 자리에서 이 리포는 설계 문서 코퍼스를
    통째로 잃을 뻔했다.

    ⚠ **오늘 이 갈래는 안 밟힌다 — 아래 검사가 그 이유다.** 처음엔 라이브 검사에서
    `doc_type=NULL` 행을 만들어 확인하려 했고 **CI 가 스키마로 막았다**(`NOT NULL`).
    막힌 것이 옳다: 없는 상태를 지어내 통과시키면 그 검사는 아무것도 안 지킨다.
    이 술어는 칸 이름을 인자로 받으므로 그 제약이 없는 칸에도 쓰일 수 있고, 그래서
    갈래는 남긴다 — **관측된 구조가 아니라 보험**이라고 적어 둔다.
    """
    frag, _ = doc_type_exclusion_predicate("d.doc_type", 3, ["spec"])
    assert "IS NULL" in frag, "종류 미상 문서가 이 필터에 쓸려 나간다"



def test_the_param_number_is_the_callers_to_choose():
    """다리마다 앞 바인딩 수가 달라서 번호를 함수가 정하면 안 된다."""
    for n in (3, 5, 9):
        frag, _ = doc_type_exclusion_predicate("d.doc_type", n, ["spec"])
        assert f"${n}" in frag


# ── 배선: 라이브 코퍼스에서 실제로 빠지는가 ───────────────────────────────────

pytestmark_db = pytest.mark.skipif(
    not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "doc_type_filter_test"


@pytestmark_db
@pytest.mark.asyncio
async def test_the_schema_is_why_that_branch_is_insurance(db_pool):
    """⭐ **위 갈래가 왜 안 밟히는지를 스키마에서 읽는다.**

    `documents.doc_type` 이 `NOT NULL` 인 동안 그 갈래는 보험이다. 누가 그 제약을 풀면
    이 검사가 먼저 붉어지고, 그때부터 위 갈래는 보험이 아니라 **실제로 막는 것**이 된다.
    """
    async with db_pool.acquire() as con:
        nullable = await con.fetchval(
            "select is_nullable from information_schema.columns "
            "where table_name='documents' and column_name='doc_type'")
    assert nullable == "NO", (
        "`documents.doc_type` 이 NULL 을 받게 됐다 — 이제 `IS NULL OR` 갈래가 "
        "실제로 행을 지키고 있다. 위 검사의 「보험」이라는 설명을 고쳐라")


async def _seed(pool):
    """빼려는 종류 둘 + 안 뺄 종류 둘. 넷 다 종류를 **안다** — 스키마가 NULL 을 안 받는다.

    ⛔ **문서 행만 심으면 키워드 다리가 아무것도 못 찾는다 (CI 가 잡았다, 2026-09-20).**
    `_save_document` 는 이름 그대로 문서만 저장한다. BM25 는 `chunks.tsvector_ko` 를 보고,
    그것을 채우는 것은 `index_chunk_bm25` 다. 내 첫 판은 문서 넷을 심고 히트 0건을 받았다.
    """
    from nexus.index.bm25 import index_chunk_bm25

    async with pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)

    class _Chunk:
        def __init__(self, text, prefix):
            self.chunk_text, self.section_path, self.context_prefix = text, "root", prefix

    kinds = (("spec.md", "spec"), ("journal.md", "design_doc"),
             ("sop.md", "policy"), ("mystery.md", "markdown"))
    for name, doc_type in kinds:
        rid = f"doc_{_TENANT}_{name.replace('.', '_')}"
        async with pool.acquire() as con:
            await con.execute(
                "INSERT INTO documents (rid, tenant, source_uri, hash, title, doc_type, "
                "classification, status) VALUES ($1,$2,$3,'h',$4,$5,'INTERNAL','active')",
                rid, _TENANT, f"{_TENANT}:{name}", name, doc_type)
        chunk = _Chunk("파지 실패 절차 본문", f"[{name}]")
        crid = f"chunk_{rid}"
        async with pool.acquire() as con:
            await con.execute(
                "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, section_path, "
                "chunk_text, context_prefix, classification, status) "
                "VALUES ($1,$2,$3,$4,'root',$5,$6,'INTERNAL','active')",
                crid, _TENANT, f"{_TENANT}:{name}", rid, chunk.chunk_text,
                chunk.context_prefix)
        await index_chunk_bm25(crid, chunk)


@pytestmark_db
@pytest.mark.asyncio
async def test_the_excluded_type_leaves_the_candidate_pool(db_pool):
    """⛔ 함수가 옳은 것과 다리가 그 함수를 부르는 것은 다른 사실이다.

    이 리포는 그 구분에서 이미 데였다 — `section_fill` 이 범위를 직접 묶고 있어서 보강
    둘이 이틀간 조용히 죽었고, 검사 열셋이 그동안 초록이었다.
    """
    from nexus import db
    from nexus.search.hybrid import _bm25_search

    previous = db._pool
    db._pool = db_pool
    try:
        await _seed(db_pool)

        async def titles(exclude):
            hits, _ = await _bm25_search("파지 실패 절차", _TENANT, "INTERNAL", 50,
                                         exclude_doc_types=exclude)
            async with db_pool.acquire() as con:
                rows = await con.fetch(
                    "SELECT rid, title FROM documents WHERE rid = any($1::text[])",
                    [h.doc_rid for h in hits])
            return {r["title"] for r in rows}

        everything = await titles([])
        assert {"spec.md", "journal.md", "sop.md", "mystery.md"} <= everything, \
            f"씨앗이 안 심겼다: {everything}"

        narrowed = await titles(["spec", "design_doc"])
        assert "spec.md" not in narrowed and "journal.md" not in narrowed, \
            "빼라고 한 종류가 후보에 남았다"
        assert "sop.md" in narrowed, "안 뺀 종류가 같이 사라졌다"
        assert "mystery.md" in narrowed, "안 뺀 종류가 같이 사라졌다"

        assert await titles(["nonexistent_type"]) == everything, \
            "없는 종류를 빼라고 했더니 무언가가 사라졌다"

        async with db_pool.acquire() as con:
            await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
            await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    finally:
        db._pool = previous


@pytest.mark.asyncio
async def test_both_legs_actually_receive_the_exclusion(monkeypatch):
    """⛔ 한 다리만 거르면 그 문서가 **다른 다리로** 융합에 들어온다.

    RRF 는 두 다리의 합의를 올리므로, 한쪽에만 남은 문서도 순위를 받는다. 즉 반만 건
    필터는 "덜 걸린다" 가 아니라 **안 걸린 것과 구별이 안 된다.**

    ⛔ **첫 판은 서명만 봤고, 그래서 변이를 놓쳤다 (2026-09-20).** `inspect.signature` 로
    두 함수가 인자를 *받는지*만 확인했는데, 호출부에서 벡터 다리의 인자를 지우는 변이가
    그 검사를 그대로 통과했다. 함수가 받을 수 있는 것과 부르는 쪽이 주는 것은 다른 사실이고,
    이 리포는 그 구분에서 이미 이틀짜리 침묵을 겪었다(`section_fill`).

    그래서 **`hybrid_search` 를 실제로 돌려서** 두 다리가 손에 쥔 값을 본다.
    """
    from nexus.search import hybrid

    got: dict[str, object] = {}

    async def spy_bm25(query, tenant, clearance, top_k=20, window=None, exclude_doc_types=()):
        got["bm25"] = tuple(exclude_doc_types)
        return [], None

    async def spy_vector(query, svc, tenant, clearance, top_k=20, column=None,
                         window=None, exclude_doc_types=()):
        got["vector"] = tuple(exclude_doc_types)
        return [], None

    async def no_enrich(fused, tenant, max_snippet_chars=300):
        return []

    monkeypatch.setattr(hybrid, "_bm25_search", spy_bm25)
    monkeypatch.setattr(hybrid, "_vector_search", spy_vector)
    monkeypatch.setattr(hybrid, "_enrich_hits", no_enrich)

    result = await hybrid.hybrid_search(
        "파지 실패", tenant="t", clearance="INTERNAL", route="hybrid_only",
        embedding_svc=object(), exclude_doc_types=[" spec ", "design_doc", "spec"])

    assert got.get("bm25") == ("spec", "design_doc"), \
        f"키워드 다리가 받은 것: {got.get('bm25')!r}"
    assert got.get("vector") == ("spec", "design_doc"), \
        f"벡터 다리가 받은 것: {got.get('vector')!r} — 한 다리만 걸리면 필터가 무의미하다"
    assert got["bm25"] == got["vector"], \
        "두 다리가 다른 목록을 받았다 — 정규화가 갈렸다는 뜻이다"
    assert result.excluded_doc_types == ["spec", "design_doc"], \
        "호출자가 실제로 적용된 목록을 응답에서 볼 수 없다"


@pytest.mark.asyncio
async def test_the_nested_search_of_the_correction_pass_inherits_the_exclusion(monkeypatch):
    """⛔ **랭킹에서만 걸리고 읽는 사람 앞에서는 안 걸리던 것 (실측 2026-09-20).**

    라이브에서 `spec`·`design_doc` 을 뺐는데 근거에 설계 일지 조각 둘이 앉았다. 히트에는
    0건이었다 — 정정 패스가 **새 질의로 검색을 다시 부르면서** 제외를 안 들고 갔기 때문이다.

    ⭐ 그래서 `packet_for_answer` 는 제외를 **인자로 받지 않는다.** `SearchResult` 에 이미
    실려 있는 것을 읽는다 — 답변 표면이 셋인데 표면마다 넘기게 두면 하나가 잊고, 그 조합은
    검사가 초록인 채로 틀린다.
    """
    from nexus.search import reconcile

    seen: list[tuple] = []

    async def spy_search(query, **kw):
        seen.append(tuple(kw.get("exclude_doc_types") or ()))

        class _R:
            hits: list = []
        return _R()

    class _Hit:
        rid = "c1"
        chunk_text = "정원 정책이 개정되었다"

    monkeypatch.setattr(reconcile, "names_in", lambda _t: ["정원"])
    await reconcile.corrections_for([_Hit()], "t", "INTERNAL", search=spy_search,
                                    exclude_doc_types=("spec", "design_doc"))

    assert seen, "정정 패스가 검색을 한 번도 안 불렀다 — 이 검사가 아무것도 안 지킨다"
    assert all(s == ("spec", "design_doc") for s in seen), \
        f"중첩 검색이 제외를 안 들고 갔다: {seen!r}"


def test_the_packet_seam_reads_the_exclusion_off_the_result():
    """제외가 **인자로 전달되지 않는다**는 성질 자체를 박아 둔다.

    인자가 되는 순간 표면 셋이 각자 넘겨야 하고, 하나가 잊으면 그 표면만 조용히 샌다.
    """
    import inspect

    from nexus.search.reconcile import packet_for_answer

    params = inspect.signature(packet_for_answer).parameters
    assert "exclude_doc_types" not in params, \
        ("제외가 `packet_for_answer` 의 인자가 됐다 — 표면마다 넘기면 하나가 잊는다. "
         "`result.excluded_doc_types` 를 읽어야 검색과 보강이 어긋날 수 없다")
    assert "excluded_doc_types" in inspect.getsource(packet_for_answer), \
        "보강이 검색의 제외를 안 읽는다"


@pytestmark_db
@pytest.mark.asyncio
async def test_the_legs_accept_it_in_their_own_signature(db_pool):
    """위 검사의 보조 — 인자 이름이 바뀌면 여기서 먼저 말해 준다."""
    import inspect

    from nexus.search.hybrid import _bm25_search, _vector_search

    for fn in (_bm25_search, _vector_search):
        assert "exclude_doc_types" in inspect.signature(fn).parameters, \
            f"{fn.__name__} 이 종류 제외를 안 받는다"