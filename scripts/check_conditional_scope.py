"""`OPEN.md` §4 가 **세는 대상 집합**을 놓치고 있지 않은가.

⛔ **왜 있나 (실측 2026-09-10).** §4 는 SPEC 안에 트리거가 적힌 조건부 잔여를 센다. 그 수는
`check_open_counts.py` 가 세는 §1·§2 와 달리 **표에 손으로 적은 SPEC 아홉 건**에서만 나온다.
그래서 새 SPEC 이 미해결 절을 달고 표에 안 들어가면 그 항목들은 **어디에도 안 세어진다** —
§4 머리말이 *"이것을 안 세면 다음 회차가 또 '안 봤다' 를 '없다' 로 읽는다"* 고 적어 둔
바로 그 사고가, 다른 자리에서 그대로 난다.

**항목의 수를 세지 않는다 — 집합을 센다.** 항목 단위 검사는 승인된 SPEC 본문에 표식을 달아야
하는데 그 본문은 승인 시점 바이트로 얼어 있다(A37). 그래서 이 검사기는 **어떤 SPEC 이 미해결
절을 갖고 있는가**만 보고, 그 전부가 `OPEN.md` 에서 처분됐는지 확인한다. 처분은 둘 중 하나다 —
§4 표에 줄이 있거나, 아래 선언 목록에 *어디서 세는지*와 함께 적혀 있거나.

⚠ **대조군 없이는 판정하지 않는다.** 미해결 절을 가진 SPEC 을 하나도 못 찾으면 그것은
*"전부 처분됐다"* 가 아니라 **패턴이 안 맞는 것**이다(제목 서식이 셋이다: `Open items` ·
`Open questions` · `미해결`). 그 경우 exit 76 으로 판정을 안 낸다.

    python scripts/check_conditional_scope.py
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
OPEN_MD = ROOT / "OPEN.md"

#: 미해결 절의 제목. 서식이 셋인 것은 사실이고, 하나로 통일하려면 얼어 있는 본문을 고쳐야 한다.
SECTION = re.compile(r"^##\s+\d+\.\s+(Open items|Open questions|미해결)\s*$")

#: §4 표에서 SPEC 이름을 읽는 자리. 표의 첫 칸은 `SPEC-nexus-` 접두어를 뗀 이름이다.
TABLE_ROW = re.compile(r"^\|\s*([a-z0-9][a-z0-9-]+)\s*\|\s*(\d+)\s*\|")

#: 표 밖에서 처분됐다고 선언하는 자리. `- <이름> — <어디서 세는가>`
DECLARED = re.compile(r"^-\s+`(SPEC-[a-z0-9-]+)`\s+—\s+(\S.*)$")


def specs_with_open_sections() -> set[str]:
    """미해결 절을 가진 SPEC 파일 이름."""
    out = set()
    for p in sorted(SPECS.glob("SPEC-*.md")):
        for line in p.read_text(encoding="utf-8").splitlines():
            if SECTION.match(line.strip()):
                out.add(p.name)
                break
    return out


def _section_4(text: str) -> list[str]:
    lines = text.splitlines()
    try:
        i = next(n for n, ln in enumerate(lines) if ln.startswith("## 4. 조건부 잔여"))
    except StopIteration:
        return []
    j = next((n for n, ln in enumerate(lines) if n > i and ln.startswith("## ")), len(lines))
    return lines[i:j]


def accounted(text: str) -> dict[str, str]:
    """`OPEN.md` §4 가 처분했다고 말하는 SPEC → 어디서 세는가."""
    out: dict[str, str] = {}
    for line in _section_4(text):
        m = TABLE_ROW.match(line)
        if m:
            out[f"SPEC-nexus-{m.group(1)}.md"] = "§4 표"
            continue
        d = DECLARED.match(line.strip())
        if d:
            out[f"{d.group(1)}.md"] = d.group(2).strip()
    return out


def problems(text: str, present: set[str]) -> list[str]:
    said = accounted(text)
    out = [f"{name}: 미해결 절이 있는데 §4 가 처분하지 않았다"
           for name in sorted(present - set(said))]
    out += [f"{name}: §4 가 처분했다고 적었는데 그런 SPEC 이 없다"
            for name in sorted(set(said) - present)]
    return out


def _say(line: str) -> None:
    """콘솔 코드페이지가 cp949 여도 죽지 않는다. **검사기는 죽으면 아무것도 안 말한다.**

    `check_open_counts.py` 와 같은 도우미다. 이 파일의 첫 판은 대체 경로를 ascii 로 적었고,
    실패를 보고하려는 바로 그 순간 `UnicodeEncodeError` 로 다시 죽었다.
    """
    try:
        print(line)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def main() -> int:
    present = specs_with_open_sections()
    if not present:
        # ⛔ 대조군. 빈 집합은 "없다" 가 아니라 "못 찾았다" 다.
        _say("⛔ 미해결 절을 가진 SPEC 을 하나도 못 찾았다 — 제목 서식이 바뀌었을 가능성이 높다.")
        _say("   판정하지 않는다. `SECTION` 정규식을 확인하라.")
        return 76
    bad = problems(OPEN_MD.read_text(encoding="utf-8"), present)
    if bad:
        _say("⛔ OPEN.md §4 가 세는 집합이 실제와 다르다 — "
             "**표에 줄을 넣거나, 어디서 세는지 선언하라**")
        for b in bad:
            _say(f"   {b}")
        return 1
    _say(f"✓ 미해결 절을 가진 SPEC {len(present)}건이 전부 §4 에서 처분됐다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
