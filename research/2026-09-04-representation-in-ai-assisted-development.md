# 표상(representation) — AI 를 쓰는 개발에서 담당자의 시스템 모델은 어떻게 되는가

*2026-09-04 논의 기록. 문헌 + 실측치 + 그로부터 끌어낸 설계 판단.*

---

## 0. 한계 (먼저)

- **판단과 조사가 섞여 있다.** §1~§4 는 공개 문헌이고 §5~§7 은 거기서 끌어낸 **설계 판단**이다.
  등급이 다르므로 절 머리에 표시했다.
- 수치는 원 출처의 보고값이고 독립 검증한 것이 아니다.
- ⛔ **이 문서는 아직 아무것도 반증하지 않았다.** 방향 판정까지이고, §7 의 반증 조건은 미실행이다.

---

## 1. 문제를 다시 놓는다 — 지식 격차가 아니라 책임·이해 불일치

처음에 나는 이걸 *"인수인계·팀 경계에서 표상이 무너진다"* 로 놓았고 **그 서술이 틀렸다**(사용자
지적, 2026-09-04). 남의 담당을 모르는 것은 정상이다. 문제는 그게 아니다.

| | 인수인계 격차 | 여기서 말하는 격차 |
|---|---|---|
| 조직이 격차를 아나 | **안다** → 인계 문서·온보딩·물어볼 사람이 붙는다 | **모른다** — 커밋 이력상 내가 썼다 |
| 드러나는 시점 | 인계 시점 (여유 있음) | **장애 시점** (여유 없음) |
| 프로토콜 | 있다 | **없다** |
| 책임 | 이전된다 | **이미 내 것** |

⭐ **인수인계 격차는 격차인 줄 아는 격차다. 이쪽은 아무도 격차라고 부르지 않는 격차다.**
그래서 점검 트리거가 없고, 처음 울리는 트리거가 장애다.

---

## 2. 측정된 것

- **`comprehension debt` · `cognitive debt` · `intent debt`** 로 문헌이 형성됐다(ACM Queue, arXiv 다수).
  정의: *코드가 존재하는 양과 사람이 실제로 이해하는 양 사이의 격차.* 기술 부채와 다른 점 셋 —
  인공물이 아니라 **인지**에 쌓이고, **인지 요구가 이해를 넘길 때까지 안 보이며**, 설계 지름길이
  아니라 **이해가 코드 증가를 못 따라갈 때** 쌓인다.
- **Anthropic RCT (2026-01-29, 엔지니어 52명).** 낯선 라이브러리를 쓰게 하고 몇 분 뒤 개념을
  물었다. AI 그룹 **50%** vs 손코딩 **67%**. ⭐ **가장 크게 떨어진 것이 디버깅**이고 그다음이
  코드 읽기, 그다음이 개념 이해다 — **가장 먼저 없어지는 능력이 장애 때 필요한 능력이다.**
- **프로덕션 빈도.** 설문에서 **AI 생성 코드 변경의 43%가 프로덕션에서 디버깅을 필요로 한다.**
- **DORA 2025.** 90%가 AI 를 쓰고 80%+ 가 생산성이 올랐다는데, **30%는 산출을 거의 신뢰하지
  않고 60%+ 가 배포 후에** AI 유래 결함을 발견한다.
- **GitClear (커밋 6억).** 블록 중복 40.3(2023) → 73.0(2026). 이동된 코드 21%(2022) → **3.8%**.
  12개월 이상 된 코드를 손대는 비율 **−74%**.

⇒ 위 §1 의 시나리오는 예외가 아니라 **주된 경로**다.

---

## 3. ⭐ 함정 — 흔한 대비책이 원인 쪽에 있다

Anthropic 이 참가자의 상호작용을 여섯 형태로 갈랐다.

**낮은 셋 (평균 40% 미만)**

1. `AI Delegation` — 통째로 맡긴다. 가장 빠르지만 독립적 사고가 최소
2. `Progressive AI Reliance` — 처음엔 조금 묻다가 점점 전부 맡긴다
3. ⭐ **`Iterative AI Debugging` — AI 를 이해가 아니라 디버깅·검증에 쓴다**

**높은 셋 (65% 이상)**

1. `Generation-then-Comprehension` — 생성 뒤 직접 읽고 후속 질문
2. `Hybrid Code-Explanation` — 코드와 설명을 함께 요청
3. ⭐ **`Conceptual Inquiry` — 개념만 묻고 코드는 자기가 쓴다.** 오류를 많이 만났지만 스스로
   풀었고 **높은 셋 중 가장 빨랐다**

여기서 두 문장이 나온다.

**① *"장애 나면 그때 AI 로 디버깅하면 되지"* 가 저점수 형태다.** AI 로 디버깅하는 습관 자체가
장애 때 필요한 능력을 깎는다.

