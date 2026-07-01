---
title: Archon
description: 도메인의 불변식과 값에 대한 권위 창구. 코드에서 읽어 보정된 답을 준다.
---

:::caution[상태]
Archon은 현재 Nexus 저장소 안의 브랜치(`spec/domain-invariant-governance`)와 `claims` 패키지로 존재합니다. 아래 경로는 그 브랜치를 참조합니다.
:::

Archon은 도메인 진실(domain truth)에 대한 **권위 창구**입니다. 사람이든 에이전트든 "여기서 무엇이 참이고, 누구의 권위로 그러한가?"를 묻는 단일한 곳이며, 거버넌스된 출처에 근거한 답을 신선도·신뢰도와 함께 정직하게 돌려줍니다.

비엔지니어는 회의에서 시스템의 전제조건(한도·정책·불변식)을 수시로 건드리지만, *현재 값*을 빠르게 확인할 방법이 없습니다. 엔지니어를 붙잡거나 낡았을지 모를 Notion을 믿고, 잘못된 전제 위에 의사결정이 쌓입니다. Archon이 항상 정답일 수는 없지만(불가능합니다), **보정(calibration)**되어 있습니다. soft하거나 낡은 답을 hard한 답인 척 내놓지 않습니다. 값은 출처인 코드 상수에서 조회 시점에 다시 읽으므로 낡지 않습니다. 아는 것은 분명히 말하고, 검증할 수 없는 것은 답하지 않습니다.

한마디로: **Nexus 위에 구현한 도메인 값·불변식·권위 거버넌스.** 모델이 당신의 비즈니스 규칙의 의미를 제멋대로 지어내는 실패를 막습니다.

<svg class="kh-fig" viewBox="0 0 560 210" role="img" aria-label="Archon은 조회 시점에 코드 상수 config/limits.py:12 (MAX_RETRIES = 5)를 읽고 그 content-hash가 승인 해시와 일치하는지 검증한 뒤, 보정되고 인용된 답을 돌려준다: MAX_RETRIES = 5.">
<defs><marker id="ar-a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="kh-fig-ah" d="M0 0 L10 5 L0 10 z"/></marker></defs>
<text class="kh-fig-q" x="24" y="22">› max retry limit?</text>
<rect class="kh-fig-panel" x="24" y="36" width="250" height="150" rx="8"/>
<text class="kh-fig-h" x="42" y="60">READ CONSTANT</text>
<line class="kh-fig-rule" x1="42" y1="72" x2="256" y2="72"/>
<text class="kh-fig-d" x="42" y="94">config/limits.py:12</text>
<text class="kh-fig-ans" x="42" y="120">MAX_RETRIES = 5</text>
<text class="kh-fig-s" x="42" y="146">content-hash 3f9a2c</text>
<text class="kh-fig-verified" x="42" y="168">✓ matches approved</text>
<path class="kh-fig-line-acc" d="M274 111 L300 111" marker-end="url(#ar-a)"/>
<rect class="kh-fig-panel" x="300" y="36" width="236" height="150" rx="8"/>
<text class="kh-fig-h" x="318" y="60">GROUNDED ANSWER</text>
<line class="kh-fig-rule" x1="318" y1="72" x2="518" y2="72"/>
<text class="kh-fig-ans" x="318" y="98">MAX_RETRIES = 5</text>
<text class="kh-fig-d" x="318" y="124">→ config/limits.py:12</text>
<text class="kh-fig-s" x="318" y="148">read at query time · calibrated</text>
<text class="kh-fig-verified" x="318" y="170">✓ VERIFIED · no drift</text>
</svg>

## 핵심 개념

- **개념이 척추, 사실은 매달린다** — 용어·액터·객체(유비쿼터스 언어) 레지스트리가 토대이고, 값·불변식·요구는 그 개념을 참조하는 *claim*입니다.
- **신뢰성 = 캘리브레이션(정직함)** — 시스템은 결코 거짓말하지 않습니다. (Notion이 못 하는 바로 그것입니다.)
- **복사하지 말고 가리켜라(anti-shelfware)** — 값을 저장소에 복사하면 썩습니다. claim은 권위 출처를 *가리켜* 현재값을 읽고 신선도를 표기합니다.
- **claim ↔ code drift** — 코드 심볼의 (파일경로+심볼명) hash가 마지막 검증 커밋 이후 바뀌면 claim에 드리프트를 태깅합니다.
- **System decides, LLM narrates** — 분류·검증·경로 판정은 결정론적 코드, LLM은 제안·요약만.

전체 CLI(`nexus claim-seed` / `nexus claim-value` / `nexus grade-authority`)와 MCP 도구(`archon_claim_value`, `archon_grade_authority`)는 영어 페이지([Archon](/tools/archon/))를 참고하세요.
