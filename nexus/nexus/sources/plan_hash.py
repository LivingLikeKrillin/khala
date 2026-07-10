"""재조정 계획의 지문 — 미리보기와 확정 사이에 계획이 바뀌었는지 판별한다.

SPEC-nexus-notion-source-console §4.4.

rid 집합만 해싱하면 부족하다. 같은 rid 라도
  · 걸은 root 집합이 다르면 다른 계획이고,
  · 문서 본문이 바뀌었으면 미리보기 당시 보던 그 문서가 아니다.
둘 다 해시에 들어간다. "2건 지웁니다"를 보고 확정을 눌렀는데 200건이 지워지는 일을 막는 장치다.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

#: (rid, content_hash) 쌍
PlanEntry = tuple[str, str]


def _render(entries: Iterable[PlanEntry]) -> str:
    return ",".join(f"{rid}:{content_hash}" for rid, content_hash in sorted(entries))


def compute_plan_hash(
    walked_roots: Iterable[str],
    prune: Iterable[PlanEntry],
    revive: Iterable[PlanEntry],
) -> str:
    """정렬로 순서 독립. prune/revive 를 라벨로 분리해 같은 문서의 반대 계획이 충돌하지 않게 한다."""
    payload = (
        "roots:" + ",".join(sorted(walked_roots)) + "\n"
        "prune:" + _render(prune) + "\n"
        "revive:" + _render(revive)
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
