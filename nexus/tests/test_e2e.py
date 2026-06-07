"""인프라 통합 테스트 — 실제 PostgreSQL + pgvector 대상.

실행 조건:
    1. docker compose -f docker-compose.test.yml up -d
    2. KHALA_TEST_DB_URL=postgresql://khala:khala@localhost:5433/khala_test pytest tests/test_e2e.py -v

테스트 시나리오:
    - CRM 모델 CRUD
    - search_text GENERATED 컬럼
    - pgvector 스키마
    - Graph 관계 + evidence
    - Quarantine 격리
    - Diff 뷰
    - Classification 필터
    - 멀티 테넌트 격리
"""

from __future__ import annotations

import pytest

from khala.rid import (
    doc_rid, chunk_rid, entity_rid, edge_rid, evidence_rid,
    observed_edge_rid, canonicalize_entity_name,
)

pytestmark = pytest.mark.integration


class TestDocumentCRUD:
    """문서/청크 기본 CRUD."""

    async def test_insert_document(self, db_pool):
        d_rid = doc_rid("test:payment.md")
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents (rid, tenant, source_uri, hash, title, doc_type)
                VALUES ($1, 'default', 'test:payment.md', 'abc123', '결제 서비스 설계', 'markdown')
                """,
                d_rid,
            )
            row = await conn.fetchrow("SELECT * FROM documents WHERE rid = $1", d_rid)
            assert row is not None
            assert row["title"] == "결제 서비스 설계"
            assert row["status"] == "active"
            assert row["is_quarantined"] is False

    async def test_insert_chunk_with_search_text(self, db_pool):
        """search_text GENERATED 컬럼이 정상 생성되는지."""
        d_rid = doc_rid("test:search-text.md")
        c_rid = chunk_rid(d_rid, "아키텍처 > 이벤트", 0)

        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents (rid, tenant, source_uri, hash, title)
                VALUES ($1, 'default', 'test:search-text.md', 'h1', '테스트 문서')
                """,
                d_rid,
            )
            await conn.execute(
                """
                INSERT INTO chunks (rid, tenant, source_uri, doc_rid, section_path, chunk_text, chunk_index)
                VALUES ($1, 'default', 'test:search-text.md', $2, '아키텍처 > 이벤트',
                        'payment.completed 이벤트를 Kafka로 발행한다', 0)
                """,
                c_rid, d_rid,
            )
            row = await conn.fetchrow("SELECT search_text FROM chunks WHERE rid = $1", c_rid)
            assert row is not None
            assert "[아키텍처 > 이벤트]" in row["search_text"]
            assert "payment.completed" in row["search_text"]

    async def test_context_prefix_overrides_section_path(self, db_pool):
        """context_prefix가 있으면 search_text에 반영."""
        d_rid = doc_rid("test:ctx-prefix.md")
        c_rid = chunk_rid(d_rid, "원래 경로", 0)

        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO documents (rid, tenant, source_uri, hash, title) VALUES ($1, 'default', 'test:ctx.md', 'h2', 'ctx')",
                d_rid,
            )
            await conn.execute(
                """
                INSERT INTO chunks (rid, tenant, source_uri, doc_rid, section_path, chunk_text, context_prefix, chunk_index)
                VALUES ($1, 'default', 'test:ctx.md', $2, '원래 경로', '본문 텍스트', '[커스텀 접두사]', 0)
                """,
                c_rid, d_rid,
            )
            row = await conn.fetchrow("SELECT search_text FROM chunks WHERE rid = $1", c_rid)
            assert "[커스텀 접두사]" in row["search_text"]
            assert "[원래 경로]" not in row["search_text"]


class TestQuarantine:
    """격리 정책 검증."""

    async def test_quarantined_excluded_from_index(self, db_pool):
        """is_quarantined=true인 청크는 base_filter 조건에서 제외."""
        d_rid = doc_rid("test:quarantine.md")
        c_rid = chunk_rid(d_rid, "민감", 0)

        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO documents (rid, tenant, source_uri, hash, title) VALUES ($1, 'default', 'test:q.md', 'hq', 'q')",
                d_rid,
            )
            await conn.execute(
                """
                INSERT INTO chunks (rid, tenant, source_uri, doc_rid, section_path, chunk_text,
                                    chunk_index, is_quarantined)
                VALUES ($1, 'default', 'test:q.md', $2, '민감', 'PII 포함 텍스트', 0, true)
                """,
                c_rid, d_rid,
            )

            row = await conn.fetchrow(
                """
                SELECT rid FROM chunks
                WHERE tenant = 'default'
                  AND is_quarantined = false
                  AND status = 'active'
                  AND rid = $1
                """,
                c_rid,
            )
            assert row is None


