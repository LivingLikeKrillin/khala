"""적재가 남긴 구멍을 누가 말하는가 — REAL Postgres. SPEC-nexus-index-completeness §6-4·§6-5.

2026-08-10 에 51개 청크가 벡터 다리에서 빠진 채 적재가 끝났고, 요약은 정상으로 보였다.
여기서 못박는 두 가지:

* **부분 실패** — 배치 하나만 터졌을 때 보고되는 구멍이 정확히 그 배치만큼인가. 전부 터지는
  경우만 시험하면 이 경로는 깨진 채로 초록이 된다 (§6-4).
* **프로세스가 죽어도** — 적재 프로세스 없이, 상태만 보고 같은 답이 나오는가. 그 실행이 예외를
  냈는지 죽었는지는 **끝내 확인되지 않았고**(§2.5), 그래서 보장이 프로세스 밖에 있어야 한다.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(not os.getenv("NEXUS_TEST_DB_URL"), reason="NEXUS_TEST_DB_URL 필요")

_TENANT = "gap_report"
_COL = "embedding_1024"


@pytest.fixture
async def clean(db_pool):
    from nexus import db

    db._pool = db_pool
    async with db_pool.acquire() as con:
        await con.execute("DELETE FROM chunks WHERE tenant=$1", _TENANT)
        await con.execute("DELETE FROM documents WHERE tenant=$1", _TENANT)
    yield
    db._pool = None


class _HalfDeadEmbedder:
    """첫 배치는 벡터를 주고, 그 다음부터는 터진다 — 관측된 사고의 모양 그대로."""

    def __init__(self, dimensions: int = 1024):
        self.dimensions = dimensions
        self.calls = 0
        self.served = 0

    def get_model_name(self) -> str:
        return "KURE-v1"

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError("사이드카가 죽었다")
        self.served += len(texts)
        return [[0.0] * self.dimensions for _ in texts]


async def _write_docs(tmp_path, n: int) -> None:
    for i in range(n):
        (tmp_path / f"doc{i}.md").write_text(
            f"---\ntitle: 문서 {i}\n---\n\n## 절\n\n본문 {i} 입니다.\n", encoding="utf-8")


async def test_partial_failure_reports_exactly_what_it_left_behind(clean, tmp_path, monkeypatch):
    """§6-4 — 살아남은 배치는 채워지고, 터진 배치만 구멍으로 보고된다."""
    from nexus.ingest.pipeline import run_ingest

    svc = _HalfDeadEmbedder()
    monkeypatch.setattr("nexus.providers.embedding.embedding_service_from_config",
                        lambda *_a, **_k: svc)
    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", _COL)

    await _write_docs(tmp_path, 25)
    result = await run_ingest(str(tmp_path), force=True, tenant=_TENANT, skip_graph=True)

    assert svc.calls > 1, "배치가 하나뿐이면 부분 실패를 측정하는 시험이 아니다"
    assert result.coverage is not None, "인덱싱이 터져도 커버리지는 측정해야 한다"
    active, embedded = result.coverage["active"], result.coverage[_COL]
    assert 0 < embedded < active, "일부만 채워진 상태여야 한다"
    assert embedded == svc.served
    assert result.coverage["gap_1024"] == active - svc.served


async def test_the_gap_is_answerable_without_the_ingest_process(clean, tmp_path, monkeypatch):
    """§6-5 — 적재 프로세스가 없어도 같은 수가 나온다. §2.5 의 결론이 이것이다."""
    from nexus.index.embed_health import fetch_coverage_by_tenant
    from nexus.ingest.pipeline import run_ingest

    svc = _HalfDeadEmbedder()
    monkeypatch.setattr("nexus.providers.embedding.embedding_service_from_config",
                        lambda *_a, **_k: svc)
    monkeypatch.setenv("NEXUS_EMBEDDING_COLUMN", _COL)

    await _write_docs(tmp_path, 25)
    result = await run_ingest(str(tmp_path), force=True, tenant=_TENANT, skip_graph=True)

    # 적재가 돌려준 값은 **버린다.** 상태만 보고 다시 묻는다 — 죽은 프로세스가 남기는 것이 상태다.
    from_state = next(r for r in await fetch_coverage_by_tenant() if r["tenant"] == _TENANT)
    assert from_state["gap_1024"] == result.coverage["gap_1024"] > 0
