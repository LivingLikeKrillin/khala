"""새로 쓰는 산문에 걷어낸 말이 다시 들어오는지 본다.

**정본은 `GLOSSARY.md` 다.** 이 파일은 목록을 갖지 않고 거기서 읽는다 — 손으로 미러링한
목록은 전부 부패원이고, 이 리포는 그 자리에서 이미 데였다.

**왜 diff 만 보나.** 정책이 "앞으로만" 이다(과거 기록물은 그때 그 말로 남긴다). 그러면
검사도 앞으로 쓰는 줄만 보면 되고, 그래야 "자" 같은 흔한 글자에 예외를 수십 개 달지
않는다. 예외가 수십 개인 검사는 곧 꺼지고, 꺼진 검사는 없는 검사다.

    python scripts/check_terms.py             # origin/master 와의 diff
    python scripts/check_terms.py --base HEAD~1
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLOSSARY = ROOT / "GLOSSARY.md"

# 콘솔 코드페이지가 cp949 여도 죽지 않는다 — `check_doc_drift.py` 와 같은 처리.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

#: 이 정책은 **사람이 읽는 산문**에만 걸린다. 코드·설정은 범위 밖이다.
PROSE = (".md",)

#: 그때 그 말로 쓰인 기록물 — 손대지 않으므로 검사도 하지 않는다.
ARCHIVAL_PREFIXES = ("specs/", ".reviews/", "adr/", ".superpowers/")
ARCHIVAL_FILES = (
    "docs/src/content/docs/ko/engineering-log.md",
    "docs/src/content/docs/engineering-log.md",
)
#: 사전은 자기가 금지한 말을 적어야 한다.
EXEMPT_FILES = ("GLOSSARY.md",)

#: 날짜가 박힌 파일 = 그날 그 측정의 기록. 옆의 README 는 살아 있는 안내문이다.
DATED = re.compile(r"(^|/)\d{4}-\d{2}-\d{2}[-.]")

_CODE_SPAN = re.compile(r"`[^`]*`")
_KO = "[가-힣]"

#: 낱말 뒤에 붙을 수 있는 조사. 이것만 허용하고, **조사 뒤에 글자가 더 오면 합성어**로 본다.
#:   자가   → 자 + 가(조사)      = 걸린다
#:   자가용 → 조사 뒤에 '용'      = 안 걸린다
#:   자기   → '기' 는 조사가 아님 = 안 걸린다 (자동·자료·자리도 같다)
_JOSA = "|".join(sorted([
    "으로써", "으로서", "에서는", "이라는", "이라고", "에서", "에게", "으로", "부터", "까지",
    "처럼", "보다", "마다", "조차", "밖에", "만큼", "이나", "라도",
    "가", "이", "은", "는", "을", "를", "에", "의", "로", "와", "과", "도", "만", "라",
], key=len, reverse=True))


def is_archival(path: str) -> bool:
    p = path.replace("\\", "/")
    # `lstrip("./")` 를 쓰면 안 된다 — 문자 집합을 벗기는 함수라 `.reviews/` 의 앞 점까지 갉는다.
    while p.startswith("./"):
        p = p[2:]
    if p in EXEMPT_FILES or p in ARCHIVAL_FILES:
        return True
    if any(p.startswith(pre) for pre in ARCHIVAL_PREFIXES):
        return True
    return bool(DATED.search(p))


def load_banned(glossary: Path = GLOSSARY) -> dict[str, str]:
    """`GLOSSARY.md` 의 「걷어낸 말」 표를 읽는다.

    표에 한 줄 더하면 그날부터 검사에 든다 — 이 파일은 안 고쳐도 된다.
    """
    try:
        text = glossary.read_text(encoding="utf-8")
    except OSError:
        return {}
    section = text.split("## 걷어낸 말", 1)
    if len(section) < 2:
        return {}
    body = section[1].split("\n## ", 1)[0]
    banned: dict[str, str] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0] in ("쓰지 않는 말", ""):
            continue
        word, replacement = cells[0], cells[1]
        if word:
            banned[word] = replacement
    return banned


def check_line(path: str, line: str, banned: dict[str, str]) -> list[tuple[str, str]]:
    """이 줄이 규칙을 어겼는가. 어긴 (말, 대신 쓸 말) 목록을 낸다.

    두 가지를 일부러 빼고 본다:
      · **기록물 경로** — 과거는 그대로 둔다
      · **코드 스팬** — `SPEC-…-ruler.md` 같은 식별자·파일명은 산문이 아니고, 오히려
        인용해야 할 때가 있다
    """
    if is_archival(path):
        return []
    prose = _CODE_SPAN.sub(" ", line)
    hits = []
    for word, replacement in banned.items():
        # 낱말 경계. 앞에 한글이 붙었으면 합성어이고('사용자'·'숫자'), **숫자·영문이 붙었으면
        # 단위**다('3,000자'·'12자'). 뒤는 조사까지만 허용한다.
        # 이런 거짓 경고를 하나라도 내보내면 사람이 검사를 끈다.
        if re.search(rf"(?<![가-힣0-9A-Za-z]){re.escape(word)}(?:{_JOSA})?(?![가-힣])", prose):
            hits.append((word, replacement))
    return hits


def added_lines(diff: str) -> list[tuple[str, str]]:
    """유니파이드 diff 에서 **추가된** 산문 줄만 뽑는다.

    지우는 줄과 맥락 줄은 안 본다 — 낡은 말을 걷어내는 커밋이 자기 검사에 걸리면
    정리를 못 한다.
    """
    out: list[tuple[str, str]] = []
    path: str | None = None
    for line in diff.splitlines():
        if line.startswith("+++ "):
            target = line[4:].strip()
            target = target[2:] if target.startswith("b/") else target
            path = target if target.endswith(PROSE) else None
            continue
        if line.startswith(("--- ", "diff --git", "@@", "index ")):
            continue
        if path and line.startswith("+"):
            out.append((path, line[1:]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="새 산문에 걷어낸 말이 들어왔는지 본다")
    ap.add_argument("--base", default=None, help="비교 기준 (기본: origin/master 또는 master)")
    args = ap.parse_args()

    base = args.base
    if base is None:
        for cand in ("origin/master", "master"):
            probe = subprocess.run(["git", "rev-parse", "--verify", "--quiet", cand],
                                   cwd=ROOT, capture_output=True, text=True)
            if probe.returncode == 0:
                base = cand
                break
    if base is None:
        print("기준 브랜치를 못 찾았다 — 검사를 건너뛴다")
        return 0

    diff = subprocess.run(["git", "diff", "--unified=0", f"{base}...HEAD"],
                          cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    banned = load_banned()
    if not banned:
        print("GLOSSARY.md 의 「걷어낸 말」 표를 못 읽었다")
        return 1

    bad = []
    for path, line in added_lines(diff.stdout or ""):
        for word, replacement in check_line(path, line, banned):
            bad.append((path, word, replacement, line.strip()[:90]))

    if not bad:
        print(f"✓ 새로 추가된 산문에 걷어낸 말 없음 (금지 {len(banned)}개, 기준 {base})")
        return 0

    print(f"✗ 걷어낸 말이 새 줄에 {len(bad)}건 들어왔다 — GLOSSARY.md 를 보라\n")
    for path, word, replacement, sample in bad:
        print(f"  {path}: '{word}' → {replacement}")
        print(f"      {sample}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
