# Stage Spans (Unit 1) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record what each retrieval stage received and produced — including every leg's candidate pool with its raw score — so a production failure can later be attributed to a stage.

**Architecture:** Two new tables (`search_span` summary, `search_span_candidate` detail) parented on `search_log.id`. Stage records are accumulated as **pure data** on `SearchResult`/`AnswerResult` and persisted best-effort in `signals.record_search`, with `search_log` committed **before** the span batch so a child constraint violation cannot roll the parent back. Purge reuses the existing scheduler. **Ships disabled** (`spans.enabled=false`), so merging accumulates nothing.

**Tech Stack:** Python 3.13 · asyncpg · PostgreSQL 16 · pytest · structlog

**Spec:** [`specs/SPEC-nexus-stage-spans.md`](../specs/SPEC-nexus-stage-spans.md) (approved 2026-09-04, `content_hash: sha256:69c6397b…`)

---

## Errata against the approved spec

⚠ **Read this before Chunk 1.** The spec's §2 says the leg pools are *"sized by `search.bm25_top_k` / `search.vector_top_k` (both 20)"*. That is **wrong as of the pool-25 adoption** (OPEN.md A51): `nexus/config.yaml` has `bm25_top_k: 25`, `vector_top_k: 20`.

The consequence is §1.4's worst-case arithmetic. Corrected:

| term | spec (both 20) | actual (25 / 20) |
|---|---|---|
| legs, 2 channels × 2 legs | 80 | **90** |
| fusion merged union | ≤ 80, capped 100 | ≤ 90, capped 100 |
| diversify inputs (cap-exempt) | ≤ 80 | **≤ 90** |
| fill (`diversity_per_doc_cap`) | 5 | 5 |
| packet (`final_top_k`) | 10 | 10 |
| **total** | 255 | **285** |

⛔ **Do not edit the spec body to fix this.** It is content-hash stamped; editing flips it to `stale` and `scripts/ledger_integrity.py` will say so. Implement against the real config values, keep this erratum, and let the owner decide whether a restamp is worth it. **Never hardcode 20 or 25** — read from config.

---

## File structure

| file | responsibility |
|---|---|
| `nexus/migrations/040_stage_spans.sql` | **create** — tables, indexes, constraints, the jsonb helper |
| `nexus/nexus/search/spans.py` | **create** — the span data model and pure builders. No I/O |
| `nexus/nexus/search/span_store.py` | **create** — persistence only. Knows asyncpg, knows nothing about stages |
| `nexus/nexus/search/hybrid.py` | modify — accumulate leg/fusion/diversify/section_fill spans onto `SearchResult` |
| `nexus/nexus/search/evidence_packet.py` | modify — accumulate the `packet` span |
| `nexus/nexus/llm/answer.py` | modify — accumulate the `answer` span |
| `nexus/nexus/search/signals.py` | modify — call `span_store` after the `search_log` commit |
| `nexus/nexus/search/purge_schedule.py` | modify — one more purge call |
| `nexus/config.yaml` | modify — the `spans:` block |
| `nexus/tests/test_spans_assembly.py` | **create** — pure builders, no DB |
| `nexus/tests/test_spans_store_db.py` | **create** — persistence, constraints, cascade |
| `nexus/tests/test_spans_purge_db.py` | **create** — retention |
| `nexus/tests/test_spans_gate_db.py` | **create** — ⭐ the registered CI gate |
| `nexus/tests/test_spans_equivalence_db.py` | **create** — capture on/off equivalence + destructive path |

**Why `spans.py` and `span_store.py` are separate:** the builders must be testable with no database at all (that is most of the test surface), and the store must be swappable for the fault injection the destructive test needs. Mixing them makes both harder to test and is the shape this repository already uses (`search/signals.py` pure `extract_signals` vs. `_persist`).

---

## Chunk 1: Schema and config

### Task 1: The migration

**Files:**
- Create: `nexus/migrations/040_stage_spans.sql`

- [ ] **Step 1: Write the migration**