class TestGraph:
    """Graph 관계 + Evidence 테스트."""

    async def _setup_entities(self, conn):
        name_a = canonicalize_entity_name("payment-service", "Service")
        name_b = canonicalize_entity_name("notification-service", "Service")
        rid_a = entity_rid("default", "Service", name_a)
        rid_b = entity_rid("default", "Service", name_b)

        await conn.execute(
            "INSERT INTO entities (rid, tenant, entity_type, name) VALUES ($1, 'default', 'Service', $2)",
            rid_a, name_a,
        )
        await conn.execute(
            "INSERT INTO entities (rid, tenant, entity_type, name) VALUES ($1, 'default', 'Service', $2)",
            rid_b, name_b,
        )
        return rid_a, rid_b, name_a, name_b

    async def test_edge_with_evidence(self, db_pool):
        """Edge 생성 시 evidence 바인딩."""
        async with db_pool.acquire() as conn:
            rid_a, rid_b, _, _ = await self._setup_entities(conn)
            e_rid = edge_rid("default", "CALLS", rid_a, rid_b)

            d_rid = doc_rid("test:edge-evidence.md")
            c_rid = chunk_rid(d_rid, "관계", 0)
            await conn.execute(
                "INSERT INTO documents (rid, tenant, source_uri, hash, title) VALUES ($1, 'default', 'test:ee.md', 'he', 'ee')",
                d_rid,
            )
            await conn.execute(
                "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, section_path, chunk_text, chunk_index) VALUES ($1, 'default', 'test:ee.md', $2, '관계', 'A가 B를 호출', 0)",
                c_rid, d_rid,
            )

            await conn.execute(
                "INSERT INTO edges (rid, tenant, edge_type, from_rid, to_rid, confidence) VALUES ($1, 'default', 'CALLS', $2, $3, 0.9)",
                e_rid, rid_a, rid_b,
            )

            ev_rid = evidence_rid(e_rid, c_rid)
            await conn.execute(
                "INSERT INTO evidence (rid, tenant, subject_rid, evidence_rid, kind, weight) VALUES ($1, 'default', $2, $3, 'text_snippet', 0.15)",
                ev_rid, e_rid, c_rid,
            )

            row = await conn.fetchrow(
                "SELECT * FROM evidence WHERE subject_rid = $1 AND status = 'active'", e_rid,
            )
            assert row is not None
            assert row["evidence_rid"] == c_rid

    async def test_graph_neighbors_function(self, db_pool):
        """f_graph_neighbors DB 함수 동작 확인."""
        async with db_pool.acquire() as conn:
            rid_a, rid_b, _, _ = await self._setup_entities(conn)
            e_rid = edge_rid("default", "CALLS", rid_a, rid_b)

            await conn.execute(
                "INSERT INTO edges (rid, tenant, edge_type, from_rid, to_rid, confidence) VALUES ($1, 'default', 'CALLS', $2, $3, 0.85)",
                e_rid, rid_a, rid_b,
            )

            rows = await conn.fetch("SELECT * FROM f_graph_neighbors($1, 1)", rid_a)
            assert len(rows) >= 1
            assert rows[0]["edge_type"] == "CALLS"

    async def test_observed_edge(self, db_pool):
        """관측 edge 삽입 및 조회."""
        async with db_pool.acquire() as conn:
            rid_a, rid_b, _, _ = await self._setup_entities(conn)
            o_rid = observed_edge_rid("default", "CALLS_OBSERVED", rid_a, rid_b)

            await conn.execute(
                """
                INSERT INTO observed_edges (rid, tenant, edge_type, from_rid, to_rid,
                    call_count, error_rate, latency_p50, latency_p95)
                VALUES ($1, 'default', 'CALLS_OBSERVED', $2, $3, 1500, 0.02, 45.0, 120.0)
                """,
                o_rid, rid_a, rid_b,
            )

            row = await conn.fetchrow("SELECT * FROM observed_edges WHERE rid = $1", o_rid)
            assert row["call_count"] == 1500
            assert row["error_rate"] == pytest.approx(0.02)


