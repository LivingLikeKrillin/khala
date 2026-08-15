# Nexus — Project Context for Claude Code

> Nexus는 조직 내부 지식(문서/정책/설정)과 운영 사실(OTel trace/metric)을 결합하여,
> 근거 기반(grounded)으로 검색·답변하는 엔터프라이즈 검색 계층이다.
> 맥락 기반 AI Agent(Code Review / Troubleshooting)의 context provider가 최종 목표다.
>
> **이 파일은 코드보다 뒤처지면 위험하다.** 문서는 안 읽으면 그만이지만 이건 매 세션 로드되고,
> 여기 적힌 틀린 전제 위에서 만들어진 것은 전부 틀린다. 규칙을 고칠 때는 **근거를 함께 적어라** —
> 근거 없는 규칙은 나중에 아무도 지우지 못해 파일만 부푼다.

---

## 핵심 원칙 (절대 위반 금지)

1. **Grounded answers only**: 모든 답변은 source chunk 또는 trace 포인터를 근거로 인용. 추측 금지.
2. **System decides, LLM narrates**: 접근 통제, 분류, 경로 판정은 코드(deterministic). LLM은 요약/설명만.
   - **인용을 요구하는 것과 인용이 실재하는지 확인하는 것은 다른 일이다.** 프롬프트로 요구한 뒤 `llm/citations.py` 가 evidence packet 과 대조해 **코드로** 판정하고, 해소되지 않는 것은 출처인 척 통과시키지 않고 `unverified_citations` 로 따로 보고한다. 숫자도 `llm/numbers.py` 가 같은 방식으로 검사한다. 이 원칙을 "프롬프트에 잘 적으면 된다" 로 이해하지 말 것.
3. **Default-deny + Quarantine**: 분류 불확실 또는 PII 감지 → `is_quarantined=true`, 인덱싱 중단. 검색에 절대 포함 금지.
4. **한국어 first**: 모든 텍스트 파이프라인이 한국어 형태소 특성(조사/어미 결합)을 고려. mecab-ko로 BM25 인덱싱.
5. **Nexus는 인덱스, 저장소가 아님**: 원본 문서는 Git, 원본 trace는 Tempo. Nexus DB에는 파생 데이터만.
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
  감사 추적, tenant 관리 UI
