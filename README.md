<p align="center">
  <img src="logo.png" alt="Khala" width="180" />
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" />
  <img src="https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white" />
  <img src="https://img.shields.io/badge/Korean_NLP-mecab--ko-FF6F00?style=for-the-badge" />
</p>

<h1 align="center">Khala</h1>

<p align="center">
  <strong>Enterprise RAG + GraphRAG for Grounded Knowledge Retrieval</strong><br/>
  문서 기반 설계와 OTel 기반 관측을 결합하여, 근거 있는 답변만 제공하는 지식 검색 시스템
</p>

---

## What is Khala?

Khala는 조직 내부 지식(문서, 정책, 설정)과 운영 사실(OTel trace, metric)을 결합하여 **근거 기반(grounded)으로 검색하고 추론하는 시스템**입니다.

AI Agent(Code Review, Troubleshooting)의 **context provider**로서, 추측이 아닌 실제 문서와 관측 데이터에 기반한 답변을 제공합니다.

```
"결제 서비스가 발행하는 토픽이 뭐야?"

→ 검색: BM25(한국어 형태소) + Vector(768d) + Graph(2-hop)
→ 근거: API_CONTRACT.md §5.2, 최근 OTel trace 47건
→ 답변: "payment-service는 payment.completed 토픽을 발행합니다. (confidence: 0.85)"
         + 출처 링크 + trace 포인터
```

### Why Khala?

| 기존 RAG | Khala |
|:--------:|:-----:|
| 문서만 검색 | 문서 + 실시간 trace 결합 |
| 추측 기반 답변 | 근거(evidence) 필수 |
| 영어 최적화 | 한국어 형태소 분석 (mecab-ko) |
| Flat retrieval | Graph 관계 + Hybrid search |
| LLM이 판단 | System decides, LLM narrates |

---

## Architecture

```
                              ┌──────────────────────┐
                              │     Client / Agent   │
                              │ API, CLI, Web UI,   │
                              │ Slack Bot, MCP 2.0  │
                              └──────────┬───────────┘
                                         │
                              ┌──────────▼───────────┐
                              │    FastAPI (8000)     │
                              │  ┌────────────────┐   │
                              │  │ Hybrid Search  │   │
                              │  │ BM25+Vec+Graph │   │
                              │  └───┬────┬───┬───┘   │
                              │      │    │   │       │
                    ┌─────────┼──────┘    │   └──┐    │
                    │         │           │      │    │
              ┌─────▼─────┐   │   ┌───────▼──┐   │    │
              │ PostgreSQL │   │   │  Ollama  │   │    │
              │    16      │   │   │ nomic-   │   │    │
              │ ┌────────┐ │   │   │ embed    │   │    │
              │ │pgvector│ │   │   │ (768d)   │   │    │
              │ │tsvector│ │   │   │ (11434)  │   │    │
              │ │pg_trgm │ │   │   └──────────┘   │    │
              │ └────────┘ │   │                  │    │
              │  (5432)    │   │   ┌──────────────▼┐   │
              └────────────┘   │   │ OTel Collector│   │
                               │   │    (4318)     │   │
                ┌──────────┐   │   └──────┬────────┘   │
                │  Claude  │   │          │            │
                │ Sonnet   ◄───┘   ┌──────▼────────┐   │
                │  (LLM)   │       │ Grafana Tempo │   │
                └──────────┘       │  (3200)       │   │
                                   └───────────────┘   │
                                                       │
```

### Data Flow

```
┌─────────┐     ┌──────────┐     ┌───────────┐     ┌──────────┐     ┌───────────┐
│ Git Repo│────▶│ Classify │────▶│ Quarantine│────▶│  Chunk   │────▶│   Index   │
│  (*.md) │     │ + PII    │     │   Gate    │     │  (H1/H2) │     │BM25+Vec+G │
└─────────┘     └──────────┘     └───────────┘     └──────────┘     └───────────┘

┌──────────┐     ┌──────────┐     ┌───────────┐     ┌──────────────────┐
│OTel Trace│────▶│  Tempo   │────▶│ Aggregate │────▶│ CALLS_OBSERVED   │
│ (spans)  │     │ (store)  │     │ (5min win)│     │ + Evidence       │
└──────────┘     └──────────┘     └───────────┘     └──────────────────┘
```

