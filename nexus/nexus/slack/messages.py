"""결과 → 사용자/운영자 메시지 — SPEC-nexus-slack-bot §4.3.

순수 함수. 자격증명을 절대 보간하지 않는다(각 메시지는 고정 문자열이다). 봇이 답할 수 없을
때, 그 이유를 **올바른 대상에게** 말한다: 401 은 운영자(봇 토큰이 틀린 것이지 질문이 틀린 게
아니다), 나머지는 사용자에게 정직하게.
"""

from __future__ import annotations

from enum import Enum


class Outcome(str, Enum):
    BAD_TOKEN = "bad_token"            # Nexus 401 — 운영자용
    UNAVAILABLE = "unavailable"        # 503 / 연결 불가
    EMPTY_GROUNDING = "empty_grounding"  # 근거 0건 (코퍼스는 있음)
    EMPTY_CORPUS = "empty_corpus"      # 문서 0건
    OTHER = "other"                    # 429/500/timeout/malformed


_MESSAGES: dict[Outcome, str] = {
    Outcome.BAD_TOKEN: "봇 인증 설정이 잘못되었습니다 — 운영자에게 알리세요.",
    Outcome.UNAVAILABLE: "지금 답변할 수 없습니다. 잠시 후 다시 시도하세요.",
    Outcome.EMPTY_GROUNDING: "인덱싱된 문서에서 답을 찾지 못했습니다.",
    Outcome.EMPTY_CORPUS: "아직 인덱싱된 문서가 없습니다. 먼저 문서를 적재하세요.",
    Outcome.OTHER: "답변 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.",
}


def message_for(outcome: Outcome) -> str:
    """결과에 대응하는 고정 메시지. 자격증명은 여기 들어오지 않는다."""
    return _MESSAGES[outcome]
