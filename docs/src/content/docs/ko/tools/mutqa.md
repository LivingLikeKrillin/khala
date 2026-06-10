---
title: mutqa
description: 변이로 측정하는 테스트 품질 — 어드바이저리 리뷰가 놓치는 행위검증 공백을 살아남는 변이로 결정론적으로 드러낸다.
---

mutqa는 뮤테이션-구동 테스트 품질 하네스입니다. 어드바이저리 리뷰(TDD 스킬, LLM 테스트 리뷰어)가 체계적으로 놓치는 **행위검증 공백**을, 코드를 변이시키고 스위트가 그 변이를 잡지 못하는지로 *결정론적으로* 드러냅니다. green 스위트에서 살아남은 변이는 어떤 행위가 실제로 검증되지 않았다는 측정된 증거입니다.

mutqa가 보정하는 문제는 이렇습니다. 통과하는 테스트 스위트는 행위를 검증하는 스위트와 같지 않습니다. 특히 AI가 생성한 테스트는 green이면서도 속이 빈 경우가 많습니다 — 구조만 단언하고 행위는 단언하지 않습니다. 어드바이저리 리뷰어는 의견을 주지만, mutqa는 증거를 줍니다. 핵심 규율은 **결정론 영역(러너)과 판단 영역을 섞지 않는 것**입니다 — 러너는 유일한 계약(살아남은 변이 목록)을 산출하고, Test Quality Critic은 "이 변이에도 스위트가 green이었다"는 *측정된 사실*에만 근거해 각 항목을 triage합니다. 이 근거가 순수 LLM 리뷰와의 차별점입니다.

한 줄 정체성: "테스트가 통과한다"를 "테스트가 실제로 행위를 검증한다"로 바꾸는 하네스 — 살아남은 변이가 그 결정론적 신호입니다.

<img
  src="/diagrams/mutqa.svg"
  alt="변이 흐름: green 스위트 → cosmic-ray 변이 → 변이별 스위트 실행 → 살아남은 변이? 없으면 공백 없음 보고, 있으면 Critic triage → 원장 → biting real-gap 리포트."
  style="max-width: 100%; height: auto; display: block; margin: 1.5rem auto;"
/>

## 핵심 개념

- **변이(cosmic-ray)** — 변경된 소스 모듈을 변이시키고 각 변이마다 스위트를 돌립니다.
- **survivor** — 스위트가 잡지 못한 변이 = 테스트가 고정하지 못한 행위. 러너의 survivor 목록이 판단으로 넘어가는 유일한 계약입니다.
- **Test Quality Critic** — 각 survivor를 `real-gap`/`equivalent`/`low-value`로 triage하는 서브에이전트로, 결정론 증거에만 근거해 `{verdict, rationale, suggested_test_intent}`를 돌려줍니다.
- **원장(`mutqa-ledger.yaml`)** — 커밋되는 판정 기록. 재실행 시 *새* survivor만 재심의하므로 동치 노이즈를 매번 재심의하던 비용이 사라집니다.
- **무는(unwaived) real-gap = headline** — 리포트의 머리줄은 변이 점수가 아니라 무는 real-gap의 수입니다.
- **아직은 어드바이저리, 게이트 아님** — 현재는 리포트만 냅니다. 강제(무는 real-gap이 있으면 커밋 실패)는 다음 마일스톤입니다.

사전 조건(`pip install cosmic-ray`), `changed_source_modules` → `run_mutation` → survivors → Critic → 리포트 절차는 영어 페이지([mutqa](/tools/mutqa/))를 참고하세요.
