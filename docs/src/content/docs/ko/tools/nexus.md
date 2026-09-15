---
title: Nexus
description: 인용 가능한 출처에서만 답하고, 그 인용을 코드로 검증하는 검색 계층.
---

Nexus는 에코시스템의 지식 베이스입니다. 조직 내부 지식(문서·정책·설정)과 운영 사실(OpenTelemetry 트레이스)에 대한 질문에 **인용 가능한 근거가 있을 때만** 답합니다. 모든 답에는 신뢰도(confidence)와, 그 답을 떠받치는 source chunk 또는 trace로 돌아가는 링크가 붙습니다.

일반적인 RAG는 텍스트를 검색한 뒤 모델이 즉흥적으로 답하게 두므로, 근거가 있든 없든 그럴듯한 답을 만들어 냅니다. Nexus는 반대로 동작합니다. 무엇을 검색할 수 있고 그 답이 근거로 뒷받침되는지는 시스템이 판정하고, 모델은 이미 존재하는 근거 위에서 서술만 합니다. 인용할 출처가 없으면 답을 내지 않습니다.

한마디로: **근거 기반 답변을 위한 엔터프라이즈 검색 계층.** 코드 리뷰·트러블슈팅 에이전트를 위한 컨텍스트 계층으로, 추측이 아니라 실제 문서와 관측된 텔레메트리에서 일하도록 받칩니다.

<svg class="kh-fig" viewBox="0 0 580 384" role="img" aria-label="질의 'payment-service dependencies'에 대한 검색 트레이스. 두 검색기(BM25/mecab-ko, 벡터/pgvector)가 후보 청크를 점수화하고 RRF가 하나의 랭킹으로 통합한다. 2-hop 그래프 조회는 따로 돌며 점수에 기여하지 않고, 융합이 끝난 뒤 답변에 엣지로 덧붙는다. 결과: payment-service는 ledger·fx-rate에 의존, PIPELINE_SPEC.md 인용, 인용은 근거 패킷과 대조해 검증됨.">
<defs><marker id="nx-a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="kh-fig-ah" d="M0 0 L10 5 L0 10 z"/></marker></defs>
<text class="kh-fig-q" x="24" y="22">› payment-service dependencies?</text>
<text class="kh-fig-h" x="24" y="52">BM25 · MECAB-KO</text>
<text class="kh-fig-d" x="30" y="72">PIPELINE_SPEC</text>
<rect class="kh-fig-track" x="150" y="67" width="100" height="6" rx="3"/>
<rect class="kh-fig-bar" x="150" y="67" width="86" height="6" rx="3"/>
<text class="kh-fig-d" x="30" y="92">API_CONTRACT</text>
<rect class="kh-fig-track" x="150" y="87" width="100" height="6" rx="3"/>
<rect class="kh-fig-bar" x="150" y="87" width="44" height="6" rx="3"/>
<text class="kh-fig-h" x="24" y="122">VECTOR · PGVECTOR</text>
<text class="kh-fig-d" x="30" y="142">PIPELINE_SPEC</text>
<rect class="kh-fig-track" x="150" y="137" width="100" height="6" rx="3"/>
<rect class="kh-fig-bar" x="150" y="137" width="74" height="6" rx="3"/>
<text class="kh-fig-d" x="30" y="162">ledger.svc</text>
<rect class="kh-fig-track" x="150" y="157" width="100" height="6" rx="3"/>
<rect class="kh-fig-bar" x="150" y="157" width="58" height="6" rx="3"/>
<path class="kh-fig-line-acc" d="M250 72 C 296 72, 292 132, 320 132"/>
<path class="kh-fig-line-acc" d="M250 150 C 296 150, 302 132, 320 132"/>
<path class="kh-fig-line-acc" d="M320 132 L336 132" marker-end="url(#nx-a)"/>
<line class="kh-fig-rule" x1="24" y1="186" x2="250" y2="186"/>
<text class="kh-fig-h" x="24" y="208">GRAPH · 2-HOP</text>
<text class="kh-fig-d" x="30" y="228">payment→fx · payment→ledger</text>
<text class="kh-fig-s" x="30" y="246">점수 없음 — 융합 이후 덧붙음</text>
<path class="kh-fig-line-acc" d="M250 228 C 300 228, 330 236, 330 252" marker-end="url(#nx-a)"/>
<rect class="kh-fig-panel" x="336" y="44" width="212" height="176" rx="8"/>
<text class="kh-fig-h" x="354" y="66">RRF · BM25 + VECTOR</text>
<line class="kh-fig-rule" x1="354" y1="80" x2="530" y2="80"/>
<text class="kh-fig-rk" x="354" y="102">1</text>
<text class="kh-fig-d" x="376" y="102">PIPELINE_SPEC.md</text>
<text class="kh-fig-rk" x="354" y="126">2</text>
<text class="kh-fig-d" x="376" y="126">ledger.svc</text>
<text class="kh-fig-rk" x="354" y="150">3</text>
<text class="kh-fig-d" x="376" y="150">API_CONTRACT.md</text>
<path class="kh-fig-line-acc" d="M442 220 L442 252" marker-end="url(#nx-a)"/>
<rect class="kh-fig-panel" x="24" y="252" width="532" height="116" rx="8"/>
<text class="kh-fig-h" x="42" y="276">GROUNDED ANSWER</text>
<text class="kh-fig-verified" x="538" y="276" text-anchor="end">✓ CITED</text>
<line class="kh-fig-rule" x1="42" y1="290" x2="538" y2="290"/>
<text class="kh-fig-ans" x="42" y="313">payment-service → ledger, fx-rate</text>
<text class="kh-fig-s" x="42" y="333">documented + observed · no drift</text>
<text class="kh-fig-s" x="42" y="356">SOURCE</text>
<text class="kh-fig-d" x="96" y="356">PIPELINE_SPEC.md</text>
<text class="kh-fig-s" x="538" y="356" text-anchor="end">CONFIDENCE 0.92</text>
</svg>

