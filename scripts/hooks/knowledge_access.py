"""에이전트가 **조직 지식**을 어디서 가져갔는지 센다 — khala 를 통해서인가, 우회해서인가.

**왜 있나.** 2026-08-26 에 확인한 것: khala 의 모든 문(슬랙·A2A·MCP)이 두 달간 0에 가까웠고,
그 사이 이 리포에서 조직 지식을 실제로 꺼내 쓴 소비자는 **에이전트 하나**였다. 그런데 그
에이전트는 `psql` 과 `grep` 으로 갔다. 문이 있는데 안 쓴 게 아니라 **부를 방법이 없었다.**

문을 열었으면(`CLAUDE.md` 의 계약) 그 다음 질문은 하나다 — **실제로 그 문으로 가는가.**
그것을 자기 보고로 세면 자기 채점이 된다. 그래서 도구 호출을 그대로 센다.

    분자  khala 를 통해 간 횟수
    분모  분자 + 우회(조직 코퍼스 DB · 팀 코드 트리를 직접 뒤진 횟수)

**막지 않는다.** 언제나 exit 0 이고, 판정이 틀려도 작업은 그대로 간다. 세는 것이 전부다.

⚠ **명령 원문을 남기지 않는다.** 질의문에는 조직 어휘가 들어간다(이 리포는 public 이다).
남기는 것은 분류와 12자 해시뿐이고, 기록 파일 자체도 gitignore 된다.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG = Path(__file__).resolve().parents[2] / ".khala" / "knowledge-access.jsonl"

#: khala 를 통해 간 것. CLI·MCP·HTTP 어느 문이든 이 이름을 지난다.
_VIA_KHALA = re.compile(
    r"nexus\.cli\s+query|nexus\s+query|nexus_search|nexus_answer|/search/answer")

#: 우회 — 조직 지식을 **직접** 뒤진 것.
#:   · 조직 코퍼스가 사는 DB 를 psql 로 친다
#:   · 팀 코드 트리(`/code-src`)나 파트너 리포를 뒤진다
#: khala 자신의 코드·테스트를 뒤지는 것은 우회가 아니다 — 그건 `grep` 이 정확한 자리다.
_BYPASS = re.compile(r"psql\b.*\bnexus\b|nexus-db\b|/code-src\b")


def classify(cmd: str) -> str | None:
    if not cmd:
        return None
    if _VIA_KHALA.search(cmd):
        return "khala"
    if _BYPASS.search(cmd):
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
    if not LOG.exists():
        _say("기록 없음 — 훅이 아직 한 번도 안 걸렸다 (또는 조직 지식을 안 꺼냈다)")
        return 0
    rows = [json.loads(ln) for ln in LOG.read_text(encoding="utf-8").splitlines() if ln.strip()]
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


def main() -> int:
    if "--report" in sys.argv[1:]:
        return report()
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    cmd = ((payload.get("tool_input") or {}).get("command")) or ""
    kind = classify(cmd)
    if kind is None:
        return 0
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "kind": kind,
            "cmd_sha": hashlib.sha256(cmd.encode("utf-8")).hexdigest()[:12],
        }, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