---

## Key Features

### Hybrid Search: BM25 + Vector + Graph

3가지 검색을 병렬 실행하고 RRF(Reciprocal Rank Fusion)로 통합합니다.

```python
# BM25: mecab-ko 형태소 분석으로 한국어 조사/어미를 정확히 처리
"서비스가" → ["서비스"]  # 조사 '가' 제거
"발행한다" → ["발행"]    # 어미 '한다' 제거

# Vector: nomic-embed-text (768d) 다국어 임베딩
# Graph: Entity 관계 2-hop 탐색

# RRF Fusion: score = Σ 1/(k + rank + 1), k=60
```

### Dual Knowledge Layer: Designed + Observed

```
┌─────────────────────────────────────────────────┐
│              Knowledge Graph                     │
│                                                  │
│  [payment-service] ──CALLS──▶ [order-service]   │  ← 설계 문서에서 추출
│         │                          │             │
│    PUBLISHES                  SUBSCRIBES         │
│         │                          │             │
│         ▼                          ▼             │
│  [payment.completed]    [order.created]          │
│                                                  │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─  │
│                                                  │
│  [payment-service] ═CALLS_OBSERVED═▶ [order-svc]│  ← OTel trace에서 관측
│         calls: 1,247                             │
│         error_rate: 2.3%                         │
│         p95: 142ms                               │
└─────────────────────────────────────────────────┘
```

### Design-Observation Diff

문서에만 있고 실제로 관측되지 않는 관계(Dead Doc), 관측되지만 문서화되지 않은 관계(Shadow Dependency)를 자동 탐지합니다.

| Diff Type | 의미 | 예시 |
|-----------|------|------|
| `doc_only` | 문서에는 있지만 관측 안 됨 | 사용 중단된 API |
| `observed_only` | 관측되지만 문서에 없음 | 미문서화 의존성 |
| `conflict` | 둘 다 있지만 불일치 | 프로토콜 변경 |

### Default-Deny Security

```
PII 감지 (주민번호, 카드번호, AWS Key, JWT)
    → 즉시 quarantine
    → 인덱싱 중단
    → 검색 결과에 절대 포함 금지

Classification: PUBLIC < INTERNAL < RESTRICTED
    → 모든 쿼리에 clearance 필터 적용
    → base_filter: tenant + classification + quarantine + status
```

---

