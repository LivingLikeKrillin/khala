"""질문 → claim 고르기. **결정론이다 — LLM 은 여기 없다.**

⛔ **왜 이 모듈이 있나 (2026-08-30).** `find_by_concept` 은 개념 문자열 **하나**를 정확히
받는다. 사람이 슬랙에 던지는 문장에는 그런 것이 없다. 그래서 값 조회는 전용 CLI 로만 닿았고,
실제 질문에는 **한 번도** 코드 값이 붙지 않았다.

**규칙: claim 의 개념이 전부 질문에 나와야 붙는다.** 하나만 겹쳐도 붙이면 `이름` 하나로
파티 이름·플레이리스트 이름·닉네임 claim 이 전부 딸려 온다. 좁게 잡는 쪽을 고른 이유는,
안 붙는 것은 오늘과 같지만 **잘못 붙는 것은 답을 틀리게** 만들기 때문이다.

⚠ 이 규칙은 표기 변형을 모른다(`파티룸` 질문에 `파티` 개념은 붙지만 그 반대는 아니다).
넓히려면 형태소 분석을 태워야 하는데, 그것은 검색 경로의 도구이고 여기 값은 정확해야 한다.
넓히기 전에 **안 붙은 질문을 세어 보고** 정한다.
"""

from __future__ import annotations


def claims_for_question(question: str, claims: list) -> list:
    """개념이 **전부** 질문에 나오는 claim 만."""
    q = (question or "").lower()
    if not q:
        return []
    out = []
    for c in claims:
        concepts = [str(x).lower() for x in (c.concepts or []) if str(x).strip()]
        if concepts and all(x in q for x in concepts):
            out.append(c)
    return out
