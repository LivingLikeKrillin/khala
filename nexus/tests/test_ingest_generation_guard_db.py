"""적재가 세대 선언에 복종하는가 — REAL Postgres. SPEC-nexus-generation-of-record §6-3·4·7·8.

2026-08-10 의 사고를 고친 코드에 대고 다시 재현한다: 호스트가 해석한 768 세대로 1024 코퍼스에
적재하려 하면 **아무것도 쓰지 않고** 멈춰야 한다.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_T = "guard_test"


@pytest.fixture
async def clean(db_pool):
    from nexus import db

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM index_generation_events WHERE tenant = $1", _T)
        await con.execute("DELETE FROM chunks WHERE tenant = $1", _T)
        await con.execute("DELETE FROM documents WHERE tenant = $1", _T)
    yield
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM index_generation_events WHERE tenant = $1", _T)
    db._pool = None


class _Embedder:
    """차원·이름을 인자로 받는 가짜. 어느 세대인 척할지가 이 시험의 변수다."""

    def __init__(self, model: str, dimensions: int):
        self.model, self.dimensions = model, dimensions

    def get_model_name(self) -> str:
        return self.model

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dimensions for _ in texts]


async def _counts() -> tuple[int, int]:
    from nexus import db

    docs = await db.fetch_val("SELECT count(*) FROM documents WHERE tenant = $1", _T)
    chunks = await db.fetch_val("SELECT count(*) FROM chunks WHERE tenant = $1", _T)
    return int(docs or 0), int(chunks or 0)


def _write(tmp_path, body: str = "본문 첫 판.") -> None:
    (tmp_path / "note.md").write_text(f"---\ntitle: 노트\n---\n\n## 절\n\n{body}\n",
                                      encoding="utf-8")


async def test_a_mismatched_generation_refuses_before_writing_anything(clean, tmp_path,
                                                                       monkeypatch):
    """§6-4 — 오류가 났는지가 아니라 **행이 안 생겼는지**를 단언한다."""
    from nexus.index import generation as gen
    from nexus.ingest.pipeline import run_ingest

    await gen.declare(_T, "embedding_1024", "KURE-v1", "alice")
    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", "embedding")     # 호스트가 보던 세대
    monkeypatch.setattr("nexus.providers.embedding.embedding_service_from_config",
                        lambda *_a, **_k: _Embedder("nomic-embed-text", 768))

    _write(tmp_path)
    before = await _counts()
    with pytest.raises(gen.GenerationMismatch):
        await run_ingest(str(tmp_path), force=True, tenant=_T, skip_graph=True)
    assert await _counts() == before == (0, 0), "거부는 문서 한 행도 남기지 않는다"


async def test_a_matching_generation_ingests_as_before(clean, tmp_path, monkeypatch):
    """§6-3 — 선언과 같으면 아무것도 달라지지 않는다."""
    from nexus.index import generation as gen
    from nexus.ingest.pipeline import run_ingest

    await gen.declare(_T, "embedding_1024", "KURE-v1", "alice")
    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", "embedding_1024")
    monkeypatch.setattr("nexus.providers.embedding.embedding_service_from_config",
                        lambda *_a, **_k: _Embedder("KURE-v1", 1024))

    _write(tmp_path)
    result = await run_ingest(str(tmp_path), force=True, tenant=_T, skip_graph=True)
    assert result.indexed == 1
    assert (await _counts())[1] > 0


async def test_an_undeclared_tenant_still_ingests(clean, tmp_path, monkeypatch):
    """§3.2 — 업그레이드가 배포를 멈추면 안 된다."""
    from nexus.ingest.pipeline import run_ingest

    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", "embedding")
    monkeypatch.setattr("nexus.providers.embedding.embedding_service_from_config",
                        lambda *_a, **_k: _Embedder("nomic-embed-text", 768))

    _write(tmp_path)
    assert (await run_ingest(str(tmp_path), force=True, tenant=_T, skip_graph=True)).indexed == 1


async def test_changing_the_text_invalidates_every_vector_column(clean, tmp_path, monkeypatch):
    """§6-7·8 — 이것이 낡은 벡터를 만든 결함이다. 레지스트리를 열거해 단언한다."""
    from nexus import db
    from nexus.index.vector_index import VECTOR_COLUMNS
    from nexus.ingest.pipeline import run_ingest

    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", "embedding_1024")
    monkeypatch.setattr("nexus.providers.embedding.embedding_service_from_config",
                        lambda *_a, **_k: _Embedder("KURE-v1", 1024))

    _write(tmp_path, "본문 첫 판.")
    await run_ingest(str(tmp_path), force=True, tenant=_T, skip_graph=True)

    # 두 컬럼을 다 채워 둔다 — 옛 코드가 지우지 않던 쪽이 실제로 지워지는지 보려면 있어야 한다.
    for col, dim in VECTOR_COLUMNS.items():
        await db.execute(
            f"UPDATE chunks SET {col} = $1::vector WHERE tenant = $2",
            "[" + ",".join(["0"] * dim) + "]", _T)
    await db.execute("UPDATE chunks SET tsvector_ko = 'a'::tsvector WHERE tenant = $1", _T)

    _write(tmp_path, "본문이 완전히 달라졌다. 다른 문장이다.")
    await run_ingest(str(tmp_path), force=True, tenant=_T, skip_graph=True, skip_index=True)

    for col in VECTOR_COLUMNS:
        left = await db.fetch_val(
            f"SELECT count(*) FROM chunks WHERE tenant = $1 AND {col} IS NOT NULL", _T)
        assert left == 0, f"{col} 이 옛 텍스트의 벡터를 들고 남았다 — 재임베딩 큐가 못 본다"
    assert await db.fetch_val(
        "SELECT count(*) FROM chunks WHERE tenant = $1 AND tsvector_ko IS NOT NULL", _T) == 0
