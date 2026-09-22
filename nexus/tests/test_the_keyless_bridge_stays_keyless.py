"""이 브리지는 **키 없이 돈다** — 무엇을 물려받았든.

⛔ **왜 생겼나 (실측 2026-09-22).** 설명 층이 판을 돌렸고 생성 열셋이 **전부 즉시** 죽었다.
검색은 멀쩡했고 조각도 제대로 왔다. 브리지도 살아 있었다(무토큰 POST 에 403 을 2.8ms 에 답했다).

컨테이너에서 확인하니 닿는 것도 되고 토큰도 맞았다. 막힌 자리는 그 다음이었다:

    HTTP 502
    ⚠ claude.ai connectors are disabled because ANTHROPIC_API_KEY or another auth
      source is set and takes precedence over your claude.ai login

⛔ **내가 만든 결함이다.** `#529` 로 브리지가 `nexus/.env` 를 읽게 하면서 **파일 전체**를
`os.environ` 에 부었다. 그 파일에는 유료 키가 있고, `subprocess.run` 은 기본으로 부모 환경을
물려주므로 **유료 키가 키리스 백엔드의 자식에게 그대로 넘어갔다.**

⭐ **거부가 우리를 구했다.** `claude` 가 받아들였으면 「개발 실행에 돈을 쓰지 않는다」가
**조용히** 깨진 채로 돌았을 것이다 — 그리고 이 리포의 어떤 검사도 그것을 안 봤다.

⚠ **밖에서는 이것이 「생성이 즉시 죽는다」로만 보인다.** 소비자는 벽도 아니고 배선도 아니라는
것까지만 알 수 있었다. 그래서 시동 배너가 **뺀 인증 자료의 수**를 말한다.
"""

from __future__ import annotations

import os
import subprocess

import pytest

from nexus.tools import claude_llm_bridge as bridge


@pytest.fixture(autouse=True)
def _restore_environment():
    before = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(before)


@pytest.mark.parametrize("name", bridge.BLOCKED_CHILD_ENV)
def test_no_paid_credential_reaches_the_child(monkeypatch, name):
    """⛔ **파일에서 왔든 셸에서 왔든 자식에게는 안 간다.**

    파일 쪽은 `ENV_PREFIX` 가 막고, 셸 쪽은 이것이 막는다. 둘 다 필요하다 — 운영자가
    export 한 키는 `.env` 를 안 거친다.
    """
    monkeypatch.setenv(name, "값이-무엇이든")
    assert name not in bridge.child_env(), f"{name} 이 자식 환경에 남아 있다"


def test_it_keeps_everything_else(monkeypatch):
    """대조군 — 막는 것만 막는다. 다 지우면 `claude` 가 `PATH` 도 못 찾는다."""
    monkeypatch.setenv("NEXUS_LLM_BRIDGE_TIMEOUT", "420")
    env = bridge.child_env()
    assert env.get("NEXUS_LLM_BRIDGE_TIMEOUT") == "420"
    assert "PATH" in env or "Path" in env, "환경을 통째로 비웠다"


def test_the_runner_hands_that_env_to_the_subprocess(monkeypatch):
    """⛔ **함수가 옳은 것과 부르는 쪽이 넘기는 것은 다른 사실이다.**

    `child_env()` 만 검사하면, 그것을 아무도 안 넘겨도 초록이다 — `cwd` 가 같은 구분에서
    이미 한 번 이 리포를 물었다(`test_bridge_runs_outside_the_repo`).
    """
    seen: dict = {}

    class _P:
        returncode, stdout, stderr = 0, "ok", ""

    def fake_run(argv, **kw):
        seen.update(kw)
        return _P()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "이-값은-자식에게-가면-안-된다")
    monkeypatch.setattr(bridge.subprocess, "run", fake_run)
    bridge._subprocess_runner(["claude"], "프롬프트", 5.0)

    assert "env" in seen, "`env` 를 안 넘긴다 — 부모 환경을 통째로 물려준다"
    assert "ANTHROPIC_API_KEY" not in seen["env"], "넘긴 환경에 유료 키가 있다"


def test_the_banner_says_what_it_stripped():
    """⛔ **안 적혀 있던 동안 밖에서는 「생성이 즉시 죽는다」로만 보였다.**

    시동 한 줄이 그 수를 말하면, 키가 근처에 있었다는 사실이 그 자리에서 보인다.
    """
    import inspect

    src = inspect.getsource(bridge.main)
    assert "BLOCKED_CHILD_ENV" in src, "배너가 뺀 인증 자료를 안 말한다"


def test_the_blocked_list_covers_what_the_cli_named():
    """`claude` 가 이름으로 부른 것은 반드시 목록에 있다."""
    assert "ANTHROPIC_API_KEY" in bridge.BLOCKED_CHILD_ENV


@pytest.mark.skipif(not (
    __import__("pathlib").Path(bridge.__file__).resolve().parents[2] / ".env").exists(),
    reason="이 배포에만 있는 파일")
def test_this_deployment_would_have_leaked(monkeypatch):
    """⭐ **대조군 — 이 배포의 `.env` 에 실제로 막을 것이 들어 있다.**

    없으면 위 검사들이 전부 빈 총이다. 값은 절대 읽지 않고 **키 이름만** 본다.
    """
    import pathlib

    path = pathlib.Path(bridge.__file__).resolve().parents[2] / ".env"
    names = {ln.split("=", 1)[0].strip()
             for ln in path.read_text(encoding="utf-8").splitlines()
             if "=" in ln and not ln.strip().startswith("#")}
    assert names & set(bridge.BLOCKED_CHILD_ENV), \
        "이 배포의 .env 에 막을 것이 없다 — 그러면 위 검사들이 무엇도 안 지킨다"
    assert not any(n.startswith(bridge.ENV_PREFIX) for n in (names & set(bridge.BLOCKED_CHILD_ENV))), \
        "막는 이름이 브리지 접두사와 겹친다 — 두 규칙이 서로를 무효로 만든다"
