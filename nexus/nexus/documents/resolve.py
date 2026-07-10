"""ref(rid | 경로 | URI) → 문서 rid. SPEC-nexus-document-lifecycle §4.6.

`supersede.resolve_active_doc` 는 경로 조회를 active 로 좁힌다 — supersede 의 대상은 active 여야
하므로 옳다. 하지만 hide 를 되돌리거나 supersession 을 취소할 때 대상은 **정의상 active 가 아니다**.
그 해석기로는 숨긴 문서를 영영 경로로 부를 수 없고, 사람은 rid 를 손으로 옮겨 적게 된다.

여기 있는 것은 같은 결정 순서를 쓰되 상태를 가리지 않는 해석기다. 모호하면 여전히 거부한다 —
문서를 지우는 명령이 후보 중 하나를 임의로 고르게 두지 않는다.
"""

from __future__ import annotations

from nexus import db


async def resolve_doc(ref: str, tenant: str, *, active_only: bool = False) -> str:
    """ref 를 rid 로 확정. 위반 시 ValueError.

    결정 순서: (1) rid 패스스루 → (2) source_uri 정확일치 → (3) basename LIKE.
    판정: 정확히 1건→rid · 0건→ValueError · 2건+→ValueError(후보 나열).

    active_only=True 는 (2)(3) 을 active 문서로 좁힌다. (1) rid 패스스루는 두 모드 모두
    status 무관이다 — 호출자(supersede/hide/…)가 상태를 재검증하므로 안전하다.
    """
    hit = await db.fetch_val(
        "SELECT rid FROM documents WHERE rid = $1 AND tenant = $2", ref, tenant)
    if hit is not None:
        return hit

    status_clause = "AND status = 'active'" if active_only else ""

    rows = await db.fetch_all(
        f"SELECT DISTINCT rid, source_uri FROM documents "
        f"WHERE tenant = $1 {status_clause} AND (source_uri = $2 OR source_uri = $3)",
        tenant, ref, f"{tenant}:{ref}")

    if not rows:
        escaped = ref.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = await db.fetch_all(
            f"SELECT DISTINCT rid, source_uri FROM documents "
            f"WHERE tenant = $1 {status_clause} AND source_uri LIKE $2 ESCAPE '\\' "
            f"ORDER BY source_uri",
            tenant, f"%/{escaped}")

    if len(rows) == 1:
        return rows[0]["rid"]
    if not rows:
        what = "active 문서" if active_only else "문서"
        raise ValueError(f"일치하는 {what} 없음: {ref}")
    candidates = ", ".join(r["source_uri"] for r in rows)
    raise ValueError(
        f"'{ref}'에 여러 문서가 일치합니다 — 경로를 더 구체적으로 주거나 rid 로 지정하세요. "
        f"후보: {candidates}")
