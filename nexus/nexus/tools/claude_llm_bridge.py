"""claude-code LLM 브리지 (dev 전용) — SPEC-nexus-claude-code-llm-dev-backend.

Nexus(컨테이너)의 LLMService(provider=claude-code)가 HTTP 로 이 브리지를 부르면, 브리지는 호스트에
이미 인증된 `claude`를 headless(`-p`)로 돌려 서술을 만든다. 유료 키·청구 없음.

**보안(§5, load-bearing):** Nexus 는 문서 내용을 프롬프트에 넣고, 문서는 injection 을 담을 수 있다.
그래서 `claude`를 **모든 문이 닫힌** 순수 텍스트 완성으로만 부른다:
  --allowed-tools ""      빌트인 툴 전면 금지(빈 allowlist = deny-all, print 모드엔 승인이 없음)
  --strict-mcp-config     사용자 전역 MCP 서버 무시(툴 유입 차단)
  --setting-sources ""    프로젝트/유저 세팅·훅·스킬·CLAUDE.md 미로드
  --no-session-persistence  프롬프트(=문서 내용)를 ~/.claude 트랜스크립트에 안 남김

**dev 전용.** 호스트 `claude`+인증이 필요해 서버 백엔드가 아니다. 팀/프로덕션 compose 에 넣지 않는다.

실행:
    NEXUS_LLM_BRIDGE_TOKEN=<secret> python -m nexus.tools.claude_llm_bridge
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# 문 닫기 플래그 — §5 의 계약. 순서·값이 test_claude_llm_bridge 로 고정된다.
_DOORS_CLOSED = [
    "--allowed-tools", "",
    "--strict-mcp-config",
    "--setting-sources", "",
    "--no-session-persistence",
]
#: `claude` 한 번에 줄 시간(초). `NEXUS_LLM_BRIDGE_TIMEOUT` 로 배포가 정한다.
#:
#: ⛔ **상수 하나였고 그 사실이 아무 데도 안 적혀 있었다** (실측 2026-09-19). 설명 층이
#: 정황을 실으면서 질의가 길어지자 합성이 100~119초를 쓰게 됐고, 이 120 초 벽에 **호출
#: 셋 중 하나**가 걸렸다. 최대 성공 118.8초 · 최소 실패 121.0초 — 사이가 2.3초다.
#:
#: ⚠ **기본값은 그대로 120 이다.** 올려서 조용히 바꾸지 않는다 — 배포가 자기 값을 정하고,
#: 걸렸을 때 얼마나 기다렸는지를 504 가 말한다(아래). 느린 것을 벽을 올려 덮으면 느리다는
#: 사실만 안 보이게 된다.
#:
#: 참고로 이 배포의 내역(2026-09-19 실측): 검색 2.3초 · 합성 44.6초(답변 1,410자·근거 26).
#: 벽보다 먼저 볼 값은 **합성이 무엇에 그 시간을 쓰는가**다.
_DEFAULT_TIMEOUT = float(os.getenv("NEXUS_LLM_BRIDGE_TIMEOUT", "120") or 120)


def build_argv(model: str | None) -> list[str]:
    """claude headless 호출 argv. 항상 모든 문이 닫힌 순수 텍스트 완성."""
    argv = ["claude", "-p", "--output-format", "text", *_DOORS_CLOSED]
    if model:
        argv += ["--model", model]
    return argv


def build_vision_argv(model: str | None) -> list[str]:
    """이미지를 읽는 호출 argv. **문은 그대로 다 닫혀 있다.**

    이미지를 CLI 로 넘기는 통상 경로는 경로 + `Read` 툴인데, [[ADR-0010]] §6 이 그걸 금지한다 —
    추출은 quarantine 게이트 **앞**에서 공격자가 넣을 수 있는 바이트에 대해 돌기 때문에, 적재
    사용자가 읽을 수 있는 아무 경로나 여는 판독기는 유출 원시도구가 된다.

    `--input-format stream-json` 은 그 문을 열지 않고 이미지를 넣는다: stdin 으로 받는 JSON
    메시지의 content 블록에 base64 를 그대로 싣는다. 툴 정의가 없으니 부를 tool 도 없고,
    경로를 준 적이 없으니 열 파일도 없다.
    """
    argv = ["claude", "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json", "--verbose",
            *_DOORS_CLOSED]
    if model:
        argv += ["--model", model]
    return argv


def build_vision_stdin(system: str, image_b64: str, media_type: str) -> str:
    """stream-json 입력 한 줄. **이미지 하나, 그 외 아무것도 없다.**"""
    return json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "image",
         "source": {"type": "base64", "media_type": media_type, "data": image_b64}},
        {"type": "text", "text": system},
    ]}}, ensure_ascii=False) + "\n"


def parse_vision_stdout(out: str) -> str:
    """stream-json 출력에서 assistant 텍스트만 모은다. 나머지 이벤트는 버린다."""
    parts: list[str] = []
    for line in (out or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "assistant":
            for b in (ev.get("message") or {}).get("content") or []:
                if b.get("type") == "text":
                    parts.append(b.get("text") or "")
    return "".join(parts).strip()




def _subprocess_runner(argv: list[str], prompt: str, timeout: float):
    """argv 를 실행하고 (returncode, stdout, stderr) 반환. 타임아웃은 예외로.

    Windows cp949 는 프롬프트의 em-dash 를 못 쓰므로 파이프를 UTF-8 로 고정한다.
    """
    p = subprocess.run(
        argv, input=prompt, capture_output=True, text=True,
        encoding="utf-8", timeout=timeout,
    )
    return (p.returncode, p.stdout, p.stderr)


#: 동시에 도는 `claude` 프로세스 수. 기본 1 — **오늘 동작 그대로**다.
#:
#: ⛔ **왜 벽을 따로 두나 (실측 2026-09-19, 설명 층 보고).** 서버가 `HTTPServer` 였다.
#: 합성 한 건이 2분 도는 동안 **소켓이 다른 아무것도 받지 않는다** — 밖에서 건 `curl` 이
#: 그대로 타임아웃했다. 그리고 이 브리지를 부르는 것은 설명 층만이 아니다: 주기 재적재
#: (`nexus-reingest`)도 같은 문을 친다. 줄을 세우는 곳이 없으니 조용히 겹쳤다.
#:
#: `ThreadingHTTPServer` 로 받되 **생성은 이 문으로 줄 세운다.** 둘을 같이 하는 이유:
#: 스레드만 늘리면 `claude` 프로세스가 동시에 여럿 떠서 호스트를 갈아 넣고, 문만 두면
#: 소켓이 여전히 막힌다. 소켓은 열고, 비싼 것만 하나씩.
#:
#: ⚠ 기본을 1 에서 올리는 것은 **호스트 자원 판단**이다. 배포가 정한다.
_MAX_CONCURRENT = max(1, int(os.getenv("NEXUS_LLM_BRIDGE_CONCURRENCY", "1") or 1))
_GATE = threading.BoundedSemaphore(_MAX_CONCURRENT)

#: 문 앞에서 기다려 주는 시간(초).
#:
#: ⛔ **요청의 예산을 줄 서는 데 다 쓰면 안 된다** (실측 2026-09-19, 라이브에서 내 첫 판이
#: 그랬다). 처음엔 요청 자신의 `timeout` 만큼 기다렸는데, 그러면 앞 건이 2분 걸릴 때 뒤
#: 요청은 **자기 예산을 전부 대기에 쓰고 들어가서 남은 시간이 0** 이거나, 부르는 쪽이 자기
#: 벽에서 먼저 죽는다. 라이브 확인에서 둘째 요청이 503 대신 클라이언트 타임아웃으로 죽었다.
#:
#: 짧게 기다리고 **503 으로 돌려보내는 편이 낫다.** 줄이 길다는 사실은 그 자체로 정보이고,
#: 다시 시도하는 비용은 왕복 한 번이다. 동시 한도가 1 이고 합성이 2분이면 줄은 늘 길다.
_GATE_WAIT = max(0.0, float(os.getenv("NEXUS_LLM_BRIDGE_QUEUE_WAIT", "5") or 5))


def busy_detail(waited: float) -> str:
    """503 본문. **얼마나 기다렸고 왜 못 들어갔는지**를 말한다.

    ⛔ 조용히 더 기다리게 하면 부르는 쪽은 자기 벽에서 타임아웃으로 죽고, 그것을
    *"합성이 느리다"* 로 읽는다. 줄을 선 것과 느린 것은 다른 사건이고 처방도 다르다.
    """
    return (f"브리지가 다른 합성 중이라 {waited:.1f}초 기다렸고 못 들어갔다 "
            f"(동시 실행 한도 {_MAX_CONCURRENT}, NEXUS_LLM_BRIDGE_CONCURRENCY · "
            f"대기 한도 {_GATE_WAIT:g}초, NEXUS_LLM_BRIDGE_QUEUE_WAIT). "
            f"이것은 느린 것이 아니라 줄 선 것이다 — 다시 시도하면 된다")


def timeout_detail(limit: float) -> str:
    """504 본문. **얼마나 기다렸고 그 한계가 어디서 왔는지**를 같이 말한다.

    ⛔ 전에는 `"claude 응답이 시간 초과되었습니다"` 뿐이었다. 읽는 쪽은 자기가 121초에
    걸렸는지 300초에 걸렸는지 모르고, 그 수를 모르면 **기다릴지 질의를 줄일지** 를 못 정한다.
    #513 에서 502 가 이유를 버렸던 것과 같은 자리다 — 값은 있었고 전달이 없었다.
    """
    return (f"claude 가 {limit:g}초 안에 안 끝났다 "
            f"(한계는 NEXUS_LLM_BRIDGE_TIMEOUT, 기본 120). "
            f"질의를 줄이거나 이 값을 올려라 — 다만 합성이 그 시간을 쓰는 것 자체가 먼저 볼 값이다")


def failure_detail(out: str, err: str) -> str:
    """rc != 0 일 때 **왜** 인지를 고른다.

    ⛔ **stderr 만 보면 안 된다.** `claude` 는 치명적 사유를 **stdout** 으로 낸다. 실측
    2026-09-18: 호스트 OAuth 세션이 만료돼 `rc=1 · stderr='' ·
    stdout='Failed to authenticate: OAuth session expired and could not be refreshed'`
    였는데, 502 본문에는 `"claude non-zero exit"` 만 실렸다. 처방이 적힌 그 한 줄이
    버려져서, 읽는 쪽은 포트와 컨테이너와 네트워크를 먼저 뒤졌다.

    이 리포의 규율 그대로다 — 백엔드 메시지는 **요약하지 말고 그대로** 남긴다.
    "왜 안 되는지" 가 곧 처방이다 (`nexus/CLAUDE.md` §에러 처리).

    ⚠ 둘 다 비면 **비었다고 말한다.** "non-zero exit" 만 적으면 *이유를 못 받은 것*과
    *이유가 이것인 것*이 같은 문장이 된다.
    """
    for text in (err, out):
        s = (text or "").strip()
        if s:
            return s[:1000]
    return "claude 가 0 이 아닌 코드로 끝났고 stdout·stderr 가 둘 다 비어 있다"


def _acquire_or_busy(timeout: float) -> tuple[int, dict] | None:
    """생성 문에 들어간다. 못 들어가면 **503 을 돌려준다** — 조용히 더 기다리지 않는다.

    ⚠ 반환이 `None` 이면 들어간 것이고, **호출자가 `finally` 로 놓아야 한다.**
    """
    # ⚠ `timeout`(=`claude` 에 줄 시간)이 아니라 `_GATE_WAIT` 만큼만 기다린다. 위 ⛔ 참고.
    # 다만 요청이 그보다 짧게 참겠다면 그쪽을 따른다 — 검사가 짧은 값을 주는 자리다.
    wait = min(_GATE_WAIT, timeout)
    t0 = time.monotonic()
    if _GATE.acquire(timeout=wait):
        return None
    return 503, {"error": busy_detail(time.monotonic() - t0)}


def handle_generate(
    payload: dict,
    token_header: str | None,
    *,
    runner=_subprocess_runner,
    token: str = "",
    timeout: float = _DEFAULT_TIMEOUT,
) -> tuple[int, dict]:
    """POST /v1/generate 의 순수 로직. (status, body) 반환. 서버/소켓과 분리해 단위 테스트한다."""
    # 인증: 토큰이 설정돼 있으면 헤더가 일치해야 한다. 불일치면 claude 를 절대 부르지 않는다.
    if token and token_header != token:
        return 403, {"error": "forbidden: bad or missing X-Bridge-Token"}

    system = (payload.get("system") or "").strip()
    prompt = payload.get("prompt") or ""
    model = payload.get("model")
    full = f"{system}\n\n---\n\n{prompt}" if system else prompt

    argv = build_argv(model)
    gate = _acquire_or_busy(timeout)
    if gate is not None:
        return gate
    try:
        rc, out, err = runner(argv, full, timeout)
    except (subprocess.TimeoutExpired, TimeoutError):
        return 504, {"error": timeout_detail(timeout)}
    except OSError as e:
        # claude 미설치/실행 불가 등 — 크래시 대신 502 로 원인을 알린다.
        return 502, {"error": f"claude 실행 실패: {e}"}
    finally:
        _GATE.release()
    if rc != 0:
        return 502, {"error": failure_detail(out, err)}
    return 200, {"text": out}


def handle_vision(
    payload: dict,
    token_header: str | None,
    *,
    runner=_subprocess_runner,
    token: str = "",
    timeout: float = _DEFAULT_TIMEOUT,
) -> tuple[int, dict]:
    """POST /v1/vision 의 순수 로직. (status, body)."""
    if token and token_header != token:
        return 403, {"error": "forbidden: bad or missing X-Bridge-Token"}

    image_b64 = payload.get("image_b64") or ""
    if not image_b64:
        return 400, {"error": "image_b64 가 필요하다"}
    system = (payload.get("system") or "").strip()
    media_type = payload.get("media_type") or "image/png"

    argv = build_vision_argv(payload.get("model"))
    stdin = build_vision_stdin(system, image_b64, media_type)
    gate = _acquire_or_busy(timeout)
    if gate is not None:
        return gate
    try:
        rc, out, err = runner(argv, stdin, timeout)
    except (subprocess.TimeoutExpired, TimeoutError):
        return 504, {"error": timeout_detail(timeout)}
    except OSError as e:
        return 502, {"error": f"claude 실행 실패: {e}"}
    finally:
        _GATE.release()
    if rc != 0:
        return 502, {"error": failure_detail(out, err)}
    return 200, {"text": parse_vision_stdout(out)}


class _Handler(BaseHTTPRequestHandler):
    token = ""

    def _send(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:  # noqa: N802 — http.server 규약
        route = self.path.rstrip("/")
        if route not in ("/v1/generate", "/v1/vision"):
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            # 손상/비-UTF-8 본문은 400 으로 — 핸들러가 크래시하지 않는다.
            self._send(400, {"error": "malformed or non-UTF-8 JSON body"})
            return
        fn = handle_vision if route == "/v1/vision" else handle_generate
        status, body = fn(payload, self.headers.get("X-Bridge-Token"), token=self.token)
        self._send(status, body)

    def log_message(self, *args) -> None:  # 토큰·프롬프트가 접근 로그로 새지 않게 침묵
        return


def _say(line: str) -> None:
    """시작 문구를 **콘솔 코드페이지 때문에 죽지 않게** 낸다.

    ⛔ **이것 때문에 브리지가 시동에서 죽었다 (실측 2026-09-20).** 위 두 줄에 em-dash 가
    들어 있는데 이 기계의 기본 코드페이지는 `cp949` 라, stdout 이 파이프·리디렉션이면
    `UnicodeEncodeError` 가 나고 **`serve_forever` 에 닿기 전에** 프로세스가 끝난다.
    로그 한 줄이 서버를 못 띄우는 모양이다.

    ⚠ 대화형 콘솔에서는 안 나기도 한다 — 그래서 손으로 띄울 때는 멀쩡하고 무인으로
    띄우면 죽는, 가장 늦게 발견되는 부류가 된다.

    이 리포는 같은 처방을 이미 두 곳에 갖고 있다(`scripts/check_readme_counts.py` ·
    훅의 stdin 디코딩). 브리지만 빠져 있었다.
    """
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")
        sys.stdout.buffer.flush()


def main() -> None:
    # 토큰은 필수(§5). 무인증 + claude 실행이라 토큰 없이는 시동 거부한다.
    token = os.getenv("NEXUS_LLM_BRIDGE_TOKEN", "")
    if not token:
        raise SystemExit(
            "NEXUS_LLM_BRIDGE_TOKEN 이 필요합니다 — 무인증으로 claude 를 실행하는 브리지는 열지 않는다. "
            "임의의 시크릿을 정하고 Nexus 쪽 NEXUS_LLM_BRIDGE_TOKEN 과 같게 맞추세요.")
    # 기본은 로컬 루프백(§5: 0.0.0.0 아님). Nexus 컨테이너가 host.docker.internal 로 닿게 하려면
    # 운영자가 NEXUS_LLM_BRIDGE_HOST 를 도커 게이트웨이 인터페이스(또는 0.0.0.0)로 명시 설정한다 —
    # 그 경우에도 위 토큰이 방어선이다.
    host = os.getenv("NEXUS_LLM_BRIDGE_HOST", "127.0.0.1")
    port = int(os.getenv("NEXUS_LLM_BRIDGE_PORT", "8900"))
    _Handler.token = token
    _say(f"claude-code LLM 브리지: http://{host}:{port}/v1/generate  (dev 전용, 툴 전면 차단)")
    _say(f"  동시 실행 한도 {_MAX_CONCURRENT} — 소켓은 열어 두고 생성만 줄 세운다")
    ThreadingHTTPServer((host, port), _Handler).serve_forever()


if __name__ == "__main__":
    main()
