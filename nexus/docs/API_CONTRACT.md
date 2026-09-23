# Nexus API 계약서

> **이 문서는 전체 목록이 아니다.** 핵심 8개 엔드포인트의 request/response 스키마와, 모든 엔드포인트에 공통으로 걸리는 규칙을 정의한다.
> FastAPI + Pydantic v2 기준. Claude Code는 이 문서를 보고 정확한 Pydantic 모델을 생성해야 한다.

## 문서 범위 및 관리 원칙

전체 API 명세의 정본은 런타임 FastAPI 애플리케이션이 자동 생성하는 `/docs`(Swagger UI) 및 `/openapi.json`입니다. 본 문서는 자동 생성 스키마만으로 파악하기 어려운 런타임 거버넌스 규칙과 핵심 경로의 계약을 정의합니다:

1. **공통 거버넌스 규칙 (§공통 규칙)** — 공통 응답 래퍼(`NexusResponse`), 표준 에러 포맷, 테넌트/보안등급(`tenant`/`classification`) 자동 격리 필터, 리소스 식별자(`rid`) 생성 규약 등 전역 시스템 불변식을 명시합니다.
2. **핵심 엔드포인트 계약 (§1–§8)** — 검색, 수집, 지식 그래프, 설계-관측 diff, 헬스체크 등 외부 클라이언트 및 에이전트와 연동되는 핵심 API의 입출력 계약을 정의합니다.

여기 없지만 존재하는 계열(스키마는 `/docs` 참조):

| 계열 | 대략의 경로 | 다루는 문서 |
|---|---|---|
| Notion 소스 콘솔 | `/roots` · `/sync` · `/preview` · `/sync/{run_id}` | — (콘솔 UI가 유일한 소비자) |
| 문서 생애주기 | `/documents/{rid}` · `/hide` · `/restore` · `/supersede` · `/unsupersede` | — |
| 답변 피드백 | `/feedback/offer` · `/vote` · `/reason` | [SLACK_BOT.md](SLACK_BOT.md) |
| 클레임·권위 | `/claims/value` · `/claims/grade-authority` | — (Archon 계열, 코드가 정본) |
| 운영 | `/health` · `/corpus` · `/visibility` · `/auth/dev-token` | [TEAM_DOGFOOD_DEPLOY.md](TEAM_DOGFOOD_DEPLOY.md) |

> `/auth/dev-token`은 **의도적으로 비-게이트**다(토큰을 받기 전 단계라 게이트를 걸 수 없다). `NEXUS_DEV_TOKEN`이 설정된 로컬 dev에서만 값을 돌려주고, 미설정 시 `token=null`이라 노출이 없다. 따라서 위험은 엔드포인트 자체가 아니라 **외부에 노출된 배포에 그 env를 설정하는 것**이다.

## 공통 규칙

- 모든 응답은 `NexusResponse` wrapper로 감싼다
- 에러는 HTTP status code + `error` 필드로 반환
- 모든 검색/조회에 `tenant` + `classification` 필터 자동 적용
- timestamp는 ISO 8601 형식 (UTC)
- rid는 항상 `make_rid()` 함수로 생성된 값
- **모르는 요청 칸은 `422` 로 거절한다** (아래 §모르는 칸)
- **요청이 보낸 값이 아니라 서버가 실제로 한 것을 응답에 싣는다** (아래 §서버가 한 것)

### 모르는 칸 — 버리지 않고 거절한다 (2026-09-23)

요청 모델 전부가 `extra="forbid"` 다(`api.py` 의 `RequestModel` 한 곳에 있다). 스키마에 없는
칸이 오면 **`422` 와 함께 그 칸 이름을 돌려준다.**

전에는 pydantic 기본값(`extra="ignore"`)이라 **`200` 과 함께 조용히 사라졌다.** 오타든, 낡은
깃발이든, 그 표면에 없는 깃발이든 결과가 같아서 호출자는 *"켰는데 안 걸렸다"* 와 *"여기서는
켤 수 없다"* 를 구별할 수 없었다. 한 소비자는 그 자리를 자기 소스에 **덫으로 적고 우회**하고
있었다.

⚠ **이것은 이름만 본다.** 이름이 맞는데 값이 안 먹은 것은 `422` 가 안 난다 — 그건 아래 규칙이
맡는다. 둘은 같은 이음매의 반대쪽 반이고 서로 대신하지 못한다.