```

> ⚠ **인증은 이 로드맵에서 빠졌다 — 이미 만들어졌기 때문이다.** 예전에 "Phase 3: JWT 인증/인가"로
> 적혀 있었으나 실제로 출하된 것은 JWT 가 아니라 **불투명 bearer 토큰**이고, 설계가 다르다:
> 토큰 하나 = 고정된 `(tenant, clearance)`, capabilities 기본 비어 있음(읽기 전용), roles 없음.
> **clearance 는 요청이 고를 수 없다** — 서버가 토큰으로 정한다. 자세한 것은
> `nexus/auth/principal.py` 와 [docs/UI_INTEGRATION.md §9](./docs/UI_INTEGRATION.md).

핵심 관점: **전체 조직이 하나의 RAG를 공유하는 것은 비효율적이다.**
팀마다 문서 구조, 용어, 검색 패턴이 다르므로 tenant 기반 맞춤형으로 진화한다.

---

## 기술 스택

- **Language**: Python 3.11+
- **Framework**: FastAPI (API) + Typer (CLI)
- **DB**: PostgreSQL 16 + pgvector + tsvector(mecab-ko) + pg_trgm
- **Embedding**: `EmbeddingService` 래퍼를 **반드시** 경유. 세대는 둘 — `nomic-embed-text`(768, ollama, 기본) · `KURE-v1`(1024, sidecar). **차원과 지시문은 설정이 아니라 모델의 사실**이라 `providers/embedding.py` 의 레지스트리에 산다(config.yaml 에 숫자를 또 적으면 세 번째 진실이 생긴다).
- **LLM**: `LLMService` 래퍼를 **반드시** 경유. 백엔드 이음매는 `NEXUS_LLM_PROVIDER` — `anthropic`(기본, 키 필요) · `claude-code`(dev, 호스트의 Claude Code 를 브리지로. **유료 키 불필요**). dev 실행이 조용히 돈을 쓰지 않게 하는 게 이 이음매의 목적이다.
- **한국어**: mecab-ko + mecab-ko-dic (Docker 내 설치)
- **OTel**: OpenTelemetry Collector + Grafana Tempo
- **Container**: Docker Compose (6개 컨테이너)

---

## 프로젝트 구조 — 이음매 지도

> **전체 파일 트리를 여기 두지 않는다.** 예전에 55행짜리 트리를 손으로 관리했고, 그 사이 실제
> 패키지 10개(`a2a` `auth` `claims` `documents` `feedback` `mcp` `slack` `sources` `tools` `web`)가
> 트리에 없는 채로 늘었다. 트리는 반드시 뒤처지고, 뒤처졌다는 사실조차 조용하다.
> 파일 목록이 필요하면 `ls` 를 쳐라. 여기 남기는 것은 **어디를 거쳐야 하는가**뿐이다.

| 하려는 일 | 반드시 경유할 곳 | 왜 |
|---|---|---|
| 그래프 조회 | `repositories/graph.py` (`GraphRepository`) | 직접 SQL 금지 — 백엔드 교체 시 재설계 방지 |
| 임베딩 생성 | `providers/embedding.py` (`EmbeddingService`) | Ollama·사이드카 직접 호출 금지. 모델별 지시문 정책이 여기 한 곳에 산다 |
| LLM 호출 | `providers/llm.py` (`LLMService`) | 백엔드 이음매(`NEXUS_LLM_PROVIDER`)가 여기 |
| 검색/임베딩 텍스트 | `utils.get_search_text()` | `chunk_text` 직접 사용 금지 — Contextual Enrichment 대비 |
| entity rid | `rid.canonicalize_entity_name()` | 추출기 교체 시 rid 안정성 |
| 벡터 컬럼 선택 | `index/vector_index.py` (`configured_column`/`VECTOR_COLUMNS`) | 화이트리스트 밖이면 기동 실패 |
| 적재 (모든 경로) | `ingest/pipeline.py` (`run_ingest`) | CLI·HTTP·A2A·Notion 이 전부 여기로 모이므로 세대 게이트가 한 곳이면 된다 |
| 출처 등급 표기 | `search/provenance.py` | 프롬프트·응답·MCP·웹이 같은 어휘를 써야 한다. 사본 금지 |
| clearance 판정 | `auth/clearance.py` | 정본 하나. 사본을 만들면 두 답이 생긴다 |

**검색 경로의 사실 하나** — `search/hybrid.py` 는 **BM25 와 벡터 두 다리**를 RRF(`k=60`)로 융합한다.
그래프는 3-way 융합에 들어가지 않는다: `_diversify` 와 top-k 컷이 **끝난 뒤** `result.graph` 로
따로 붙는 보강이고, 히트 점수에 기여하지 않는다. (이 파일은 오랫동안 "3-way 병렬 + RRF" 라고
적고 있었다.)

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

모든 Nexus 리소스의 공통 필드. 새로운 모델을 만들 때 반드시 `NexusResource`를 상속.

```python
@dataclass
class NexusResource:
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
- Embedding 실패: **삼키지 말고 `index/embed.py:record_refusal()` 로 거부를 행으로 남긴다**(`embed_refusals`). 삼키면 그 청크는 벡터 다리에서 영구히 사라지고 아무도 모른다. 백엔드 메시지는 **요약하지 말고 그대로** 남긴다 — "왜 안 되는지" 가 곧 처방이다(`413 max_seq_length` 는 청킹을 고치라는 말이고, 인코딩 오류는 다른 처방이다). 기계가 낸 사실인 `embed_refusals` 와 사람이 이름을 걸고 포기한 `embed_waivers` 를 **섞지 않는다**. 거부 기록 자체가 실패해도 색인은 계속한다 — 진단이 진단 대상을 죽이면 안 된다.
- LLM 호출 실패: evidence snippet 은 그대로 제공하고, `llm_failed` 와 **안정적인** `llm_failure_reason`(`llm/failure.py`)을 붙인다. 서술이 없다고 검색 결과까지 버리지 않는다.
- 근거 0건: **LLM 을 아예 호출하지 않는다.** 고정 문장 + `abstained=True, abstain_reason="no_evidence"`. 근거가 없을 때 모델에게 물어보는 것 자체가 환각을 초대한다.
- DB 연결 실패: 503. partial result 반환 금지

