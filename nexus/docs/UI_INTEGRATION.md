# Khala 2.0 — UI 연동 규격

> Web UI / Slack Bot / MCP 클라이언트가 Khala API를 사용할 때의 연동 규격.
> 모든 인터페이스는 동일한 FastAPI 백엔드를 공유한다.

---

## 1. 전체 구조

```
┌─────────────────────────────────────────────┐
│  Web UI (React/Next.js)                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐ │
│  │ 검색 채팅  │ │ 그래프 뷰  │ │ 문서 브라우저  │ │
│  └────┬─────┘ └────┬─────┘ └──────┬───────┘ │
│       │            │              │          │
└───────┼────────────┼──────────────┼──────────┘
        │            │              │
   SSE Stream    REST GET       REST GET
        │            │              │
┌───────┴────────────┴──────────────┴──────────┐
│  Khala FastAPI Backend                       │
│  POST /search/answer/stream  (SSE)           │
│  POST /search                (JSON)          │
│  POST /search/answer         (JSON)          │
│  GET  /graph/{entity}        (JSON)          │
│  GET  /entities/suggest      (JSON)          │
│  GET  /documents             (JSON)          │
│  GET  /diff                  (JSON)          │
│  GET  /status                (JSON)          │
└──────────────────────────────────────────────┘
```

---

## 2. 응답 규약

### 2.1 공통 응답 포맷

모든 REST 엔드포인트는 `KhalaResponse`로 감싼다.

```json
{
  "success": true,
  "data": { ... },
  "error": null,
  "meta": { "total": 42, "offset": 0, "limit": 20 }
}
```

### 2.2 에러 응답

```json
{
  "success": false,
  "data": null,
  "error": "데이터베이스 연결 실패",
  "meta": {}
}
```

| HTTP Status | 의미 | UI 처리 |
|-------------|------|---------|
| 400 | 잘못된 요청 (빈 쿼리 등) | 입력 필드에 인라인 에러 표시 |
| 404 | 엔티티 없음 | "결과 없음" 안내 |
| 409 | 파일 중복 (업로드) | 덮어쓰기 확인 다이얼로그 |
| 500 | 서버 내부 오류 | 토스트 알림 + 재시도 버튼 |
| 503 | DB 연결 실패 | 전체 서비스 불가 배너 |

---

## 3. 검색 + 채팅 (핵심 기능)

### 3.1 비스트리밍 검색 (검색 결과만 필요한 경우)

```
POST /search
Content-Type: application/json

{
  "query": "결제 서비스가 발행하는 토픽이 뭐야?",
  "top_k": 10,
  "route": "auto",
  "classification_max": "INTERNAL",
  "tenant": "default",
  "include_graph": true,
  "include_evidence": true
}
```

### 3.2 스트리밍 답변 (채팅 UI)

SSE(Server-Sent Events)를 사용한다. 검색 결과와 LLM 답변을 순차적으로 스트리밍한다.

```
POST /search/answer/stream
Content-Type: application/json

{
  "query": "결제 서비스가 발행하는 토픽이 뭐야?",
  "top_k": 10,
  "route": "auto",
  "classification_max": "INTERNAL",
  "tenant": "default"
}
```

**SSE 이벤트 시퀀스:**

```
event: evidence
data: {"evidence_snippets": [...], "provenance": [...], "route_used": "hybrid_then_graph"}

event: graph
data: {"center": "payment-service", "designed_edges": [...], "observed_edges": [...]}

event: answer_delta
data: {"text": "결제 서비스는 "}

event: answer_delta
data: {"text": "payment.completed 토픽을 "}

event: answer_delta
data: {"text": "발행합니다."}

event: done
data: {"timing_ms": {"total_ms": 1234, "bm25_ms": 45}}
```

**이벤트 타입:**

