"""읽기 범위가 **목록**일 때 근거 보강 셋이 그대로 도는가 — 진짜 Postgres 에 대고.

⛔ **왜 이 검사가 있나 (실측 2026-09-02).** `effective_read_scope` 가 2026-08-31 부터 범위를
**튜플**로 돌려준다. `section_fill.fill_for_docs` 는 그 값을 `c.tenant = $n` 에 그대로 묶고
있었고, asyncpg 는 튜플을 TEXT 인자로 받지 않는다. 부르는 쪽은 그 예외를 **삼키도록** 만들어져
있어서(보강 실패가 검색을 죽이면 안 된다) 절 채움과 짝 확장이 **모든 HTTP 답변 요청에서**
조용히 꺼졌다 — 원소가 하나여도 튜플이므로 단일 테넌트 배포까지 같이 꺼졌고, 라이브 로그에
이틀치 `section_fill_failed` 가 쌓이는 동안 검사는 전부 초록이었다.

**초록이던 이유가 이 파일의 설계다.** `test_section_fill_db.py` 는 여덟 검사 전부가 테넌트를
**문자열**로 넘겼고, `test_pair_expansion.py` 는 DB 를 아예 안 친다. 그래서 여기서는 단언을
반환값이 아니라 **아무 보강도 조용히 죽지 않았는가**에 건다 — 지금 있는 셋뿐 아니라 앞으로
답변 경로에 붙을 보강까지 같은 회귀 검사에 든다.

세 모양을 다 돈다: 문자열(옛 계약) · 원소 하나 튜플(오늘의 단일 테넌트) · 둘(컷오버 뒤 슬랙).
셋은 SQL 이 서로 다르다 — `tenant_predicate` 가 원소 하나에는 `= $n`, 여럿에는 `= ANY($n)` 을
낸다. 하나만 돌려서는 나머지를 아무것도 보증하지 않는다.
"""

from __future__ import annotations

import os

import pytest
import structlog

from nexus.search import hybrid
from nexus.search.evidence_packet import format_for_llm
from nexus.search.reconcile import packet_for_answer

