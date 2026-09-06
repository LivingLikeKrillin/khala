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
4. **한국어 first**: 모든 텍스트 파이프라인이 한국어 형태소 특성(조사/어미 결합)을 고려. mecab-ko 로 BM25 인덱싱하고, **영어 전용 임베딩 모델을 쓰지 않는다**.
5. **Nexus는 인덱스, 저장소가 아님**: 원본 문서는 Git, 원본 trace는 Tempo. Nexus DB에는 파생 데이터만.
6. **Evidence 없는 edge 금지**: 근거 없는 관계는 존재하지 않는 관계.

---

## 방향

페이즈 구성(팀 맞춤형 → 검색 지능화 → 거버넌스)은 [ROADMAP.md](./ROADMAP.md) 가 정본이다.

> ⚠ **인증은 로드맵에서 빠졌다 — 이미 만들어졌기 때문이다.** 예전에 "Phase 3: JWT 인증/인가"로
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
- **의존성을 늘리지 않는다**: Neo4j·Redis·Elasticsearch 를 더하지 않는다. 그래프는 `GraphRepository` 뒤에 있으므로 필요해지면 그때 바꾸면 되고, 지금 더하면 운영 대상만 늘어난다.

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
| 벡터가 **낡았을 수 있는지** 보기 | `index/provenance.py` (`fetch_freshness`) | 복구 큐는 `WHERE <컬럼> IS NULL` 이라 **안 지워진 낡은 값을 구조적으로 못 본다** — 이 리포가 그 계열로 두 번 데였다. 같은 표의 `written_at` 이 2026-08-14 부터 쌓이고 있었는데 **읽는 코드가 하나도 없었다.** ⭐ 값은 부정 쪽이다: `written_at >= updated_at` 이면 **낡을 수 없다** ⇒ 전수 재계산(수십 분)이 그만큼 줄어든다. ⛔ **`candidates` 는 낡은 개수가 아니라 상한이다** — `updated_at` 은 내용이 안 바뀐 재적재에도 움직인다. 판정은 `scripts/check_stale_vectors.py` 가 재계산으로 한다 |
| 적재 (모든 경로) | `ingest/pipeline.py` (`run_ingest`) | CLI·HTTP·A2A·Notion 이 전부 여기로 모이므로 세대 게이트가 한 곳이면 된다 |
| 출처 등급 표기 | `search/provenance.py` | 프롬프트·응답·MCP·웹이 같은 어휘를 써야 한다. 사본 금지 |
| 근거에 무언가 덧붙이기 | `search/reconcile.py` (`packet_for_answer`) | 네 표면(web API ×2·A2A·CLI)이 전부 여기로 모인다. 표면마다 붙이면 하나가 조용히 빠진다 — **2026-09-02 에 실제로 그랬다**: 스트리밍 경로가 `assemble_packet` 을 직접 불러 정정·짝·코드 값이 웹 채팅에서만 빠졌다(외부 평가 F2). 지금은 `tests/test_answer_surfaces_share_the_seam.py` 가 표면을 센다 |
| 앵커 상태 판정 | `index/anchors.py` (`status_from_counts`) | 재검사(CLI)와 요청 경로(`search/anchor_status.py`)가 같은 규칙을 써야 한다 |
| clearance 판정 | `auth/clearance.py` | 정본 하나. 사본을 만들면 두 답이 생긴다 |
| 답변의 **모양**을 남기기 | `search/format_compliance.py` (`shape_if_measured`) | 답변 표면 셋이 한 갈래를 쓴다. 표면마다 분기를 쓰면 하나만 고쳐진다 — `packet_for_answer` 와 같은 이유다. ⛔ **준수를 판정하지 않는다**: `check` 는 요청 유형을 받는데 라이브에는 그것을 아는 부품이 없다. 기권·생성실패의 고정 안내문은 측정하지 않고 같은 키를 `None` 으로 남긴다(측정 안 한 것과 유실을 가르는 유일한 표시다) |
| 실패를 **검색 탓/서술 탓으로 가르기** | `scripts/ko_eval_answer_quality.py` (`attribute_facts`) | 두 러너(`answer_fact_probe` · `ko_eval_answer_run`)가 같은 판정을 써야 리포트를 나란히 읽는다. ⛔ **인자가 불리언 목록인 것이 설계다** — 존재 판정은 부르는 쪽이 자기 정규화로 끝낸다. 두 러너의 정규화가 다르고(쉼표 제거 vs 공백 축약), 귀속이 자기 정규화를 들고 다니면 그것이 셋째가 된다. 이 리포는 정규화가 갈려 한 라벨의 1판·2판이 반대로 나온 적이 있다 |
| 라벨을 돌릴 **코퍼스 정하기** | `scripts/ko_eval_corpus_reach.py` (`resolve_tenant`) | ⛔ **기본값이 없다.** 라벨이 `corpus.tenant` 로 선언하거나 사람이 `--tenant` 로 주고, 둘 다 없으면 돌지 않는다. 말없이 고른 `default` 때문에 설계 라벨을 물으면서 다른 코퍼스를 측정했고 그 결과를 코퍼스 결함으로 읽었다 — 같은 사고가 세 번 났고 앞의 두 번은 주석으로만 남았다. 요구 사실이 그 코퍼스에 하나도 없으면 실행을 **멈춘다** |
| 답변이 맞았는지 채점 | `scripts/ko_eval_answer_quality.py` | 답변 채점기는 **이미 있다** — 새로 쓰지 마라. `facts_present`=값이 어딘가 있는가, `asserts_value`=답으로 내세웠는가(단일 값 질문 전용). 2026-08-26 에 이것을 모르고 부분일치 채점기를 다시 썼고, 그 채점기는 천장에 붙어 아무것도 못 측정했다 |
| 라벨을 **새로 저술**할 때 | `scripts/label_authoring_check.py` | 요구가 gold 에서 성립하고 **대조군에서 불성립**하는가를 채점기의 정본 함수로 판정한다. 2026-09-03 에 후보 8건 중 **4건을 반려**했다 — 하나는 요구가 자기 gold 에 아예 없었고(판독 텍스트가 그 자리에서 줄바꿈해 인용부호가 끼었다 — 눈으로는 안 보인다), 셋은 다른 정책 문서에서도 성립했다. ⛔ 이 검사는 요구가 *답에 필요한지* 는 못 본다 — 그건 사람이 읽는다 |
| 얼린 팩에 문서를 **더할** 때 | `ko_eval_packb extend` | ⛔ `freeze` 를 부르지 마라 — 스냅샷 테넌트를 **지우고 다시 만든다**. 하나 더하려다 이미 얼린 문서 전부의 본문이 지금 것으로 바뀌고, 그 본문은 재서명 워크시트가 *무엇이 달라졌나* 를 보여 주는 유일한 재료다 |
| 서명한 **뒤** 스냅샷 | `ko_eval_packb align` | 그 서명이 다음 대조의 기준점이 되게 맞춘다. 규칙 한 줄: **지금 본문이 곧 서명된 본문인 문서만** 맞춘다 — 만료된 문서는 손대지 않는다 (스냅샷이 든 옛 본문이 다음 재서명자가 볼 전부다) |

