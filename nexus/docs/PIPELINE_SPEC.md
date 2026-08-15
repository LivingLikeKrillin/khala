# Nexus Pipeline 상세 명세

> 각 파이프라인의 input/output/단계/에러 처리를 정확히 정의한다.
> Claude Code는 이 문서를 보고 각 모듈의 함수 시그니처와 에러 핸들링을 생성해야 한다.

---

## 1. Ingestion Pipeline

### 개요
Markdown 문서를 수집하여 Nexus DB에 인덱싱한다. 소스는 두 갈래다 — 파일시스템(Git repo)과 Notion. 어느 쪽이든 `run_ingest()` 한 곳으로 모인다.

### 전체 흐름
```
[Git repo]  ──────────────────────────┐
                                      │
                                      ├→ [세대 게이트] → Collect → Classify → Quarantine Gate
[Notion] → 이미지 판독 → Markdown ────┘    assert_writable
             (machine_read)

  → Chunk → Index(BM25 + Vector) → Extract Graph → Store
```

**세대 게이트가 맨 앞인 것은 의도다.** `collect`보다 먼저 본다 — "아무것도 쓰기 전에 거부한다"는 문서 한 행도 안 남긴다는 뜻이다. 모든 쓰기 경로(CLI·HTTP·A2A·ingest-notion)가 `run_ingest()`로 모이므로 검사는 이 한 곳이면 된다.

**Notion 경로의 이미지는 적재 시점에 텍스트로 판독된다.** 판독된 텍스트에서 나온 청크는 `provenance_tier='machine_read'`로 표시되고, 그 표시는 프롬프트·API 응답·웹 UI까지 따라간다. 사람이 쓴 청크와 같은 근거로 취급되지 않는다.

### 1.1 Collect (collector.py)

**Input**: 폴더 경로 (str), force 여부 (bool)

**Output**: `list[CollectedFile]`

```python
@dataclass
class CollectedFile:
    path: str               # 절대 경로
    relative_path: str      # repo root 기준 상대 경로
    content: str            # 파일 내용
    content_hash: str       # SHA-256
    frontmatter: dict       # YAML frontmatter 파싱 결과 (없으면 {})
    canonical_uri: str      # git://repo/relative_path
```

**동작**:
1. `glob("**/*.md")` 로 Markdown 파일 목록 수집
2. 각 파일의 content_hash(SHA-256) 계산
3. DB에서 같은 canonical_uri + 같은 hash가 있으면 → skip (force=true면 무시)
4. YAML frontmatter 파싱 (있으면 title/doc_type/classification/owner/tags 추출)
5. frontmatter 없으면: title = 첫 번째 H1 또는 파일명

**에러 처리**:
- 파일 읽기 실패: 해당 파일 skip, 에러 로그, 나머지 계속
- frontmatter 파싱 실패: frontmatter={}, 기본값 사용, 경고 로그

---

### 1.2 Classify (classifier.py)

**Input**: `CollectedFile`

**Output**: `ClassificationResult`

```python
@dataclass
class ClassificationResult:
    classification: str     # PUBLIC | INTERNAL | RESTRICTED
    doc_type: str          # markdown | policy | glossary
    language: str          # ko | en | mixed
    is_quarantined: bool
    quarantine_reason: str | None  # pii_detected | secret_detected | unlabeled | conflict
    pii_types: list[str]   # email | phone | account | aws_key | jwt
```

**동작 (순서 중요, 먼저 매치된 규칙이 우선)**:

1. **PII/Secret 스캔** (scanner.py):
   - 정규식 패턴 매칭 (config.yaml에서 로드):
     - AWS Access Key: `AKIA[0-9A-Z]{16}`
     - JWT: `eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_.+/=]+`
     - 신용카드: `\b[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}[- ]?[0-9]{4}\b` + Luhn 검증
     - 한국 주민번호: `\b[0-9]{6}-[1-4][0-9]{6}\b`
     - 한국 전화번호 + 이메일 조합: 둘 다 같은 문서에 있으면 PII
   - 하나라도 매치 → `is_quarantined=true, quarantine_reason="pii_detected"`

