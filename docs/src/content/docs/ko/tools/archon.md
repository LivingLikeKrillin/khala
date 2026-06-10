---
title: Archon
description: 도메인 진실 거버넌스 — 불변식과 값에 대한 권위 창구, 코드에서 보정된 정직함으로 답한다.
---

:::caution[상태]
Archon은 현재 Nexus 저장소 안의 브랜치(`spec/domain-invariant-governance`)와 `claims` 패키지로 존재합니다. 아래 경로는 그 브랜치를 참조합니다.
:::

Archon은 도메인 진실(domain truth)에 대한 **권위 창구**입니다. 사람이든 에이전트든 "여기서 무엇이 참이고, 누구의 권위로 그러한가?"를 묻는 단일한 곳이며, 거버넌스된 출처에 근거한 답을 신선도·신뢰도와 함께 정직하게 돌려줍니다.

Archon이 보정(calibrate)하는 문제는 이렇습니다. 기획자(비엔지니어)는 회의에서 시스템의 전제조건 — 한도·정책·불변식 — 을 수시로 건드리지만, *현재 값*을 빠르게 확인할 방법이 없습니다. 엔지니어를 붙잡거나, 낡았을지 모를 Notion을 믿고, 잘못된 전제 위에 의사결정이 쌓입니다. Archon의 답은 "항상 정답"이 아니라(불가능합니다) **보정(calibration)**되어 있습니다 — soft하거나 낡은 답을 hard한 답인 척 내놓지 않습니다. 값은 권위 있는 출처(코드 상수)에서 조회 시점에 다시 읽으므로 낡지 않으며, 아는 것은 단정하고 모르는 것은 단정하지 않습니다.

한 줄 정체성: **Nexus 확장으로 구현한 도메인 값·불변식·권위 거버넌스** — 기계가 당신의 비즈니스 규칙의 의미를 제멋대로 지어내는 실패 모드에 대한 방어입니다.

<img
  src="/diagrams/archon.svg"
  alt="Archon이 도메인 질문에 답하는 흐름: 클레임을 찾고, 조회 시점에 코드 상수를 읽는다. 출처를 읽을 수 없으면 단언을 거부하고, 클레임의 마지막 검증 이후 코드 해시가 드리프트했으면 드리프트 경고와 함께, 아니면 보정된 답을 돌려준다."
  style="max-width: 100%; height: auto; display: block; margin: 1.5rem auto;"
/>

## 핵심 개념

- **개념이 척추, 사실은 매달린다** — 용어·액터·객체(유비쿼터스 언어) 레지스트리가 토대이고, 값·불변식·요구는 그 개념을 참조하는 *claim*입니다.
- **신뢰성 = 캘리브레이션(정직함)** — 시스템은 결코 거짓말하지 않습니다. (Notion이 못 하는 바로 그것입니다.)
- **복사하지 말고 가리켜라(anti-shelfware)** — 값을 저장소에 복사하면 썩습니다. claim은 권위 출처를 *가리켜* 현재값을 읽고 신선도를 표기합니다.
- **claim ↔ code drift** — 코드 심볼의 (파일경로+심볼명) hash가 마지막 검증 커밋 이후 바뀌면 claim에 드리프트를 태깅합니다.
- **System decides, LLM narrates** — 분류·검증·경로 판정은 결정론적 코드, LLM은 제안·요약만.

전체 CLI(`nexus claim-seed` / `nexus claim-value` / `nexus grade-authority`)와 MCP 도구(`archon_claim_value`, `archon_grade_authority`)는 영어 페이지([Archon](/tools/archon/))를 참고하세요.
