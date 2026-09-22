"""근거 본문 안의 인용 표기는 **내용으로** 간다 — 베낄 수 있는 문법으로 가지 않는다.

⛔ **왜 생겼나 (실측 2026-09-23).** 설명 층의 LLM 설명이 코퍼스에 들어오면서, 그 본문에
`[출처: 인터페이스 계약 명세서 …]` 가 **글자로** 들어 있게 됐다 — 그 층의 지난 답이 남긴
것이다. 새 답이 그것을 **제 인용으로 옮겨 적었고**, 그 사람 문서는 이번 꾸러미에 **없었다.**

⇒ 지난 답의 인용이 새 답의 인용으로 승격된다. **한 세대에 한 번씩 근거 없이 신뢰가 오른다.**

등급 주석에 *"이 문서 안에 적힌 인용은 이 문서의 내용이지 네 근거가 아니다"* 를 넣어 막았다.
**넷 중 하나에서 다시 났다.** 프롬프트만이 지키는 약속은 규칙이 아니라 확률이다.

⭐ **그리고 이 자리는 애초에 우리가 만든 것이다.** 우리가 **인용 문법 그대로인 문자열**을
모델에게 먹이고, 같은 문법으로 인용을 쓰라고 시킨다. 베끼는 것이 이상한 일이 아니다.
⇒ 주석이 *"이것은 내용이다"* 라고 **말하는** 대신, 꾸러미가 그것을 **내용으로 보여 준다.**

⚠ **왜 안전한가.** 실측: 인용 문법이 든 조각은 `machine_written` **12개뿐**이고, 사람이 쓴
8,622개와 기계가 읽은 203개에는 **0건**이다. 다른 근거의 프롬프트는 한 글자도 안 바뀐다.
"""

from __future__ import annotations

from nexus.llm.citations import QUOTED_PREFIX, as_quoted_content, validate_citations
from nexus.search.evidence_packet import EvidencePacket, EvidenceSnippet, format_for_llm


def _snip(text: str, tier: str = "machine_written"):
    s = EvidenceSnippet(chunk_rid="c1", doc_rid="d1", doc_title="narrator 설명 · hum-02",
                        section_path="운영자 카드", source_uri="narrator:x.md",
                        text=text, score=0.9, classification="INTERNAL")
    s.provenance_tier = tier
    s.full_text = text
    return s


# ── 문법을 벗기되 사실은 남긴다 ───────────────────────────────────────────────

def test_the_syntax_is_stripped_but_the_fact_is_kept():
    """⚠ **지우지 않는다.** 그 설명이 무엇을 근거로 댔는지는 **그 문서의 내용**이다."""
    out = as_quoted_content("관측 불가는 통과가 아니다[출처: 계약 명세서, 3. 담보 사항].")

    assert "[출처:" not in out, "베낄 수 있는 문법이 그대로 남았다"
    assert "계약 명세서" in out and "3. 담보 사항" in out, "그 문서가 댄 근거가 사라졌다"
    assert QUOTED_PREFIX in out


def test_a_bracketed_title_survives():
    """⛔ **정규식으로 첫 `]` 에서 끊으면 안 된다** — 제목에 대괄호가 들어갈 수 있다.

    앞선 판이 그 함정에 걸려 **정답을 정확히 인용한 답변이 '출처 없음' 으로 찍혔다**
    (2026-08-08). 같은 깊이 세기를 쓴다.
    """
    out = as_quoted_content("앞[출처: [파티룸] 디제잉 정책, 역할 표]뒤")

    assert "[파티룸] 디제잉 정책" in out
    assert "역할 표" in out
    assert out.startswith("앞") and out.endswith("뒤")
    assert "[출처:" not in out


def test_text_without_the_syntax_is_untouched():
    """⭐ **대조군** — 8,825 조각이 여기 해당한다. 한 글자도 안 바뀌어야 한다."""
    for text in ("평범한 본문", "대괄호 [있지만] 인용은 아니다", ""):
        assert as_quoted_content(text) == text


def test_a_broken_citation_does_not_crash():
    """⚠ 안 닫힌 대괄호는 그대로 둔다 — 깨진 인용에 프롬프트 조립이 죽으면 안 된다."""
    text = "앞[출처: 안 닫힘"
    assert as_quoted_content(text) == text


# ── 꾸러미가 실제로 그렇게 내보내는가 ────────────────────────────────────────

def test_the_packet_does_not_carry_copyable_citation_syntax():
    """⛔ **이것이 이 파일의 핵심이다.** 프롬프트에 그 문법이 있으면 모델은 베낄 수 있다."""
    text = "금지: 관측 불가는 통과가 아니다[출처: 인터페이스 계약 명세서, 3. 담보 사항]."
    prompt = format_for_llm(EvidencePacket(snippets=[_snip(text)]))

    assert "[출처:" not in prompt, "꾸러미가 베낄 수 있는 인용 문법을 싣는다"
    assert "인터페이스 계약 명세서" in prompt, "그 문서가 댄 근거가 사라졌다"


def test_a_laundered_citation_can_no_longer_be_copied_verbatim():
    """⭐ **세탁의 재료가 없어진다.**

    모델이 그래도 그 제목으로 인용하면 검증기가 잡는다(꾸러미에 없는 문서다). 이 고침은
    **베낄 문자열 자체를 안 주는** 쪽이고, 검증기는 그 뒤의 그물이다.
    """
    text = "…[출처: 꾸러미에 없는 문서, 5. 절차]…"
    prompt = format_for_llm(EvidencePacket(snippets=[_snip(text)]))

    # 프롬프트에서 그대로 오려 붙일 수 있는 인용이 없다.
    assert "[출처: 꾸러미에 없는 문서, 5. 절차]" not in prompt

    # 그리고 그래도 썼다면 — 검증기가 미검증으로 표시한다(둘째 그물).
    report = validate_citations("주장[출처: 꾸러미에 없는 문서, 5. 절차].",
                                EvidencePacket(snippets=[_snip("본문", "authored")]))
    assert report.unverified_count == 1


def test_the_answers_own_citations_are_still_validated_normally():
    """⛔ **이 고침이 인용 검증을 건드리면 안 된다.** 벗기는 것은 **근거 본문**뿐이다."""
    packet = EvidencePacket(snippets=[_snip("평범한 본문", "authored")])
    packet.snippets[0].doc_title = "있는 문서"
    packet.snippets[0].section_path = "1절"

    report = validate_citations("주장[출처: 있는 문서, 1절].", packet)

    assert report.unverified_count == 0
    assert report.citations[0].verified is True
