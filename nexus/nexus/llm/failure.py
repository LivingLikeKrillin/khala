"""LLM 실패를 **한 번** 분류한다 — 예외가 살아 있는 그 자리에서.

여태 `nexus/llm/answer.py` 는 `except Exception` 으로 전부 잡아 `str(e)` 만 로그에 남기고
버렸다. 그래서 응답에는 `llm_failed: true` 불리언 하나만 남았고, 클라이언트는 **기다리면 되는
실패**와 **사람이 결제해야 하는 실패**를 구별할 수 없었다.

2026-08-13 슬랙 파일럿에서 그 대가를 치렀다: Anthropic 크레딧이 떨어졌는데 사용자에게 나간
문장은 "답변 중 오류가 발생했습니다. 잠시 후 다시 시도하세요." 였다. 기다려도 영원히 안 된다.
반대로 진짜 일시 장애에 "운영자에게 알리세요" 라고 하면 아무 일도 없는데 사람을 부른다.

분류는 **여기서만** 한다. 클라이언트가 공급자 문구를 문자열 매칭하면 안 된다 — 그 문구는
공급자가 바꾸고, 그때 조용히 오분류가 시작된다.
"""

from __future__ import annotations

#: 안정적인 사유 코드. 응답에 실려 나가므로 **값을 바꾸면 계약이 바뀐다.**
QUOTA = "quota"              # 크레딧/청구 소진 — 결제 전까지 영원히 실패
AUTH = "auth"                # 키가 없거나 틀렸다 — 설정 전까지 영원히 실패
RATE_LIMIT = "rate_limit"    # 분당 상한 — 기다리면 된다
UNAVAILABLE = "unavailable"  # 타임아웃·연결 실패·5xx — 기다리면 된다
OTHER = "other"              # 분류되지 않음. **재시도 가능하다고 단정하지 않는다.**

REASONS = (QUOTA, AUTH, RATE_LIMIT, UNAVAILABLE, OTHER)

#: 기다리면 나아지는가. 클라이언트가 이 축을 각자 다시 유도하면 표면마다 답이 갈린다.
_TRANSIENT = frozenset({RATE_LIMIT, UNAVAILABLE})

#: 크레딧 소진만 상태 코드로 못 가른다 — Anthropic 은 그것을 400 `invalid_request_error` 로
#: 준다. 그래서 **400 일 때만** 좁게 본문을 본다. 문구가 바뀌면 `other` 로 떨어지고, 그건
#: 오분류가 아니라 "모른다" 이다 (§`other` 는 재시도 가능으로 치지 않는다).
_QUOTA_MARKERS = ("credit balance", "insufficient_quota", "billing", "quota")


def _status_of(exc: BaseException) -> int | None:
    """예외에서 HTTP 상태를 캔다. anthropic SDK 와 httpx 가 서로 다른 자리에 둔다.

    **SDK 를 import 하지 않는다.** `nexus` 는 anthropic 없이도 도는 배포가 있고(브리지 백엔드),
    분류하려고 선택적 의존을 필수로 만들 수는 없다.
    """
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def classify(exc: BaseException) -> str:
    """예외 → 사유 코드. 모르면 `other` 다 — 모르는 것을 일시 장애라고 부르지 않는다."""
    name = type(exc).__name__
    text = str(exc).lower()
    status = _status_of(exc)

    # 타임아웃·연결 실패는 상태 코드가 없다. 이름으로 본다(httpx·anthropic 둘 다 이 관례다).
    if "timeout" in name.lower() or "connect" in name.lower():
        return UNAVAILABLE

    if status == 401 or status == 403 or "authenticationerror" in name.lower():
        return AUTH
    if status == 429:
        return RATE_LIMIT
    if status == 402:
        return QUOTA
    if status is not None and 500 <= status < 600:
        return UNAVAILABLE
    if status == 400 and any(m in text for m in _QUOTA_MARKERS):
        # 좁게, 400 일 때만. 크레딧 소진은 "요청이 잘못됐다" 로 오는 유일한 청구 사건이다.
        return QUOTA
    return OTHER


def is_transient(reason: str | None) -> bool:
    """기다리면 나아지는 실패인가. 사용자에게 "잠시 후 다시" 라고 말해도 되는 자리."""
    return reason in _TRANSIENT
