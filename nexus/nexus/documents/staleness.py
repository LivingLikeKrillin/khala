"""근거 신선도(staleness) 판정 — SPEC-nexus-answer-staleness-warning.

updated_at(적재시각) 나이를 doc_type 별 TTL 과 대조한다. 결정론·순수·무예외.
"System decides": 코드가 시간으로 판정하고 LLM 은 개입 안 한다. supersession(옛 버전 배제)과
직교 — 여기선 '현행이지만 오래됨'을 경고만 한다(랭킹·배제 안 함).

한계: updated_at 은 적재 시각이라, 내용 그대로 재동기화된 문서는 신선해 보인다(under-warn).
오차 방향은 안전(무고 아닌 놓침). 더 정확한 신호(origin_last_edited·review 날짜)는 후속.
"""

from __future__ import annotations

from datetime import datetime, timezone


def staleness(updated_at: datetime | None, doc_type: str | None,
              now: datetime, ttl: dict) -> dict:
    """{age_days, ttl_days, stale}. 미상 나이·null/음수 TTL 은 stale 아님."""
    ttl_days = ttl.get((doc_type or "").upper(), ttl.get("default"))
    if not (isinstance(ttl_days, int) and not isinstance(ttl_days, bool) and ttl_days > 0):
        ttl_days = None                                  # null/음수/0/비수치 → TTL 없음(never stale)
    if updated_at is None:
        return {"age_days": None, "ttl_days": ttl_days, "stale": False}
    if updated_at.tzinfo is None:                        # naive → UTC 로 간주(예외 방지)
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    age_days = max(0, (now - updated_at).days)           # 미래/시계어긋남 → 0
    stale = ttl_days is not None and age_days > ttl_days
    return {"age_days": age_days, "ttl_days": ttl_days, "stale": stale}


def annotate_staleness(snippets: list[dict], now: datetime, ttl: dict) -> tuple[list[dict], int]:
    """각 스니펫(updated_at datetime + doc_type)에 'staleness' 서브딕트 부착 + stale 개수."""
    annotated: list[dict] = []
    n_stale = 0
    for s in snippets:
        st = staleness(s.get("updated_at"), s.get("doc_type", ""), now, ttl)
        annotated.append({**s, "staleness": st})
        if st["stale"]:
            n_stale += 1
    return annotated, n_stale
