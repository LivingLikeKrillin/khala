"""브리지가 **배포의 `.env` 를 스스로 읽는다** — 그리고 실효 벽을 시동에서 말한다.

⛔ **왜 생겼나 (실측 2026-09-20).** 브리지 둘이 동시에 떠 있었다. 하나는 `.env` 를 읽는
실행기로 **420초**, 다른 하나는 맨 `python -m nexus.tools.claude_llm_bridge` 로 **120초**.
작은 쪽이 이기므로, 어느 것이 응답하느냐에 따라 벽이 달랐고 **그 사실은 504 가 날 때까지
아무 데도 안 보였다.**

그 사이 `providers/llm.py` 는 이렇게 적고 있었다:

    두 프로세스가 같은 `.env` 를 읽지만 **각자 기동할 때** 읽는다.

⛔ **한쪽이 아예 안 읽는 것은 그 문장이 그리는 그림이 아니다.** 앱은 compose 의 `env_file`
로 받고 브리지는 셸이 준 것만 봤다. 이 파일이 지키는 것은 그 문장이 참이 되는 것이다.
"""

from __future__ import annotations

import importlib
import os
import pathlib

import pytest

from nexus.tools import claude_llm_bridge as bridge

ENV_PATH = pathlib.Path(bridge.__file__).resolve().parents[2] / ".env"


@pytest.fixture(autouse=True)
def _restore_environment():
    """⛔ **이 파일은 `os.environ` 을 쓴다 — 그러니 되돌려 놓는다.**

    첫 판이 안 되돌려서 검사 둘을 깨뜨렸다: 실물 `.env` 를 읽는 순간 임베딩 세대가
    프로세스 전체에 퍼져, 배포 대조군과 span 게이트가 다른 세대를 보게 됐다.
    ⭐ 이 리포는 그 모양에 이미 데였다(#503) — **주변 환경을 읽는 검사는 기계를 시험한다.**
    """
    before = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(before)


def test_it_looks_for_the_env_file_beside_the_deployment():
    """`.env` 는 `nexus/` 에 있다 — 앱의 compose `env_file` 이 보는 그 파일이다."""
    assert ENV_PATH.name == ".env"
    assert ENV_PATH.parent.name == "nexus", f"엉뚱한 자리를 본다: {ENV_PATH}"