```sql
-- 040: **단계별 span** — 어느 단계에서 잃었는지를 사후에 물을 수 있게 한다.
--
-- **무엇이 막혔나.** `search_log` 는 요청당 한 행이라 *풀에 못 들어왔다* 와 *융합에서 밀렸다*
-- 와 *프롬프트에 안 실렸다* 가 전부 같아 보인다. 라이브 답이 틀렸을 때 단계를 물으려면 라벨
-- 있는 질의로 재현해야 했다 (SPEC-nexus-stage-spans §1).
--
-- **꺼진 채로 온다.** `spans.enabled` 기본값이 false 다. 이 마이그레이션은 자리를 만들 뿐
-- 아무것도 쌓지 않는다 — 스키마·제약·파괴 경로를 프로덕션 행이 생기기 전에 두들기기 위해서다.
--
-- **보존은 3일**(소유자 결정, SPEC §7). `chunk_rid` 는 남긴다 — 상관 노출을 해상도가 아니라
-- 시간으로 묶는 쪽이 Unit 2 의 청크 단위 귀속을 지킨다.

ALTER TABLE search_log
    ADD COLUMN IF NOT EXISTS spans_expected INTEGER;
COMMENT ON COLUMN search_log.spans_expected IS
    'NULL = 캡처 꺼짐. 값이 있는데 span 행이 0 이면 배치가 통째로 유실된 것이다.';

-- detail 은 스칼라만 담는다. CHECK 에 서브쿼리를 못 쓰므로 IMMUTABLE 함수로 감싼다.
CREATE OR REPLACE FUNCTION jsonb_values_all_scalar(j jsonb) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT bool_and(jsonb_typeof(value) NOT IN ('object','array')) IS NOT FALSE
    FROM jsonb_each(j)
$$;

CREATE TABLE IF NOT EXISTS search_span (
    id                   BIGSERIAL PRIMARY KEY,
    search_log_id        BIGINT      NOT NULL REFERENCES search_log(id) ON DELETE CASCADE,
    ts                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    seq                  INTEGER     NOT NULL,
    stage                TEXT        NOT NULL,
    channel              TEXT,
    leg                  TEXT,
    n_in                 INTEGER,
    n_out                INTEGER,
    fired                BOOLEAN     NOT NULL DEFAULT true,
    score_kind           TEXT,
    index_generation     TEXT,
    candidates_expected  INTEGER,
    candidates_cap       INTEGER,
    candidates_purged_at TIMESTAMPTZ,
    detail               JSONB       NOT NULL DEFAULT '{}',
    UNIQUE (search_log_id, seq),
    CONSTRAINT span_stage_known CHECK (stage IN
        ('leg','fusion','diversify','section_fill','packet','answer')),
    CONSTRAINT span_score_kind_known CHECK (score_kind IS NULL OR score_kind IN
        ('ts_rank_cd','cosine_distance','rrf')),
    CONSTRAINT span_leg_fields CHECK (
        (stage = 'leg' AND leg IN ('bm25','vector') AND channel IS NOT NULL AND channel <> '')
     OR (stage <> 'leg' AND leg IS NULL AND channel IS NULL)),
    -- 최상위 타입 검사가 먼저다: jsonb_each 는 object 가 아니면 **런타임 에러**를 내고,
    -- 그러면 깔끔한 제약 위반 대신 배치가 통째로 죽는다.
    CONSTRAINT span_detail_scalar CHECK (
        jsonb_typeof(detail) = 'object' AND jsonb_values_all_scalar(detail))
);

CREATE INDEX IF NOT EXISTS idx_search_span_ts  ON search_span (ts);
CREATE INDEX IF NOT EXISTS idx_search_span_log ON search_span (search_log_id, seq);
-- **AT MOST one** per non-leg stage. "at least one" 은 부분 유니크 인덱스로 표현할 수 없고,
-- writer 불변식과 테스트가 맡는다 (SPEC §3.3).
CREATE UNIQUE INDEX IF NOT EXISTS idx_search_span_singleton
    ON search_span (search_log_id, stage) WHERE stage <> 'leg';

CREATE TABLE IF NOT EXISTS search_span_candidate (
    span_id   BIGINT  NOT NULL REFERENCES search_span(id) ON DELETE CASCADE,
    rank      INTEGER NOT NULL,
    chunk_rid TEXT,
    doc_rid   TEXT    NOT NULL,
    raw_score DOUBLE PRECISION,
    dropped   BOOLEAN NOT NULL DEFAULT false,
    -- rank 다. chunk_rid 가 아니다 — 보존 옵션 3 은 chunk_rid 를 지우고, 그러면 행에
    -- 신원이 없어진다 (SPEC §3.1).
    PRIMARY KEY (span_id, rank)
);
COMMENT ON COLUMN search_span_candidate.raw_score IS
    '부모 span 의 score_kind 로 해석한다. **span 안에서만 비교 가능**하다 — ts_rank_cd 는 클수록 좋고 cosine_distance 는 작을수록 좋다.';
```

- [ ] **Step 2: Apply it and verify the constraints actually reject**

```bash
docker exec -i nexus-postgres psql -U nexus -d nexus < nexus/migrations/040_stage_spans.sql
docker exec nexus-postgres psql -U nexus -d nexus -c \
  "INSERT INTO search_span (search_log_id, seq, stage, detail) VALUES (1, 1, 'leg', '[]');"
```

Expected: the second command **fails**. Two distinct failures are acceptable and both prove a guard: `span_detail_scalar` (the detail check) or `span_leg_fields` (leg row with NULL leg). If it **succeeds**, a constraint is missing — stop and fix the migration.

- [ ] **Step 3: Commit**

