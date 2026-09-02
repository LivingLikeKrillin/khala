"""검색 재현율 회귀 세트 — SPEC-nexus-search-recall §4.3.

**이 파일이 없어서 BM25 경로가 몇 년째 침묵하는 줄 아무도 몰랐다.** `tests/` 어디에도
"이 질의는 이 문서를 찾아야 한다" 는 단언이 없었다. 여기 그것을 둔다.

살아 있는 `default` 코퍼스가 아니라 **리포에 고정된 fixture** 를 쓴다. 누가 Notion 을
동기화할 때마다 바뀌는 코퍼스에 바닥값을 못 박으면, 그건 아무것에도 못 박지 않은 것이다.

측정 전에 **평가 하니스를 먼저 검사한다.** 조사 중에 정답 id 를 8자 접두사로 줬다가 서로 다른 두
페이지에 매칭됐고, 채점기가 정답 1위를 '회귀' 로 기록했다. 그 회귀를 고치려고 설계를 하나
만들 뻔했다. 평가 하니스가 틀린 측정은 약한 측정이 아니라 허구다.
"""

from __future__ import annotations

import os

import pytest

from nexus.index.bm25 import _get_mecab, tokenize_korean


def _has_mecab() -> bool:
    return _get_mecab() is not None


# 이 스위트는 **mecab-ko 가 있어야만 의미가 있다.** 없으면 `tokenize_korean` 이 공백 분리로
# 내려앉고, 그건 프로덕션이 쓰는 토크나이저가 아니다 — 다른 평가 하니스로 측정한 숫자는 바닥값이 아니다.
# mecab 은 Dockerfile 에서 소스 빌드된다. 그래서 CI 는 이 파일을 **이미지 안에서** 돌린다.
pytestmark = [
    pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요"),
    pytest.mark.skipif(not _has_mecab(), reason="mecab-ko 없음 — 프로덕션 토크나이저가 아니면 측정하지 않는다"),
]

_TENANT = "recall_fixture"

#: 고정 코퍼스. 본문이 여기 있으므로 무엇이 매칭되는지 눈으로 확인할 수 있다.
DOCS: dict[str, str] = {
    "entity": (
        "## Entity 식별\n\n"
        "도메인 모델에서 Entity 는 고유한 식별자를 갖는 객체다. "
        "Value Object 는 식별자 없이 속성으로만 동등성을 판단한다."
    ),
    "index": (
        "## Index 접근 방식\n\n"
        "데이터베이스 인덱스는 Sequential Access 와 Random Access 를 지원한다. "
        "B+ Tree 는 범위 조회에 유리하다."
    ),
    "join": (
        "## Join 유형\n\n"
        "논리적인 조인 유형에는 Inner Join, Outer Join, Cross Join 이 있다."
    ),
    "tunnel": (
        "## Cloudflare 터널 배포\n\n"
        "팀에 배포할 때는 cloudflared 터널을 열고 Access 로 보호한다."
    ),
    "lock": (
        "## 락 개념 정리\n\n"
        "비관적 락과 낙관적 락은 경합을 다루는 방식이 다르다."
    ),
}

#: (질의, 정답 문서 키, 매칭을 지탱할 것으로 기대하는 어휘)
#:
#: 기대 어휘를 명시한다 — "content word 가 들어 있으면" 같은 말은 mecab 이 무엇을 어휘로
#: 보는지 우리가 모르기 때문에 테스트가 될 수 없다 (SPEC I-002, I-003).
QUERIES: list[tuple[str, str, str]] = [
    ("엔티티를 어떻게 식별하나", "entity", "식별"),
    ("데이터베이스 인덱스는 어떤 접근 방식이 있나", "index", "인덱스"),
    ("조인의 논리적 유형에는 어떤 것들이 있나", "join", "유형"),
    ("Cloudflare 터널로 팀에 배포하는 방법", "tunnel", "터널"),
    ("락 개념 정리", "lock", "락"),
    ("Value Object 로 식별해야 하는 경우", "entity", "식별"),
]

#: 2026-07-10, 위 fixture 에서 측정. 올리면 진보이고, 내리면 같은 커밋에서 이유를 말해야 한다.
KEYWORD_MISSES_MAX = 0
KEYWORD_MRR_MIN = 0.80
FUSED_MISSES_MAX = 0


@pytest.fixture
async def corpus(db_pool):
    from nexus import db
    from nexus.index.bm25 import index_chunk_bm25

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
        for key, text in DOCS.items():
            rid = f"doc_{key}"
            await con.execute(
                "INSERT INTO documents (rid, tenant, source_uri, hash, content_hash, title, status) "
                "VALUES ($1,$2,$3,'h','h',$4,'active')",
                rid, _TENANT, f"{_TENANT}:{key}.md", key)
            await con.execute(
                "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, chunk_text, section_path, "
                "chunk_index, status, hash) VALUES ($1,$2,$3,$4,$5,'root',0,'active','h')",
                f"chunk_{key}", _TENANT, f"{_TENANT}:{key}.md", rid, text)

    class _C:
        def __init__(self, t):
            self.chunk_text, self.section_path, self.context_prefix = t, "root", None

    for key, text in DOCS.items():
        await index_chunk_bm25(f"chunk_{key}", _C(text))

    yield
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    db._pool = None


