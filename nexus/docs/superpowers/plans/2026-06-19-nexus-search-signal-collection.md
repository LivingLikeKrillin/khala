# Nexus 검색 품질 신호 수집 체계 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 검색 1건마다 PII-safe 품질 신호 1행을 모든 경로(HTTP·CLI·A2A)에서 핫패스 지연 없이 영속하고, 롤링 집계 뷰 + `nexus status` 요약으로 demand-pull 게이트 신호를 노출한다.

**Architecture:** `a2a_audit`/`record_audit`(PR #23) 패턴을 미러링. 순수 함수 `extract_signals`가 `SearchResult`/`AnswerResult`에서 신호를 조립하고, best-effort IO `record_search`가 structlog(항상) + DB insert(서버=fire-and-forget, CLI=await, 절대 raise 안 함)를 수행한다. 4개 진입점이 `n_entities`·`latency_ms` 스칼라와 함께 호출한다.

**Tech Stack:** Python 3.11, FastAPI, asyncpg, structlog, pytest(`asyncio_mode=auto`).

**Spec:** `nexus/docs/superpowers/specs/2026-06-19-nexus-search-signal-collection-design.md` (Rev 2, 독립 리뷰 2회 통과).

**Branch:** `feat/nexus-search-signal-collection` (스펙 커밋 완료).

**작업 디렉터리:** 모든 경로·명령은 `nexus/` 기준. 테스트는 `cd nexus && python -m pytest …`.

---

## File Structure

- **Create** `nexus/nexus/search/signals.py` — `SearchSignals` dataclass, `query_sha256`, `extract_signals`(순수), `record_search`/`_persist`(IO). 단일 책임: 검색 신호 추출+영속.
- **Create** `nexus/tests/test_signals.py` — 순수/IO 단위 테스트(DB 불필요).
- **Create** `nexus/tests/test_signals_db.py` — DB-gated 통합 테스트(`integration` 마커, `NEXUS_TEST_DB_URL`).
- **Modify** `nexus/init.sql` — `search_log` 테이블 + 인덱스 + `v_search_health` 뷰 (a2a_audit 블록 뒤).
- **Modify** `nexus/nexus/db.py` — `SEARCH_LOG_DDL` 상수 + `ensure_search_log()` 멱등 DDL.
- **Modify** `nexus/nexus/api.py` — `lifespan`에서 `ensure_search_log()` 호출; `/search`·`/search/answer` 배선.
- **Modify** `nexus/nexus/cli.py` — `_query()` 배선(`close_pool` 이전 await); `status` 명령에 신호 한 줄.
- **Modify** `nexus/nexus/a2a/server.py` — `_default_answer_fn` 내부 배선.

---

## Chunk 1: signals 모듈 (순수 추출 + best-effort IO)

### Task 1: `SearchSignals` + `query_sha256` + `extract_signals` (순수)

**Files:**
- Create: `nexus/nexus/search/signals.py`
- Test: `nexus/tests/test_signals.py`

- [ ] **Step 1: 실패 테스트 작성** — `nexus/tests/test_signals.py`

```python
"""검색 품질 신호 — 순수 추출(extract_signals) + best-effort IO(record_search).

a2a_audit 패턴 미러링: 원문 query는 sha256+len으로만 기록(Nexus 원칙 #3).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from structlog.testing import capture_logs

from nexus.search.signals import SearchSignals, extract_signals, query_sha256
# 주의: record_search / SIGNAL_EVENT는 Task 2에서 구현되므로 여기서 import하지 않는다
# (모듈 상단 import는 -k 필터보다 먼저 평가되어 수집 단계 ImportError를 낸다).


# ── 테스트용 더크 타입(실 클래스 import 불필요) ──
@dataclass
class _Hit:
    score: float


@dataclass
class _Graph:
    edges: list = field(default_factory=list)
    observed_edges: list = field(default_factory=list)


@dataclass
class _Result:
    hits: list = field(default_factory=list)
    graph: object | None = None
    route_used: str = "hybrid_only"


@dataclass
class _Answer:
    llm_failed: bool = False


def test_query_sha256_is_stable():
    assert query_sha256("abc") == hashlib.sha256(b"abc").hexdigest()


def test_no_hits_means_no_answer_and_null_top_score():
    sig = extract_signals(_Result(hits=[]), None, path="search",
                          tenant="t", clearance="INTERNAL", query="q")
    assert sig.no_answer is True
    assert sig.top_score is None
    assert sig.n_snippets == 0


def test_top_score_from_first_hit():
    sig = extract_signals(_Result(hits=[_Hit(0.42), _Hit(0.1)]), None, path="search",
                          tenant="t", clearance="INTERNAL", query="q")
    assert sig.top_score == 0.42
    assert sig.n_snippets == 2
    assert sig.no_answer is False


def test_graph_requested_and_empty_graph():
    # route가 graph인데 edge가 0 → graph-empty 신호
    sig = extract_signals(_Result(hits=[_Hit(0.5)], graph=None, route_used="hybrid_then_graph"),
                          None, path="search", tenant="t", clearance="INTERNAL", query="q")
    assert sig.graph_requested is True
    assert sig.n_graph_edges == 0


def test_graph_edges_counted():
    g = _Graph(edges=[1, 2], observed_edges=[3])
    sig = extract_signals(_Result(hits=[_Hit(0.5)], graph=g, route_used="graph_then_hybrid"),
                          None, path="search", tenant="t", clearance="INTERNAL", query="q")
    assert sig.n_graph_edges == 3


def test_llm_failed_only_when_answer_present():
    assert extract_signals(_Result(hits=[_Hit(0.5)]), None, path="search",
                           tenant="t", clearance="INTERNAL", query="q").llm_failed is False
    assert extract_signals(_Result(hits=[_Hit(0.5)]), _Answer(llm_failed=True), path="search_answer",
                           tenant="t", clearance="INTERNAL", query="q").llm_failed is True


def test_scalars_pass_through_and_query_is_hashed():
    secret = "주민번호 901201-1234567"
    sig = extract_signals(_Result(hits=[_Hit(0.5)]), None, path="cli",
                          tenant="t", clearance="INTERNAL", query=secret,
                          n_entities=3, latency_ms=180)
    assert sig.n_entities == 3
    assert sig.latency_ms == 180
    assert sig.query_sha256 == hashlib.sha256(secret.encode("utf-8")).hexdigest()
    assert sig.query_len == len(secret)
    # 원문은 dataclass 어디에도 없음
    assert secret not in json.dumps(sig.__dict__, ensure_ascii=False)
```

- [ ] **Step 2: 실패 확인**

Run: `cd nexus && python -m pytest tests/test_signals.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'nexus.search.signals'`

- [ ] **Step 3: 최소 구현** — `nexus/nexus/search/signals.py`

```python
"""검색 품질 신호 추출(순수) + 영속(best-effort IO).

extract_signals는 SearchResult/AnswerResult에서 신호를 조립하는 순수 함수,
record_search는 structlog(항상) + best-effort DB insert(절대 raise 안 함)다.
a2a/audit.py의 record_audit 패턴을 미러링한다. 원문 query는 sha256+len으로만 기록.
"""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from nexus import db

if TYPE_CHECKING:  # 런타임 import 불필요(순환 회피) — 속성 접근만 한다
    from nexus.llm.answer import AnswerResult
    from nexus.search.hybrid import SearchResult

log = structlog.get_logger("nexus.search.signals")

SIGNAL_EVENT = "search.signal"
_GRAPH_ROUTES = ("hybrid_then_graph", "graph_then_hybrid")


def query_sha256(query: str) -> str:
    """원문 query의 sha256 hex — 신호에 들어갈 수 있는 유일한 형태."""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()


@dataclass
class SearchSignals:
    path: str
    tenant: str | None
    clearance: str | None
    route: str
    query_sha256: str
    query_len: int
    n_snippets: int
    top_score: float | None
    n_entities: int
    graph_requested: bool
    n_graph_edges: int
    no_answer: bool
    llm_failed: bool
    latency_ms: int


def extract_signals(
    result: SearchResult,
    answer: AnswerResult | None = None,
    *,
    path: str,
    tenant: str | None,
    clearance: str | None,
    query: str,
    n_entities: int = 0,
    latency_ms: int = 0,
) -> SearchSignals:
    """SearchResult(+선택 AnswerResult)와 진입점 스칼라에서 신호를 조립. 순수."""
    hits = result.hits
    graph = result.graph
    n_graph_edges = (len(graph.edges) + len(graph.observed_edges)) if graph else 0
    route = result.route_used or ""
    return SearchSignals(
        path=path,
        tenant=tenant,
        clearance=clearance,
        route=route,
        query_sha256=query_sha256(query),
        query_len=len(query),
        n_snippets=len(hits),
        top_score=hits[0].score if hits else None,
        n_entities=n_entities,
        graph_requested=route in _GRAPH_ROUTES,
        n_graph_edges=n_graph_edges,
        no_answer=len(hits) == 0,
        llm_failed=bool(answer.llm_failed) if answer is not None else False,
        latency_ms=latency_ms,
    )
```

(record_search는 Task 2에서 같은 파일에 추가한다.)

- [ ] **Step 4: 통과 확인**

Run: `cd nexus && python -m pytest tests/test_signals.py -q`
Expected: PASS (7 passed). 이 시점엔 `record_search`/`SIGNAL_EVENT` import·테스트가 없으므로 수집 오류 없이 통과한다.

- [ ] **Step 5: 커밋**

```bash
git add nexus/nexus/search/signals.py nexus/tests/test_signals.py
git commit -m "feat(nexus/search): extract_signals — pure search-quality signal extraction"
```

### Task 2: `record_search` (best-effort IO, 절대 raise 안 함)

**Files:**
- Modify: `nexus/nexus/search/signals.py` (append)
- Test: `nexus/tests/test_signals.py` (append)

- [ ] **Step 1: 실패 테스트 추가** — 먼저 `nexus/tests/test_signals.py` 상단 import에 추가:

```python
from nexus.search.signals import SIGNAL_EVENT, record_search  # Task 2에서 추가
```

그리고 파일 끝에 다음 테스트를 추가:

```python
async def test_record_search_without_pool_is_structlog_only(monkeypatch):
    """풀 없으면 structlog만 — DB 연결 시도 없음, 무예외."""
    from nexus import db
    monkeypatch.setattr(db, "has_pool", lambda: False)
    called = {"execute": False}

    async def _fail_execute(*a, **k):
        called["execute"] = True
        raise AssertionError("execute는 호출되면 안 됨")

    monkeypatch.setattr(db, "execute", _fail_execute)

    sig = extract_signals(_Result(hits=[_Hit(0.5)]), None, path="search",
                          tenant="t", clearance="INTERNAL", query="비밀 hunter2", n_entities=1)
    with capture_logs() as logs:
        await record_search(sig, await_persist=True)
    rec = [r for r in logs if r.get("event") == SIGNAL_EVENT][0]
    assert rec["path"] == "search"
    assert rec["n_snippets"] == 1
    assert "hunter2" not in json.dumps(rec, ensure_ascii=False)
    assert called["execute"] is False


async def test_record_search_swallows_persist_error(monkeypatch):
    """풀이 있어도 INSERT 실패는 삼키고 요청 경로를 깨지 않는다."""
    from nexus import db
    monkeypatch.setattr(db, "has_pool", lambda: True)

    async def _boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "execute", _boom)

    sig = extract_signals(_Result(hits=[]), None, path="search",
                          tenant="t", clearance="INTERNAL", query="q")
    # 예외가 전파되지 않아야 한다
    await record_search(sig, await_persist=True)
```

- [ ] **Step 2: 실패 확인**

Run: `cd nexus && python -m pytest tests/test_signals.py -k record -q`
Expected: FAIL — `ImportError: cannot import name 'record_search'` (또는 AttributeError)

- [ ] **Step 3: 구현 추가** — `nexus/nexus/search/signals.py` 끝에

```python
async def _persist(sig: SearchSignals) -> None:
    """search_log에 1행 insert. 실패는 삼킴(신호 영속은 요청 경로를 깨지 않는다)."""
    try:
        await db.execute(
            """
            INSERT INTO search_log (
                path, tenant, clearance, route, query_sha256, query_len,
                n_snippets, top_score, n_entities, graph_requested, n_graph_edges,
                no_answer, llm_failed, latency_ms
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            """,
            sig.path, sig.tenant, sig.clearance, sig.route, sig.query_sha256, sig.query_len,
            sig.n_snippets, sig.top_score, sig.n_entities, sig.graph_requested,
            sig.n_graph_edges, sig.no_answer, sig.llm_failed, sig.latency_ms,
        )
    except Exception as exc:  # noqa: BLE001 - signal persistence must never break the request
        log.warning("search.signal.persist_failed", error=str(exc))


async def record_search(sig: SearchSignals, *, await_persist: bool = False) -> None:
    """structlog(항상, 동기) + best-effort DB 적재. 절대 raise 안 함.

    서버 경로(api/a2a)는 기본 fire-and-forget(create_task) — 응답 지연에 DB 쓰기 미가산.
    CLI는 await_persist=True — asyncio.run 종료/close_pool 이전에 적재 완료 보장.
    """
    log.info(
        SIGNAL_EVENT,
        path=sig.path, tenant=sig.tenant, clearance=sig.clearance, route=sig.route,
        query_sha256=sig.query_sha256, query_len=sig.query_len,
        n_snippets=sig.n_snippets, top_score=sig.top_score, n_entities=sig.n_entities,
        graph_requested=sig.graph_requested, n_graph_edges=sig.n_graph_edges,
        no_answer=sig.no_answer, llm_failed=sig.llm_failed, latency_ms=sig.latency_ms,
    )
    if not db.has_pool():
        return
    if await_persist:
        await _persist(sig)
    else:
        asyncio.create_task(_persist(sig))
```

- [ ] **Step 4: 통과 확인**

Run: `cd nexus && python -m pytest tests/test_signals.py -q`
Expected: PASS (9 passed)

- [ ] **Step 5: ruff + 커밋**

Run: `cd nexus && python -m ruff check nexus/search/signals.py tests/test_signals.py`
Expected: All checks passed!

```bash
git add nexus/nexus/search/signals.py nexus/tests/test_signals.py
git commit -m "feat(nexus/search): record_search — best-effort PII-safe signal sink"
```

---

## Chunk 2: 스키마 + 멱등 ensure

### Task 3: `init.sql` search_log/뷰 + `db.ensure_search_log()`

**Files:**
- Modify: `nexus/init.sql` (a2a_audit 블록 뒤, 파일 끝)
- Modify: `nexus/nexus/db.py`
- Test: `nexus/tests/test_signals_db.py` (Create, DB-gated)

- [ ] **Step 1: `init.sql`에 DDL 추가** — `idx_a2a_audit_denied` 라인 뒤(파일 끝)

```sql
-- ============================================================
-- search_log — search-quality signals (demand-pull gate signals)
-- ============================================================
-- One row per retrieval across all paths (search | search_answer | cli | a2a).
-- PII-safe: the raw query is NEVER stored — only sha256 + length (Nexus principle #3),
-- mirroring a2a_audit. Best-effort, fire-and-forget on server paths.
CREATE TABLE IF NOT EXISTS search_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    path            TEXT NOT NULL,
    tenant          TEXT,
    clearance       TEXT,
    route           TEXT,
    query_sha256    TEXT NOT NULL DEFAULT '',
    query_len       INTEGER NOT NULL DEFAULT 0,
    n_snippets      INTEGER NOT NULL DEFAULT 0,
    top_score       DOUBLE PRECISION,
    n_entities      INTEGER NOT NULL DEFAULT 0,
    graph_requested BOOLEAN NOT NULL DEFAULT false,
    n_graph_edges   INTEGER NOT NULL DEFAULT 0,
    no_answer       BOOLEAN NOT NULL DEFAULT false,
    llm_failed      BOOLEAN NOT NULL DEFAULT false,
    latency_ms      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_search_log_ts     ON search_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_search_log_tenant ON search_log (tenant, ts DESC);
CREATE INDEX IF NOT EXISTS idx_search_log_route  ON search_log (route, ts DESC);

CREATE OR REPLACE VIEW v_search_health AS
SELECT path, route,
       count(*)                                                        AS n,
       avg((no_answer)::int)::numeric(4,3)                             AS no_answer_rate,
       avg((graph_requested AND n_graph_edges = 0)::int)::numeric(4,3) AS graph_empty_rate,
       avg((llm_failed)::int)::numeric(4,3)                            AS llm_fail_rate,
       avg(n_snippets)::numeric(6,2)                                   AS avg_snippets,
       percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms)        AS p95_latency_ms
FROM search_log
WHERE ts > now() - interval '7 days'
GROUP BY path, route;
```

- [ ] **Step 2: `db.py`에 `SEARCH_LOG_DDL` + `ensure_search_log()` 추가** — `check_connection()` 뒤(파일 끝)

위 init.sql의 `CREATE TABLE/INDEX/VIEW` 블록과 **동일한** DDL을 `SEARCH_LOG_DDL` 문자열 상수로 두고(주석 줄 제외, 멱등 구문만), 다음 함수를 추가:

```python
# search_log 멱등 DDL — init.sql과 동일. 기존 배포 DB도 startup에서 즉시 적재 가능하게.
SEARCH_LOG_DDL = """
CREATE TABLE IF NOT EXISTS search_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    path            TEXT NOT NULL,
    tenant          TEXT,
    clearance       TEXT,
    route           TEXT,
    query_sha256    TEXT NOT NULL DEFAULT '',
    query_len       INTEGER NOT NULL DEFAULT 0,
    n_snippets      INTEGER NOT NULL DEFAULT 0,
    top_score       DOUBLE PRECISION,
    n_entities      INTEGER NOT NULL DEFAULT 0,
    graph_requested BOOLEAN NOT NULL DEFAULT false,
    n_graph_edges   INTEGER NOT NULL DEFAULT 0,
    no_answer       BOOLEAN NOT NULL DEFAULT false,
    llm_failed      BOOLEAN NOT NULL DEFAULT false,
    latency_ms      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_search_log_ts     ON search_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_search_log_tenant ON search_log (tenant, ts DESC);
CREATE INDEX IF NOT EXISTS idx_search_log_route  ON search_log (route, ts DESC);
CREATE OR REPLACE VIEW v_search_health AS
SELECT path, route,
       count(*)                                                        AS n,
       avg((no_answer)::int)::numeric(4,3)                             AS no_answer_rate,
       avg((graph_requested AND n_graph_edges = 0)::int)::numeric(4,3) AS graph_empty_rate,
       avg((llm_failed)::int)::numeric(4,3)                            AS llm_fail_rate,
       avg(n_snippets)::numeric(6,2)                                   AS avg_snippets,
       percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms)        AS p95_latency_ms
FROM search_log
WHERE ts > now() - interval '7 days'
GROUP BY path, route;
"""


async def ensure_search_log() -> None:
    """search_log 테이블/인덱스/뷰를 멱등 생성. 풀 있을 때만, 실패는 삼킴(startup을 깨지 않음)."""
    if not has_pool():
        return
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(SEARCH_LOG_DDL)  # 인자 없는 execute = simple protocol, 다중 구문 허용
    except Exception as exc:  # noqa: BLE001
        logger.warning("ensure_search_log_failed", error=str(exc))
```

- [ ] **Step 3: DB-gated 통합 테스트 작성** — `nexus/tests/test_signals_db.py`

먼저 `tests/test_e2e.py` 상단의 skip 관용구(`NEXUS_TEST_DB_URL` 미설정 시 skip)를 그대로 따른다. 그 패턴으로:

```python
"""search_log 영속 + v_search_health 집계 (DB 통합). NEXUS_TEST_DB_URL 필요."""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration

_DB = os.getenv("NEXUS_TEST_DB_URL")
# skip은 conftest가 integration 마커로 처리(NEXUS_TEST_DB_URL 미설정 시) — 별도 데코레이터 불필요.


async def test_ensure_creates_table_and_view_idempotently():
    from nexus import db
    os.environ["DATABASE_URL"] = _DB
    await db.get_pool()
    try:
        await db.ensure_search_log()
        await db.ensure_search_log()  # 멱등 — 두 번 호출해도 실패 없음
        # 뷰 존재 확인
        val = await db.fetch_val("SELECT count(*) FROM v_search_health")
        assert val is not None
    finally:
        await db.close_pool()


async def test_record_search_persists_and_view_aggregates():
    from nexus import db
    from nexus.search.signals import SearchSignals, record_search
    os.environ["DATABASE_URL"] = _DB
    await db.get_pool()
    try:
        await db.ensure_search_log()
        await db.execute("DELETE FROM search_log WHERE path = 'test_agg'")
        # no_answer 1건 + 정상 1건
        for no_ans in (True, False):
            sig = SearchSignals(
                path="test_agg", tenant="t", clearance="INTERNAL", route="hybrid_only",
                query_sha256="x", query_len=1, n_snippets=0 if no_ans else 3,
                top_score=None if no_ans else 0.5, n_entities=0,
                graph_requested=False, n_graph_edges=0, no_answer=no_ans,
                llm_failed=False, latency_ms=100,
            )
            await record_search(sig, await_persist=True)
        row = await db.fetch_one(
            "SELECT n, no_answer_rate FROM v_search_health WHERE path = 'test_agg'"
        )
        assert row["n"] == 2
        assert float(row["no_answer_rate"]) == 0.5
    finally:
        await db.execute("DELETE FROM search_log WHERE path = 'test_agg'")
        await db.close_pool()
```

> 실행 전 `tests/test_e2e.py`를 열어 실제 skip/DB 부트스트랩 관용구를 확인하고 일치시킨다(스키마 적용 방식이 다르면 맞춘다).

- [ ] **Step 4: 단위 스위트 통과(무DB) 확인 — 통합은 skip**

Run: `cd nexus && python -m pytest tests/test_signals.py tests/test_signals_db.py -q`
Expected: PASS — test_signals 9 passed; test_signals_db 2 skipped (NEXUS_TEST_DB_URL 미설정)

- [ ] **Step 5: (선택, DB 있으면) 통합 실행**

Run: `cd nexus && docker compose -f docker-compose.test.yml up -d && NEXUS_TEST_DB_URL=postgresql://nexus:nexus@localhost:5433/nexus_test python -m pytest tests/test_signals_db.py -q`
Expected: 2 passed. (끝나면 `docker compose -f docker-compose.test.yml down`)

- [ ] **Step 6: ruff + 커밋**

Run: `cd nexus && python -m ruff check nexus/db.py tests/test_signals_db.py`
Expected: All checks passed!

```bash
git add nexus/init.sql nexus/nexus/db.py nexus/tests/test_signals_db.py
git commit -m "feat(nexus/db): search_log schema + idempotent ensure_search_log + v_search_health"
```

---

## Chunk 3: 진입점 배선

> 공통 원칙: 각 진입점에서 `import time` 후 작업 시작점에 `_t0 = time.time()`을 두고,
> 신호 기록 직전 `latency_ms=int((time.time() - _t0) * 1000)`로 측정한다.
> 서버 경로(api/a2a)는 `await record_search(sig)`(fire-and-forget, 기본),
> CLI는 `await record_search(sig, await_persist=True)`를 **`db.close_pool()` 이전에** 호출한다.

### Task 4: `lifespan`에서 `ensure_search_log()` 호출

**Files:**
- Modify: `nexus/nexus/api.py:58-65` (`lifespan`)

- [ ] **Step 1: 호출 추가** — `await _bootstrap_gazetteer()` 다음 줄

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    AuthConfig.from_dict(_load_config()).validate_startup()
    await db.get_pool()
    await _bootstrap_gazetteer()
    await db.ensure_search_log()   # ← 추가: 멱등, 기존 DB도 적재 시작
    yield
    await db.close_pool()
```

- [ ] **Step 2: import 스모크 + 기존 스위트 회귀 없음 확인**

Run: `cd nexus && python -c "import nexus.api" && python -m pytest -q`
Expected: import OK; 기존 + 신규 전부 PASS, 통합만 skip (회귀 0).

- [ ] **Step 3: 커밋**

```bash
git add nexus/nexus/api.py
git commit -m "feat(nexus/api): ensure_search_log on startup (lifespan)"
```

### Task 5: `/search`·`/search/answer` 배선

**Files:**
- Modify: `nexus/nexus/api.py` (`search` 170-261, `search_answer` 264-327)

- [ ] **Step 1: import 추가** — api.py 상단 import 블록

```python
import time
from nexus.search.signals import extract_signals, record_search
```

- [ ] **Step 2: `/search` 배선** — `search()` try 본문 시작에 `_t0 = time.time()` 추가, `return NexusResponse(...)` 직전에:

```python
        sig = extract_signals(
            result, None, path="search",
            tenant=req.tenant, clearance=req.classification_max, query=req.query,
            n_entities=len(entity_rids),
            latency_ms=int((time.time() - _t0) * 1000),
        )
        await record_search(sig)   # fire-and-forget
        return NexusResponse(...)  # 기존 그대로
```

- [ ] **Step 3: `/search/answer` 배선** — `search_answer()` try 시작에 `_t0 = time.time()`, `return` 직전에:

```python
        sig = extract_signals(
            search_result, answer_result, path="search_answer",
            tenant=req.tenant, clearance=req.classification_max, query=req.query,
            n_entities=len(entity_rids),
            latency_ms=int((time.time() - _t0) * 1000),
        )
        await record_search(sig)   # fire-and-forget
        return NexusResponse(...)  # 기존 그대로
```

- [ ] **Step 4: 회귀 없음 확인 + ruff**

Run: `cd nexus && python -m pytest -q && python -m ruff check nexus/api.py`
Expected: 전체 PASS(통합 skip), ruff clean.

- [ ] **Step 5: 커밋**

```bash
git add nexus/nexus/api.py
git commit -m "feat(nexus/api): record search signals on /search and /search/answer"
```

### Task 6: CLI `_query()` 배선 + `status` 신호 한 줄

**Files:**
- Modify: `nexus/nexus/cli.py` (`_query` 204-265, `status` 명령)

- [ ] **Step 1: `_query()` 배선** — `_query` 시작에 `import time; _t0 = time.time()`. `answer_result = None`을 `if answer and result.hits:` 블록 *이전*에 초기화하고, 블록 안에서 기존대로 대입. 그리고 **`await db.close_pool()` 바로 앞에** 추가:

```python
        from nexus.search.signals import extract_signals, record_search
        sig = extract_signals(
            result, answer_result, path="cli",
            tenant=tenant, clearance="INTERNAL", query=q,
            n_entities=len(entity_rids),
            latency_ms=int((time.time() - _t0) * 1000),
        )
        await record_search(sig, await_persist=True)   # close_pool 이전에 적재 완료
        await db.close_pool()
```

- [ ] **Step 2: `status` 명령에 신호 요약 추가** — `status` 명령의 `_status()` 본문에서, 기존 doc/chunk 카운트 출력 뒤 **`await db.close_pool()` 이전에**:

```python
        try:
            row = await db.fetch_one(
                """
                SELECT count(*) AS n,
                       avg((no_answer)::int) AS no_ans,
                       avg((graph_requested AND n_graph_edges = 0)::int) AS graph_empty,
                       percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95
                FROM search_log WHERE ts > now() - interval '7 days'
                """
            )
            if row and row["n"]:
                typer.echo(
                    f"검색 신호 (7d): {row['n']:,}건 · "
                    f"no-answer {float(row['no_ans'] or 0) * 100:.1f}% · "
                    f"graph-empty {float(row['graph_empty'] or 0) * 100:.1f}% · "
                    f"p95 {int(row['p95'] or 0)}ms"
                )
            else:
                typer.echo("검색 신호: 없음")
        except Exception:
            typer.echo("검색 신호: 없음")   # 구버전 DB(테이블 부재) 우아한 격하
```

> `status` 명령의 정확한 구조/`close_pool` 위치를 먼저 열어 확인하고, 위 블록을 그 직전에 삽입한다.
> (status 요약은 가중평균 계산이 번거로운 뷰 대신 base 테이블을 직접 집계 — 뷰는 path/route 분해용으로 남는다.)

- [ ] **Step 3: CLI 스모크 + 회귀**

Run: `cd nexus && python -c "import nexus.cli" && python -m pytest -q && python -m ruff check nexus/cli.py`
Expected: import OK, 전체 PASS, ruff clean. (DB 없이 `nexus status`는 "검색 신호: 없음" 격하 — 예외 없음.)

- [ ] **Step 4: 커밋**

```bash
git add nexus/nexus/cli.py
git commit -m "feat(nexus/cli): record signals in query (await before close_pool) + status summary"
```

### Task 7: A2A `_default_answer_fn` 배선

**Files:**
- Modify: `nexus/nexus/a2a/server.py:216-267` (`_default_answer_fn`)

- [ ] **Step 1: 배선** — `_default_answer_fn` 시작에 `import time; _t0 = time.time()`. `answer_result = await generate_answer(...)`로 받은 뒤(현재는 바로 return), 기록 후 반환:

```python
    answer_result = await generate_answer(
        query=query, packet=packet, llm_svc=llm_svc,
        route_used=route, timing_ms=search_result.timing_ms,
    )
    from nexus.search.signals import extract_signals, record_search
    sig = extract_signals(
        search_result, answer_result, path="a2a",
        tenant=tenant, clearance=clearance, query=query,
        n_entities=len(entity_rids),
        latency_ms=int((time.time() - _t0) * 1000),
    )
    await record_search(sig)   # fire-and-forget; a2a_audit(인가)와 별개로 품질 기록
    return answer_result
```

> 외부 jsonrpc 핸들러는 변경하지 않는다(SearchResult 미보유). 주입된 커스텀 `resolved_answer_fn`은 신호를 남기지 않음 — 의도된 범위(스펙 §Approach).

- [ ] **Step 2: A2A 스위트 회귀 없음 확인**

Run: `cd nexus && python -m pytest tests/test_a2a_server.py tests/test_a2a_audit.py tests/test_a2a_integration.py -q && python -m ruff check nexus/a2a/server.py`
Expected: PASS, ruff clean. (`_default_answer_fn`은 DB 풀 필요 경로라 단위 스위트에선 커스텀 answer_fn을 쓰므로 record_search 미발화 — 회귀 0 확인.)

- [ ] **Step 3: 커밋**

```bash
git add nexus/nexus/a2a/server.py
git commit -m "feat(nexus/a2a): record search signals inside _default_answer_fn"
```

---

## Chunk 4: 전체 검증

### Task 8: 전체 스위트 + ruff + (선택) DB 통합

- [ ] **Step 1: 전체 단위 스위트**

Run: `cd nexus && python -m pytest -q`
Expected: 기존(300) + 신규(test_signals 9) PASS, 통합(test_signals_db 2 + 기존 e2e) skip. 회귀 0.

- [ ] **Step 2: 전체 ruff**

Run: `cd nexus && python -m ruff check nexus/ tests/`
Expected: 신규/수정 파일에서 새 finding 0 (기존 carry-over 외).

- [ ] **Step 3: (DB 있으면) 통합 실행**

Run: `cd nexus && docker compose -f docker-compose.test.yml up -d && NEXUS_TEST_DB_URL=postgresql://nexus:nexus@localhost:5433/nexus_test python -m pytest tests/test_signals_db.py tests/test_e2e.py -q; docker compose -f docker-compose.test.yml down`
Expected: 통합 PASS.

- [ ] **Step 4: PR**

```bash
git push -u origin feat/nexus-search-signal-collection
gh pr create --title "feat(nexus): search quality-signal collection (search_log + v_search_health + status)" --body "<스펙 §요약 + 검증 결과>"
```

---

## 완료 기준 (Definition of Done)

- `extract_signals` 순수 함수 + `record_search` best-effort 싱크(절대 raise 안 함) 구현·테스트.
- `search_log` 테이블·인덱스·`v_search_health` 뷰가 init.sql + startup ensure 양쪽에서 멱등 생성.
- 4경로(`/search`·`/search/answer`·CLI·A2A) 모두 신호 기록. 서버=fire-and-forget, CLI=close_pool 이전 await.
- PII-safe: 원문 query는 어디에도 저장 안 됨(sha256+len만) — 테스트로 강제.
- `nexus status`가 7일 신호 요약 한 줄 출력, 테이블 부재 시 "없음"으로 격하.
- 전체 단위 스위트 회귀 0, ruff clean. DB 통합 테스트는 DB 있을 때 PASS.
- 범위 밖(명시 피드백·SSE 스트리밍·뷰 tenant 그룹화·api /status 보강)은 구현하지 않음.
