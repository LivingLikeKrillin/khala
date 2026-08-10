"""등급이 여섯 hop 을 통과하는가 — ADR-0010 §4.

ADR-0010 이 이 목록을 conformance 조건으로 못박은 이유는, 어느 한 곳에서 벗겨지면 읽는 사람이
저자 텍스트와 기계가 읽은 텍스트를 **구별할 수 없기** 때문이다. 그 상태는 추출을 안 하느니만
못하다: 알려진 공백이 표시 없는 주장으로 바뀐다.

    1 chunking/저장 · 2 SearchHit · 3 evidence packet(→프롬프트) · 4 인용 ·
    5 API 응답 · 6 MCP tool 결과

hop 당 단언 하나. 초안이 hop 을 다섯 개로 세면서 MCP 를 A2A 와 함께 떨어뜨렸고 — 비평이
잡았다 — 그런 식으로 hop 은 조용히 사라진다.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.ingest import vision  # noqa: E402
from nexus.ingest.chunker import chunk_document  # noqa: E402
from nexus.llm.citations import validate_citations  # noqa: E402
from nexus.search.evidence_packet import assemble_packet, format_for_llm  # noqa: E402
from nexus.search.hybrid import SearchHit  # noqa: E402


def _machine_hit(title="정책 A", text="| 아바타 | 해금 |\n|---|---|\n| A | 1200 |"):
    return SearchHit(rid="c1", doc_rid="d1", doc_title=title, section_path="해금",
                     source_uri="u1", snippet=text[:50], chunk_text=text,
                     score=0.9, classification="INTERNAL",
                     provenance_tier="machine_read")


def _authored_hit(title="정책 B", text="담당자에게 문의한다."):
    return SearchHit(rid="c2", doc_rid="d2", doc_title=title, section_path="문의",
                     source_uri="u2", snippet=text, chunk_text=text,
                     score=0.5, classification="INTERNAL")


# ── hop 1: 청킹과 저장 ────────────────────────────────────────────────────────

def test_hop1_chunking_assigns_the_tier():
    e = vision.Extraction("표 내용 1200", "m/abc12345", "s" * 64)
    doc = "# 정책\n\n앞 문단\n\n" + vision.build_block(e) + "\n\n뒤 문단\n"
    # 컨버터가 쓴 본문이므로 마커를 신뢰한다. 기본값은 **불신**이다 — 파일시스템 문서나 외부
    # spec 이 마커를 담고 있어도 저자 산문이 machine_read 로 찍히면 안 되기 때문이다.
    chunks = chunk_document(doc, language="ko", trust_vision_markers=True)
    tiers = {c.provenance_tier for c in chunks}
    assert tiers == {"authored", "machine_read"}


def test_hop1_the_insert_carries_the_tier():
    """저장 SQL 이 컬럼을 안 쓰면 나머지 다섯 hop 은 전부 기본값 authored 를 나른다 —
    벗겨진 것이 아니라 **애초에 실린 적이 없는** 상태이고, 증상은 똑같다."""
    src = (ROOT / "nexus" / "ingest" / "pipeline.py").read_text(encoding="utf-8")
    assert "provenance_tier" in src, "적재가 등급을 저장하지 않는다"
    assert "provenance_tier = EXCLUDED.provenance_tier" in src, (
        "재적재 시 등급이 텍스트를 따라가지 않는다 — 저자 텍스트가 들어온 자리에 옛 등급이 남으면 "
        "그 chunk 는 자기 내용에 대해 거짓말을 한다")


# ── hop 2: SearchHit ──────────────────────────────────────────────────────────

def test_hop2_search_hit_carries_the_tier():
    assert _machine_hit().provenance_tier == "machine_read"
    assert _authored_hit().provenance_tier == "authored"


def test_hop2_the_enrich_query_selects_the_column():
    src = (ROOT / "nexus" / "search" / "hybrid.py").read_text(encoding="utf-8")
    assert "c.provenance_tier" in src, "검색이 등급 컬럼을 읽지 않는다"


# ── hop 3: evidence packet → 프롬프트 ─────────────────────────────────────────

def test_hop3_the_packet_carries_the_tier():
    packet = assemble_packet([_machine_hit(), _authored_hit()], None)
    tiers = {s.doc_title: s.provenance_tier for s in packet.snippets}
    assert tiers["정책 A"] == "machine_read" and tiers["정책 B"] == "authored"


def test_hop3_the_prompt_says_which_kind_it_is():
    """답을 쓰는 모델이 구별할 수 있어야 한다. 여기서 빠지면 인용이 그 구별을 약속할 수 없다."""
    prompt = format_for_llm(assemble_packet([_machine_hit(), _authored_hit()], None))
    assert "그림에서 기계가 읽은 텍스트" in prompt


def test_hop3_authored_evidence_is_not_marked():
    """기본이 조용해야 표시가 뜻을 갖는다 — 전부에 붙으면 아무것도 구별하지 못한다."""
    prompt = format_for_llm(assemble_packet([_authored_hit()], None))
    assert "그림에서 기계가 읽은 텍스트" not in prompt


# ── hop 4: 인용 ───────────────────────────────────────────────────────────────

def test_hop4_a_citation_to_machine_read_text_says_so():
    packet = assemble_packet([_machine_hit(), _authored_hit()], None)
    report = validate_citations("답변입니다 [출처: 정책 A]", packet)
    (c,) = report.citations
    assert c.verified and c.provenance_tier == "machine_read"


def test_hop4_a_citation_to_authored_text_stays_authored():
    packet = assemble_packet([_machine_hit(), _authored_hit()], None)
    report = validate_citations("답변입니다 [출처: 정책 B]", packet)
    (c,) = report.citations
    assert c.provenance_tier == "authored"


def test_hop4_a_title_carrying_both_kinds_is_mixed():
    """한 문서가 저자 chunk 와 기계 chunk 를 함께 가질 수 있다. 하나를 고르면 거짓이 되므로
    섞였다고 말한다 — 애매함을 감추는 것은 이 등급이 하는 일의 반대다."""
    a = _machine_hit(title="정책 C")
    b = _authored_hit(title="정책 C")
    report = validate_citations("답변 [출처: 정책 C]", assemble_packet([a, b], None))
    (c,) = report.citations
    assert c.provenance_tier == "mixed"


# ── hop 5: API 응답 ───────────────────────────────────────────────────────────

def test_hop5_the_search_response_carries_the_tier():
    from nexus.api import _search_hit_to_dict
    assert _search_hit_to_dict(_machine_hit())["provenance_tier"] == "machine_read"
    assert _search_hit_to_dict(_authored_hit())["provenance_tier"] == "authored"


def test_hop5_the_answer_response_carries_it_on_snippets_and_citations():
    src = (ROOT / "nexus" / "llm" / "answer.py").read_text(encoding="utf-8")
    assert src.count("provenance_tier") >= 2, (
        "답변 응답이 스니펫과 인용 양쪽에 등급을 싣지 않는다")


# ── hop 6: MCP ────────────────────────────────────────────────────────────────

def test_hop6_mcp_marks_machine_read_results():
    """에이전트 표면. 초안은 이 hop 을 A2A 와 함께 떨어뜨렸다 — A2A 만 빠지는 것이 맞고
    (ADR-0004: 소비자가 당길 때까지 확장하지 않는다) MCP 는 오늘 살아 있는 표면이다.

    표시 함수는 `nexus.search.provenance` 에 있다. `nexus/mcp/server.py` 는 설치된 mcp
    패키지 버전에 따라 import 가 실패할 수 있고, 표시 함수를 그 안에 두면 이 hop 을 **테스트할
    수 없다** — 이 리포에서 못 도는 테스트는 없는 테스트다.
    """
    from nexus.search.provenance import mark
    assert mark("machine_read") == " [그림에서 기계가 읽음]"
    assert mark("mixed") == " [그림에서 기계가 읽음]", "섞였으면 확인이 필요하다는 뜻이다"
    assert mark("authored") == "" and mark(None) == ""


def test_hop6_both_mcp_tools_use_the_shared_mark():
    """`nexus_search` 와 `nexus_answer` 둘 다 표시를 붙이는가.

    소스를 읽는다 — mcp 패키지가 이 환경에서 import 되지 않아 함수를 직접 못 부른다. 그래서
    이 테스트가 확인할 수 있는 것은 **두 호출부가 존재하고 문장을 지역에서 지어내지 않는다**는
    것까지이고, 그 한계를 여기 적어 둔다. 실제 출력은 hop 6 의 `mark()` 테스트가 잡는다.
    """
    src = (ROOT / "nexus" / "mcp" / "server.py").read_text(encoding="utf-8")
    assert src.count("_tier_mark(") == 2, "MCP 도구 중 하나가 등급을 안 나른다"
    assert "from nexus.search.provenance import" in src, (
        "표시 문장을 지역에서 지어내면 표면마다 등급이 다른 뜻이 된다")
    assert "그림에서 기계가 읽음" not in src, "문장이 공용 어휘에서 갈라졌다"


# ── 통합: 여섯 hop 을 한 줄로 ─────────────────────────────────────────────────

def test_the_tier_survives_from_chunk_to_citation():
    """hop 1→4 를 실제 값으로 통과시킨다. 파일 grep 이 아니라 값이 흐르는지를 본다."""
    e = vision.Extraction("| 아바타 | 해금 |\n|---|---|\n| A | 1200 |", "m/abc12345", "s" * 64)
    doc = "# 정책 A\n\n앞 문단\n\n" + vision.build_block(e) + "\n"
    # 컨버터가 쓴 본문이므로 마커를 신뢰한다. 기본값은 **불신**이다 — 파일시스템 문서나 외부
    # spec 이 마커를 담고 있어도 저자 산문이 machine_read 로 찍히면 안 되기 때문이다.
    chunks = chunk_document(doc, language="ko", trust_vision_markers=True)
    machine = [c for c in chunks if c.provenance_tier == "machine_read"]
    assert machine, "hop 1 에서 이미 끊겼다"

    hit = SearchHit(rid="c1", doc_rid="d1", doc_title="정책 A", section_path="해금",
                    source_uri="u", snippet=machine[0].chunk_text[:50],
                    chunk_text=machine[0].chunk_text, score=0.9,
                    classification="INTERNAL",
                    provenance_tier=machine[0].provenance_tier)
    packet = assemble_packet([hit], None)
    assert packet.snippets[0].provenance_tier == "machine_read"          # hop 3
    assert "그림에서 기계가 읽은 텍스트" in format_for_llm(packet)        # hop 3
    (c,) = validate_citations("답변 [출처: 정책 A]", packet).citations
    assert c.provenance_tier == "machine_read"                            # hop 4
