"""LLM 실패 사유 — 기다리면 되는 것과 사람이 고쳐야 하는 것을 가른다.

2026-08-13 슬랙 파일럿에서 크레딧이 떨어졌고, 사용자에게 나간 문장은 "잠시 후 다시
시도하세요" 였다. 기다려도 영원히 안 된다. 이 파일이 지키는 것은 그 문장이 두 번 다시 그
상황에서 나오지 않는다는 것이다.
"""

from __future__ import annotations

import httpx
import pytest

from nexus.llm import failure as F


class _Status(Exception):
    """anthropic SDK 의 APIStatusError 모양 — `status_code` 를 예외에 직접 단다."""

    def __init__(self, status_code: int, message: str = ""):
        super().__init__(message)
        self.status_code = status_code


class _Timeout(Exception):
    """이름에 timeout 이 든 예외(httpx.TimeoutException·anthropic.APITimeoutError 관례)."""


# ── 분류 ──────────────────────────────────────────────────────────────────────

def test_credit_exhaustion_is_quota_not_a_generic_error():
    """실제로 온 문장 그대로. 이것이 `other` 로 떨어지면 아무도 결제하지 않는다."""
    real = ("Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
            "'message': 'Your credit balance is too low to access the Anthropic API. "
            "Please go to Plans & Billing to upgrade or purchase credits.'}}")
    assert F.classify(_Status(400, real)) == F.QUOTA


def test_an_ordinary_bad_request_is_not_quota():
    """400 이라고 다 청구 문제가 아니다 — 그렇게 보면 진짜 버그가 결제 안내로 위장한다."""
    assert F.classify(_Status(400, "messages: at least one message is required")) == F.OTHER


@pytest.mark.parametrize("status,expected", [
    (401, F.AUTH), (403, F.AUTH), (402, F.QUOTA), (429, F.RATE_LIMIT),
    (500, F.UNAVAILABLE), (502, F.UNAVAILABLE), (529, F.UNAVAILABLE),
])
def test_status_codes_map_to_stable_reasons(status, expected):
    assert F.classify(_Status(status, "x")) == expected


def test_the_bridge_carries_its_status_on_the_response():
    """브리지는 httpx 다 — 상태가 예외가 아니라 `.response` 에 있다. 둘 다 캐야 한다."""
    req = httpx.Request("POST", "http://bridge/x")
    exc = httpx.HTTPStatusError("502", request=req, response=httpx.Response(502, request=req))
    assert F.classify(exc) == F.UNAVAILABLE


def test_timeouts_and_connection_failures_have_no_status():
    assert F.classify(_Timeout("read timed out")) == F.UNAVAILABLE
    assert F.classify(httpx.ConnectError("refused")) == F.UNAVAILABLE


def test_an_unknown_failure_is_not_called_transient():
    """모르는 것을 '기다리면 된다' 로 분류하면, 영원히 실패하는 것에 대해 기다리라고 말하게 된다."""
    assert F.classify(RuntimeError("무슨 일인지 모른다")) == F.OTHER
    assert F.is_transient(F.OTHER) is False


def test_the_retry_axis_lives_here_not_in_each_client():
    """표면마다 이 축을 다시 유도하면 답이 갈린다."""
    assert F.is_transient(F.RATE_LIMIT) and F.is_transient(F.UNAVAILABLE)
    assert not F.is_transient(F.QUOTA) and not F.is_transient(F.AUTH)
    assert not F.is_transient(None)


def test_reason_codes_are_a_closed_set():
    """응답에 실려 나가는 값이다 — 늘리는 것은 계약 변경이고, 조용히 하면 안 된다."""
    assert set(F.REASONS) == {"quota", "auth", "rate_limit", "unavailable", "other"}


# ── 생성기가 사유를 남기는가 ───────────────────────────────────────────────────

async def test_generate_answer_records_why_it_failed(monkeypatch):
    """`except Exception` 이 예외를 버리던 자리. 사유가 결과에 남아야 응답에 실을 수 있다."""
    from nexus.llm import answer as A

    class _Boom:
        model = "m"
        configured = True

        async def generate_full(self, *a, **k):
            raise _Status(400, "Your credit balance is too low")

    result = await A.generate_answer("질문", await _packet(), llm_svc=_Boom())
    assert result.llm_failed is True
    assert result.llm_failure_reason == F.QUOTA


async def test_a_successful_answer_has_no_failure_reason(monkeypatch):
    from nexus.llm import answer as A
    from nexus.providers.llm import LLMResult, Usage

    class _Ok:
        model = "m"
        configured = True

        async def generate_full(self, *a, **k):
            return LLMResult(text="답", usage=Usage(1, 1, None, "m"))

    result = await A.generate_answer("질문", await _packet(), llm_svc=_Ok())
    assert result.llm_failed is False
    assert result.llm_failure_reason is None


