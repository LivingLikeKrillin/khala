"""인용 사후검증 — SPEC-nexus-citation-validation.

LLM 이 뱉은 `[출처: 문서 제목, 섹션]` 인용을, LLM 에게 실제로 보여준 근거 스니펫 제목과 대조한다.
"System decides, LLM narrates": 인용이 실재하는지는 시스템이 판정하고, LLM 은 제안만 한다.

순수 함수(I/O 없음). 존재하지 않는 출처(packet 에 없던 제목)를 잡는다 — 실재하는 제목을 잘못된
주장에 붙인 것(entailment)은 범위 밖.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

_OPEN = "[출처:"


def _inner_citations(text: str) -> list[str]:
    """`[출처: …]` 안쪽 문자열들. **제목에 대괄호가 들어갈 수 있다.**

    옛 정규식은 `[^\\]]+?` 로 첫 `]` 에서 끊었다. 그런데 Notion 문서 제목이
    `[파티룸] 디제잉 정책` 이면 `[출처: [파티룸] 디제잉 정책, 역할 표]` 에서 `[출처: [파티룸`
    까지만 잡히고, **정답을 정확히 인용한 답변이 '출처 없음' 으로 찍힌다.** 2026-08-08 측정에서
    실제로 그랬다.

    그래서 여는 대괄호의 깊이를 세어 **짝이 맞는 자리**에서 닫는다. 안 닫히면 그 인용은 무시한다
    (옛 동작과 같다 — 깨진 인용에 크래시하지 않는다).
    """
    out: list[str] = []
    i = 0
    while (start := text.find(_OPEN, i)) != -1:
        depth, j = 1, start + len(_OPEN)
        while j < len(text) and depth:
            if text[j] == "[":
                depth += 1
            elif text[j] == "]":
                depth -= 1
            j += 1
        if depth:                      # 닫히지 않았다 — 무시하고 다음으로
            break
        out.append(text[start + len(_OPEN):j - 1].strip())
        i = j
    return out


@dataclass(frozen=True)
class Citation:
    title: str
    section: str
    verified: bool
    #: 이 인용이 가리키는 텍스트가 어떻게 존재하게 됐는가 (ADR-0010 hop 4).
    #: 'authored' | 'machine_read' | 'mixed'. 인용이 약속하는 것이 바뀐 지점이다:
    #: 이전엔 "사람이 이걸 썼다", 이제는 "이것이 **어느 종류인지** 밝힌다".
    provenance_tier: str = "authored"


@dataclass(frozen=True)
class CitationReport:
    citations: list[Citation]
    unverified_count: int


#: 활자 문장부호 → ASCII. 문서 제목은 Notion·에디터를 거치며 ‘ ’ “ ” — 를 달고 오는데, LLM 은
#: 그것을 ' ' " " - 로 옮겨 적는다. 접지 않으면 **따옴표 한 글자 때문에 '출처 미검증' 이 뜬다** —
#: 2026-08-08 측정에서 미검증 23건 중 대부분이 이것이었고, 지어낸 출처는 하나도 없었다.
_PUNCT = str.maketrans({
    "‘": "'", "’": "'",        # ‘ ’
    "“": '"', "”": '"',        # “ ”
    "–": "-", "—": "-",        # – —
    " ": " ",                       # nbsp
})


def _norm(s: str) -> str:
    """공백 축약 + trim + 소문자 + 활자 문장부호 접기 — 표면 차이로 인한 오탐 방지."""
    return re.sub(r"\s+", " ", s.translate(_PUNCT).strip()).lower()


def _unique_prefix(cited: str, known: dict[str, str]) -> str | None:
    """제목 뒤를 잘라 인용한 경우. **모호하면 받지 않는다.**

    LLM 은 `Nexus 팀 도그푸딩 배포 런북 (로컬 + Cloudflare Tunnel)` 을 괄호 없이 적는다. 그것은
    지어낸 출처가 아니라 같은 문서의 짧은 이름이다.

    다만 접두라고 다 받으면 `동시성` 하나로 세 문서가 다 맞아 검사가 무너진다. 그래서 **단 하나의
    제목에만** 걸려야 하고, 잘린 자리가 **낱말 경계**여야 한다(`…런북` + `" ("`). 이러면 짧은
    접두는 모호해져 저절로 걸러지고, 지어낸 제목은 애초에 어떤 제목의 접두도 아니다.
    """
    hits = [full for norm, full in known.items()
            if norm != cited and norm.startswith(cited + " ")]
    return hits[0] if len(hits) == 1 else None


#: 제목과 섹션을 가르는 자리. 프롬프트는 `제목, 섹션` 을 지시하지만 모델은 `제목 > 섹션` 도 쓴다 —
#: 근거 헤더가 `[제목] (섹션)` 이라 콤마가 눈앞에 없고, `>` 는 흔한 관례다. 분리자 하나 때문에
#: **실재하는 문서가 미검증으로 세어지면** 그 손해는 검증기가 만든 것이다: Pack A 3런에서 런당
#: 5~8건이 이 모양이었고 지어낸 출처는 한 건도 없었다(2026-08-12). Pack B 문서는 짧아 섹션을
#: 붙일 일이 드물어 드러나지 않았다.
_SECTION_SEP = re.compile(r"\s*[,>]\s*")


def _classify(inner: str, known: dict[str, str]) -> Citation:
    """인용 안쪽 텍스트를 (title, section, verified) 로 분류.

    제목에 콤마나 `>` 가 있을 수 있으므로(Notion 페이지·파일명) 첫 분리자로 순진하게 자르지
    않는다: 전체를 제목으로 먼저 시도하고, 아니면 분할점을 **뒤에서부터**(긴 제목 우선) 훑어
    앞부분이 알려진 제목과 정확히 일치하면 verified + 뒷부분을 섹션으로.
    """
    innorm = _norm(inner)
    if innorm in known:                       # 전체가 제목(섹션 없음, 제목에 분리자 포함 가능)
        return Citation(title=known[innorm], section="", verified=True)

    cuts = list(_SECTION_SEP.finditer(inner))
    for m in reversed(cuts):                  # 긴 제목 우선(제목 안 분리자 흡수)
        title_part, section_part = inner[:m.start()].strip(), inner[m.end():].strip()
        tnorm = _norm(title_part)
        if tnorm in known:
            return Citation(title=known[tnorm], section=section_part, verified=True)
    # 정확 일치가 없을 때만 접두를 본다 — 정확 일치를 접두가 가로채면 안 된다.
    if (full := _unique_prefix(innorm, known)):
        return Citation(title=full, section="", verified=True)
    for m in reversed(cuts):
        if (full := _unique_prefix(_norm(inner[:m.start()].strip()), known)):
            return Citation(title=full, section=inner[m.end():].strip(), verified=True)
    return Citation(title=inner, section="", verified=False)   # packet 에 없는 출처


def _tier_by_title(packet) -> dict[str, str]:
    """제목 → 등급. 한 제목 아래 두 종류가 섞이면 `mixed`.

    인용은 제목(+섹션)으로 해소되는데 한 문서는 저자 chunk 와 기계 chunk 를 함께 가질 수 있다.
    그럴 때 하나를 고르면 거짓이 되므로 섞였다고 말한다 — **읽는 사람이 확인해야 한다**는 것이
    이 등급이 하는 일의 전부이고, 애매함을 감추는 것은 그 일의 반대다.
    """
    seen: dict[str, set[str]] = {}
    for sn in getattr(packet, "snippets", []):
        title = getattr(sn, "doc_title", "")
        if not title:
            continue
        seen.setdefault(title, set()).add(getattr(sn, "provenance_tier", "authored"))
    return {t: (v.pop() if len(v) == 1 else "mixed") for t, v in seen.items()}


def validate_citations(answer_text: str, packet) -> CitationReport:
    """답변의 모든 [출처: …] 를 packet.snippets 제목과 대조. 순수·무예외."""
    known = {_norm(s.doc_title): s.doc_title
             for s in getattr(packet, "snippets", []) if getattr(s, "doc_title", "")}
    tiers = _tier_by_title(packet)
    citations = [
        replace(c, provenance_tier=tiers.get(c.title, "authored"))
        for c in (_classify(inner, known) for inner in _inner_citations(answer_text or ""))
    ]
    unverified = sum(1 for c in citations if not c.verified)
    return CitationReport(citations=citations, unverified_count=unverified)
