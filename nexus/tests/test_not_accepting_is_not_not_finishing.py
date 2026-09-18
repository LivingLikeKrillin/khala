"""「안 받는다」와 「안 끝난다」가 같은 사유 코드였다.

⛔ **실측 2026-09-18~19, 이틀에 걸쳐 두 고장.**

  1일차 — 502. 호스트 `claude` 의 OAuth 세션이 만료됐다. **사람이 다시 로그인하기 전에는
          영원히 실패한다.** 그런데 분류는 `unavailable` = 「기다리면 된다」였다.
  2일차 — 504. 합성이 120초 벽에 걸렸다. **기다리거나 질의를 줄이면 된다.** 분류는
          똑같이 `unavailable` 이었다.

설명 층 입장에서 두 사건은 **다음 행동이 다른데** 같은 값으로 왔다. 그쪽이 그것을 지적했다:
*"내 층에서는 「안 받는다」와 「안 끝난다」가 구별되지 않는다."*

⛔ 1일차가 특히 나쁘다 — 이 모듈이 만들어진 이유가 **정확히 그 모양**이기 때문이다.
2026-08-13 에 크레딧이 떨어졌는데 사용자에게 나간 문장이 "잠시 후 다시 시도하세요" 였다.
기다려도 영원히 안 되는 실패를 일시 장애로 부른 것이고, 어제 그것이 OAuth 로 다시 났다.
"""

from __future__ import annotations

import httpx
import pytest

from nexus.llm import failure as F

_OAUTH = "Failed to authenticate: OAuth session expired and could not be refreshed"


def _http(status: int, body: str = "") -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "http://host.docker.internal:8900/v1/generate")
    resp = httpx.Response(status, request=req, text=body)
    return httpx.HTTPStatusError(f"{status}", request=req, response=resp)


# ── 안 끝난다 ──────────────────────────────────────────────────────────────

def test_a_gateway_timeout_is_its_own_reason():
    """⛔ 이 검사가 이 단위의 절반이다. 504 는 벽에 걸린 것이고 처방이 따로 있다."""
    assert F.classify(_http(504)) == F.TIMEOUT


def test_waiting_helps_for_a_timeout():
    assert F.is_transient(F.TIMEOUT) is True


# ── 안 받는다 ──────────────────────────────────────────────────────────────

def test_a_plain_bad_gateway_is_still_unavailable():
    """⚠ 좁게 본다 — 표시가 없으면 예전 그대로다."""
    assert F.classify(_http(502)) == F.UNAVAILABLE


def test_an_auth_failure_wrapped_in_a_5xx_is_auth():
    """⛔ 나머지 절반. 브리지가 상류의 인증 실패를 502 로 싸서 주고, **사유는 본문에만 있다.**
    이것을 일시 장애로 읽으면 사용자는 영원히 재시도한다."""
    assert F.classify(_http(502, _OAUTH)) == F.AUTH


def test_waiting_never_helps_for_auth():
    """⭐ 이 한 줄이 2026-08-13 사고의 전부다."""
    assert F.is_transient(F.AUTH) is False


def test_a_timeout_body_is_not_read_as_auth():
    """504 는 본문을 보기 전에 갈린다 — 순서가 뒤집히면 타임아웃이 인증 실패가 된다."""
    assert F.classify(_http(504, _OAUTH)) == F.TIMEOUT


# ── 분류가 진단 대상을 죽이지 않는가 ───────────────────────────────────────

def test_a_body_that_cannot_be_read_does_not_break_the_classifier():
    """⚠ 스트리밍 응답의 `.text` 는 던질 수 있다. 실패를 분류하려다 실패 처리가 터지면 안 된다."""
    class _Exploding:
        status_code = 502

        @property
        def text(self):
            raise RuntimeError("스트리밍 본문은 못 읽는다")

    exc = RuntimeError("wrapped")
    exc.response = _Exploding()                      # type: ignore[attr-defined]
    assert F.classify(exc) == F.UNAVAILABLE


def test_a_missing_body_is_not_an_error():
    exc = RuntimeError("no response at all")
    assert F.classify(exc) == F.OTHER


# ── 표면까지 오는가 ────────────────────────────────────────────────────────

@pytest.mark.parametrize("reason", [F.TIMEOUT, F.UNAVAILABLE, F.RATE_LIMIT])
def test_every_transient_reason_can_say_wait(reason):
    from nexus.slack.bot import _OUTCOME_BY_REASON

    assert reason in _OUTCOME_BY_REASON, (
        "기다리면 되는 사유가 표면에 안 닿으면 `GENERATION_FAILED` 로 떨어진다")
