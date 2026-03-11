# Khala Mini MVP 설계 문서

> **10일 시범 구축 — Hybrid Search + Graph + OTel Diff**
> 맥락 기반 AI Agent (Code Review / Troubleshooting)의 초석

| 항목 | 값 |
|------|-----|
| 대상 | 팀 문서 100–500개 (한국어 주력) + OTel trace |
| 기간 | 10일 (Claude Code 활용) |
| 인프라 | PostgreSQL + OTel Collector + Tempo (Docker Compose) |
| 원본 저장소 | Git 단일 repo (Source of Truth) |
| 데이터 모델 | Canonical Resource Model (CRM) |
| 최종 목표 | Code Review / Troubleshooting Agent의 context provider |

---

## 목차

1. [목적과 비전](#1-목적과-비전)
2. [아키텍처](#2-아키텍처)
3. [Canonical Resource Model (CRM)](#3-canonical-resource-model-crm)
4. [DB 스키마](#4-db-스키마)
5. [핵심 파이프라인](#5-핵심-파이프라인)
6. [2.0 전환 대비: 추상화 전략](#6-20-전환-대비-추상화-전략)
7. [일별 구현 계획 (10일)](#7-일별-구현-계획-10일)
8. [기술 스택](#8-기술-스택)
9. [테스트 시나리오 (18건)](#9-테스트-시나리오-18건)
10. [MVP → 2.0 로드맵](#10-mvp--20-로드맵)

---

## 1. 목적과 비전

Khala는 조직 내부 지식(문서/정책/설정)과 운영 사실(OTel trace/metric)을 결합하여,
근거 기반으로 검색하고 관계를 추론하는 시스템이다.

### 1.1 최종 목표: AI Agent의 Context Provider

Khala는 단독 검색 도구가 아니라, 다음 AI Agent들의 초석이다:

| 목표 Agent | 필요한 컨텍스트 | Khala가 제공하는 것 |
|-----------|---------------|-------------------|
| 맥락 기반 Code Review | PR이 변경하는 서비스 간 호출이 실제 프로덕션과 일치하는가? | 설계 edge (CALLS) + 관측 edge (CALLS_OBSERVED) + diff flag |
| 맥락 기반 Troubleshooting | 장애 경로가 문서 경로와 다른가? 어디서 갈라졌나? | CALLS_OBSERVED 경로 + 문서 경로 + semantic mismatch |
| 문서 검색 (Q&A) | 이 개념/정책/구조가 문서에서 어떻게 정의되어 있는가? | Hybrid Search + 근거 chunk + 출처 |

### 1.2 1.0과 2.0의 관계

```
Khala 1.0 (MVP)                         Khala 2.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
주체:  AI Agent                          주체:  사람 + Agent

인터페이스:                               인터페이스:
  ├ FastAPI (Agent가 호출)                  ├ Web UI (검색 + 채팅)
  ├ CLI (개발자 검증용)                      ├ Slack Bot
  └ (MCP는 확장에서)                        ├ MCP Server
                                           └ FastAPI (기존 유지)
```

Agent가 MCP로 질의해서 맥락을 확보하는 것과 사람이 자연어로 질의해서 정보를 얻는 것은
**같은 기능이다. 주체만 다르다.** 1.0에서 코어를 완성하고, 2.0에서 사람용 인터페이스를 붙인다.

### 1.3 설계-관측 diff가 핵심인 이유

- **Code Review Agent**: PR이 바꾸는 호출이 CALLS_OBSERVED에 존재하는지 검증.
- **Troubleshooting Agent**: 장애 시 CALLS_OBSERVED 경로를 추적하고, 문서와 비교하여 drift 발견.
- OTel 없이는 "설계도만 보고 진단하는 의사". 실제 환자(프로덕션)를 봐야 한다.

---

## 2. 아키텍처

### 2.1 전체 구성도

| 컴포넌트 | 기술 | 역할 |
|---------|------|------|
| PostgreSQL 16 | pgvector + tsvector + pg_trgm | Vector + BM25 + metadata + graph + evidence 모두 |
| mecab-ko | Docker 내 설치 (app container) | 한국어 형태소 분석 |
| Ollama | Docker container | multilingual-e5 embedding 로컬 실행 |
| OTel Collector | Docker container | OTLP trace 수신 |
| Tempo | Docker container | Trace 저장 + 쿼리 backend |
| FastAPI | 앱 container | Indexer, Search, OTel Aggregator, API |
| Claude Sonnet | External API | 근거 기반 답변 생성 |

### 2.2 경계 설계

Khala의 유일한 인터페이스는 FastAPI이다. 모든 클라이언트는 API를 통해 접근한다:

| 클라이언트 | 접근 방식 | 시점 |
|-----------|----------|------|
| CLI | `khala query/ingest/diff` 명령어 (FastAPI 호출) | MVP |
| Code Review Agent | `POST /search` + `GET /diff` | 확장 1 |
| Troubleshooting Agent | `POST /search` + `GET /graph/{rid}` + `GET /diff` | 확장 2 |
| Slack Bot | `POST /search` wrapper | 2.0 |
| MCP Server | MCP protocol → FastAPI | 2.0 |
| Web UI | SvelteKit / Streamlit (FastAPI 호출) | 2.0 |

### 2.3 원본 저장소

Khala는 인덱스(index)이지 저장소(storage)가 아니다. Source of Truth는 외부에 있다.

| 구분 | 역할 | 위치 |
|------|------|------|
| 원본 (Source of Truth) | Markdown 문서 버전 관리 | Git repo (로컬 checkout) |
| 관측 (Source of Truth) | Trace/span 원본 | Tempo |
| Khala DB (인덱스) | 파생: chunk, embedding, graph, evidence, OTel 집계 | PostgreSQL |

**Khala DB에 원문 전체를 저장하지 않는다:**

- `documents` 테이블: metadata + `source_uri` + `source_version`만.
- `chunk_text`: 검색 단위 부분만 저장.
- 원문 전체 필요 시 `source_uri`로 Git/Tempo에서 직접 조회.
- 비개발자 문서 입력: MVP에서는 웹 업로드 API, 2.0에서 Git-backed wiki 검토.

---

## 3. Canonical Resource Model (CRM)

Khala의 모든 데이터는 Resource라는 공용 모델을 따른다.
문서/청크/그래프/OTel 집계/도메인 스토리 모두 동일한 규칙으로 식별/권한/근거/수명주기를 다룬다.

### 3.1 Resource 공통 필드

| Field | Type | 설명 |
|-------|------|------|
| rid | TEXT PK | 전역 유일 canonical resource id |
| rtype | TEXT | document \| chunk \| entity \| edge \| observed_edge \| evidence |
| tenant | TEXT | 조직 경계 |
| classification | TEXT | PUBLIC \| INTERNAL \| RESTRICTED |
| owner | TEXT | 소유자 (팀/개인) |
| source_uri | TEXT | 원본 위치 (git://repo/path, otlp://tempo 등) |
| source_version | TEXT | 원본 버전 (commit SHA, time range 등) |
| source_kind | TEXT | git \| wiki \| file \| otel \| manual |
| hash | TEXT | 내용/구조 해시 (증분 인덱싱용) |
| labels | TEXT[] | 검색/필터용 태그 |
| is_quarantined | BOOLEAN | PII/secret/미분류 격리 |
| quality_flags | TEXT[] | doc_only \| observed_only \| conflict \| stale_doc |
| created_at | TIMESTAMPTZ | 생성 시각 |
| updated_at | TIMESTAMPTZ | 수정 시각 |
| status | TEXT | active \| superseded \| soft_deleted |

### 3.2 Canonical ID (rid) 규칙

| rtype | rid 공식 | 예시 |
|-------|---------|------|
| document | hash("doc:" + canonical_uri) | doc_a1b2c3d4 |
| chunk | hash("chunk:" + doc_rid + ":" + section_path + ":" + idx) | chk_e5f6g7h8 |
| entity | hash("ent:" + tenant + ":" + type + ":" + canonical_name) | ent_i9j0k1l2 |
| edge | hash("edge:" + tenant + ":" + type + ":" + from_rid + ":" + to_rid) | edg_m3n4o5p6 |
| observed_edge | hash("obs_edge:" + tenant + ":" + type + ":" + from_rid + ":" + to_rid) | obs_q7r8s9t0 |
| evidence | hash("evi:" + subject_rid + ":" + evidence_rid) | evi_u1v2w3x4 |

**rid 설계 원칙:**

- 내용이 바뀌어도 동일 객체로 취급되는 단위에서 안정적.
- `document rid`: canonical_uri 기반. 내용 업데이트되어도 rid 유지.
- `chunk rid`: chunking 규칙 변경 시 rid도 변경됨. 단, doc_rid는 유지되므로 재생성/정리 가능.
- `edge rid`: deterministic composite key로 idempotent upsert 보장.
- `observed_edge rid`: window는 속성으로, 같은 rid에 시계열 업데이트. edge 폭발 방지.

### 3.3 Provenance (출처 추적)

Source(원본 위치)와 Provenance(어떻게 만들어졌나)를 2단으로 분리한다:

| Field | Type | 설명 |
|-------|------|------|
| prov_pipeline | TEXT | 생성 파이프라인 (indexer-v1, otel-agg-v1) |
| prov_generated_at | TIMESTAMPTZ | 생성 시각 |
| prov_inputs | TEXT[] | 입력 rid 목록 (edge를 만든 chunk rid 등) |
| prov_transform | TEXT | 변환 방법 (chunking:h2+token, regex:pii_v2) |

### 3.4 Evidence Model

| Field | Type | 설명 |
|-------|------|------|
| rid | TEXT PK | evidence 자체의 rid |
| subject_rid | TEXT | 근거가 필요한 대상 (edge/entity/observed_edge) |
| evidence_rid | TEXT | 근거 리소스 (chunk/otel_query 등) |
| kind | TEXT | text_snippet \| policy_line \| trace_ref \| metric_ref |
| weight | FLOAT | 0–1 신뢰도 가중치 |
| note | TEXT? | 근거 이유 짧은 설명 |

Evidence는 `rid → rid`로 범용적:

- `edge → chunk`: 문서에서 추출된 관계의 근거
- `observed_edge → otel_query`: 관측의 근거 (trace query ref + sample IDs)
- `entity → chunk`: entity가 언급된 문서
- 어떤 Resource든 다른 Resource의 근거가 될 수 있다.

---

## 4. DB 스키마

CRM 공통 필드 + rtype별 고유 필드로 구성된다.

### 4.1 documents

CRM 공통 + `title`, `doc_type`, `language`, `content_hash`

### 4.2 chunks

CRM 공통 + `chunk_text`, `section_path`, `context_prefix`, `search_text` (GENERATED), `embedding` (vector(768)), `tsvector_ko`, `metadata` (JSONB), `embed_model`

```sql
-- search_text: 검색/임베딩에 사용되는 가공된 텍스트
-- chunk_text와 분리하여 2.0 Contextual Enrichment 대비
search_text TEXT GENERATED ALWAYS AS (
    COALESCE(context_prefix, '') || ' ' || chunk_text
) STORED
```

### 4.3 entities

CRM 공통 + `type` (Service|API|Topic|DB|Term), `name`, `aliases[]`, `description`

### 4.4 edges

CRM 공통 + `edge_type` (CALLS|PUBLISHES|SUBSCRIBES), `from_rid`, `to_rid`, `confidence`, `source_category` (DESIGNED|MANUAL)

### 4.5 observed_edges

CRM 공통 + `edge_type` (CALLS_OBSERVED), `from_rid`, `to_rid`, `call_count`, `error_rate`, `latency_p50/p95/p99`, `sample_trace_ids[]`, `trace_query_ref`, `resolved_via`, `window_start`, `window_end`, `last_seen_at`

### 4.6 evidence

3.4절 Evidence Model 그대로.

### PostgreSQL 하나로 모두

- **pgvector**: chunk embedding + cosine similarity
- **tsvector (mecab-ko)**: 한국어 BM25
- **pg_trgm**: 3-gram fallback
- **일반 테이블**: metadata, entity, edge, observed_edge, evidence
- 100–500 문서 규모에서 entity 수백, edge 수천 → adjacency table + recursive CTE로 2-hop 충분.

---

## 5. 핵심 파이프라인

### 5.1 Ingestion + Indexing

```
Git repo에서 Markdown 수집 (content_hash 비교로 변경분만)
    ↓
PII/Secret 스캔 → 감지 시 is_quarantined=true
    ↓
경로 규칙으로 classification 자동 부여
    ↓
한국어 비율 측정 → language 필드
    ↓
doc_type별 Hierarchical Chunking
  ├ 1차: H1/H2 경계로 섹션 분리 (구조 보존)
  └ 2차: 1000-1200 tokens 초과 시 recursive 분할 (한국어)
         600-800 tokens (영어), 오버랩 10-20%
    ↓
get_search_text(chunk) → search_text 생성
  └ 1.0: "[section_path] chunk_text"
  └ 2.0: Contextual Enrichment로 교체 가능
    ↓
search_text → mecab-ko → tsvector + GIN index (BM25)
search_text → EmbeddingService → pgvector index (Vector)
    ↓
Entity/relation 추출 → graph table + evidence link
    ↓
모든 객체에 CRM 공통 필드 + provenance 기록
```

### 5.2 Hybrid Search + RRF

최신 연구(arXiv:2507.03226, arXiv:2507.03608)에 기반한 3-way 병렬 검색:

```
Query
  ↓
┌──────────────┬──────────────┬──────────────────┐
│ BM25         │ Vector       │ Graph            │
│ mecab-ko     │ cosine sim   │ entity 추출 →    │
│ → tsquery    │ → top-20     │ 1-2 hop 확장     │
│ → top-20     │ (~120ms)     │ (~50ms)          │
│ (~8ms)       │              │                  │
└──────┬───────┴──────┬───────┴────────┬─────────┘
       │              │               │
       └──────┬───────┘               │
              ↓                       │
       RRF Fusion (k=60)             │
              ↓                       │
       top-50 후보 ←─────────────────┘
              ↓
       [2.0: Cross-Encoder Reranking]
              ↓
       top-10 최종
              ↓
       Evidence Packet → LLM
```

**Pre-filter**: `classification <= user.clearance AND is_quarantined = false`

**RRF Fusion**: `score = Σ 1/(k + rank)`, k=60 (업계 표준, 논문 검증)

**성능 벤치마크 (연구 기반):**

| 지표 | Vector만 | + BM25 Hybrid | + Graph | + Reranking (2.0) |
|------|----------|---------------|---------|-------------------|
| 적중률 (top-10) | baseline | +15~20% | +8~15% | +10~15% |
| Faithfulness | 0.82 | 0.88 | 0.96 | 0.96 |
| 멀티홉 정확도 | 23% | 35% | 87% | 87% |
| 레이턴시 | 120ms | 130ms | 180ms | 280ms |

### 5.3 Graph 조회

```
Hybrid 결과에서 entity rid 추출 (gazetteer 매칭)
    ↓
GraphRepository.get_neighbors(rid, hops=1)
  └ edges + observed_edges 테이블에서 1-2 hop 확장
    ↓
각 hop의 evidence chunk 추가 검색
    ↓
graph_findings를 Evidence Packet에 추가
```

### 5.4 OTel 집계 + Observed Graph

```
OTel Collector가 OTLP trace 수신 → Tempo에 저장
    ↓
Aggregator (5분 batch): Tempo 쿼리 → CALLS_OBSERVED edge 생성
    ↓
Service name resolution: peer.service → k8s metadata → reverse DNS → hash fallback
    ↓
GraphRepository.upsert_edges(observed_edges)
  └ CRM 공통 필드 + 관측 메트릭 저장
    ↓
evidence: trace_query_ref + sample_trace_ids (원문은 Tempo에)
```

**Raw trace는 Khala DB에 절대 저장하지 않음.**

### 5.5 설계-관측 Diff

| Diff 유형 | quality_flag | 조건 | 의미 |
|-----------|-------------|------|------|
| Dead Doc | doc_only | CALLS 존재, CALLS_OBSERVED 없음 | 문서에만 있고 실제 호출 없음 |
| Shadow Dependency | observed_only | CALLS_OBSERVED 존재, CALLS 없음 | 미문서화 의존성 |
| Semantic Mismatch | conflict | 양쪽 존재, protocol/style 불일치 | 아키텍처 drift |

`quality_flags`는 CRM 공통 필드이므로, diff 결과가 자동으로 edge/observed_edge에 태그된다.
별도 diff 엔진 없이 SQL 쿼리로 보고서 생성 가능.

---

## 6. 2.0 전환 대비: 추상화 전략

MVP 10일 안에서 과잉 설계를 피하되, 2.0 전환 시 재설계를 방지하기 위한 최소한의 추상화.

### 6.1 원칙

```
Protocol이 필요한 경우:  구현이 여러 파일에 흩어지는 것
래퍼 클래스면 충분한 경우: 외부 API 호출을 한 곳에 모으는 것
함수면 충분한 경우:     변환 로직을 한 줄로 격리하는 것
파일 분리면 충분한 경우: 이미 단일 파일에 모여 있는 것
```

### 6.2 반드시 해야 하는 것 (반나절)

#### Protocol 1개: GraphRepository

Graph 쿼리는 search.py, diff_engine.py, api.py, otel_aggregator.py 4곳에서 사용된다.
PostgreSQL → Neo4j 전환 시 4곳을 모두 수정해야 하므로 Protocol 필수.

```python
# khala/repositories/graph.py
from typing import Protocol

class GraphRepository(Protocol):
    async def get_neighbors(self, rid: str, hops: int = 1) -> list[Edge]:
        """entity의 이웃 edge 조회 (designed + observed)"""
        ...

    async def get_subgraph(self, center_rid: str, radius: int) -> SubGraph:
        """entity 중심 서브그래프 조회"""
        ...

    async def upsert_edges(self, edges: list[Edge]) -> None:
        """edge 일괄 upsert (idempotent)"""
        ...

    async def find_path(self, from_rid: str, to_rid: str) -> list[Edge]:
        """두 entity 간 경로 탐색"""
        ...

    async def get_diff(self, tenant: str) -> list[DiffItem]:
        """설계 edge vs 관측 edge 비교"""
        ...

# 1.0 구현
class PostgresGraphRepository:
    """PostgreSQL adjacency table + recursive CTE"""
    ...

# 2.0 구현 (교체만 하면 됨)
# class Neo4jGraphRepository:
#     """Neo4j Cypher + Leiden community detection"""
#     ...
```

#### 함수 1개: get_search_text()

임베딩과 tsvector 생성 시 `chunk_text`를 직접 쓰지 않고 이 함수를 경유.
2.0 Contextual Enrichment 시 이 함수만 수정하면 전체 재인덱싱 로직은 그대로.

```python
# khala/utils.py
def get_search_text(chunk) -> str:
    """청크의 검색/임베딩용 텍스트 생성.
    1.0: section_path 접두사
    2.0: LLM Contextual Enrichment로 교체 가능
    """
    prefix = chunk.context_prefix or f"[{chunk.section_path}]"
    return f"{prefix} {chunk.chunk_text}"
```

사용:
```python
# 임베딩 생성 시
text = get_search_text(chunk)              # ← 이 함수 경유
embedding = await embedding_service.embed([text])

# tsvector 생성 시
tsvector = mecab_to_tsvector(get_search_text(chunk))  # ← 이 함수 경유
```

#### 래퍼 클래스 2개: EmbeddingService, LLMService

외부 API 직접 호출을 한 곳에 모아서, 2.0에서 프로바이더 교체 시 이 클래스만 수정.

```python
# khala/providers/embedding.py
class EmbeddingService:
    """임베딩 생성. Ollama 직접 호출을 격리."""

    def __init__(self, model: str = "multilingual-e5-base"):
        self.model = model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """텍스트 → 벡터. 2.0에서 Jina/Late Chunking으로 교체 가능."""
        # Ollama API 호출
        ...

    def get_model_name(self) -> str:
        return self.model

    def get_dimensions(self) -> int:
        return 768
```

```python
# khala/providers/llm.py
class LLMService:
    """LLM 답변 생성. Claude API 직접 호출을 격리."""

    async def generate(self, messages: list, evidence: EvidencePacket) -> str:
        """근거 기반 답변 생성. 2.0에서 Multi-LLM으로 교체 가능."""
        # Claude API 호출
        ...

    async def stream(self, messages: list, evidence: EvidencePacket):
        """스트리밍 답변. 2.0 채팅 UI에서 SSE로 활용."""
        # Claude API 스트리밍
        ...
```

### 6.3 나머지: 파일 분리만 잘하면 됨

아래 모듈들은 이미 MVP 설계에서 단일 파일에 모여 있으므로, 2.0에서 해당 파일만 리팩토링하면 된다.

| 모듈 | MVP 파일 | 2.0 변경 시 | Protocol 불필요 이유 |
|------|---------|------------|---------------------|
| Chunking | `chunker.py` | Semantic/Late Chunking 도입 | 1개 파일에만 존재 |
| Entity 추출 | `extract_relations.py` | dep.parsing/LLM 추출 전환 | 1개 파일에만 존재 |
| 문서 수집 | `ingest.py` | Slack/Jira source 추가 | source_kind 분기 추가 |
| 검색 흐름 | `search.py` | Rerank 단계 삽입 | 1개 파일에만 존재 |

### 6.4 Entity Name 정규화 함수 분리 (필수)

추출기(regex/dep.parsing/LLM)가 바뀌어도 동일 entity가 동일 rid를 받도록,
name 정규화를 추출기와 독립적으로 분리한다.

```python
# khala/rid.py
def canonicalize_entity_name(raw_name: str, entity_type: str) -> str:
    """entity name → canonical form. 추출기가 바뀌어도 rid 안정성 보장."""
    name = raw_name.strip().lower()
    name = name.replace("_", "-")
    # 한국어 변형 통일 (결제서비스, 결제 서비스, payment-service → payment-service)
    # aliases 매핑은 entities.yaml에서 관리
    return name
```

### 6.5 전체 추상화 요약

```
비용       항목                    형태              효과
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
반나절     GraphRepository        Protocol          Neo4j 전환 시 재설계 방지
10분      get_search_text()      함수 1개          Contextual Enrichment 대비
30분      EmbeddingService       래퍼 클래스        임베딩 모델 교체 대비
30분      LLMService             래퍼 클래스        Multi-LLM 대비
10분      canonicalize_entity_name 함수 1개        추출기 교체 시 rid 안정성
0분       파일 분리 유지          설계 습관          나머지 모든 전환 대비
```

---

## 7. 일별 구현 계획 (10일)

Claude Code 적극 활용 전제. 3개 구간으로 구분된다.

### === 구간 1: 검색 기반 (Day 1–4) ===

#### Day 1: 스켈레톤 + 인프라

| 작업 | Deliverable |
|------|------------|
| 프로젝트 초기화 (Python + FastAPI + Typer CLI) | pyproject.toml + 기본 구조 |
| docker-compose: PostgreSQL(pgvector) + Ollama + OTel Collector + Tempo | docker-compose.yml |
| CRM base class (Python dataclass) | khala/models/resource.py |
| DB 스키마 DDL (6개 테이블 + index) | init.sql |
| rid 생성 함수 + `canonicalize_entity_name()` | khala/rid.py |
| `GraphRepository` Protocol + PostgreSQL 구현체 | khala/repositories/graph.py |
| `EmbeddingService` 래퍼 + `LLMService` 래퍼 | khala/providers/ |
| `get_search_text()` 함수 | khala/utils.py |
| mecab-ko 검증 (한국어 형태소 분석 테스트) | test 통과 |
| config.yaml (경로 규칙, PII 패턴, doc_type) | config.yaml |

> **Day 1 완료**: docker-compose up으로 전체 기동. 6개 테이블 확인. 추상화 레이어 완비.

#### Day 2: Ingestion + Chunking

| 작업 | Deliverable |
|------|------------|
| Markdown 파일 수집기 (glob + content_hash 변경 감지) | ingest.py |
| PII/Secret 스캐너 (AWS key, JWT, 신용카드 regex) | scanner.py |
| Classification (경로 규칙 + 파일타입) | classifier.py |
| Hierarchical Chunker (H1/H2 + 토큰 분할 + 한국어 보정) | chunker.py |
| Provenance 기록 (pipeline, inputs, transform) | ingest.py 내 |

> **Day 2 완료**: `python ingest.py ./docs` → documents + chunks 테이블에 데이터. PII 문서 quarantine.

#### Day 3: BM25 + Vector 인덱싱

| 작업 | Deliverable |
|------|------------|
| tsvector 생성 (`get_search_text()` → mecab-ko → tsvector → GIN) | indexer_bm25.py |
| Embedding 생성 (`get_search_text()` → `EmbeddingService` → pgvector) | indexer_embed.py |
| BM25 단독 검색 테스트 (한국어 조사/어미) | test 통과 |
| Vector 단독 검색 테스트 | test 통과 |

#### Day 4: Hybrid Search + LLM 답변

| 작업 | Deliverable |
|------|------------|
| RRF Fusion (BM25 top-20 + Vector top-20, k=60) | search.py |
| Pre-filter (classification + quarantine) | search.py 내 |
| Evidence Packet 조립 | evidence.py |
| `LLMService` 연동 + 근거 기반 답변 | answer.py |
| CLI: `khala query '질문'` → 답변 + 출처 | cli.py |

> **Day 4 완료 (★ 첫 번째 마일스톤)**:
> `khala query '결제 서비스가 발행하는 토픽?'` → Hybrid 검색 → LLM 답변 + 출처.

### === 구간 2: Graph + OTel (Day 5–8) ===

#### Day 5: Entity/Graph 기반

| 작업 | Deliverable |
|------|------------|
| entities.yaml 작성 (20–50개 entity + aliases[한국어 변형]) | entities.yaml |
| Entity 로드 (CRM 공통 필드 포함) | load_entities.py |
| NL 관계 추출 (regex trigger + mecab-ko + gazetteer 검증) | extract_relations.py |
| Edge + evidence 저장 (CRM rid 규칙) | extract_relations.py 내 |
| `GraphRepository`로 1-hop 쿼리 | graph_query.py |
| 검색 통합: Hybrid → entity 추출 → graph 확장 | search.py 확장 |

> **Day 5 완료**: '결제 서비스 의존성' → CALLS/PUBLISHES edge + 근거 chunk.

#### Day 6: OTel 수집 + Aggregation

| 작업 | Deliverable |
|------|------------|
| OTel Collector 설정 (OTLP receiver → Tempo exporter) | otel-config.yaml |
| Tempo 쿼리 테스트 (테스트 trace 전송 + 조회) | test_tempo.py |
| Service name resolution (peer.service → k8s meta → hash fallback) | resolver.py |
| OTel Aggregator: Tempo 쿼리 → CALLS_OBSERVED edge 생성 | otel_aggregator.py |
| `GraphRepository.upsert_edges()`로 observed_edges 저장 | otel_aggregator.py 내 |

> **Day 6 완료**: 테스트 trace → Tempo → CALLS_OBSERVED edge 생성 확인.

#### Day 7: Diff Detection + 보고서

| 작업 | Deliverable |
|------|------------|
| `GraphRepository.get_diff()`로 edges vs observed_edges 비교 | diff_engine.py |
| quality_flags 자동 태깅 (doc_only, observed_only, conflict) | diff_engine.py 내 |
| Diff 보고서 CLI: `khala diff` → 불일치 목록 + 양쪽 evidence | cli.py 확장 |
| Diff API: `GET /diff` → JSON 보고서 | api.py |

> **Day 7 완료 (★ 두 번째 마일스톤)**:
> `khala diff` → Dead Doc / Shadow Dependency / Semantic Mismatch 목록.

#### Day 8: Graph + OTel 검색 통합

| 작업 | Deliverable |
|------|------------|
| 검색에 observed_edge 포함: entity 조회 시 designed + observed 양쪽 반환 | search.py 확장 |
| Evidence Packet에 designed_edges + observed_edges + diff_flags 포함 | evidence.py 확장 |
| LLM 답변에 "설계 기준" vs "관측 기준" 구분 표시 | answer.py 확장 |

> **Day 8 완료**: "문서에는 A→B HTTP, 실제로는 A→Kafka→B" 같은 응답 가능.

### === 구간 3: 통합 + 품질 (Day 9–10) ===

#### Day 9: API + 통합 테스트

| 작업 | Deliverable |
|------|------------|
| FastAPI 엔드포인트 정리: POST /search, POST /ingest, GET /graph/{rid}, GET /diff | api.py |
| 통합 테스트 18건 (9장 테스트 시나리오) | test_integration.py |
| 증분 재인덱싱 (content_hash 변경분만) | ingest.py 확장 |
| 웹 업로드 API: POST /upload → Git repo 저장 + 자동 인덱싱 | api.py 확장 |

#### Day 10: 품질 평가 + 문서화

| 작업 | Deliverable |
|------|------------|
| 품질 평가: 15개 테스트 쿼리로 Hybrid vs BM25-only vs Vector-only | eval_results.md |
| Diff 품질: 알려진 diff 케이스 3건 재현 확인 | eval_results.md |
| 버그 수정 + 안정화 | bugfix |
| README (설치, 사용법, 아키텍처) | README.md |
| 데모 시나리오 3개 (검색 + graph + diff) | demo.md |

> **Day 10 완료 (MVP 완성)**

---

## 8. 기술 스택

| 컴포넌트 | 선택 | 이유 |
|---------|------|------|
| Language | Python 3.11+ | ML/NLP 생태계 + Claude Code 생산성 |
| Framework | FastAPI + Typer CLI | API 경계 + CLI 병행 |
| DB | PostgreSQL 16 + pgvector | Vector+BM25+Graph+OTel 통합 단일 DB |
| 한국어 | mecab-ko (Docker 내) | tsvector 연동 BM25 형태소 매칭 |
| Embedding | multilingual-e5-base (Ollama) | 한국어 성능 우수 + 로컬 |
| LLM | Claude Sonnet API | 한국어 답변 품질 우수 |
| OTel | OTel Collector + Grafana Tempo | Trace 수집 + 저장 + 쿼리 |
| Container | Docker Compose | 6개 컨테이너 한 명령어 기동 |

### 8.1 Docker Compose 구성

| 컨테이너 | 이미지 | 포트 |
|---------|-------|------|
| khala-db | postgres:16 + pgvector 확장 | 5432 |
| khala-ollama | ollama/ollama | 11434 |
| khala-otel | otel/opentelemetry-collector | 4317 (gRPC), 4318 (HTTP) |
| khala-tempo | grafana/tempo | 3200 (query), 4317 (OTLP) |
| khala-app | Custom (Python + mecab-ko) | 8000 (FastAPI) |
| khala-grafana (선택) | grafana/grafana | 3000 (trace 시각화) |

---

## 9. 테스트 시나리오 (18건)

| # | 카테고리 | 시나리오 | 통과 기준 |
|---|---------|---------|----------|
| 1 | 한국어 BM25 조사 | "서비스" 검색 | "서비스가/를/의" 모두 반환 |
| 2 | 한국어 BM25 어미 | "발행" 검색 | "발행한다/된" 반환 |
| 3 | 한영 혼용 | "payment-service 토픽" | 혼용 문서 매칭 |
| 4 | Hybrid > Vector | exact entity 이름 | Hybrid top-1 향상 |
| 5 | Vector semantic | "결제 관련 이벤트" | 의미 유사 문서 |
| 6 | Quarantine | AWS key 문서 | quarantine + 검색 미반환 |
| 7 | Classification | RESTRICTED 문서 | 일반 검색에서 미반환 |
| 8 | Evidence link | edge evidence 확인 | chunk이 relation 언급 |
| 9 | Graph 1-hop | entity 이웃 조회 | 연결된 entity + edge |
| 10 | LLM 근거 | LLM 답변 | doc_uri 인용 포함 |
| 11 | OTel 집계 | A→B trace 전송 | CALLS_OBSERVED edge 생성 |
| 12 | Dead Doc | 문서: A→B, trace: 없음 | doc_only flag |
| 13 | Shadow Dep | trace: A→C, 문서: 없음 | observed_only flag |
| 14 | Semantic Mismatch | 문서: sync, trace: async | conflict flag |
| 15 | Diff 보고서 | `khala diff` 실행 | 3개 유형 모두 표시 |
| 16 | rid 안정성 | 문서 수정 후 재인덱싱 | doc rid 유지, chunk rid 재생성 |
| 17 | Provenance | Edge provenance 확인 | prov_inputs에 source chunk rid |
| 18 | CRM 필터 | 모든 rtype에 classification 필터 | RESTRICTED이면 rtype 무관 미반환 |

---

## 10. MVP → 2.0 로드맵

### 확장 계획

| 단계 | 내용 | 기간 | 관련 추상화 |
|------|------|------|-----------|
| 확장 1 | Code Review Agent: PR diff → Khala 검색 → 정합성 판단 | 1주 | API 추가 |
| 확장 2 | Troubleshooting Agent: 장애 trace → graph + diff → 근본 원인 | 1주 | API 추가 |
| 확장 3 | Cross-encoder reranking + query expansion | 3–5일 | search.py 수정 |
| 확장 4 | Neo4j 전환 + Leiden community detection | 1주 | **GraphRepository 교체** |
| 확장 5 | OpenAPI/Proto/Rego 파서 (결정적 추출) | 1주 | extract_relations.py 수정 |
| 확장 6 | MCP Server + Structured query syntax | 3–5일 | API 래퍼 추가 |
| 확장 7 | OPA PDP + quarantine SLA + 에스컬레이션 | 1주 | UserContext 확장 |
| 확장 8 | Git-backed wiki + Slack Bot | 1주 | ingest.py source_kind 분기 |

### 2.0 전환 시 추상화 활용 지점

```
확장 항목          활용하는 추상화              변경 방법
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
확장 3 Reranking   search.py                  search.py에 rerank 단계 삽입
확장 4 Neo4j       GraphRepository Protocol   Neo4jGraphRepository 구현체 교체
확장 5 파서 추가    extract_relations.py       파일 내 추출 로직 교체/확장
확장 8 Slack/Wiki  ingest.py                  source_kind 분기 추가
모델 교체          EmbeddingService 래퍼       클래스 내부 교체
Multi-LLM         LLMService 래퍼             클래스 내부 교체
Contextual Enrich get_search_text() 함수      함수 1개 수정 → 재인덱싱
Entity 추출 변경   canonicalize_entity_name()  rid 안정성 유지
```

### 우선순위 판단

1. **Code Review / Troubleshooting Agent가 최우선** → Khala의 존재 이유.
2. 검색 품질 부족 시 → reranking + query expansion.
3. Graph 복잡도 증가 시 → Neo4j 전환.
4. 비개발자 협업 필요 시 → wiki + Slack.

---

## 참고 문헌

- [Towards Practical GraphRAG: Efficient KG Construction and Hybrid Retrieval](https://arxiv.org/abs/2507.03226)
- [Benchmarking Vector, Graph and Hybrid RAG Pipelines](https://arxiv.org/abs/2507.03608)
- [HybridRAG: Integrating Knowledge Graphs and Vector RAG](https://arxiv.org/abs/2408.04948)
- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
- [Late Chunking: Contextual Chunk Embeddings](https://arxiv.org/pdf/2409.04701)
- [Graph RAG in 2026: A Practitioner's Guide](https://medium.com/graph-praxis/graph-rag-in-2026-a-practitioners-guide-to-what-actually-works-dca4962e7517)
- [Optimizing RAG with Hybrid Search & Reranking](https://superlinked.com/vectorhub/articles/optimizing-rag-with-hybrid-search-reranking)
- [The Ultimate RAG Blueprint 2025/2026](https://langwatch.ai/blog/the-ultimate-rag-blueprint-everything-you-need-to-know-about-rag-in-2025-2026)