**② 이해를 지키는 것이 느리다는 교환은 항상 성립하지 않는다.** `Conceptual Inquiry` 가 높은 셋
중 가장 빨랐다 ⇒ **얼마나 맡기느냐가 아니라 무엇을 맡기느냐**의 문제다.

저자들의 문장: *"인지적 노력 — 심지어 고통스럽게 막히는 것 — 이 숙달에 중요할 것이다."*

---

## 4. 개입 연구 — 작동하는 개입이 미움받는 개입이다

- **`cognitive forcing function`** (Buçinca et al., CHI 2021, N=199) — AI 출력을 받아들이기
  **전에** 명시적 성찰 행동을 하게 만드는 개입. 단순 설명형 AI 보다 **과의존을 크게 줄였다.**
- ⚠ **그런데 사람들이 그 설계에 가장 낮은 주관 평점을 줬다.** 단순 설명형을 더 신뢰하고, 더
  선호하고, 덜 복잡하다고 느꼈다.
- ⚠ 그리고 **Need for Cognition 이 높은 사람이 더 이득**을 봤다. NFC 는 지능이 아니라 **성향**
  이다 — *애써 생각하는 일에 몰두하고 그것을 즐기는 경향*(Cacioppo & Petty, 1982). ⇒ 그 개입은
  **도움이 가장 필요한 쪽**(인지적 노력을 회피하는 쪽)에서 **가장 안 듣고 가장 미움받는다.**
- **후속 연구가 방향을 냈다.** 같은 저자군이 오프라인 RL 로 *누구에게 · 언제 · 어떤 종류의
  지원을 줄지* 를 정하게 했고, 정확도와 참여를 올리면서 **주관적 즐거움을 깎지 않았다.**

⇒ **미움받는 것은 개입이 아니라 획일적 개입이다.**

---

## 5. 판단 — 사후 심문은 형성하지 못한다

**⚠ 여기부터는 조사가 아니라 판단이다.**

`Adept` 형태(작업이 끝난 뒤 별도 표면에서 묻고 채점하는 것)의 결함 둘:

- **시점** — 컨텍스트가 이미 빠져나간 뒤에 묻고, 되살리는 비용을 사람이 전액 부담한다
- **경로** — 개발 흐름 밖이라 별도 표면을 열어야 한다

그리고 근본적으로 — **사후 시험은 결손을 측정할 뿐 형성하지 않는다.** §3 의 형태 분류로 보면,
작업 중 상호작용이 `AI Delegation` 인 사람은 나중에 시험을 봐도 여전히 `AI Delegation` 이다.
**형성은 작업 중에만 일어난다.**

⛔ 이것은 질문 생성·채점·vouch 를 버리자는 말이 **아니다.** 그 셋은 그대로 필요하고, **판정
시점이 사후에서 작업 중으로 옮겨야** 한다는 말이다.

---

## 6. 방향 — 받는 지도가 아니라 고치는 지도

**⚠ 판단이다.**

### 6.1 "아무도 안 읽는다" 의 원인은 텍스트가 아니라 속도다

- ICLR 2026 동료심사 **75,800건 중 21%가 전부 AI 생성**, 그중 15,899건은 환각 인용에 논문의
  실제 기여와 맞물리지 않는 피드백이었다.
- 승인 쪽: *승인 요청이 사람이 읽을 수 있는 속도보다 빠르게 도착하면 감독은 rubber-stamping
  으로 붕괴하고, 확인은 결정이 아니라 반사가 된다.*

⇒ ⛔ **그러므로 그림으로 바꿔도 같은 실패가 난다.** 받기만 하는 산출물은 그림이어도 같은 경로로
승인된다 — **오히려 더 위험하다. 그림은 "봤다"는 느낌을 텍스트보다 싸게 준다.**

UML 문헌도 결이 같다: 다이어그램의 이해 효과는 **배치와 친숙도에 크게 의존**하고, 배치가 나쁘면
이득이 사라진다. *"다이어그램이 있으면 이해된다"* 는 성립하지 않는다.

### 6.2 EventStorming 의 기제는 그림이 아니라 언어다

먹히는 이유는 산출된 벽이 아니라 **여럿이 같이 만드는 과정**이고, 시작을 명사(도메인 객체)가
아니라 **동사(도메인 이벤트)** 로 한다는 점이다. 그 계열의 결론: **"매 단계의 투자는 언어에
들어간다. 코드는 따라온다."**

### 6.3 그래서 형태

| | 비용 | 결과 |
|---|---|---|
| 사람이 **그리게** 한다 | 비싸다 | 안 한다 |
| 시스템이 **만들어 준다** | 싸다 | 안 읽는다 |
| ⭐ **틀린 것을 고치게 한다** | **싸다** | **개입이 성립한다** |

`doc-anchors` 가 *"이 문서가 낡았나"* 를 사람 판정에서 조인 한 번으로 바꾼 것과 같은 수다 —
**판단을 없애지 않고 비용만 낮춘다.**

