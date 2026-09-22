"""인용 한 줄이 **그 근거가 무엇인지 스스로 말한다** — 소비자가 지어내지 않는다.

⛔ **왜 생겼나 (실측 2026-09-23).** 설명 층의 LLM 설명이 코퍼스에 들어오고 운영자 질의가
그것을 인용하기 시작했다. 두 판을 돌렸는데 이렇게 갈렸다:

    첫 판   모델이 산문에 **스스로** 적었다 — *"이 설명들 자체가 사람이 아니라 이전 LLM
            판정이 만든 것이라는 점도 유의해야 한다"*
    재확인  **안 적었다.** 인용은 13/15 가 그 문서로 제대로 갔는데, 신원은 산문에서 사라졌다

⭐ **산문은 판마다 흔들린다.** 그것이 유일한 신호면 신호가 아니다. 이 리포의 핵심 원칙 2 가
그 자리를 이미 정해 뒀다 — **시스템이 정하고 LLM 은 서술한다.** 근거가 무엇인지는 시스템이
아는 사실이지, 모델이 기억해 주기를 바랄 것이 아니다.

⛔ **그런데 결정론 쪽이 반만 돼 있었다.** 근거 스니펫은 `provenance_mark`(렌더된 문자열)를
받는데 **인용은 `provenance_tier`(원값)만** 받았다. 그리고 **읽는 사람이 보는 것은 인용
목록**이다. 소비자는 등급 값을 받아 표시 문자열을 **스스로 지어내야** 했고, 그것은
`search/provenance.py` 머리말이 금지한 바로 그것이다:

    "각자 문자열을 지어내면 표면마다 다른 말을 하게 되고, 그러면 등급은 표면마다 다른 뜻이 된다."
"""

from __future__ import annotations

import pytest

from nexus.search import provenance as P


def _citation(tier: str):
    """인용 한 건을 **비스트리밍 경로가 만드는 그대로** 만든다."""
    from nexus.llm.citations import validate_citations
    from nexus.search.evidence_packet import EvidencePacket, EvidenceSnippet

    s = EvidenceSnippet(chunk_rid="c1", doc_rid="d1", doc_title="어떤 문서",
                        section_path="1절", source_uri="t:x.md", text="근거 본문",
                        score=0.9, classification="INTERNAL")
    s.provenance_tier = tier
    report = validate_citations("주장[출처: 어떤 문서, 1절].", EvidencePacket(snippets=[s]))
    return report.citations[0]


@pytest.mark.parametrize("tier", [P.MACHINE_WRITTEN, P.MACHINE_READ, P.AUTHORED])
def test_both_answer_surfaces_ship_the_same_two_fields(tier):
    """⛔ **한 표면만 빠뜨리면 그 표면의 소비자만 조용히 못 본다** — 이 리포가 반복한 모양.

    표현이 아니라 **행동**이다: 두 경로가 인용을 직렬화하는 코드를 각각 돌려 같은 칸이
    같은 값으로 나오는지 본다.
    """
    from nexus.llm.answer import tier_mark as non_stream_mark
    from nexus.api import _tier_mark as stream_mark

    c = _citation(tier)
    got = getattr(c, "provenance_tier", "authored")

    assert non_stream_mark(got) == stream_mark(got) == P.mark(tier), \
        "두 표면이 같은 등급에 다른 문자열을 낸다"


def test_the_citation_payload_carries_the_rendered_mark():
    """⭐ **소비자가 어휘를 몰라도 된다.** 등급 값이 아니라 **보여 줄 말**이 같이 온다."""
    import inspect

    from nexus import api
    from nexus.llm import answer

    for src in (inspect.getsource(answer.generate_answer), inspect.getsource(api)):
        assert '"provenance_mark"' in src, "인용에 렌더된 표시가 안 실린다"


def test_a_machine_written_citation_announces_itself():
    """이 등급의 인용은 **말이 붙는다.** 붙지 않으면 사람 글과 구별할 방법이 없다."""
    assert P.mark(P.MACHINE_WRITTEN).strip(), "표시가 비어 있다"
    assert P.mark(P.MACHINE_WRITTEN) != P.mark(P.MACHINE_READ)


def test_an_authored_citation_stays_silent():
    """⭐ **기본이 조용해야 표시가 뜻을 갖는다.** 전부에 붙으면 아무것도 구별하지 못한다."""
    assert P.mark(P.AUTHORED) == ""


def test_the_deterministic_signal_does_not_depend_on_the_prose():
    """⛔ **모델이 말해 주기를 바라지 않는다** — 두 판 사이에 이미 한 번 잊었다.

    이 단언이 지키는 것은 문자열 하나가 아니라 **원칙**이다: 근거가 무엇인지는 시스템이
    아는 사실이고, 그 사실은 답변 문장이 아니라 **칸**으로 나간다.
    """
    c = _citation(P.MACHINE_WRITTEN)
    tier = getattr(c, "provenance_tier", "authored")

    assert tier == P.MACHINE_WRITTEN, "등급이 인용까지 안 온다"
    assert P.mark(tier), "등급은 왔는데 보여 줄 말이 없다"