| Event | 설명 | 전송 시점 |
|-------|------|-----------|
| `evidence` | 검색 결과 (snippets + provenance) | 검색 완료 직후, LLM 호출 전 |
| `graph` | 그래프 관계 데이터 | 그래프 조회 완료 시 (없으면 생략) |
| `answer_delta` | LLM 답변 조각 (incremental) | LLM 스트리밍 중 |
| `done` | 완료 신호 + 타이밍 정보 | 모든 처리 완료 |
| `error` | 에러 발생 | 처리 중 예외 발생 시 |

**UI 구현 가이드:**

```javascript
// EventSource 사용 예시 (POST는 fetch + ReadableStream으로)
const response = await fetch('/search/answer/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ query, top_k: 10, route: 'auto' }),
});

const reader = response.body.getReader();
const decoder = new TextDecoder();
let answer = '';

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  const text = decoder.decode(value);
  for (const line of text.split('\n')) {
    if (line.startsWith('event: ')) {
      currentEvent = line.slice(7);
    } else if (line.startsWith('data: ')) {
      const data = JSON.parse(line.slice(6));
      switch (currentEvent) {
        case 'evidence':
          // 사이드패널에 출처 목록 렌더링
          renderEvidencePanel(data.evidence_snippets);
          break;
        case 'graph':
          // 그래프 시각화 컴포넌트 업데이트
          renderGraphView(data);
          break;
        case 'answer_delta':
          // 채팅 버블에 텍스트 append
          answer += data.text;
          updateChatBubble(answer);
          break;
        case 'done':
          // 완료 상태 표시
          markComplete(data.timing_ms);
          break;
        case 'error':
          showError(data.error);
          break;
      }
    }
  }
}
```

---

## 4. 엔티티 자동완성

검색창에서 엔티티 이름을 타이핑할 때 후보를 제안한다. pg_trgm의 similarity 함수를 활용하여 오타에도 대응한다.

```
GET /entities/suggest?q=결제&tenant=default&limit=5
```

```json
{
  "success": true,
  "data": [
    {
      "rid": "ent_a1b2c3d4e5f6",
      "name": "payment-service",
      "type": "Service",
      "aliases": ["결제 서비스", "결제서비스"],
      "description": "결제 처리 마이크로서비스"
    }
  ]
}
```

**UI 구현:**
- 입력 300ms debounce 후 호출
- 최소 1글자부터 제안
- 엔티티 선택 시 → 자동으로 `@payment-service` 형태로 쿼리에 삽입
- 선택된 엔티티는 검색 시 `include_graph: true` + 해당 entity의 그래프 조회로 연결

---

## 5. 문서 브라우저

인덱싱된 문서 목록을 페이지네이션으로 조회한다.

```
GET /documents?tenant=default&offset=0&limit=20
```

```json
{
  "success": true,
  "data": [
    {
      "rid": "doc_f1e2d3c4b5a6",
      "title": "결제 서비스 설계 문서",
      "source_uri": "git://khala-docs/docs/payment-design.md",
      "source_version": "abc123",
      "classification": "INTERNAL",
      "doc_type": "design_doc",
      "language": "ko",
      "chunk_count": 12,
      "updated_at": "2026-03-14T12:00:00"
    }
  ],
  "meta": { "total": 42, "offset": 0, "limit": 20 }
}
```

---

## 6. 그래프 시각화

### 6.1 데이터 조회

```
GET /graph/payment-service?hops=2&include_evidence=true
```

이름 또는 rid로 조회 가능. 응답에는 center entity, designed edges, observed edges가 포함된다.

### 6.2 시각화 데이터 매핑

```
edges[] → 실선 (파란색)
    confidence로 선 굵기 결정 (0.5~1.0 → 1~3px)
    edge_type 라벨 표시

observed_edges[] → 점선 (주황색)
    call_count로 선 굵기 결정
    error_rate > 5%면 빨간색으로 변경
    latency_p95 > 1000ms면 경고 아이콘

diff_flags[] → 노드/엣지에 배지 표시
    doc_only: 📄 (문서에만 존재)
    observed_only: 👁 (관측에만 존재)
    conflict: ⚠️ (불일치)
```

