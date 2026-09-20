"""브리지가 **자기 시작 문구 때문에** 죽지 않는다.

⛔ **왜 생겼나 (실측 2026-09-20).** 브리지를 무인으로 띄우려다 이것에 걸렸다:

    UnicodeEncodeError: 'cp949' codec can't encode character '\\u2014'
      File ".../claude_llm_bridge.py", line 323, in main
        print(f"  동시 실행 한도 {_MAX_CONCURRENT} — 소켓은 …")

`main()` 이 `serve_forever` 에 **닿기 전에** 끝난다. 포트는 안 열리고, 로그 한 줄이 서버를
못 띄운다.

⚠ **가장 늦게 발견되는 부류다** — 대화형 콘솔에서는 안 나기도 해서, 손으로 띄우면 멀쩡하고
무인으로 띄우면 죽는다.

⭐ 이 리포는 같은 처방을 **이미 두 곳에** 갖고 있었다(`scripts/check_readme_counts.py::_say` ·
훅의 stdin 디코딩). 브리지만 빠져 있었다. 그래서 이 파일이 지키는 것은 함수 하나가 아니라
**그 처방이 여기에도 걸려 있다**는 사실이다.
"""

from __future__ import annotations

import io
import subprocess
import sys

import pytest

from nexus.tools import claude_llm_bridge as bridge


class _Cp949Stdout(io.TextIOBase):
    """cp949 콘솔 흉내 — 인코딩 못 하는 글자에서 `print` 가 터진다."""

    def __init__(self) -> None:
        self.buffer = io.BytesIO()

    def write(self, text: str) -> int:
        text.encode("cp949")          # 여기서 UnicodeEncodeError
        return len(text)


def test_the_banner_does_not_kill_the_process_on_a_cp949_console(monkeypatch):
    """⛔ 이 검사가 없어서 서버가 안 떴다."""
    fake = _Cp949Stdout()
    monkeypatch.setattr(sys, "stdout", fake)

    bridge._say("동시 실행 한도 1 — 소켓은 열어 두고 생성만 줄 세운다")

    assert fake.buffer.getvalue(), "대체 경로가 아무것도 안 썼다"
    assert "동시 실행 한도" in fake.buffer.getvalue().decode("utf-8")


def test_a_plain_console_still_gets_the_ordinary_print(monkeypatch):
    """대조군 — 인코딩이 되는 콘솔에서는 `print` 그대로다(바이트 경로로 안 샌다)."""
    written: list[str] = []

    class _Ok(io.TextIOBase):
        buffer = io.BytesIO()

        def write(self, text: str) -> int:
            written.append(text)
            return len(text)

    monkeypatch.setattr(sys, "stdout", _Ok())
    bridge._say("평범한 줄 — em-dash 포함")
    assert any("평범한 줄" in w for w in written)
    assert _Ok.buffer.getvalue() == b"", "되는 콘솔인데 대체 경로로 갔다"


def test_main_prints_through_the_guard_not_through_print():
    """⛔ **금지 단언은 호출을 겨눈다.**

    `main` 안에 맨 `print(` 가 남아 있으면 이 처방이 절반만 걸린 것이다. 부분 문자열로
    `"print"` 를 금지하면 주석·docstring 을 물으므로, 줄 단위로 **호출 모양**만 본다.
    """
    import inspect

    src = inspect.getsource(bridge.main)
    bare = [ln.strip() for ln in src.splitlines() if ln.strip().startswith("print(")]
    assert not bare, f"`main` 이 아직 맨 print 로 낸다: {bare}"


@pytest.mark.skipif(sys.platform != "win32", reason="cp949 콘솔은 이 기계의 사실이다")
def test_the_module_starts_under_a_cp949_pipe():
    """⭐ **끝까지 간다.** 단위가 아니라 실제 프로세스로, 실제 코드페이지로 확인한다.

    토큰 없이 띄우면 `main` 이 시동을 **거부**하는데(§5), 그 거부는 배너보다 앞이라
    지나왔다는 증거가 못 된다. 그래서 토큰은 주고 **서버만 대신 세운다** — 배너를 지나
    `serve_forever` 까지 가고, 거기서 곧장 돌아온다.

    ⛔ 포트를 막는 방식은 안 쓴다. 첫 판이 그렇게 했다가 포트가 **실제로 열려** 60초를
    기다렸다 — 시동을 확인하려는 검사가 시동에 성공해서 걸린 것이다.
    """
    code = (
        "import os, sys, io\n"
        "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='cp949')\n"
        "os.environ['NEXUS_LLM_BRIDGE_TOKEN'] = 'x'\n"
        "import nexus.tools.claude_llm_bridge as b\n"
        "class _S:\n"
        "    def __init__(self, *a, **k): pass\n"
        "    def serve_forever(self): print('SERVING')\n"
        "b.ThreadingHTTPServer = _S\n"
        "b.main()\n"
    )
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=60)
    combined = (p.stdout + p.stderr).decode("utf-8", "replace")
    assert "UnicodeEncodeError" not in combined, \
        f"배너에서 인코딩으로 죽는다:\n{combined[:400]}"
    assert "SERVING" in combined, \
        f"배너를 못 지나 `serve_forever` 에 닿지 못했다:\n{combined[:400]}"
