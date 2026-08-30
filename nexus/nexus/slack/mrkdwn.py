"""모델이 쓴 마크다운을 **슬랙이 실제로 그리는 것**으로 바꾼다.

⛔ **왜 있나 (2026-08-30, 파일럿 첫날).** 답변이 `mrkdwn` 블록에 그대로 들어가고 있었다.
그런데 슬랙 mrkdwn 은 **표를 모르고 헤딩을 모르며 굵게는 별 하나**다. 그래서 답변이 좋을수록
화면이 나빠졌다 — 표를 잘 쓴 답변일수록 `|------|------|` 가 글자 그대로 나갔다. 사용자가
첫 질문에서 그것을 보고 알려 줬다.

이 리포가 이미 여러 번 적은 실패와 같은 모양이다: **사람이 보는 표면을 실행하지 않으면 초록은
아무 뜻이 없다.** `formatter.py` 머리에 2026-08-13 의 같은 사고(자르기 상한을 블록이 아니라
메시지 기준으로 계산해 첫 실사용 질문에서 죽은 것)가 적혀 있는데, **같은 파일이 같은 자리에서
또 걸렸다.**

**변환은 답변 텍스트가 아니라 표면의 몫이다.** 프롬프트에 "표를 쓰지 마라" 를 넣지 않는 이유가
그것이다 — API·CLI 에서는 표가 옳고, 못 그리는 것은 슬랙이다.
"""

from __future__ import annotations

import re

#: 마크다운 표 한 줄인가.
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
#: 표의 구분 줄(`|---|:--:|`). 사람에게 보일 것이 없는 줄이다.
_TABLE_RULE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")
#: 마크다운 헤딩. 슬랙은 `#` 을 모른다.
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$")
#: 가로줄. 블록 구분선이 이미 따로 있으므로 본문에서는 뺀다.
_HRULE = re.compile(r"^\s{0,3}([-*_])\1{2,}\s*$")
#: 굵게. **슬랙은 별 하나다** — `**x**` 는 별이 그대로 보인다.
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)

#: 열 폭을 셀 때 두 칸으로 세는 경계. 한글·CJK 는 고정폭 글꼴에서 두 칸을 차지하므로,
#: 글자 수로 재면 열이 어긋나 표가 더 못 읽게 된다.
_WIDE_FROM = 0x2E80


def _display_width(text: str) -> int:
    return sum(2 if ord(c) >= _WIDE_FROM else 1 for c in text)


def _bold(text: str) -> str:
    """굵게만 바꾼다. **줄 단위로 부른다** — 통째로 치환하면 코드 블록 안의 별표까지
    바뀌고, 그건 사람이 보라고 쓴 글자다(검사가 이 자리를 잡았다)."""
    return _BOLD.sub(lambda m: "*" + m.group(1) + "*", text)


def _cells(row: str) -> list[str]:
    return [_bold(c.strip()) for c in row.strip().strip("|").split("|")]


def table_to_code_block(rows: list[str]) -> list[str]:
    """표를 **고정폭 코드 블록**으로. 슬랙에서 표를 보이게 하는 방법은 이것뿐이다.

    Block Kit 에 표가 없다. 열 폭을 맞춰 코드 블록에 넣으면 사람이 읽을 수 있고, 아무것도
    안 하면 파이프와 하이픈이 그대로 화면에 나간다.
    """
    grid = [_cells(r) for r in rows if not _TABLE_RULE.match(r)]
    if not grid:
        return []
    width = max(len(r) for r in grid)
    grid = [r + [""] * (width - len(r)) for r in grid]
    cols = [max(_display_width(r[i]) for r in grid) for i in range(width)]
    out = ["```"]
    for row in grid:
        padded = [c + " " * (cols[i] - _display_width(c)) for i, c in enumerate(row)]
        out.append("  ".join(padded).rstrip())
    out.append("```")
    return out


def to_slack(text: str) -> str:
    """마크다운 → 슬랙 mrkdwn.

    **코드 블록 안은 건드리지 않는다.** 거기 있는 파이프·별표는 사람이 보라고 쓴 글자다.
    """
    out: list[str] = []
    table: list[str] = []
    in_code = False

    for line in (text or "").splitlines():
        if line.lstrip().startswith("```"):
            if table:
                out.extend(table_to_code_block(table))
                table = []
            in_code = not in_code
            out.append(line)
            continue
        if in_code:
            # 코드 블록 안은 손대지 않는다 — 거기 파이프와 별표는 사람이 보라고 쓴 글자다.
            out.append(line)
            continue
        if _TABLE_ROW.match(line):
            table.append(line)
            continue
        if table:
            out.extend(table_to_code_block(table))
            table = []
        if _HRULE.match(line):
            continue
        heading = _HEADING.match(line)
        out.append("*" + _bold(heading.group(1)) + "*" if heading else _bold(line))

    if table:
        out.extend(table_to_code_block(table))
    # **줄 단위로 이미 바꿨다.** 여기서 통째로 한 번 더 치환하면 코드 블록 안의 별표까지
    # 바뀐다 — 검사가 정확히 그것을 잡았다.
    return "\n".join(out)
