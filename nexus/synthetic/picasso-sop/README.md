---
title: 합성 SOP 6종 — 코퍼스 안내
labels: [synthetic]
updated: 2026-09-18
---

# 합성 SOP 6종 — picasso 코퍼스 평가용

> ⚠ **여기 있는 것은 전부 지어낸 문서다.** 현장 절차가 아니고, 운영에 쓰면 안 된다.
> 여섯 편 모두 `labels: [synthetic]` 을 선언하고, 그 표식은 검색 결과의 히트마다
> `synthetic: true` 로 실려 나간다.

## 왜 있나

`picasso` 코퍼스는 설계 문서 35편이다. 설계는 *"이 상태가 왜 생기는가"* 에 답하지만
*"그래서 무엇을 하는가"* 에는 답하지 않는다. 설명 계층의 평가에는 **절차 문서**가
필요한데, 현장 SOP 는 없다.

그래서 지어냈다. 지어낸 것을 지어냈다고 표시하는 것이 이 디렉터리의 절반이다 —
표식이 없으면 이 여섯 편이 실제 운영 문서와 같은 얼굴로 근거에 실린다. **검색이 잘 될수록
나쁜 종류의 결함이다**: 지어낸 절차를 정확히 인용해 온다.

## 적재

`picasso` 테넌트에 넣는다. 설계 문서와 같은 코퍼스에서 함께 찾혀야 하기 때문이다.

```bash
docker exec nexus-app python -m nexus.cli ingest /app/synthetic/picasso-sop --tenant picasso
```

⚠ 주기 재적재 잡(`REINGEST_TENANT=picasso`)은 `/ingest-src` 만 본다. 이 디렉터리는
거기 없으므로 **내용을 고치면 위 명령을 손으로 한 번 돌려야 한다.**

### frontmatter 가 말할 수 있는 것

| 키 | 무엇 | 안 적으면 |
|---|---|---|
| `title` | 문서 제목 | 첫 제목 줄에서 뽑는다 |
| `labels` | 자칭 라벨. **`synthetic` 하나만** 자칭할 수 있다 | 표식 없이 실린다 |
| `doc_type` | 문서 종류. 여기 여섯 편은 `policy` | 경로에서 추론한다 |
| `updated` | **원본이 말하는 수정 시각** → `documents.origin_updated_at` | 시각 미상이 되고 시각 범위 질의가 이 문서를 **거를 수 없다** |

⛔ **`updated` 는 2026-09-20 까지 읽히지 않았다.** 적재기가 `origin_last_edited`(노션
커넥터의 이름)만 봤고, 봤더라도 `updated: 2026-09-18` 은 YAML 이 `date` 객체로 주는데
문자열만 받고 있었다. 여섯 편이 이 줄을 적은 채 여섯 편 다 NULL 이었다 —
**적재는 성공했으므로 아무 경보도 울리지 않았다.** 지금은 둘 다 읽는다
(`ingest/pipeline.py: ORIGIN_TIME_KEYS`), 그리고 그 두 이름이 갈리면
`tests/test_origin_updated_at.py` 가 이 디렉터리를 직접 읽어 깨진다.

## 무엇을 덮고 무엇을 비웠나

⭐ **일부러 다 덮지 않았다.** 근거가 없는 사건이 남아 있어야 *"근거 없을 때 모른다고
답하는가"* 를 측정할 수 있다. 여섯 편이 15종 분류를 다 덮으면 그 측정이 불가능해진다.

| `FailureClass` | 절차 | 어디 |
|---|---|---|
| `GRASP_FAILED` | ✅ | SOP-01 |
| `PAYLOAD_LOST` | ✅ | SOP-01 |
| `PLACE_FAILED` | ✅ | SOP-02 |
| `PRECONDITION_FAILED` | ✅ | SOP-03 |
| `ROUTE_BLOCKED` | ✅ | SOP-04 |
| `NO_ROUTE` | ✅ | SOP-04 |
| `LOCALIZATION_LOST` | ✅ | SOP-05 |
| `CONTROL_AUTHORITY_LOST` | ✅ | SOP-06 |
| `COMMAND_OVERRIDDEN` | ✅ | SOP-06 |
| `PERCEPTION_FAILED` | ❌ **비움** | |
| `GRASP_PLANNING_FAILED` | ❌ **비움** | |
| `COMMAND_TIMED_OUT` | ❌ **비움** | |
| `HARDWARE_FAULT` | ❌ **비움** | |
| `ROBOT_FELL` | ❌ **비움** | |
| `UNCLASSIFIED` | ❌ **비움** | |

상태·판정 어휘도 같이 실었다: `residualHold` · `expectedHold`/`observedHold`/
`effectMismatch` (SOP-01·02), `preconditionSubjects` (SOP-03), `UNVERIFIED` ·
`VERIFICATION_MISMATCH` (SOP-02), 탐색 대장의 `FOUND`/`NONE`(`NO_CAPABILITY` ·
`DEPTH_LIMIT`)/`WITHHELD` (SOP-03).

## ⚠ 비운 여섯도 완전한 공백은 아니다

설계 문서(`2026-09-09-middleware-core-design.md` §1.3)가 **15종을 전부 표로 나열한다.**
그래서 *"`ROBOT_FELL` 이 뭔가"* 라고 물으면 정의는 나온다. 비어 있는 것은 **절차**이지
용어가 아니다.

