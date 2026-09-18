"""502 가 **왜** 인지를 실어 보내는가.

⛔ **실측 2026-09-18.** 호스트의 `claude` OAuth 세션이 만료돼 브리지가 즉시 502 를 냈다.
그런데 본문은 `"claude non-zero exit"` 하나였다 — 처방이 적힌 줄
(`Failed to authenticate: OAuth session expired and could not be refreshed`)은
**stdout 에 있었고 버려졌다.** 코드가 `err` 만 봤기 때문이다.

그 한 줄이 없어서 읽는 쪽은 *"생성 서비스가 안 받는다"* 로 읽고 포트·컨테이너·네트워크를
먼저 뒤졌다. 실제로 필요한 것은 사람이 한 번 다시 로그인하는 것이었다.

이 리포의 규율은 이미 그 반대를 적어 두었다 — 백엔드 메시지는 **요약하지 말고 그대로**
남긴다, *"왜 안 되는지" 가 곧 처방이다* (`nexus/CLAUDE.md` §에러 처리, `embed_refusals`
가 같은 이유로 그렇게 돼 있다).
"""

from __future__ import annotations

import pytest

from nexus.tools.claude_llm_bridge import failure_detail, handle_generate, handle_vision

_AUTH = "Failed to authenticate: OAuth session expired and could not be refreshed"


def _runner(rc: int, out: str, err: str):
    def run(argv, prompt, timeout):
        return (rc, out, err)
    return run


# ── 어느 쪽에 있든 이유를 집는다 ───────────────────────────────────────────

def test_a_reason_on_stdout_is_not_thrown_away():
    """⛔ 이 검사가 이 단위의 전부다. 실제로 버려진 것이 이 문자열이다."""
    assert failure_detail(_AUTH + "\n", "") == _AUTH


def test_stderr_wins_when_both_speak():
    assert failure_detail("noise", "real reason") == "real reason"


def test_silence_says_it_is_silence():
    """⚠ *이유를 못 받은 것*과 *이유가 이것인 것*이 같은 문장이면 안 된다."""
    got = failure_detail("", "   ")
    assert "비어 있다" in got


def test_the_reason_is_not_summarised_only_bounded():
    long = "x" * 5000
    assert failure_detail("", long) == "x" * 1000


# ── 두 경로가 같은 규칙을 쓰는가 ───────────────────────────────────────────

@pytest.mark.parametrize("handler,payload", [
    (handle_generate, {"prompt": "q"}),
    (handle_vision, {"system": "s", "image_b64": "aGk=", "media_type": "image/png"}),
], ids=["generate", "vision"])
def test_both_paths_carry_the_reason(handler, payload):
    """⛔ 한쪽만 고치면 다음 사람이 다른 쪽에서 같은 자리를 다시 밟는다."""
    status, body = handler(payload, token_header=None,
                           runner=_runner(1, _AUTH, ""), token="")
    assert status == 502
    assert _AUTH in body["error"], "이유가 본문에 없다"


def test_the_bridge_does_not_keep_its_own_copy_of_the_rule():
    """규칙이 두 곳에 있으면 한쪽만 고쳐진다 — 이번이 정확히 그 모양이었다(두 곳 다 틀렸다)."""
    import pathlib

    from nexus.tools import claude_llm_bridge

    src = pathlib.Path(claude_llm_bridge.__file__).read_text(encoding="utf-8")
    assert src.count("failure_detail(out, err)") == 2
    assert "claude non-zero exit" not in src.split("def failure_detail")[0], (
        "옛 문구가 아직 어딘가에 하드코딩돼 있다")
