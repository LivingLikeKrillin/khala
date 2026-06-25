"""LLM 인용 가독성: LLM 에 읽는 제목을 인용 핸들로 제시(파일 UUID 미끼 제거).

라이브 narration 실증에서 LLM 이 `[출처: ext-notion-<uuid>.md]` 로 인용함을 관찰 —
format_for_llm 이 per-snippet 에 `출처: {source_uri}`(UUID)를 제시해 LLM 이 그걸 베낌.
읽는 제목(doc_title)을 인용 핸들로 올리고, source_uri 는 추적용 출처 목록에만 둔다.
"""

from __future__ import annotations

from nexus.search.evidence_packet import assemble_packet, format_for_llm
from nexus.search.hybrid import SearchHit


def _hit():
    return SearchHit(
        rid="chunk_1", doc_rid="doc_1", doc_title="1. 동시성 문제의 본질",
        section_path="개요", source_uri="default:ext-notion-abc.md",
        snippet="본문", score=0.9, classification="INTERNAL", doc_type="NOTE",
    )


def test_evidence_presents_readable_title():
    out = format_for_llm(assemble_packet([_hit()]))
    assert "1. 동시성 문제의 본질" in out


def test_no_per_snippet_uri_citation_lure():
    # per-snippet 에서 source_uri 를 '출처:' 핸들로 제시하지 않는다(LLM UUID 인용 방지).
    out = format_for_llm(assemble_packet([_hit()]))
    assert "출처: default:ext-notion-abc.md" not in out


def test_source_uri_retained_for_traceability():
    # UUID 는 추적용으로 출처 목록에는 남는다(완전 삭제 아님).
    out = format_for_llm(assemble_packet([_hit()]))
    assert "default:ext-notion-abc.md" in out


def test_provenance_carries_title():
    packet = assemble_packet([_hit()])
    assert packet.provenance[0].doc_title == "1. 동시성 문제의 본질"


def test_provenance_list_is_title_led():
    out = format_for_llm(assemble_packet([_hit()]))
    assert "- 1. 동시성 문제의 본질" in out