```bash
git add nexus/migrations/040_stage_spans.sql
git commit -m "migration: stage span tables, disabled until config turns capture on"
```

### Task 2: Config block

**Files:**
- Modify: `nexus/config.yaml` (after the `search:` block)

- [ ] **Step 1: Add the block**

```yaml
# 단계별 span (SPEC-nexus-stage-spans, Unit 1)
#
# ⛔ **기본이 꺼짐이다.** 캡처는 요청마다 순위 매겨진 후보 목록을 쌓는데, 그것은 질의의
# 지문이고 테넌트 구성·시각·principal 과 상관된다. 그 위험을 묶는 보존 창이 정해지기 전에
# 쌓기 시작하면 안 된다 (SPEC §3.3, §7). 켜는 것은 별개의 명시적 행위다.
spans:
  enabled: false
  # 소유자 결정(SPEC §7): 되돌릴 수 있는 쪽. 창은 나중에 넓힐 수 있지만 버린 행은 못 되살린다.
  candidate_retain_days: 3
  # 한 span 의 후보 행 상한. diversify 는 **면제** — 잘린 행이 곧 진단 자료라
  # 입력 순위로 자르면 정확히 그것을 버린다 (SPEC §3.1).
  max_candidates_per_span: 100
```

- [ ] **Step 2: Commit**

```bash
git add nexus/config.yaml
git commit -m "config: spans block, capture off by default"
```

---

## Chunk 2: Pure assembly

### Task 3: The span data model

**Files:**
- Create: `nexus/nexus/search/spans.py`
- Test: `nexus/tests/test_spans_assembly.py`

- [ ] **Step 1: Write the failing test**

```python
"""단계 span 조립 — DB 없이 도는 순수 함수만."""
from nexus.search.spans import Candidate, SpanSet, StageSpan


def test_leg_span_carries_its_pool_and_names_its_metric():
    spans = SpanSet(max_candidates=100)
    spans.add_leg(
        channel="original", leg="bm25",
        candidates=[Candidate(rank=1, chunk_rid="c1", doc_rid="d1", raw_score=4.7),
                    Candidate(rank=2, chunk_rid="c2", doc_rid="d1", raw_score=0.4)],
    )
    (span,) = spans.spans
    assert span.stage == "leg"
    assert span.score_kind == "ts_rank_cd"      # 경로 이름이 아니라 **지표** 이름
    assert span.n_in is None                    # 질의에는 의미 있는 입력 개수가 없다
    assert span.n_out == 2
    assert span.candidates_expected == 2
    assert span.seq == 1


def test_seq_is_dense_and_a_stage_that_did_not_run_still_writes_a_row():
    spans = SpanSet(max_candidates=100)
    spans.add_leg(channel="original", leg="bm25", candidates=[])
    spans.add_leg(channel="original", leg="vector", candidates=[])
    spans.add_fusion(candidates=[], rrf_k=60, n_channels=1)
    spans.add_diversify(candidates=[], top_k=10, per_doc_cap=5, fired=False)
    assert [s.seq for s in spans.spans] == [1, 2, 3, 4]
    assert spans.spans[-1].fired is False        # 안 돌아도 행은 남는다


def test_truncation_keeps_the_head_and_still_reports_the_full_expectation():
    spans = SpanSet(max_candidates=2)
    spans.add_leg(channel="original", leg="vector",
                  candidates=[Candidate(rank=i, chunk_rid=f"c{i}", doc_rid="d1",
                                        raw_score=float(i)) for i in range(1, 6)])
    (span,) = spans.spans
    assert [c.rank for c in span.candidates] == [1, 2]   # 머리를 남기고 꼬리를 버린다
    assert span.candidates_expected == 5                 # 잘렸다는 사실이 보인다
    assert span.candidates_cap == 2                      # 그때의 상한을 행에 박는다


def test_diversify_is_exempt_from_the_cap_because_its_cut_rows_are_the_payload():
    spans = SpanSet(max_candidates=2)
    spans.add_diversify(
        candidates=[Candidate(rank=i, chunk_rid=f"c{i}", doc_rid="d1",
                              raw_score=None, dropped=(i > 3)) for i in range(1, 6)],
        top_k=3, per_doc_cap=5,
    )
    (span,) = spans.spans
    assert len(span.candidates) == 5
    assert span.candidates_cap is None


def test_detail_rejects_a_non_scalar_before_it_reaches_the_database():
    import pytest
    spans = SpanSet(max_candidates=100)
    with pytest.raises(ValueError, match="scalar"):
        spans.add_packet(candidates=[], n_snippets=0, n_graph_edges=[1, 2])
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd nexus && python -m pytest tests/test_spans_assembly.py -v
```

Expected: `ModuleNotFoundError: No module named 'nexus.search.spans'`

- [ ] **Step 3: Implement `spans.py`**

