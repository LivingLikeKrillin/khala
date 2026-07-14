"""임베딩 세대 조회 (DB 통합) — SPEC-nexus-embed-generation-drift §5.

fetch_embed_generations 의 WHERE(=idx_chunk_vector 부분술어) + GROUP BY 정확성.
전역 집계라 잔존 데이터에 안전하도록 고유 모델명으로 내 행만 검증한다.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

_DB = os.getenv("NEXUS_TEST_DB_URL")
_VEC = "[" + ",".join(["0"] * 768) + "]"


async def test_fetch_groups_indexed_vectors_and_excludes_out_of_index():
    from nexus import db
    from nexus.index.embed_health import fetch_embed_generations
    os.environ["DATABASE_URL"] = _DB or ""
    await db.get_pool()
    try:
        await db.execute("DELETE FROM chunks WHERE rid LIKE 'eh\\_%'")
        await db.execute("DELETE FROM documents WHERE rid = 'eh_doc'")
        await db.execute(
            "INSERT INTO documents (rid, source_uri, hash) VALUES ('eh_doc','git://eh','h')")
        # A·B: 임베딩된 서로 다른 세대(집계돼야) · null: 임베딩 없음(인덱스 밖) · quar: 격리(제외)
        rows_in = [
            ("eh_a", "eh-test-A", _VEC, False),
            ("eh_b", "eh-test-B", _VEC, False),
            ("eh_null", "eh-test-null", None, False),
            ("eh_quar", "eh-test-quar", _VEC, True),
        ]
        for rid, model, emb, quar in rows_in:
            await db.execute(
                "INSERT INTO chunks (rid, source_uri, doc_rid, chunk_text, embed_model, "
                "embedding, is_quarantined) VALUES ($1,'git://eh','eh_doc','t',$2,$3::vector,$4)",
                rid, model, emb, quar)

        gens = dict(await fetch_embed_generations())
        assert gens.get("eh-test-A") == 1
        assert gens.get("eh-test-B") == 1        # 서로 다른 세대 → GROUP BY 로 분리 집계
        assert "eh-test-null" not in gens        # embedding NULL → 인덱스 밖, 제외
        assert "eh-test-quar" not in gens        # is_quarantined → 제외(WHERE = 인덱스 부분술어)
    finally:
        await db.execute("DELETE FROM chunks WHERE rid LIKE 'eh\\_%'")
        await db.execute("DELETE FROM documents WHERE rid = 'eh_doc'")
        await db.close_pool()