⛔ 정책을 모델마다 적지 않는다. 갈리면 **같은 오타가 한 표면에서는 `422` 이고 다른 표면에서는
통과한다** — 갈리는 것이 조용한 것보다 나쁘다.

### 서버가 한 것 — 요청을 그대로 돌려주지 않는다

범위·필터·처치는 요청이 정하지 못한다. `tenant` 는 토큰이 정하고 요청은 **좁히기만** 하며,
범위 밖을 물어도 **오류를 내지 않는다**(그 테넌트가 있는지를 흘리지 않기 위해서다,
`auth/scope.py::resolve_read_scope`). 그래서 그 대신이 규칙으로 걸려 있다 — **응답에 해소된
결과를 싣는다.** 없으면 호출자는 코퍼스 X 를 묻고 Y 로 답을 받고도 아무 신호를 못 받는다.

같은 이유로 붙어 있는 칸들:

| 칸 | 무엇을 가르나 | 어디 |
|---|---|---|
| `searched_tenants` | 실제로 후보였던 코퍼스 | `/search` · `/search/answer` · `…/stream` |
| `excluded_doc_types` | 오타로 무시된 것 / 목록이 통째로 안 닿은 것 | `/search/answer` |
| `identifier_channel` + `_asked` | 안 켰다 / 켰는데 발화 안 했다 | `/search/answer` |
| `n_unknown_origin_time` | 좁히기가 닿지 못한 건수 (**안 물었으면 `None`**) | 검색·답변 |
| `degraded` · `enrichment_failed` | 빈 결과 / 죽은 경로 | 검색·답변 |

⚠ **범위 밖이었다는 사실 자체는 안 싣는다** — 그것을 알리면 그 테넌트가 있다는 것이 샌다
(1R I-009). 그건 운영자 로그로만 간다.

⭐ HTTP 밖의 표면도 같은 사실을 **자기 어법으로** 낸다: A2A 는 아티팩트의
`policy.tenant`, CLI `query` 는 출력 첫 줄의 `코퍼스:` 다. 표면이 늘면
`tests/test_the_agent_surfaces_say_which_corpus_they_searched.py` 의 목록에 행을 더한다.

```python
class NexusResponse(BaseModel):
    success: bool
    data: Any | None = None
    error: str | None = None
    meta: dict | None = None  # pagination, timing 등
```

---

## 1. POST /search — Hybrid 검색

가장 핵심 엔드포인트. BM25 + Vector + RRF 결합 검색.

### Request
```python
class SearchRequest(BaseModel):
    query: str                          # 검색어 (한국어/영어/혼합)
    history: list[Turn] = []            # 대화 이력. U2 에서 서버는 상한만 걸고 버린다
    top_k: int = 10                     # 반환 결과 수
    route: str = "auto"                 # auto | hybrid_only | hybrid_then_graph | graph_then_hybrid
    classification_max: str = "INTERNAL"  # 사용자 clearance — **요청이 올릴 수는 없다**
    tenant: str = "default"             # 좁히기만 된다. 안 보내면 토큰의 범위 전체
    include_graph: bool = True          # Graph 확장 포함 여부
    include_evidence: bool = True       # Evidence snippet 포함 여부
    origin_since: datetime | None       # **문서 자신의** 시각 (`origin_updated_at`, migration 039)
    origin_until: datetime | None       # ⛔ 적재 시각이 아니다. 시각을 모르는 문서는 안 떨군다
```

⛔ **`tenant` 는 안 보내는 것과 보내는 것이 다르다.** 기본값이 채워 넣은 것과 호출자가 고른
것을 `model_fields_set` 으로 가른다 — 그러지 않으면 *"안 물으면 범위 전체"* 가 영원히 발화하지
않는다(실측 2026-08-31, 컷오버가 그 자리에서 조용히 무효가 됐다). ⚠ 그래서 **칸 이름을 오타
내면 범위가 좁아지는 게 아니라 넓어진다** — 「안 물었다」로 읽히기 때문이다. 오타 자체는
`422` 가 잡는다(§모르는 칸).