```python
"""단계 span 조립 — **순수 데이터**. DB 도, 설정 읽기도 여기 없다.

왜 갈라놨나: 테스트 표면의 대부분이 DB 없이 돌아야 하고, 저장은 파괴 경로 시험을 위해
갈아 끼울 수 있어야 한다. `search/signals.py` 가 순수 `extract_signals` 와 `_persist` 를
가른 것과 같은 관례다.

⛔ **비율을 만들지 않는다. 개수만 남긴다** — 비율은 분모를 지운다 (`search/evidence_share.py`).
⛔ **문턱을 두지 않는다.** 첫 회차는 관측이다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: 경로 이름이 아니라 **지표** 이름이다. ts_rank_cd 는 유사도(클수록 좋음),
#: cosine_distance 는 거리(작을수록 좋음) — 극성이 반대라 span 을 넘어 비교하면 안 된다.
SCORE_KIND = {"bm25": "ts_rank_cd", "vector": "cosine_distance"}

_SCALAR = (str, int, float, bool, type(None))


@dataclass(frozen=True)
class Candidate:
    rank: int                       # 그 단계의 **입력** 순서, 1부터
    doc_rid: str
    chunk_rid: str | None = None    # 보존 옵션 3 에서 비워진다
    raw_score: float | None = None
    dropped: bool = False           # diversify 전용: 이 행이 잘렸다


@dataclass
class StageSpan:
    seq: int
    stage: str
    channel: str | None = None
    leg: str | None = None
    n_in: int | None = None
    n_out: int | None = None
    fired: bool = True
    score_kind: str | None = None
    index_generation: str | None = None
    candidates_expected: int | None = None
    candidates_cap: int | None = None
    detail: dict = field(default_factory=dict)
    candidates: list[Candidate] = field(default_factory=list)


def _check_scalar(detail: dict) -> dict:
    bad = [k for k, v in detail.items() if not isinstance(v, _SCALAR)]
    if bad:
        raise ValueError(f"detail must hold scalar values only; not scalar: {bad}")
    return detail


class SpanSet:
    """한 요청의 span 들. `seq` 는 1부터 조밀하다."""

    def __init__(self, max_candidates: int, index_generation: str | None = None):
        self._max = max_candidates
        self._generation = index_generation
        self.spans: list[StageSpan] = []

    def _add(self, stage: str, candidates: list[Candidate], *, cap_exempt: bool = False,
             **kw) -> StageSpan:
        detail = _check_scalar(kw.pop("detail", {}))
        cap = None if cap_exempt else self._max
        kept = candidates if cap is None else candidates[:cap]
        span = StageSpan(
            seq=len(self.spans) + 1, stage=stage, detail=detail,
            index_generation=self._generation,
            candidates_expected=len(candidates), candidates_cap=cap,
            candidates=kept, **kw,
        )
        self.spans.append(span)
        return span

    # --- 단계별 겉면. 각각이 그 단계의 어휘를 안다 -----------------------------
    def add_leg(self, *, channel: str, leg: str, candidates: list[Candidate],
                fired: bool = True) -> StageSpan:
        return self._add("leg", candidates, channel=channel, leg=leg, fired=fired,
                         n_in=None, n_out=len(candidates), score_kind=SCORE_KIND[leg],
                         detail={"pool_size": len(candidates)})

    def add_fusion(self, *, candidates: list[Candidate], rrf_k: int,
                   n_channels: int) -> StageSpan:
        return self._add("fusion", candidates, n_in=None, n_out=len(candidates),
                         score_kind="rrf",
                         detail={"rrf_k": rrf_k, "n_channels": n_channels})

    def add_diversify(self, *, candidates: list[Candidate], top_k: int, per_doc_cap: int,
                      fired: bool = True) -> StageSpan:
        # 상한 면제: 잘린 행이 곧 진단 자료라 입력 순위로 자르면 정확히 그것을 버린다.
        kept = sum(1 for c in candidates if not c.dropped)
        return self._add("diversify", candidates, cap_exempt=True, fired=fired,
                         n_in=len(candidates), n_out=kept,
                         detail={"top_k": top_k, "per_doc_cap": per_doc_cap})

    def add_section_fill(self, *, candidates: list[Candidate], trigger_saturated: bool,
                         fired: bool = True) -> StageSpan:
        return self._add("section_fill", candidates, fired=fired,
                         n_in=None, n_out=len(candidates),
                         detail={"trigger_saturated": trigger_saturated})

    def add_packet(self, *, candidates: list[Candidate], n_snippets: int,
                   n_graph_edges: int) -> StageSpan:
        # 그래프 findings 는 청크가 아니라 doc_rid 가 없다 → 후보 행을 안 만들고 개수만 남긴다.
        return self._add("packet", candidates, n_in=None, n_out=len(candidates),
                         detail={"n_snippets": n_snippets,
                                 "n_graph_edges": n_graph_edges})

    def add_answer(self, *, n_in: int | None, fired: bool = True, **detail) -> StageSpan:
        return self._add("answer", [], n_in=n_in, n_out=None, fired=fired,
                         detail=detail)
```