### 6.3 노드 클릭 인터랙션

```
엔티티 노드 클릭 → GET /graph/{clicked_entity_rid}?hops=1
    → 그래프 확장 (현재 그래프에 merge)

엣지 클릭 → evidence[] 사이드패널 표시
    → 근거 문서 snippet 렌더링
    → observed면 trace_query_ref 링크 (→ Grafana Tempo)
```

---

## 7. Diff 대시보드

### 7.1 전체 diff

```
GET /diff?tenant=default
```

### 7.2 특정 엔티티 diff

```
GET /diff?tenant=default&entity_filter=payment-service
```

### 7.3 UI 표시 규칙

| flag | 아이콘 | 색상 | 의미 |
|------|--------|------|------|
| `doc_only` | 📄 | 파란색 | 문서에는 있으나 관측 안 됨 |
| `observed_only` | 👁 | 주황색 | 관측되었으나 문서에 없음 (shadow dependency) |
| `conflict` | ⚠️ | 빨간색 | 문서와 관측이 불일치 |

**designed_evidence**: 클릭 시 해당 문서 chunk로 이동
**observed_evidence**: 클릭 시 Grafana Tempo 링크로 이동 (`trace_query_ref`)

---

## 8. 시스템 상태 모니터링

```
GET /status
```

UI 헤더/사이드바에 연결 상태를 표시한다.

| 필드 | 표시 위치 | 표시 방법 |
|------|-----------|-----------|
| `db_connected` | 상태바 | 초록/빨간 원 |
| `ollama_connected` | 상태바 | 초록/빨간 원 |
| `tempo_connected` | 상태바 | 초록/빨간 원 |
| `documents_count` | 사이드바 | 숫자 뱃지 |
| `diff_summary` | 사이드바 | doc_only/observed_only/conflict 카운트 |

---

## 9. 인증/인가 (2.0 계획)

1.0에서는 인증 없이 동작. 2.0에서 다음을 추가한다:

```
Authorization: Bearer <JWT>

JWT payload:
{
  "sub": "user-123",
  "tenant": "default",
  "clearance": "INTERNAL",   ← classification_max로 자동 매핑
  "roles": ["viewer", "editor"]
}
```

**clearance 매핑:**
- `PUBLIC`: 공개 문서만
- `INTERNAL`: 내부 문서까지 (기본값)
- `RESTRICTED`: 제한 문서까지

UI는 JWT에서 clearance를 읽어 API 호출 시 `classification_max`에 자동 설정한다.
편집자 역할(`editor`)만 `/ingest`, `/upload` 호출 가능.

---

## 10. 파일 업로드 (비개발자용)

```
POST /upload
Content-Type: multipart/form-data

file: (Markdown 파일)
path: "guides"
tenant: "default"
```

**UI 구현:**
- 드래그 앤 드롭 영역
- Markdown 파일만 허용 (`.md` 확장자 검증)
- 업로드 진행 바
- 완료 시: "인덱싱 완료" 또는 "PII 감지로 격리됨" 안내
- 409 응답 시: "같은 이름의 파일이 있습니다. 덮어쓸까요?" 다이얼로그

---

## 11. UI 레이아웃 권장 구조