### Response
```python
class SearchResult(BaseModel):
    rid: str                            # chunk rid
    doc_rid: str                        # 소속 문서 rid
    doc_title: str
    section_path: str                   # H1 > H2 경로
    source_uri: str                     # 원본 위치 (git://...)
    snippet: str                        # chunk_text 중 관련 부분 (highlight)
    score: float                        # RRF fusion 점수
    bm25_rank: int | None               # BM25 순위 (있으면)
    vector_rank: int | None             # Vector 순위 (있으면)
    classification: str

class GraphFinding(BaseModel):
    designed_edges: list[EdgeSummary]    # 문서 기반 edge
    observed_edges: list[ObservedEdgeSummary]  # OTel 기반 edge
    diff_flags: list[str]               # doc_only, observed_only, conflict

class EdgeSummary(BaseModel):
    edge_rid: str
    edge_type: str                      # CALLS | PUBLISHES | SUBSCRIBES
    from_entity: str                    # entity name
    to_entity: str
    confidence: float
    evidence_count: int

class ObservedEdgeSummary(BaseModel):
    edge_rid: str
    edge_type: str                      # CALLS_OBSERVED
    from_entity: str
    to_entity: str
    call_count: int
    error_rate: float
    latency_p95: float
    last_seen_at: str                   # ISO 8601
    sample_trace_ids: list[str]

class SearchResponse(BaseModel):
    results: list[SearchResult]
    graph_findings: GraphFinding | None  # include_graph=true일 때
    route_used: str                     # 실제 사용된 route
    searched_tenants: list[str]         # 실제로 후보였던 코퍼스 — 요청이 보낸 값이 아니라
                                        # 토큰으로 해소된 범위다. 범위 밖을 물으면 오류 대신
                                        # 여기에 해소 결과가 온다 (§서버가 한 것, 비평 3R I-010)
    n_unknown_origin_time: int | None   # 좁히기가 닿지 못한 건수. 안 물었으면 None —
                                        # 0 으로 내보내면 "물었고 전부 안다" 와 구별되지 않는다
    timing_ms: float                    # 전체 소요 시간
    degraded: list[str]                 # 실패해서 기여하지 못한 경로 ("bm25"|"vector"|"graph")
                                        # 빈 결과와 죽은 경로는 다른 사실이다
                                        # (SPEC-nexus-embedding-cutover-seam §4.4)
    enrichment_failed: list[str]        # 터진 보강 패스. 같은 이유로 죽은 것과 빈 것을 가른다
```

### 에러 케이스
- `400`: query가 빈 문자열, 또는 없는 `route` (무엇을 고를 수 있는지 `detail` 에 나온다)
- `413` / `400`: `history` 가 상한을 넘거나 모양이 틀렸다 — **조용히 자르지 않는다** (SPEC §3.1)
- `422`: 스키마에 없는 요청 칸 (§모르는 칸). `detail` 이 그 칸 이름을 말한다
- `503`: DB 연결 실패 (partial result 반환 금지)

---

## 2. POST /search/answer — 검색 + LLM 답변

/search 결과를 Evidence Packet으로 조립하여 Claude에 전달, 근거 기반 답변 생성.

### Request
```python
class AnswerRequest(BaseModel):
    query: str
    history: list[Turn] = []
    top_k: int = 20                     # ⚠ **검색 전용 경로의 10 과 다르다.** 집합 질문이
                                        # 10 에서 잘렸다 — 근거가 8,163자에서 19,184자로 는다
                                        # (실측 2026-08-30). 유료 백엔드에서는 그대로 비용이다
    route: str = "auto"
    classification_max: str = "INTERNAL"
    tenant: str = "default"
    origin_since: datetime | None       # SearchRequest 와 같은 뜻
    origin_until: datetime | None
    exclude_doc_types: list[str] = []   # 후보 단계부터 뺄 문서 종류. **권한이 아니다** —
                                        # 좁히기만 하고 넓히지 못한다
    identifier_channel: bool = False    # 질의에 섞인 식별자만 따로 묻는 둘째 채널.
                                        # ⛔ **기본 꺼짐이 설계다** — 이것은 처치이고 측정
                                        # 대상이다 (`docs/PROCEDURE_RETRIEVAL_PREREGISTRATION.md` T2)
```

⚠ `identifier_channel` 은 **이 요청에만 있다.** `/search` 로 보내면 `422` 다 — 전에는 조용히
버려져서 *"켰는데 처치가 안 걸렸다"* 를 호출자가 알 방법이 없었다.

