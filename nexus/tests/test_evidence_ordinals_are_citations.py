"""우리가 붙여 준 번호(`근거 4`)로 인용하면 그것도 인용이다.

⛔ **실측 2026-09-19, 설명 층 골든셋.** `format_for_llm` 은 스니펫마다
`### 근거 {i} [{제목}] ({섹션})` 을 찍는다 — **번호를 먼저 보여준다.** 그런데 검증기는 제목만
받았다. 빠른 모델(Haiku 4.5)이 그 번호로 인용했고 **57건 중 23건이 미검증**으로 찍혔다.
한 사건은 13건 중 13건이 전부 떨어졌다.

지어낸 출처가 아니라 **우리가 준 이름표**를 쓴 것이다. 번호를 붙여 보여주고 그 번호를
거부하는 것은 모델의 실패가 아니라 우리 쪽 불일치다.

⭐ **느슨해지는 것이 아니라 엄격해지는 것이다.** 제목 대조는 정규화·접두 휴리스틱을 거치지만
번호는 **범위 안 정수** 하나다 — `근거 99` 는 packet 이 13개면 그냥 틀린다.

⚠ 그리고 이것은 설명 층 지표를 **정확하게** 만든다. 지금까지 「인용 검증 통과율」에는
*"제목을 받아들여지는 꼴로 썼나"* 가 섞여 있었다. 그건 *"근거를 지어냈나"* 와 다른 축이다.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from nexus.llm.citations import validate_citations


@dataclass
class _Snippet:
    doc_title: str
    section_path: str = ""
    provenance_tier: str = "authored"


@dataclass
class _Packet:
    snippets: list = field(default_factory=list)


_TITLES = ["picasso — 이기종 로봇 표준 I/F 계약과 운영 변경 체계",
           "SOP-01 파지 실패와 잔여 파지 처리",
           "운영 시나리오 명세서",
           "picasso — 표준 용어 사전 (Glossary)"]
_PACKET = _Packet([_Snippet(t) for t in _TITLES])


def _one(text: str):
    rep = validate_citations(text, _PACKET)
    assert len(rep.citations) == 1, rep.citations
    return rep.citations[0]


# ── 받아야 할 것 ───────────────────────────────────────────────────────────

def test_an_ordinal_resolves_to_that_snippet():
    """⛔ 이 검사가 이 단위의 이유다. 넷째 근거를 가리킨 것이 넷째 문서로 해소돼야 한다."""
    c = _one("[출처: 근거 4]")
    assert c.verified and c.title == _TITLES[3]


def test_an_ordinal_with_a_section_keeps_the_section():
    c = _one("[출처: 근거 1, §15.91]")
    assert c.verified and c.title == _TITLES[0] and c.section == "§15.91"


def test_a_space_after_the_word_is_optional():
    assert _one("[출처: 근거2]").title == _TITLES[1]


def test_the_bare_bracket_form_works_too():
    """접두사 없는 인용도 같은 규칙을 탄다 — 모델이 자주 그렇게 쓴다."""
    rep = validate_citations("결론이다 [근거 3]", _PACKET)
    assert [c.title for c in rep.citations if c.verified] == [_TITLES[2]]


# ── 받으면 안 되는 것 (이빨) ───────────────────────────────────────────────

def test_an_ordinal_past_the_packet_is_not_a_citation():
    """⛔ **이것이 이 기능의 이빨이다.** 없는 근거를 가리킨 것은 지어낸 출처와 같다."""
    c = _one("[출처: 근거 99]")
    assert not c.verified


@pytest.mark.parametrize("bad", ["근거 0", "근거 -1", "근거", "근거 넷", "근거 4개"],
                         ids=["zero", "negative", "no-number", "hangul", "counter"])
def test_things_that_are_not_ordinals(bad):
    assert not _one(f"[출처: {bad}]").verified


def test_a_real_title_wins_over_the_ordinal_reading():
    """⚠ 문서 제목이 진짜로 `근거 4` 이면 그쪽이 이긴다 — 정확 일치를 먼저 본다."""
    packet = _Packet([_Snippet("근거 4"), _Snippet("다른 문서"), _Snippet("셋째"),
                      _Snippet("넷째 문서")])
    rep = validate_citations("[출처: 근거 4]", packet)
    assert rep.citations[0].verified and rep.citations[0].title == "근거 4"


def test_an_empty_packet_accepts_no_ordinal():
    rep = validate_citations("[출처: 근거 1]", _Packet([]))
    assert not rep.citations[0].verified


# ── 있던 것이 안 깨졌는가 ──────────────────────────────────────────────────

def test_a_title_citation_still_works():
    assert _one(f"[출처: {_TITLES[1]}]").verified


def test_a_made_up_title_is_still_unverified():
    """⛔ 이 모듈의 존재 이유가 이것이다 — 번호를 받았다고 지어낸 제목까지 받으면 안 된다."""
    assert not _one("[출처: 존재하지 않는 문서, 3장]").verified


def test_the_numbering_matches_what_the_prompt_shows():
    """⛔ **1부터다.** `format_for_llm` 이 `enumerate(..., 1)` 로 찍는다 — 여기가 0부터면
    모든 인용이 한 칸씩 밀려 **엉뚱한 문서로 해소된다.** 조용히 틀리는 종류다."""
    import pathlib

    from nexus.search import evidence_packet

    src = pathlib.Path(evidence_packet.__file__).read_text(encoding="utf-8")
    assert "enumerate(packet.snippets, 1)" in src
    assert _one("[출처: 근거 1]").title == _TITLES[0]