# ── 평가 하니스를 먼저 검사한다 ────────────────────────────────────────────────────────

async def test_every_gold_label_resolves_to_exactly_one_document(corpus):
    from nexus import db

    for _, gold, _ in QUERIES:
        n = await db.fetch_val(
            "SELECT count(*) FROM documents WHERE tenant=$1 AND source_uri LIKE '%'||$2||'%'",
            _TENANT, f"{gold}.md")
        assert n == 1, f"정답 라벨 '{gold}' 이 문서 {n}건에 매칭된다 — 측정 이전에 틀렸다"


async def test_the_label_gate_fires_on_an_ambiguous_reference(corpus):
    """게이트가 실제로 무는지 확인한다. `.md` 없이 'in' 만 주면 index/join 둘 다 걸린다."""
    from nexus import db

    n = await db.fetch_val(
        "SELECT count(*) FROM documents WHERE tenant=$1 AND source_uri LIKE '%'||$2||'%'",
        _TENANT, "n")
    assert n > 1, "모호한 참조가 1건에만 매칭되면 이 테스트는 게이트를 검증하지 못한다"


# ── 키워드 경로 (이 단언이 몇 년간 없었다) ────────────────────────────────────

async def test_the_expected_lexeme_actually_survives_tokenisation(corpus):
    """기대 어휘가 mecab 을 통과하지 못하면, 재현율 테스트는 엉뚱한 것을 측정하게 된다."""
    for query, gold, lexeme in QUERIES:
        assert lexeme in tokenize_korean(query), f"'{query}' 의 토큰에 '{lexeme}' 이 없다"
        assert lexeme in tokenize_korean(DOCS[gold]), f"'{gold}' 문서 토큰에 '{lexeme}' 이 없다"


@pytest.mark.parametrize(("query", "gold", "lexeme"), QUERIES)
async def test_the_keyword_leg_alone_finds_the_gold_document(corpus, query, gold, lexeme):
    """AND 였을 때 이 질의들 대부분이 0건을 반환했다 (SPEC §3.1)."""
    from nexus.search import hybrid

    hits, _top = await hybrid._bm25_search(query, _TENANT, "INTERNAL", 20)
    assert hits, f"'{query}' — 키워드 경로가 아무것도 반환하지 않았다 ('{lexeme}' 는 문서에 있다)"
    assert any(r == f"chunk_{gold}" for r, _ in hits), f"'{query}' → {gold} 를 못 찾았다"


async def test_the_keyword_leg_holds_its_recall_floor(corpus):
    from nexus.search import hybrid

    misses, rr = 0, 0.0
    for query, gold, _ in QUERIES:
        hits, _top = await hybrid._bm25_search(query, _TENANT, "INTERNAL", 20)
        rank = next((i + 1 for i, (r, _) in enumerate(hits) if r == f"chunk_{gold}"), None)
        misses += rank is None
        rr += 1 / rank if rank else 0

    assert misses <= KEYWORD_MISSES_MAX
    assert rr / len(QUERIES) >= KEYWORD_MRR_MIN, f"MRR {rr / len(QUERIES):.3f} < {KEYWORD_MRR_MIN}"


async def test_and_semantics_would_break_this_suite(corpus):
    """되돌림 방지: `&` 로 조립하면 이 fixture 에서도 재현율이 무너진다는 것을 직접 보인다."""
    from nexus.search import hybrid

    original = hybrid.tokens_to_tsquery
    hybrid.tokens_to_tsquery = lambda ts: " & ".join(f"'{t}'" for t in ts if t.strip())
    try:
        misses = 0
        for query, gold, _ in QUERIES:
            hits, _top = await hybrid._bm25_search(query, _TENANT, "INTERNAL", 20)
            misses += not any(r == f"chunk_{gold}" for r, _ in hits)
    finally:
        hybrid.tokens_to_tsquery = original

    assert misses > KEYWORD_MISSES_MAX, "AND 로 되돌려도 통과한다면 이 스위트는 아무것도 지키지 않는다"


# ── 융합 ──────────────────────────────────────────────────────────────────────

async def test_the_fused_search_finds_every_gold_document_without_the_vector_leg(corpus):
    """임베딩 없이도(=BM25 만으로) 융합이 정답을 놓치지 않는다."""
    from nexus.search import hybrid

    misses = 0
    for query, gold, _ in QUERIES:
        res = await hybrid.hybrid_search(query, tenant=_TENANT, top_k=10,
                                         embedding_svc=None, route="keyword_only")
        misses += not any(f"{gold}.md" in h.source_uri for h in res.hits)
    assert misses <= FUSED_MISSES_MAX