2. **경로 규칙** (config.yaml):
   ```yaml
   path_rules:
     - pattern: "/security/**"
       classification: RESTRICTED
     - pattern: "/credentials/**"
       classification: RESTRICTED
     - pattern: "/public/**"
       classification: PUBLIC
   ```

3. **파일 타입 규칙**:
   - `*.rego`, `*.pem`, `*.key`, `*.crt`, `*.env` → RESTRICTED

4. **Frontmatter 명시**:
   - frontmatter에 classification 있으면 그 값 사용
   - 단, 규칙이 RESTRICTED를 부여했는데 frontmatter가 INTERNAL이면 → RESTRICTED 유지 (보수적)

5. **기본값**: classification=INTERNAL, doc_type=markdown

6. **언어 감지**:
   - 한국어 문자(가-힣) 비율 > 50% → "ko"
   - 한국어 < 10% → "en"
   - 그 외 → "mixed"

**에러 처리**:
- 스캔 실패: RESTRICTED + quarantine으로 보수적 처리 (안전한 실패)

---

### 1.3 Quarantine Gate

classify 결과에서 `is_quarantined=true`인 경우:
- documents 테이블에 메타데이터만 저장 (is_quarantined=true)
- **chunk를 생성하지 않음** (절대)
- **embedding을 생성하지 않음** (절대)
- **graph extraction을 수행하지 않음** (절대)
- 로그: `QUARANTINED: {path} reason={reason} pii_types={types}`

---

### 1.4 Chunk (chunker.py)

**Input**: `CollectedFile` + `ClassificationResult`

**Output**: `list[ChunkData]`

```python
@dataclass
class ChunkData:
    chunk_text: str
    section_path: str      # "H1 Title > H2 Title"
    chunk_index: int       # 문서 내 순서 (0-based)
    token_count: int       # 실제 토큰 수
```

**동작**:

1. **구조 파싱**: Markdown → H1/H2 기준으로 섹션 분리
2. **토큰 기준 분할**:
   - 한국어 문서 (language=ko/mixed): 1000-1200 tokens 목표, 150 token overlap
   - 영어 문서 (language=en): 600-800 tokens 목표, 80 token overlap
   - 코드블록/표: 가능하면 단일 블록 유지 (분할 시 블록 경계 존중)
3. **section_path 생성**: 가장 최근 H1 + H2를 경로로

**토큰 카운터**: tiktoken 또는 간이 카운터 (공백 기준 × 한국어 보정 2.3배)

**에러 처리**:
- 빈 문서: chunk 0개 반환. 정상 처리 (documents에는 저장)
- 파싱 실패: 전체 텍스트를 단일 chunk로 (section_path="")

---

### 1.5 Index - BM25 (bm25.py)

**Input**: `ChunkData` + chunk_text

**Output**: tsvector (PostgreSQL에 직접 저장)

**동작**:
1. mecab-ko로 chunk_text 형태소 분석
2. 명사(NNG, NNP), 동사 어간(VV), 형용사 어간(VA), 외래어(SL), 숫자(SN) 추출
3. 조사(JKS, JKO, JKB...), 어미(EP, EF, EC...), 기호(SF, SP...) 제거
4. 추출된 형태소를 공백 join → PostgreSQL `to_tsvector('simple', joined_morphemes)`
5. chunks 테이블의 tsvector_ko 컬럼에 UPDATE

**예시**:
```
입력: "결제 서비스가 알림 모듈에 이벤트를 전달한다"
mecab 출력: 결제/NNG 서비스/NNG 가/JKS 알림/NNG 모듈/NNG 에/JKB 이벤트/NNG 를/JKO 전달/NNG 하/VV 다/EF
필터 후: "결제 서비스 알림 모듈 이벤트 전달 하"
tsvector: '결제':1 '서비스':2 '알림':3 '모듈':4 '이벤트':5 '전달':6 '하':7
```

**검색 시 (tsquery 생성)**:
```
입력: "서비스"
mecab 출력: 서비스/NNG
tsquery: '서비스'
→ "서비스가", "서비스를", "서비스의" 포함 문서 모두 매칭 (조사가 제거되었으므로)
```

