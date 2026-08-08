"""고쳐진 청크는 병들어 보이면 안 된다.

`embed_refusals` 는 기계가 낸 사실이고 **재시도가 성공하면 사라져야 한다**(migration 010 의 계약).
단건 경로는 그렇게 했는데 배치 경로는 안 했고, **적재는 배치를 탄다.** 2026-08-08 에 실물에서
드러났다: 18,854자 청크를 잘라 임베딩까지 성공했는데 거부 행이 남아 코퍼스 뷰가 없는 문제를
계속 보고했다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nexus.index import embed as embed_mod  # noqa: E402


class _Svc:
    def get_model_name(self):
        return "KURE-v1"

    async def embed_documents(self, texts):
        return [[0.1, 0.2] for _ in texts]


class _Chunk:
    chunk_text = "본문"
    section_path = "root"
    context_prefix = None


@pytest.fixture
def spy(monkeypatch):
    cleared: list[tuple[str, str]] = []

    async def _clear(rid, col):
        cleared.append((rid, col))

    async def _exec(*a, **k):
        return None

    monkeypatch.setattr(embed_mod, "clear_refusal", _clear)
    monkeypatch.setattr(embed_mod.db, "execute", _exec)
    return cleared


@pytest.mark.asyncio
async def test_the_batch_path_clears_the_refusal(spy):
    """**이것이 빠져 있던 것.** 적재가 타는 경로다."""
    n = await embed_mod.index_chunks_embedding(
        [("chunk_a", _Chunk()), ("chunk_b", _Chunk())], _Svc(), column="embedding_1024")
    assert n == 2
    assert spy == [("chunk_a", "embedding_1024"), ("chunk_b", "embedding_1024")]


@pytest.mark.asyncio
async def test_the_single_path_still_clears_it(spy):
    ok = await embed_mod.index_chunk_embedding("chunk_c", _Chunk(), _Svc(),
                                               column="embedding_1024")
    assert ok is True
    assert ("chunk_c", "embedding_1024") in spy


@pytest.mark.asyncio
async def test_nothing_is_cleared_when_the_backend_returns_no_vector(monkeypatch, spy):
    """실패했는데 지우면 거부 기록이 영영 안 쌓인다 — 반대 방향."""
    class _Empty(_Svc):
        async def embed_documents(self, texts):
            return []

    async def _record(*a, **k):
        return None

    monkeypatch.setattr(embed_mod, "record_refusal", _record)
    ok = await embed_mod.index_chunk_embedding("chunk_d", _Chunk(), _Empty(),
                                               column="embedding_1024")
    assert ok is False and spy == []
