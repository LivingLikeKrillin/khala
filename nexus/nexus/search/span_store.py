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

# detail tier(`search_span_candidate`)만 만료된다 — 순위 매겨진 후보 목록이 질의의 지문이고,
# 테넌트 구성·시각·principal 과 상관되면 재식별이 가능해지는 것은 그 목록이지 요약 행이 아니다.
# summary tier(`search_span`)는 `search_log` 캐스케이드로만 사라진다(여기서 지우지 않는다).
#
# `expired` 는 **아직 후보 행이 남아 있는** span 만 고른다(JOIN). 그래서 두 번째 실행에서는
# 이미 지운 span 이 다시 잡히지 않고, `stamped` 의 `candidates_purged_at IS NULL` 조건과
# 합쳐져 자연히 멱등이 된다 — 같은 스케줄러 틱이 두 번 돌아도 이중 도장·에러가 없다.
#
# `answer` 처럼 후보가 원래 없던 단계, 부분 쓰기로 자식이 아예 안 생긴 span 은 `expired` 에
# 들지 못한다(JOIN 이 아무것도 안 남긴다) — 그래서 도장이 안 찍힌다. *지워졌다* 와 *원래
# 없었다* 를 같은 관측으로 만들지 않는 것이 `candidates_purged_at` 컬럼이 있는 이유다.
_PURGE_CANDIDATES = """
WITH expired AS (
    SELECT DISTINCT s.id FROM search_span s
    JOIN search_span_candidate c ON c.span_id = s.id
    WHERE s.ts < now() - make_interval(days => $1)
), gone AS (
    DELETE FROM search_span_candidate WHERE span_id IN (SELECT id FROM expired)
), stamped AS (
    UPDATE search_span SET candidates_purged_at = now()
    WHERE id IN (SELECT id FROM expired) AND candidates_purged_at IS NULL
)
-- `expired` 의 행 수를 센다 — DELETE/UPDATE 의 RETURNING 행 수가 아니다. WITH 안의
-- data-modifying 문은 최종 SELECT 가 참조하지 않아도 항상 끝까지 실행되므로(PostgreSQL
-- 문서) `gone`·`stamped` 는 이 SELECT 와 무관하게 돈다. count(*) 는 언제나 한 행을 내
-- (0 이든 N 이든) `fetch_val` 로 실제 개수를 그대로 돌려준다 — "RETURNING 1" 스케치처럼
-- 첫 행만 집어 span 이 몇 개든 1 을 내는 실패를 여기서 원천적으로 피한다.
SELECT count(*) FROM expired
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


async def purge_candidates(retain_days: int) -> int:
    """`retain_days` 보다 오래된 span 의 후보 행을 지우고 그 span 에 도장을 찍는다.

    반환값은 **이번에 후보가 지워진 span 개수**다 — 지운 행 수도, 찍은 도장 수도 아니다
    (이미 도장이 있던 span 은 애초에 `expired` 에 들지 않으므로 둘은 이 함수에선 늘 같지만,
    이름이 말하는 것은 span 이다). 소유자 결정은 3일(`spans.candidate_retain_days`,
    config.yaml) 이지만 그 숫자는 호출자(`purge_schedule`)가 config 에서 읽어 넘긴다 —
    여기 하드코딩하면 창을 넓히는 되돌릴 수 있는 조정이 배포마다 코드 변경이 된다.
    """
    return await db.fetch_val(_PURGE_CANDIDATES, retain_days)
