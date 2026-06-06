# 도메인 불변식·값 거버넌스 (Khala 확장) — 설계 문서

> 작성일: 2026-06-06
> 상태: Draft (브레인스토밍 합의 통합)
> 위치: Khala 에코시스템 확장 (#17, 구 "도메인 스토리텔링 MCP")

---

## 0. 한 줄 요약

서비스 전체에 걸친 **용어·액터·객체(개념)의 이름을 고정·추적**하고, 그 개념에 매달린 **도메인 불변식·값·요구의 현재 상태를 사람(특히 비엔지니어 기획자)과 AI가 근거 기반으로 조회·검증**할 수 있게 하는 시스템. **Khala의 확장**으로 구현한다.

---

## 1. 문제와 맥락

### 1.1 진짜 고통

개발·운영 단계의 기획+개발 합동 회의에서 **시스템의 전제조건(불변식)이 수시로 건드려진다.** 새 기능 논의, 정책 변경, 한도 조정마다 암묵적으로 불변식을 만지는데:

- 기획자(비엔지니어)는 **현재 전제조건이 무엇인지 빠르게 확인할 방법이 없다.** 코드를 못 읽으니 엔지니어를 붙잡거나, 낡았을지 모르는 Notion을 믿는다.
- 그 결과 **잘못된 전제 위에 의사결정이 쌓인다.**

기획자가 실제로 묻는 질문의 형태:
- "우리 준회원은 지금 플레이리스트를 몇 개 가질 수 있죠?" (현재 **값**)
- "파티룸 재생곡 제한 시간은 얼마로 설정되어 있죠?" (현재 **값**)
- "강퇴된 크루는 같은 방에 재입장 못 하게 돼 있나요?" (**보장 여부**)
- "승격 시 프로필 설정 강제가 들어갔나요?" (**반영 여부**)

### 1.2 원래 의도 (북극성)

"도메인 스토리텔링"을 고수했던 이유는 **서비스 전체에 걸쳐 쓰이는 용어·액터·객체의 이름을 고정하고 추적하기 쉬운 상태**를 만들고 싶었기 때문이다. 즉 진짜 목표는 **유비쿼터스 언어(ubiquitous language)의 단일 진실원천**이고, 불변식·값은 그 위에 매달리는 사실이다.

---

## 2. 무엇이 아닌가 (선행 리서치로 폐기한 것)

deep-research(소스 26개, 적대적 검증)와 사전 타당성 분석으로 다음을 **명시적으로 폐기**한다:

| 폐기 항목 | 이유 |
|---|---|
| 도메인 스토리 → 불변식 **자동 도출** | 귀납 문제. 유한 예시(∃)에서 보편 제약(∀)을 건전하게 도출 불가. codecentric 실험이 현장 확증("스토리는 불변식을 놓친다") |
| 도메인 스토리 = **자동 동기화 진실원천** | 선행 사례 없음. DS는 본래 일회성 스냅샷 기법 |
| spec→code **자동 커버리지 %** | 가장 어려운 D. 거짓 확신 위험 |
| **SLO·동시성·분산합의** 불변식 | 엔지니어 내부 관심사. 기획자와 공유하는 사용자 스토리 불변식이 아님 (범위 밖) |
| 모호한 **목표를 불변식으로 취급** | "신선하게 느껴져야"는 목표지 불변식이 아님. 기준이 정의돼야 불변식 |

### 핵심 리서치 결론

- **기술 블록은 검증됨** (실행단언/형식기법이 코드와 동기화 유지 — TLA+@AWS, PBT@Jane Street).
- **통합 전체는 미검증**, 그러나 반증된 것도 아님.
- **진짜 실패 모드는 기술이 아니라 조직·유지비(shelfware)** — 수동 RTM은 "생성 직후 대부분 쓸모 상실".
- **중요도 기반 차등 추적은 검증된 완화책** (VBRT, Ramesh low/high-end taxonomy).
- **LLM-as-judge는 턴키 결정론 검증기가 아님** — 멀티샘플 필수, 단독샷 금지, 결정론 oracle이 gating해야 신뢰.

---

## 3. 핵심 원칙

1. **개념이 척추, 사실은 매달린다.** 개념 레지스트리(용어/액터/객체)가 토대. 값·불변식·요구는 개념을 참조하는 사실.
2. **신뢰성 = 캘리브레이션(정직함).** "항상 정답"은 불가능. 달성 가능하고 충분한 정의: **시스템이 결코 거짓말하지 않는다 — soft하거나 낡은 답을 hard한 답인 척 내놓지 않는다.** (Notion이 못 하는 것이 바로 이것.)
3. **복사하지 말고 가리켜라 (anti-shelfware).** 값·정의를 복사 저장하면 썩는다. 권위 있는 출처(코드 상수, 문서 chunk)를 *가리켜* 현재값을 읽고 신선도를 표기.
4. **System decides, LLM narrates.** (Khala 원칙 계승) 분류·검증·경로 판정은 코드(결정론). LLM은 제안·요약만, 최종 권한 없음.
5. **Grounded only.** 근거 없는 주장·관계는 존재하지 않는 것으로 취급.

---

## 4. 아키텍처 — Khala 확장

### 4.1 Khala가 이미 제공하는 것 (재사용)

| 필요 기능 | Khala의 기존 자산 |
|---|---|
| 개념 레지스트리(척추) | `entities` (type=`Term`, `aliases[]`, `description`) |
| 근거 바인딩 **메커니즘** | Evidence 모델(`rid→rid`) + "Evidence 없는 edge 금지" — *패턴만 재사용. 코드앵커 자체는 §4.2 net-new* |
| 드리프트 **태깅 메커니즘** | `quality_flags`(`stale_doc`/`conflict`/`doc_only`) 태깅 방식 — *기존은 문서↔트레이스용. claim↔code diff는 §4.2 net-new* |
| 신뢰성=캘리브레이션 | "Grounded answers only" + "System decides, LLM narrates" + quarantine |
| 기획자 자연어 조회 | Hybrid Search + 근거 답변 + **Web UI/Slack/MCP (이미 Done)** — *검색·조회 표면만 재사용. claim 답변 템플릿(§10)은 net-new* |
| 통합 모델 | CRM — 모든 rtype 동일 규칙 (문서/청크/그래프/OTel/도메인 스토리) |

### 4.2 #17이 추가하는 것 (net-new)

1. **신규 rtype `claim`** — CRM enum(`document|chunk|entity|edge|observed_edge|evidence`)에 없음 → **enum 확장**. `kind` 필드로 `goal|invariant|requirement` 세분(rtype 자체는 단일 `claim`). value-bearing은 `value` 하위필드로.
2. **★ 코드 소스 (가장 중요한 net-new).** CRM `source_kind` enum(`git|wiki|file|otel|manual`)에 **`code` 추가**. 코드 상수·설정·강제 메커니즘을 파싱해 Resource로 인덱싱하고, 각 코드 심볼의 **(파일경로+심볼명) 단위 hash**를 저장 → commit 간 hash diff로 변경/stale 판정. Khala는 코드를 인덱싱하지 않으므로 추출기·hash 저장 전부 신규. (Khala 드리프트는 문서↔트레이스이지 문서↔코드상수가 아님.)
3. **claim↔code diff** — claim의 `value.source`/`enforcement` 링크가 가리키는 코드 심볼 hash가 `last_verified.commit` 이후 바뀌면 claim에 `quality_flags`(예: `claim_code_drift`) 태깅. 별도 엔진 없이 Khala diff 패턴(SQL+flag) 재사용. (기존 design↔observed와 다른 새 차원.)
4. **기획문서 → claim 전처리기** — 기존 ingestion 위에 claim 추출 + 조작화 게이트 + 사람 큐레이션.
5. **기획자 질문 패턴/답변 템플릿** — 값/보장/반영 3종 질문에 대한 캘리브레이션 답변.

### 4.3 결합 방식

**Khala 내부 확장** (선택됨). CRM에 rtype 추가, 새 source/diff를 Khala 파이프라인에 통합. entities/evidence/grounding/검색/MCP를 그대로 재사용. (Probe식 외부 소비 아님 — 중복 회피, 가장 타이트한 통합.)

---

## 5. 데이터 모델

### 5.1 척추: 개념 (= Khala entity, type=Term 확장)

기존 `entities`를 그대로 사용하되 도메인 개념(액터/객체/용어)을 1급으로:
- `name` (canonical), `aliases[]`, `description`(근거 chunk에 grounding)
- 연결된 **코드 심볼**(이 개념을 표현하는 클래스/엔티티) — *net-new: §4.2 `code` source가 선행돼야 함. 기존 entity는 문서 추출 기반이라 코드 심볼 링크 없음*
- 사용처 추적: 심볼+별칭이 코드·문서·claim 전반에서 참조되는 위치

### 5.2 매달린 사실: claim

```yaml
# 예: 값을 품은 불변식 (가장 흔한 질문 유형)
id: associate-max-playlists
rtype: claim
kind: invariant            # goal | invariant | requirement
concepts: [준회원, 플레이리스트]   # 척추 개념 참조
statement: "준회원은 플레이리스트를 최대 N개 가질 수 있다"
value:                     # value-bearing: 복사 말고 가리킴 (claim-로컬 하위필드)
  source: "PlaylistPolicy.ASSOCIATE_MAX_PLAYLISTS"
  ref_kind: code_constant  # code_constant|config_key|db_default — Resource의 CRM source_kind=code 와 구분되는 claim-로컬 분류
criticality: core          # core | peripheral   (생명주기 축1)
activity: active           # active | dormant | archived  (축2)
status: held               # invariant: held|violated|unverified
                           # requirement: reflected|partial|not-reflected|unverified
confidence: high           # high(결정론) | medium(LLM멀티샘플+사람확정) | low(수동/단일)
enforcement:               # boolean 불변식의 "조치 반영" 검증
  mechanism: "PlaylistPolicy 단일 진입 + count 제약"          # ⓐ 강제 메커니즘 존재
  no_bypass_check: "ArchUnit: 플레이리스트 생성은 PlaylistService만"  # ⓑ 우회 없음
  correctness_check: "PlaylistPolicyTest#associateLimit"      # ⓒ 로컬 정확성
  residual_risk: "동시 생성 레이스는 통합테스트로만 커버"        # 잔여 정직 표기
last_verified: { commit: a1b2c3d, date: 2026-06-06 }
owner: "@backend-lead"     # CRM 공통 owner 재사용. claim에 한해 큐레이션 게이트에서 비-"unknown" 강제 (소유권=생존변수)
```

### 5.3 필드 설계 의도

| 필드 | 역할 | 근거 |
|---|---|---|
| `concepts` | 척추 개념 참조 | 사실은 개념에 매달린다 |
| `value.source` | 현재값을 *가리킴* | anti-shelfware: 복사 안 함 |
| `kind` | goal/invariant/requirement | 타입 체계(§6) |
| `confidence` | 어느 티어가 매긴 상태인가 | 결정론=high, LLM멀티=medium, 수동=low |
| `criticality`×`activity` | 2축 생명주기 | 축1 검증됨(VBRT), 축2 우리 베팅 |
| `enforcement.{ⓐⓑⓒ}` | "조치 반영" 검증 분해 | 증명 대신 "조치 반영+우회없음+로컬정확성" |
| `residual_risk` | 동시성 등 잔여 | 숨기지 않고 표기 |
| `last_verified.commit` | 신선도 | code 변경 대비 stale 판정 |
| `owner` | 책임 주체 **필수** | shelfware의 진짜 원인은 소유권 부재 |

---

## 6. 타입 체계와 조작화 게이트

```
목표(goal)            "신선하게 느껴져야"          ← 술어 없음. 불변식 아님. 검증 대상 아님.
   │ 조작화(operationalize): 기준을 정의
   ▼
불변식(가정)          "최근 20곡 내 반복 없음"      ← 정확한 술어. 체크 없음 → confidence: low
   │ 집행(write check)
   ▼
불변식(집행됨)        위 술어를 CI 단언으로          ← confidence: high
```

- `goal`은 1급 타입이되 **명시적으로 검증 안 함.** AI가 "이건 목표지 보장이 아님"을 분명히 답함.
- **조작화 강제:** 모호한 것을 `invariant`로 등록하려 하면 "기준(술어)을 정의하라"고 유도/거부. *이 강제가 모호한 목표의 불변식 위장을 막는 핵심 가치.*
- `goal → invariant` 조작화 관계를 edge로 기록 ("신선함 목표는 이 3개 불변식으로 조작화됨").
- "체크 없는 불변식"은 *불변식이 아닌 게 아니라* **아직 검증 안 된 가정**(confidence: low). 단 "보장됨"으로 취급하면 거짓말.

---

## 7. 검증 티어

> 검증 대상은 "속성 증명"이 아니라 **"조치 반영 ⓐ + 우회없음 ⓑ + 로컬정확성 ⓒ", 잔여(동시성)는 정직 표기.**

| 티어 | 누가 상태 기록 | confidence | 신선도 |
|---|---|---|---|
| ① 결정론 | CI 스크립트(테스트/ArchUnit/상수읽기 통과) | high | 매 CI 자동 갱신 → 항상 fresh |
| ② LLM보조 | AI 멀티샘플 *제안* → 사람 확정 시 기록 | medium | code_links 변경 시 stale |
| ③ 수동 | 사람 직접 단언 | low | code_links 변경 시 stale |

### 값 조회 (가장 흔하고 가장 신뢰 높음)

`value.source`가 코드 상수/repo 설정 → **결정론적으로 현재값 읽음.** "준회원 현재 5개 (PlaylistPolicy, 오늘 커밋 기준)". 증명도 LLM도 불필요. 드리프트 0.

### 신선도 판정 (시간 아니라 코드 변경)

```
stale = tier ≠ deterministic  AND  code_links/value.source 중 하나라도 last_verified.commit 이후 변경됨
```

> 변경 판정은 §4.2-2의 **(파일경로+심볼명) hash diff**로 한다. 그리고 **값 조회 답변은 조회 시점에 `value.source`를 재읽기**하므로 항상 fresh다 — 캐시할 경우엔 조회 시 hash 재확인 필수(미확인 캐시는 stale 가능). 이 "조회 시 재실행" 전제가 §11 "드리프트 0" 주장의 근거다.

### "core인데 비결정론" 자동 플래그

core는 항상 검증돼야 하나 모든 core가 실행단언화 가능하진 않음. → `criticality:core + tier≠deterministic` 조합을 위험으로 플래그하고 **사람이 판정 분기**: (a) 단지 체크 미작성 → 작성하라, vs (b) 의미·한계상 결정론 불가 → 한계로 인정·표기. *(이는 티어가 아니라 판정 라벨. confidence 티어는 high/medium/low 셋뿐.)*

---

## 8. 생명주기 · 시즌 스코핑

2축 (직교):

| 축 | 값 | 검증 정책 |
|---|---|---|
| 중요도 | core / peripheral | **core는 시즌 무관 항상 검증** |
| 활성도 | active / dormant / archived | active=고밀도 유지, dormant=조회만 |

- **휴면 ≠ 삭제.** 휴면 claim도 조회되되 `마지막 검증: N시즌 전 — 신선도 낮음` 배지. (회의의 "그거 반영됐나요?"는 휴면 기능 질문일 때가 많음.)
- **working-set 스코핑**으로 유지비 폭발(shelfware) 방지: core 상시 + active 고밀도 + 나머지 휴면.
- 시즌 경계는 **기존 스프린트/릴리스 주기에 얹는다** (새 의식 만들지 않음).

---

## 9. 입력: 기획문서 → claim 전처리

```
[기획문서] (산문·사용자스토리·회의록)
   ▼ ① 추출    LLM이 후보 주장 식별 (멀티샘플)
   ▼ ② 분류    goal | invariant | requirement
   ▼ ③ 조작화 게이트   모호 → "기준 정의하라" 강제
   ▼ ④ 연결 제안   concept ↔ 강제조치/코드(ⓐⓑⓒ) 매핑을 LLM이 제안
   ▼ ⑤ 큐레이션(사람)   제안된 claim diff를 검토·수정·승인  ← 필수 관문
   ▼ [Khala claim store] → 검증 → 조회
```

### 정직한 한계 (프로젝트 생사가 여기)

1. **추출 신뢰도** — LLM은 쓰인 것만. 멀티샘플+사람검토 필수.
2. **완전성 함정 (가장 중요)** — 가장 위험한 불변식은 문서에 없고 대화에만 있음(codecentric 확증). 전처리 = 초안, 빈틈은 사람이 채움.
3. **모호한 목표 홍수** — 조작화 게이트가 대량 발화 → working-set 스코핑(core·active만 조작화)이 안전판.

---

## 10. 출력: 기획자 자연어 조회

Khala의 기존 Web UI/Slack/MCP를 통해. 3종 질문에 **캘리브레이션 답변**:

| 질문 유형 | 예 | 답하는 법 | 신뢰 |
|---|---|---|---|
| 현재 **값** (최다) | "준회원 플레이리스트 몇 개?" | `value.source` 읽기 | 🟢 결정론 |
| **보장** 여부 | "강퇴 크루 재입장 막혀요?" | 조치 ⓐⓑⓒ 검증 | 🟡 검증+잔여 |
| **반영** 여부 | "프로필 설정 강제 들어갔어요?" | requirement 상태 | 🟡/🟠 티어별 |
| 개념 **정의** | "준회원이 뭐예요?" | entity.description **grounding** + 출처 인용 + stale 플래그 | 🟢 캘리브레이션 |

→ 모든 답에 `confidence` + `freshness` 동봉. "준회원 5개 (확실: 코드 상수, 오늘)" vs "정의는 2시즌 전 작성, 코드 일치 미확인"을 *구분해서* 제공. **이 구분이 곧 신뢰.**

---

## 11. MVP 쐐기

**값 조회(value-bearing claim의 현재값)부터.** 가장 높은 가치·가장 낮은 위험·결정론적.

- pfplay 핵심 개념 8~10개를 Khala entity로 + 코드앵커.
- 그 위에 value-bearing claim 5~10개 (실제 상수: 준회원 플레이리스트 한도, 재생곡 제한시간 등).
- `code` source 추출기 최소 구현 (상수 읽기).
- Khala MCP/Web으로 기획자가 자연어 조회.

**검증할 가치 가설:** *"기획자가 '준회원 플레이리스트 몇 개?'를 이걸로 묻고, 코드앵커 답을 낡은 Notion보다 믿고 쓰는가."* (= 리서치가 지목한 핵심 미검증 #4. 단 사용자는 "신뢰성만 보장되면 쓴다"고 가치 판단 내림.)

**합격선(정량):** 기획자 **≥3명 × 실제 질문 ≥10건**에서 **≥80%가 코드앵커 답을 1차 신뢰원으로 채택**하고, **최소 1건의 Notion-stale(코드와 어긋난 기존 문서)을 적발**. 미달 시 #4 가설 기각 → 범위 축소/중단 재검토.

boolean 불변식 검증·요구 반영·기획문서 전처리는 그 위에 순차로 얹음.

---

## 12. 리스크 · 미해결

| 항목 | 상태 | 대응 |
|---|---|---|
| 기획자 실제 채택 (#4) | 사용자 확신, 경험 미검증 | MVP 쐐기로 실측 |
| 활성/휴면 축 | 선행 사례 없음(novel) | 작게 실증 |
| 동적/런타임 값 (DB설정·플래그·환경별) | 단일 정답 없음 | MVP는 정적(repo) 값만. 런타임 어댑터는 Phase 2 |
| claim↔code 추출기 (코드 파싱) | net-new, 언어별 | pfplay(Java) 한정으로 시작 |
| 완전성 함정 (암묵 불변식) | 원리적 한계 | "전처리=초안" 운영, 사람 보완 |
| 유지비/소유권 | shelfware 주원인 | `owner` 필수 + working-set 스코핑 + code-anchor |

---

## 13. 명시적 범위 밖 (YAGNI)

- spec→code 자동 커버리지 %
- 도메인 스토리 → 불변식 자동도출
- SLO·동시성·분산 불변식의 **검증·집행** (엔지니어 관심사). 단 도메인 불변식 *구현*의 동시성 잔여는 `enforcement.residual_risk`로 **표기만** 함 — 검증·집행 대상이 아님(§5.2/§7과 일관)
- 런타임/동적 값 실시간 읽기 (Phase 2)
- 그래프 DB 전환 (Khala가 이미 pgvector, 필요 시 GraphRepository로 교체)
- 권한/인증 (Khala 기존 classification 재사용)

---

## 부록 A — 용어

- **개념(concept)**: 서비스에서 쓰이는 액터·객체·용어. = Khala entity(Term).
- **claim**: 개념에 매달린 사실. goal/invariant/requirement.
- **value-bearing**: 값을 품은 claim. 값은 출처를 가리켜 현재값을 읽음.
- **조치 반영**: 불변식을 강제하는 메커니즘이 코드에 존재·우회불가·로컬정확.
- **캘리브레이션 신뢰성**: 정답 보장이 아니라, 자기 확신도를 정직히 표기해 거짓말 안 함.
