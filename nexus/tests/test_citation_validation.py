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


# ── 표면 차이는 지어낸 출처가 아니다 (2026-08-08) ────────────────────────────
#
# 답변 품질을 처음 재던 날, 미검증 인용 23건이 나왔다. 열어보니 **지어낸 출처는 하나도 없었다** —
# 전부 활자 따옴표(‘락’ vs '락')이거나 제목 뒤 괄호를 뗀 것이었다. `unverified_citations` 는 API
# 응답에 실려 웹에서 신뢰 배지가 되므로, 따옴표 한 글자 때문에 경고가 뜨고 있었다.


def _p(*titles):
    return _Packet(snippets=[_Snip(doc_title=t) for t in titles])


def test_typographic_quotes_are_not_a_different_document():
    r = validate_citations("…이다 [출처: 동시성 #1 - '락' 개념 정리, 2절]",
                           _p("동시성 #1 - ‘락’ 개념 정리"))
    assert r.unverified_count == 0
    assert r.citations[0].title == "동시성 #1 - ‘락’ 개념 정리"
    assert r.citations[0].section == "2절"


def test_an_em_dash_written_as_a_hyphen_still_matches():
    r = validate_citations("…[출처: Nexus 2.0 - UI 연동 규격]", _p("Nexus 2.0 — UI 연동 규격"))
    assert r.unverified_count == 0


def test_a_title_cited_without_its_parenthetical_matches():
    r = validate_citations("…[출처: Nexus 팀 도그푸딩 배포 런북, §4]",
                           _p("Nexus 팀 도그푸딩 배포 런북 (로컬 + Cloudflare Tunnel)"))
    assert r.unverified_count == 0
    assert r.citations[0].section == "§4"


def test_an_ambiguous_prefix_is_refused():
    """**받으면 안 되는 쪽.** `동시성` 하나로 세 문서가 다 맞으면 검사가 무너진다."""
    r = validate_citations("…[출처: 동시성]",
                           _p("동시성 #1 - 락", "동시성 #2 - 핫스팟", "동시성 #3 - 제어"))
    assert r.unverified_count == 1


def test_a_fabricated_title_is_still_refused():
    """지어낸 제목은 어떤 실제 제목의 접두도 아니다 — 느슨해진 규칙이 이것까지 통과시키면 안 된다."""
    assert validate_citations("…[출처: 존재하지 않는 사내 규정집]",
                              _p("플레이리스트 정책")).unverified_count == 1


def test_a_prefix_that_stops_mid_word_is_refused():
    """낱말 경계에서 잘린 것만 받는다 — `플레이리` 는 짧은 이름이 아니라 오타다."""
    assert validate_citations("…[출처: 플레이리]", _p("플레이리스트 정책")).unverified_count == 1


def test_an_exact_match_is_never_overridden_by_a_prefix():
    """정확히 일치하는 제목이 있으면 그것이 이긴다."""
    r = validate_citations("…[출처: 로그인 정책]", _p("로그인 정책", "로그인 정책 부록 A"))
    assert r.unverified_count == 0 and r.citations[0].title == "로그인 정책"


# ── 제목에 대괄호가 들어간다 (2026-08-08) ─────────────────────────────────────
#
# Notion 문서 제목이 `[파티룸] 디제잉 정책` 이다. 옛 추출기는 `[^\]]+?` 로 첫 `]` 에서 끊어서
# `[출처: [파티룸` 까지만 잡았고, **정답을 정확히 인용한 답변이 '출처 없음' 으로 찍혔다.**


def test_a_title_containing_brackets_is_extracted_whole():
    r = validate_citations("Admin 만 가능합니다 [출처: [파티룸] 디제잉 정책, 역할(Role) 권한 테이블]",
                           _pkt("[파티룸] 디제잉 정책"))
    assert r.unverified_count == 0
    assert r.citations[0].title == "[파티룸] 디제잉 정책"
    assert r.citations[0].section == "역할(Role) 권한 테이블"


def test_two_bracketed_citations_in_one_answer_are_both_found():
    r = validate_citations("가 [출처: [파티룸] 디제잉 정책] 나 [출처: 로그인 정책]",
                           _pkt("[파티룸] 디제잉 정책", "로그인 정책"))
    assert len(r.citations) == 2 and r.unverified_count == 0


def test_an_unclosed_citation_is_ignored_rather_than_crashing():
    r = validate_citations("정상 [출처: 로그인 정책] 그리고 깨진 [출처: 로그인 정책",
                           _pkt("로그인 정책"))
    assert len(r.citations) == 1 and r.unverified_count == 0


def test_text_after_a_bracketed_title_still_scans():
    """깊이 세기가 위치를 잘못 잡으면 그 뒤 인용을 통째로 놓친다."""
    r = validate_citations("[출처: [파티룸] 디제잉 정책] 중간 문장 [출처: 플레이리스트 정책] 끝",
                           _pkt("[파티룸] 디제잉 정책", "플레이리스트 정책"))
    assert [c.title for c in r.citations] == ["[파티룸] 디제잉 정책", "플레이리스트 정책"]
