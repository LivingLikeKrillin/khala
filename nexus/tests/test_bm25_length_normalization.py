"""키워드 다리의 길이 정규화 — 짧은 문서가 긴 문서에 밀려 잘려나가지 않게 한다.

`SPEC-nexus-bm25-length-normalization` (초안). 측정은
`tests/eval/bm25-normalization/README.md` 에 있고, 사전등록한 바는 "파편이 오르고 대조군이
안 떨어질 것" 이었다.

**왜 이 검사가 있나.** `ts_rank_cd` 를 정규화 없이 쓰면 커버 밀도가 매치 수에 비례해 **긴
청크가 이긴다.** 2026-08-26 라이브 실측: 매칭 140건 중 1위가 1,228자(4.700), 정답인 19자
행은 48위(0.400). 못 찾은 것이 아니라 `bm25_top_k` 밖으로 밀린 것이고, 그래서 RRF 에
한쪽 다리 점수만 들고 들어가 융합에서 탈락했다.
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

DB_URL = os.getenv("NEXUS_TEST_DB_URL")


def test_the_flag_is_declared_and_used():
    """상수가 선언돼 있고 **쿼리가 실제로 그것을 넘긴다.**

    상수만 두고 SQL 이 안 받으면 값은 0 이다 — 이 리포가 여러 번 밟은 "쓰기는 있고 읽기가
    없다" 의 가장 작은 판이다.
    """
    from nexus.search import hybrid

    assert hybrid.BM25_LENGTH_NORMALIZATION == 1
    src = hybrid._bm25_search.__doc__ or ""
    assert src is not None
    import inspect
    body = inspect.getsource(hybrid._bm25_search)
    assert "ts_rank_cd(c.tsvector_ko, to_tsquery('simple', $1)," in body
    assert "BM25_LENGTH_NORMALIZATION" in body


@pytest.mark.skipif(not DB_URL, reason="NEXUS_TEST_DB_URL 필요")
def test_normalisation_shifts_score_toward_the_short_exact_row():
    """행동으로 확인한다 — 정규화가 **짧은 청크 쪽으로 점수 비율을 옮긴다.**

    ⚠ *"짧은 행이 긴 문서를 이긴다"* 는 단언은 **쓰지 않는다.** `1` 은 `1 + log(길이)` 로
    나누는 완만한 감쇠라 어휘를 40번 반복한 문서는 여전히 이길 수 있고, 라이브에서도 파편
    Recall 은 0.111 → 0.444 로 *일부만* 올랐다. 픽스처를 통과할 때까지 손보면 그 검사는
    코드가 아니라 픽스처를 지키게 된다.

    대신 **기제**를 단언한다: 짧은쪽/긴쪽 점수 비율이 정규화를 켜면 반드시 커진다. 이 성질은
    `1` 이 하는 일의 정의 그대로이고, 인자가 쿼리에 안 닿으면 두 비율이 같아져 깨진다.
    """
    from nexus import db

    loop = asyncio.SelectorEventLoop() if sys.platform == "win32" else asyncio.new_event_loop()

    async def inner():
        import asyncpg
        from nexus.index.bm25 import active_tokenizer, index_chunk_bm25, tokens_to_tsquery
        from nexus.search import hybrid

        pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=2)
        db._pool = pool
        try:
            async with pool.acquire() as con:
                await con.execute("TRUNCATE documents, chunks CASCADE")
                await con.execute(
                    "INSERT INTO documents (rid, tenant, source_uri, hash, title, status) "
                    "VALUES ('doc_s','acme','seed:s.md','h','짧은 표 행','active'),"
                    "       ('doc_l','acme','seed:l.md','h','긴 안내 문서','active')")

            class _C:
                def __init__(self, text, prefix):
                    self.chunk_text, self.section_path, self.context_prefix = text, "root", prefix

            short = _C("- **디제잉 포인트**: 4000", "[디제잉 아바타 10]")
            long_doc = _C("아바타 해금 안내. " + "아바타 포인트 해금 아바타 포인트 " * 40,
                          "[긴 안내 문서]")
            for rid, doc, c in (("chunk_s", "doc_s", short), ("chunk_l", "doc_l", long_doc)):
                async with pool.acquire() as con:
                    await con.execute(
                        "INSERT INTO chunks (rid, tenant, source_uri, doc_rid, section_path, "
                        "chunk_text, context_prefix) VALUES ($1,'acme',$2,$3,'root',$4,$5)",
                        rid, f"seed:{doc}.md", doc, c.chunk_text, c.context_prefix)
                await index_chunk_bm25(rid, c)

            tsq = tokens_to_tsquery(active_tokenizer().tokenize("아바타 10 포인트"))
            ratios = {}
            for norm in (0, hybrid.BM25_LENGTH_NORMALIZATION):
                rows = await db.fetch_all(
                    "SELECT rid, ts_rank_cd(tsvector_ko, to_tsquery('simple',$1), $2) AS s "
                    "FROM chunks WHERE tenant='acme' AND tsvector_ko @@ to_tsquery('simple',$1)",
                    tsq, norm)
                sc = {r["rid"]: float(r["s"]) for r in rows}
                assert sc.get("chunk_s") and sc.get("chunk_l"), f"둘 다 매칭돼야 한다: {sc}"
                ratios[norm] = sc["chunk_s"] / sc["chunk_l"]

            assert ratios[hybrid.BM25_LENGTH_NORMALIZATION] > ratios[0], (
                f"정규화가 점수 비율을 안 옮겼다: {ratios} — 인자가 쿼리에 안 닿았을 수 있다")

            # 그리고 그 인자로 실제 프로덕션 경로가 돈다(예외 없이, 둘 다 반환).
            hits, _top = await hybrid._bm25_search("아바타 10 포인트", "acme", "INTERNAL", 10)
            assert {rid for rid, _ in hits} == {"chunk_s", "chunk_l"}
        finally:
            await pool.close()
            db._pool = None

    try:
        loop.run_until_complete(inner())
    finally:
        loop.close()