⚠ `add_answer` passes `candidates=[]`, so `candidates_expected` is `0` and `candidates_cap` is the max — the spec says `candidates_cap` should be NULL for the answer stage. Fix that in the same step by overriding after `_add`, or by giving `add_answer` `cap_exempt=True`. **Use `cap_exempt=True`** — it yields `candidates_cap=None` and `candidates_expected=0`, exactly as §3.1 requires.

- [ ] **Step 4: Run the tests**

```bash
cd nexus && python -m pytest tests/test_spans_assembly.py -v
```

Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add nexus/nexus/search/spans.py nexus/tests/test_spans_assembly.py
git commit -m "spans: pure stage-span assembly with cap, density and scalar guards"
```

---

## Chunk 3: Persistence

### Task 4: The store

**Files:**
- Create: `nexus/nexus/search/span_store.py`
- Test: `nexus/tests/test_spans_store_db.py`

- [ ] **Step 1: Write the failing test**

```python
"""span 저장 — postgres. NEXUS_TEST_DB_URL 이 필요하다."""
import pytest

from nexus import db
from nexus.search.span_store import persist_spans
from nexus.search.spans import Candidate, SpanSet

pytestmark = pytest.mark.asyncio


async def _a_search_log_row() -> int:
    return await db.fetch_val(
        "INSERT INTO search_log (path, route) VALUES ('/t', 'hybrid_only') RETURNING id")


async def test_children_attach_to_the_right_stage(clean_db):
    log_id = await _a_search_log_row()
    spans = SpanSet(max_candidates=100)
    spans.add_leg(channel="original", leg="bm25",
                  candidates=[Candidate(rank=1, chunk_rid="b1", doc_rid="d1", raw_score=4.7)])
    spans.add_leg(channel="original", leg="vector",
                  candidates=[Candidate(rank=1, chunk_rid="v1", doc_rid="d2", raw_score=0.19)])
    await persist_spans(log_id, spans)

    rows = await db.fetch_all(
        """SELECT s.leg, c.chunk_rid FROM search_span s
           JOIN search_span_candidate c ON c.span_id = s.id
           WHERE s.search_log_id = $1 ORDER BY s.seq""", log_id)
    # 다중행 RETURNING 의 행 순서를 가정하면 여기서 뒤바뀐다.
    assert [(r["leg"], r["chunk_rid"]) for r in rows] == [("bm25", "b1"), ("vector", "v1")]


async def test_deleting_the_parent_takes_everything(clean_db):
    log_id = await _a_search_log_row()
    spans = SpanSet(max_candidates=100)
    spans.add_leg(channel="original", leg="bm25",
                  candidates=[Candidate(rank=1, chunk_rid="b1", doc_rid="d1")])
    await persist_spans(log_id, spans)
    await db.execute("DELETE FROM search_log WHERE id = $1", log_id)
    assert await db.fetch_val("SELECT count(*) FROM search_span_candidate") == 0


async def test_a_second_fusion_row_is_refused(clean_db):
    log_id = await _a_search_log_row()
    spans = SpanSet(max_candidates=100)
    spans.add_fusion(candidates=[], rrf_k=60, n_channels=1)
    spans.add_fusion(candidates=[], rrf_k=60, n_channels=1)   # 같은 요청에 둘째 fusion
    with pytest.raises(Exception):
        await persist_spans(log_id, spans, swallow=False)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
cd nexus && NEXUS_TEST_DB_URL=postgresql://nexus:nexus@localhost:5432/nexus_test \
  python -m pytest tests/test_spans_store_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'nexus.search.span_store'`

- [ ] **Step 3: Implement `span_store.py`**

```python
"""span 저장. **여기만 asyncpg 를 안다.**

⛔ **부모 커밋이 먼저다.** 자식 제약 위반이 하나라도 나면 다중행 INSERT 가 통째로 중단되는데,
부모와 한 트랜잭션이면 `search_log` 행까지 롤백된다 — 그러면 `spans_expected` 가 남지 않고
"캡처 실패가 보인다" 는 시험이 통과할 수 없다 (SPEC §3.3).
"""
from __future__ import annotations

import structlog

from nexus import db
from nexus.search.spans import SpanSet

logger = structlog.get_logger(__name__)

_INSERT_SPAN = """
INSERT INTO search_span (search_log_id, seq, stage, channel, leg, n_in, n_out, fired,
                         score_kind, index_generation, candidates_expected,
                         candidates_cap, detail)
SELECT $1, u.seq, u.stage, u.channel, u.leg, u.n_in, u.n_out, u.fired,
       u.score_kind, u.index_generation, u.candidates_expected, u.candidates_cap, u.detail
FROM unnest($2::int[], $3::text[], $4::text[], $5::text[], $6::int[], $7::int[],
            $8::bool[], $9::text[], $10::text[], $11::int[], $12::int[], $13::jsonb[])
     AS u(seq, stage, channel, leg, n_in, n_out, fired, score_kind, index_generation,
          candidates_expected, candidates_cap, detail)
RETURNING id, seq
"""


