"""벽이 어디 있고, 걸렸을 때 그 사실을 말하는가.

⛔ **실측 2026-09-19.** 설명 층이 질의에 정황을 싣기 시작하자 합성이 100~119초를 쓰게 됐고,
브리지의 **하드코딩 120초**에 호출 셋 중 하나가 걸렸다. 최대 성공 118,755ms · 최소 실패
121,040ms — 사이가 2.3초다. 그런데 504 본문은 `"claude 응답이 시간 초과되었습니다"` 뿐이라,
읽는 쪽은 자기가 121초에 걸렸는지 300초에 걸렸는지 몰랐다. **그 수를 모르면 기다릴지
질의를 줄일지 정할 수 없다.**

⚠ **기본값은 올리지 않았다.** 벽을 올려 덮으면 느리다는 사실만 안 보이게 된다. 이 배포의
실제 내역은 검색 2.3초 · 합성 44.6초(답변 1,410자·근거 26)이고, 벽보다 먼저 볼 값은 그쪽이다.
"""

from __future__ import annotations

import importlib
import subprocess

import pytest

from nexus.tools import claude_llm_bridge as bridge


def _reload(monkeypatch, value: str | None):
    if value is None:
        monkeypatch.delenv("NEXUS_LLM_BRIDGE_TIMEOUT", raising=False)
    else:
        monkeypatch.setenv("NEXUS_LLM_BRIDGE_TIMEOUT", value)
    return importlib.reload(bridge)


@pytest.fixture(autouse=True)
def _restore():
    yield
    importlib.reload(bridge)


# ── 벽이 배포의 것인가 ─────────────────────────────────────────────────────

def test_the_wall_defaults_to_two_minutes(monkeypatch):
    """⚠ 기본을 바꾸지 않았다는 것 자체를 고정한다 — 조용히 올리면 느림이 숨는다."""
    assert _reload(monkeypatch, None)._DEFAULT_TIMEOUT == 120.0


def test_a_deployment_can_move_the_wall(monkeypatch):
    assert _reload(monkeypatch, "300")._DEFAULT_TIMEOUT == 300.0


def test_an_empty_value_is_the_default_not_zero(monkeypatch):
    """⛔ `NEXUS_LLM_BRIDGE_TIMEOUT=` 가 0 초가 되면 **모든 호출이 즉시 죽는다.**
    빈 값은 "안 정했다" 이지 "0" 이 아니다."""
    assert _reload(monkeypatch, "")._DEFAULT_TIMEOUT == 120.0


# ── 걸렸을 때 무엇을 말하는가 ──────────────────────────────────────────────

def test_the_timeout_body_says_how_long_it_waited():
    """⛔ 이 검사가 이 단위의 이유다. 수가 없으면 다음 행동을 못 정한다."""
    got = bridge.timeout_detail(120.0)
    assert "120" in got


def test_the_timeout_body_names_the_knob():
    """읽는 사람이 **어디를 고치는지**까지 와야 한 번에 끝난다."""
    assert "NEXUS_LLM_BRIDGE_TIMEOUT" in bridge.timeout_detail(120.0)


def test_the_timeout_body_does_not_only_say_raise_it():
    """⚠ 벽을 올리는 것이 유일한 처방인 것처럼 적으면 느림이 영원히 안 보인다."""
    assert "합성" in bridge.timeout_detail(120.0)


@pytest.mark.parametrize("handler,payload", [
    ("handle_generate", {"prompt": "q"}),
    ("handle_vision", {"system": "s", "image_b64": "aGk=", "media_type": "image/png"}),
], ids=["generate", "vision"])
def test_both_paths_report_the_limit(handler, payload):
    """⛔ 한쪽만 고치면 다음 사람이 다른 쪽에서 같은 자리를 다시 밟는다 — #513 이 그랬다."""
    def boom(argv, prompt, timeout):
        raise subprocess.TimeoutExpired(argv, timeout)

    status, body = getattr(bridge, handler)(
        payload, token_header=None, runner=boom, token="", timeout=137.0)
    assert status == 504
    assert "137" in body["error"], "기다린 시간이 본문에 없다"


def test_neither_path_keeps_its_own_copy_of_the_sentence():
    import pathlib

    src = pathlib.Path(bridge.__file__).read_text(encoding="utf-8")
    assert src.count("timeout_detail(timeout)") == 2
    # ⚠ 파일 전체에서 옛 문구를 금지하면 **그 문구를 인용한 주석**까지 걸린다. 금지할 것은
    # 그것을 **돌려주는 것**이지 그것에 대해 말하는 것이 아니다 — 이 검사를 처음 쓸 때 실제로
    # 내 주석이 걸렸다.
    assert '{"error": "claude 응답' not in src, "옛 문구를 아직 그대로 돌려준다"
