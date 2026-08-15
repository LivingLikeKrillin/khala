# Nexus — UI 연동 규격

> Web UI / Slack Bot / MCP 클라이언트가 Nexus API를 사용할 때의 연동 규격.
> **모든 인터페이스는 동일한 FastAPI 백엔드를 HTTP로 공유한다** — 이게 이 문서가 지키려는 유일한 불변식이다. 어느 클라이언트도 DB에 직접 붙지 않고, 그래서 셋이 서로 다른 진실을 볼 수 없다.

---

## 1. 전체 구조

웹 UI는 **vanilla ESM이고 빌드 스텝이 없다.** React도 Next.js도 쓰지 않는다 — `nexus/web/index.html`이 `/static/js/app.js`를 모듈로 불러오고, 서드파티는 `vendor/`에 받아둔 것(marked · DOMPurify · vis-network)을 그대로 쓴다. 빌드 산출물이 없으므로 **고친 파일이 곧 배포되는 파일**이다.

```
┌──────────────────────────────────────────────────────────┐
│  Web UI — vanilla ESM (nexus/web/js), no build step       │
│  ┌──────────┐ ┌──────────┐ ┌──────────────┐              │
│  │ 검색 채팅  │ │ 그래프 뷰  │ │ 문서 브라우저  │              │
│  └────┬─────┘ └────┬─────┘ └──────┬───────┘              │
│       │            │              │                       │
│  표시 계층 모듈: citations · freshness · doctype-signal    │
│                 llm-failure · corpus-hint · history        │
└───────┼────────────┼──────────────┼──────────────────────┘
        │            │              │
   SSE Stream    REST GET       REST GET
        │            │              │
┌───────┴────────────┴──────────────┴──────────┐
│  Nexus FastAPI Backend                       │
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

표시 계층 모듈이 따로 있는 이유는, **백엔드가 이미 판정한 것을 UI가 다시 판정하지 않기 위해서**다. 인용 검증 결과·최신성·문서 타입·생성 실패 사유는 전부 응답에 실려 오고, 이 모듈들은 그것을 배지와 문구로 옮기기만 한다. UI가 스스로 계산하기 시작하면 같은 질문에 대해 화면과 API가 다른 답을 하게 된다.

---

## 2. 응답 규약

### 2.1 공통 응답 포맷

모든 REST 엔드포인트는 `NexusResponse`로 감싼다.

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
      "source_uri": "git://nexus-docs/docs/payment-design.md",
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

## 9. 인증/인가

> 이 절은 예전에 "2.0 계획"으로 JWT + roles 설계를 적어두었다. 실제로 만들어진 것은 다른 물건이고, **UI가 지켜야 할 규칙이 정반대**라 그대로 두면 위험하다.

**불투명 bearer 토큰**을 쓴다. JWT가 아니다. 토큰 안에 읽을 것이 없다.

```
Authorization: Bearer <opaque-token>
```

서버는 `sha256(token)`을 설정의 `auth.principals[].token_sha256`과 **상수 시간**으로 대조해 principal을 찾는다. 토큰이 없거나 모르는 값이면 principal이 없다.

**하나의 토큰 = 하나의 (tenant, clearance).**

```python
Principal(name=..., tenant=..., clearance=..., capabilities=())
```

- **clearance는 토큰에 묶여 있고 요청이 고를 수 없다.** 옛 문서는 "UI가 JWT에서 clearance를 읽어 `classification_max`에 자동 설정한다"고 적었는데, 그건 **클라이언트가 자기 권한을 정하는 모양**이다. 지금 설계는 반대다 — 서버가 토큰으로 정하고, 요청은 그보다 넓게 볼 수 없다.
- **설정이 잘못돼도 넘치지 않는다.** principal의 clearance는 `floor_public()`을 거치므로, 오설정이 실수로 `PUBLIC` 이상을 주는 일이 없다.
- **기본은 읽기 전용이다.** `capabilities`는 비어 있는 것이 기본이고(default-deny), 쓰기는 여기 명시된 능력이 있어야 한다. `roles`도 `editor` 역할도 없다 — 그 어휘는 만들어지지 않았다.

**UI가 할 일**: 토큰을 `Authorization` 헤더에 실어 보낸다. 그게 전부다. clearance를 계산하거나 `classification_max`를 채워 넣으려 하지 말 것.

로컬 dev 온램프로 `GET /auth/dev-token`이 있다. `NEXUS_DEV_TOKEN`이 설정된 경우에만 값을 돌려주고, 미설정이면 `token=null`이다.

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
│ [상태 표시등]  Nexus  [문서 수: 42]  [Diff: 3 ⚠️] │
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
│ │ Diff │ │  │  │ Nexus: payment.completed  │   │  │
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

> **UI가 쓰는 것만 적는다. 전체 목록이 아니다** — 앱이 서빙하는 경로는 이보다 훨씬 많고, 살아 있는 전체 명세는 `/docs`(Swagger)와 `/openapi.json`이다. 손으로 옮겨 적은 목록은 반드시 뒤처지고, 뒤처졌다는 사실조차 조용하다. 소스 콘솔·문서 생애주기·피드백 계열은 [API_CONTRACT.md](API_CONTRACT.md)의 표를 참고할 것.

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

**`"*"`가 아니다.** §9대로 `Authorization` 헤더를 쓰는 순간 와일드카드 origin은 성립하지 않는다(`allow_credentials=True`와 함께 쓸 수 없고, 써서도 안 된다). origin은 **설정에서 온다**:

```python
allow_origins=_cors_origins()   # auth.allowed_origins + (A2A 활성 시) 외부 A2A 호출자 origin
allow_credentials=True
```

허용 목록은 `auth.allowed_origins`이고, A2A 표면이 켜져 있으면 외부 A2A 호출자의 origin이 합집합으로 더해진다. 즉 **배포마다 다르며 코드에 박혀 있지 않다** — 새 프런트엔드를 다른 호스트에 올렸는데 요청이 막힌다면 먼저 여기를 본다.

---

## 14. Slack Bot 연동

**출하됨.** 정본은 [SLACK_BOT.md](SLACK_BOT.md)이고, 여기서는 이 문서의 관심사인 *"같은 API를 공유한다"*만 확인한다.

봇은 다른 클라이언트와 마찬가지로 **HTTP로** Nexus에 붙는다 — DB에 직접 붙지 않는다. 자기 bearer 토큰을 쓰므로 §9의 규칙이 그대로 적용되고, 봇의 clearance가 곧 **워크스페이스 전원에게 확장하는 신뢰의 바닥**이 된다.

옛 서술 중 만들어지지 않은 것: 그래프를 서버사이드 렌더링한 **이미지 attachment로 보내지 않는다.** 텍스트 라인으로 낸다.

---

## 15. MCP Server 연동

**출하됨.** 도구 목록과 스키마의 정본은 [MCP_SERVER.md](MCP_SERVER.md)와 `nexus/mcp/server.py`다. 여기 베껴 적으면 또 뒤처진다 — 옛 서술은 도구가 `nexus_search` 하나인 것처럼 적혀 있었고, 지금은 검색·답변·그래프·문서 생애주기·소스 콘솔·Archon 클레임까지 **20개 가까이** 있다.

이 문서의 관심사만 확인한다: **MCP 서버는 내부적으로 같은 FastAPI 엔드포인트를 HTTP로 호출한다.** 즉 웹 UI·Slack 봇·MCP가 서로 다른 진실을 볼 수 없고, §9의 인증 규칙도 셋 다 동일하게 적용된다.
