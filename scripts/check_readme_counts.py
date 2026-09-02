"""`README.md` 가 주장하는 수가 실제와 같은가.

⛔ **왜 있나 (외부 평가 F4, 2026-09-02).** README 가 *"약 1,900 test functions · 17 CI jobs ·
10 ADRs · 49 SPECs"* 라고 적고 있었는데 실측은 **2,585 · 17 · 10 · 52** 였다. 손으로 미러링한
수는 반드시 낡는다.

**같은 사고를 이 리포가 이미 겪었다.** `OPEN.md` 의 미결 수를 손으로 증감시키다 틀렸고
(2026-09-02, 26 이라고 보고한 것이 실제로는 21), 그래서 `check_open_counts.py` 를 CI 에 걸었다.
**같은 보호가 README 에는 없었다** — 평가자가 그 비대칭을 정확히 지적했다.

세는 규칙은 여기 한 곳에만 있다. README 쪽 숫자를 고칠 때 이 파일도 같이 고치면 그 순간
사본이 둘이 되므로, **README 는 값을 적고 이 파일이 그 값을 검증**한다.

    python scripts/check_readme_counts.py
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def _test_functions() -> int:
    """`def test_*` 의 수. **CI 에서 실제로 도는 수와는 다르다**(스킵·마커 제외 등).

    README 도 그렇게 읽히도록 "run across" 가 아니라 개수만 말한다.
    """
    out = subprocess.run(
        ["git", "grep", "-hoE", r"^\s*(async )?def test_[a-zA-Z0-9_]+", "--", "*.py"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return len([ln for ln in out.stdout.splitlines() if ln.strip()])


def counts() -> dict[str, int]:
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    return {
        "tests": _test_functions(),
        "ci_jobs": len(re.findall(r"^  [a-z0-9-]+:$", ci, re.M)),
        "adrs": len(list((ROOT / "adr").glob("ADR-*.md"))),
        "specs": len(list((ROOT / "specs").glob("SPEC-*.md"))),
    }


#: README 에서 그 수를 읽어내는 자리. 문장을 바꾸면 여기도 바뀌어야 한다 —
#: 그러라고 이름이 붙어 있다.
PATTERNS = {
    "tests": r"([\d,]+)\s+test functions",
    "ci_jobs": r"(\d+)\s+CI jobs",
    "adrs": r"\((\d+)\s+ADRs",
    "specs": r"(\d+)\s+SPECs\)",
}


def claimed(text: str) -> dict[str, int | None]:
    out: dict[str, int | None] = {}
    for key, pat in PATTERNS.items():
        m = re.search(pat, text)
        out[key] = int(m.group(1).replace(",", "")) if m else None
    return out


def problems(text: str) -> list[str]:
    real, said = counts(), claimed(text)
    out = []
    for key, n in real.items():
        c = said[key]
        if c is None:
            out.append(f"{key}: README 에서 그 수를 못 찾았다 (문장이 바뀌었나)")
        elif c != n:
            out.append(f"{key}: README {c} != 실제 {n}")
    return out


def _say(line: str) -> None:
    """콘솔 코드페이지가 cp949 여도 죽지 않는다 — 검사기는 죽으면 아무것도 안 말한다."""
    try:
        print(line)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def main() -> int:
    bad = problems((ROOT / "README.md").read_text(encoding="utf-8"))
    if bad:
        _say("⛔ README 의 수가 실제와 다르다 — **세어서 고쳐라**")
        for b in bad:
            _say(f"   {b}")
        return 1
    _say("✓ README 의 수 일치 — " + " · ".join(f"{k} {v}" for k, v in counts().items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
