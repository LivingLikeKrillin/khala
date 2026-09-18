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
UNAVAILABLE = "unavailable"  # 연결 실패·5xx — **안 받는다.** 기다리면 된다
TIMEOUT = "timeout"          # 504·클라이언트 타임아웃 — **안 끝난다.** 기다리거나 줄인다
OTHER = "other"              # 분류되지 않음. **재시도 가능하다고 단정하지 않는다.**

REASONS = (QUOTA, AUTH, RATE_LIMIT, UNAVAILABLE, TIMEOUT, OTHER)

#: 기다리면 나아지는가. 클라이언트가 이 축을 각자 다시 유도하면 표면마다 답이 갈린다.
_TRANSIENT = frozenset({RATE_LIMIT, UNAVAILABLE, TIMEOUT})

#: 5xx 본문에서 **인증 실패**를 알아보는 표시.
#:
#: ⛔ **왜 본문을 보나 (실측 2026-09-18~19).** dev 브리지는 상류 `claude` 가 실패하면 502 로
#: 싼다. 그 502 하나가 두 사건을 덮는다 — *상류가 못 돈다*(기다리면 낫는다)와 *사람이 다시
#: 로그인해야 한다*(기다려도 **영원히** 안 된다). 상태 코드로는 못 가르고, 사유는 본문에
#: 있었다: `Failed to authenticate: OAuth session expired and could not be refreshed`.
#:
#: 그동안 그 사건은 `unavailable` = 일시 장애로 분류됐다. 이 모듈이 막으려고 만들어진
#: 2026-08-13 사고와 **같은 모양**이다 — 영원히 안 되는 실패에 "잠시 후 다시" 라고 말했다.
#:
#: ⚠ 좁게 본다. 표시가 바뀌면 `unavailable` 로 떨어지고, 그건 오분류가 아니라 "모른다" 쪽이다.
_AUTH_MARKERS = (
    "failed to authenticate", "oauth session expired", "not authenticated",
    "please run /login", "invalid api key",
)

#: 청구·한도 사건만 상태 코드로 못 가른다 — Anthropic 은 그것을 400 `invalid_request_error` 로
#: 준다. 그래서 **400 일 때만** 좁게 본문을 본다. 문구가 바뀌면 `other` 로 떨어지고, 그건
#: 오분류가 아니라 "모른다" 이다 (§`other` 는 재시도 가능으로 치지 않는다).
#:
#: `usage limit` 은 2026-08-13 에 **실제로 맞고 나서** 추가했다. 계정에 설정한 월 사용 한도에
#: 걸린 것이고("You have reached your specified API usage limits. You will regain access on
#: 2026-09-01"), 크레딧 잔액과는 다른 사건이지만 사용자에게는 같다: **사람이 손대기 전까지
#: 영원히 실패한다.** 그때 이 목록은 그것을 못 잡아 `other` 로 떨어뜨렸고, 사용자는
#: "재시도해도 안 됩니다" 대신 일반 오류 문구를 받았을 것이다.
_QUOTA_MARKERS = (
    "credit balance", "insufficient_quota", "billing", "quota",
    "usage limit", "usage limits", "spend limit", "spending limit",
)


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


def _body_of(exc: BaseException) -> str:
    """응답 본문(소문자). 없거나 못 읽으면 빈 문자열.

    ⚠ **분류가 진단 대상을 죽이면 안 된다.** 스트리밍 응답의 `.text` 는 예외를 던질 수 있고,
    그걸 여기서 흘리면 실패를 분류하려다 실패 처리 자체가 터진다.
    """
    response = getattr(exc, "response", None)
    try:
        return (getattr(response, "text", "") or "").lower()
    except Exception:                        # noqa: BLE001
        return ""


def classify(exc: BaseException) -> str:
    """예외 → 사유 코드. 모르면 `other` 다 — 모르는 것을 일시 장애라고 부르지 않는다."""
    name = type(exc).__name__
    text = str(exc).lower()
    status = _status_of(exc)

    # 타임아웃·연결 실패는 상태 코드가 없다. 이름으로 본다(httpx·anthropic 둘 다 이 관례다).
    # ⚠ 둘을 가른다 — 타임아웃은 **줄이면** 되고 연결 실패는 그렇지 않다.
    if "timeout" in name.lower():
        return TIMEOUT
    if "connect" in name.lower():
        return UNAVAILABLE

    if status == 401 or status == 403 or "authenticationerror" in name.lower():
        return AUTH
    if status == 429:
        return RATE_LIMIT
    if status == 402:
        return QUOTA
    if status == 504:
        return TIMEOUT
    if status is not None and 500 <= status < 600:
        # 브리지가 상류의 인증 실패를 5xx 로 싸서 줄 때가 있다. 그때 사유는 **본문에만**
        # 있고, 그것을 일시 장애로 읽으면 사용자는 영원히 재시도한다.
        if any(m in _body_of(exc) for m in _AUTH_MARKERS):
            return AUTH
        return UNAVAILABLE
    if status == 400 and any(m in text for m in _QUOTA_MARKERS):
        # 좁게, 400 일 때만. 크레딧 소진은 "요청이 잘못됐다" 로 오는 유일한 청구 사건이다.
        return QUOTA
    return OTHER


def is_transient(reason: str | None) -> bool:
    """기다리면 나아지는 실패인가. 사용자에게 "잠시 후 다시" 라고 말해도 되는 자리."""
    return reason in _TRANSIENT