async def persist_spans(search_log_id: int, spans: SpanSet, *, swallow: bool = True) -> bool:
    """부모는 이미 커밋돼 있다고 가정한다. 성공하면 True.

    `swallow=False` 는 테스트 전용 — 프로덕션 경로는 절대 raise 하지 않는다.
    """
    if not spans.spans:
        return True
    try:
        pool = await db.get_pool()
        async with pool.acquire() as con:
            async with con.transaction():        # **부모와 별개의** 트랜잭션
                rows = await con.fetch(
                    _INSERT_SPAN, search_log_id,
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
                    [__import__("json").dumps(s.detail) for s in spans.spans],
                )
                # ⛔ **seq 로 맞춘다.** 다중행 RETURNING 의 행 순서는 보장되지 않고,
                #    잘못 맞추면 엉뚱한 단계에 풀이 붙어 **에러 대신 그럴듯한 오답**이 남는다.
                id_by_seq = {r["seq"]: r["id"] for r in rows}
                children = [
                    (id_by_seq[s.seq], c.rank, c.chunk_rid, c.doc_rid, c.raw_score, c.dropped)
                    for s in spans.spans for c in s.candidates
                ]
                if children:
                    await con.executemany(
                        """INSERT INTO search_span_candidate
                           (span_id, rank, chunk_rid, doc_rid, raw_score, dropped)
                           VALUES ($1,$2,$3,$4,$5,$6)""", children)
        return True
    except Exception as e:  # noqa: BLE001
        if not swallow:
            raise
        # 답이 사용자에게 못 가는 일은 없어야 한다. 다만 **기록에는 남는다** —
        # spans_expected 가 값인데 행이 0 이면 배치가 유실된 것이다.
        logger.warning("span_persist_failed", search_log_id=search_log_id, error=str(e)[:200])
        return False
```

- [ ] **Step 4: Run the tests**

```bash
cd nexus && NEXUS_TEST_DB_URL=postgresql://nexus:nexus@localhost:5432/nexus_test \
  python -m pytest tests/test_spans_store_db.py -v
```

Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add nexus/nexus/search/span_store.py nexus/tests/test_spans_store_db.py
git commit -m "spans: persistence with its own transaction and seq-matched id mapping"
```

### Task 5: Wire the accumulation and the write

**Files:**
- Modify: `nexus/nexus/search/hybrid.py` (`SearchResult`, `hybrid_search`)
- Modify: `nexus/nexus/search/evidence_packet.py` (`assemble_packet`)
- Modify: `nexus/nexus/llm/answer.py` (`generate_answer`)
- Modify: `nexus/nexus/search/signals.py` (`_persist`)

- [ ] **Step 1: Add the field to `SearchResult`**

```python
    #: 이번 요청의 단계 span (SPEC-nexus-stage-spans). **순수 데이터** — 여기서는 DB 를
    #: 건드리지 않는다. `spans.enabled` 가 꺼져 있으면 None 이고, 그러면 아무것도 안 쌓인다.
    spans: "SpanSet | None" = None
```

- [ ] **Step 2: Accumulate in `hybrid_search`**

Read the config once at the top of `hybrid_search`, beside the existing `bm25_top_k` reads:

```python
    spans_cfg = cfg.get("spans", {})
    spans = SpanSet(max_candidates=spans_cfg.get("max_candidates_per_span", 100),
                    index_generation=await current_generation()) \
        if spans_cfg.get("enabled") else None
```

Then after each leg's task resolves, after `fuse_channels`, after `_diversify`, and after the fill step, call the matching `spans.add_*` **guarded by `if spans is not None`**. A leg that ended in `degraded` writes `fired=False` with an empty pool.

⛔ **Never read `bm25_top_k` as a literal.** The erratum at the top of this plan exists because the spec did.

- [ ] **Step 3: Write `spans_expected` and persist, in `signals._persist`**

`spans_expected` must go into the **same `search_log` INSERT** as everything else — it is known before the span write, and a later UPDATE would leave a crash window in which the value is NULL, indistinguishable from capture-disabled. After that insert returns the id:

```python
    if spans is not None:
        await persist_spans(row_id, spans)      # 절대 raise 안 한다
```

- [ ] **Step 4: Run the existing suite to prove nothing moved**

```bash
cd nexus && python -m pytest tests/ -q -x
```

Expected: PASS. Capture is off by default, so **every existing test must be unaffected**. A failure here means the accumulation is not actually gated.

- [ ] **Step 5: Commit**

