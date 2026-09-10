"""달력에 걸린 트리거가 울렸는데 아무도 안 집었는가.

⛔ **왜 있나.** 이 리포는 울린 트리거를 놓친 적이 있다 — 2026-08-15 훑기가 H7 을 그렇게
찾아냈다(generation-of-record §8 이 트리거를 *"이 SPEC 이 승인된 직후"* 로 적어 뒀고, 승인은
이미 지나 있었다). 사람이 다시 읽어야만 보이는 트리거는 **읽을 때까지 안 울린 것과 구별되지
않는다.** 날짜로 울리는 것은 기계가 대신 볼 수 있다.

**날짜를 리포에서 긁어오지 않는다 — 선언을 읽는다.** SPEC 의 미해결 절에 있는 날짜 아홉 중
여덟은 *언제 측정했다*는 **기록**이고 트리거가 아니다(실측 2026-09-10). 긁어서 세면 그 여덟이
매번 붉어지고, 검사는 곧 꺼진다. 그래서 `OPEN.md` §4 가 어느 날짜가 트리거인지 선언하고,
이 검사기는 **그 선언이 SPEC 본문과 맞는지 확인한 다음** 날짜를 본다.

⚠ **선언한 날짜가 그 SPEC 에 없으면 판정하지 않는다(exit 76).** 선언과 본문이 갈리면 남은
것은 사본 하나이고, 사본을 근거로 초록을 내면 이 검사기가 막으려는 것을 스스로 한다.

    python scripts/check_dated_triggers.py

`--today YYYY-MM-DD` 로 그날을 가정해 돌릴 수 있다 — 이 검사에 이빨이 있는지 보려면
**미래 날짜로 한 번 돌려 봐야 한다.**
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SPECS = ROOT / "specs"
OPEN_MD = ROOT / "OPEN.md"

#: `- <SPEC 이름> — YYYY-MM-DD — <그날 무엇을 하는가>`
DECLARED = re.compile(r"^-\s+`(SPEC-[a-z0-9-]+)`\s+—\s+(20\d\d-\d\d-\d\d)\s+—\s+(\S.*)$")

SECTION = re.compile(r"^##\s+\d+\.\s+(Open items|Open questions|미해결)\s*$")


def _section_4(text: str) -> list[str]:
    lines = text.splitlines()
    try:
        i = next(n for n, ln in enumerate(lines) if ln.startswith("## 4. 조건부 잔여"))
    except StopIteration:
        return []
    j = next((n for n, ln in enumerate(lines) if n > i and ln.startswith("## ")), len(lines))
    return lines[i:j]


def declared(text: str) -> list[tuple[str, dt.date, str]]:
    """§4 가 선언한 (SPEC, 날짜, 그날 할 일)."""
    out = []
    for line in _section_4(text):
        m = DECLARED.match(line.strip())
        if m:
            out.append((m.group(1), dt.date.fromisoformat(m.group(2)), m.group(3).strip()))
    return out


def open_section_of(spec: str) -> str | None:
    """그 SPEC 의 미해결 절 본문. 절이 없으면 None."""
    p = SPECS / f"{spec}.md"
    if not p.is_file():
        return None
    lines = p.read_text(encoding="utf-8").splitlines()
    idx = [n for n, ln in enumerate(lines) if SECTION.match(ln.strip())]
    if not idx:
        return None
    i = idx[0]
    j = next((n for n, ln in enumerate(lines) if n > i and re.match(r"^##\s", ln)), len(lines))
    return "\n".join(lines[i:j])


def unanchored(text: str) -> list[str]:
    """선언했는데 그 SPEC 본문에 그 날짜가 없는 것. **판정 자격이 없다는 뜻이다.**"""
    out = []
    for spec, when, _ in declared(text):
        body = open_section_of(spec)
        if body is None:
            out.append(f"{spec}: 미해결 절을 못 찾았다")
        elif when.isoformat() not in body:
            out.append(f"{spec}: 선언한 {when.isoformat()} 이 그 SPEC 미해결 절에 없다")
    return out


def fired(text: str, today: dt.date) -> list[str]:
    return [f"{spec} — {when.isoformat()} 이 지났다 — {what}"
            for spec, when, what in declared(text) if today >= when]


def _say(line: str) -> None:
    """콘솔 코드페이지가 cp949 여도 죽지 않는다. **검사기는 죽으면 아무것도 안 말한다.**"""
    try:
        print(line)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(line.encode("utf-8", "replace") + b"\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", default=None, help="그날을 가정한다 (YYYY-MM-DD)")
    args = ap.parse_args()
    today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()

    text = OPEN_MD.read_text(encoding="utf-8")
    rows = declared(text)
    if not rows:
        # ⛔ 대조군. 빈 목록은 "울린 것이 없다" 가 아니라 "못 읽었다" 다.
        _say("⛔ OPEN.md §4 에서 날짜 트리거 선언을 하나도 못 읽었다 — 서식이 바뀌었을 수 있다.")
        _say("   판정하지 않는다. `DECLARED` 정규식과 §4 의 목록을 확인하라.")
        return 76

    loose = unanchored(text)
    if loose:
        _say("⛔ 선언이 SPEC 본문과 맞지 않는다 — 판정하지 않는다")
        for line in loose:
            _say(f"   {line}")
        return 76

    rung = fired(text, today)
    if rung:
        _say(f"⛔ 달력 트리거가 울렸다 ({today.isoformat()}) — **처분하고 이 줄을 지워라**")
        for line in rung:
            _say(f"   {line}")
        return 1
    nxt = min(when for _, when, _ in rows)
    _say(f"✓ 날짜 트리거 {len(rows)}건, 울린 것 없음 (가장 이른 것 {nxt.isoformat()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
