# Khala — Project Context for Claude Code

> Khala는 조직 내부 지식(문서/정책/설정)과 운영 사실(OTel trace/metric)을 결합하여,
> 근거 기반(grounded)으로 검색·추론하는 Enterprise RAG + GraphRAG 시스템이다.
> 맥락 기반 AI Agent(Code Review / Troubleshooting)의 context provider가 최종 목표다.

---

## 핵심 원칙 (절대 위반 금지)

1. **Grounded answers only**: 모든 답변은 source chunk 또는 trace 포인터를 근거로 인용. 추측 금지.
2. **System decides, LLM narrates**: 접근 통제, 분류, 경로 판정은 코드(deterministic). LLM은 요약/설명만.
3. **Default-deny + Quarantine**: 분류 불확실 또는 PII 감지 → `is_quarantined=true`, 인덱싱 중단. 검색에 절대 포함 금지.
4. **한국어 first**: 모든 텍스트 파이프라인이 한국어 형태소 특성(조사/어미 결합)을 고려. mecab-ko로 BM25 인덱싱.
5. **Khala는 인덱스, 저장소가 아님**: 원본 문서는 Git, 원본 trace는 Tempo. Khala DB에는 파생 데이터만.
6. **Evidence 없는 edge 금지**: 근거 없는 관계는 존재하지 않는 관계.

---

## 로드맵 — 테마 기반 페이즈

전체 로드맵은 [에코시스템 ROADMAP.md](./ROADMAP.md) 참조.

```
Phase 1 — 팀 맞춤형
  tenant별 검색 프로파일, 문서 풀 격리, 역할별 reranking

Phase 2 — 검색 지능화
  Adaptive 검색 깊이 (simple/standard/deep), Cross-Encoder Reranking

Phase 3 — 거버넌스
  JWT 인증/인가, 감사 추적, tenant 관리 UI
```

핵심 관점: **전체 조직이 하나의 RAG를 공유하는 것은 비효율적이다.**
팀마다 문서 구조, 용어, 검색 패턴이 다르므로 tenant 기반 맞춤형으로 진화한다.

---

## 기술 스택

- **Language**: Python 3.11+
- **Framework**: FastAPI (API) + Typer (CLI)
- **DB**: PostgreSQL 16 + pgvector + tsvector(mecab-ko) + pg_trgm
- **Embedding**: multilingual-e5-base via Ollama (로컬) → `EmbeddingService` 래퍼
- **LLM**: Claude Sonnet API → `LLMService` 래퍼
- **한국어**: mecab-ko + mecab-ko-dic (Docker 내 설치)
- **OTel**: OpenTelemetry Collector + Grafana Tempo
- **Container**: Docker Compose (6개 컨테이너)

---

## 프로젝트 구조

```
khala/
├── CLAUDE.md                           ← 이 파일
├── README.md
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── config.yaml                         ← 경로 규칙, PII 패턴, doc_type 매핑
├── entities.yaml                       ← Entity gazetteer (수동 정의)
├── init.sql                            ← DB 스키마 DDL
├── otel-config.yaml
├── tempo-config.yaml
│
├── docs/                               ← 설계/명세 문서
│   ├── khala-mvp-design.md             ← MVP 설계 문서 (마스터)
│   ├── API_CONTRACT.md                 ← API 계약서
│   └── PIPELINE_SPEC.md               ← 파이프라인 상세
│
├── khala/
│   ├── __init__.py
│   │
│   ├── models/                         ← CRM 기반 도메인 모델
│   │   ├── resource.py                 ← KhalaResource base class
│   │   ├── document.py
│   │   ├── chunk.py
│   │   ├── entity.py
│   │   ├── edge.py
│   │   ├── observed_edge.py
│   │   └── evidence.py
│   │
│   ├── repositories/                   ← 데이터 접근 추상화
│   │   ├── graph.py                    ← GraphRepository Protocol + PostgresGraphRepository
│   │   └── __init__.py
│   │
│   ├── providers/                      ← 외부 API 래퍼
│   │   ├── embedding.py                ← EmbeddingService (Ollama 격리)
│   │   ├── llm.py                      ← LLMService (Claude API 격리)
│   │   └── __init__.py
│   │
│   ├── rid.py                          ← Canonical ID 생성 + canonicalize_entity_name()
│   ├── utils.py                        ← get_search_text() 등 공용 함수
│   ├── db.py                           ← PostgreSQL 연결 + 쿼리 헬퍼
│   │
│   ├── ingest/
│   │   ├── collector.py                ← 파일 수집 (glob + hash 변경 감지)
│   │   ├── scanner.py                  ← PII/Secret 스캐너
│   │   ├── classifier.py               ← Classification 규칙 엔진
│   │   ├── chunker.py                  ← doc_type별 Hierarchical Chunking
│   │   └── pipeline.py                 ← Ingestion orchestrator
│   │
│   ├── index/
│   │   ├── bm25.py                     ← get_search_text() → mecab-ko → tsvector
│   │   ├── embed.py                    ← get_search_text() → EmbeddingService → pgvector
│   │   └── graph_extractor.py          ← Entity/relation 추출 + evidence binding
│   │
│   ├── search/
│   │   ├── hybrid.py                   ← BM25 + Vector + Graph 3-way 병렬 + RRF
│   │   ├── evidence_packet.py          ← Evidence Packet 조립
│   │   └── router.py                   ← Query route 판별 (규칙 기반)
│   │
│   ├── otel/
│   │   ├── aggregator.py               ← Tempo 쿼리 → CALLS_OBSERVED 생성
│   │   ├── resolver.py                 ← Service name resolution
│   │   └── diff_engine.py              ← 설계-관측 diff + quality_flags 태깅
│   │
│   ├── llm/
│   │   ├── answer.py                   ← LLMService 호출 + 근거 기반 답변
│   │   └── prompts.py                  ← System/user prompt 템플릿
│   │
│   ├── api.py                          ← FastAPI 엔드포인트
│   └── cli.py                          ← Typer CLI
│
└── tests/
    ├── test_bm25_korean.py
    ├── test_hybrid.py
    ├── test_graph.py
    ├── test_otel.py
    ├── test_diff.py
    ├── test_quarantine.py
    ├── test_crm.py
    └── test_integration.py
```