**검색 경로의 사실 하나** — `search/hybrid.py` 는 **BM25 와 벡터 두 경로**를 RRF(`k=60`)로 융합한다.
그래프는 3-way 융합에 들어가지 않는다: `_diversify` 와 top-k 컷이 **끝난 뒤** `result.graph` 로
따로 붙는 보강이고, 히트 점수에 기여하지 않는다. (이 파일은 오랫동안 "3-way 병렬 + RRF" 라고
적고 있었다.)

---

## Canonical Resource Model (CRM)

새 모델은 `NexusResource` 를 상속한다. 필드 정의는 `models/resource.py` 가 정본이므로 여기 베끼지
않는다 — 사본을 두면 반드시 어긋나고, 어긋났다는 사실조차 조용하다.

지켜야 할 것 넷:

- **rid 는 `make_rid()` 로만 만든다.** 문자열로 직접 조립 금지. entity 는 `canonicalize_entity_name()`
  을 먼저 거친다 — 추출기를 갈아끼워도 rid 가 흔들리지 않게 하는 유일한 장치다.
- **검색·임베딩 텍스트는 `get_search_text()` 를 경유한다.** `chunk_text` 직접 사용 금지.
  1.0 은 `section_path` 접두사이고, 2.0 의 Contextual Enrichment 가 이 함수만 갈아끼우면 되도록
  격리해 둔 것이다.