**에러 처리**:
- mecab 분석 실패: pg_trgm fallback (chunk_text ILIKE '%query%')
- mecab 프로세스 죽음: 재시작 후 retry 1회

---

### 1.6 Index - Embedding (index/embed.py + providers/embedding.py)

**Input**: chunk (dict) — 텍스트는 `get_search_text()`를 경유한다. 즉 `chunk_text` 원문이 아니라 `context_prefix` 또는 `[section_path]`가 앞에 붙은 검색용 텍스트다.

**Output**: 설정된 벡터 컬럼에 UPDATE. 차원은 **모델이 정한다**(아래).

**동작**:
1. `configured_column()`이 이번 세대의 대상 컬럼을 정한다. 화이트리스트는 `index/vector_index.py`의 `VECTOR_COLUMNS`이고, 밖의 값이면 기동에 실패한다.
2. `EmbeddingService`가 모델별 지시문을 붙여 백엔드를 호출한다. **`index/embed.py`는 Ollama를 직접 부르지 않는다.**
3. 반환 벡터를 `chunks.<column>`에 UPDATE하고, `chunk_vector_provenance`에 (청크, 컬럼)별 모델 출처를 남긴다.

**모델 레지스트리 — 설정이 아니라 사실이다** (`providers/embedding.py`)

세대는 **모델 · 벡터 컬럼 · 백엔드** 셋이 함께 움직인다. 하나만 움직인 상태는 조용히 틀리므로 기동 시점에 막는다.

| 모델 | 차원 | 백엔드 | 지시문 (document / query) |
|---|---|---|---|
| `nomic-embed-text` (기본) | 768 | ollama | `search_document: ` / `search_query: ` |
| `KURE-v1` | 1024 | sidecar | `("", "")` |

- **차원은 `config.yaml`에 없다.** `MODEL_DIMENSIONS`에 산다 — 설정에 같은 숫자를 또 적으면 세 번째 진실이 생긴다.
- **지시문도 설정 기본값이 아니다.** 모델 카드에서 온다. `("", "")`은 "미지정"이 아니라 **"이 모델은 지시문을 쓰지 않는다"는 적극적 사실**이고, 둘은 구분된다. 한 모델의 형식을 다른 모델에 씌우면 "그 모델을 잘못 쓴 결과"를 재게 된다.

**기동 시점에 실패하는 것들** — 전부 조용히 틀리는 경로를 막기 위한 것이다.

- `UnknownEmbeddingModel` — 레지스트리에 없는 모델. 조용히 nomic 형식을 물려주면 그 모델을 잘못 쓴다.
- `ConflictingPrefixConfig` — 지시문 없는 모델에 지시문을 설정했다.
- `InconsistentEmbeddingGeneration` — 모델·컬럼·백엔드가 한 세대를 안 가리킨다. 빈 컬럼일 때는 0행이라 아무 일도 없다가, 재임베딩으로 행이 차는 순간 pgvector가 `different vector dimensions`를 낸다.
- `WrongVectorDimensions` — 백엔드가 그 모델의 차원이 아닌 벡터를 돌려줬다. Matryoshka 절단·잘못 띄운 사이드카·헤드가 바뀐 체크포인트가 전부 이 모양으로 온다.

**세대 선언 게이트**: 적재는 `collect`보다도 먼저 `assert_writable()`을 통과해야 한다(§1.0 참조, `index/generation.py`). 실행 중인 해석이 코퍼스의 선언과 다르면 **문서를 한 건도 읽기 전에** 거부한다. 이 게이트가 막는 실패는 *문서화된 명령이 아무도 검색하지 않는 컬럼에 조용히 적재하는 것*이다.

**에러 처리**:
- 배치 실패 시 `embedding_batch_failed`를 남기고 **그 배치의 각 청크에 대해 `record_refusal()`로 거부를 행으로 남긴다.** 삼키면 그 청크는 벡터 다리에서 영구히 사라지고 아무도 모른다.
- 거부 사유는 백엔드 메시지를 **요약하지 않고 그대로** 남긴다. "왜 안 되는지"가 곧 처방이기 때문이다 — `413 max_seq_length(8192)`는 청킹을 고치라는 말이고, 인코딩 오류는 다른 처방이다.
- `embed_refusals`(기계가 낸 사실)와 `embed_waivers`(사람이 이름을 걸고 포기한 결정)는 **섞지 않는다.**
- 거부 기록 자체가 실패해도 색인은 계속한다 — 진단이 진단 대상을 죽이면 안 된다.