---

## 2.0 전환 대비 추상화 규칙

### 추상화 판단 기준

```
Protocol이 필요한 경우:  구현이 여러 파일에 흩어지는 것
래퍼 클래스면 충분한 경우: 외부 API 호출을 한 곳에 모으는 것
함수면 충분한 경우:     변환 로직을 한 줄로 격리하는 것
파일 분리면 충분한 경우: 이미 단일 파일에 모여 있는 것
```

### 반드시 적용할 추상화 (Day 1에 구현)

| 비용 | 항목 | 형태 | 효과 |
|------|------|------|------|
| 반나절 | `GraphRepository` | Protocol | Neo4j 전환 시 재설계 방지 |
| 10분 | `get_search_text()` | 함수 1개 | Contextual Enrichment 대비 |
| 30분 | `EmbeddingService` | 래퍼 클래스 | 임베딩 모델 교체 대비 |
| 30분 | `LLMService` | 래퍼 클래스 | Multi-LLM 대비 |
| 10분 | `canonicalize_entity_name()` | 함수 1개 | 추출기 교체 시 rid 안정성 |

---

## Canonical Resource Model (CRM)

모든 Khala 리소스의 공통 필드. 새로운 모델을 만들 때 반드시 `KhalaResource`를 상속.

```python
@dataclass
class KhalaResource:
    rid: str              # make_rid()로 생성. 직접 문자열 생성 금지
    rtype: str            # document|chunk|entity|edge|observed_edge|evidence
    tenant: str = "default"
    classification: str = "INTERNAL"
    owner: str = "unknown"
    source_uri: str = ""
    source_version: str = ""
    source_kind: str = "git"
    hash: str = ""
    labels: list[str] = field(default_factory=list)
    is_quarantined: bool = False
    quality_flags: list[str] = field(default_factory=list)
    status: str = "active"
    created_at: datetime
    updated_at: datetime
    prov_pipeline: str = ""
    prov_inputs: list[str] = field(default_factory=list)
    prov_transform: str = ""
```

### rid 생성 규칙

```python
# 반드시 이 함수를 사용. 직접 rid를 문자열로 만들지 말 것.
def make_rid(prefix: str, *parts: str) -> str:
    raw = ":".join([prefix] + list(parts))
    return prefix.split(":")[0] + "_" + hashlib.sha256(raw.encode()).hexdigest()[:12]

# 편의 함수
doc_rid(canonical_uri)
chunk_rid(parent_doc_rid, section_path, chunk_index)
entity_rid(tenant, entity_type, canonical_name)  # ← canonicalize_entity_name() 적용 후
edge_rid(tenant, edge_type, from_rid, to_rid)
observed_edge_rid(tenant, edge_type, from_rid, to_rid)
evidence_rid(subject_rid, evidence_source_rid)
```

### get_search_text() — 검색/임베딩 텍스트 생성

```python
# chunk_text를 직접 사용 금지. 반드시 이 함수를 경유.
def get_search_text(chunk) -> str:
    """1.0: section_path 접두사. 2.0: Contextual Enrichment로 교체."""
    prefix = chunk.context_prefix or f"[{chunk.section_path}]"
    return f"{prefix} {chunk.chunk_text}"
```

