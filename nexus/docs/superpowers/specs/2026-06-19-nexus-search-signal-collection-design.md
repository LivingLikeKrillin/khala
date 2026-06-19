# Nexus 검색 품질 신호 수집 체계 — design

**Date:** 2026-06-19
**Status:** approved (brainstorming) → spec review
**Scope:** 단일 슬라이스. demand-pull 게이트(리랭킹 / 그래프-랭킹 / LLM-보조-추출)를 여닫을
신호를 싸게 상시 수집하고, 리서치가 지적한 관측성 공백을 닫는다. Related:
[durable A2A audit (`a2a_audit`)](../../../../specs/SPEC-nexus-a2a-external-exposure-audit-phase2.md),
[ROADMAP GraphRAG 정렬 평가](../../../ROADMAP.md).

## Problem

Nexus는 검색 품질 신호를 **거의 남기지 않는다.** `/search`·`/search/answer`·CLI는 `structlog`로
흘려보낼 뿐 영속하지 않고, `AnswerResult`에는 답변 confidence 필드조차 없다. 유일하게 영속되는
관측 데이터는 `a2a_audit`인데, 이는 **A2A 경로의 인가/접근 기록**(principal·denied·task_state)이라
검색 *품질* 렌즈가 아니다.

그 결과, 우리가 ROADMAP에 demand-pull 게이트로 둔 기능들(리랭킹·그래프-랭킹·LLM-보조-추출)을
**열어야 할지 판단할 신호가 없다.** "검색 품질 불만"을 추측이 아니라 측정으로 잡으려면, 게이트마다
대응하는 신호를 상시 수집해야 한다. 이는 외부 RAG 운영 회고가 "배포된 프로토타입의 진짜 #1 공백은
관측성 — retrieved docs/grounding 미로깅"이라 지적한 바와 정확히 같은 공백이다.

## Goal

검색 1건마다 **PII-safe 품질 신호 1행**을, 모든 경로(HTTP·CLI·A2A)에서, **요청 핫패스에 지연을
더하지 않고** 영속한다. 그 위에 롤링 집계 뷰와 `nexus status` 요약을 얹어, 게이트 판단 신호를
운영자가 한 줄로 본다.

각 신호 컬럼은 특정 게이트에 직접 매핑된다:

| 신호 | 매핑되는 게이트/관심사 |
|------|------------------------|
| `top_score`, `no_answer` | 리랭킹 / 검색 공백 (정답이 있는데 상위에 못 옴, 또는 무결과) |
| `n_entities` | LLM-보조-추출 (gazetteer 미적중) |
| `graph_requested` vs `n_graph_edges` | 그래프-랭킹 (관계 질의인데 그래프 비어 답 못함) |
| `llm_failed`, `latency_ms` | 운영 안정성 |

## Non-goals (YAGNI / Stage 2 — demand-pull)

- **명시 피드백**(👍/👎), 재질의(re-ask) 감지, 근거 클릭스루 — Stage 2. 실제 사용자 트래픽이
  생긴 뒤에만.
- **채널 불일치 컬럼**(bm25-only / vector-only top) — `top_score`+`no_answer`가 검색 취약을 이미
  프록시. 필요해지면 추가.
- **뷰의 tenant 그룹화** — `tenant` 컬럼은 적재하되 뷰는 path+route만 그룹화(ad-hoc 질의로 충분).
- **api `/status` JSON 보강** — CLI `nexus status`가 운영자 표면. 선택적 후속.
- **a2a_audit 변경 일절 없음** — "A2A는 더 안 건드린다" 결정 존중. search_log는 독립 표면.

## Approach

진입점(api `/search`·`/search/answer`, cli `query`, `a2a/server.py`)이 공용 헬퍼로 신호를
조립해 `record_search`를 **한 번** 호출한다. `a2a_audit`의 `record_audit` 호출 패턴과 동형 —
진입점만이 "검색 + 답변 + 경로"를 한 자리에서 안다. 기록은 fire-and-forget(서버) / await(CLI).

