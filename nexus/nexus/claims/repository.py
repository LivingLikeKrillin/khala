"""ClaimRepository — claims 테이블 CRUD (asyncpg, CRM 필터).

parameterized query만 사용. base_filter 4요소(tenant/classification/quarantine/status='active')를
asyncpg `$N` + `::classification_level` 캐스트로 직접 작성(base_filter_sql은 psycopg 스타일이라 미사용).
"""

from __future__ import annotations

from nexus.models.claim import Claim


class ClaimRepository:
    def __init__(self, pool):
        self.pool = pool

    async def upsert(self, c: Claim) -> None:
        async with self.pool.acquire() as con:
            await con.execute(
                """
                INSERT INTO claims (
                    rid, rtype, tenant, classification, owner, source_kind, source_uri, hash,
                    status, claim_id, kind, concepts, statement, value_source, value_ref_kind,
                    criticality, activity, claim_status, confidence,
                    value_symbol_hash, last_verified_commit)
                VALUES ($1,'claim',$2,$3::classification_level,$4,'code',$5,$6,
                        'active',$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
                ON CONFLICT (rid) DO UPDATE SET
                    classification=EXCLUDED.classification, owner=EXCLUDED.owner,
                    statement=EXCLUDED.statement, concepts=EXCLUDED.concepts,
                    value_source=EXCLUDED.value_source, value_ref_kind=EXCLUDED.value_ref_kind,
                    criticality=EXCLUDED.criticality, activity=EXCLUDED.activity,
                    claim_status=EXCLUDED.claim_status, confidence=EXCLUDED.confidence,
                    value_symbol_hash=EXCLUDED.value_symbol_hash,
                    last_verified_commit=EXCLUDED.last_verified_commit,
                    hash=EXCLUDED.hash, source_uri=EXCLUDED.source_uri, updated_at=now()
                """,
                c.rid, c.tenant, c.classification, c.owner, c.source_uri, c.hash,
                c.claim_id, c.kind, c.concepts, c.statement, c.value_source,
                c.value_ref_kind, c.criticality, c.activity, c.claim_status,
                c.confidence, c.value_symbol_hash, c.last_verified_commit,
            )

    async def find_by_concept(self, concept: str, tenant: str, clearance: str) -> list[Claim]:
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                """
                SELECT rid, tenant, classification, owner, source_uri, hash, claim_id, kind,
                       concepts, statement, value_source, value_ref_kind, criticality, activity,
                       claim_status, confidence, value_symbol_hash, last_verified_commit
                FROM claims
                WHERE $1 = ANY(concepts)
                  AND tenant = $2
                  AND classification <= $3::classification_level
                  AND is_quarantined = false
                  AND status = 'active'
                """,
                concept, tenant, clearance,
            )
        return [_row_to_claim(r) for r in rows]


    async def find_all(self, tenant: str, clearance: str) -> list[Claim]:
        """테넌트의 활성 claim 전부.

        답변 경로는 개념 하나가 아니라 **문장**을 들고 온다. 그래서 고르기는 파이썬에서
        하고(`claims/matching.py`), 여기서는 범위만 지킨다 — 등급·격리·상태는 SQL 이
        판정한다. 이 표가 커지면 그때 고르기를 SQL 로 내린다.
        """
        async with self.pool.acquire() as con:
            rows = await con.fetch(
                """
                SELECT rid, tenant, classification, owner, source_uri, hash, claim_id, kind,
                       concepts, statement, value_source, value_ref_kind, criticality, activity,
                       claim_status, confidence, value_symbol_hash, last_verified_commit
                FROM claims
                WHERE tenant = $1
                  AND classification <= $2::classification_level
                  AND is_quarantined = false
                  AND status = 'active'
                """,
                tenant, clearance,
            )
        return [_row_to_claim(r) for r in rows]


def _row_to_claim(r) -> Claim:
    return Claim(
        rid=r["rid"], tenant=r["tenant"], classification=r["classification"],
        owner=r["owner"], source_uri=r["source_uri"], hash=r["hash"],
        claim_id=r["claim_id"], kind=r["kind"], concepts=list(r["concepts"]),
        statement=r["statement"], value_source=r["value_source"],
        value_ref_kind=r["value_ref_kind"], criticality=r["criticality"],
        activity=r["activity"], claim_status=r["claim_status"],
        confidence=r["confidence"], value_symbol_hash=r["value_symbol_hash"],
        last_verified_commit=r["last_verified_commit"],
    )
