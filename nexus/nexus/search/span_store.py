"""span 저장. **여기만 asyncpg 를 안다.**

⛔ **부모 커밋이 먼저다.** 자식 제약 위반이 하나라도 나면 다중행 INSERT 가 통째로 중단되는데,
부모와 한 트랜잭션이면 `search_log` 행까지 롤백된다 — 그러면 `spans_expected` 가 남지 않고
"캡처 실패가 보인다" 는 시험이 통과할 수 없다. 그래서 이 함수는 자기만의 트랜잭션에서 돌고,
호출부의 `search_log` INSERT 와는 절대 같은 트랜잭션을 공유하지 않는다.
"""
from __future__ import annotations

import json

import structlog

from nexus import db
from nexus.search.spans import SpanSet

log = structlog.get_logger("nexus.search.span_store")

_INSERT_SPANS = """
INSERT INTO search_span (
    search_log_id, seq, stage, channel, leg, n_in, n_out, fired,
    score_kind, index_generation, candidates_expected, candidates_cap, detail
)
SELECT $1, u.seq, u.stage, u.channel, u.leg, u.n_in, u.n_out, u.fired,
       u.score_kind, u.index_generation, u.candidates_expected, u.candidates_cap, u.detail::jsonb
FROM unnest(
    $2::int[], $3::text[], $4::text[], $5::text[], $6::int[], $7::int[],
    $8::bool[], $9::text[], $10::text[], $11::int[], $12::int[], $13::text[]
) AS u(seq, stage, channel, leg, n_in, n_out, fired, score_kind, index_generation,
       candidates_expected, candidates_cap, detail)
RETURNING id, seq
"""

_INSERT_CANDIDATES = """
INSERT INTO search_span_candidate (span_id, rank, chunk_rid, doc_rid, raw_score, dropped)
SELECT * FROM unnest(
    $1::bigint[], $2::int[], $3::text[], $4::text[], $5::double precision[], $6::bool[]
)
"""


async def persist_spans(search_log_id: int, spans: SpanSet, *, swallow: bool = True) -> bool:
    """`spans` 를 한 트랜잭션(부모와는 별개)으로 적재한다.

    반환값이 곧 결과다: 성공하면 True, 실패해서 삼켰으면 False. `swallow=False` 는
    **시험 전용** — 프로덕션 경로는 항상 True/False 만 돌려주고 절대 올리지 않는다.

    ⛔ 자식은 반환된 `seq` 로 부모를 찾는다. 다중행 RETURNING 의 행 순서는 계약이 아니다 —
    입력 순서를 가정하면 pool 이 엉뚱한 단계에 붙는, 에러보다 나쁜 그럴싸한 오답이 나온다.
    """
    if not spans.spans:
        return True
    try:
        pool = await db.get_pool()
        async with pool.acquire() as conn, conn.transaction():
            span_rows = await conn.fetch(
                _INSERT_SPANS,
                search_log_id,
                [s.seq for s in spans.spans],
                [s.stage for s in spans.spans],
                [s.channel for s in spans.spans],
                [s.leg for s in spans.spans],
                [s.n_in for s in spans.spans],
                [s.n_out for s in spans.spans],
                [s.fired for s in spans.spans],
                [s.score_kind for s in spans.spans],
                [s.index_generation for s in spans.spans],
                [s.candidates_expected for s in spans.spans],
                [s.candidates_cap for s in spans.spans],
                [json.dumps(s.detail) for s in spans.spans],
            )
            # seq → id. RETURNING 의 행 순서를 믿지 않고 값으로 다시 찾는다.
            span_id_by_seq = {row["seq"]: row["id"] for row in span_rows}

            cand_span_id, cand_rank, cand_chunk_rid = [], [], []
            cand_doc_rid, cand_raw_score, cand_dropped = [], [], []
            for span in spans.spans:
                span_id = span_id_by_seq[span.seq]
                for c in span.candidates:
                    cand_span_id.append(span_id)
                    cand_rank.append(c.rank)
                    cand_chunk_rid.append(c.chunk_rid)
                    cand_doc_rid.append(c.doc_rid)
                    cand_raw_score.append(c.raw_score)
                    cand_dropped.append(c.dropped)

            if cand_span_id:
                await conn.execute(
                    _INSERT_CANDIDATES,
                    cand_span_id, cand_rank, cand_chunk_rid,
                    cand_doc_rid, cand_raw_score, cand_dropped,
                )
        return True
    except Exception as exc:  # noqa: BLE001 - span 유실이 요청을 죽이면 안 된다
        if not swallow:
            raise
        log.warning("span_persist_failed", search_log_id=search_log_id,
                    error=str(exc)[:500])
        return False