근거 없는 사건을 만들려면 질문을 **절차 쪽으로** 세워야 한다 — 예를 들어
*"기체가 넘어졌을 때 자재를 어떻게 회수하는가"*. 어느 편을 얼마나 비울지는 골든셋을
짜는 쪽에서 정하고, 필요하면 이 표를 그때 다시 맞춘다.

## ⚠ 어휘 대조에서 셋이 걸렸다 (2026-09-18)

설명 계층이 이 문서들을 **근거로 인용한다.** 그래서 틀린 상태 이름은 그대로 운영자에게
전달되고, **인용 검증은 그것을 못 잡는다** — 검증은 *"그 문서가 그렇게 적혀 있는가"* 를
보지 *"그 문서가 맞는가"* 를 보지 않는다.

| 어디 | 썼던 것 | 맞는 것 | 왜 |
|---|---|---|---|
| SOP-01 §5.1 | `NEEDS_INTERVENTION` | `OPERATOR_HOLD` | 앞엣것은 **태스크 상태**(어댑터→계약)다 |
| SOP-04 §5 | `NEEDS_INTERVENTION` | `OPERATOR_HOLD` | 같음 |
| SOP-06 §4 | `UNKNOWN` | `IN_DOUBT` | `UNKNOWN` 은 **능력 선언**의 3값 표기지 단위 상태가 아니다 |

⛔ **그리고 이 정정문 자체가 같은 실수를 한 번 더 했다 (AGENT-04 재검토).** 여기 적혀
있던 「단위 상태 열하나」는 **단위 상태가 아니라 실행 상태**였다. 내가 인용한 표의 머리글이
`architecture.md:95` 에 **「실행 상태 (`picasso` 미들웨어)」** 라고 적혀 있고, 같은 코퍼스의
`2026-09-09-middleware-core-design.md:30` 은 그것을 `execution.physical_state` 라고 부른다.
**코퍼스만으로 잡혔어야 했다 — 내가 인용한 표의 머리글을 안 읽은 것이다.**

### 상태 enum 이 셋이다. 헷갈리는 이유는 **값을 여섯이나 공유**하기 때문이다

| enum | 값 | 어디 |
|---|---|---|
| `UnitState` (9) | `PENDING` · `IN_DOUBT` · `RUNNING` · `VERIFYING` · `OPERATOR_HOLD` · `DONE` · `UNVERIFIED` · `FAILED` · `ABORTED` | picasso `Model.kt:73` |
| `PhysicalState` (11) | `REQUESTED` · `ACCEPTED` · `RUNNING` · `PARTIAL` · `IN_DOUBT` · `OPERATOR_HOLD` · `PHYSICALLY_DONE` · `UNVERIFIED` · `FAILED` · `CANCELING` · `ABORTED` | `Model.kt:24` · 코퍼스 `architecture.md:98` 왼쪽 칸 |
| `TaskState` (10) | `ACCEPTED` · `RUNNING` · `PAUSED` · `SUCCEEDED` · `FAILED` · `RETRIABLE` · `NEEDS_INTERVENTION` · `CANCELLING` · `CANCELLED` · `CANCELLED_RECOVERY_FAILED` | 계약 · `architecture.md:98` 오른쪽 칸 |

**`UnitState` 와 `PhysicalState` 가 공유하는 값 여섯** — `IN_DOUBT` · `RUNNING` ·
`OPERATOR_HOLD` · `UNVERIFIED` · `FAILED` · `ABORTED`.

단위에만 있는 것: `PENDING` · `VERIFYING` · `DONE`.
실행에만 있는 것: `REQUESTED` · `ACCEPTED` · `PARTIAL` · `PHYSICALLY_DONE` · `CANCELING`.

⭐ **위 세 정정은 그대로 유효하다.** `OPERATOR_HOLD` 와 `IN_DOUBT` 는 두 enum 에 다 있어서
바꾼 값이 어느 쪽으로 읽어도 맞다. 틀렸던 것은 설명용 목록 한 줄이다.

### 다음에 상태 이름을 쓸 때

**어느 enum 소속인지 한 번 대조한다.** `Model.kt` 하나에만 상태처럼 읽히는 enum 이
여럿 있고(`UnitState` · `PhysicalState` · `UpstreamAck` · `Verification` ·
`ExecutionLookup` · `OperatorDecision` · `Route`), 계약 쪽 `TaskState` 까지 합치면 더 많다.

⛔ **이건 검사로 못 막는다.** 네 번 다 **실재하는 값**이었고 틀린 것은 계층뿐이었다. 값이
실재하는지는 기계가 보지만, *이 문장이 어느 계층을 말하는가* 는 문장의 뜻이라 사람이 본다 —
인용 검증이 「그 문서가 맞는가」를 못 보는 것과 같은 이유다. 그래서 검사 대신 **위 표**를
여기 둔다.

⚠ **`DEPTH_LIMIT`(SOP-03 §6)은 실물에서 안 밟힌다.** 파지가 네 값인데 효과가 내는 것은
둘뿐이라, 너비 우선 탐색이 깊이 상한에 닿기 전에 볼 것이 없어진다. 문서에 남겨 두는 것은
해롭지 않지만 **골든셋의 정답으로 쓰면 영영 안 나오는 사건을 묻는 셈**이다.

## 내용의 현실성은 검토가 필요하다

구조·용어·상태 이름은 `picasso` 설계 문서에서 가져왔다. **절차 자체는 현장을 모르는
채로 썼다.** 시간 상한(SOP-04 §5)처럼 눈에 띄게 임의인 수는 그 자리에 표시해 뒀다.
현실성 검토는 설명 계층 쪽 몫이다.
