"""거부의 **이유**가 사람에게 닿는가 — REAL Postgres. OPEN.md A7.

`embed_refusals` 는 2026-08-07 부터 이유를 그대로 적어 왔다(`413 max_seq_length(8192)` 같은,
곧 처방이 되는 문장). 그런데 **읽는 곳이 코퍼스 뷰 하나뿐이었다.** 적재는 "벡터 경로가 못 보는
청크 N건" 과 "`nexus reembed run` 으로 복구하라" 를 찍는데, 그 재시도는 같은 이유로 다시
실패한다 — 이유를 안 보여줬기 때문에.

세 가지를 못박는다:

* 적재가 남긴 거부의 **이유가 결과에 실린다**(수만이 아니라).
* 다른 테넌트의 거부가 이 수에 섞이지 않는다.
* 재시도가 성공하면 **수가 0으로 돌아온다** — 낡은 거부가 남으면 멀쩡한 코퍼스가 병들어 보인다.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "refusal_reasons"
_OTHER = "refusal_other"
_COL = "embedding_1024"
_REASON = "413 max_seq_length(8192)"


@pytest.fixture
async def clean(db_pool):
    from nexus import db

    db._pool = db_pool
    async with db_pool.acquire() as con:
        for t in (_TENANT, _OTHER):
            await con.execute(
                "DELETE FROM embed_refusals WHERE chunk_rid IN "
                "(SELECT rid FROM chunks WHERE tenant=$1)", t)
            await con.execute("DELETE FROM chunks WHERE tenant=$1", t)
            await con.execute("DELETE FROM documents WHERE tenant=$1", t)
    yield
    db._pool = None


class _RefusingEmbedder:
    """사이드카가 길이를 이유로 거부한다 — 관측된 사고의 모양 그대로."""

    dimensions = 1024

    def get_model_name(self) -> str:
        return "KURE-v1"

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise RuntimeError(_REASON)


class _WorkingEmbedder:
    dimensions = 1024

    def get_model_name(self) -> str:
        return "KURE-v1"

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self.dimensions for _ in texts]


async def _write_docs(tmp_path, n: int) -> None:
    for i in range(n):
        (tmp_path / f"doc{i}.md").write_text(
            f"---\ntitle: 문서 {i}\n---\n\n## 절\n\n본문 {i} 입니다.\n", encoding="utf-8")


async def test_the_ingest_carries_the_reason_not_only_the_count(clean, tmp_path, monkeypatch):
    """수는 "무엇을 할까" 에 답하지 않는다. 이유가 곧 처방이다."""
    from nexus.ingest.pipeline import run_ingest

    monkeypatch.setattr("nexus.providers.embedding.embedding_service_from_config",
                        lambda *_a, **_k: _RefusingEmbedder())
    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", _COL)

    await _write_docs(tmp_path, 3)
    result = await run_ingest(str(tmp_path), force=True, tenant=_TENANT, skip_graph=True)

    assert result.coverage is not None and result.coverage["gap_1024"] > 0, (
        "전제: 이 적재는 구멍을 남겼어야 한다")
    assert result.refusals is not None, "구멍은 보고하면서 그 이유는 안 실었다"
    assert result.refusals["total"] == result.coverage["gap_1024"], (
        "거부된 수와 구멍이 다르면 둘 중 하나가 다른 것을 세고 있다")
    top = result.refusals["reasons"][0]
    assert _REASON in top[0], f"백엔드 메시지가 그대로 오지 않았다: {top[0]!r}"


async def test_another_tenants_refusals_do_not_leak_in(clean, tmp_path, monkeypatch):
    """섞이면 이 수로는 아무 처방도 못 내린다."""
    from nexus import db
    from nexus.index.embed_health import fetch_refusals
    from nexus.ingest.pipeline import run_ingest

    monkeypatch.setattr("nexus.providers.embedding.embedding_service_from_config",
                        lambda *_a, **_k: _RefusingEmbedder())
    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", _COL)

    await _write_docs(tmp_path, 2)
    await run_ingest(str(tmp_path), force=True, tenant=_TENANT, skip_graph=True)

    # 다른 테넌트에 거부 하나를 심는다 — 전역 집계라면 여기서 티가 난다.
    await db.execute(
        "INSERT INTO documents (rid, source_uri, title, tenant, classification, hash) "
        "VALUES ('doc_ro', 'test://ro', '남', $1, 'INTERNAL', 'h')", _OTHER)
    await db.execute(
        "INSERT INTO chunks (rid, doc_rid, chunk_text, tenant, classification, chunk_index, "
        "source_uri) VALUES ('chunk_ro', 'doc_ro', '본문', $1, 'INTERNAL', 0, 'test://ro')", _OTHER)
    await db.execute(
        "INSERT INTO embed_refusals (chunk_rid, column_name, reason) "
        "VALUES ('chunk_ro', $1, '남의 이유')", _COL)

    mine = await fetch_refusals(_COL, tenant=_TENANT)
    everyone = await fetch_refusals(_COL)

    assert all("남의 이유" not in r for r, _ in mine["reasons"])
    assert everyone["total"] > mine["total"], (
        "테넌트를 빼고 물었는데 같은 수가 나왔다 — 필터가 안 걸렸거나 대조군이 안 심겼다")


def test_the_ingest_command_actually_prints_the_reason(tmp_path, monkeypatch):
    """**배선 검사.** 결과 객체가 이유를 들고 있는 것과 사람이 그것을 보는 것은 다르다 —
    이 리포는 "신호는 있는데 전달이 없다" 로 이미 한 번 하루를 잃었다.

    동기 테스트인 이유: CLI 는 자기 이벤트 루프를 연다(`asyncio.run`). 비동기 테스트 안에서
    부르면 루프가 겹쳐 죽고, 그 실패는 이 검사가 측정하려는 것과 아무 상관이 없다.
    """
    import asyncio

    from typer.testing import CliRunner

    from nexus import db
    from nexus.cli import app

    monkeypatch.setenv("DATABASE_URL", os.environ["NEXUS_TEST_DB_URL"])
    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", _COL)
    monkeypatch.setattr("nexus.providers.embedding.embedding_service_from_config",
                        lambda *_a, **_k: _RefusingEmbedder())

    async def _purge() -> None:
        await db.get_pool()
        await db.execute("DELETE FROM embed_refusals WHERE chunk_rid IN "
                         "(SELECT rid FROM chunks WHERE tenant=$1)", _TENANT)
        await db.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await db.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
        await db.close_pool()

    asyncio.run(_purge())
    for i in range(2):
        (tmp_path / f"doc{i}.md").write_text(
            f"---\ntitle: 문서 {i}\n---\n\n## 절\n\n본문 {i} 입니다.\n", encoding="utf-8")
    try:
        result = CliRunner().invoke(
            app, ["ingest", str(tmp_path), "--tenant", _TENANT, "--force", "--no-graph"])
        out = result.stdout + str(result.stderr or "")
        assert "벡터 경로가 못 보는 청크" in out, f"전제: 구멍이 보고돼야 한다\n{out}"
        # **`_REASON in out` 로 쓰면 안 된다.** structlog 가 같은 stdout 으로 `embedding_index_failed`
        # 와 `ingest_left_chunks_unindexed` 를 찍고 거기에도 그 문자열이 들어 있다 — 실제로 이
        # 검사를 그렇게 썼다가, CLI 출력을 **꺼 놓고도 통과**하는 것을 보고 고쳤다. 그러므로
        # CLI 가 자기 손으로 만든 줄의 모양을 본다.
        assert f"거부 2건: {_REASON}" in out, (
            "구멍의 크기만 찍고 이유는 안 찍었다 — 안내한 재시도가 같은 이유로 다시 실패한다\n"
            f"{out}")
    finally:
        asyncio.run(_purge())


async def test_a_successful_retry_takes_the_number_back_to_zero(clean, tmp_path, monkeypatch):
    """낡은 거부가 남으면 고쳐진 코퍼스가 계속 병들어 보인다 (migration 010 의 계약)."""
    from nexus.index.embed_health import fetch_refusals
    from nexus.ingest.pipeline import run_ingest

    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", _COL)
    monkeypatch.setattr("nexus.providers.embedding.embedding_service_from_config",
                        lambda *_a, **_k: _RefusingEmbedder())
    await _write_docs(tmp_path, 2)
    await run_ingest(str(tmp_path), force=True, tenant=_TENANT, skip_graph=True)
    assert (await fetch_refusals(_COL, tenant=_TENANT))["total"] > 0, "전제: 거부가 있어야 한다"

    monkeypatch.setattr("nexus.providers.embedding.embedding_service_from_config",
                        lambda *_a, **_k: _WorkingEmbedder())
    result = await run_ingest(str(tmp_path), force=True, tenant=_TENANT, skip_graph=True)

    assert (await fetch_refusals(_COL, tenant=_TENANT))["total"] == 0
    assert result.refusals["total"] == 0