def test_the_file_only_fills_the_bridges_own_blanks(monkeypatch, tmp_path):
    """⛔ **이미 있는 값을 덮지 않고, 제 몫이 아닌 것은 아예 안 가져온다.**

    덮으면 운영자가 한 번 지정한 것을 파일이 조용히 되돌린다 — 그 되돌림은 기동 로그에도
    안 남는다. 그리고 ⛔ **제 몫이 아닌 것을 가져오면 유료 키가 이 프로세스에 앉는다**
    (`ENV_PREFIX` 머리말, 실측 2026-09-22).
    """
    monkeypatch.setenv("NEXUS_LLM_BRIDGE_TIMEOUT", "77")
    # ⛔ **빈 칸 검사에 토큰 칸을 쓰지 않는다.** 배포 환경에 이미 값이 있으면 단언이 실패하고,
    #    pytest 가 그 **실제 값을 diff 로 찍는다** — 이 리포는 자격 증명이 기록에 찍힌 사고를
    #    이미 여러 건 갖고 있다. 비밀이 아닌 칸으로 같은 계약을 확인한다.
    monkeypatch.delenv("NEXUS_LLM_BRIDGE_QUEUE_WAIT", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    fake = tmp_path / "nexus" / ".env"
    fake.parent.mkdir(parents=True)
    fake.write_text("NEXUS_LLM_BRIDGE_TIMEOUT=999\n"
                    "NEXUS_LLM_BRIDGE_QUEUE_WAIT=9\n"
                    "ANTHROPIC_API_KEY=이-값은-절대-안-가져온다\n", encoding="utf-8")
    monkeypatch.setattr(bridge, "__file__", str(tmp_path / "nexus" / "nexus" / "tools" / "x.py"))

    bridge._load_env_file()

    assert os.environ["NEXUS_LLM_BRIDGE_TIMEOUT"] == "77", "환경에 있던 값을 파일이 덮었다"
    assert os.environ.get("NEXUS_LLM_BRIDGE_QUEUE_WAIT") == "9", "제 몫의 빈 칸을 안 채웠다"
    assert "ANTHROPIC_API_KEY" not in os.environ, \
        "유료 키를 파일에서 가져왔다 — 이 브리지는 키 없이 돈다"


def test_a_missing_file_is_not_an_error(monkeypatch, tmp_path):
    """`.env` 가 없는 체크아웃에서도 브리지는 뜬다 — 없으면 `None` 이고 그것이 전부다."""
    monkeypatch.setattr(bridge, "__file__", str(tmp_path / "a" / "b" / "c" / "x.py"))
    assert bridge._load_env_file() is None


def test_importing_the_module_does_not_touch_the_environment(monkeypatch):
    """⛔ **import 만으로 `os.environ` 이 바뀌면 그 프로세스의 다른 모든 것이 바뀐다.**

    첫 판이 그렇게 만들었다가 검사 셋을 깨뜨렸다 — `.env` 의 임베딩 세대가 흘러들어
    배포 대조군과 span 게이트가 다른 세대를 보게 됐다. 이 리포는 그 모양에 이미 데였다(#503).
    """
    monkeypatch.delenv("NEXUS_LLM_BRIDGE_TIMEOUT", raising=False)
    importlib.reload(bridge)
    assert os.environ.get("NEXUS_LLM_BRIDGE_TIMEOUT") is None, "환경이 바뀌었다"
    assert bridge.ENV_FILE is None, "import 가 파일을 읽었다 — 읽는 자리는 `main()` 이다"


def test_the_wall_is_read_at_call_time_not_frozen_at_import(monkeypatch):
    """⛔ **`main()` 이 `.env` 를 읽은 뒤에 요청이 온다.**

    벽을 모듈 상수로 굳히면 파일을 읽고도 옛 값으로 돌고, 그 갈림은 504 가 날 때까지
    안 보인다 — 실제로 앱 420 · 브리지 120 으로 갈려 돌았다.
    """
    monkeypatch.setenv("NEXUS_LLM_BRIDGE_TIMEOUT", "420")
    assert bridge.current_timeout() == 420.0
    monkeypatch.setenv("NEXUS_LLM_BRIDGE_TIMEOUT", "300")
    assert bridge.current_timeout() == 300.0, "한 번 읽고 굳었다"


def test_main_loads_the_file_before_it_checks_the_token():
    """토큰도 그 파일에 있다 — 뒤에 두면 파일이 있는데도 시동을 거부한다."""
    import inspect

    src = inspect.getsource(bridge.main)
    assert src.index("_load_env_file()") < src.index("NEXUS_LLM_BRIDGE_TOKEN")


def test_the_banner_states_the_effective_wall():
    """⛔ **안 적혀 있던 동안 120 으로 도는 브리지가 조용히 섰다.**

    시동 한 줄이 값을 말하면, 다른 값으로 뜬 것이 그 자리에서 보인다.
    """
    import inspect

    src = inspect.getsource(bridge.main)
    assert "current_timeout()" in src, "배너가 실효 벽을 안 말한다"


@pytest.mark.skipif(not ENV_PATH.exists(), reason="이 배포에만 있는 파일")
def test_this_deployment_agrees_with_the_app(monkeypatch):
    """⭐ **대조군 — 두 프로세스가 같은 수를 본다.**

    앱은 `providers/llm.py::_bridge_timeout` 으로 브리지 벽 + 여유를 만든다. 두 값이 같은
    파일에서 나오는지 여기서 본다. 갈리면 작은 쪽이 이기고, 그 갈림은 조용하다.
    """
    monkeypatch.delenv("NEXUS_LLM_BRIDGE_TIMEOUT", raising=False)
    bridge._load_env_file()          # `main()` 이 하는 그 일
    from_file = bridge.current_timeout()

    from nexus.providers import llm

    assert llm._bridge_timeout() == pytest.approx(from_file + llm._BRIDGE_HEADROOM), \
        "앱이 보는 벽과 브리지가 보는 벽이 같은 파일에서 안 나온다"
    assert from_file > 0
