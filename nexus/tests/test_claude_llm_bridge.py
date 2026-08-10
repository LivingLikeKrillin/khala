"""claude-code LLM 브리지 — SPEC-nexus-claude-code-llm-dev-backend §5·§7.

브리지 로직은 소켓/서버 없이 순수 함수(`handle_generate`)로 단위 테스트한다. `claude`는 주입된
runner로 대체한다. 급소는 §5의 '문 닫기' 플래그 — argv가 그걸 담는지가 이 하네스의 핵심 계약.
"""

from __future__ import annotations

from nexus.tools.claude_llm_bridge import build_argv, handle_generate
import json


def _runner_ok(text="근거 기반 답변입니다"):
    seen = {}

    def run(argv, prompt, timeout):
        seen["argv"] = argv
        seen["prompt"] = prompt
        seen["timeout"] = timeout
        return (0, text, "")

    return run, seen


# ── §5 보안: 문 닫기 플래그 (load-bearing) ──────────────────────────────────────

def test_argv_closes_every_door():
    """빌트인 툴·MCP·세팅·transcript 지속 — 넷 다 닫혔는지 argv로 고정."""
    argv = build_argv(model=None)
    assert "--allowed-tools" in argv
    # --allowed-tools 다음 토큰은 빈 문자열(deny-all allowlist)
    assert argv[argv.index("--allowed-tools") + 1] == ""
    assert "--strict-mcp-config" in argv
    assert "--no-session-persistence" in argv
    assert "--setting-sources" in argv
    assert "-p" in argv and "--output-format" in argv


def test_argv_adds_model_when_given():
    argv = build_argv(model="claude-sonnet-4-6")
    assert argv[argv.index("--model") + 1] == "claude-sonnet-4-6"


def test_argv_omits_model_when_none():
    assert "--model" not in build_argv(model=None)


# ── §7 handle_generate ──────────────────────────────────────────────────────

def test_generate_returns_claude_stdout_as_text():
    run, seen = _runner_ok("결제 서비스는 payment.completed 를 발행합니다")
    status, body = handle_generate(
        {"system": "너는 근거만 말한다", "prompt": "결제 토픽?"},
        token_header="secret", runner=run, token="secret")
    assert status == 200
    assert body["text"] == "결제 서비스는 payment.completed 를 발행합니다"


def test_prompt_combines_system_and_user():
    run, seen = _runner_ok()
    handle_generate({"system": "SYS-MARKER", "prompt": "USER-MARKER"},
                    token_header="secret", runner=run, token="secret")
    assert "SYS-MARKER" in seen["prompt"] and "USER-MARKER" in seen["prompt"]


def test_nonzero_exit_is_502_with_stderr():
    def run(argv, prompt, timeout):
        return (2, "", "claude exploded")

    status, body = handle_generate({"prompt": "q"}, token_header="secret",
                                   runner=run, token="secret")
    assert status == 502
    assert "claude exploded" in body["error"]


def test_timeout_is_504():
    def run(argv, prompt, timeout):
        raise TimeoutError("agent turn hung")

    status, body = handle_generate({"prompt": "q"}, token_header="secret",
                                   runner=run, token="secret")
    assert status == 504


def test_wrong_token_is_rejected_and_runner_never_spawned():
    called = {"n": 0}

    def run(argv, prompt, timeout):
        called["n"] += 1
        return (0, "x", "")

    status, body = handle_generate({"prompt": "q"}, token_header="WRONG",
                                   runner=run, token="secret")
    assert status in (401, 403)
    assert called["n"] == 0            # 인증 실패 시 claude 를 절대 부르지 않는다


def test_no_token_configured_allows_request():
    """토큰 미설정(빈 문자열) dev 환경에서는 헤더 검사를 건너뛴다."""
    run, seen = _runner_ok()
    status, body = handle_generate({"prompt": "q"}, token_header=None,
                                   runner=run, token="")
    assert status == 200


def test_claude_not_executable_is_502_not_crash():
    """runner 가 OSError(claude 미설치 등)를 던져도 크래시하지 않고 502."""
    def run(argv, prompt, timeout):
        raise FileNotFoundError("claude not found")

    status, body = handle_generate({"prompt": "q"}, token_header="secret",
                                   runner=run, token="secret")
    assert status == 502
    assert "claude" in body["error"]


# ── 이미지 판독: 문은 그대로 닫혀 있는가 ─────────────────────────────────────

def test_vision_argv_keeps_every_door_closed():
    """이미지를 CLI 로 넘기는 통상 경로는 경로 + `Read` 툴인데 ADR-0010 §6 이 그걸 금지한다.
    추출은 quarantine 게이트 **앞**에서 공격자가 넣을 수 있는 바이트에 대해 도는 탓이다.

    `--input-format stream-json` 은 그 문을 안 열고 같은 일을 한다."""
    from nexus.tools.claude_llm_bridge import _DOORS_CLOSED, build_vision_argv

    argv = build_vision_argv(None)
    for i in range(0, len(_DOORS_CLOSED)):
        assert _DOORS_CLOSED[i] in argv
    assert "--allowed-tools" in argv and argv[argv.index("--allowed-tools") + 1] == ""
    assert "--input-format" in argv and "stream-json" in argv
    assert not any(a in ("Read", "--add-dir") for a in argv), "파일시스템 문이 열렸다"


def test_vision_stdin_carries_one_image_and_no_path():
    from nexus.tools.claude_llm_bridge import build_vision_stdin

    line = build_vision_stdin("옮겨 적어라", "QUJD", "image/png")
    msg = json.loads(line)
    content = msg["message"]["content"]
    images = [b for b in content if b.get("type") == "image"]
    assert len(images) == 1
    assert images[0]["source"] == {"type": "base64", "media_type": "image/png", "data": "QUJD"}
    assert "tools" not in msg and "path" not in line.lower().replace("input-format", "")


def test_vision_stdout_keeps_only_assistant_text():
    """stream-json 은 이벤트 스트림이다. 시스템·결과 이벤트를 본문으로 흘리면 추출물에
    판독기가 안 쓴 문장이 섞인다."""
    from nexus.tools.claude_llm_bridge import parse_vision_stdout

    out = "\n".join([
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "| 점수 | 해금 |"}]}}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "\n| 5 | 아바타2 |"}]}}),
        json.dumps({"type": "result", "subtype": "success", "total_cost_usd": 0.1}),
        "쓰레기 한 줄",
    ])
    assert parse_vision_stdout(out) == "| 점수 | 해금 |\n| 5 | 아바타2 |"


def test_vision_requires_an_image():
    from nexus.tools.claude_llm_bridge import handle_vision

    status, body = handle_vision({"system": "x"}, None, runner=_never_called)
    assert status == 400 and "image_b64" in body["error"]


def test_vision_refuses_without_the_token_and_never_runs_claude():
    from nexus.tools.claude_llm_bridge import handle_vision

    status, body = handle_vision(
        {"image_b64": "QUJD"}, "wrong", runner=_never_called, token="secret")
    assert status == 403


def _never_called(*a, **k):
    raise AssertionError("claude 를 불렀다")
