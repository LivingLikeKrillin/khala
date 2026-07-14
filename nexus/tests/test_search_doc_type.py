"""축-A doc_type 가 *검색 HTTP 응답*까지 도달하는지 가드.

S3 가 doc_type 을 SearchHit/EvidenceSnippet/format_for_llm 에 보존했지만, HTTP 직렬화
(`/search` 의 results, `/search/answer` 의 evidence_snippets)가 필드를 떨궈 웹 클라이언트가
타입 배지를 못 그렸다(라이브 적재 실증서 관찰). 이 테스트가 두 직렬화 경로를 모두 잠근다.
"""

from __future__ import annotations

from nexus.api import _search_hit_to_dict
from nexus.llm.answer import generate_answer
from nexus.search.evidence_packet import assemble_packet
from nexus.search.hybrid import SearchHit


def _hit(doc_type="DESIGN"):
    return SearchHit(
        rid="chunk_1", doc_rid="doc_1", doc_title="결제 설계",
        section_path="개요", source_uri="git:payment.md",
        snippet="결제 서비스 명세", score=0.9, classification="INTERNAL",
        doc_type=doc_type,
    )


def test_search_hit_dict_includes_doc_type():
    out = _search_hit_to_dict(_hit("DESIGN"))
    assert out["doc_type"] == "DESIGN"


def test_search_hit_dict_missing_doc_type_is_empty_string():
    out = _search_hit_to_dict(_hit(""))
    assert out["doc_type"] == ""


def test_search_hit_dict_keeps_existing_fields():
    out = _search_hit_to_dict(_hit("ADR"))
    # 회귀 방지: 기존 계약 필드를 떨구지 않는다.
    for key in ("rid", "doc_rid", "doc_title", "section_path", "source_uri",
                "snippet", "score", "bm25_rank", "vector_rank", "classification"):
        assert key in out


class _FakeLLM:
    async def generate_full(self, system_prompt: str, user_prompt: str):
        from nexus.providers.llm import LLMResult, Usage
        return LLMResult(text="근거 기반 답변", usage=Usage(None, None, None, "fake"))


async def test_answer_evidence_snippets_include_doc_type():
    packet = assemble_packet([_hit("RUNBOOK")])
    result = await generate_answer("질문", packet, _FakeLLM())
    assert result.evidence_snippets[0]["doc_type"] == "RUNBOOK"
