"""근거 점유율 — 순수 계산 + **행이 실제로 앉는가**.

**무엇을 지키나 (SPEC-nexus-design-corpus-cutover §5.3).** `read_scope` 는 *읽을 수 있었던*
범위이고 이 값은 *읽은 것*이다. 둘이 갈리는 상태 — 범위를 넓혀 놓고 근거가 여전히 한쪽에서만
오는 것 — 을 보려고 만든 칸이므로, **패킷에서 세는가**가 이 파일의 핵심 단언이다. 히트만
세면 채운 절·짝 문서·정정 확인 패스가 빠지고, 그 셋이 바로 컷오버가 설계 코퍼스에서
끌어오는 근거다.

⚠ 그리고 **행이 앉는지**를 따로 묻는다. 이 리포는 필드가 있는 것과 행이 앉는 것이 다르다는
것을 34시간짜리 침묵으로 배웠다.
"""

from __future__ import annotations

import os

import pytest

from nexus.search import evidence_share as ES


class _Piece:
    def __init__(self, tenant: str) -> None:
        self.tenant = tenant


# ── 순수 ─────────────────────────────────────────────────────────────────────

def test_counts_are_ordered_by_size_then_name():
    """읽는 사람이 **무엇이 지배하는가**를 첫 줄에서 본다."""
    items = [_Piece("default")] * 2 + [_Piece("design_docs")] * 5 + [_Piece("alpha")] * 2
    assert ES.counts(items) == [("design_docs", 5), ("alpha", 2), ("default", 2)]


def test_encode_is_a_string_a_text_column_can_hold():
    """⛔ 목록을 `str` 칸에 넣었다가 적재가 34시간 조용히 죽었다. 직렬화는 여기 하나뿐이다."""
    out = ES.encode([_Piece("design_docs")] * 6 + [_Piece("default")] * 4)
    assert out == "design_docs:6,default:4"
    assert isinstance(out, str)


def test_no_evidence_is_none_not_an_empty_string():
    """빈 문자열은 *근거 0* 과 *형식 오류* 를 못 가른다. `None` 하나만 쓴다."""
    assert ES.encode([]) is None
    assert ES.encode(None) is None


def test_a_piece_without_a_tenant_is_counted_not_dropped():
    """⛔ 버리면 분모가 조용히 줄고 그러면 비율이 틀린다. 이 이름이 보이면 배선이 빠진 것."""
    assert ES.encode([_Piece("default"), _Piece("")]) == "(미상):1,default:1"


def test_decode_round_trips():
    items = [_Piece("design_docs")] * 3 + [_Piece("default")]
    assert ES.decode(ES.encode(items)) == ES.counts(items)


def test_decode_survives_a_row_it_cannot_read():
    """옛 행·손으로 고친 행이 들어와도 요약이 죽지 않는다."""
    assert ES.decode("garbage") == []
    assert ES.decode(None) == []
    assert ES.decode("default:2,broken,design_docs:1") == [("default", 2), ("design_docs", 1)]


def test_summarize_says_nothing_when_there_is_nothing():
    assert "없다" in ES.summarize([None, ""])


def test_summarize_separates_the_total_from_the_lean():
    """합계만 내면 큰 질문 몇 개가 분포를 지배하고, 쏠림만 내면 양이 사라진다."""
    text = ES.summarize(["design_docs:6,default:4", "default:10", "design_docs:3"])
    assert "질문 3건" in text and "조각 23개" in text
    assert "섞임 — 1건" in text
    assert "문턱은 없다" in text, "문턱을 도입하면 이 검사가 빨간불이 돼야 한다"


def test_a_small_sample_gets_counts_but_no_percentages():
    """⛔ 질문 하나로 낸 `100.0%` 는 인용될 만해 보인다. 그게 이 규율이 있는 이유다."""
    small = ES.summarize(["default:18"])
    assert "18개" in small
    assert "%" not in small, "표본이 모자란데 비율을 냈다"
    assert "표본이 아니다" in small


def test_a_big_enough_sample_gets_percentages():
    """대조군 — 규율이 비율을 **영원히** 끄는 것이 아니다."""
    big = ES.summarize([f"default:{i + 1}" for i in range(ES.MIN_SAMPLE)])
    assert "%" in big
    assert "표본이 아니다" not in big


# ── 배선: 패킷에서 세는가, 그리고 행이 앉는가 ────────────────────────────────

