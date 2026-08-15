#!/usr/bin/env python3
"""문서가 서술하는 코드와 얼마나 벌어졌는지 센다.

두 가지를 본다. 성격이 다르므로 처분도 다르다.

  1. 앵커 무결성 (구조적) — doc-anchors.yml 이 가리키는 경로가 실제로 있는가.
     없으면 실패한다. 코드가 옮겨갔는데 문서가 안 따라온 것이고, 경로를 고치려면
     문서를 다시 읽을 수밖에 없다. 이건 판단이 아니라 조회라서 오탐이 없다.

  2. 드리프트 폭 (신호) — 문서가 마지막으로 손봐진 뒤 그 코드가 몇 번 바뀌었는가.
     기본값은 보고만 한다. 커밋이 많다고 문서가 틀렸다는 뜻은 아니기 때문이다.
     막고 싶으면 --max-commits 로 상한을 준다.

LLM 을 부르지 않는다. 네트워크도 쓰지 않는다.

    python scripts/check_doc_drift.py
    python scripts/check_doc_drift.py --max-commits 60
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "doc-anchors.yml"

# 이 파일의 출력은 한국어다. Windows 기본 콘솔은 cp949 라서 그대로 쓰면 터진다
# (UnicodeEncodeError). CI(리눅스)는 UTF-8 이므로 이 줄이 무해하다.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def git(*args: str) -> str:
    out = subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, encoding="utf-8"
    )
    if out.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 실패: {out.stderr.strip()}")
    return out.stdout.strip()


def last_commit_date(path: str) -> str | None:
    """해당 경로를 마지막으로 건드린 커밋 날짜. 커밋 이력이 없으면 None."""
    return git("log", "-1", "--format=%ad", "--date=short", "--", path) or None


def commits_since(date: str, paths: list[str]) -> int:
    raw = git("rev-list", "--count", f"--since={date}", "HEAD", "--", *paths)
    return int(raw or 0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--max-commits", type=int, default=None,
                    help="문서 갱신 이후 앵커 코드 커밋이 이 수를 넘으면 실패시킨다 "
                         "(기본: 보고만 한다)")
    args = ap.parse_args()

    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    entries = manifest.get("docs") or []
    if not entries:
        print(f"{MANIFEST.name} 에 항목이 없다.", file=sys.stderr)
        return 2

    orphans: list[tuple[str, str]] = []
    rows: list[tuple[int, str, str, int]] = []

    for entry in entries:
        doc = entry["doc"]
        sources = entry.get("sources") or []

        if not (REPO / doc).exists():
            orphans.append((doc, doc))
            continue

        missing = [s for s in sources if not (REPO / s).exists()]
        for m in missing:
            orphans.append((doc, m))
        live = [s for s in sources if (REPO / s).exists()]
        if not live:
            continue

        doc_date = last_commit_date(doc)
        if doc_date is None:
            # 아직 커밋되지 않은 문서. 방금 고친 것이므로 드리프트를 물을 수 없다.
            rows.append((-1, doc, "uncommitted", 0))
            continue

        rows.append((commits_since(doc_date, live), doc, doc_date, len(live)))

    rows.sort(key=lambda r: (-r[0], r[1]))

    print(f"{'COMMITS':>8}  {'DOC UPDATED':<12}  {'ANCHORS':>7}  DOC")
    print("-" * 78)
    for n, doc, date, n_src in rows:
        shown = "-" if n < 0 else str(n)
        print(f"{shown:>8}  {date:<12}  {n_src:>7}  {doc}")

    failed = False

    if orphans:
        print()
        print("끊어진 앵커 — 경로가 없다:")
        for doc, path in orphans:
            print(f"  {doc}")
            print(f"    → {path}")
        print()
        print("코드가 옮겨갔는데 문서가 따라오지 않았다. doc-anchors.yml 의 경로를 고치되,")
        print("고치기 전에 그 문서가 아직 사실인지 읽어라. 경로만 바꾸면 검사만 통과한다.")
        failed = True

    if args.max_commits is not None:
        over = [r for r in rows if r[0] > args.max_commits]
        if over:
            print()
            print(f"드리프트 상한({args.max_commits}) 초과:")
            for n, doc, date, _ in over:
                print(f"  {n:>5} 커밋  {doc}  (문서 {date})")
            failed = True

    if not failed:
        print()
        print("앵커 정상. 드리프트는 위 표로 판단하라 — 커밋 수는 신호이지 판정이 아니다.")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
