"""내가 **사람에게 하는 말**에 용어 규칙을 건다 — `Stop` 훅.

**왜 있나.** `scripts/check_terms.py` 는 `.md` diff 만 본다. 그 범위는 정책과 맞다(문서는
앞으로 쓰는 줄만 지키면 된다). 그런데 규칙을 `CLAUDE.md` 에 넣은 당일부터 내가 **보고
문장에서** 세 번 다시 어겼고, 그 셋은 어떤 검사에도 안 걸렸다 — 내 문장은 diff 가 아니다.

`Stop` 훅에는 그 턴의 응답 전문이 `last_assistant_message` 로 들어온다. 그리고 출력으로
`{"decision": "block", "reason": …}` 을 주면 **끝내려는 것을 막고 이유를 되먹일 수 있다.**
그래서 문을 여기에 단다.

**판정은 새로 만들지 않는다.** 경계 규칙 — 합성어(`사용자`)·단위(`3,000자`)·조사·코드 스팬 —
은 `check_terms` 가 이미 갖고 있고, 목록의 정본은 `GLOSSARY.md` 다. 여기서 더하는 것은
**대화에만 있는 것** 셋뿐이다:

    펜스 코드 블록    붙여넣은 diff·명령 출력은 내 산문이 아니다
    인용 줄(`>`)      남의 말을 내가 고쳐 옮기면 인용이 아니다
    재귀 방지         한 턴에 한 번만 막는다

⚠ **파이프는 UTF-8 이 아니다.** 훅의 stdin/stdout 은 콘솔 코드페이지로 해석된다(실측:
한국어 Windows 에서 `cp949`). 한글이 든 페이로드를 그냥 `sys.stdin.read()` 로 읽으면 조용히
뭉개져서 **아무 말도 안 걸린다** — 단위 테스트는 전부 초록인 채로. 그래서 양쪽 다 바이트로
다룬다: 들어올 때 UTF-8 로 디코드하고, 나갈 때는 `ensure_ascii` 로 순수 ASCII 만 낸다.

⚠ **막히면 세션이 선다.** 그러니 이 훅은 어떤 실패에서도 **통과**로 끝난다 — 용어집을 못
읽어도, 페이로드가 깨져도, 예외가 나도 exit 0 이고 아무것도 안 막는다. 여기서 잡으려는 것
(말 한 마디)보다 매 턴이 막히는 쪽이 비교가 안 되게 비싸다.
"""

from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import check_terms  # noqa: E402

#: 목록의 정본. 사본을 들면 갈라진다 — 이 리포는 그 자리에서 이미 데였다.
GLOSSARY = os.path.join(ROOT, "GLOSSARY.md")

#: `check_terms.check_line` 은 경로로 기록물 여부를 가린다. 내 문장은 파일이 아니니
#: 기록물도 날짜 파일도 아닌 이름을 준다.
_NOT_A_FILE = "<assistant-message>"

_FENCE = "```"


def load_banned() -> dict[str, str]:
    from pathlib import Path
    return check_terms.load_banned(Path(GLOSSARY))


def my_prose(message: str) -> list[str]:
    """이 응답에서 **내가 쓴 산문**만 남긴다.

    빼는 둘은 이유가 같다 — 그 글자는 내가 고를 수 있는 것이 아니다. 펜스 블록은 도구가
    낸 출력이거나 파일의 내용이고, 인용 줄은 남이 그때 쓴 말이다. 고쳐서 옮기면 그건
    인용도 출력도 아니다.
    """
    out: list[str] = []
    fenced = False
    for line in message.splitlines():
        stripped = line.strip()
        if stripped.startswith(_FENCE):
            fenced = not fenced
            continue
        if fenced or stripped.startswith(">"):
            continue
        out.append(line)
    return out


def offenders(message: str, banned: dict[str, str]) -> list[tuple[str, str, str]]:
    """어긴 (말, 대신 쓸 말, 그 줄) 목록. 같은 말은 처음 한 번만 든다."""
    seen: set[str] = set()
    hits: list[tuple[str, str, str]] = []
    for line in my_prose(message):
        for word, replacement in check_terms.check_line(_NOT_A_FILE, line, banned):
            if word in seen:
                continue
            seen.add(word)
            hits.append((word, replacement, line.strip()[:90]))
    return hits


def reason(hits: list[tuple[str, str, str]]) -> str:
    """되먹일 문장. **무엇을 쓰라고** 말해야 다음 문장이 같은 자리에서 안 난다."""
    lines = ["걷어낸 말이 응답에 들어갔다 — 고쳐서 다시 답하라 (정본: GLOSSARY.md)"]
    for word, replacement, sample in hits:
        lines.append(f"  '{word}' → {replacement}")
        lines.append(f"      {sample}")
    lines.append("  그 말 자체를 인용해야 하면 백틱으로 감싼다.")
    return "\n".join(lines)


def _read_stdin() -> str:
    """파이프는 콘솔 코드페이지를 따른다 — 바이트로 받아 UTF-8 로 읽는다.
    (테스트가 갈아 끼우는 `StringIO` 에는 `buffer` 가 없다.)"""
    buf = getattr(sys.stdin, "buffer", None)
    return buf.read().decode("utf-8", "replace") if buf is not None else sys.stdin.read()


def _emit(verdict: dict) -> None:
    """순수 ASCII 로 낸다 — `cp949` 콘솔에서 한글을 쓰면 `UnicodeEncodeError` 가 나고,
    그러면 훅이 죽어 아무것도 안 막는다. JSON 이스케이프는 받는 쪽이 되돌린다."""
    data = json.dumps(verdict, ensure_ascii=True)
    buf = getattr(sys.stdout, "buffer", None)
    if buf is not None:
        buf.write(data.encode("ascii"))
        buf.flush()
    else:
        sys.stdout.write(data)


def main() -> int:
    try:
        payload = json.loads(_read_stdin())
    except Exception:
        return 0
    try:
        # 이미 한 번 막고 다시 온 것이다. 여기서 또 막으면 끝낼 방법이 없어진다.
        if payload.get("stop_hook_active"):
            return 0
        message = payload.get("last_assistant_message") or ""
        if not message:
            return 0
        banned = load_banned()
        if not banned:
            return 0
        hits = offenders(message, banned)
        if not hits:
            return 0
        _emit({"decision": "block", "reason": reason(hits)})
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
