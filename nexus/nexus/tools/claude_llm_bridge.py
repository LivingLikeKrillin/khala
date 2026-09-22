"""claude-code LLM 브리지 (dev 전용) — SPEC-nexus-claude-code-llm-dev-backend.

Nexus(컨테이너)의 LLMService(provider=claude-code)가 HTTP 로 이 브리지를 부르면, 브리지는 호스트에
이미 인증된 `claude`를 headless(`-p`)로 돌려 서술을 만든다. 유료 키·청구 없음.

**보안(§5, load-bearing):** Nexus 는 문서 내용을 프롬프트에 넣고, 문서는 injection 을 담을 수 있다.
그래서 `claude`를 **모든 문이 닫힌** 순수 텍스트 완성으로만 부른다:
  --allowed-tools ""      빌트인 툴 전면 금지(빈 allowlist = deny-all, print 모드엔 승인이 없음)
  --strict-mcp-config     사용자 전역 MCP 서버 무시(툴 유입 차단)
  --setting-sources ""    프로젝트/유저 세팅·훅·스킬·CLAUDE.md 미로드
  --no-session-persistence  프롬프트(=문서 내용)를 ~/.claude 트랜스크립트에 안 남김

⛔ **`--setting-sources ""` 는 CLAUDE.md 를 막지 못한다** (실측 2026-09-20). 그 줄은 오래
막는다고 적혀 있었고 아니었다 — 프로젝트 맥락은 **작업 디렉터리**로 들어온다. 그래서
`claude` 는 빈 디렉터리에서 돈다(`neutral_cwd`). 그 자리의 실측은 거기 주석에 있다.

**dev 전용.** 호스트 `claude`+인증이 필요해 서버 백엔드가 아니다. 팀/프로덕션 compose 에 넣지 않는다.

실행:
    python -m nexus.tools.claude_llm_bridge      # `nexus/.env` 를 읽는다 (아래)

⛔ **이 프로세스는 `nexus/.env` 를 스스로 읽는다** (2026-09-20 신설). 앞서는 안 읽었고,
그 사이 `providers/llm.py` 는 *"두 프로세스가 같은 `.env` 를 읽지만 각자 기동할 때 읽는다"*
고 적고 있었다 — **한쪽이 아예 안 읽는 것은 그 문장이 그리는 그림이 아니다.** 실제로 벽이
갈렸다: 앱은 `.env` 의 420 을, 브리지는 기본 120 을 들고 돌았고 작은 쪽이 이긴다.
이미 환경에 있는 값이 이긴다 — 파일은 **비어 있는 칸만** 채운다.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import tempfile
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
#: `.env` 에서 **이것으로 시작하는 것만** 가져온다.
#:
#: ⛔ **왜 좁히나 (실측 2026-09-22).** 처음에는 파일 전체를 `os.environ` 에 부었다(#529).
#: 그 파일에는 `ANTHROPIC_API_KEY` 가 있고, `subprocess.run` 은 기본으로 부모 환경을
#: 물려주므로 **유료 키가 키리스 백엔드의 자식에게 그대로 넘어갔다.** `claude` 가 그것을
#: 보고 거부했다:
#:
#:     claude.ai connectors are disabled because ANTHROPIC_API_KEY or another auth
#:     source is set and takes precedence over your claude.ai login
#:
#: ⛔ **거부가 우리를 구했다.** 받아들였으면 「돈을 쓰지 않는다」가 조용히 깨진 채로 돌았다
#: (`nexus/CLAUDE.md`). 이 브리지의 정체가 **키 없이 도는 것**이므로, 키가 근처에 오는 길을
#: 여기서 끊는다.
#:
#: ⭐ 브리지가 읽는 환경 변수는 전부 이 접두사다(`TIMEOUT`·`CONCURRENCY`·`QUEUE_WAIT`·
#: `TOKEN`·`HOST`·`PORT`). 그래서 좁혀도 잃는 것이 없다.
ENV_PREFIX = "NEXUS_LLM_BRIDGE_"

#: 자식에게 **절대 물려주지 않는** 것. 접두사 규칙과 별개로 한 겹 더 건다 — 파일이 아니라
#: **띄운 셸**이 들고 있어도 같은 일이 난다. 이 브리지는 무엇을 물려받았든 키 없이 돈다.
BLOCKED_CHILD_ENV = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                     "CLAUDE_CODE_OAUTH_TOKEN", "GEMINI_API_KEY", "OPENAI_API_KEY")


def child_env() -> dict[str, str]:
    """`claude` 에게 줄 환경. **유료 인증 자료를 뺀다.**"""
    return {k: v for k, v in os.environ.items() if k not in BLOCKED_CHILD_ENV}


def _load_env_file() -> str | None:
    """`nexus/.env` 의 **브리지 몫만** 가져와 비어 있는 환경 변수를 채운다. 그 경로를 돌려준다.

    ⛔ **이미 있는 값을 덮지 않는다.** 셸이나 compose 가 준 값이 파일보다 세다 — 그 반대로
    만들면 운영자가 한 번 지정한 것을 파일이 조용히 되돌린다.

    ⛔ **파일 전체를 붓지 않는다.** `ENV_PREFIX` 머리말을 보라 — 처음 판이 그렇게 했다가
    유료 키를 키리스 백엔드에 넘겼다.

    ⚠ **`_DEFAULT_TIMEOUT` 보다 먼저 돌아야 한다.** 그 상수는 import 시점에 한 번 읽히므로,
    뒤에 두면 파일을 읽고도 옛 기본값으로 굳는다.
    """
    path = pathlib.Path(__file__).resolve().parents[2] / ".env"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key.startswith(ENV_PREFIX):
            os.environ.setdefault(key, val.strip())
    return str(path)


#: `_load_env_file()` 이 실제로 읽은 경로. `main()` 이 채운다.
#:
#: ⛔ **import 시점에 읽지 않는다** (2026-09-20, 내가 그렇게 만들었다가 되돌렸다).
#: 모듈을 들여오는 것만으로 `os.environ` 이 바뀌면 그 프로세스의 **다른 모든 것**이 같이
#: 바뀐다 — 실제로 검사 셋이 깨졌다(임베딩 세대가 `.env` 값으로 넘어가 배포 대조군과
#: span 게이트가 다른 세대를 보게 됐다). 이 리포는 그 모양에 이미 데였다(#503).
#: `.env` 는 **프로그램으로 돌 때**만 읽는다.
ENV_FILE: str | None = None

#: 기본 벽. 이 상수는 **문서화된 기본값**이고 `.env` 와 무관하다 — 그 사실을
#: `test_bridge_timeout_is_configurable` 이 고정한다.
_DEFAULT_TIMEOUT = float(os.getenv("NEXUS_LLM_BRIDGE_TIMEOUT", "120") or 120)


def current_timeout() -> float:
    """지금 이 순간의 벽. **호출 시점에 읽는다.**

    ⛔ `main()` 이 `.env` 를 읽은 뒤에 요청이 오므로, 모듈 상수로 굳히면 파일을 읽고도
    옛 값으로 돈다. 그 갈림은 조용하고 504 가 날 때까지 안 보인다 — 실제로 앱 420 ·
    브리지 120 으로 갈려 돌았다.
    """
    raw = os.getenv("NEXUS_LLM_BRIDGE_TIMEOUT")
    return float(raw) if raw else _DEFAULT_TIMEOUT


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




#: `claude` 를 돌릴 **빈 디렉터리**. 프로세스의 작업 디렉터리가 곧 프로젝트 맥락이다.
#:
#: ⛔ **이 자리가 모든 키리스 측정을 오염시키고 있었다 (실측 2026-09-20).** 이 모듈 머리말은
#: `--setting-sources ""` 가 *"프로젝트/유저 세팅·훅·스킬·CLAUDE.md 미로드"* 라고 적어 뒀는데,
#: **CLAUDE.md 는 막히지 않는다.** 같은 argv 로 작업 디렉터리만 바꿔 대조했다:
#:
#:     리포 안에서   "이 저장소에서 specledger 의 새 이름은?"  →  "Arbiter"
#:     중립 디렉터리                     같은 질문            →  "모른다"
#:
#:     리포 안에서   "당신은 무엇인가?"  →  "khala/nexus 저장소에서 … 작업 중인 세션"
#:     중립 디렉터리        같은 질문     →  "터미널에서 작업을 돕는 AI 에이전트"
#:
#: ⚠ **왜 이것이 측정을 움직이나.** 이 리포의 `CLAUDE.md` 는 *"grounded answers only · 추측
#: 금지"* · *"System decides, LLM narrates"* 를 적고 있다. 그 문장을 들고 도는 모델은 우리가
#: **재려는 바로 그 축**(환각·인용 규율)에서 더 잘한다. 즉 키리스 브리지로 낸 답변 품질
#: 수치는 그만큼 낙관 쪽으로 기울어 있었고, 유료 키로 도는 배포에는 그 맥락이 없다.
#:
#: ⛔ 도구는 원래부터 전부 닫혀 있다(`_DOORS_CLOSED`). 그러므로 이 디렉터리에서 무언가를
#: 읽을 수는 없다 — 여기서 막는 것은 **읽기가 아니라 맥락 주입**이다.
_NEUTRAL_CWD = os.path.join(tempfile.gettempdir(), "nexus-bridge-cwd")


def neutral_cwd() -> str:
    """`claude` 를 돌릴 자리. 만들 수 없으면 시스템 임시 디렉터리로 물러선다.

    ⚠ **리포 안으로는 절대 물러서지 않는다** — 물러선 자리가 맥락을 주면 이 함수는 아무
    일도 안 한 것이 된다.
    """
    try:
        os.makedirs(_NEUTRAL_CWD, exist_ok=True)
        return _NEUTRAL_CWD
    except OSError:
        return tempfile.gettempdir()


def _subprocess_runner(argv: list[str], prompt: str, timeout: float):
    """argv 를 실행하고 (returncode, stdout, stderr) 반환. 타임아웃은 예외로.

    Windows cp949 는 프롬프트의 em-dash 를 못 쓰므로 파이프를 UTF-8 로 고정한다.

    ⛔ **`cwd` 를 반드시 넘긴다.** 안 넘기면 브리지를 띄운 셸의 위치를 물려받고, 이 배포에서
    그 자리는 리포 안이다 (위 `_NEUTRAL_CWD` 의 실측).

    ⛔ **`env` 도 반드시 넘긴다.** 안 넘기면 부모 환경을 통째로 물려받고, 거기에 유료 키가
    있으면 **키리스 백엔드가 키로 돈다** (`BLOCKED_CHILD_ENV` 머리말의 실측).
    """
    p = subprocess.run(
        argv, input=prompt, capture_output=True, text=True,
        encoding="utf-8", timeout=timeout, cwd=neutral_cwd(), env=child_env(),
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
    timeout: float | None = None,
) -> tuple[int, dict]:
    """POST /v1/generate 의 순수 로직. (status, body) 반환. 서버/소켓과 분리해 단위 테스트한다."""
    timeout = current_timeout() if timeout is None else timeout
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
    timeout: float | None = None,
) -> tuple[int, dict]:
    """POST /v1/vision 의 순수 로직. (status, body)."""
    timeout = current_timeout() if timeout is None else timeout
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
    # ⛔ **여기서 읽는다, import 에서가 아니다** (위 `ENV_FILE` 주석). 그리고 토큰 검사보다
    #    먼저다 — 토큰도 이 파일에 있으므로, 뒤에 두면 파일이 있는데도 시동을 거부한다.
    global ENV_FILE
    ENV_FILE = _load_env_file()
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
    # ⛔ **벽을 시동에서 말한다.** 안 적혀 있던 동안, 다른 값으로 도는 브리지가 조용히 섰고
    #    그 사실은 504 가 날 때까지 아무 데도 안 보였다 (실측 2026-09-20: 앱 420 · 브리지 120).
    _say(f"  생성 벽 {current_timeout():g}초 "
         f"({'nexus/.env' if ENV_FILE else '환경변수/기본값'}) · "
         f"작업 디렉터리 {neutral_cwd()}")
    # ⛔ **키가 근처에 있었는지도 시동에서 말한다.** 안 적혀 있던 동안, 유료 키가 자식에게
    #    넘어가 `claude` 가 거부했고 밖에서는 「생성이 즉시 죽는다」로만 보였다(2026-09-22).
    _stripped = [k for k in BLOCKED_CHILD_ENV if k in os.environ]
    _say(f"  자식 환경에서 뺀 인증 자료 {len(_stripped)}건"
         f"{' — ' + ', '.join(_stripped) if _stripped else ' (환경에 없었다)'}")
    ThreadingHTTPServer((host, port), _Handler).serve_forever()


if __name__ == "__main__":
    main()
