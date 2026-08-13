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
    EMPTY_GROUNDING = "empty_grounding"  # 근거 0건 (볼 수 있는 문서는 있음)
    EMPTY_CORPUS = "empty_corpus"      # 문서 0건
    #: 코퍼스는 있는데 이 등급으로 **보이는 문서가 0건** — 검색 실패가 아니라 설정 결함이다.
    #: 이것이 EMPTY_GROUNDING 에 섞여 있던 동안, 봇은 "문서에서 못 찾았다" 고 답했다. 뒤진
    #: 문서가 하나도 없었으므로 그 문장은 거짓이었고, 팀은 그것을 코퍼스의 한계로 읽었을 것이다.
    NO_VISIBLE_DOCS = "no_visible_docs"
    #: LLM 생성 실패. 답변 자리에 근거 덤프가 들어오므로 **그대로 올리면 실패가 답변이 된다.**
    #: 사유를 모르거나 분류되지 않은 경우가 여기다.
    GENERATION_FAILED = "generation_failed"
    #: 크레딧/청구 소진. **기다려도 영원히 안 된다** — 사람이 결제해야 한다.
    LLM_QUOTA = "llm_quota"
    #: LLM 키가 없거나 틀렸다. 역시 기다려서 낫지 않는다.
    LLM_AUTH = "llm_auth"
    #: 레이트리밋·일시 장애. **이것만 "잠시 후 다시" 가 참이다.**
    LLM_BUSY = "llm_busy"
    OTHER = "other"                    # 429/500/timeout/malformed


_MESSAGES: dict[Outcome, str] = {
    Outcome.BAD_TOKEN: "봇 인증 설정이 잘못되었습니다 — 운영자에게 알리세요.",
    Outcome.UNAVAILABLE: "지금 답변할 수 없습니다. 잠시 후 다시 시도하세요.",
    Outcome.EMPTY_GROUNDING: "인덱싱된 문서에서 답을 찾지 못했습니다.",
    Outcome.EMPTY_CORPUS: "아직 인덱싱된 문서가 없습니다. 먼저 문서를 적재하세요.",
    # 사용자에게 "없다" 고 말하지 않는다 — 없는 게 아니라 **안 보이는** 것이고, 그 차이를
    # 고칠 수 있는 사람은 운영자다.
    Outcome.NO_VISIBLE_DOCS: (
        "이 봇의 열람 등급으로 볼 수 있는 문서가 없습니다 — 운영자에게 알리세요. "
        "(문서가 없는 것이 아니라 접근 설정 문제입니다.)"
    ),
    Outcome.GENERATION_FAILED: (
        "근거는 찾았지만 답변 생성에 실패했습니다 — 운영자에게 알리세요."
    ),
    # 왜 문장을 갈라 놓는가: 2026-08-13 파일럿에서 크레딧이 소진됐는데 사용자가 본 문장은
    # "잠시 후 다시 시도하세요" 였다. 기다려도 영원히 안 된다. 반대로 진짜 일시 장애에
    # "운영자에게 알리세요" 라고 하면 아무 일도 없는데 사람을 부른다.
    # **두 원인을 함께 말한다.** 2026-08-13 에 실제로 온 것은 크레딧 소진이 아니라 계정에
    # 설정된 **사용 한도**였는데, 문구가 "크레딧 소진" 이면 운영자가 한도를 올려야 할 상황에
    # 결제를 하러 간다. 사용자에게 필요한 것은 원인 구분이 아니라 **누가 무엇을 해야 하는가**다.
    Outcome.LLM_QUOTA: (
        "답변 생성 한도에 도달했습니다(크레딧 소진 또는 사용 한도) — 운영자에게 알리세요. "
        "(재시도해도 해결되지 않습니다. 근거는 검색되었습니다.)"
    ),
    Outcome.LLM_AUTH: (
        "답변 생성 키 설정이 잘못되었습니다 — 운영자에게 알리세요. "
        "(재시도해도 해결되지 않습니다.)"
    ),
    Outcome.LLM_BUSY: "답변 생성이 일시적으로 밀렸습니다. 잠시 후 다시 시도하세요.",
    Outcome.OTHER: "답변 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.",
}


def message_for(outcome: Outcome) -> str:
    """결과에 대응하는 고정 메시지. 자격증명은 여기 들어오지 않는다."""
    return _MESSAGES[outcome]
