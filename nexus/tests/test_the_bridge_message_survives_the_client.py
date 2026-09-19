"""브리지가 만든 오류 문장이 호출자에게 **도착하는가**, 그리고 벽 둘 중 어느 쪽이 먼저 끊는가.

⛔ **실측 2026-09-19, 설명 층 보고.** 브리지는 504 본문에 *"claude 가 120초 안에 안 끝났다
(한계는 NEXUS_LLM_BRIDGE_TIMEOUT, 기본 120)"* 를 싣는다(#515). 그런데 호출자 로그에 남은 것은
`Server error '504 Gateway Timeout' for url …` 뿐이었다 — `resp.raise_for_status()` 가 httpx
일반 문구로 바꾸고 `resp.text` 를 버렸다. **#513 에서 고친 자리가 한 층 위에 그대로 있었다.**

⛔ **그리고 벽이 둘이었다.** `_BRIDGE_TIMEOUT = 180.0` 상수(앱→브리지)와
`NEXUS_LLM_BRIDGE_TIMEOUT`(브리지→claude, 기본 120). **작은 쪽이 이긴다.** 배포가 브리지 벽을
300 으로 올려도 앱이 180 에서 먼저 끊어 그 300 은 도달 불가였고, 그때는 브리지 문장도 안 온다
(클라이언트 타임아웃은 그 정보를 안 들고 있다). 설명 층이 *"벽이 두 번 옮겨졌는데 실패 건수는
안 줄었다"* 고 보고한 것이 이 자리다.
"""

from __future__ import annotations

import httpx
import pytest

from nexus.llm import failure as F
from nexus.providers import llm as P

_BRIDGE_504 = ("claude 가 300초 안에 안 끝났다 (한계는 NEXUS_LLM_BRIDGE_TIMEOUT, 기본 120). "
               "질의를 줄이거나 이 값을 올려라")
_BRIDGE_502 = "Failed to authenticate: OAuth session expired and could not be refreshed"


def _resp(status: int, body: str) -> httpx.Response:
    req = httpx.Request("POST", "http://host.docker.internal:8900/v1/generate")
    return httpx.Response(status, request=req, json={"error": body})


# ── 문장이 살아서 오는가 ───────────────────────────────────────────────────

def test_the_bridge_sentence_reaches_the_caller():
    """⛔ 이 검사가 이 단위의 이유다. 숫자가 없으면 121초에 걸렸는지 300초에 걸렸는지 모른다."""
    with pytest.raises(httpx.HTTPStatusError) as ei:
        P._raise_with_bridge_body(_resp(504, _BRIDGE_504))
    assert "300초" in str(ei.value)


def test_a_success_does_not_raise():
    P._raise_with_bridge_body(_resp(200, "ok"))          # 예외가 아니어야 한다


def test_the_exception_still_carries_status_and_response():
    """⛔ **`RuntimeError` 로 바꾸면 안 되는 이유.** `llm/failure.py` 가 `.response` 에서
    상태와 본문을 캐서 사유를 가른다(#516). 예외 종류를 바꾸면 그 분류가 통째로 `other` 다."""
    with pytest.raises(httpx.HTTPStatusError) as ei:
        P._raise_with_bridge_body(_resp(504, _BRIDGE_504))
    assert ei.value.response.status_code == 504


@pytest.mark.parametrize("status,body,reason", [
    (504, _BRIDGE_504, F.TIMEOUT),
    (502, _BRIDGE_502, F.AUTH),
    (502, "claude 실행 실패: [Errno 2]", F.UNAVAILABLE),
], ids=["timeout", "auth-in-body", "plain-5xx"])
def test_the_classifier_still_reads_it(status, body, reason):
    """⭐ 두 단위가 **같은 예외**에 기대고 있다 — 이 검사가 그 결합을 고정한다."""
    with pytest.raises(httpx.HTTPStatusError) as ei:
        P._raise_with_bridge_body(_resp(status, body))
    assert F.classify(ei.value) == reason


def test_neither_bridge_path_uses_raise_for_status():
    """한쪽만 고치면 다음 사람이 다른 쪽에서 같은 자리를 다시 밟는다."""
    import pathlib

    # ⚠ **부르는 것**을 금지해야지 **말하는 것**을 금지하면 안 된다. 파일 전체에서 문자열을
    # 찾으면 그 함수의 docstring(= 왜 그러면 안 되는지 적어 둔 곳)이 걸린다. 이 실수를 이
    # 세션에서 세 번 했다 — 호출부는 들여쓰기가 붙은 **문장**이라 그것으로 가른다.
    src = pathlib.Path(P.__file__).read_text(encoding="utf-8")
    calls = [ln for ln in src.splitlines() if ln.strip() == "resp.raise_for_status()"]
    assert not calls, f"브리지 경로가 아직 본문을 버린다: {calls}"
    assert src.count("_raise_with_bridge_body(resp)") == 2


# ── 벽 둘 중 어느 쪽이 먼저 끊는가 ─────────────────────────────────────────

def test_the_client_wall_is_looser_than_the_bridge_wall(monkeypatch):
    """⛔ 클라이언트가 먼저 끊으면 브리지 문장이 영영 안 온다."""
    monkeypatch.setenv("NEXUS_LLM_BRIDGE_TIMEOUT", "300")
    assert P._bridge_timeout() > 300.0


def test_the_client_wall_follows_the_bridge_wall(monkeypatch):
    """⚠ 두 수를 따로 적으면 반드시 어긋난다 — 실제로 180 과 120 으로 어긋나 있었다."""
    monkeypatch.setenv("NEXUS_LLM_BRIDGE_TIMEOUT", "90")
    tight = P._bridge_timeout()
    monkeypatch.setenv("NEXUS_LLM_BRIDGE_TIMEOUT", "600")
    assert P._bridge_timeout() > tight


def test_an_empty_value_is_the_default_not_zero(monkeypatch):
    """⛔ 0 이 되면 모든 합성이 즉시 죽는다. 빈 값은 "안 정했다" 이지 "0" 이 아니다."""
    monkeypatch.setenv("NEXUS_LLM_BRIDGE_TIMEOUT", "")
    assert P._bridge_timeout() == 120.0 + P._BRIDGE_HEADROOM


def test_the_client_wall_is_not_a_constant_any_more():
    import pathlib

    src = pathlib.Path(P.__file__).read_text(encoding="utf-8")
    assert "_BRIDGE_TIMEOUT = 180.0" not in src
    assert "timeout=_bridge_timeout()" in src