```bash
git add nexus/nexus/search/hybrid.py nexus/nexus/search/evidence_packet.py \
        nexus/nexus/llm/answer.py nexus/nexus/search/signals.py
git commit -m "spans: accumulate stage records and persist after the search_log commit"
```

---

## Chunk 4: Retention

### Task 6: Purge

**Files:**
- Modify: `nexus/nexus/search/purge_schedule.py`
- Test: `nexus/tests/test_spans_purge_db.py`

- [ ] **Step 1: Write the failing test**

```python
async def test_purge_cuts_candidates_leaves_summaries_and_stamps_only_what_had_rows(clean_db):
    log_id = await _a_search_log_row()
    spans = SpanSet(max_candidates=100)
    spans.add_leg(channel="original", leg="bm25",
                  candidates=[Candidate(rank=1, chunk_rid="b1", doc_rid="d1")])
    spans.add_answer(n_in=1, n_citations=0)          # 후보가 원래 없는 단계
    await persist_spans(log_id, spans)
    await db.execute(
        "UPDATE search_span SET ts = now() - interval '10 days' WHERE search_log_id = $1",
        log_id)

    from nexus.search.span_store import purge_candidates
    assert await purge_candidates(retain_days=3) == 1

    assert await db.fetch_val("SELECT count(*) FROM search_span_candidate") == 0
    assert await db.fetch_val("SELECT count(*) FROM search_span") == 2   # 요약은 남는다
    stamped = await db.fetch_all(
        "SELECT stage, candidates_purged_at FROM search_span WHERE search_log_id = $1", log_id)
    by_stage = {r["stage"]: r["candidates_purged_at"] for r in stamped}
    assert by_stage["leg"] is not None
    # ⭐ 후보가 애초에 없던 단계에 도장을 찍으면 *지워졌다* 와 *원래 없었다* 가 같아진다.
    assert by_stage["answer"] is None
```

- [ ] **Step 2: Run it and watch it fail** — `ImportError: cannot import name 'purge_candidates'`

- [ ] **Step 3: Implement `purge_candidates` in `span_store.py`**

```python
async def purge_candidates(retain_days: int) -> int:
    """만료된 후보 행을 지우고, **행이 있었던 span 에만** 도장을 찍는다.

    도장을 무차별로 찍으면 *지워졌다* 와 *원래 없었다* 가 구별되지 않는다 — 그 구별이
    이 칸의 존재 이유다 (SPEC §3.4).
    """
    return await db.fetch_val(
        """
        WITH expired AS (
            SELECT DISTINCT s.id FROM search_span s
            JOIN search_span_candidate c ON c.span_id = s.id
            WHERE s.ts < now() - make_interval(days => $1)
        ), gone AS (
            DELETE FROM search_span_candidate WHERE span_id IN (SELECT id FROM expired)
        )
        UPDATE search_span SET candidates_purged_at = now()
        WHERE id IN (SELECT id FROM expired) AND candidates_purged_at IS NULL
        RETURNING 1
        """, retain_days) or 0
```

⚠ `fetch_val` returns the first row only. Use `db.fetch_all(...)` and return `len(rows)`, or wrap the statement so it yields a single count. **Verify the returned number against the test's expected `1` before moving on** — a purge that silently reports zero is the failure mode `purge_schedule.py` was written to prevent.

- [ ] **Step 4: Call it from the scheduler**

In `run_once`, beside the existing `query_retention.purge()`:

```python
                from nexus.search.span_store import purge_candidates
                deleted["span_candidates"] = await purge_candidates(_retain_days())
```

- [ ] **Step 5: Run the tests, then commit**

```bash
cd nexus && NEXUS_TEST_DB_URL=... python -m pytest tests/test_spans_purge_db.py -v
git add nexus/nexus/search/span_store.py nexus/nexus/search/purge_schedule.py \
        nexus/tests/test_spans_purge_db.py
git commit -m "spans: purge candidates on the existing schedule, stamp only what had rows"
```

---

## Chunk 5: The registered gate

### Task 7: The constructed case

**Files:**
- Test: `nexus/tests/test_spans_gate_db.py`

This is **the** registered pass criterion (SPEC §1.3). Both legs are built, not ranked.

- [ ] **Step 1: Write the test**