### Response
```python
class AnswerResponse(BaseModel):
    answer: str                         # LLM 생성 답변 (근거 인용 포함)
    evidence_snippets: list[EvidenceSnippet]
    graph_findings: GraphFinding | None
    provenance: list[ProvenanceRef]     # 사용자가 검증할 수 있는 출처
    route_used: str
    timing_ms: float
    degraded: list[str]                 # 검색 단계에서 죽은 경로 (SearchResponse 와 같은 뜻)

    # ── 표면이 답변 문장에서 **되읽을 수 없는** 사실들 ─────────────────────
    # 이 칸들이 빠지면 표면은 추측하거나 침묵한다. 전부 그렇게 한 번씩 데여서 생겼다.
    # 전체 목록의 정본은 `/openapi.json` 이고, 여기 적는 것은 **왜 있는가**다.
    searched_tenants: list[str]         # 무엇이 애초에 후보였나 (§서버가 한 것)
    excluded_doc_types: list[str]       # 실제로 SQL 에 간 것 — 오타로 무시된 것과
                                        # 목록이 통째로 안 닿은 것을 이 값으로 가른다
    identifier_channel: list[str]       # 식별자 채널이 **무엇으로 발화했나**
    identifier_channel_asked: bool      # 호출자가 **요청했는가** — 빈 목록 하나로는
                                        # "안 켰다" 와 "켰는데 식별자가 없었다" 가 안 갈린다
    abstained: bool                     # 기권은 코드가 내린 판단이다. 답변 문장을
    abstain_reason: str | None          # 문자열 대조해서 알아내지 않는다
    llm_failed: bool                    # **생성 실패는 답변이 아니다**
    llm_failure_reason: str | None      # 기다리면 되는 실패와 사람이 결제해야 하는 실패는
                                        # 같은 문장으로 나가면 안 된다 (`llm/failure.py`)
    weak_evidence: bool                 # 근거는 있었지만 **잘 맞지 않았다**
    top_distance: float | None          # 문턱에 겨우 걸린 것인지 한참 밖인지. None 은
    top_bm25: float | None              # 그 경로가 **못 낸 것**이고 0 이 아니다
    citations: list[Citation]           # 코드가 evidence packet 과 대조해 판정한 것
    unverified_citations: list[str]     # 해소되지 않은 인용 — 출처인 척 통과시키지 않는다
    unverified_numbers: list[str]       # 숫자도 같은 방식으로 검사한다 (`llm/numbers.py`)
    numbers: list[dict]                 # 수만 내면 무엇이 걸렸는지 못 본다
    n_stale: int                        # 낡았다고 판정된 근거 수
    evidence_tenants: dict[str, int]    # 실제로 기여한 코퍼스별 근거 수

class EvidenceSnippet(BaseModel):
    chunk_rid: str
    doc_title: str
    section_path: str
    source_uri: str
    text: str                           # 관련 chunk 텍스트
    score: float
    doc_type: str                       # 축-A 타입 (웹 신뢰 배지)
    provenance_tier: str                # 'authored' | 'machine_read' | 'machine_written'
                                        # (ADR-0010). 'machine_written' = LLM 이 만든 지난
                                        # 설명 — 사람이 쓴 문장이 아니다 (migration 043)
    updated_at: str | None              # ISO. staleness 판정 결과가 같이 붙는다
    code_anchors: dict | None           # 아래 — 앵커가 없는 코퍼스에서는 null

# 이 문단이 부른 코드 이름이 **지금도 코드에 있는가** (SPEC-nexus-doc-code-anchors §3.4).
# 판정은 서버가 끝내서 보낸다 — 클라이언트가 다시 세면 답이 둘이 된다.
# 이름은 어긋난 것만 싣는다: fresh 20개를 나열하면 아무도 안 읽는다.
{
  "total": 7,                 # 이 청크가 바인딩한 앵커 수 (분모)
  "fresh": 5,                 # 이름도 텍스트도 그대로
  "changed": ["Beta"],        # 이름은 있는데 본문이 바뀌었다
  "orphaned": ["Gamma"],      # 이름이 코드에서 사라졌다
  "ambiguous_now": [],        # 바인딩 뒤 동명이 생겼다 — 다시 겨누지 않는다
  # 문서가 부르는데 **지워진** 이름. 바인딩된 적이 없으므로 `total` 에 안 들어간다.
  # 외부 타입·미구현은 여기 오지 않는다 (git 이력으로 가른다, 마이그레이션 029).
  "deleted": [{"name": "AvatarBodyRequest", "date": "2026-02-21",
               "commit": "abc1234", "subject": "refactor: unify DTO naming"}]
}

class ProvenanceRef(BaseModel):
    doc_rid: str
    source_uri: str                     # git://repo/path
    source_version: str                 # commit SHA
```

