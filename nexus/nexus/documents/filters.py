"""문서 목록의 상태 필터 (SPEC-nexus-document-lifecycle §4.4).

응답이 내보내는 모든 상태는 필터 값으로도 받아야 한다. 그렇지 않으면 그 행에 도달할
길이 없다 — `pruned` 가 정확히 그런 상태였다.

`hidden` 과 `pruned` 는 같은 status(soft_deleted)에 hold 만 다르다. 원인이 다르고,
그래서 복구 의미가 다르다: pruned 문서는 페이지가 돌아오면 스스로 되살아나고,
hold 문서는 절대 되살아나지 않는다.
"""

from __future__ import annotations

#: 필터 값 → SQL 술어 (d 는 documents 별칭)
STATUS_FILTERS: dict[str, str] = {
    "active": "d.status = 'active'",
    "hidden": "d.status = 'soft_deleted' AND d.hold = true",
    "pruned": "d.status = 'soft_deleted' AND d.hold = false",
    "superseded": "d.status = 'superseded'",
    "all": "TRUE",
}


def reportable_status(status: str, hold: bool) -> str:
    """DB 상태 → 사용자에게 보여줄 상태. 같은 행, 다른 원인, 다른 문장."""
    if status == "soft_deleted":
        return "hidden" if hold else "pruned"
    return status