pytestmark = pytest.mark.skipif(
    not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "scope_enrichment_test"
#: 범위의 두 번째 원소. **비어 있는 테넌트를 일부러 고른다** — 결과가 세 모양에서 같아야
#: 단언이 하나로 서고, 달라지면 그것은 범위 확장이 아니라 코퍼스 차이다.
_ABSENT = "scope_enrichment_test_absent"
_QUERY = "정책 문서"
#: 질의와 어휘를 하나도 공유하지 않는 절 — 어떤 랭킹으로도 못 온다. 채움이 실어야 온다.
_FILLED = "보관 한도는 열두 상자다"
#: 짝 문서(계획)에만 있는 값. 짝 확장이 죽으면 근거에 없다.
_MATE = "이 값은 계획 문서에만 있다"

_SCOPES = [
    pytest.param(_TENANT, id="string"),
    pytest.param((_TENANT,), id="one-element-tuple"),
    pytest.param((_TENANT, _ABSENT), id="two-element-tuple"),
]

_CFG = {"search": {"diversity_per_doc_cap": 2, "bm25_top_k": 50, "vector_top_k": 50,
                   "section_fill": True, "pair_expansion": True}}


async def _doc(con, uri_tail: str, title: str, texts: list[str]) -> str:
    from nexus.index.bm25 import active_tokenizer
    from nexus.rid import chunk_rid, doc_rid

    uri = f"{_TENANT}:{uri_tail}"
    drid = doc_rid(uri)
    await con.execute(
        "INSERT INTO documents (rid,tenant,source_uri,hash,content_hash,title,status) "
        "VALUES ($1,$2,$3,'h','h',$4,'active')", drid, _TENANT, uri, title)
    for i, text in enumerate(texts):
        await con.execute(
            "INSERT INTO chunks (rid,tenant,source_uri,doc_rid,chunk_text,section_path,"
            "chunk_index,status,hash,classification,tsvector_ko) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,'active','h','INTERNAL'::classification_level,"
            "to_tsvector('simple',$8))",
            chunk_rid(drid, "root", i), _TENANT, uri, drid, text, f"{i}. 절", i,
            " ".join(active_tokenizer().tokenize(text)))
    return drid


@pytest.fixture
async def corpus(db_pool):
    """설계 하나 + 그 짝 계획 하나. 설계는 다양성 상한을 채워 절 채움도 같이 건다."""
    from nexus import db

    previous_pool = db._pool
    db._pool = db_pool
    async with db_pool.acquire() as con:
        for t in (_TENANT, _ABSENT):
            await con.execute("DELETE FROM chunks WHERE tenant=$1", t)
            await con.execute("DELETE FROM documents WHERE tenant=$1", t)
        await _doc(con, "superpowers/specs/2026-01-01-thing-design.md", "설계 문서", [
            "정책 문서 개요", "정책 문서 상세", "정책 문서 부록", _FILLED,
        ])
        await _doc(con, "superpowers/plans/2026-01-01-thing.md", "계획 문서", [_MATE])
        yield
        for t in (_TENANT, _ABSENT):
            await con.execute("DELETE FROM chunks WHERE tenant=$1", t)
            await con.execute("DELETE FROM documents WHERE tenant=$1", t)
    db._pool = previous_pool


async def _packet_and_logs(scope):
    """답변 경로를 통째로 한 번 — 그리고 그동안 찍힌 로그 전부."""
    with structlog.testing.capture_logs() as caught:
        result = await hybrid.hybrid_search(
            _QUERY, tenant=scope, clearance="INTERNAL", top_k=10,
            embedding_svc=None, config=_CFG)
        packet = await packet_for_answer(
            result, scope, "INTERNAL", config=_CFG, search=hybrid.hybrid_search,
            embedding_svc=None, question=_QUERY, pool=None)
    return result, packet, caught


#: 이 검사가 보는 것은 **요청 경로의 보강**이지 환경이 아니다. mecab 초기화 실패는 사전이
#: 없는 개발 기계에서 늘 찍히고(CI 에는 있다) 보강과 아무 상관이 없다. 성질과 무관한 이유로
#: 빨간불이 되는 회귀 검사는 곧 지워지고, 지워진 검사는 없는 검사다.
_NOT_AN_ENRICHMENT = {"mecab_init_failed"}


def _silently_dead(caught) -> list[dict]:
    """조용히 죽은 보강. 이름이 아니라 **모양**으로 잡는다 — 다음에 붙을 보강도 같이 든다."""
    return [e for e in caught
            if str(e.get("event", "")).endswith(("_failed", ".failed"))
            and e.get("event") not in _NOT_AN_ENRICHMENT]


@pytest.mark.parametrize("scope", _SCOPES)
async def test_no_enrichment_dies_silently_on_this_scope_shape(corpus, scope):
    """⛔ **가장 중요한 검사.** 보강은 실패를 삼키므로, 죽었는지는 로그로만 보인다."""
    _, _, caught = await _packet_and_logs(scope)
    assert _silently_dead(caught) == [], (
        "보강이 조용히 죽었다 — 사용자는 답을 받고 아무도 모른다")


@pytest.mark.parametrize("scope", _SCOPES)
async def test_the_filled_section_reaches_the_prompt_on_this_scope_shape(corpus, scope):
    """로그가 조용해도 값이 안 붙었을 수 있다. 프롬프트 본문으로 확인한다."""
    result, packet, _ = await _packet_and_logs(scope)
    assert all(_FILLED not in (h.chunk_text or "") for h in result.hits), \
        "전제가 깨졌다 — 채울 절이 랭킹으로 올라왔다면 이 검사는 아무것도 증명하지 않는다"
    assert _FILLED in format_for_llm(packet), "절 채움이 프롬프트에 없다"


@pytest.mark.parametrize("scope", _SCOPES)
async def test_the_mate_document_reaches_the_prompt_on_this_scope_shape(corpus, scope):
    """짝 확장도 같은 함수를 지난다 — 그래서 같은 자리에서 같이 죽었다."""
    _, packet, _ = await _packet_and_logs(scope)
    assert _MATE in format_for_llm(packet), "짝 문서가 프롬프트에 없다"