### 에러 케이스
- `400`: query 빈 문자열, 또는 없는 `route`
- `413` / `400`: `history` 상한 초과 / 모양 오류 — **조용히 자르지 않는다** (SPEC §3.1)
- `422`: 스키마에 없는 요청 칸 (§모르는 칸)
- `503`: DB 연결 실패
- `502`: LLM API 호출 실패 → answer="답변을 생성할 수 없습니다" + evidence는 그대로 반환

⚠ **생성 실패는 `502` 로만 오지 않는다.** 근거는 살아 있고 서술만 죽은 실행은 `200` 에
`llm_failed=true` 로 온다 — 그 경우 답변 자리의 문자열을 답으로 렌더하면 안 된다.

---

## 3. POST /ingest — 문서 인덱싱

지정된 경로의 Markdown 문서를 인덱싱한다.

### Request
```python
class IngestRequest(BaseModel):
    path: str                           # 폴더 경로 또는 단일 파일
    force: bool = False                 # true면 hash 무시, 전체 재인덱싱
    tenant: str = "default"
```

### Response
```python
class IngestResponse(BaseModel):
    total_files: int                    # 스캔한 파일 수
    indexed: int                        # 인덱싱 완료
    skipped: int                        # hash 미변경으로 skip
    quarantined: int                    # PII/secret 감지로 격리
    failed: int                         # 실패 (로그 참조)
    errors: list[IngestError]

class IngestError(BaseModel):
    file_path: str
    error: str
    stage: str                          # collect | classify | chunk | embed | index
```

---

## 4. POST /upload — 파일 업로드 (비개발자용)

Markdown 파일을 업로드하면 Git repo에 저장 + 자동 인덱싱.

### Request
- Content-Type: multipart/form-data
- file: UploadFile (Markdown만 허용)
- path: str (저장 경로, 예: "guides/onboarding.md")
- tenant: str = "default"

### Response
```python
class UploadResponse(BaseModel):
    doc_rid: str
    source_uri: str                     # git://nexus-docs/guides/onboarding.md
    indexed: bool
    quarantined: bool
    message: str
```

### 에러 케이스
- `400`: Markdown이 아닌 파일
- `409`: 이미 같은 경로에 파일 존재 (덮어쓰려면 force=true 파라미터)

---

## 5. GET /graph/{entity_rid} — Entity 관계 조회

특정 entity의 이웃 관계를 조회한다. designed edge와 observed edge 모두 반환.

### Path Parameter
- `entity_rid`: entity의 rid (또는 entity name으로 조회 → 내부에서 rid 변환)

### Query Parameters
```
hops: int = 1                          # 1 또는 2
tenant: str = "default"
classification_max: str = "INTERNAL"
include_evidence: bool = true
```

### Response
```python
class GraphResponse(BaseModel):
    center_entity: EntityDetail
    edges: list[EdgeDetail]
    observed_edges: list[ObservedEdgeDetail]
    diff_flags: list[DiffFlag]

class EntityDetail(BaseModel):
    rid: str
    name: str
    type: str                           # Service | API | Topic | DB | Term
    aliases: list[str]
    description: str | None

class EdgeDetail(BaseModel):
    rid: str
    edge_type: str
    from_entity: EntityDetail
    to_entity: EntityDetail
    confidence: float
    evidence: list[EvidenceSnippet]     # include_evidence=true일 때

class ObservedEdgeDetail(BaseModel):
    rid: str
    edge_type: str                      # CALLS_OBSERVED
    from_entity: EntityDetail
    to_entity: EntityDetail
    call_count: int
    error_rate: float
    latency_p50: float
    latency_p95: float
    latency_p99: float
    last_seen_at: str
    sample_trace_ids: list[str]
    trace_query_ref: str

class DiffFlag(BaseModel):
    edge_rid: str | None
    observed_edge_rid: str | None
    flag: str                           # doc_only | observed_only | conflict
    detail: str                         # 사람이 읽을 수 있는 설명
```

### 에러 케이스
- `404`: entity_rid에 해당하는 entity 없음

---

## 6. GET /diff — 설계-관측 Diff 보고서

edges(designed)와 observed_edges의 불일치를 보고한다.

### Query Parameters
```
tenant: str = "default"
flag_filter: str | None = None         # doc_only | observed_only | conflict (없으면 전체)
entity_filter: str | None = None       # 특정 entity에 관련된 diff만
```