**배치 처리**: 기본 `batch_size=10`. 타임아웃은 `EMBEDDING_BATCH_TIMEOUT`(기본 600초).

---

### 1.7 Graph Extraction (graph_extractor.py)

**Input**: `list[ChunkData]` + entities.yaml (gazetteer)

**Output**: `list[EdgeCandidate]`

```python
@dataclass
class EdgeCandidate:
    edge_type: str          # CALLS | PUBLISHES | SUBSCRIBES
    from_entity_name: str   # gazetteer에서 매칭된 canonical name
    to_entity_name: str
    source_chunk_rid: str   # 근거가 된 chunk
    confidence: float       # 0.0-1.0
    trigger_text: str       # 매칭된 원문 구간
```

**동작**:

1. **Entity 인식**:
   - entities.yaml에서 name + aliases 로드
   - chunk_text에서 entity mention 탐색 (exact match + alias match)
   - mecab-ko로 형태소 분석 후 entity name 매칭 (조사 제거 상태에서)

2. **Relation trigger 탐색**:
   ```yaml
   triggers:
     CALLS:
       ko: ["호출한다", "호출하는", "요청한다", "요청하는", "연동", "통신"]
       en: ["calls", "invokes", "requests", "connects to"]
     PUBLISHES:
       ko: ["발행한다", "발행하는", "전송한다", "보낸다", "publish"]
       en: ["publishes", "emits", "sends", "produces"]
     SUBSCRIBES:
       ko: ["구독한다", "구독하는", "수신한다", "받는다", "consume"]
       en: ["subscribes", "consumes", "listens", "receives"]
   ```

3. **Window 제약**: 같은 문장 또는 인접 3문장 이내에 2개 entity + 1개 trigger가 있으면 후보

4. **부정 필터**: "호출하지 않는다", "does not call" → skip

5. **Gazetteer 검증**: 양쪽 entity가 모두 entities.yaml에 존재해야 함. 미등록 entity → 로그만 남기고 skip

6. **Edge 저장**: `make_rid("edge", ...)` 로 rid 생성 → upsert (같은 rid면 confidence 갱신)

7. **Evidence 저장**: edge ↔ chunk evidence link 생성

**에러 처리**:
- Entity 인식 실패 (0개 매칭): 해당 chunk에서 graph 추출 skip. 정상
- Trigger 매칭 없음: skip. 정상
- Gazetteer 파일 로드 실패: 전체 graph extraction 중단. 에러 반환

---

## 2. Hybrid Search Pipeline

### 전체 흐름
```
[Query] → mecab-ko 분석 → BM25 topK + Vector topK (병렬) → RRF Fusion → Classification Filter → Evidence Packet → LLM → Answer
```

### 2.1 Query 전처리

**Input**: query (str)

**Output**: `QueryParts`

```python
@dataclass
class QueryParts:
    original: str          # 원본
    tsquery: str           # mecab-ko 분석 → tsquery 문자열
    embedding: list[float] # query embedding (768차원)
    detected_entities: list[str]  # gazetteer에서 매칭된 entity name
```

**동작**:
1. mecab-ko로 형태소 분석 → 명사/동사어간/외래어 추출
2. 추출 형태소로 tsquery 생성: `'결제' & '서비스' & '토픽'`
3. Ollama로 query embedding 생성: `"query: " + original`
4. Entity gazetteer에서 매칭: query에 entity name/alias가 포함되면 추출

### 2.2 BM25 검색

```sql
SELECT c.rid, c.chunk_text, c.doc_rid, c.section_path, c.source_uri,
       ts_rank(c.tsvector_ko, query) as bm25_score
FROM chunks c
WHERE c.tsvector_ko @@ to_tsquery('simple', %(tsquery)s)
  AND c.tenant = %(tenant)s
  AND c.classification <= %(clearance)s
  AND c.is_quarantined = false
  AND c.status = 'active'
ORDER BY bm25_score DESC
LIMIT %(top_k)s;
```

