"""그래프 채널의 base_filter 강제 — SPEC-nexus-graph-scope-filter §6.

그래프 이웃/증거 조회가 호출자의 (tenant, clearance)를 양 끝 엔티티(및 증거 청크)에 강제하는지
DB 로 증명한다. 누출이 SQL 에 있으므로 실제 DB(_disposable_test_db)로만 잡을 수 있다.
"""

from __future__ import annotations

import pytest

from nexus.repositories.graph import PostgresGraphRepository
from nexus.rid import edge_rid, entity_rid

pytestmark = pytest.mark.integration


async def _ent(conn, tenant, etype, name, *, classification="INTERNAL", quarantined=False):
    rid = entity_rid(tenant, etype, name)
    await conn.execute(
        """INSERT INTO entities (rid, tenant, entity_type, name, classification, is_quarantined,
                                 source_uri, hash)
           VALUES ($1, $2, $3, $4, $5::classification_level, $6, 'test:scope', 'h')""",
        rid, tenant, etype, name, classification, quarantined,
    )
    return rid


async def _edge(conn, tenant, frm, to):
    e = edge_rid(tenant, "CALLS", frm, to)
    await conn.execute(
        """INSERT INTO edges (rid, tenant, edge_type, from_rid, to_rid, confidence)
           VALUES ($1, $2, 'CALLS', $3, $4, 0.9)""",
        e, tenant, frm, to,
    )
    return e


async def _seed(conn):
    """a1—a2 (in scope), a1—b1 (cross-tenant), a1—a_secret (RESTRICTED), a1—a_quar (quarantined)."""
    a1 = await _ent(conn, "default", "service", "a1")
    a2 = await _ent(conn, "default", "service", "a2")
    b1 = await _ent(conn, "other", "service", "b1")
    a_secret = await _ent(conn, "default", "service", "a_secret", classification="RESTRICTED")
    a_quar = await _ent(conn, "default", "service", "a_quar", quarantined=True)
    await _edge(conn, "default", a1, a2)
    await _edge(conn, "other", a1, b1)          # cross-tenant edge from a1
    await _edge(conn, "default", a1, a_secret)
    await _edge(conn, "default", a1, a_quar)
    return a1


def _names(subgraph):
    out = set()
    for e in subgraph.edges:
        out.add(e.from_name)
        out.add(e.to_name)
    return out


async def test_neighbors_exclude_cross_tenant_over_clearance_and_quarantined(db_pool):
    async with db_pool.acquire() as conn:
        a1 = await _seed(conn)
    repo = PostgresGraphRepository(db_pool)

    sg = await repo.get_neighbors(a1, hops=2, tenant="default", clearance="INTERNAL")
    names = _names(sg)
    assert "a2" in names                      # 같은 테넌트·INTERNAL·active → 보임
    assert "b1" not in names                  # 타 테넌트 → 누출 금지
    assert "a_secret" not in names            # 상위 등급 → 누출 금지
    assert "a_quar" not in names              # 격리 → 누출 금지


async def test_higher_clearance_reveals_restricted(db_pool):
    async with db_pool.acquire() as conn:
        a1 = await _seed(conn)
    repo = PostgresGraphRepository(db_pool)

    sg = await repo.get_neighbors(a1, hops=2, tenant="default", clearance="RESTRICTED")
    names = _names(sg)
    assert "a_secret" in names                # 필터는 좁힐 뿐, 등급을 올리면 보인다
    assert "b1" not in names                  # 그래도 타 테넌트는 여전히 차단
    assert "a_quar" not in names              # 격리는 등급과 무관하게 차단


async def test_evidence_channel_excludes_out_of_scope_chunk_content(db_pool):
    """`GET /graph/{rid}?include_evidence=true` 의 증거 쿼리(§4.3)가 스코프 밖 chunk_text 를 배제한다.

    엔드포인트 배선이 아니라 보안 술어 자체를 증명한다: 같은 edge 에 in-scope/out-of-scope 청크가
    각각 증거로 달렸을 때, base_filter 를 건 쿼리는 in-scope 본문만 돌려준다.
    """
    from nexus.rid import chunk_rid, doc_rid, evidence_rid

    async with db_pool.acquire() as conn:
        a1 = await _ent(conn, "default", "service", "a1")
        a2 = await _ent(conn, "default", "service", "a2")
        e = await _edge(conn, "default", a1, a2)

        async def _evi(tenant, marker):
            d = doc_rid(f"test:{tenant}.md")
            c = chunk_rid(d, "s", 0)
            await conn.execute(
                "INSERT INTO documents (rid, tenant, source_uri, hash, title) "
                "VALUES ($1,$2,'u','h',$3)", d, tenant, f"{tenant}-doc")
            await conn.execute(
                "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, section_path, chunk_text, "
                "chunk_index) VALUES ($1,$2,'u',$3,'s',$4,0)", c, tenant, d, marker)
            await conn.execute(
                "INSERT INTO evidence (rid, tenant, subject_rid, evidence_rid, kind, weight) "
                "VALUES ($1,$2,$3,$4,'text_snippet',0.1)", evidence_rid(e, c), tenant, e, c)

        await _evi("default", "IN-SCOPE-CONTENT")
        await _evi("other", "SECRET-CROSS-TENANT-CONTENT")

        # api.py 의 증거 쿼리와 동일한 술어(§4.3)
        rows = await conn.fetch(
            """SELECT c.chunk_text FROM evidence ev
               JOIN chunks c ON ev.evidence_rid = c.rid
               JOIN documents d ON c.doc_rid = d.rid
               WHERE ev.subject_rid = $1 AND ev.status = 'active'
                 AND c.tenant = $2 AND c.classification <= $3::classification_level
                 AND c.is_quarantined = false AND c.status = 'active' AND d.status = 'active'""",
            e, "default", "INTERNAL",
        )
    texts = {r["chunk_text"] for r in rows}
    assert "IN-SCOPE-CONTENT" in texts
    assert "SECRET-CROSS-TENANT-CONTENT" not in texts     # 타 테넌트 본문 누출 금지


async def test_out_of_scope_seed_yields_empty_no_center_leak(db_pool):
    async with db_pool.acquire() as conn:
        await _seed(conn)
        b1 = entity_rid("other", "service", "b1")
    repo = PostgresGraphRepository(db_pool)

    # 타 테넌트 seed 를 default 스코프로 조회 → 빈 서브그래프, center 이름 누출 없음
    sg = await repo.get_neighbors(b1, hops=2, tenant="default", clearance="INTERNAL")
    assert sg.edges == []
    assert sg.center_name != "b1"             # 이름을 되돌려주지 않는다(rid 폴백)
