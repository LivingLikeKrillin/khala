"""`claude` 의 **오류가 답으로 나가지 않는가** — 브리지가 출력의 **모양**을 보고 가른다.

⛔ **왜 생겼나 (2026-09-27, 설명 레이어 자문).** 브리지는 `claude -p --output-format text` 의 stdout 을
그대로 답으로 돌려줬다. `claude` 가 오류를 **stdout 에 글로** 쓰고 0 으로 끝나면 그 문장이 200 과
함께 **답변**으로 나간다. 인용 검증도 숫자 검증도 그것을 오류로 못 본다 — 인용 없는 짧은 답일
뿐이다. 사용 한도 안내가 그 모양의 후보였고, 그 경우 `llm_failed` 가 안 서서 재시도할 쪽은
**틀린 답을 받은 줄도 모른다.**

JSON 출력은 오류를 **값으로** 준다: `is_error` · `api_error_status` · `result`. 실측(2026-09-30,
없는 모델 이름으로 생성 없이 실패시켰다): rc 1 · `is_error: true` · `api_error_status: 404` ·
`result` 에 오류 문장. ⛔ 그리고 **`subtype` 은 오류에도 `"success"` 였다** — 판정은 `is_error` 로 한다.
"""

from __future__ import annotations

import json

import httpx
import pytest

from nexus.llm import failure as F
from nexus.providers import llm as P
from nexus.tools.claude_llm_bridge import build_argv, handle_generate, handle_vision

#: 실측한 오류 결과의 모양(09-30). 값만 바꿔 쓴다 — 키를 지어내지 않는다.
_MEASURED_ERROR = {
    "type": "result", "subtype": "success", "is_error": True, "api_error_status": 404,
    "stop_reason": "stop_sequence", "result": "There's an issue with the selected model "
    "(claude-nonexistent-model-x). It may not exist or you may not have access to it.",
    "modelUsage": {}, "usage": {},
}


def _result(**kw) -> str:
    return json.dumps({"type": "result", "subtype": "success", "is_error": False,
                       "api_error_status": None, "result": "", **kw}, ensure_ascii=False)


def _runner(rc: int, out: str, err: str = ""):
    def run(argv, prompt, timeout):
        return (rc, out, err)
    return run


def _generate(rc: int, out: str, err: str = ""):
    return handle_generate({"prompt": "q"}, token_header=None, runner=_runner(rc, out, err), token="")


def test_the_bridge_asks_for_structured_output():
    argv = build_argv(model=None)
    assert argv[argv.index("--output-format") + 1] == "json"


def test_a_success_result_is_the_answer():
    status, body = _generate(0, _result(result="결제 서비스는 payment.completed 를 발행합니다"))
    assert (status, body) == (200, {"text": "결제 서비스는 payment.completed 를 발행합니다"})


def test_an_error_result_is_never_an_answer_even_when_claude_exits_zero():
    """⛔ **이 검사가 이 단위의 이유다.** 종료 코드가 0 이어도 오류는 오류다."""
    limit = "Claude AI usage limit reached. Your limit will reset at 3pm."
    status, body = _generate(0, _result(is_error=True, api_error_status=429, result=limit))
    assert status == 429, "상류 상태를 그대로 넘겨야 앱의 분류기가 가른다"
    assert "text" not in body, "오류 문장이 답의 자리로 나갔다"
    assert limit in body["error"], "오류 문장은 버리지 않는다 — 그것이 처방이다"


def test_an_error_without_an_upstream_status_is_a_502():
    status, body = _generate(0, _result(is_error=True, result="무언가 잘못됐다"))
    assert status == 502 and "text" not in body and "무언가 잘못됐다" in body["error"]


def test_the_measured_error_carries_its_own_sentence_not_the_debug_line():
    """실측 그대로: rc 1 에 stderr 는 디버그 한 줄, 사유는 JSON 의 `result` 에 있다."""
    status, body = _generate(1, json.dumps(_MEASURED_ERROR),
                             '[claude-code:unrecognized_model] {"model":"x"}')
    assert status == 404
    assert "issue with the selected model" in body["error"]


def test_output_that_is_not_json_is_not_an_answer():
    """무엇이 왔는지 모르면 답으로 내보내지 않는다 — 옛 경로가 바로 이것을 답으로 냈다."""
    status, body = _generate(0, "Claude AI usage limit reached|1759240000")
    assert status == 502 and "text" not in body
    assert "JSON" in body["error"]


def test_a_result_without_text_is_not_an_answer():
    status, body = _generate(0, _result(result=None))
    assert status == 502 and "text" not in body


def _vision(rc: int, out: str):
    return handle_vision({"image_b64": "QUJD"}, None, runner=_runner(rc, out), token="")


def _events(*events) -> str:
    return "\n".join(json.dumps(e, ensure_ascii=False) for e in events)


def test_the_image_path_does_not_pass_an_error_off_as_extracted_text():
    """기계 판독 경로도 같은 구멍이다 — API 오류는 **assistant 문장**으로도 흐른다."""
    out = _events(
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "API Error: 529 overloaded"}]}},
        {"type": "result", "subtype": "success", "is_error": True, "api_error_status": 529,
         "result": "API Error: 529 overloaded"},
    )
    status, body = _vision(0, out)
    assert status == 529 and "text" not in body


def test_the_image_path_still_returns_what_was_read():
    out = _events(
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "| 점수 | 해금 |"}]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": "| 점수 | 해금 |"},
    )
    assert _vision(0, out) == (200, {"text": "| 점수 | 해금 |"})


def test_an_image_run_that_never_reported_a_result_is_not_trusted():
    """끝을 알리는 결과 이벤트가 없으면 끝까지 읽었는지 모른다 — 반쪽 표를 완결로 넘기지 않는다."""
    out = _events({"type": "assistant", "message": {"content": [{"type": "text", "text": "| 점수 |"}]}})
    status, body = _vision(0, out)
    assert status == 502 and "text" not in body


# ── 앱까지 — 오류가 **사유 있는 실패**로 도착하는가 ─────────────────────────────

@pytest.mark.parametrize("upstream, reason", [
    (429, F.RATE_LIMIT),
    (None, F.UNAVAILABLE),
], ids=["with-status", "without-status"])
async def test_the_app_sees_a_failure_with_a_reason_not_an_answer(upstream, reason, monkeypatch):
    """브리지가 넘긴 상태를 앱의 분류기가 읽는다 — 분류 규칙은 브리지에 두지 않는다
    (`test_bridge_failure_detail.py` 의 마지막 검사가 사본을 막는다)."""
    out = _result(is_error=True, api_error_status=upstream, result="Claude AI usage limit reached")

    def bridge(request: httpx.Request) -> httpx.Response:
        status, body = handle_generate(json.loads(request.content), None,
                                       runner=_runner(0, out), token="")
        return httpx.Response(status, json=body)

    monkeypatch.setattr(P, "_bridge_transport", lambda: httpx.MockTransport(bridge))
    with pytest.raises(httpx.HTTPStatusError) as ei:
        await P._ClaudeCodeBackend("claude-sonnet-5").generate_full("sys", "user", 100)
    assert F.classify(ei.value) == reason
