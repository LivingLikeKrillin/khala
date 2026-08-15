"""체크아웃 스냅샷 가드 — 드리프트 판정을 낼 자격이 있는 상태인지 본다.

SPEC-nexus-doc-code-anchors §3.5.

**왜 오프라인인가.** 원격과 비교하는 가드는 원격이 안 닿을 때 조용히 통과한다 — 즉 가드가
필요한 순간에 정확히 열린다. 그리고 SPEC §2 가 네트워크를 비목표로 박았다. 그래서 원격 대비
낡음은 **의도적으로 판정하지 않는다**: 그건 사용자의 `git pull` 이고, 그게 일어났다고 가정하는
보고서가 이 가드가 막으려는 실패다.

`unknown` 은 정답이다. 더러운 트리에서 계산한 `fresh` 는 아니다.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SnapshotState:
    ok: bool
    reason: str          # 'clean' | 'dirty' | 'detached' | 'scan_ahead_of_head' | 'scan_diverged' | 'no_git'
    head: str = ""
    scan_commit: str = ""

    def explain(self) -> str:
        if self.ok:
            return f"스냅샷 정상 (HEAD={self.head[:12]})"
        return {
            "dirty": "작업 트리가 더럽다 — 커밋되지 않은 변경 위에서 계산한 판정은 거짓이다.",
            "detached": "HEAD 가 detached 다 — 어느 분기의 사실인지 말할 수 없다.",
            "scan_ahead_of_head": (
                f"스캔 커밋({self.scan_commit[:12]})이 HEAD({self.head[:12]})보다 앞이다 — "
                "체크아웃을 되돌린 뒤 다시 스캔하지 않았다."),
            "scan_diverged": (
                f"스캔 커밋({self.scan_commit[:12]})과 HEAD({self.head[:12]})가 갈라졌다."),
            "no_git": "git 저장소가 아니거나 git 을 실행할 수 없다.",
        }.get(self.reason, self.reason)


def _git(repo: Path, *args: str) -> tuple[int, str]:
    try:
        out = subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except OSError:
        return 127, ""
    return out.returncode, out.stdout.strip()


def head_commit(repo: Path) -> str | None:
    code, out = _git(repo, "rev-parse", "HEAD")
    return out if code == 0 and out else None


def check(repo: Path, scan_commit: str) -> SnapshotState:
    """`scan_commit` 으로 만든 인덱스가 지금 이 체크아웃을 설명한다고 말해도 되는가."""
    head = head_commit(repo)
    if head is None:
        return SnapshotState(False, "no_git", scan_commit=scan_commit)

    code, dirty = _git(repo, "status", "--porcelain")
    if code != 0:
        return SnapshotState(False, "no_git", head=head, scan_commit=scan_commit)
    if dirty:
        return SnapshotState(False, "dirty", head=head, scan_commit=scan_commit)

    # symbolic-ref 는 detached 에서 0 이 아닌 코드를 낸다.
    code, _ = _git(repo, "symbolic-ref", "-q", "HEAD")
    if code != 0:
        return SnapshotState(False, "detached", head=head, scan_commit=scan_commit)

    if scan_commit == head:
        return SnapshotState(True, "clean", head=head, scan_commit=scan_commit)

    # 스캔이 HEAD 의 조상이면 정상(그 사이 커밋은 §3.4 가 changed/orphaned 로 잡는다).
    code, _ = _git(repo, "merge-base", "--is-ancestor", scan_commit, head)
    if code == 0:
        return SnapshotState(True, "clean", head=head, scan_commit=scan_commit)

    code, _ = _git(repo, "merge-base", "--is-ancestor", head, scan_commit)
    reason = "scan_ahead_of_head" if code == 0 else "scan_diverged"
    return SnapshotState(False, reason, head=head, scan_commit=scan_commit)