### OTel 관련
- Raw trace는 Nexus DB에 절대 저장 금지. Tempo에 포인터만
- CALLS_OBSERVED rid: window를 rid에 넣지 않음. 같은 from→to = 같은 rid
- Service name resolution: peer.service → k8s metadata → reverse DNS → hash fallback

---

## 절대 하지 말 것 (Don'ts)

1. **LLM으로 classification 결정 금지**
2. **quarantined 리소스를 검색 결과에 포함 금지**
3. **rid를 직접 문자열로 생성 금지** → `make_rid()` 필수
4. **SQL에 f-string 사용 금지** → parameterized query만
5. **원문 전체를 DB에 저장 금지** → chunk_text만, 원문은 Git
6. **Raw trace를 Nexus DB에 저장 금지** → 집계 + 포인터만
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
# 기동 (컨테이너 + DB 마이그레이션 + 모델 자동 pull). Task 없으면 README §2 의 두 줄.
task up
task up:prod          # 팀 배포 — docker-compose.prod.yml 오버레이 (reload 없음·이미지 구움·강토큰 필수)

# ⚠ 쓰는 명령은 **배포의 임베딩 세대가 설정된 곳**에서 돌려야 한다. 이 배포에서는 컨테이너 안이다
#   (세대는 env 로 오고, 그 env 는 컨테이너에만 있다). 호스트 셸에서 그냥 `nexus ingest` 를 치면
#   config.yaml 기본값 = 768/nomic 세대로 해석돼, **검색되지 않는 컬럼**에 적재된다.
#   2026-08-10 에 실제로 그렇게 됐다 (SPEC-nexus-generation-of-record).
#   컨테이너 없이 돌리는 배포라면 NEXUS_EMBEDDING_MODEL/NEXUS_EMBEDDING_COLUMN 을 같은 값으로
#   export 한 셸에서 돌린다. 세대를 DB 에 선언해 두면 어긋난 실행은 거부된다:
#     docker exec nexus-app nexus generation declare --tenant default \
#         --column embedding_1024 --model KURE-v1 --by <who>
#     docker exec nexus-app nexus generation show

# 문서 인덱싱
docker exec nexus-app nexus ingest ./docs
docker exec nexus-app nexus ingest ./docs --force   # hash 무시, 전체 재인덱싱

# Notion 적재 (미러 — 정본은 Notion 에 남는다)
docker exec nexus-app nexus ingest-notion --roots "pageId1,pageId2"
docker exec nexus-app nexus ingest-notion --roots "..." --reconcile --dry-run   # 계획만 확인
docker exec nexus-app nexus ingest-notion --roots "..." --reconcile             # soft_delete + revive

# 검색
nexus query "결제 서비스가 발행하는 토픽이 뭐야?"

# Graph 조회
nexus graph payment-service
nexus graph payment-service --hops 2

# OTel 집계
nexus otel-aggregate

# Diff 보고서
nexus diff
nexus diff --type observed_only

# 상태 확인
nexus status
```

## 테스트

```bash
pytest tests/ -v
pytest tests/test_bm25_korean.py -v
```

## 환경 변수

```
DATABASE_URL=postgresql://nexus:nexus@localhost:5432/nexus
OLLAMA_URL=http://localhost:11434
ANTHROPIC_API_KEY=sk-ant-...
TEMPO_URL=http://localhost:3200
OTEL_COLLECTOR_URL=http://localhost:4318
DEFAULT_TENANT=default
```
