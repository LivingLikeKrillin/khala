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

- **하이브리드 검색** — 두 검색기를 병렬 실행하고 RRF(Reciprocal Rank Fusion, `k=60`)로 통합합니다: 한국어 형태소(mecab-ko, 조사·어미 정확 분리) 기반 BM25와 pgvector 벡터 검색. 융합 뒤에는 문서당 상한을 걸어 한 파일이 결과를 도배하지 못하게 합니다.
- **그래프는 랭킹이 아니라 맥락** — 그래프 라우트에서 엔티티 2-hop 탐색이 돌지만, 이는 **융합이 끝난 뒤**에 일어나며 히트 점수에 전혀 기여하지 않습니다. 탐색 결과는 랭킹에 섞이지 않고 답변 옆에 엣지로 반환됩니다.
- **인용은 믿지 않고 검증합니다** — 모델에게 인용을 요구한 뒤, 그 인용이 실제로 건네진 근거 패킷과 대조해 **코드로** 검사됩니다. 해소되지 않는 인용은 출처인 척 통과하는 대신 `unverified`로 따로 보고됩니다. 답변 속 숫자도 같은 방식으로 검사합니다.
- **근거 기반 엣지** — 근거(evidence) 없이는 어떤 관계(edge)도 존재하지 않습니다.
- **이중 지식 계층 — 설계(Designed) vs 관측(Observed)** — 설계 문서에서 추출한 관계와 실제 트레이스에서 관측된 관계(`CALLS_OBSERVED`: 호출 수·에러율·지연)를 나란히 둡니다.
- **설계-관측 diff** — `doc_only`(문서엔 있으나 관측 안 됨), `observed_only`(관측되나 미문서화), `conflict`(둘 다 있으나 불일치)를 자동 탐지합니다.
- **Default-deny 보안** — PII/시크릿 감지 시 즉시 quarantine, 인덱싱에서 제외하고 검색 결과에 절대 포함하지 않습니다. 모든 쿼리는 분류(`PUBLIC < INTERNAL < RESTRICTED`)로 필터링됩니다.
- **출처 등급(provenance tier)** — 사람이 쓴 청크와 모델이 스크린샷에서 읽어낸 청크는 같은 종류의 근거가 아닙니다. 기계 판독 텍스트는 그렇게 표시되고, 그 표시가 프롬프트·API 응답·웹 UI까지 그대로 따라갑니다. 추출물이 조용히 저술된 정책 행세를 하지 못하게 하는 장치입니다.
- **선언된 인덱스 세대** — 임베딩 모델·차원·벡터 컬럼은 하나의 세대로 함께 움직이며 DB에 append-only로 선언됩니다. 실행 중인 설정이 선언된 세대와 다르면 **문서를 한 건도 수집하기 전에** 적재가 거부됩니다. 이 게이트가 막는 실패는 *문서화된 명령이 아무도 검색하지 않는 컬럼에 조용히 적재하는 것*입니다. 리포 기본값은 `nomic-embed-text`(768차원)이고, KURE-v1(1024차원) 세대를 배포별로 선택할 수 있습니다.
- **최신성은 보여주되 강제하지 않습니다** — 답변은 스니펫마다 타입별 TTL 대비 경과 경고를 답니다. 읽는 사람을 위한 라벨이며, **의도적으로** 랭킹이나 배제에 관여하지 않습니다.
- **정직한 부재** — 인용할 것이 없으면 모델을 아예 호출하지 않습니다. 근거가 없다는 고정 문장을 돌려주고, 응답 페이로드에도 그렇게 표시합니다.
- **저장소가 아니라 인덱스** — 원본은 Git과 Tempo에 있고, Nexus에는 파생 데이터(chunks·embeddings·graph edges)만 저장됩니다.

## 빠른 시작

Docker Compose 스택으로 돕니다. 기본은 **핵심 컨테이너**(PostgreSQL + Ollama + FastAPI 앱)만 뜨고, OTel 관측 파이프라인은 옵트인입니다. 아래 `task` 한 줄은 내부 `docker compose` 명령을 감쌉니다(원시 명령 병기).

사전 준비: Docker Desktop · (선택) [go-task](https://taskfile.dev) · (선택) LLM 답변용 Anthropic API 키.

```bash
# 1. 클론 & 설정
git clone https://github.com/LivingLikeKrillin/khala.git
cd khala
cp nexus/.env.example nexus/.env        # (선택) nexus/.env 에 ANTHROPIC_API_KEY 설정 시 LLM 답변 생성

# 2. 기동 — 컨테이너 + DB 마이그레이션 + 모델 자동 pull, 한 줄
task up

# Task 없으면 그 세 가지를 직접 (nexus/ 에서):
#   docker compose up -d --wait                                  # 컨테이너 + 모델 자동 pull
#   docker compose exec -T nexus-app python -m scripts.migrate   # ← 빠뜨리면 소스 콘솔·문서 관리가 깨진다
```

→ `http://localhost:8000` 에서 채팅으로 질문(근거와 함께 답). 문서 적재: `docker compose exec nexus-app nexus ingest ./docs`. 웹 UI 사용법은 **[Nexus 웹 사용 가이드](/ko/tools/nexus-web/)** 참고.

```bash
# 업데이트 / 정지
git pull && task update    # 이미지 재빌드·재기동 + DB 마이그레이션 적용
task down                  # 정지 (또는: docker compose down)
```

OTel 관측(trace 집계)이 필요할 때만 옵트인: `docker compose --profile observability up -d`.

전체 명령어·API 레퍼런스는 영어 페이지([Nexus](/tools/nexus/)) 또는 [소스 저장소 README](https://github.com/LivingLikeKrillin/khala)를 참고하세요.
