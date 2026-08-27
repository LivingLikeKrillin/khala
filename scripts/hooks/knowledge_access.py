"""에이전트가 **조직 지식**을 어디서 가져갔는지 센다 — khala 를 통해서인가, 우회해서인가.

**왜 있나.** 2026-08-26 에 확인한 것: khala 의 모든 문(슬랙·A2A·MCP)이 두 달간 0에 가까웠고,
그 사이 이 리포에서 조직 지식을 실제로 꺼내 쓴 소비자는 **에이전트 하나**였다. 그런데 그
에이전트는 코퍼스 DB 와 `grep` 으로 갔다. 문이 있는데 안 쓴 게 아니라 **부를 방법이 없었다.**

문을 열었으면(`CLAUDE.md` 의 계약) 그 다음 질문은 하나다 — **실제로 그 문으로 가는가.**
그것을 자기 보고로 세면 자기 채점이 된다. 그래서 도구 호출을 그대로 센다.

    분자  khala 를 통해 간 횟수
    분모  분자 + 우회(조직 코퍼스 DB · 팀 코드 트리를 직접 뒤진 횟수)

**막지 않는다.** 언제나 exit 0 이고, 판정이 틀려도 작업은 그대로 간다. 세는 것이 전부다.

⚠ **명령 원문을 남기지 않는다.** 질의문에는 조직 어휘가 들어간다(이 리포는 public 이다).
남기는 것은 분류와 12자 해시뿐이고, 기록 파일 자체도 gitignore 된다.

**값싸야 한다.** 이 훅은 **모든** 도구 호출 앞에 선다. 실측(2026-08-27): 실제 일은 0 ms 에
가깝고 값은 전부 파이썬 부팅과 import 였다 — `pathlib` 하나가 30 ms, `json` 22 ms. 그래서
무거운 것은 전부 **셀 일이 있다고 판명된 뒤에** 부른다(`might_be_an_access`). 90 ms → 24 ms.
"""

from __future__ import annotations

import sys

#: 기록 파일. 문자열로 둔다 — `pathlib` 를 부르는 값(30 ms)이 이 훅 전체보다 크다.
_HERE = sys.modules[__name__].__file__ or __file__
LOG = None  # 아래에서 채운다 (테스트는 이 이름을 갈아 끼운다)

#: 배포가 팀 코드 트리를 어디에 두는지. `/code-src` 마운트의 **원본**이다.
_TREE_KEY = "CODE_SRC_PATH"

#: 값싼 선별에 쓰는 표식. **넉넉한 상위집합**이다 — 거짓 양성은 느릴 뿐이지만,
#: 거짓 음성은 정밀 분류기를 아예 안 부르게 만든다 = 조용히 안 세어진다.
_MARKERS = ("nexus.cli", "nexus query", "nexus_search", "nexus_answer",
            "/search/answer", "psql", "nexus-db", "/code-src")


def _root() -> str:
    import os
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(_HERE))))


def _log_path():
    if LOG is not None:
        return LOG
    import os
    return os.path.join(_root(), ".khala", "knowledge-access.jsonl")


def _squash(text: str) -> str:
    """슬래시를 지우고 소문자로. 원문은 아직 JSON 이라 Windows 경로의 역슬래시가
    `\\\\` 로 이스케이프돼 있다 — 방향도 겹침도 여기서 없앤다."""
    return text.replace("\\", "").replace("/", "").lower()


def might_be_an_access(raw: str, tree: str | None) -> bool:
    """**디코드하기 전에** 한 번 거른다. 대부분의 호출은 여기서 끝난다.

    이 선별은 정확할 필요가 없다 — 정확한 판정은 뒤의 `classify` 가 한다. 여기서 필요한
    성질은 하나뿐이다: **진짜 접근을 놓치지 않을 것.**
    """
    squashed = _squash(raw)
    if any(_squash(m) in squashed for m in _MARKERS):
        return True
    return bool(tree) and _squash(tree) in squashed