pytestmark_db = pytest.mark.skipif(
    not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "evidence_share_test"
_OTHER = "evidence_share_test_other"


def _sig(**kw):
    from nexus.search.hybrid import SearchResult
    from nexus.search.signals import extract_signals
    return extract_signals(SearchResult(route_used="hybrid_only"), None,
                           path="t", tenant=_TENANT, clearance="INTERNAL",
                           query="질문", **kw)


def test_the_signal_falls_back_to_hits_when_no_packet_is_given():
    """새 호출부가 아무것도 안 해도 이 칸이 비지 않는다."""
    from nexus.search.hybrid import SearchHit, SearchResult
    from nexus.search.signals import extract_signals

    result = SearchResult(route_used="hybrid_only")
    result.hits = [SearchHit(rid="a", doc_rid="d", tenant="default")]
    sig = extract_signals(result, None, path="t", tenant="default",
                          clearance="INTERNAL", query="질문")
    assert sig.evidence_tenants == "default:1"


def test_an_explicit_packet_wins_over_the_hits():
    """답변 경로는 패킷을 넘긴다 — 채움·짝·정정이 히트에 없기 때문이다."""
    from nexus.search.hybrid import SearchHit, SearchResult
    from nexus.search.signals import extract_signals

    result = SearchResult(route_used="hybrid_only")
    result.hits = [SearchHit(rid="a", doc_rid="d", tenant="default")]
    sig = extract_signals(result, None, path="t", tenant="default",
                          clearance="INTERNAL", query="질문",
                          evidence=[_Piece("default"), _Piece("design_docs")])
    assert sig.evidence_tenants == "default:1,design_docs:1"


@pytestmark_db
@pytest.mark.asyncio
async def test_the_row_actually_lands_with_its_share(db_pool):
    """⛔ 필드가 있는 것과 행이 앉는 것은 다르다."""
    from nexus import db
    from nexus.search.signals import record_search

    db._pool = db_pool
    await db.ensure_search_log()
    async with db_pool.acquire() as con:
        before = await con.fetchval("SELECT count(*) FROM search_log")

    await record_search(_sig(evidence=[_Piece("default")] * 2 + [_Piece("design_docs")]),
                        await_persist=True)

    async with db_pool.acquire() as con:
        row = await con.fetchrow(
            "SELECT evidence_tenants FROM search_log ORDER BY id DESC LIMIT 1")
        after = await con.fetchval("SELECT count(*) FROM search_log")
    db._pool = None

    assert after == before + 1, "행이 안 앉았다 — 적재가 조용히 죽는 그 모양이다"
    assert row["evidence_tenants"] == "default:2,design_docs:1"


async def _seed_doc(con, tenant: str, uri_tail: str, title: str, texts: list[str]) -> None:
    from nexus.index.bm25 import active_tokenizer
    from nexus.rid import chunk_rid, doc_rid

    uri = f"{tenant}:{uri_tail}"
    drid = doc_rid(uri)
    await con.execute(
        "INSERT INTO documents (rid,tenant,source_uri,hash,content_hash,title,status) "
        "VALUES ($1,$2,$3,'h','h',$4,'active')", drid, tenant, uri, title)
    for i, text in enumerate(texts):
        await con.execute(
            "INSERT INTO chunks (rid,tenant,source_uri,doc_rid,chunk_text,section_path,"
            "chunk_index,status,hash,classification,tsvector_ko) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,'active','h','INTERNAL'::classification_level,"
            "to_tsvector('simple',$8))",
            chunk_rid(drid, "root", i), tenant, uri, drid, text, f"{i}. 절", i,
            " ".join(active_tokenizer().tokenize(text)))


@pytest.fixture
async def two_tenant_corpus(db_pool):
    """두 코퍼스에 각각 걸리는 문서. A 는 다양성 상한을 채워 **채움**도 같이 건다."""
    from nexus import db

    previous_pool = db._pool
    db._pool = db_pool
    async with db_pool.acquire() as con:
        for t in (_TENANT, _OTHER):
            await con.execute("DELETE FROM chunks WHERE tenant=$1", t)
            await con.execute("DELETE FROM documents WHERE tenant=$1", t)
        await _seed_doc(con, _TENANT, "a.md", "정책 A", [
            "정책 문서 개요", "정책 문서 상세", "정책 문서 부록", "보관 한도는 열두 상자다"])
        await _seed_doc(con, _OTHER, "b.md", "설계 B", ["정책 문서 설계 노트"])
        yield
        for t in (_TENANT, _OTHER):
            await con.execute("DELETE FROM chunks WHERE tenant=$1", t)
            await con.execute("DELETE FROM documents WHERE tenant=$1", t)
    db._pool = previous_pool


@pytestmark_db
@pytest.mark.asyncio
async def test_the_share_counts_the_packet_not_the_hits(two_tenant_corpus):
    """⛔ **이 파일의 핵심 단언.**

    채운 절은 랭킹을 거치지 않으므로 `result.hits` 에 없다. 히트만 세면 답변이 기댄 코퍼스를
    과소평가하고, 그러면 이 칸은 컷오버가 값을 냈는지 못 말한다.
    """
    from nexus.search import hybrid
    from nexus.search.reconcile import packet_for_answer

    scope = (_TENANT, _OTHER)
    cfg = {"search": {"diversity_per_doc_cap": 2, "bm25_top_k": 50, "vector_top_k": 50,
                      "section_fill": True}}
    result = await hybrid.hybrid_search(
        "정책 문서", tenant=scope, clearance="INTERNAL", top_k=10,
        embedding_svc=None, config=cfg)
    packet = await packet_for_answer(
        result, scope, "INTERNAL", config=cfg, search=hybrid.hybrid_search,
        embedding_svc=None, question="정책 문서", pool=None)

    from_hits = dict(ES.counts(result.hits))
    from_packet = dict(ES.counts(packet.snippets))

    assert sum(from_packet.values()) > sum(from_hits.values()), \
        "패킷이 히트보다 크지 않다 — 채움이 안 걸렸으면 이 검사는 아무것도 증명하지 않는다"
    assert set(from_packet) == {_TENANT, _OTHER}, \
        "두 코퍼스에서 왔는데 한쪽만 세어졌다"
    assert ES.UNKNOWN not in from_packet, \
        "조각에 테넌트가 안 실렸다 — SearchHit 을 만드는 자리 하나가 배선에서 빠졌다"