### 2.3 Vector 검색

```sql
SELECT c.rid, c.chunk_text, c.doc_rid, c.section_path, c.source_uri,
       1 - (c.embedding <=> %(query_embedding)s) as vector_score
FROM chunks c
WHERE c.tenant = %(tenant)s
  AND c.classification <= %(clearance)s
  AND c.is_quarantined = false
  AND c.status = 'active'
  AND c.embedding IS NOT NULL
ORDER BY c.embedding <=> %(query_embedding)s
LIMIT %(top_k)s;
```

### 2.4 RRF Fusion

```python
def rrf_fusion(bm25_results: list, vector_results: list, k: int = 60) -> list:
    """Reciprocal Rank Fusion. k=60은 표준값."""
    scores = {}

    for rank, result in enumerate(bm25_results):
        rid = result.rid
        scores[rid] = scores.get(rid, 0) + 1.0 / (k + rank + 1)

    for rank, result in enumerate(vector_results):
        rid = result.rid
        scores[rid] = scores.get(rid, 0) + 1.0 / (k + rank + 1)

    # 점수 내림차순 정렬
    sorted_rids = sorted(scores.keys(), key=lambda r: scores[r], reverse=True)
    return sorted_rids[:top_k]
```

### 2.5 Classification Filter (post-retrieval)

RRF 결과에서 한 번 더 classification 확인. pre-filter에서 대부분 걸리지만 safety net.

### 2.6 Evidence Packet 조립

```python
@dataclass
class EvidencePacket:
    question: str
    route_used: str
    evidence_snippets: list[EvidenceSnippet]  # 상위 chunk들
    graph_findings: GraphFinding | None        # entity 관계 (있으면)
    provenance: list[ProvenanceRef]            # 출처 목록
```

### 2.7 LLM 호출

**System prompt** (prompts.py):
```
당신은 조직의 내부 문서와 운영 데이터를 기반으로 답변하는 AI 어시스턴트입니다.

규칙:
1. 제공된 evidence만을 기반으로 답변하세요. 추측하지 마세요.
2. 각 주장에는 반드시 출처(source_uri + section_path)를 인용하세요.
3. 설계 문서 기반 정보와 OTel 관측 기반 정보가 모두 있으면, 구분하여 표시하세요.
4. diff_flags가 있으면 (doc_only, observed_only, conflict) 반드시 언급하세요.
5. 근거가 없는 질문에는 "현재 인덱싱된 문서에서 관련 정보를 찾을 수 없습니다"라고 답하세요.
```

**호출 전 — 정직한 부재**: evidence packet의 snippet이 0건이면 **LLM을 아예 호출하지 않는다.** 고정 문장을 돌려주고 `abstained=True, abstain_reason="no_evidence"`로 표시한다. 근거가 없을 때 모델에게 물어보는 것 자체가 환각을 초대하는 일이다.

### 2.8 호출 이후 — 모델 출력은 검증 대상이다

프롬프트로 인용을 **요구**하는 것과 인용이 **실재하는지 확인**하는 것은 다른 일이다. 규칙 2를 지켰는지는 코드가 판정한다.

- **인용 검증** (`llm/citations.py`) — 답변이 단 인용을 실제로 건네진 evidence packet과 대조한다. 해소되지 않는 것은 출처인 척 통과시키지 않고 `unverified_citations`로 따로 보고한다.
- **숫자 검증** (`llm/numbers.py`) — 답변 속 숫자를 evidence 및 *모델이 실제로 본 질의*와 대조한다.
- **최신성 라벨** (`documents/staleness.py`) — 스니펫마다 타입별 TTL 대비 경과를 붙이고 `n_stale`을 센다. 읽는 사람을 위한 라벨이며 **랭킹이나 배제에 관여하지 않는다.**
- **출처 등급 표기** (`search/provenance.py`) — `machine_read` 청크에는 표시가 붙고, 그 어휘는 프롬프트·응답·MCP·웹에서 한 곳(`provenance.py`)에서만 나온다.
- **생성 실패는 답변 실패와 다르다** (`llm/failure.py`) — LLM 호출이 실패해도 `llm_failed`와 안정적인 `llm_failure_reason`을 붙여 **근거는 그대로 반환한다.** 서술이 없다고 검색 결과까지 버리지 않는다.