## 핵심 개념

- **하이브리드 검색 (Hybrid Retrieval)** — BM25(mecab-ko 기반 형태소 분석 및 어휘 분리)와 pgvector(밀집 벡터 임베딩) 경로를 병렬 질의한 후 상호 순위 융합(RRF, Reciprocal Rank Fusion, `k=60`)으로 통합합니다. 융합 후 문서당 최대 청크 수 상한을 적용하여 특정 단일 문서로의 편중을 방지합니다.
- **그래프 맥락 확장 (Graph Contextualization)** — 2-hop 엔티티 탐색은 RRF 융합 이후 수행되며, 검색 히트 점수 계산에 관여하지 않고 독립된 인접 관계 엣지로 답변 컨텍스트에 추가됩니다.
- **인용 및 수치 검증 (Citation & Numeric Verification)** — LLM이 생성한 인용 표기(`[S1]`, `[T1]`)를 전달된 근거 패킷과 바이트 단위로 대조 검증합니다. 근거와 부합하지 않는 인용은 `unverified`로 분류하여 클라이언트에 명시적으로 전달하며, 답변 본문 내 수치 역시 근거 패킷 내 수치와의 일치 여부를 검증합니다.
- **근거 기반 엣지 (Evidence-backed Edges)** — 명시적인 원천 근거(Evidence)가 확보된 관계에 대해서만 지식 그래프 엣지를 생성 및 유지합니다.
- **이중 지식 계층 (Designed vs Observed)** — 정적 설계 문서 기반 관계와 런타임 OTel 트레이스 관측 관계(`CALLS_OBSERVED`: 호출 빈도, 오류율, 레이턴시)를 병렬 관리합니다.
- **설계-관측 불일치 분석 (Design-Observed Diff)** — `doc_only`(문서에만 기술되고 미관측), `observed_only`(실행 관측되었으나 미문서화), `conflict`(설계와 관측 불일치) 상태를 자동 식별합니다.
- **기본 차단 보안 모델 (Default-Deny Security)** — 개인식별정보(PII) 및 보안 자격증명 감지 시 즉시 격리(Quarantine)하고 색인 및 검색 대상에서 영구 제외합니다. 모든 질의는 접근 권한 분류(`PUBLIC < INTERNAL < RESTRICTED`)에 따라 강제 필터링됩니다.
- **출처 등급 체계 (Provenance Tier)** — 인간 작성 청크(`authored`)와 비전 모델 추출 청크(`machine_read`) 간의 신뢰성 등급을 명시적으로 구분하며, 해당 메타데이터를 프롬프트, API 페이로드, 웹 UI 전반에 전파합니다.
- **색인 세대 무결성 (Index Generation Invariant)** — 임베딩 모델 식별자, 벡터 차원, 저장 컬럼을 하나의 세대 레코드로 관리합니다. 런타임 설정이 데이터베이스에 선언된 세대와 불일치할 경우 데이터 수집(Ingest)을 사전에 차단합니다 (기본값: `nomic-embed-text`, 768차원; 환경별 `KURE-v1`, 1024차원 지원).
- **섹션 보강 (Section Completion)** — 검색 랭킹에서 특정 문서의 청크가 상한을 충족한 경우, 어휘 불일치로 누락될 수 있는 인접 중요 절을 랭킹 점수와 무관하게 근거 패킷에 추가 결합하여 문맥 연속성을 보장합니다.
- **정정 문서 동시 조회 (Reconciliation Path)** — 대체(Supersede) 관계에 있는 최신 개정 문서가 길이 또는 키워드 빈도 차이로 검색 하위에 머무는 현상을 방지하기 위해, 1차 근거 식별자를 기반으로 2차 정정 확인 조회를 수행하여 최신 정정 문서를 근거에 강제 포함합니다.
- **설계-계획 쌍 확장 (Design-Plan Pairs)** — 설계 사양(Why/What)과 구현 계획(Files/Order)이 분리된 문서 구조에서 질문이 두 영역을 포괄할 때, 파일 식별자 매핑 규칙에 따라 짝 문서를 근거 패킷에 자동 보강합니다.
- **코드 불변식 병치 표기 (Code Claims Binding)** — 문서에 명시된 제약 조건이 소스코드 심볼에 매핑되어 있는 경우, 질의 시점에 소스코드의 실제 상수 값(`@Size`, 유효성 검증 어노테이션 등)을 함께 조회하여 문서의 기술 값과 나란히 표기합니다.
- **근거 적합도 기반 서술 제약 (Evidence Adequacy Contraction)** — 두 검색 경로의 점수가 모두 임계치 미만인 경우, 질의에 대한 허위 생성을 억제하기 위해 근거 범위 제한을 안내하는 간결한 응답 계약으로 자동 전환합니다.
- **문서 부채 상태 노출 (Document Debt Signaling)** — 인용 대상 문서가 대체되었거나 동명 문서 간 식별 모호성이 존재하는 경우 해당 상태를 페이로드에 플래그로 명시합니다.
- **코드 앵커 무결성 검증 (Code Anchors Verification)** — 청크 내 백틱 심볼 식별자를 소스코드 색인과 조인하여, 코드베이스에서 삭제된 심볼을 인용하는 문서의 참조 무결성 만료를 실시간으로 탐지합니다.
- **후속 질의 정규화 (Multi-turn Query Rewriting)** — 대화 맥락이 존재하는 경우 지시대명사 해소, 서식 제거, 사용자 제공 사실 반영, 범위 한정의 엄격한 4대 규칙에 한해서만 질의를 재작성하며 원본 질의를 항상 유지합니다.
- **신선도 지표 (Freshness TTL)** — 문서 유형별 유효 기간(TTL) 초과 여부를 경고 라벨로 노출하며 랭킹 임의 조작은 배제합니다.
- **결정론적 기각 (Deterministic Abstention)** — 유효 근거 패킷이 확보되지 않은 경우 LLM 생성을 호출하지 않고 고정된 기각 응답을 반환합니다.
- **파생 색인 저장소** — 원천 소스코드는 형상관리(Git) 및 원격 저장소에 영속화되며, Nexus에는 파생 색인(청크, 임베딩, 지식 그래프 엣지)만 보관됩니다.