async def _packet():
    """근거가 **있는** 패킷. 비어 있으면 생성기는 LLM 을 부르기 전에 기권하고(abstained),
    그러면 이 시험은 실패 분류가 아니라 기권 경로를 측정하게 된다."""
    from nexus.search.evidence_packet import assemble_packet
    from nexus.search.hybrid import SearchHit

    hit = SearchHit(rid="c1", doc_rid="d1", doc_title="문서", section_path="절",
                    source_uri="git://repo:d.md", snippet="근거", chunk_text="근거 본문",
                    score=0.9)
    return await assemble_packet([hit], None)


# ── 슬랙이 사유별로 다른 말을 하는가 ────────────────────────────────────────────

import httpx as _httpx  # noqa: E402

from nexus.slack import bot  # noqa: E402
from nexus.slack.messages import Outcome, message_for  # noqa: E402


def _bot_answering(monkeypatch, *, reason=None):
    """서버가 `llm_failed` + 사유를 돌려주는 상황을 만든다."""
    def handler(request):
        return _httpx.Response(200, json={"success": True, "data": {
            "answer": "답변을 생성할 수 없습니다. 아래 근거를 직접 확인해주세요.\n\n" + "근거" * 500,
            "evidence_snippets": [{"doc_title": "t"}],
            "llm_failed": True, "llm_failure_reason": reason}})
    monkeypatch.setattr(bot, "_transport", lambda: _httpx.MockTransport(handler))
    monkeypatch.setattr(bot, "NEXUS_SLACK_TOKEN", "tok")


@pytest.mark.parametrize("reason,outcome", [
    ("quota", Outcome.LLM_QUOTA),
    ("auth", Outcome.LLM_AUTH),
    ("rate_limit", Outcome.LLM_BUSY),
    ("unavailable", Outcome.LLM_BUSY),
    ("other", Outcome.GENERATION_FAILED),
    (None, Outcome.GENERATION_FAILED),      # 사유를 모르는 옛 서버와도 물린다
])
async def test_each_reason_reaches_its_own_message(monkeypatch, reason, outcome):
    _bot_answering(monkeypatch, reason=reason)
    with pytest.raises(bot.NexusCallError) as e:
        await bot._call_nexus_api("q")
    assert e.value.outcome is outcome


def test_only_the_transient_failures_tell_the_user_to_wait():
    """**이 파일의 이유 전부.** 크레딧 소진에 "잠시 후 다시" 라고 말하면 아무도 결제하지 않는다."""
    assert "잠시 후" in message_for(Outcome.LLM_BUSY)
    for permanent in (Outcome.LLM_QUOTA, Outcome.LLM_AUTH):
        m = message_for(permanent)
        assert "잠시 후" not in m, f"{permanent}: 기다리면 된다고 말하고 있다"
        assert "운영자" in m, f"{permanent}: 고칠 사람을 안 부른다"


def test_quota_says_what_ran_out_and_that_retrying_will_not_help():
    m = message_for(Outcome.LLM_QUOTA)
    assert "크레딧" in m and "재시도" in m


def test_no_message_leaks_a_provider_string():
    """공급자 문구는 바뀐다. 사용자에게 그대로 흘리면 우리 UI 가 공급자 릴리스에 묶인다."""
    for o in Outcome:
        m = message_for(o)
        assert "Anthropic" not in m and "credit balance" not in m


def test_a_configured_usage_limit_is_quota_not_other():
    """2026-08-13 에 실제로 온 문장. 잡지 못해 `other` 로 떨어졌고, 사용자는 일반 오류를 받는다.

    크레딧 잔액과 다른 사건이지만 사용자에게는 같다 — **사람이 한도를 올리기 전까지 영원히
    실패한다.** 재시도하라고 말하면 거짓이 된다.
    """
    real = ("Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', "
            "'message': 'You have reached your specified API usage limits. "
            "You will regain access on 2026-09-01 at 00:00 UTC.'}}")
    assert F.classify(_Status(400, real)) == F.QUOTA
    assert F.is_transient(F.QUOTA) is False


def test_the_word_limit_alone_does_not_mean_quota():
    """`rate limit` 은 429 로 오고 기다리면 풀린다 — 문구만 보고 청구로 몰면 오분류다."""
    assert F.classify(_Status(400, "context length limit exceeded")) == F.OTHER
    assert F.classify(_Status(429, "rate limit exceeded")) == F.RATE_LIMIT
