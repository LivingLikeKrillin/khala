"""Keyless Arbiter critic — SPEC-arbiter-claude-code-critic §4·§5·§7.

`claude`를 실제로 띄우지 않고 주입 runner 로 단위 테스트한다. 급소는 §5의 '문 닫기' 플래그 —
critic 이 spawn 하는 argv 가 그 넷을 담는지가 계약. 파싱 실패·비정상 종료는 raise(fail-closed).
"""

from __future__ import annotations

import pytest

from khala.arbiter.critique import (
    AnthropicCritic,
    ClaudeCodeCritic,
    make_critic,
)

RUBRIC = ["risky-assumption", "adr-contradiction"]


def _runner(rc=0, out='[{"category":"risky-assumption","severity":"high","description":"d"}]', err=""):
    seen = {}

    def run(argv, prompt, timeout):
        seen["argv"] = argv
        seen["prompt"] = prompt
        seen["timeout"] = timeout
        return (rc, out, err)

    return run, seen


# ── §5 보안: 문 닫기 (load-bearing) ──────────────────────────────────────────

def test_argv_closes_every_door():
    run, seen = _runner()
    ClaudeCodeCritic(runner=run).find_issues("body", [], RUBRIC)
    argv = seen["argv"]
    assert argv[argv.index("--allowed-tools") + 1] == ""       # deny-all allowlist
    assert "--strict-mcp-config" in argv
    assert "--setting-sources" in argv
    assert "--no-session-persistence" in argv
    assert "-p" in argv


# ── §7 파싱 & fail-closed ────────────────────────────────────────────────────

def test_find_issues_parses_json_array():
    run, _ = _runner(out='[{"category":"adr-contradiction","severity":"medium","description":"x"}]')
    issues = ClaudeCodeCritic(runner=run).find_issues("b", [], RUBRIC)
    assert issues == [("adr-contradiction", "medium", "x")]


def test_find_issues_unwraps_fenced_json():
    run, _ = _runner(out='```json\n[{"category":"risky-assumption","severity":"low","description":"y"}]\n```')
    issues = ClaudeCodeCritic(runner=run).find_issues("b", [], RUBRIC)
    assert issues == [("risky-assumption", "low", "y")]


def test_nonzero_exit_raises():
    run, _ = _runner(rc=2, out="", err="claude exploded")
    with pytest.raises(Exception):
        ClaudeCodeCritic(runner=run).find_issues("b", [], RUBRIC)


def test_unparseable_output_raises():
    run, _ = _runner(out="this is not json")
    with pytest.raises(Exception):
        ClaudeCodeCritic(runner=run).find_issues("b", [], RUBRIC)


def test_prompt_carries_body_and_rubric():
    run, seen = _runner()
    ClaudeCodeCritic(runner=run).find_issues("UNIQUE-BODY-MARKER", [], RUBRIC)
    assert "UNIQUE-BODY-MARKER" in seen["prompt"]
    assert "adr-contradiction" in seen["prompt"]        # rubric 이 프롬프트에 들어간다


# ── §4.2 selector ────────────────────────────────────────────────────────────

def test_make_critic_default_is_anthropic(monkeypatch):
    monkeypatch.delenv("ARBITER_CRITIC", raising=False)
    assert isinstance(make_critic(), AnthropicCritic)


def test_make_critic_claude_code(monkeypatch):
    monkeypatch.setenv("ARBITER_CRITIC", "claude-code")
    assert isinstance(make_critic(), ClaudeCodeCritic)


def test_make_critic_unknown_raises(monkeypatch):
    monkeypatch.setenv("ARBITER_CRITIC", "gpt5")
    with pytest.raises(ValueError):
        make_critic()