---

## 3. OTel Aggregation Pipeline

### 전체 흐름
```
[Tempo] → Query traces → Group by (from_service, to_service) → Resolve service names → Aggregate metrics → Upsert observed_edges
```

### 3.1 Tempo 쿼리

**Input**: window_minutes, lookback_minutes

**동작**:
1. Tempo HTTP API 호출: `GET /api/search` (TraceQL)
2. 쿼리: `{status = ok || status = error}` + time range
3. 각 trace에서 span 추출: root span → child spans → (from_service, to_service) 쌍 추출

### 3.2 Service Name Resolution (resolver.py)

**Input**: span attributes

**Output**: canonical service name (str)

**우선순위 (순서대로 시도)**:
1. `service.name` attribute (가장 신뢰)
2. `peer.service` attribute → entities.yaml에서 검증
3. `k8s.deployment.name` + `k8s.namespace.name` (있으면)
4. `server.address` → reverse DNS 시도
5. fallback: `unknown_svc_` + hash(address)[:8]

**Output에 `resolved_via` 필드 기록**: 어떤 단계에서 resolve되었는지

### 3.3 Aggregation

**Input**: (from_service, to_service) 쌍들의 span 목록

**Output**: observed_edge 데이터

```python
@dataclass
class AggregatedEdge:
    from_service: str
    to_service: str
    call_count: int
    error_rate: float       # error_count / total_count
    latency_p50: float      # ms
    latency_p95: float
    latency_p99: float
    protocol: str           # span attribute에서 추출
    interaction_style: str  # span.kind로 판별: CLIENT/SERVER=SYNC, PRODUCER/CONSUMER=ASYNC
    sample_trace_ids: list[str]  # 무작위 3-5개
    trace_query_ref: str    # 이 집계를 재현하는 Tempo 쿼리
    resolved_via: str
```

### 3.4 Upsert

- rid = `make_rid("obs_edge", tenant, "CALLS_OBSERVED", from_rid, to_rid)`
- 같은 rid 존재 → 메트릭 업데이트 (call_count 누적이 아니라 최신 window로 교체)
- entity가 entities.yaml에 없으면 → entity 자동 생성 (type="Service", source_kind="otel")
- evidence 생성: subject_rid=observed_edge.rid, evidence_rid=trace_query_ref

---

## 4. Diff Pipeline

### 전체 흐름
```
[edges] + [observed_edges] → Compare → Tag quality_flags → Generate report
```

### 4.1 비교 로직

```python
def compute_diff(tenant: str):
    # 1. edges에서 (from_rid, to_rid) 쌍 추출
    designed = {(e.from_rid, e.to_rid): e for e in get_active_edges(tenant)}

    # 2. observed_edges에서 (from_rid, to_rid) 쌍 추출
    observed = {(o.from_rid, o.to_rid): o for o in get_active_observed(tenant)}

    # 3. 비교
    for pair in designed:
        if pair not in observed:
            # doc_only: 문서에만 있고 관측에 없음
            tag_quality_flag(designed[pair].rid, "doc_only")

    for pair in observed:
        if pair not in designed:
            # observed_only: 관측에만 있고 문서에 없음
            tag_quality_flag(observed[pair].rid, "observed_only")

    for pair in designed:
        if pair in observed:
            # 양쪽 존재: protocol/style 비교
            d, o = designed[pair], observed[pair]
            # MVP: 향후 interaction_style, protocol 비교로 conflict 탐지
            pass
```

### 4.2 quality_flags 태깅

- DB의 quality_flags 배열에 flag를 추가/갱신
- flag는 누적이 아니라 매 diff 실행 시 재계산
- diff 실행 전 기존 flag를 초기화 후 다시 계산

### 4.3 보고서 생성

v_edge_diff 뷰를 조회하여 JSON 또는 CLI 테이블로 출력.
각 diff 항목에 대해:
- designed edge의 evidence (문서 chunk) 첨부
- observed edge의 trace_query_ref + sample_trace_ids 첨부
