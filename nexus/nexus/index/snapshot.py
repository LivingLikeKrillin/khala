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
    #: 아래 넷은 통과/거부를 바꾸지 않는다. **무엇을 사실로 삼았는지 말하는 몫**이다.
    #: 2026-08-15 에 3주 된 문서 피처 브랜치를 스캔해놓고 "심볼 6,264개" 라고 보고했다.
    #: 트리는 깨끗했고 스캔 커밋과 HEAD 도 같았으므로 가드는 통과했다 — 아무도 *어느 브랜치의
    #: 언제 것인지* 를 묻지 않았기 때문이다. 전부 로컬 정보라 네트워크를 쓰지 않는다(§2).
    branch: str = ""
    head_date: str = ""
    behind: int = 0      # 로컬에 저장된 원격 추적 ref 기준 — **마지막 fetch 시점의 사실**
    ahead: int = 0

    def context(self) -> str:
        """무엇을 사실로 삼았는지. 통과했더라도 **항상** 함께 출력한다."""
        bits = [f"branch={self.branch or '?'}", f"HEAD={self.head[:12]}"]
        if self.head_date:
            bits.append(self.head_date[:10])
        if self.behind or self.ahead:
            bits.append(f"업스트림 대비 -{self.behind}/+{self.ahead} (마지막 fetch 기준)")
        return " · ".join(bits)

    def warnings(self) -> list[str]:
        """거부는 아니지만 조용히 넘기면 안 되는 것들."""
        out = []
        if self.branch and self.branch not in _MAINLINE:
            out.append(f"기본 브랜치가 아닙니다({self.branch}) — 이 인덱스는 그 브랜치의 사실입니다.")
        if self.behind:
            out.append(f"업스트림보다 {self.behind}커밋 뒤입니다(마지막 fetch 기준). "
                       "원격은 확인하지 않습니다 — `git pull` 은 당신 몫입니다.")
        if self.ahead:
            out.append(f"업스트림보다 {self.ahead}커밋 앞입니다 — 푸시되지 않은 작업 위에서 재고 있습니다.")
        return out

    def explain(self) -> str:
        if self.ok:
            return f"스냅샷 정상 ({self.context()})"
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


#: 정본으로 볼 만한 브랜치 이름. 여기 없으면 경고할 뿐 막지는 않는다 — 피처 브랜치를
#: 일부러 재는 경우가 있고, 그건 말해주기만 하면 되는 일이다.
_MAINLINE = frozenset({"main", "master", "develop", "development"})


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


def _describe(repo: Path) -> dict:
    """브랜치·HEAD 날짜·업스트림 격차. 전부 로컬 ref 에서 읽는다 — 네트워크 없음."""
    _, branch = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    _, date = _git(repo, "log", "-1", "--format=%cI")
    behind = ahead = 0
    code, counts = _git(repo, "rev-list", "--left-right", "--count", "@{u}...HEAD")
    if code == 0 and counts:
        parts = counts.split()
        if len(parts) == 2:
            behind, ahead = int(parts[0]), int(parts[1])
    return {"branch": branch, "head_date": date, "behind": behind, "ahead": ahead}


def check(repo: Path, scan_commit: str) -> SnapshotState:
    """`scan_commit` 으로 만든 인덱스가 지금 이 체크아웃을 설명한다고 말해도 되는가."""
    head = head_commit(repo)
    if head is None:
        return SnapshotState(False, "no_git", scan_commit=scan_commit)
    extra = _describe(repo)

    code, dirty = _git(repo, "status", "--porcelain")
    if code != 0:
        return SnapshotState(False, "no_git", head=head, scan_commit=scan_commit, **extra)
    if dirty:
        return SnapshotState(False, "dirty", head=head, scan_commit=scan_commit, **extra)

    # symbolic-ref 는 detached 에서 0 이 아닌 코드를 낸다.
    code, _ = _git(repo, "symbolic-ref", "-q", "HEAD")
    if code != 0:
        return SnapshotState(False, "detached", head=head, scan_commit=scan_commit, **extra)

    if scan_commit == head:
        return SnapshotState(True, "clean", head=head, scan_commit=scan_commit, **extra)

    # 스캔이 HEAD 의 조상이면 정상(그 사이 커밋은 §3.4 가 changed/orphaned 로 잡는다).
    code, _ = _git(repo, "merge-base", "--is-ancestor", scan_commit, head)
    if code == 0:
        return SnapshotState(True, "clean", head=head, scan_commit=scan_commit, **extra)

    code, _ = _git(repo, "merge-base", "--is-ancestor", head, scan_commit)
    reason = "scan_ahead_of_head" if code == 0 else "scan_diverged"
    return SnapshotState(False, reason, head=head, scan_commit=scan_commit, **extra)