## Quick Start

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- (Optional) [Anthropic API Key](https://console.anthropic.com/) — LLM 답변 생성용

### 1. Clone & Configure

```bash
git clone https://github.com/LivingLikeKrillin/khala.git
cd khala

cp .env.example .env
# .env에서 ANTHROPIC_API_KEY 설정 (LLM 답변 기능 사용 시)
```

### 2. Start Infrastructure

```bash
docker compose up -d
```

5개 컨테이너가 시작됩니다:

| Container | Role | Port |
|-----------|------|------|
| khala-db | PostgreSQL 16 + pgvector | 5432 |
| khala-ollama | Embedding model | 11434 |
| khala-tempo | Trace storage | 3200 |
| khala-otel | OTel Collector | 4317/4318 |
| khala-app | FastAPI server | **8000** |

### 3. Pull Embedding Model (first time only)

```bash
docker exec khala-ollama ollama pull nomic-embed-text
```

### 4. Index Documents

```bash
# 컨테이너 내 CLI 사용
docker exec khala-app khala ingest ./docs

# 또는 API 호출
curl -X POST http://localhost:8000/ingest \
  -H "Content-Type: application/json" \
  -d '{"path": "./docs"}'
```

### 5. Search

```bash
# CLI
docker exec khala-app khala query "결제 서비스 의존성"

# API
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{"query": "결제 서비스가 발행하는 토픽"}'
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/search` | Hybrid search (BM25 + Vector + RRF) |
| `POST` | `/search/answer` | Search + LLM grounded answer |
| `POST` | `/search/answer/stream` | SSE 스트리밍 답변 (Web UI 채팅) |
| `POST` | `/ingest` | Index Markdown documents |
| `POST` | `/upload` | Upload & index a single file |
| `GET` | `/graph/{entity}` | Entity relationships (이름 또는 rid로 조회) |
| `GET` | `/entities/suggest` | 엔티티 자동완성 (pg_trgm) |
| `GET` | `/documents` | 인덱싱된 문서 목록 (페이지네이션) |
| `GET` | `/diff` | Design vs. observation mismatch report |
| `POST` | `/otel/aggregate` | Trigger OTel trace aggregation |
| `GET` | `/status` | System health check |

### Example: Search with Graph

```bash
curl -X POST http://localhost:8000/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "payment-service 의존성",
    "route": "hybrid_then_graph",
    "top_k": 5
  }'
```

### Example: Grounded Answer

```bash
curl -X POST http://localhost:8000/search/answer \
  -H "Content-Type: application/json" \
  -d '{
    "query": "결제 서비스가 어떤 서비스를 호출하나요?",
    "clearance": "INTERNAL"
  }'
```

Response includes evidence snippets with source URIs and provenance.

---

## CLI Commands

```bash
khala ingest ./docs              # 문서 인덱싱
khala ingest ./docs --force      # 전체 재인덱싱 (hash 무시)
khala query "검색어"              # 검색
khala graph payment-service      # 그래프 조회
khala graph payment-service -h 2 # 2-hop 그래프
khala otel-aggregate             # OTel 집계
khala diff                       # 설계-관측 diff
khala status                     # 시스템 상태
```

---

## Project Structure

```
khala/
├── khala/
│   ├── models/              # CRM 도메인 모델 (7 models)
│   │   ├── resource.py      #   KhalaResource base class
│   │   ├── document.py      #   Document, Chunk, Entity
│   │   ├── edge.py          #   Edge, ObservedEdge, Evidence
│   │   └── ...
│   │
│   ├── ingest/              # Ingestion pipeline
│   │   ├── collector.py     #   File collection + hash dedup
│   │   ├── scanner.py       #   PII/Secret detection
│   │   ├── classifier.py    #   Classification rules
│   │   ├── chunker.py       #   Hierarchical chunking
│   │   └── pipeline.py      #   Pipeline orchestrator
│   │
│   ├── index/               # Indexing engines
│   │   ├── bm25.py          #   mecab-ko → tsvector
│   │   ├── embed.py         #   Ollama → pgvector
│   │   └── graph_extractor.py  # Entity/relation extraction
│   │
│   ├── search/              # Search engines
│   │   ├── hybrid.py        #   BM25 + Vector + Graph + RRF
│   │   ├── evidence_packet.py  # Evidence assembly
│   │   └── router.py        #   Query route detection
│   │
│   ├── otel/                # OTel integration
│   │   ├── aggregator.py    #   Tempo → CALLS_OBSERVED
│   │   ├── resolver.py      #   Service name resolution
│   │   └── diff_engine.py   #   Design vs. observation diff
│   │
│   ├── llm/                 # LLM integration
│   │   ├── answer.py        #   Grounded answer generation
│   │   └── prompts.py       #   System/user prompts
│   │
│   ├── providers/           # External API wrappers
│   │   ├── embedding.py     #   EmbeddingService (Ollama)
│   │   └── llm.py           #   LLMService (Claude API)
│   │
│   ├── repositories/        # Data access
│   │   └── graph.py         #   GraphRepository Protocol
│   │
│   ├── slack/               # Slack Bot
│   │   ├── app.py           #   Socket Mode 진입점
│   │   ├── bot.py           #   이벤트 핸들러 + API 호출
│   │   └── formatter.py     #   Block Kit 포매터
│   │
│   ├── mcp/                 # MCP Server (AI Agent 도구)
│   │   ├── server.py        #   FastMCP 도구 6개 정의
│   │   └── __main__.py      #   진입점 (stdio/http)
│   │
│   ├── web/                 # Web UI (Vanilla JS, 빌드 불필요)
│   │   ├── index.html       #   SPA 쉘
│   │   ├── css/style.css    #   다크 테마 + 한국어 타이포그래피
│   │   └── js/              #   라우터, API 클라이언트, 뷰 5개
│   │
│   ├── api.py               # FastAPI endpoints (11개)
│   ├── cli.py               # Typer CLI
│   ├── db.py                # PostgreSQL connection pool
│   ├── rid.py               # Canonical ID generation
│   └── utils.py             # get_search_text()
│
├── tests/                   # 151 tests across 14 files
├── docs/                    # Design documents
│   ├── API_CONTRACT.md      #   API 계약서
│   ├── UI_INTEGRATION.md    #   Web UI 연동 규격
│   ├── SLACK_BOT.md         #   Slack Bot 설정 가이드
│   ├── MCP_SERVER.md        #   MCP Server 설정 가이드
│   └── ...
├── config.yaml              # Classification, PII, search params
├── entities.yaml            # Entity gazetteer
├── init.sql                 # DB schema (6 tables + views)
├── docker-compose.yml       # 6-container infrastructure
├── docker-compose.test.yml  # 통합 테스트용 (포트 충돌 방지)
└── Dockerfile               # Python 3.11 + mecab-ko
```

---

## Design Principles

### 1. Grounded Answers Only

모든 답변에는 source chunk 또는 trace 포인터가 근거로 첨부됩니다. 추측은 제공하지 않습니다.

### 2. System Decides, LLM Narrates

접근 통제, 분류, 검색 경로 판정은 모두 **deterministic 코드**가 수행합니다. LLM은 검색된 evidence를 바탕으로 요약/설명만 담당합니다.

### 3. Khala is an Index, Not Storage

원본 문서는 Git에, 원본 trace는 Tempo에 있습니다. Khala DB에는 파생 데이터(chunks, embeddings, graph edges)만 저장됩니다.

### 4. Evidence-Driven Edges

근거(evidence) 없이는 어떤 관계(edge)도 생성되지 않습니다. 모든 edge는 반드시 source chunk 또는 trace query ref에 연결됩니다.

### 5. 2.0-Ready Abstractions

MVP 단계부터 교체 가능한 추상화를 적용하여, 2.0 전환 시 재설계를 방지합니다:

| Abstraction | Purpose |
|-------------|---------|
| `GraphRepository` Protocol | Neo4j 전환 대비 |
| `EmbeddingService` wrapper | 임베딩 모델 교체 대비 |
| `LLMService` wrapper | Multi-LLM 대비 |
| `get_search_text()` | Contextual Enrichment 대비 |
| `canonicalize_entity_name()` | 추출기 교체 시 rid 안정성 |

---

## Testing

```bash
# 전체 테스트 (151 tests — e2e는 DB 연결 시 실행)
docker exec khala-app pytest tests/ -v

# 카테고리별
docker exec khala-app pytest tests/test_bm25_korean.py -v   # 한국어 BM25
docker exec khala-app pytest tests/test_quarantine.py -v    # PII/보안
docker exec khala-app pytest tests/test_hybrid.py -v        # 검색
docker exec khala-app pytest tests/test_graph.py -v         # 그래프
docker exec khala-app pytest tests/test_otel.py -v          # OTel
docker exec khala-app pytest tests/test_api.py -v           # API 모델
docker exec khala-app pytest tests/test_streaming.py -v     # SSE 스트리밍
docker exec khala-app pytest tests/test_slack.py -v         # Slack Bot
docker exec khala-app pytest tests/test_mcp.py -v           # MCP Server

# 통합 테스트 (실제 DB 필요)
docker compose -f docker-compose.test.yml up -d
KHALA_TEST_DB_URL=postgresql://khala:khala@localhost:5433/khala_test \
  pytest tests/test_e2e.py -v
docker compose -f docker-compose.test.yml down
```

---

## Configuration

`config.yaml`에서 주요 파라미터를 조정할 수 있습니다:

```yaml
# 한국어 청킹 파라미터
chunking:
  korean_tokens: 1100
  english_tokens: 700
  overlap_ratio: 0.15

# 검색 튜닝
search:
  bm25_top_k: 20
  vector_top_k: 20
  rrf_k: 60          # RRF fusion 파라미터

# PII 탐지 패턴 추가
pii_patterns:
  korean_ssn: '\b[0-9]{6}-[1-4][0-9]{6}\b'
  aws_key: 'AKIA[0-9A-Z]{16}'
```

`entities.yaml`에서 Entity gazetteer를 관리합니다:

```yaml
entities:
  - name: payment-service
    type: Service
    aliases: ["결제 서비스", "결제서비스", "payment"]
  - name: payment.completed
    type: Topic
    aliases: ["결제 완료 이벤트", "payment completed event"]
```

---

## Web UI

`http://localhost:8000/` 접속 시 Web UI를 사용할 수 있습니다. 빌드 불필요 — FastAPI에서 직접 서빙합니다.

| 뷰 | 기능 |
|----|------|
| 채팅 | SSE 스트리밍 답변 + Evidence 패널 + 인라인 그래프 |
| 그래프 | vis-network 엔티티 관계 시각화 (노드 클릭 확장) |
| 문서 | 페이지네이션 문서 브라우저 |
| Diff | 설계-관측 불일치 대시보드 |
| 업로드 | 드래그앤드롭 Markdown 업로드 |

자세한 연동 규격: [docs/UI_INTEGRATION.md](docs/UI_INTEGRATION.md)

---

## Slack Bot

Slack에서 `@khala`로 멘션하거나 DM으로 질문하면 근거 기반 답변을 받을 수 있습니다.

```bash
pip install -e '.[slack]'
python -m khala.slack.app
```

설정 및 사용법: [docs/SLACK_BOT.md](docs/SLACK_BOT.md)

---

## MCP Server

AI Agent(Claude, Cursor 등)가 MCP 프로토콜로 Khala에 질의할 수 있습니다.

```bash
pip install -e '.[mcp]'
python -m khala.mcp                    # stdio (로컬)
python -m khala.mcp --transport http   # streamable-http (원격)
```

6개 도구 제공: `khala_search`, `khala_answer`, `khala_graph`, `khala_suggest`, `khala_diff`, `khala_status`

설정 및 사용법: [docs/MCP_SERVER.md](docs/MCP_SERVER.md)

---

## Roadmap

테마 기반 페이즈로 진화한다. 전체 로드맵은 [에코시스템 ROADMAP.md](./ROADMAP.md) 참조.

```
Phase 1 — 팀 맞춤형
  ├ tenant별 검색 프로파일 (BM25/Vector/Graph 가중치 조정)
  ├ tenant별 문서 풀 격리 (팀 전용 + 공유)
  └ 역할별 결과 reranking

Phase 2 — 검색 지능화
  ├ Adaptive 검색 깊이 (simple/standard/deep)
  ├ router.py 확장 (쿼리 복잡도 자동 판정)
  └ Cross-Encoder Reranking

Phase 3 — 거버넌스
  ├ JWT 인증/인가
  ├ 감사 추적
  └ tenant 관리 UI
```

---

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Language | Python 3.11+ | ML/NLP ecosystem |
| API | FastAPI | Async-first, OpenAPI |
| CLI | Typer | Developer productivity |
| Database | PostgreSQL 16 | pgvector + BM25 + Graph 통합 |
| Korean NLP | mecab-ko + mecab-ko-dic | 조사/어미 정확 분리 |
| Embedding | nomic-embed-text (Ollama) | 768d, multilingual, local |
| LLM | Claude Sonnet (Anthropic) | Grounded answer generation |
| Tracing | OTel Collector + Tempo | Trace 수집 + 쿼리 |
| Container | Docker Compose | One-command infra |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://khala:khala@localhost:5432/khala` | PostgreSQL 연결 |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API |
| `ANTHROPIC_API_KEY` | — | Claude API key (LLM 답변용) |
| `TEMPO_URL` | `http://localhost:3200` | Grafana Tempo |
| `OTEL_COLLECTOR_URL` | `http://localhost:4318` | OTel Collector |
| `DEFAULT_TENANT` | `default` | 기본 테넌트 |
| `SLACK_BOT_TOKEN` | — | Slack Bot OAuth Token (Slack Bot용) |
| `SLACK_APP_TOKEN` | — | Slack App-Level Token (Socket Mode) |
| `KHALA_API_URL` | `http://localhost:8000` | Slack Bot → Khala API 주소 |

---

## License

MIT

---

<p align="center">
  <sub>Built with Claude Code</sub>
</p>