결정론(신호 추출)과 IO(영속)를 분리해, 추출은 순수 함수로 단위 테스트하고 IO는 절대 raise하지
않는 best-effort 싱크로 격리한다. `a2a_audit`/`record_audit`이 검증한(PR #23) 패턴을 미러링한다.

## 1. 스키마 — 새 `search_log` 테이블

`a2a_audit` 관례를 그대로 따른다: `BIGSERIAL` PK, `ts DEFAULT now()`, **원문 절대 저장 안 함 —
`query_sha256` + `query_len`만**(Nexus 원칙 #3). edge가 아니라 이벤트 인덱스이므로 "Nexus는
인덱스지 저장소가 아니다" 원칙과 합치한다.

```sql
CREATE TABLE IF NOT EXISTS search_log (
    id              BIGSERIAL PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT now(),
    path            TEXT NOT NULL,            -- 'search' | 'search_answer' | 'cli' | 'a2a'
    tenant          TEXT,
    clearance       TEXT,
    route           TEXT,                     -- hybrid_only | hybrid_then_graph | graph_then_hybrid
    query_sha256    TEXT NOT NULL DEFAULT '',
    query_len       INTEGER NOT NULL DEFAULT 0,
    n_snippets      INTEGER NOT NULL DEFAULT 0,
    top_score       DOUBLE PRECISION,         -- RRF top-1 점수 (NULL = 무결과)
    n_entities      INTEGER NOT NULL DEFAULT 0,   -- 감지된 gazetteer 엔티티 수
    graph_requested BOOLEAN NOT NULL DEFAULT false,
    n_graph_edges   INTEGER NOT NULL DEFAULT 0,   -- designed + observed 합
    no_answer       BOOLEAN NOT NULL DEFAULT false,  -- n_snippets == 0
    llm_failed      BOOLEAN NOT NULL DEFAULT false,  -- 답변 경로 한정 (그 외 항상 false)
    latency_ms      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_search_log_ts     ON search_log (ts DESC);
CREATE INDEX IF NOT EXISTS idx_search_log_tenant ON search_log (tenant, ts DESC);
CREATE INDEX IF NOT EXISTS idx_search_log_route  ON search_log (route, ts DESC);
```

**컬럼 의미론(모호성 제거):**
- `top_score`: `SearchResult.hits[0].score`(RRF 융합 점수). hits 비면 `NULL`.
- `n_snippets`: `len(SearchResult.hits)`. (답변 경로의 evidence snippet 수와 동일 — packet은 hits로 조립됨.)
- `n_entities`: 진입점이 감지해 `hybrid_search(entity_rids=…)`로 넘긴 엔티티 수(`len(entity_rids)`).
  진입점에서 엔티티 감지를 하지 않는 경로(예: 순수 텍스트 검색)는 0.
- `graph_requested`: `route in ('hybrid_then_graph','graph_then_hybrid')`.
- `n_graph_edges`: `len(graph.edges) + len(graph.observed_edges)` (graph 없으면 0).
- `no_answer`: `n_snippets == 0`. 검색이 근거를 못 찾은 경우(답변 경로의 "찾을 수 없습니다" 분기와 일치).
- `llm_failed`: 답변 경로에서 `AnswerResult.llm_failed`. 검색 전용 경로는 항상 false.
- `path='a2a'`: A2A 경로는 `a2a_audit`(인가)과 `search_log`(품질)에 **둘 다** 기록. 관심사가 다르고
  둘 다 best-effort·저트래픽이라 이중 기록 허용.

## 2. 컴포넌트 — `nexus/search/signals.py` (신규 모듈)

**`extract_signals(result, answer, *, path, tenant, clearance, query) -> SearchSignals`** — 순수 함수.
`SearchResult`와 선택적 `AnswerResult`에서 위 컬럼 의미론대로 신호를 조립해 `SearchSignals`
dataclass를 반환한다. IO·시각·랜덤 없음 → 완전 단위 테스트 가능.

**`record_search(sig, *, await_persist=False) -> None`** — IO 싱크. `record_audit` 계약 그대로:
1. **항상** `log.info("search.signal", …)` (동기, 외부 의존 0, 에어갭 유지). 여기서 query는 받지 않고
   이미 해시된 `query_sha256`/`query_len`만 받는다(원문이 싱크에 들어오지 않음).
2. `db.has_pool()`일 때만 INSERT. **서버 경로**(api/a2a)는 `asyncio.create_task`로 fire-and-forget →
   응답 지연에 DB 쓰기가 더해지지 않음. **CLI**는 `await_persist=True`로 인라인 await(핫패스 아님 +
   `asyncio.run` 종료 시 백그라운드 태스크 유실 방지).
3. INSERT 실패는 삼키고 `log.warning("search.signal.persist_failed", error=…)`. **record_search는
   요청 경로를 절대 raise로 깨지 않는다.**

`query_sha256`는 layering상 `search`가 `a2a`에 의존하지 않도록 `signals.py` 내부에 1줄 헬퍼로 둔다
(`a2a/audit.py`의 동명 함수와 동일 구현, 의도적 소규모 중복).

`SearchSignals` dataclass는 `record_search`가 받는 입력이자 INSERT 컬럼과 1:1.

## 3. 데이터 흐름

```
진입점 (api /search·/search/answer | cli query | a2a server)
  → hybrid_search(...)        → SearchResult
  → (답변 경로) generate_answer → AnswerResult
  → sig = extract_signals(result, answer?, path=…, tenant, clearance, query)
  → record_search(sig, await_persist=<CLI면 True>)
        · log.info("search.signal", …)     # 항상, 동기
        · db.has_pool() → create_task(INSERT) (서버) / await INSERT (CLI)   # best-effort
  → 응답 반환 (서버 경로의 INSERT는 백그라운드에서 완료)
```

## 4. 집계 — `v_search_health` 뷰

롤링 7일 윈도우, path+route별 그룹. 리서치 교훈(평균은 국소 실패를 가린다)을 반영해 p95(꼬리)를 포함.

```sql
CREATE OR REPLACE VIEW v_search_health AS
SELECT path, route,
       count(*)                                                      AS n,
       avg((no_answer)::int)::numeric(4,3)                           AS no_answer_rate,
       avg((graph_requested AND n_graph_edges = 0)::int)::numeric(4,3) AS graph_empty_rate,
       avg((llm_failed)::int)::numeric(4,3)                          AS llm_fail_rate,
       avg(n_snippets)::numeric(6,2)                                 AS avg_snippets,
       percentile_disc(0.95) WITHIN GROUP (ORDER BY latency_ms)      AS p95_latency_ms
FROM search_log
WHERE ts > now() - interval '7 days'
GROUP BY path, route;
```

`graph_empty_rate`는 그래프-랭킹 게이트의 직접 신호, `no_answer_rate`는 검색 공백/리랭킹 신호다.
`tenant`별 분석은 컬럼이 있으므로 ad-hoc SQL로 충분(뷰 그룹화는 YAGNI).

## 5. 노출 — `nexus status`

`cli.py`의 `status` 커맨드에 한 줄 추가: `v_search_health`를 읽어 전체 합산 요약을 출력한다. 예:

```
검색 신호 (7d): 1,234건 · no-answer 4.2% · graph-empty 1.1% · p95 180ms
```

테이블/뷰가 없거나(구버전 DB) 데이터가 0건이면 `검색 신호: 없음`으로 우아하게 격하(예외 금지).

## 6. 스키마 적용 / 마이그레이션

- `init.sql`에 테이블 + 인덱스 + 뷰 DDL 추가(신규 DB 자동 생성).
- **추가로** 앱 startup에서 멱등 `ensure_search_log()` 실행 → 기존 배포 DB도 즉시 적재 시작.
  모든 DDL은 `IF NOT EXISTS`/`CREATE OR REPLACE`라 init.sql과 startup 양쪽에서 안전(멱등).
  - `a2a_audit`은 init.sql만 의존하고 테이블 부재 시 graceful-degrade했으나, 본 기능의 목적은
    "실제로 신호를 모으는 것"이므로 startup ensure를 더한다.
  - ensure는 `db.has_pool()` 가드 + 실패 삼킴(로그만) — startup을 깨지 않는다.

## 7. 에러 처리

- **DB 다운 / 풀 없음** → `structlog`만 기록, 무오류. 신호는 로그 사이드로 살아남음.
- **백그라운드 INSERT 실패**(서버) → 삼킴 + `search.signal.persist_failed` 경고.
- **CLI await INSERT 실패** → 동일하게 삼킴, status 출력/검색 결과에 영향 없음.
- **`extract_signals`** 는 순수 함수이며 None 안전(graph 없음, hits 비음, answer None)을 모두 처리.
- **`v_search_health` / 테이블 부재** → `nexus status`가 잡아 "없음"으로 격하.
- 불변식: **record_search·extract_signals 어느 것도 검색/답변/CLI 경로를 raise로 중단시키지 않는다.**

## 8. 테스트

**단위 (DB 불필요, `test_hybrid` 순수함수 스타일):**
- `extract_signals`: hits 비면 `no_answer=True`·`top_score=None`; hits 있으면 `top_score=hits[0].score`;
  `graph_requested`와 `n_graph_edges` 조합(요청했으나 0 → graph-empty 케이스); `answer=None`이면
  `llm_failed=False`; `answer.llm_failed=True` 전파.
- `record_search`: `db.has_pool()`=False → `log.info`만, INSERT 시도 없음, 무예외.
- `record_search`: 가짜 풀이 INSERT에서 raise → 삼킴, 무예외.

**통합 (DB-gated, 무DB 시 skip — `test_e2e` 관례):**
- `ensure_search_log()` 후 행 1개 INSERT → `v_search_health` 질의 → 집계(no_answer_rate 등) 검증.

## 단위(units)와 경계

- `signals.extract_signals` — 입력 `SearchResult`/`AnswerResult` → 출력 `SearchSignals`. 순수.
- `signals.record_search` — 입력 `SearchSignals` → 부수효과(structlog + best-effort INSERT). 무반환.
- `db.ensure_search_log` (또는 startup 훅) — 멱등 DDL.
- `v_search_health` — 읽기 전용 집계. `nexus status`가 유일 소비자(현재).
- 진입점들은 위 단위를 호출만 한다(조립 로직은 `extract_signals`에 응집).