- **모든 SELECT 에 정책 필터를 건다. 예외 없음.**

  ```sql
  AND tenant = %(tenant)s
  AND classification <= %(clearance)s
  AND is_quarantined = false
  AND status = 'active'
  ```

- **CRM 공통 필드를 생략한 테이블을 만들지 않는다.**

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
- 모든 SELECT 에 정책 필터 적용 (위 CRM 절)
- pgvector: `embedding <=> query_embedding` (cosine distance)
- BM25 검색 대상: `search_text` (GENERATED 컬럼), chunk_text 직접 검색 금지

### 에러 처리
- Ingestion 실패: 해당 문서만 skip, 나머지 계속. 실패 로그
- PII 감지: 즉시 quarantine. 절대 chunk 생성 금지
- Embedding 실패: **삼키지 말고 `index/embed.py:record_refusal()` 로 거부를 행으로 남긴다**(`embed_refusals`). 삼키면 그 청크는 벡터 경로에서 영구히 사라지고 아무도 모른다. 백엔드 메시지는 **요약하지 말고 그대로** 남긴다 — "왜 안 되는지" 가 곧 처방이다(`413 max_seq_length` 는 청킹을 고치라는 말이고, 인코딩 오류는 다른 처방이다). 기계가 낸 사실인 `embed_refusals` 와 사람이 이름을 걸고 포기한 `embed_waivers` 를 **섞지 않는다**. 거부 기록 자체가 실패해도 색인은 계속한다 — 진단이 진단 대상을 죽이면 안 된다.
- LLM 호출 실패: evidence snippet 은 그대로 제공하고, `llm_failed` 와 **안정적인** `llm_failure_reason`(`llm/failure.py`)을 붙인다. 서술이 없다고 검색 결과까지 버리지 않는다.
- 근거 0건: **LLM 을 아예 호출하지 않는다.** 고정 문장 + `abstained=True, abstain_reason="no_evidence"`. 근거가 없을 때 모델에게 물어보는 것 자체가 환각을 초대한다.
- DB 연결 실패: 503. partial result 반환 금지

### OTel 관련
- Raw trace는 Nexus DB에 절대 저장 금지. Tempo에 포인터만
- CALLS_OBSERVED rid: window를 rid에 넣지 않음. 같은 from→to = 같은 rid
- Service name resolution: peer.service → k8s metadata → reverse DNS → hash fallback

---

## 커맨드 · 환경변수

명령 목록은 [README](./README.md), 환경변수는 [`.env.example`](./.env.example) 이 정본이다.
여기 베끼지 않는다. 테스트는 `pytest tests/ -v`.

여기 남기는 것은 **한 번 실제로 데인 것** 하나뿐이다.

> ⚠ **쓰는 명령은 배포의 임베딩 세대가 설정된 곳에서 돌려야 한다.** 이 배포에서는 컨테이너 안이다
> (세대는 env 로 오고, 그 env 는 컨테이너에만 있다). 호스트 셸에서 그냥 `nexus ingest` 를 치면
> `config.yaml` 기본값 = 768/nomic 세대로 해석돼 **검색되지 않는 컬럼**에 적재된다.
> **2026-08-10 에 실제로 그렇게 됐다** (SPEC-nexus-generation-of-record).
>
> 컨테이너 없이 돌리는 배포라면 `NEXUS_EMBEDDING_MODEL`/`NEXUS_EMBEDDING_COLUMN` 을 같은 값으로
> export 한 셸에서 돌린다. 세대를 DB 에 선언해 두면 어긋난 실행은 **거부된다**:
>
> ```bash
> docker exec nexus-app nexus generation declare --tenant default >     --column embedding_1024 --model KURE-v1 --by <who>
> docker exec nexus-app nexus generation show
> ```
