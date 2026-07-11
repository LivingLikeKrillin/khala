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
from http.server import BaseHTTPRequestHandler, HTTPServer

# 문 닫기 플래그 — §5 의 계약. 순서·값이 test_claude_llm_bridge 로 고정된다.
_DOORS_CLOSED = [
    "--allowed-tools", "",
    "--strict-mcp-config",
    "--setting-sources", "",
    "--no-session-persistence",
]
_DEFAULT_TIMEOUT = 120.0


def build_argv(model: str | None) -> list[str]:
    """claude headless 호출 argv. 항상 모든 문이 닫힌 순수 텍스트 완성."""
    argv = ["claude", "-p", "--output-format", "text", *_DOORS_CLOSED]
    if model:
        argv += ["--model", model]
    return argv


def _subprocess_runner(argv: list[str], prompt: str, timeout: float):
    """argv 를 실행하고 (returncode, stdout, stderr) 반환. 타임아웃은 예외로.

    Windows cp949 는 프롬프트의 em-dash 를 못 쓰므로 파이프를 UTF-8 로 고정한다.
    """
    p = subprocess.run(
        argv, input=prompt, capture_output=True, text=True,
        encoding="utf-8", timeout=timeout,
    )
    return (p.returncode, p.stdout, p.stderr)


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
    try:
        rc, out, err = runner(argv, full, timeout)
    except (subprocess.TimeoutExpired, TimeoutError):
        return 504, {"error": "claude 응답이 시간 초과되었습니다"}
    except OSError as e:
        # claude 미설치/실행 불가 등 — 크래시 대신 502 로 원인을 알린다.
        return 502, {"error": f"claude 실행 실패: {e}"}
    if rc != 0:
        return 502, {"error": (err or "claude non-zero exit")[:1000]}
    return 200, {"text": out}


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
        if self.path.rstrip("/") != "/v1/generate":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            # 손상/비-UTF-8 본문은 400 으로 — 핸들러가 크래시하지 않는다.
            self._send(400, {"error": "malformed or non-UTF-8 JSON body"})
            return
        status, body = handle_generate(
            payload, self.headers.get("X-Bridge-Token"), token=self.token)
        self._send(status, body)

    def log_message(self, *args) -> None:  # 토큰·프롬프트가 접근 로그로 새지 않게 침묵
        return


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
    print(f"claude-code LLM 브리지: http://{host}:{port}/v1/generate  (dev 전용, 툴 전면 차단)")
    HTTPServer((host, port), _Handler).serve_forever()


if __name__ == "__main__":
    main()
