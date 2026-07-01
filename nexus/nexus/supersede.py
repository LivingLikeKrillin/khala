"""문서 supersession 선언 프리미티브(명시적·멱등, 자동감지 없음). 스펙 §5.3."""

from __future__ import annotations

from nexus import db


async def supersede(old_rid: str, new_rid: str, tenant: str) -> str:
    """old 를 new 로 대체. 반환: 'superseded' | 'noop'. 위반 시 ValueError.

    결정규칙(순서 고정): 자기참조 → new 검증 → old 존재 → old 상태.
    """
    if old_rid == new_rid:
        raise ValueError("self-supersession not allowed")

    new_row = await db.fetch_one(
        "SELECT status FROM documents WHERE rid = $1 AND tenant = $2", new_rid, tenant)
    if new_row is None or new_row["status"] != "active":
        raise ValueError(f"new_rid not found or not active: {new_rid}")

    old_row = await db.fetch_one(
        "SELECT status FROM documents WHERE rid = $1 AND tenant = $2", old_rid, tenant)
    if old_row is None:
        raise ValueError(f"old_rid not found: {old_rid}")
    if old_row["status"] != "active":
        return "noop"  # superseded(정리 완료) 또는 soft_deleted(범위 밖) — 적용 안 함

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE documents SET status='superseded', superseded_by=$1, updated_at=now() "
                "WHERE rid=$2 AND tenant=$3 AND status='active'", new_rid, old_rid, tenant)
            await conn.execute(
                "UPDATE chunks SET status='superseded', updated_at=now() WHERE doc_rid=$1", old_rid)
    return "superseded"


async def resolve_active_doc(ref: str, tenant: str) -> str:
    """ref(rid | source_uri | basename)를 문서 rid 로 확정. 위반 시 ValueError. 스펙 §4.1.

    결정 순서: (1) rid 패스스루 → (2) source_uri 정확일치(active) → (3) basename LIKE(active).
    판정: 정확히 1건→rid · 0건→ValueError · 2건+→ValueError(후보 나열).

    주의: step 1 rid 패스스루는 status 무관(superseded/soft_deleted 포함) — 하위호환·자동화용.
    코어 supersede() 가 상태를 재검증하므로 안전. 이 패스스루를 'active 만'으로 좁히지 말 것.
    """
    # 1) rid 패스스루 (status 무관)
    hit = await db.fetch_val(
        "SELECT rid FROM documents WHERE rid = $1 AND tenant = $2", ref, tenant)
    if hit is not None:
        return hit

    # 2) source_uri 정확일치 (상대경로는 tenant 접두 자동 조립 후 바인드)
    rows = await db.fetch_all(
        "SELECT DISTINCT rid, source_uri FROM documents "
        "WHERE tenant = $1 AND status = 'active' AND (source_uri = $2 OR source_uri = $3)",
        tenant, ref, f"{tenant}:{ref}")

    # 3) 정확일치 0건이면 basename LIKE (메타문자 이스케이프 + ESCAPE)
    if not rows:
        escaped = ref.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        rows = await db.fetch_all(
            "SELECT DISTINCT rid, source_uri FROM documents "
            "WHERE tenant = $1 AND status = 'active' AND source_uri LIKE $2 ESCAPE '\\' "
            "ORDER BY source_uri",
            tenant, f"%/{escaped}")

    # 4) 판정
    if len(rows) == 1:
        return rows[0]["rid"]
    if not rows:
        raise ValueError(f"일치하는 active 문서 없음: {ref}")
    candidates = ", ".join(r["source_uri"] for r in rows)
    raise ValueError(
        f"'{ref}'에 여러 문서가 일치합니다 — 경로를 더 구체적으로 주거나 rid 로 지정하세요. 후보: {candidates}")
