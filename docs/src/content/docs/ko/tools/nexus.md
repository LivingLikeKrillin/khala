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
- **절 채움 — 검색은 문서를 고르고, 그다음 그 문서를 채운다** — 검색은 두 가지를 판정한다: *어느 문서인가*, 그리고 *그 안의 어느 절인가*. 실측 결과 앞은 신뢰할 만하고 뒤는 아니었다 — 질문과 정답 절이 어휘를 **하나도** 공유하지 않을 수 있고, 그러면 어떤 랭킹으로도 그 절에 도달하지 못한다. 그래서 한 문서가 문서당 상한을 꽉 채우면, 같은 문서의 남은 절을 **랭킹이 아니라 근거에** 더한다. Recall·1위는 바이트 단위로 동일하고 패킷만 커진다. 배포 설정에서는 켜져 있고 코드 기본값은 꺼짐이다 — 설정 없이 부르는 호출부가 DB 를 새로 건드리지 않게 하려는 것이다.
- **근거 적합도 — 시스템이 "제대로 못 찾았다"를 스스로 안다** — RRF 는 `1/(k + 순위)` 로 점수를 내므로 **순위를 담고 크기를 버린다.** 그래서 잘 맞은 질의와 코퍼스 밖 질의가 구별되지 않았다. 두 검색 경로는 정렬하려고 크기를 이미 계산하고 있었고, 이제 그것을 버리지 않는다. **둘 다** 약하면 서술 계약이 바뀐다 — 답변이 첫머리에 질문이 근거 범위 밖임을 말하고 짧게 끝낸다. **막지는 않는다**: 문턱이 틀렸을 때의 대가가 삼켜진 답이 아니라 간결함이 되도록 묶은 것이다.
- **문서 부채가 근거를 따라온다** — 인용된 문서가 대체(supersede)됐거나, 같은 제목의 활성 문서가 또 있어서 `[출처: 제목]` 인용이 **어느 쪽인지 못 가리키면** 답변이 그것을 안다. 결정론적으로 저장된 것만 여기 온다. 문서 간 **의미적 모순은 일부러 판정하지 않는다** — 그러려면 심판 모델이 필요하고 그 길의 근거는 나쁘다. 시스템은 모순을 서술할 수는 있어도 보증하지 않는다.
- **코드 앵커 — 문서가 부른 이름이 지금 코드에 있는가** — 적재가 청크마다 백틱 심볼을 코드 인덱스에 바인딩한다. 답변 시점에 패킷은 인용된 문단이 부른 이름 중 몇 개가 아직 존재하고 어느 것이 사라졌는지를 **앵커마다 조회하지 않고 집합 쿼리 하나로** 보고한다. `FooService` 가 삭제된 뒤에도 `FooService` 라고 말하는 문서가 조용히 권위를 갖는 일이 없어진다.
- **후속 질문은 보수적으로 고쳐 쓰거나, 아예 안 고친다** — "그럼 그건 언제부터야?" 에는 내용어가 없다. 대화 이력이 있으면 질의를 재작성하되 **허용된 변형은 넷뿐**이고(지시대명사 채우기·서식 요청 제거·사용자가 준 사실 채우기·소스 범위 제거), 원 질문은 **항상 별도 채널로 남겨** 재작성이 틀려도 바닥이 있다. 이력이 없으면 모델을 아예 부르지 않는다.
- **최신성은 보여주되 강제하지 않습니다** — 답변은 스니펫마다 타입별 TTL 대비 경과 경고를 답니다. 읽는 사람을 위한 라벨이며, **의도적으로** 랭킹이나 배제에 관여하지 않습니다.
- **정직한 부재** — 인용할 것이 없으면 모델을 아예 호출하지 않습니다. 근거가 없다는 고정 문장을 돌려주고, 응답 페이로드에도 그렇게 표시합니다.
- **저장소가 아니라 인덱스** — 원본은 Git과 Tempo에 있고, Nexus에는 파생 데이터(chunks·embeddings·graph edges)만 저장됩니다.

### 순위가 매겨진 뒤, 당신이 읽는 답이 되기까지

랭킹은 보이는 절반이다. 답을 믿을 만한가를 정하는 나머지 절반은 그 뒤에 있다: **한 곳**에서 독자가 근거를 판단하는 데 필요한 것을 전부 붙이고, **한 번**의 검증 패스가 모델의 출력을 실제로 건네진 근거에 대조한다.