### Response
```python
class DiffResponse(BaseModel):
    total_designed_edges: int
    total_observed_edges: int
    diffs: list[DiffItem]
    generated_at: str                   # ISO 8601

class DiffItem(BaseModel):
    flag: str                           # doc_only | observed_only | conflict
    designed_edge: EdgeSummary | None
    observed_edge: ObservedEdgeSummary | None
    detail: str                         # "문서: A→B (HTTP sync), 관측: A→B (Kafka async)"
    designed_evidence: list[EvidenceSnippet]  # 문서 근거
    observed_evidence: list[str]        # trace_query_ref + sample_trace_ids
```

---

## 7. POST /otel/aggregate — OTel 집계 실행

Tempo에서 trace를 집계하여 CALLS_OBSERVED edge를 생성/갱신한다.

### Request
```python
class OtelAggregateRequest(BaseModel):
    window_minutes: int = 5             # 집계 윈도우 크기
    lookback_minutes: int = 60          # 얼마나 과거까지 볼 것인지
    tenant: str = "default"
```

### Response
```python
class OtelAggregateResponse(BaseModel):
    edges_created: int                  # 새로 생성된 observed_edge
    edges_updated: int                  # 기존 edge 메트릭 갱신
    unresolved_services: list[str]      # service name resolution 실패 목록
    timing_ms: float
```

---

## 8. GET /status — 시스템 상태

### Response
```python
class StatusResponse(BaseModel):
    db_connected: bool
    ollama_connected: bool              # Ollama 의 접속 가능성. 임베딩 백엔드인지와 무관하다
    tempo_connected: bool
    # 임베딩 세대 — 이 프로세스가 무엇으로·어디에 붙어 도는가 (SPEC-nexus-embedding-cutover-seam §4.5)
    embedding_model: str                # 예: nomic-embed-text | KURE-v1
    embedding_backend: str              # ollama | sidecar
    embedding_column: str               # embedding | embedding_1024
    embedding_backend_connected: bool   # **지금 쓰는** 백엔드가 사는가 (2초 타임아웃)
    embedding_revision: str | None      # 사이드카의 핀. Ollama 경로에서는 null
    embedding_coverage: list[dict]      # 테넌트별 {tenant, active, embedding, embedding_1024}
    embedding_waived: int               # 사람이 서명해 벡터 검색에서 뺀 청크 수
    documents_count: int
    chunks_count: int
    entities_count: int
    edges_count: int
    observed_edges_count: int
    quarantined_count: int
    last_ingest_at: str | None
    last_otel_aggregate_at: str | None
    diff_summary: DiffSummary

class DiffSummary(BaseModel):
    doc_only_count: int
    observed_only_count: int
    conflict_count: int
```

---

## 9. POST /search/answer/stream — 스트리밍 답변 (SSE)

검색 결과를 먼저 전송하고, LLM 답변을 SSE로 스트리밍한다. 2.0 UI 채팅에서 사용.

### Request
SearchRequest와 동일한 AnswerRequest 사용.

### SSE 이벤트

| Event | Payload | 전송 시점 |
|-------|---------|-----------|
| `evidence` | `{evidence_snippets, provenance, route_used, degraded}` | 검색 완료 직후 |
| `graph` | `{center, designed_edges, observed_edges}` | 그래프 조회 완료 시 |
| `answer_delta` | `{text}` | LLM 스트리밍 중 (incremental) |
| `done` | `{timing_ms}` | 완료 |
| `error` | `{error}` | 예외 발생 |

---

## 10. GET /entities/suggest — 엔티티 자동완성

### Query Parameters
```
q: str           # 검색어 (최소 1글자)
tenant: str = "default"
limit: int = 10  # 최대 50
```

### Response
```python
class EntitySuggestion(BaseModel):
    rid: str
    name: str
    type: str         # Service | API | Topic | DB | Term
    aliases: list[str]
    description: str | None
```

---

## 11. GET /documents — 문서 목록

### Query Parameters
```
tenant: str = "default"
classification_max: str = "INTERNAL"
offset: int = 0
limit: int = 20   # 최대 100
```

### Response
```python
class DocumentListItem(BaseModel):
    rid: str
    title: str
    source_uri: str
    source_version: str
    classification: str
    doc_type: str
    language: str
    chunk_count: int
    updated_at: str | None
```

### Meta
```python
meta: { "total": int, "offset": int, "limit": int }
```