### 근거 패킷 구성 및 검증 파이프라인

검색 결과의 순위 결정 이후, 답변의 신뢰성을 담보하기 위해 단일 근거 패킷 조립 및 런타임 코드 검증 게이트를 순차 실행합니다.

<svg class="kh-fig" viewBox="0 0 580 358" role="img" aria-label="순위화된 검색 히트에서 검증된 답변 생성까지의 파이프라인: 단일 근거 패킷 구성(스니펫, 출처 등급, 신선도, 코드 앵커, 문서 부채, 섹션 보강), 근거 적합도 판정, 모델 서술, 코드 레벨 인용 및 수치 검증 단계로 진행됨.">
  <rect class="kh-fig-box" x="195" y="14" width="190" height="26" rx="3"/>
  <text class="kh-fig-d" x="290" y="27" text-anchor="middle">순위 히트 · 문서당 상한</text>
  <path class="kh-fig-line" d="M290 40 L290 62"/>
  <text class="kh-fig-h" x="110" y="52">EVIDENCE PACKET</text>
  <text class="kh-fig-s" x="470" y="52" text-anchor="end">단일 근거 패킷 인터페이스</text>
  <rect class="kh-fig-surface" x="110" y="62" width="360" height="72" rx="3"/>
  <text class="kh-fig-d" x="126" y="82">스니펫</text>
  <text class="kh-fig-d" x="126" y="101">출처 등급</text>
  <text class="kh-fig-d" x="126" y="120">신선도</text>
  <text class="kh-fig-d" x="306" y="82">코드 앵커</text>
  <text class="kh-fig-d" x="306" y="101">문서 부채</text>
  <text class="kh-fig-d" x="306" y="120">보강된 섹션</text>
  <path class="kh-fig-line" d="M290 134 L290 154"/>
  <rect class="kh-fig-box-acc" x="210" y="154" width="160" height="26" rx="3"/>
  <text class="kh-fig-rk" x="290" y="167" text-anchor="middle">근거 적합도 판정</text>
  <path class="kh-fig-line-acc" d="M370 167 L392 167"/>
  <text class="kh-fig-s" x="398" y="161">경로 신뢰도 미달 시:</text>
  <text class="kh-fig-s" x="398" y="174">제약적 간결 응답</text>
  <path class="kh-fig-line" d="M290 180 L290 200"/>
  <rect class="kh-fig-box" x="225" y="200" width="130" height="26" rx="3"/>
  <text class="kh-fig-d" x="290" y="213" text-anchor="middle">모델 답변 생성</text>
  <path class="kh-fig-line" d="M290 226 L290 248"/>
  <text class="kh-fig-h" x="140" y="238">VERIFY IN CODE</text>
  <text class="kh-fig-s" x="440" y="238" text-anchor="end">결정론적 코드 검증</text>
  <rect class="kh-fig-surface" x="140" y="248" width="300" height="52" rx="3"/>
  <text class="kh-fig-d" x="156" y="267">모든 인용의 패킷 내 해소 여부</text>
  <text class="kh-fig-d" x="156" y="286">생성된 수치의 근거 일치 여부</text>
  <path class="kh-fig-line-acc" d="M290 300 L290 318"/>
  <rect class="kh-fig-box-acc" x="205" y="318" width="170" height="26" rx="3"/>
  <text class="kh-fig-rk" x="290" y="331" text-anchor="middle">검증 완료 답변 및 인용</text>
  <text class="kh-fig-s" x="290" y="352" text-anchor="middle">미해소 인용은 unverified 메타데이터로 분리 보고</text>
