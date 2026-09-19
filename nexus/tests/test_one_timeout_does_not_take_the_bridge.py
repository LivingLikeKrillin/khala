"""브리지가 한 건 도는 동안 **다른 것도 받는가**, 그리고 줄 선 것은 줄 섰다고 말하는가.

⛔ **실측 2026-09-19, 설명 층 보고.** 서버가 `HTTPServer` 였다 — 합성 한 건이 2분 도는 동안
소켓이 다른 아무것도 받지 않는다. 밖에서 건 `curl http://127.0.0.1:8900/` 이 그대로
타임아웃했다. 그리고 이 브리지를 부르는 것은 설명 층만이 아니다: 주기 재적재
(`nexus-reingest`)도 같은 문을 친다. 줄을 세우는 곳이 없어서 조용히 겹쳤다.

관측된 순서는 **타임아웃 둘 → 브리지 프로세스 소멸 → 뒤에 줄 선 것 전부 실패**였다.
⚠ 소멸의 원인은 우리도 모른다 — 여기서 고치는 것은 *"한 건이 전체를 막는다"* 쪽이다.
막히지 않으면 한 건의 실패가 한 건으로 끝날 여지가 생긴다.

⛔ **스레드만 늘리면 안 된다.** 그러면 `claude` 프로세스가 동시에 여럿 떠서 호스트를 갈아
넣는다. **문만 두면** 소켓이 여전히 막힌다. 소켓은 열고, 비싼 것만 하나씩이다.
"""

from __future__ import annotations

import threading
import time

import pytest

from nexus.tools import claude_llm_bridge as bridge


def _slow_runner(seconds: float):
    def run(argv, prompt, timeout):
        time.sleep(seconds)
        return (0, "ok", "")
    return run


@pytest.fixture(autouse=True)
def _fresh_gate():
    """검사끼리 문을 물려주지 않는다 — 한 검사가 안 놓으면 다음 검사가 이유 없이 막힌다."""
    yield
    while bridge._GATE._value < bridge._MAX_CONCURRENT:      # noqa: SLF001
        bridge._GATE.release()


# ── 소켓이 막히지 않는가 ───────────────────────────────────────────────────

def test_the_server_is_threading():
    """⛔ 이 한 줄이 「합성 도는 동안 아무것도 못 받는다」의 전부였다."""
    import pathlib

    # ⚠ 부분 문자열로 금지하면 `ThreadingHTTPServer` 안에 `HTTPServer` 가 들어 있어서
    # **고친 줄이 스스로 걸린다.** 이 계열 실수를 이 세션에서 네 번 했다 — 줄 단위로 본다.
    src = pathlib.Path(bridge.__file__).read_text(encoding="utf-8")
    serve = [ln.strip() for ln in src.splitlines() if ".serve_forever()" in ln]
    assert serve == ["ThreadingHTTPServer((host, port), _Handler).serve_forever()"], serve


# ── 비싼 것만 줄 세우는가 ──────────────────────────────────────────────────

def test_generation_is_serialised_by_default():
    """기본 1 — 오늘 동작 그대로다. 스레드를 늘렸다고 `claude` 를 동시에 띄우지 않는다."""
    assert bridge._MAX_CONCURRENT == 1


def test_a_queued_request_is_told_it_queued_not_that_it_was_slow():
    """⛔ 조용히 더 기다리게 하면 부르는 쪽은 자기 벽에서 죽고 그것을 *"합성이 느리다"* 로
    읽는다. 줄 선 것과 느린 것은 다른 사건이고 처방이 다르다."""
    holder = threading.Thread(
        target=bridge.handle_generate,
        args=({"prompt": "q"}, None),
        kwargs={"runner": _slow_runner(1.5), "token": "", "timeout": 5.0},
        daemon=True)
    holder.start()
    time.sleep(0.3)                                   # 앞 건이 문을 잡을 시간

    status, body = bridge.handle_generate(
        {"prompt": "q2"}, None, runner=_slow_runner(0), token="", timeout=0.2)
    holder.join(timeout=5)

    assert status == 503, "줄 선 것이 503 이 아니면 부르는 쪽이 느림으로 읽는다"
    assert "줄 선 것" in body["error"]
    assert "NEXUS_LLM_BRIDGE_CONCURRENCY" in body["error"], "어디를 고치는지가 없다"


def test_the_gate_is_released_even_when_the_run_fails():
    """⛔ **가장 조용한 실패.** 실패 경로에서 안 놓으면 브리지가 영원히 「다른 합성 중」이다 —
    한 건의 타임아웃이 브리지째 데려가는 것과 결과가 같아진다."""
    def boom(argv, prompt, timeout):
        raise OSError("claude 없음")

    before = bridge._GATE._value                                    # noqa: SLF001
    status, _ = bridge.handle_generate({"prompt": "q"}, None, runner=boom, token="")
    assert status == 502
    assert bridge._GATE._value == before, "실패 경로가 문을 안 놓았다"    # noqa: SLF001


def test_the_gate_is_released_after_a_timeout():
    """타임아웃이 바로 그 사건이다 — 설명 층이 본 순서가 타임아웃 둘 뒤였다."""
    import subprocess

    def slow(argv, prompt, timeout):
        raise subprocess.TimeoutExpired(argv, timeout)

    before = bridge._GATE._value                                    # noqa: SLF001
    status, _ = bridge.handle_generate({"prompt": "q"}, None, runner=slow, token="")
    assert status == 504
    assert bridge._GATE._value == before, "타임아웃이 문을 안 놓았다"      # noqa: SLF001


def test_both_paths_go_through_the_gate():
    """한쪽만 문을 쓰면 다른 쪽이 그 문을 무시하고 동시에 돈다."""
    import pathlib

    src = pathlib.Path(bridge.__file__).read_text(encoding="utf-8")
    assert src.count("_acquire_or_busy(timeout)") == 2
    assert src.count("_GATE.release()") == 2


def test_refused_before_the_gate_does_not_hold_it():
    """⚠ 인증 거절은 `claude` 를 안 부른다 — 문을 잡지도 말아야 한다."""
    before = bridge._GATE._value                                    # noqa: SLF001
    status, _ = bridge.handle_generate({"prompt": "q"}, "WRONG", token="secret")
    assert status == 403
    assert bridge._GATE._value == before
