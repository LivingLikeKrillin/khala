"""절 채움을 **진짜 Postgres 에** 대고, **네 표면이 지나는 경로 전체로** 돌린다.

이 리포는 '테스트 초록인데 동작 안 함' 을 네 형태로 겪었고 그중 둘이 여기 걸린다: 배선 누락과
사본이 정본 그물 밖. 그래서 단언하는 것은 함수의 반환값이 아니라 **LLM 프롬프트에 그 절의 본문이
실제로 들어갔는가**다 — 채움이 어디서 끊겨도 이 검사가 빨간불이 된다.

그리고 일부러 깨뜨린다: 상한을 못 채운 문서는 안 채워지는가, **등급이 막은 절은 새지 않는가**.
"""

from __future__ import annotations

import os

import pytest

from nexus.search import hybrid
from nexus.search.evidence_packet import assemble_packet, format_for_llm
from nexus.search.section_fill import MAX_DOC_CHUNKS

pytestmark = [
    pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요"),
]

_TENANT = "section_fill_test"
_QUERY = "정책 문서"
#: 질의와 어휘를 **하나도** 공유하지 않는 절. 라이브 코퍼스가 보여 준 모양이다 —
#: 답이 여기 있는데 어떤 랭킹으로도 못 올라온다.
_ANSWER = "보관 한도는 열두 상자다"
_SECRET = "이 문장은 등급이 막는다"


async def _doc(con, key: str, title: str, chunks: list[tuple[str, str]]) -> str:
    """`chunks` = [(본문, 등급)]. rid 를 돌려준다."""
    from nexus import db
    from nexus.index.bm25 import active_tokenizer
    from nexus.rid import chunk_rid, doc_rid

    uri = f"{_TENANT}:{key}"
    drid = doc_rid(uri)
    await con.execute(
        "INSERT INTO documents (rid,tenant,source_uri,hash,content_hash,title,status) "
        "VALUES ($1,$2,$3,'h','h',$4,'active')", drid, _TENANT, uri, title)
    for i, (text, cls) in enumerate(chunks):
        crid = chunk_rid(drid, "root", i)
        await con.execute(
            "INSERT INTO chunks (rid,tenant,source_uri,doc_rid,chunk_text,section_path,"
            "chunk_index,status,hash,classification,tsvector_ko) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,'active','h',$8::classification_level,"
            "to_tsvector('simple',$9))",
            crid, _TENANT, uri, drid, text, f"{i}. 절", i, cls,
            " ".join(active_tokenizer().tokenize(text)))
    _ = db
    return drid


@pytest.fixture
async def corpus(db_pool):
    """문서 셋: 상한을 채우는 것 · 못 채우는 것 · 너무 큰 것."""
    from nexus import db

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)

        # A: 질의에 걸리는 절 셋(상한 2를 채운다) + 안 걸리는 정답 절 + 등급이 막은 절
        await _doc(con, "a.md", "정책 A", [
            ("정책 문서 개요", "INTERNAL"),
            ("정책 문서 상세", "INTERNAL"),
            ("정책 문서 부록", "INTERNAL"),
            (_ANSWER, "INTERNAL"),
            (_SECRET, "RESTRICTED"),
        ])
        # B: 걸리는 절 하나뿐 — 상한을 못 채운다
        await _doc(con, "b.md", "정책 B", [
            ("정책 문서 참고", "INTERNAL"),
            ("여기는 안 걸린다", "INTERNAL"),
        ])
        # C: 상한은 채우지만 문서가 너무 크다
        await _doc(con, "c.md", "정책 C",
                   [("정책 문서 " + str(i), "INTERNAL") for i in range(MAX_DOC_CHUNKS + 2)])
        yield
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)


def _cfg(cap: int) -> dict:
    return {"search": {"diversity_per_doc_cap": cap, "bm25_top_k": 50, "vector_top_k": 50}}


async def _search(cap: int, clearance: str = "INTERNAL"):
    # embedding_svc 없이 = BM25 다리만. 채움은 벡터와 무관하고, 키 없이 돌아야 한다.
    return await hybrid.hybrid_search(
        _QUERY, tenant=_TENANT, clearance=clearance, top_k=10,
        embedding_svc=None, config=_cfg(cap))


async def test_saturated_doc_fills_the_section_no_ranking_reached(corpus):
    """어휘를 공유하지 않아 **어떤 랭킹으로도 못 오는 절**이 근거에 들어온다."""
    res = await _search(cap=2)

    assert all(_ANSWER not in (h.chunk_text or "") for h in res.hits), \
        "전제가 깨졌다 — 정답 절이 랭킹으로 올라왔다면 이 기능은 아무것도 증명하지 않는다"
    assert any(_ANSWER in (f.chunk_text or "") for f in res.fill)
    # 순위는 건드리지 않는다
    assert len(res.hits) == len([h for h in res.hits if h.score > 0])


async def test_fill_reaches_the_llm_prompt(corpus):
    """**배선 전체.** 검색 → 패킷 → 프롬프트. 어디서 끊겨도 여기서 빨간불."""
    res = await _search(cap=2)
    packet = await assemble_packet(res.hits, res.graph, _TENANT, fill=res.fill)
    prompt = format_for_llm(packet)

    assert _ANSWER in prompt, "채운 절이 프롬프트에 없다 — 배선이 끊겼다"
    assert any(s.chunk_rid for s in packet.snippets if _ANSWER in (s.full_text or ""))


async def test_fill_is_omitted_when_the_packet_is_not_told(corpus):
    """`fill` 을 안 주면 패킷은 **오늘과 같다** — 옛 호출부 81곳이 이 약속 위에 있다."""
    res = await _search(cap=2)
    packet = await assemble_packet(res.hits, res.graph, _TENANT)
    assert _ANSWER not in format_for_llm(packet)
    assert len(packet.snippets) == len(res.hits)


async def test_unsaturated_doc_is_not_filled(corpus):
    """상한을 못 채운 문서는 안 채운다 — 방아쇠가 '몰표' 라는 뜻을 지키는가."""
    res = await _search(cap=2)
    b_titles = {f.doc_title for f in res.fill}
    assert "정책 B" not in b_titles


async def test_oversized_doc_is_not_merged(corpus):
    """큰 문서는 통째로 안 붙인다 — 근거가 문서로 바뀌는 것을 막는 유일한 상한."""
    res = await _search(cap=2)
    assert "정책 C" not in {f.doc_title for f in res.fill}


async def test_clearance_gate_holds_for_filled_sections(corpus):
    """**등급이 막은 절은 새지 않는다.** 채움은 보강이지 우회로가 아니다."""
    res = await _search(cap=2)
    packet = await assemble_packet(res.hits, res.graph, _TENANT, fill=res.fill)
    assert _SECRET not in format_for_llm(packet)
    assert all(f.classification != "RESTRICTED" for f in res.fill)


async def test_rule_off_when_cap_disabled(corpus):
    """상한이 0 이하면 규칙을 끈 것 — 전 문서가 채워지는 사고를 막는다."""
    res = await _search(cap=0)
    assert res.fill == []
