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

## 내용의 현실성은 검토가 필요하다

구조·용어·상태 이름은 `picasso` 설계 문서에서 가져왔다. **절차 자체는 현장을 모르는
채로 썼다.** 시간 상한(SOP-04 §5)처럼 눈에 띄게 임의인 수는 그 자리에 표시해 뒀다.
현실성 검토는 설명 계층 쪽 몫이다.
