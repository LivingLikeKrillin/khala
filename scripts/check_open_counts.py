"""`OPEN.md` 의 미결 수가 **실제 항목 수와 같은가.**

⛔ **왜 있나 (실측 2026-09-02).** 그날 항목을 넷 닫고 셋 열면서 머리말의 수를 **손으로
증감**시켰다(23 → 24 → 26). 세어 보니 실제는 **21** 이었고 사람 쪽도 15 가 아니라 14 였다 —
닫힌 항목을 뺄 때 머리말을 안 고쳤기 때문이다. 그 수는 보고에 그대로 나갔고, 사용자가
*"26건이나 된다고?"* 라고 물어서야 드러났다.

이 파일이 존재하는 이유가 정확히 그것이다. `OPEN.md` 머리말은 *"미결이 줄고 있는지 늘고
있는지 아무도 몰랐다"* 를 고치려고 생겼는데, **그 수 자체를 손으로 미러링하고 있었다.**
손으로 미러링하는 목록은 전부 부패원이다.

세는 규칙은 파일의 규칙 그대로다: `~~A28~~` 처럼 취소선이 그어진 줄은 닫힌 것이라 안 센다.

    python scripts/check_open_counts.py
"""

from __future__ import annotations

import pathlib
import re
import sys

#: 항목 줄. 취소선(`~~A28~~`)은 닫힌 것이라 여기 안 걸린다 — 그것이 이 파일의 세는 규칙이다.
ITEM = re.compile(r"^\|\s*((?:H|A)\d+)\s*\|")
#: 요약 표의 두 줄과 절 제목 넷.
SUMMARY = {"H": re.compile(r"^\|\s*\*\*사람만 할 수 있는 것\*\*\s*\|\s*\*\*(\d+)\*\*"),
           "A": re.compile(r"^\|\s*\*\*내가 할 수 있는 것\*\*\s*\|\s*\*\*(\d+)\*\*")}
HEADING = {"H": re.compile(r"^## 1\. 사람만 할 수 있는 것 \((\d+)\)"),
           "A": re.compile(r"^## 2\. 내가 할 수 있는 것 \((\d+)\)")}


def counts(text: str) -> dict[str, int]:
    """절별로 **열려 있는** 항목 수."""
    out = {"H": 0, "A": 0}
    section = None
    for line in text.split("\n"):
        if line.startswith("## 1."):
            section = "H"
        elif line.startswith("## 2."):
            section = "A"
        elif line.startswith("## 3."):
            section = None
        m = ITEM.match(line)
        if section and m:
            out[section] += 1
    return out


def claimed(text: str) -> dict[str, list[int]]:
    """머리말이 **주장하는** 수. 요약 표와 절 제목 둘 다 — 둘이 갈리는 것도 결함이다."""
    out: dict[str, list[int]] = {"H": [], "A": []}
    for line in text.split("\n"):
        for key in ("H", "A"):
            for pat in (SUMMARY[key], HEADING[key]):
                m = pat.match(line)
                if m:
                    out[key].append(int(m.group(1)))
    return out


def problems(text: str) -> list[str]:
    real, said = counts(text), claimed(text)
    out = []
    for key, label in (("H", "사람만 할 수 있는 것"), ("A", "내가 할 수 있는 것")):
        if not said[key]:
            out.append(f"{label}: 머리말에 수가 없다 — 셀 대상을 못 찾았다")
            continue
        for n in said[key]:
            if n != real[key]:
                out.append(f"{label}: 머리말 {n} ≠ 실제 {real[key]}")
    return out


def _say(line: str) -> None:
    """콘솔 코드페이지가 cp949 여도 죽지 않는다. **검사기는 죽으면 아무것도 안 말한다.**

    이 리포의 훅이 같은 이유로 같은 도우미를 갖고 있다. 첫 판이 이 줄 없이 나갔고,
    실패를 보고하려는 바로 그 순간 `UnicodeEncodeError` 로 죽었다.
    """
    try:
        print(line)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def main() -> int:
    path = pathlib.Path(__file__).resolve().parent.parent / "OPEN.md"
    text = path.read_text(encoding="utf-8")
    bad = problems(text)
    if bad:
        _say("⛔ OPEN.md 의 미결 수가 실제와 다르다 — **증감시키지 말고 세어라**")
        for b in sorted(set(bad)):
            _say(f"   {b}")
        return 1
    real = counts(text)
    _say(f"✓ 미결 수 일치 — 사람 {real['H']} · 나 {real['A']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