</svg>

- **단일 패킷 조립 원칙**: HTTP REST API, MCP 서버, Slack 봇, CLI가 동일한 `EvidencePacket` 구조체를 소비하여 인터페이스 간 응답 불일치를 차단합니다.
- **단계적 응답 제약**: 검색 품질이 기준 미만인 경우 무조건적 차단 대신 답변 범위를 한정하는 축약 응답 계약을 적용하여 시스템 가용성과 응답 정확성의 균형을 유지합니다.

## 실행 및 배포

Docker Compose 환경에서 실행됩니다. 기본 프로파일은 PostgreSQL, Ollama, FastAPI 핵심 애플리케이션으로 구성되며, OpenTelemetry 분산 추적 파이프라인은 옵트인으로 활성화할 수 있습니다.

```bash
# 1. 환경 설정
git clone https://github.com/LivingLikeKrillin/khala.git
cd khala
cp nexus/.env.example nexus/.env

# 2. 컨테이너 기동 및 스키마 마이그레이션
task up

# Taskfile 미사용 시 직접 실행:
#   docker compose up -d --wait
#   docker compose exec -T nexus-app python -m scripts.migrate
```

- 웹 인터페이스: `http://localhost:8000`
- 문서 수집(Ingest): `docker compose exec nexus-app nexus ingest ./docs`
- 텔레메트리 프로파일 활성화: `docker compose --profile observability up -d`
- 서비스 갱신: `task update` / 중지: `task down`