<svg class="kh-fig" viewBox="0 0 580 358" role="img" aria-label="순위가 매겨진 히트에서 검증된 답변까지의 파이프라인. 히트가 단일 근거 패킷 조립점으로 들어가고, 거기서 스니펫·출처 등급·신선도·코드 앵커·문서 부채·채운 절이 붙는다. 그다음 근거 적합도 검사가 온다: 두 검색 경로가 모두 약하면 답을 막는 대신 서술 계약이 바뀌어 범위를 밝힌 짧은 답이 된다. 모델이 서술한 뒤, 코드가 모든 인용이 패킷에 해소되는지와 모든 숫자가 근거에 있는지를 검사한다. 해소되지 않은 인용은 숨기지 않고 따로 보고된다.">
  <rect class="kh-fig-box" x="195" y="14" width="190" height="26" rx="3"/>
  <text class="kh-fig-d" x="290" y="27" text-anchor="middle">순위 히트 · 문서당 상한</text>
  <path class="kh-fig-line" d="M290 40 L290 62"/>
  <text class="kh-fig-h" x="110" y="52">EVIDENCE PACKET</text>
  <text class="kh-fig-s" x="470" y="52" text-anchor="end">패킷 하나, 표면 넷</text>
  <rect class="kh-fig-surface" x="110" y="62" width="360" height="72" rx="3"/>
  <text class="kh-fig-d" x="126" y="82">스니펫</text>
  <text class="kh-fig-d" x="126" y="101">출처 등급</text>
  <text class="kh-fig-d" x="126" y="120">신선도</text>
  <text class="kh-fig-d" x="306" y="82">코드 앵커</text>
  <text class="kh-fig-d" x="306" y="101">문서 부채</text>
  <text class="kh-fig-d" x="306" y="120">채운 절</text>
  <path class="kh-fig-line" d="M290 134 L290 154"/>
  <rect class="kh-fig-box-acc" x="210" y="154" width="160" height="26" rx="3"/>
  <text class="kh-fig-rk" x="290" y="167" text-anchor="middle">근거 적합도?</text>
  <path class="kh-fig-line-acc" d="M370 167 L392 167"/>
  <text class="kh-fig-s" x="398" y="161">두 경로 다 약하면:</text>
  <text class="kh-fig-s" x="398" y="174">밝히고 짧게</text>
  <path class="kh-fig-line" d="M290 180 L290 200"/>
  <rect class="kh-fig-box" x="225" y="200" width="130" height="26" rx="3"/>
  <text class="kh-fig-d" x="290" y="213" text-anchor="middle">모델이 서술</text>
  <path class="kh-fig-line" d="M290 226 L290 248"/>
  <text class="kh-fig-h" x="140" y="238">VERIFY IN CODE</text>
  <text class="kh-fig-s" x="440" y="238" text-anchor="end">프롬프트가 아니라 코드가</text>
  <rect class="kh-fig-surface" x="140" y="248" width="300" height="52" rx="3"/>
  <text class="kh-fig-d" x="156" y="267">모든 인용이 패킷에 해소되는가</text>
  <text class="kh-fig-d" x="156" y="286">모든 숫자가 근거에 있는가</text>
  <path class="kh-fig-line-acc" d="M290 300 L290 318"/>
  <rect class="kh-fig-box-acc" x="205" y="318" width="170" height="26" rx="3"/>
  <text class="kh-fig-rk" x="290" y="331" text-anchor="middle">답변 + 인용</text>
  <text class="kh-fig-s" x="290" y="352" text-anchor="middle">해소되지 않은 인용은 숨기지 않고 따로 보고된다</text>
</svg>

이 단계의 두 성질은 그대로 적어 둘 값이 있다. 둘 다 결함을 치르고 산 것이기 때문이다:

- **모든 것이 한 곳에서 붙는다.** 네 표면이 이 패킷을 소비한다 — HTTP 엔드포인트 둘, 에이전트 프로토콜, CLI. 표면마다 따로 붙이던 시절에는 그중 하나가 조용히 빠졌고, 같은 질문에 사람과 에이전트가 다른 답을 받았다.
- **약한 근거는 서술을 바꾸지 답을 막지 않는다.** 적합도 판정은 **두** 경로가 모두 약할 때만 발동하고, 효과는 스스로 범위를 밝히는 짧은 답이다. 막는 설계였다면 틀린 문턱의 대가가 삼켜진 답이 되지만, 이렇게 묶으면 대가가 간결함이 된다. 문턱을 정한 측정과 그 한계는 [엔지니어링 로그](/ko/engineering-log/)에 있다.

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
