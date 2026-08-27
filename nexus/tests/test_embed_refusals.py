"""임베딩 거부를 **행으로** 남긴다 (KOREAN_SEARCH_QUALITY.md §3.2).

`index/embed.py` 는 예외를 삼키고 `False` 를 돌려줬다. 그래서 벡터 다리에서 영구히 사라진 청크가
아무 데도 남지 않았다 — 2026-08-07 에 정책 문서의 18,751자 청크가 `413 max_seq_length(8192)` 로
거부되면서 실물에서 터졌다.

**`embed_waivers` 와 섞지 않는다.** 그건 사람이 이름을 걸고 포기한 *결정*이라 자동으로 만들어지지
않는다(마이그레이션 008 이 그렇게 못박았다). 이건 기계가 낸 *사실*이고, 다음 시도가 성공하면
사라져야 한다.
"""

from __future__ import annotations

import pytest

from nexus.index import embed as embed_mod


class _Svc:
    def __init__(self, name="KURE-v1", fail=None, vectors=None):
        self._name, self._fail, self._vectors = name, fail, vectors

    def get_model_name(self):
        return self._name

    async def embed_documents(self, texts):
        if self._fail:
            raise self._fail
        return self._vectors if self._vectors is not None else [[0.1] * 4]


class _Chunk:
    def __init__(self, text="본문"):
        self.chunk_text, self.section_path, self.context_prefix = text, "root", None


@pytest.fixture()
def calls(monkeypatch):
    """`db.execute` 를 가로채 어떤 SQL 이 나갔는지 본다."""
    seen: list[tuple[str, tuple]] = []

    async def _execute(sql, *args):
        seen.append((sql, args))
        return "OK"

    monkeypatch.setattr(embed_mod.db, "execute", _execute)
    monkeypatch.setattr(embed_mod, "configured_column", lambda *a, **k: "embedding_1024")
    return seen


@pytest.mark.asyncio
async def test_a_refusal_is_recorded_with_the_backend_message_verbatim(calls):
    """사유가 곧 처방이다 — `413 max_seq_length` 는 청킹을 고치라는 말이고, 인코딩 오류는 다른
    처방이다. 요약하면 그 구분이 사라진다."""
    msg = "Client error '413 Request Entity Too Large' for url 'http://nexus-embed:8080/embed'"
    ok = await embed_mod.index_chunk_embedding(
        "chunk_x", _Chunk("가" * 18751), _Svc(fail=RuntimeError(msg)))
    assert ok is False

    inserts = [c for c in calls if "embed_refusals" in c[0] and "INSERT" in c[0]]
    assert len(inserts) == 1, "거부가 행으로 남지 않았다"
    args = inserts[0][1]
    assert args[0] == "chunk_x"
    assert args[1] == "embedding_1024", "세대별로 다르게 거부될 수 있다"
    assert args[2] == "KURE-v1"
    assert msg in args[3], "백엔드 메시지를 그대로 남긴다"
    assert args[4] > 18000, "길이는 처방을 고르는 데 쓰인다"


@pytest.mark.asyncio
async def test_an_empty_result_is_also_a_refusal(calls):
    """예외가 아니라 빈 결과로 돌아오는 백엔드도 있다 — 그것도 청크가 사라지는 것은 같다."""
    ok = await embed_mod.index_chunk_embedding("chunk_y", _Chunk(), _Svc(vectors=[]))
    assert ok is False
    assert any("embed_refusals" in c[0] and "INSERT" in c[0] for c in calls)


@pytest.mark.asyncio
async def test_a_successful_retry_clears_the_old_refusal(calls):
    """지우지 않으면 고쳐진 청크가 계속 병들어 보인다."""
    ok = await embed_mod.index_chunk_embedding("chunk_z", _Chunk(), _Svc())
    assert ok is True
    deletes = [c for c in calls if "DELETE" in c[0] and "embed_refusals" in c[0]]
    assert len(deletes) == 1
    assert deletes[0][1] == ("chunk_z", "embedding_1024")
    assert not any("INSERT" in c[0] and "embed_refusals" in c[0] for c in calls)


@pytest.mark.asyncio
async def test_recording_never_breaks_indexing(monkeypatch):
    """진단이 진단 대상을 죽이면 안 된다 — 기록이 실패해도 색인 결과는 그대로여야 한다."""
    async def _boom(sql, *args):
        raise RuntimeError("embed_refusals 테이블이 없다")

    monkeypatch.setattr(embed_mod.db, "execute", _boom)
    monkeypatch.setattr(embed_mod, "configured_column", lambda *a, **k: "embedding_1024")

    ok = await embed_mod.index_chunk_embedding("c", _Chunk(), _Svc(fail=RuntimeError("nope")))
    assert ok is False, "기록 실패가 결과를 바꾸지 않는다"


def test_refusals_are_written_to_their_own_table_not_the_waiver_list(calls):
    """008 의 규율: waiver 는 사람이 이름을 걸고 만든다. 자동 기록이 그 표에 들어가면
    '포기했다' 와 '이번에 실패했다' 가 구분되지 않는다.

    측정하는 것은 주석이 아니라 **나간 SQL** 이다 — 주석에서 waiver 를 설명하는 것은 옳다.
    """
    import asyncio

    asyncio.run(embed_mod.record_refusal("c", "embedding_1024", _Svc(), "413", 18751))
    sql = " ".join(c[0] for c in calls)
    assert "embed_refusals" in sql
    assert "embed_waivers" not in sql