```python
"""⭐ 등록된 판정 기준 (SPEC-nexus-stage-spans §1.3).

**양쪽 경로를 다 만든다.** 벡터는 스텁 임베더로 픽스처 벡터를 박고, BM25 는 순위로 밀어내는
대신 **질의 어휘가 그 청크에 아예 없게** 만든다 — 풀 안의 위치는 `ts_rank_cd` 와 한국어
tsvector 설정과 `bm25_top_k` 의 성질이고, 토크나이저나 사전이 바뀌면 조용히 움직인다.
그것이 스텁 임베더를 쓰는 이유와 같은 이유다 (round 5, I-007).

**LLM 을 부르지 않는다.** 검색까지만 돈다 — 그래서 싸고 결정론이다.
"""

async def test_the_gold_is_absent_from_bm25_and_present_in_vector_at_a_known_rank(
        clean_db, stub_embedder, spans_enabled):
    # 픽스처: 질의 어휘가 하나도 없는 청크에 gold 를 둔다 → BM25 풀에 구조적으로 못 든다.
    # 같은 청크의 스텁 벡터는 질의 벡터에 가장 가깝게 박는다 → 벡터 풀 1위.
    log_id = await run_search_and_capture(query="해금 포인트 상한이 얼마인가")

    bm25 = await _candidates(log_id, stage="leg", leg="bm25")
    vector = await _candidates(log_id, stage="leg", leg="vector")

    assert GOLD_CHUNK not in {c["chunk_rid"] for c in bm25}     # 구조적 부재
    assert vector[0]["chunk_rid"] == GOLD_CHUNK                 # 알려진 순위

    # 그리고 그 뒤 단계에서 만든 대로 실려 가거나 잘렸는지가 보인다.
    fusion = await _candidates(log_id, stage="fusion")
    assert GOLD_CHUNK in {c["chunk_rid"] for c in fusion}
```

- [ ] **Step 2: Run it, watch it fail, implement the fixtures, run it again**

```bash
cd nexus && NEXUS_TEST_DB_URL=... python -m pytest tests/test_spans_gate_db.py -v
```

Expected finally: PASS.

- [ ] **Step 3: Commit**

```bash
git add nexus/tests/test_spans_gate_db.py
git commit -m "spans: the registered gate — a constructed case with both legs built, not ranked"
```

---

## Chunk 6: Equivalence, destruction, cost

### Task 8: Capture changes nothing, and failing capture changes nothing either

**Files:**
- Test: `nexus/tests/test_spans_equivalence_db.py`

- [ ] **Step 1: Write both tests**

```python
async def test_capture_does_not_perturb_retrieval(clean_db, stub_embedder):
    off = await run_search(query=Q, spans_enabled=False)
    on = await run_search(query=Q, spans_enabled=True)

    assert [h.rid for h in off.hits] == [h.rid for h in on.hits]     # 순서까지 같다

    cols = await _search_log_pair()
    # prompt_tokens 는 **포함한다** — 조립된 패킷의 함수라, 캡처가 프롬프트에 닿는 것을
    # 건드리지 않았는지 확인하는 가장 싼 검사다 (round 5, I-013).
    for col in ("n_snippets", "top_score", "prompt_tokens"):
        assert cols.off[col] == cols.on[col]
    # 생성에서 나오는 칸은 전부 뺀다 — LLM 은 재현되지 않는다.
    # (n_citations · unverified_citations · unverified_numbers · completion_tokens · cost_usd
    #  · latency_ms · spans_expected)


async def test_a_broken_span_write_does_not_take_the_answer_with_it(
        clean_db, stub_embedder, spans_enabled, broken_span_store):
    result = await run_search(query=Q)
    assert result.hits                                    # 답은 그대로 나간다
    row = await _the_search_log_row()
    assert row["spans_expected"] is not None              # 기대는 기록됐고
    assert await db.fetch_val("SELECT count(*) FROM search_span") == 0   # 배치는 유실됐다
    # ⭐ 이 조합이 곧 "유실" 의 정의다. 이 시험이 스킵되면 그 정의가 없는 것이다.
```

- [ ] **Step 2: Run, implement fixtures, run again, commit**

```bash
cd nexus && NEXUS_TEST_DB_URL=... python -m pytest tests/test_spans_equivalence_db.py -v
git add nexus/tests/test_spans_equivalence_db.py
git commit -m "spans: equivalence with capture off, and a deliberately broken write path"
```

### Task 9: Report the cost, assert nothing

**Files:**
- Modify: `nexus/tests/test_spans_gate_db.py` (or a small script beside it)

- [ ] **Step 1: Count rows per request over the fixture query set and print them**

No threshold, no assertion. The number goes into the PR body.

⚠ **It is a fixture number.** Capture ships off, so no live rows exist and no live figure is available until someone turns it on. Say that where the number is reported — a fixture count presented as a production measurement is exactly the kind of claim this spec spent five review rounds removing.

- [ ] **Step 2: Commit**

```bash
git commit -am "spans: report capture cost from the fixture set, no assertion"
```

---

## Done when

- [ ] `task test:nexus` green
- [ ] The full suite green **with capture off** — no existing test moved
- [ ] The registered gate (Chunk 5) passes
- [ ] The destructive path passes **and is not skipped**
- [ ] `python scripts/ledger_integrity.py` still green
- [ ] The PR body carries the fixture cost number, labelled as a fixture number
- [ ] The erratum at the top of this plan is repeated in the PR body so the owner can decide about a restamp