def host_code_tree(env_file=None) -> str | None:
    """팀 코드 트리의 **호스트 경로**.

    이 리포는 public 이라 경로를 박아 넣을 수 없고(조직명·개인 경로가 들어간다), 배포마다
    다르다. 그래서 배포가 **이미 갖고 있는 값**을 읽는다 — `nexus/.env` 의 `CODE_SRC_PATH`
    는 컨테이너 `/code-src` 마운트가 가리키는 바로 그 경로다.

    트리를 안 붙인 배포도 있다. 그때는 **그 축을 안 세는 것**이지 죽는 게 아니다.
    """
    if env_file is None:
        import os
        from_env = os.environ.get(_TREE_KEY, "").strip()
        if from_env:
            return from_env
        env_file = os.path.join(_root(), "nexus", ".env")
    try:
        with open(env_file, encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if line.startswith(_TREE_KEY + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


def _subject(tool_input: dict) -> str:
    """무엇을 대고 분류하는가. **우회는 셸을 안 지나도 일어난다** — Grep·Read 도 트리를 연다.

    검색 **패턴**은 일부러 안 읽는다. 리포 안에서 문 이름을 **문자열로 찾는 것**은 문을
    지난 게 아닌데, 패턴을 읽으면 그게 분자로 들어가 비율이 좋은 쪽으로 거짓이 된다.
    읽는 것은 명령과 **경로**뿐이다.
    """
    return (tool_input.get("command")
            or tool_input.get("file_path")
            or tool_input.get("path")
            or "")


def _same_tree(cmd: str, tree: str) -> bool:
    """명령이 그 트리를 건드리는가. 호스트가 Windows 라 슬래시도 대소문자도 섞여 온다."""
    def norm(t: str) -> str:
        return t.replace("\\", "/").lower()

    return norm(tree) in norm(cmd)


def classify(cmd: str, code_src: str | None = None) -> str | None:
    """`code_src` = **호스트에서의** 팀 코드 트리 경로.

    우회 패턴의 `/code-src` 는 컨테이너 마운트 지점이다 — 에이전트는 호스트에서 도니까
    그것만으로는 이 계수기가 잡으려던 우회를 못 본다. 경로는 배포마다 다르고 이 리포는
    public 이라 박아 넣을 수 없다 → 설정에서 온다(`host_code_tree`).
    """
    if not cmd:
        return None
    import re

    #: khala 를 통해 간 것. CLI·MCP·HTTP 어느 문이든 이 이름을 지난다.
    if re.search(r"nexus\.cli\s+query|nexus\s+query|nexus_search|nexus_answer|/search/answer",
                 cmd):
        return "khala"
    #: 우회 — 조직 지식을 **직접** 뒤진 것. 코퍼스가 사는 DB 를 직접 치거나, 팀 코드
    #: 트리를 뒤지거나. khala 자신의 코드를 뒤지는 것은 우회가 아니다 — `grep` 의 자리다.
    if re.search(r"psql\b.*\bnexus\b|nexus-db\b|/code-src\b", cmd):
        return "bypass"
    if code_src and _same_tree(cmd, code_src):
        return "bypass"
    return None


def _say(line: str) -> None:
    """콘솔 코드페이지가 cp949 여도 죽지 않는다. **훅은 죽으면 조용히 아무것도 안 센다.**"""
    try:
        print(line)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def report() -> int:
    """지금까지의 비율.

    **분모가 작으면 비율을 말하지 않는다** — 3건에서 나온 0.33 은 수가 아니다.
    """
    import json
    import os

    path = _log_path()
    if not os.path.exists(path):
        _say("기록 없음 — 훅이 아직 한 번도 안 걸렸다 (또는 조직 지식을 안 꺼냈다)")
        return 0
    with open(path, encoding="utf-8") as f:
        rows = [json.loads(ln) for ln in f.read().splitlines() if ln.strip()]
    khala = sum(1 for r in rows if r["kind"] == "khala")
    bypass = sum(1 for r in rows if r["kind"] == "bypass")
    n = khala + bypass
    _say(f"  조직 지식 접근 {n}건 — khala {khala} · 우회 {bypass}")
    if n < 10:
        _say("  비율은 내지 않는다 (표본 10건 미만).")
    else:
        _say(f"  **khala 경유 {khala / n:.2f}**")
    if rows:
        _say(f"  기간: {rows[0]['ts']} ~ {rows[-1]['ts']}")
    return 0


def _read_stdin() -> str:
    """⚠ **파이프는 UTF-8 이 아니다.** 훅의 stdin 은 콘솔 코드페이지로 열린다(실측
    2026-08-27, 한국어 Windows: `cp949` · `surrogateescape`). 그냥 `sys.stdin.read()` 로
    읽으면 한글이 든 질의가 서러게이트를 물고 들어와 해시 자리에서 터지고, **문을 지난
    호출만 골라서** 안 세어진다 — 우회 쪽은 대개 경로뿐이라 ASCII 로 살아남기 때문이다.
    그래서 바이트로 받아 UTF-8 로 푼다. (테스트가 갈아 끼우는 `StringIO` 에는 `buffer`
    가 없다. `terms_guard.py` 가 하루 먼저 배운 것과 같은 처방이다.)
    """
    buf = getattr(sys.stdin, "buffer", None)
    return buf.read().decode("utf-8", "replace") if buf is not None else sys.stdin.read()


def main() -> int:
    if "--report" in sys.argv[1:]:
        return report()
    raw = _read_stdin()
    tree = host_code_tree()
    if not might_be_an_access(raw, tree):
        return 0

    import hashlib
    import json
    import os
    from datetime import datetime, timezone

    try:
        payload = json.loads(raw)
    except Exception:
        return 0
    cmd = _subject(payload.get("tool_input") or {})
    kind = classify(cmd, code_src=tree)
    if kind is None:
        return 0
    path = _log_path()
    os.makedirs(os.path.dirname(str(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "cmd_sha": hashlib.sha256(cmd.encode("utf-8")).hexdigest()[:12],
        }, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
