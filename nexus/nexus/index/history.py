"""미해소 후보를 **왜** 미해소인지로 가른다 — git 이력 한 번으로.

문서가 코드에 없는 이름을 부르는 데는 서로 다른 이유가 있고, 처분도 다르다:

  external      저장소가 import 만 하는 이름(프레임워크 클래스). **문서 잘못이 아니다.**
  deleted       한때 있었고 지워졌다. 커밋이 있으므로 *언제·왜* 까지 말할 수 있다 — 드리프트.
  never_existed 이력에 없다. 아직 안 만든 것을 서술하는 설계 문서일 수 있다 — 정상일 수 있다.

이 구분이 없으면 목록이 작업 큐가 못 된다. 프레임워크 클래스를 "사라졌다" 고 올리면 받는
쪽이 목록 전체를 신뢰하지 않는다.

**모델을 부르지 않는다.** git 한 번과 집합 연산이다.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

EXTERNAL = "external"
DELETED = "deleted"
NEVER_EXISTED = "never_existed"


@dataclass(frozen=True)
class Deletion:
    commit: str
    date: str
    subject: str
    path: str


@dataclass(frozen=True)
class Verdict:
    name: str
    kind: str
    deletion: Deletion | None = None

    def explain(self) -> str:
        if self.kind == EXTERNAL:
            return "외부 타입 — 이 저장소가 선언하지 않고 import 한다. 문서 잘못이 아니다."
        if self.kind == DELETED and self.deletion:
            d = self.deletion
            return f"{d.date} `{d.commit}` 에서 삭제 — {d.subject}"
        return "이력에 없음 — 아직 만들지 않은 것을 서술하는 문서일 수 있다."


def deletion_map(repo: Path, *, suffixes: tuple[str, ...] = (".java", ".py")) -> dict[str, Deletion]:
    """저장소 전 이력에서 삭제된 파일들. **후보마다 git 을 부르지 않는다** — 한 번 훑고 끝낸다.

    후보 100여 개에 대해 개별 `git log` 를 돌리면 몇 분이 걸리고, 그 비용이 이 보고서를
    아무도 안 돌리는 이유가 된다.
    """
    out = subprocess.run(
        ["git", "log", "--diff-filter=D", "--name-only",
         "--format=%x00%h|%ad|%s", "--date=short"],
        cwd=repo, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if out.returncode != 0:
        return {}

    found: dict[str, Deletion] = {}
    commit = date = subject = ""
    for line in out.stdout.splitlines():
        if line.startswith("\x00"):
            parts = line[1:].split("|", 2)
            if len(parts) == 3:
                commit, date, subject = parts
            continue
        path = line.strip()
        if not path:
            continue
        suffix = Path(path).suffix.lower()
        if suffix not in suffixes:
            continue
        stem = Path(path).stem
        # 가장 최근 삭제가 이긴다. git log 는 최신순이므로 먼저 본 것을 지킨다.
        found.setdefault(stem, Deletion(commit, date, subject, path))
    return found


def classify(names: list[str], *, imported: frozenset[str],
             deletions: dict[str, Deletion]) -> list[Verdict]:
    """미해소 후보를 처분 가능한 세 종류로.

    순서가 의미를 가진다: **외부 판정이 먼저**다. 저장소가 import 하는 이름이 우연히 예전에
    같은 이름으로 존재했다 해도, 문서가 부른 것은 외부 타입 쪽일 가능성이 높다.
    """
    verdicts: list[Verdict] = []
    for name in names:
        if name in imported:
            verdicts.append(Verdict(name, EXTERNAL))
        elif name in deletions:
            verdicts.append(Verdict(name, DELETED, deletions[name]))
        else:
            verdicts.append(Verdict(name, NEVER_EXISTED))
    return verdicts