구체 형태: 지도를 자동 갱신하되 **모델이 확신 없는 자리를 표시하고 한 번의 선택을 요구한다** —
*이 경계가 여기 맞나 / 이 이벤트 이름이 도메인 언어인가 / 이 의존이 의도인가.*

### 6.4 DDD 가 맞는 축인 이유 셋

1. **bounded context 가 곧 온콜 경계다** — "누가 이걸 책임지나"와 거의 겹친다
2. **유비쿼터스 언어는 기계가 검증할 수 있다** — 이름이 코드·문서·대화에서 갈라졌는지는 대조
   가능하다. *그림이 예쁜가* 가 아니라 **언어가 갈라졌는가**가 측정 대상이 된다
3. **이벤트가 동사라서 실패 모드와 붙는다** — 장애는 상태가 아니라 흐름에서 난다

### 6.5 막힌 곳은 생성이 아니다

코드에서 C4 **모델**을 뽑는 것은 이미 된다(AST → 의미 그래프 → LLM → PlantUML/Structurizr/
Mermaid). 보고값 **정확도 약 88%, 3~5분**, 수작업 6~12시간 대체. 정본 조언은 **정적 그림이
아니라 "모델 as code"를 산출하라** 는 것이다.

⚠ **88%가 함정이다.** 여덟 곳 중 한 곳이 틀린 지도이고, 그걸 표상으로 받아들이면 **틀린 표상을
확신 있게 갖는다.** ⭐ 그래서 지도에 **확신 표시**가 반드시 붙어야 하는데, **확신 없는 자리가
곧 §6.3 의 개입 지점이다** — 정확도의 약점이 그대로 개입 지점 선택 기준이 된다.

---

## 7. 착수 전에 박아야 할 반증 조건

이 리포는 기법 추가로 **7전 7패**했고 오른 것은 전부 결함 제거였다. 이 방향도 같은 자리에 있다.

1. ⛔ **성공 기준이 "이해했다는 느낌" 이면 안 된다.** 측정 대상은 **복구 능력** —
   *이 코드를 AI 없이 디버깅할 수 있는가.* ⇒ vouch 의 단위가 "이 문서를 읽었다" 가 아니다.
2. **대조군이 필요하다** — 개입이 걸린 코드와 안 걸린 코드에서 나중 장애 대응이 갈리는가.
   ⚠ **사건이 있어야 측정된다.** 측정이 느리다는 것을 인정하고 시작한다.
3. **끄는 비율을 센다.** §4 가 예측한 실패가 그것이다. 껐다면 그게 첫 번째 자료다.
4. **희소성이 유지되는지 센다.** 개입이 획일적으로 번지면 §4 의 결과대로 꺼진다.

---

## 출처

**부채·기능 저하**
- [ACM Queue — From Technical Debt to Cognitive and Intent Debt](https://queue.acm.org/detail.cfm?id=3807966)
- [Addy Osmani — Comprehension Debt](https://addyosmani.com/blog/comprehension-debt/)
- [Anthropic — How AI assistance impacts the formation of coding skills](https://www.anthropic.com/research/AI-assistance-coding-skills)
- [43% of AI-generated code changes need debugging in production](https://venturebeat.com/technology/43-of-ai-generated-code-changes-need-debugging-in-production-survey-finds)
- [DORA 2025](https://dora.dev/insights/balancing-ai-tensions/) · [GitClear — The Maintainability Gap](https://www.gitclear.com/the_ai_code_quality_maintainability_gap)

**개입 연구**
- [Buçinca et al. — To Trust or to Think (CHI 2021, arXiv 2102.09692)](https://arxiv.org/abs/2102.09692)
- [Buçinca et al. — Offline RL for adaptive support (arXiv 2403.05911)](https://arxiv.org/abs/2403.05911)
- [Need for cognition (Cacioppo & Petty, 1982)](https://richardepetty.com/wp-content/uploads/2019/01/1982-jpsp-cacioppopettyncog.pdf)

**승인 붕괴 · 시각화**
- [Approval Fatigue — how human-in-the-loop gates decay into rubber stamps](https://tianpan.co/blog/2026/06/25/approval-fatigue-how-human-in-the-loop-gates-decay-into-rubber-stamps)
- [On the impact of UML analysis models on source-code comprehensibility](https://dl.acm.org/doi/10.1145/2491912)
- [Collaborative modeling and LLMs — EventStorming · Domain Storytelling](https://www.codecentric.de/en/knowledge-hub/blog/from-stories-to-code-how-domain-storytelling-and-eventstorming-give-llms-the-context-they-need)
- [AI-assisted software architecture — C4 from code](https://www.workingsoftware.dev/ai-assisted-software-architecture-generating-the-c4-model-and-views-directly-from-code/) · [Structurizr](https://structurizr.com/)