class TestDiffView:
    """v_edge_diff 뷰 테스트."""

    async def test_doc_only_diff(self, db_pool):
        """설계에만 존재하는 edge → doc_only."""
        async with db_pool.acquire() as conn:
            name_x = canonicalize_entity_name("order-service", "Service")
            name_y = canonicalize_entity_name("inventory-service", "Service")
            rid_x = entity_rid("default", "Service", name_x)
            rid_y = entity_rid("default", "Service", name_y)

            await conn.execute(
                "INSERT INTO entities (rid, tenant, entity_type, name) VALUES ($1, 'default', 'Service', $2)",
                rid_x, name_x,
            )
            await conn.execute(
                "INSERT INTO entities (rid, tenant, entity_type, name) VALUES ($1, 'default', 'Service', $2)",
                rid_y, name_y,
            )

            e_rid = edge_rid("default", "CALLS", rid_x, rid_y)
            await conn.execute(
                "INSERT INTO edges (rid, tenant, edge_type, from_rid, to_rid, confidence) VALUES ($1, 'default', 'CALLS', $2, $3, 0.8)",
                e_rid, rid_x, rid_y,
            )

            rows = await conn.fetch("SELECT * FROM v_edge_diff WHERE diff_type = 'doc_only'")
            found = any(r["from_name"] == name_x and r["to_name"] == name_y for r in rows)
            assert found, "doc_only diff에 order→inventory edge가 포함되어야 함"

    async def test_observed_only_diff(self, db_pool):
        """관측에만 존재하는 edge → observed_only."""
        async with db_pool.acquire() as conn:
            name_p = canonicalize_entity_name("auth-service", "Service")
            name_q = canonicalize_entity_name("cache-service", "Service")
            rid_p = entity_rid("default", "Service", name_p)
            rid_q = entity_rid("default", "Service", name_q)

            await conn.execute(
                "INSERT INTO entities (rid, tenant, entity_type, name) VALUES ($1, 'default', 'Service', $2)",
                rid_p, name_p,
            )
            await conn.execute(
                "INSERT INTO entities (rid, tenant, entity_type, name) VALUES ($1, 'default', 'Service', $2)",
                rid_q, name_q,
            )

            o_rid = observed_edge_rid("default", "CALLS_OBSERVED", rid_p, rid_q)
            await conn.execute(
                """
                INSERT INTO observed_edges (rid, tenant, edge_type, from_rid, to_rid, call_count, error_rate)
                VALUES ($1, 'default', 'CALLS_OBSERVED', $2, $3, 500, 0.01)
                """,
                o_rid, rid_p, rid_q,
            )

            rows = await conn.fetch("SELECT * FROM v_edge_diff WHERE diff_type = 'observed_only'")
            found = any(r["from_name"] == name_p and r["to_name"] == name_q for r in rows)
            assert found, "observed_only diff에 auth→cache edge가 포함되어야 함"


class TestClassificationFilter:
    """classification 레벨 기반 필터링."""

    async def test_restricted_excluded_at_internal(self, db_pool):
        d_rid = doc_rid("test:restricted.md")
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents (rid, tenant, source_uri, hash, title, classification)
                VALUES ($1, 'default', 'test:restricted.md', 'hr', 'restricted doc', 'RESTRICTED')
                """,
                d_rid,
            )

            row = await conn.fetchrow(
                """
                SELECT rid FROM documents
                WHERE rid = $1 AND tenant = 'default'
                  AND classification <= 'INTERNAL'::classification_level
                  AND is_quarantined = false AND status = 'active'
                """,
                d_rid,
            )
            assert row is None

    async def test_public_visible_at_internal(self, db_pool):
        d_rid = doc_rid("test:public.md")
        async with db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO documents (rid, tenant, source_uri, hash, title, classification)
                VALUES ($1, 'default', 'test:public.md', 'hp', 'public doc', 'PUBLIC')
                """,
                d_rid,
            )

            row = await conn.fetchrow(
                """
                SELECT rid FROM documents
                WHERE rid = $1 AND tenant = 'default'
                  AND classification <= 'INTERNAL'::classification_level
                  AND is_quarantined = false AND status = 'active'
                """,
                d_rid,
            )
            assert row is not None


class TestTenantIsolation:
    """멀티 테넌트 격리."""

    async def test_different_tenants_isolated(self, db_pool):
        d_rid_a = doc_rid("team-a:doc.md")
        d_rid_b = doc_rid("team-b:doc.md")

        async with db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO documents (rid, tenant, source_uri, hash, title) VALUES ($1, 'team-a', 'a:doc.md', 'ha', 'A doc')",
                d_rid_a,
            )
            await conn.execute(
                "INSERT INTO documents (rid, tenant, source_uri, hash, title) VALUES ($1, 'team-b', 'b:doc.md', 'hb', 'B doc')",
                d_rid_b,
            )

            rows = await conn.fetch(
                "SELECT rid FROM documents WHERE tenant = 'team-a' AND status = 'active'"
            )
            rids = [r["rid"] for r in rows]
            assert d_rid_a in rids
            assert d_rid_b not in rids
