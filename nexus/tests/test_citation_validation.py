"""인용 사후검증 — SPEC-nexus-citation-validation §4·§6.

LLM 없이 순수 함수로 검증한다: 답변의 [출처: …] 를 packet 의 실제 스니펫 제목과 대조해
verified/unverified 를 판정. 그리고 generate_answer 배선(주입 LLM)까지.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from nexus.llm.citations import validate_citations


@dataclass
class _Snip:
    doc_title: str
    section_path: str = "s"
    text: str = "본문"
    chunk_rid: str = "c"
    source_uri: str = "u"
    score: float = 0.9
    doc_type: str = "DESIGN_DOC"
    classification: str = "INTERNAL"
    updated_at: object = None


@dataclass
class _Packet:
    snippets: list = field(default_factory=list)
    graph: object = None
    provenance: list = field(default_factory=list)


def _pkt(*titles):
    return _Packet(snippets=[_Snip(t) for t in titles])


# ── §4.1 순수 검증기 ──────────────────────────────────────────────────────────

def test_real_title_is_verified():
    rep = validate_citations("결제는 Kafka로 발행한다 [출처: 결제 설계 문서, 아키텍처].",
                             _pkt("결제 설계 문서"))
    assert len(rep.citations) == 1
    assert rep.citations[0].verified is True
    assert rep.citations[0].section == "아키텍처"
    assert rep.unverified_count == 0


def test_fabricated_title_is_unverified():
    rep = validate_citations("답 [출처: 존재하지 않는 문서, 어딘가].", _pkt("결제 설계 문서"))
    assert rep.citations[0].verified is False
    assert rep.unverified_count == 1


def test_case_and_whitespace_difference_still_verified():
    rep = validate_citations("답 [출처:  결제   설계 문서 ].", _pkt("결제 설계 문서"))
    assert rep.citations[0].verified is True     # 정규화 → 오탐 아님


def test_no_citation_is_empty():
    rep = validate_citations("근거를 찾지 못했습니다.", _pkt("결제 설계 문서"))
    assert rep.citations == []
    assert rep.unverified_count == 0


def test_mixed_real_and_fabricated_counted():
    rep = validate_citations(
        "A [출처: 결제 설계 문서]. B [출처: 가짜 문서]. C [출처: API 명세].",
        _pkt("결제 설계 문서", "API 명세"))
    assert rep.unverified_count == 1              # '가짜 문서' 하나만
    assert sum(1 for c in rep.citations if c.verified) == 2


def test_title_containing_comma_verifies_by_prefix_not_first_comma():
    # 제목 자체에 콤마가 있다: 'Report, Inc' 가 packet 에 있고, 섹션은 '아키텍처'
    rep = validate_citations("답 [출처: Report, Inc, 아키텍처].", _pkt("Report, Inc"))
    assert rep.citations[0].verified is True
    assert rep.citations[0].section == "아키텍처"


def test_malformed_fragment_does_not_raise():
    # 닫히지 않은 [출처: 는 무시(크래시 금지)
    rep = validate_citations("답 [출처: 결제 설계 문서 without close", _pkt("결제 설계 문서"))
    assert isinstance(rep.unverified_count, int)   # 예외 없이 반환


# ── §4.2 generate_answer 배선 ─────────────────────────────────────────────────

class _FakeLLM:
    def __init__(self, answer):
        self._answer = answer
        self.configured = True

    async def generate_full(self, system, user, max_tokens=4096):
        from nexus.providers.llm import LLMResult, Usage
        return LLMResult(text=self._answer, usage=Usage(None, None, None, "fake"))


@pytest.mark.asyncio
async def test_generate_answer_attaches_citation_report():
    from nexus.llm.answer import generate_answer

    packet = _pkt("결제 설계 문서")
    llm = _FakeLLM("결제는 Kafka [출처: 결제 설계 문서]. 그리고 [출처: 지어낸 문서].")
    res = await generate_answer("결제 토픽?", packet, llm)   # type: ignore[arg-type]
    assert res.unverified_citations == 1
    assert any(c["verified"] for c in res.citations)
    assert any(not c["verified"] for c in res.citations)
