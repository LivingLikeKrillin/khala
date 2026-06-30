import subprocess
from collections.abc import Callable


def _git(cmd: list[str]) -> str:
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def changed_source_modules(
    base: str = "HEAD",
    run: Callable[[list[str]], str] = _git,
) -> list[str]:
    """base 대비 변경된 파이썬 소스 모듈 경로(테스트/__init__ 제외)."""
    raw = run(["git", "diff", "--name-only", base])
    out: list[str] = []
    for path in raw.splitlines():
        path = path.strip().replace("\\", "/")
        if not path.endswith(".py"):
            continue
        if path.startswith("tests/") or "/tests/" in path:
            continue
        if path.endswith("__init__.py"):
            continue
        out.append(path)
    return out