```
┌──────────────────────────────────────────────────┐
│ [상태 표시등]  Khala  [문서 수: 42]  [Diff: 3 ⚠️] │
├──────────┬───────────────────────────────────────┤
│          │                                       │
│  사이드바  │         메인 영역                      │
│          │                                       │
│ ┌──────┐ │  ┌─────────────────────────────────┐  │
│ │ 채팅  │ │  │  채팅 히스토리                     │  │
│ │      │ │  │  ┌───────────────────────────┐   │  │
│ │ 그래프 │ │  │  │ 사용자: 결제 서비스가        │   │  │
│ │      │ │  │  │       발행하는 토픽?         │   │  │
│ │ 문서  │ │  │  └───────────────────────────┘   │  │
│ │      │ │  │  ┌───────────────────────────┐   │  │
│ │ Diff │ │  │  │ Khala: payment.completed  │   │  │
│ │      │ │  │  │ 토픽을 발행합니다. [1][2]   │   │  │
│ └──────┘ │  │  └───────────────────────────┘   │  │
│          │  └─────────────────────────────────┘  │
│          │                                       │
│          │  ┌───────────┬─────────────────────┐  │
│          │  │ 근거 패널   │ 그래프 시각화          │  │
│          │  │ [1] 설계문서│  (payment)──▶(topic) │  │
│          │  │ [2] API명세│                     │  │
│          │  └───────────┴─────────────────────┘  │
│          │                                       │
│          │  [검색창: @entity 자동완성 지원]         │
├──────────┴───────────────────────────────────────┤
│ 입력: ________________________________________________│
└──────────────────────────────────────────────────┘
```

---

## 12. 엔드포인트 요약

| Method | Path | 용도 | 응답 타입 |
|--------|------|------|-----------|
| POST | `/search` | 하이브리드 검색 | JSON |
| POST | `/search/answer` | 검색 + LLM 답변 | JSON |
| POST | `/search/answer/stream` | 검색 + 스트리밍 답변 | SSE |
| POST | `/ingest` | 문서 인덱싱 | JSON |
| POST | `/upload` | 파일 업로드 + 인덱싱 | JSON |
| GET | `/graph/{entity}` | 엔티티 관계 조회 | JSON |
| GET | `/entities/suggest` | 엔티티 자동완성 | JSON |
| GET | `/documents` | 문서 목록 | JSON (paginated) |
| GET | `/diff` | 설계-관측 diff | JSON |
| POST | `/otel/aggregate` | OTel 집계 실행 | JSON |
| GET | `/status` | 시스템 상태 | JSON |

---

## 13. CORS 설정

개발 환경에서는 모든 origin을 허용한다. 운영 배포 시에는 허용 도메인을 제한해야 한다.

```python
# 현재 (개발)
allow_origins=["*"]

# 운영 배포 시
allow_origins=["https://khala.internal.company.com"]
```

---

## 14. Slack Bot 연동 (2.0 계획)

Slack Bot은 `/search/answer` 엔드포인트를 호출한다 (비스트리밍).

```
사용자 → Slack: @khala 결제 서비스 장애 원인?
Slack Bot → POST /search/answer { "query": "결제 서비스 장애 원인?" }
Slack Bot ← KhalaResponse { "answer": "...", "evidence_snippets": [...] }
Slack Bot → Slack: 답변 + 출처 링크
```

**Slack 메시지 포맷:**
- 답변 본문: Block Kit `section`
- 출처: Block Kit `context` (문서 링크)
- 그래프: attachment로 이미지 (서버사이드 렌더링)

---

## 15. MCP Server 연동 (2.0 계획)

AI Agent가 Khala를 tool로 사용한다. MCP(Model Context Protocol) 서버는 내부적으로 동일한 FastAPI 엔드포인트를 호출한다.

```json
// MCP Tool 정의
{
  "name": "khala_search",
  "description": "조직 내부 문서와 운영 데이터를 검색하여 근거 기반 답변을 제공합니다.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "검색 쿼리" },
      "include_graph": { "type": "boolean", "default": true }
    },
    "required": ["query"]
  }
}
```

**Agent 활용 시나리오:**
1. Code Review Agent → `khala_search("결제 서비스 API 스펙")` → 설계 문서 기반 리뷰
2. Troubleshooting Agent → `khala_search("payment-service 의존성")` → 그래프 + OTel 기반 원인 분석
3. Onboarding Agent → `khala_search("신규 입사자 가이드")` → 문서 기반 온보딩 안내
