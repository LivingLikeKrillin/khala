"""코드 안의 걷어낸 말이 **어디에** 있는지 가른다 — 고치기 전에.

주석·docstring 은 산문이므로 고쳐도 동작이 안 바뀐다. 그러나 **기능하는 문자열**은 다르다:
프롬프트 본문·CLI 출력·테스트 기댓값이 거기 있고, 바꾸면 측정이나 동작이 같이 바뀐다.
이 리포는 라벨을 건드리면 안 된다는 것을 이미 규칙으로 갖고 있다.

    python scripts/_terms_code_scan.py            # 어디에 몇 개인지
    python scripts/_terms_code_scan.py --apply    # 주석·docstring 만 고친다
"""

from __future__ import annotations

import argparse
import ast
import io
import os
import re
import sys
import tokenize
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_terms as ct  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

SKIP_DIRS = {"node_modules", "dist", ".git", ".pytest_cache", "vendor", ".venv", "__pycache__"}
SKIP_PREFIX = ("nexus/tests/eval/ko/corpus",)

#: ⛔ 손대지 않는다. 평가 라벨·질문은 **측정의 입력**이고 서명·매니페스트에 묶여 있다.
#: 철회 원장은 도장이 걸려 있다. 사전과 검사기는 그 말을 이름으로 들고 있어야 한다.
FROZEN = (
    "nexus/tests/eval/",          # 라벨·질문·워크시트 데이터
    "specs/retractions.yaml",     # 서명된 철회 원장
    "scripts/check_terms.py",
    "scripts/_terms_code_scan.py",
    "tests/test_check_terms.py",
)

#: 문맥 판단이 필요 없는 것만 기계로 바꾼다. `자` 는 뜻이 갈려 사람이 봐야 한다.
MECHANICAL = {
    "팔": "실험군",
    "방아쇠": "트리거",
    "그물": "회귀 검사",
    "손잡이": "식별자",
    "검색 다리": "검색 경로",
    "잡음 바닥": "잡음 폭",
}


def frozen(path: str) -> bool:
    return any(path.startswith(f) or path == f for f in FROZEN)


def prose_lines(src: str) -> set[int]:
    """주석과 docstring 이 차지하는 줄 번호. 나머지 문자열은 **기능하는 것**으로 본다."""
    lines: set[int] = set()
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT:
                lines.update(range(tok.start[0], tok.end[0] + 1))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return lines
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            lines.update(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return lines


def swap(text: str, word: str, repl: str) -> str:
    pat = re.compile(
        rf"(?<![가-힣0-9A-Za-z]){re.escape(word)}((?:{ct._JOSA})?)(?![가-힣])")
    return pat.sub(lambda m: repl + m.group(1), text)


def walk_files():
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        rel_dir = os.path.relpath(dp, ROOT).replace("\\", "/")
        if rel_dir == ".":
            rel_dir = ""
        if any(rel_dir.startswith(p) for p in SKIP_PREFIX):
            continue
        for fn in fns:
            if not fn.endswith((".py", ".yml", ".yaml")):
                continue
            rel = (f"{rel_dir}/{fn}" if rel_dir else fn)
            yield rel, Path(dp) / fn


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="주석·docstring 만 고친다")
    args = ap.parse_args()

    banned = ct.load_banned()
    where = Counter()
    manual: list[str] = []
    changed = 0

    for rel, path in walk_files():
        if frozen(rel):
            where["동결(손대지 않음)"] += 1
            continue
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        lines = src.splitlines()
        is_py = rel.endswith(".py")
        prose = prose_lines(src) if is_py else set()

        out = []
        touched = False
        for i, ln in enumerate(lines, 1):
            hits = [w for w, _ in ct.check_line("x.md", ln, banned)]
            if not hits:
                out.append(ln)
                continue
            # YAML 은 `#` 주석만 산문으로 본다.
            in_prose = (i in prose) if is_py else ln.lstrip().startswith("#")
            if not in_prose:
                where["기능하는 문자열·데이터"] += len(hits)
                manual.append(f"{rel}:{i}  [{','.join(hits)}]")
                out.append(ln)
                continue
            where["주석·docstring"] += len(hits)
            new = ln
            for w in hits:
                if w in MECHANICAL:
                    new = swap(new, w, MECHANICAL[w])
                else:
                    manual.append(f"{rel}:{i}  [{w}] 사람 판단")
            if new != ln:
                touched = True
            out.append(new)

        if args.apply and touched:
            path.write_text("\n".join(out) + ("\n" if src.endswith("\n") else ""),
                            encoding="utf-8")
            changed += 1

    print("어디에 있나:", dict(where))
    print(f"사람이 봐야 하는 줄: {len(manual)}")
    for m in manual[:40]:
        print("  ", m)
    if args.apply:
        print(f"\n고친 파일: {changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
