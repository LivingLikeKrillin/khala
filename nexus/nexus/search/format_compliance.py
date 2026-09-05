"""형식 요청을 지켰는가 — **기계가 판정한다** (SPEC-nexus-multi-turn-narration §5.2).

사용자가 "세 줄로" 라고 하면 답이 세 줄이어야 한다. 그것을 측정하는 채점기다.

**LLM 판정자를 쓰지 않는다.** 판정자가 흔들리면 채점기가 흔들리고, 그러면 개선인지 잡음인지 못
가른다. 여기 규칙은 전부 문자열 연산이고, 각 규칙에는 **왜 더 순진한 규칙을 안 썼는지**가
붙어 있다 — 그 반례들이 이 파일의 실제 내용이다.
"""

from __future__ import annotations

import re

#: 문장 끝. 한국어는 마침표를 자주 생략하므로 개행도 경계로 친다.
_SENTENCE_END = re.compile(r"[.!?。]+\s|\n+")

#: 인용 마크업. **문장이 아니다.** 시스템 프롬프트가 주장마다 인용을 강제하므로, 이것을
#: 문장으로 세면 "세 문장으로" 는 구조적으로 도달 불가능해진다 — 채점기가 시스템의 다른 규칙과
#: 싸우게 된다. 2026-08-14 에 실제로 그랬다(세 문장 답변이 6~9 로 세어짐).
_CITATION = re.compile(r"\[출처:[^\]]*\]")

#: 목록 번호만으로 이루어진 조각. `1.` 의 마침표는 문장 끝이 아니라 번호의 일부다.
_BARE_NUMBER = re.compile(r"^\d+[.)]?$")

#: 마크다운 표의 구분선. `|---|---|` 또는 `| :-- | --: |`
_TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?\s*$", re.M)

#: 목록 항목의 머리. 번호·불릿 둘 다.
_LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$", re.M)


def sentence_count(text: str) -> int:
    """문장 수.

    **"줄 수" 를 쓰지 않는 이유**: 개행 없는 장문 한 줄이 통과한다 — §1.1 이 문제 삼은 실패가
    정확히 그 모양(1304자짜리 답변)이므로, 줄로 세면 채점기가 그 실패를 통과시킨다.

    **인용과 목록 번호는 문장이 아니다** (2026-08-14 실측으로 추가). 세는 것은 산문이다:
    `1. 파드는 거부됩니다. [출처: 문서, 절]` 은 한 문장이고, 이걸 셋으로 세면 채점기가
    "요청을 지킨 답" 을 실패로 찍는다. 실제로 세 문장짜리 답변이 9 로 세어졌다.

    완화는 위험한 방향이 정해져 있다 — 너무 많이 지우면 문장 수가 줄어 **긴 답이 통과한다.**
    그래서 지우는 것은 `[출처: …]` 하나뿐이고, 번호는 지우지 않고 **번호만으로 이루어진
    조각을 세지 않는** 방식이다(본문의 `3.5` 는 마침표 뒤에 공백이 없어 애초에 안 갈린다).
    """
    cleaned = _CITATION.sub(" ", text or "")
    parts = [p.strip() for p in _SENTENCE_END.split(cleaned) if p and p.strip()]
    return sum(1 for p in parts if not _BARE_NUMBER.match(p))


def has_table(text: str) -> bool:
    """마크다운 표가 **실제로** 있는가.

    "`|` 가 있다" 로는 안 된다 — 본문의 파이프 문자 하나가 통과한다. 헤더 아래 **구분선**이
    있어야 렌더러가 표로 그린다. 그것이 표의 최소 조건이다.
    """
    return bool(_TABLE_SEP.search(text or ""))


def list_items(text: str) -> list[str]:
    """목록 항목 본문들. 번호·불릿 둘 다 센다."""
    return [m.group(1).strip() for m in _LIST_ITEM.finditer(text or "")]


def shorter_than(text: str, reference: str) -> bool:
    """"짧게" 는 **상대적**이다. 절대 길이 문턱은 질문마다 뜻이 달라진다."""
    return len(text or "") < len(reference or "")


#: 유형 → (판정 함수). 각 함수는 (답변, 1턴 답변) → bool.
CHECKS = {
    # "세 줄로" — 문장 셋 이하. 셋을 **넘지 않는** 것이 요구이고, 둘이면 통과다.
    "three_sentences": lambda answer, prior: sentence_count(answer) <= 3,
    "table": lambda answer, prior: has_table(answer),
    "shorter": lambda answer, prior: shorter_than(answer, prior),
}


def check(kind: str, answer: str, prior: str = "") -> bool:
    """이 답변이 그 형식 요청을 지켰는가. 모르는 유형은 예외 — 조용히 통과시키지 않는다."""
    if kind not in CHECKS:
        raise KeyError(f"알 수 없는 형식 유형: {kind!r} (아는 것: {', '.join(CHECKS)})")
    return CHECKS[kind](answer, prior)


#: 라이브에 남기는 모양의 키. `None` 으로 채울 때도 **키는 그대로 있어야** 다음 사람이
#: "안 쟀다" 와 "유실됐다" 를 가른다.
SHAPE_KEYS = ("n_sentences", "has_table", "n_list_items", "n_chars")


def shape(answer: str | None) -> dict:
    """이 답변의 **모양**. 요청이 무엇이었는지는 보지 않는다 (감사 B2).

    ⛔ **왜 준수가 아니라 모양인가.** 위 `check` 는 (요청 유형, 답변) 둘을 받는다. 평가에서는
    라벨이 유형을 주지만 **라이브에는 그것을 아는 것이 없다** — 질의에서 형식 요청을 알아내는
    부품은 이 리포에 없다. 그것을 지금 지어내면 오탐이 새 실패 유형으로 들어오고, 그건
    측정 없이 옳은 변경이 아니라 사전 등록이 필요한 기법 추가다.

    그래서 여기서는 **판정하지 않고 남긴다.** 답변의 모양은 요청과 무관하게 결정론이고,
    남겨 두면 나중에 요청을 알게 됐을 때(실제 질의 채굴) 과거까지 되짚을 수 있다.
    안 남기면 그때 가서도 없다.

    ⚠ **답변이 아닌 문자열에는 부르지 마라.** 기권 안내문·생성 실패 안내문의 모양을 세면
    그것은 측정이 아니라 상수를 센 것이다. 호출부가 그 조건을 판정하고, 아닐 때는 같은
    키를 `None` 으로 남긴다.
    """
    text = answer or ""
    return {"n_sentences": sentence_count(text),
            "has_table": has_table(text),
            "n_list_items": len(list_items(text)),
            "n_chars": len(text)}


def shape_unmeasured() -> dict:
    """모양을 잴 수 없을 때의 같은 키. **키를 빼지 않는다** — 위 docstring 의 그 이유다."""
    return dict.fromkeys(SHAPE_KEYS)


def shape_if_measured(answer: str | None, *, measured: bool) -> dict:
    """모양을 재거나, 같은 키를 비워 둔다. **호출부는 이것만 쓴다.**

    분기를 호출부마다 따로 쓰면 한 표면만 고쳐지고 나머지가 조용히 다른 규칙을 쓴다 —
    이 리포에서 답변 표면 셋이 정확히 그렇게 갈렸던 적이 있다(`packet_for_answer` 머리말).
    조건 자체는 표면마다 다르므로 호출부에 남고, **갈래는 여기 하나**다.
    """
    return shape(answer) if measured else shape_unmeasured()