### 정책 필터 (모든 검색/조회에 적용)

```python
# 이 필터는 모든 DB 쿼리에 반드시 적용. 예외 없음.
def base_filter() -> str:
    return """
        AND tenant = %(tenant)s
        AND classification <= %(clearance)s
        AND is_quarantined = false
        AND status = 'active'
    """
```

---

## 코딩 규칙

### Python 스타일
- Type hints 필수
- Pydantic v2 BaseModel (API request/response)
- dataclass (내부 도메인 모델)
- async def (FastAPI endpoint, DB 쿼리)
- f-string 사용. format() 금지
- 한국어 docstring 허용

### DB 쿼리
- asyncpg 사용
- SQL은 parameterized query만. 절대 f-string으로 SQL 조립 금지
- 모든 SELECT에 base_filter 적용
- pgvector: `embedding <=> query_embedding` (cosine distance)
- BM25 검색 대상: `search_text` (GENERATED 컬럼), chunk_text 직접 검색 금지

### 추상화 규칙
- **Graph 쿼리는 항상 `GraphRepository` Protocol을 통해 접근**. 직접 SQL 금지
- **Embedding 생성은 항상 `EmbeddingService`를 통해 호출**. Ollama 직접 호출 금지
- **LLM 호출은 항상 `LLMService`를 통해 호출**. Claude API 직접 호출 금지
- **검색/임베딩 텍스트는 항상 `get_search_text()`를 경유**. chunk_text 직접 사용 금지
- **Entity name은 항상 `canonicalize_entity_name()`을 경유**. rid 안정성 보장

### 에러 처리
- Ingestion 실패: 해당 문서만 skip, 나머지 계속. 실패 로그
- PII 감지: 즉시 quarantine. 절대 chunk 생성 금지
- Embedding 실패: retry 3회 후 skip. embedding=null 저장 (BM25로만 검색)
- LLM 호출 실패: "답변을 생성할 수 없습니다" + evidence snippet은 그대로 제공
- DB 연결 실패: 503. partial result 반환 금지

### OTel 관련
- Raw trace는 Khala DB에 절대 저장 금지. Tempo에 포인터만
- CALLS_OBSERVED rid: window를 rid에 넣지 않음. 같은 from→to = 같은 rid
- Service name resolution: peer.service → k8s metadata → reverse DNS → hash fallback

---

## 절대 하지 말 것 (Don'ts)

1. **LLM으로 classification 결정 금지**
2. **quarantined 리소스를 검색 결과에 포함 금지**
3. **rid를 직접 문자열로 생성 금지** → `make_rid()` 필수
4. **SQL에 f-string 사용 금지** → parameterized query만
5. **원문 전체를 DB에 저장 금지** → chunk_text만, 원문은 Git
6. **Raw trace를 Khala DB에 저장 금지** → 집계 + 포인터만
7. **Evidence 없는 edge 생성 금지**
8. **Neo4j, Redis, Elasticsearch 추가 금지** (MVP)
9. **영어 전용 embedding model 사용 금지** → multilingual 필수
10. **CRM 공통 필드를 생략한 테이블 생성 금지**
11. **`get_search_text()`를 거치지 않고 chunk_text를 직접 embedding/tsvector에 사용 금지**
12. **`GraphRepository`를 거치지 않고 edge/observed_edge 직접 SQL 조회 금지**
13. **`EmbeddingService`를 거치지 않고 Ollama 직접 호출 금지**
14. **`canonicalize_entity_name()`을 거치지 않고 entity rid 생성 금지**

---

## 커맨드 참조

```bash
# 인프라 기동
docker-compose up -d

# Ollama 모델 pull (최초 1회)
docker exec khala-ollama ollama pull multilingual-e5-base

# 문서 인덱싱
khala ingest ./docs
khala ingest ./docs --force          # hash 무시, 전체 재인덱싱

# 검색
khala query "결제 서비스가 발행하는 토픽이 뭐야?"

# Graph 조회
khala graph payment-service
khala graph payment-service --hops 2

# OTel 집계
khala otel-aggregate

# Diff 보고서
khala diff
khala diff --type observed_only

# 상태 확인
khala status
```

## 테스트

```bash
pytest tests/ -v
pytest tests/test_bm25_korean.py -v
```

## 환경 변수

```
DATABASE_URL=postgresql://khala:khala@localhost:5432/khala
OLLAMA_URL=http://localhost:11434
ANTHROPIC_API_KEY=sk-ant-...
TEMPO_URL=http://localhost:3200
OTEL_COLLECTOR_URL=http://localhost:4318
DEFAULT_TENANT=default
```
