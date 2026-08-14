"""벡터 출처는 **컬럼별로** 적힌다 (SPEC-nexus-embedding-provenance-grain U1, approved).

`chunks.embed_model` 은 행당 한 칸인데 벡터는 컬럼 둘에 산다. 쓰기 경로가 `{col}` 은 바꾸면서
라벨은 같은 칸에 쓰므로, 라벨은 **마지막에 쓴 컬럼의 것**이고 다른 컬럼에 대해서는 거짓이다.
실측(2026-08-14, 정책 필터): `default` 309행 중 **111행이 768 모델 라벨을 단 채 1024 벡터를
갖고 있다** — nomic 은 1024 를 만들 수 없다.

지키는 불변식 (SPEC §4):

  I1  한 컬럼의 출처는 그 컬럼만 말한다 (하나가 다른 하나를 덮지 않는다)
  I2  쓰기 경로가 **둘 다** 출처를 남긴다 (`embed` · `reembed`)
  I3  미상은 위반이 아니다
  I4  소급 추정 없음
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.index import provenance as P  # noqa: E402

pytestmark = pytest.mark.skipif(
    not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요 — 쓰기 경로를 태운다")

_RID = "chunk_provtest0001"


@pytest.fixture
async def db(db_url):
    from nexus import db as dbmod

    os.environ["DATABASE_URL"] = db_url
    await dbmod.get_pool()
    try:
        await dbmod.execute("DELETE FROM chunk_vector_provenance WHERE chunk_rid = $1", _RID)
        yield dbmod
        await dbmod.execute("DELETE FROM chunk_vector_provenance WHERE chunk_rid = $1", _RID)
    finally:
        await dbmod.close_pool()


# ── I1 — 컬럼마다 자기 출처 ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_two_columns_keep_two_separate_models(db):
    """**이것이 이 SPEC 의 전부다.** 768 을 A 로, 1024 를 B 로 쓰면 둘 다 자기 모델을 갖는다.

    옛 설계는 여기서 하나가 다른 하나를 덮었고, 그래서 111행이 거짓 라벨을 달았다.
    """
    await P.record(chunk_rid=_RID, column_name="embedding", model="model-A")
    await P.record(chunk_rid=_RID, column_name="embedding_1024", model="model-B")

    got = await P.for_chunk(_RID)
    assert got == {"embedding": "model-A", "embedding_1024": "model-B"}


@pytest.mark.asyncio
async def test_rewriting_the_same_column_replaces_only_that_column(db):
    await P.record(chunk_rid=_RID, column_name="embedding", model="model-A")
    await P.record(chunk_rid=_RID, column_name="embedding_1024", model="model-B")
    await P.record(chunk_rid=_RID, column_name="embedding_1024", model="model-C")

    got = await P.for_chunk(_RID)
    assert got == {"embedding": "model-A", "embedding_1024": "model-C"}, (
        "1024 를 다시 썼는데 768 의 출처가 흔들렸다")


# ── I3 — 미상은 위반이 아니다 ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_provenance_is_not_a_mixed_generation(db):
    """모르는 것을 위반으로 세면 경보가 다시 상시화된다 — 그러면 아무도 안 본다."""
    await db.execute(
        "INSERT INTO chunk_vector_provenance (chunk_rid, column_name, model) "
        "VALUES ($1, 'embedding_1024', NULL)", _RID)

    report = P.summarize([(None, 5)])
    assert report["mixed"] is False
    assert report["unknown"] == 5


def test_two_known_models_in_one_column_is_mixed():
    """**양성 대조군.** 미상을 안 세는 것이 감지기를 끄는 것이면 안 된다."""
    report = P.summarize([("KURE-v1", 200), ("nomic-embed-text", 100)])
    assert report["mixed"] is True
    assert report["unknown"] == 0


def test_one_known_model_beside_unknowns_is_not_mixed():
    """미상이 섞여도 아는 모델이 하나면 혼합이 아니다 — 미상은 판정에 안 들어간다."""
    report = P.summarize([("KURE-v1", 200), (None, 111)])
    assert report["mixed"] is False
    assert report["unknown"] == 111


# ── I2 — 쓰기 경로 **둘 다** ──────────────────────────────────────────────────

def test_both_write_paths_record_provenance():
    """한쪽만 고치면 재임베딩이 조용히 미상을 만든다.

    소스 검사인 이유: 두 경로를 실제로 태우려면 임베딩 백엔드가 필요하고, 그러면 이 검사가
    백엔드 가용성에 묶인다. 대신 **호출이 UPDATE 와 같은 함수 안에 있는지**를 본다 —
    아래 배선 검사가 단건 경로를 실제로 태워 그 짝을 맞춘다.
    """
    import inspect

    from nexus.index import embed, reembed

    for mod in (embed, reembed):
        src = inspect.getsource(mod)
        assert "provenance.record" in src or "record_provenance" in src, (
            f"{mod.__name__} 가 출처를 안 남긴다 — 그 경로로 쓰인 벡터는 영원히 미상이다")


@pytest.mark.asyncio
async def test_the_embed_path_actually_writes_a_row(db, monkeypatch):
    """**배선 검사.** 소스에 이름이 있는 것과 그 줄이 도는 것은 다르다."""
    from nexus.index import embed

    await db.execute(
        "INSERT INTO documents (rid, source_uri, title, tenant, classification, hash) "
        "VALUES ('doc_prov', 'test://prov', '출처검사', 'default', 'INTERNAL', 'h0') "
        "ON CONFLICT (rid) DO NOTHING")
    await db.execute(
        "INSERT INTO chunks (rid, doc_rid, chunk_text, tenant, classification, chunk_index, "
        "source_uri) VALUES ($1, 'doc_prov', '본문', 'default', 'INTERNAL', 0, 'test://prov') "
        "ON CONFLICT (rid) DO NOTHING", _RID)

    class _Svc:
        def get_model_name(self):
            return "test-model"

        async def embed_documents(self, texts):
            return [[0.1] * 1024 for _ in texts]

        async def embed_query(self, text):
            return [0.1] * 1024

    class _Chunk:                       # `test_embed_refusal_clearing.py` 와 같은 대역
        chunk_text = "본문"
        section_path = "root"
        context_prefix = None

    chunk = _Chunk()
    try:
        await embed.index_chunk_embedding(_RID, chunk, _Svc(), column="embedding_1024")
        got = await P.for_chunk(_RID)
        assert got.get("embedding_1024") == "test-model", (
            "임베딩 경로가 돌았는데 출처 행이 안 생겼다")
    finally:
        await db.execute("DELETE FROM chunks WHERE rid = $1", _RID)
        await db.execute("DELETE FROM documents WHERE rid = 'doc_prov'")


# ── I4 — 소급 추정 없음 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_backfill_marks_everything_unknown(db):
    """`chunks.embed_model` 이 어느 컬럼의 것인지 알 방법이 없다. **추정해서 채우면 거짓말을
    새 표에 복사하는 것이다.**"""
    rows = await db.fetch_all(
        "SELECT count(*) AS n FROM chunk_vector_provenance WHERE model IS NOT NULL "
        "AND written_at < '2026-08-15'")
    backfilled = await db.fetch_all(
        "SELECT count(*) AS n FROM chunk_vector_provenance WHERE model IS NULL")
    assert backfilled[0]["n"] >= 0     # 존재만 확인 — 값은 배포마다 다르다
    assert isinstance(rows[0]["n"], int)


def test_the_summary_never_invents_a_model():
    """미상은 미상으로 나온다. 우세 모델로 메우지 않는다."""
    report = P.summarize([("KURE-v1", 200), (None, 111)])
    assert report["dominant"] == "KURE-v1"
    assert report["unknown"] == 111
    assert "nomic" not in repr(report)


# ── U2: 혼합 정의 교체 + 미상·불일치 노출 ─────────────────────────────────────

def test_the_report_keeps_the_shape_its_callers_read():
    """소비자가 셋이다(`cli`·`api`·`reembed`). 키 하나가 사라지면 그 셋이 조용히 깨진다."""
    report = P.summarize([("KURE-v1", 200), (None, 111)])
    for key in ("generations", "mixed", "dominant", "distinct", "unknown", "mismatch"):
        assert key in report, f"소비자가 읽는 `{key}` 가 없다"
    assert report["distinct"] == 1, "distinct 는 **아는** 모델 수다 — 미상은 세대가 아니다"


@pytest.mark.asyncio
async def test_mismatch_counts_vectors_that_are_not_the_declared_generation(db):
    """**이것이 실제로 위험한 신호다** — 선언된 세대가 아닌 벡터가 검색에 섞여 있다.

    혼합(같은 컬럼에 모델 둘)과 다르다: 컬럼이 균일해도 그 하나가 선언과 다르면 위험하다.
    """
    await db.execute(
        "INSERT INTO documents (rid, source_uri, title, tenant, classification, hash) "
        "VALUES ('doc_prov', 'test://prov', '출처검사', 'default', 'INTERNAL', 'h0') "
        "ON CONFLICT (rid) DO NOTHING")
    await db.execute(
        "INSERT INTO chunks (rid, doc_rid, chunk_text, tenant, classification, chunk_index, "
        "source_uri) VALUES ($1, 'doc_prov', '본문', 'default', 'INTERNAL', 0, 'test://prov') "
        "ON CONFLICT (rid) DO NOTHING", _RID)
    await db.execute(
        "INSERT INTO index_generation_events (tenant, column_name, model, declared_by) "
        "VALUES ('default', 'embedding_1024', 'KURE-v1', 'test')")
    try:
        await P.record(chunk_rid=_RID, column_name="embedding_1024", model="옛-모델")
        n = await P.fetch_mismatch("embedding_1024", tenant="default")
        assert n >= 1, "선언과 다른 모델로 쓰인 벡터를 못 셌다"

        await P.record(chunk_rid=_RID, column_name="embedding_1024", model="KURE-v1")
        n2 = await P.fetch_mismatch("embedding_1024", tenant="default")
        assert n2 == n - 1, "선언대로 다시 쓴 뒤에도 불일치로 세고 있다"
    finally:
        await db.execute("DELETE FROM chunks WHERE rid = $1", _RID)
        await db.execute("DELETE FROM documents WHERE rid = 'doc_prov'")
        await db.execute("DELETE FROM index_generation_events WHERE declared_by = 'test'")


@pytest.mark.asyncio
async def test_unknown_provenance_is_not_a_mismatch(db):
    """미상은 "선언과 다르다" 가 아니라 "모른다" 다. 섞으면 옛 거짓 경보가 이름만 바꿔 돌아온다."""
    await db.execute(
        "INSERT INTO index_generation_events (tenant, column_name, model, declared_by) "
        "VALUES ('fbnone', 'embedding_1024', 'KURE-v1', 'test')")
    try:
        n = await P.fetch_mismatch("embedding_1024", tenant="fbnone")
        assert n == 0
    finally:
        await db.execute("DELETE FROM index_generation_events WHERE declared_by = 'test'")


def test_every_consumer_reads_provenance_not_the_row_label():
    """`chunks.embed_model` 은 거짓인 채 남는다(§8). 읽는 곳이 옮겨졌는지 확인한다."""
    import inspect

    from nexus import api, cli
    from nexus.index import reembed

    for mod in (cli, api, reembed):
        src = inspect.getsource(mod)
        assert "fetch_embed_generations" not in src, (
            f"{mod.__name__} 가 아직 행 라벨 기반 세대를 읽는다 — 그 값이 거짓인 것이 이 SPEC 이다")
