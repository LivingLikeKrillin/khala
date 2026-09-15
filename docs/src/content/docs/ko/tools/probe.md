---
title: Probe
description: AST 구문 변이 기반 테스트 스위트 결함 검출력 계측 하니스.
---

Probe는 변이 테스트(Mutation Testing) 기반의 테스트 스위트 품질 검증 프레임워크입니다. 정적 코드 분석이나 LLM 기반 주관적 리뷰가 식별하기 어려운 **테스트 행위 검증 공백**을, 소스코드 구문을 체계적으로 변이시킨 후 기존 테스트 스위트가 이를 실패로 검출하는지 여부를 통해 *결정론적으로* 판정합니다. 테스트 스위트가 통과 상태를 유지하면서 생존한 변이체(Survivor Mutant)는 실제 비즈니스 로직의 검증 공백을 입증하는 객관적 데이터입니다.

단순 라인 커버리지는 코드의 실행 여부만을 나타내며, 실질적인 결함 검출 능력을 보장하지 않습니다. Probe는 **결정론적 변이 실행 엔진(Runner)**과 **공학적 판정 레이어(Test Quality Critic)**를 명확히 분리합니다. 러너는 AST 변이 후 생존한 변이체 목록을 산출하며, Critic 서브시스템은 해당 실측 데이터에 입각하여 각 변이체의 영향도를 체계적으로 분류(Triage)합니다.

<svg class="kh-fig" viewBox="0 0 560 230" role="img" aria-label="Probe 변이 테스트 프로세스: 12개 변이체 중 10개 검출(Killed), 2개 생존(Survived). 생존 변이체 분석을 통해 ledger.py:reconcile 함수의 경계 조건 미검증 결함을 식별하고 보강 테스트 추가를 권고함.">
<defs><marker id="pb-a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="kh-fig-ah" d="M0 0 L10 5 L0 10 z"/></marker></defs>
<rect class="kh-fig-panel" x="24" y="28" width="250" height="180" rx="8"/>
<text class="kh-fig-h" x="42" y="52">MUTANTS · 12</text>
<line class="kh-fig-rule" x1="42" y1="64" x2="256" y2="64"/>
<rect class="kh-fig-track" x="44" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="82" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="120" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="158" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="44" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="82" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-box-acc" x="120" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="158" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-box-acc" x="44" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="82" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="120" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="158" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="42" y="180" width="12" height="12" rx="2"/>
<text class="kh-fig-s" x="60" y="187">killed ×10</text>
<rect class="kh-fig-box-acc" x="150" y="180" width="12" height="12" rx="2"/>
<text class="kh-fig-s" x="168" y="187">survived ×2</text>
<path class="kh-fig-line-acc" d="M274 118 L300 118" marker-end="url(#pb-a)"/>
<rect class="kh-fig-panel" x="300" y="28" width="236" height="180" rx="8"/>
<text class="kh-fig-h" x="318" y="52">GAP FOUND</text>
<line class="kh-fig-rule" x1="318" y1="64" x2="518" y2="64"/>
<text class="kh-fig-ans" x="318" y="94">2 survived</text>
<text class="kh-fig-d" x="318" y="122">ledger.py:reconcile</text>
<text class="kh-fig-s" x="318" y="144">boundary not covered</text>
<text class="kh-fig-d" x="318" y="176">→ add test</text>
</svg>

## 핵심 기능 명세

- **구문 변이 엔진 (`cosmic-ray`)** — 변경된 소스코드 모듈을 대상으로 연산자, 불리언 식, 경계 조건을 체계적으로 변이시키고 테스트를 실행합니다.
- **생존 변이체 (Survivor Mutant) 추출** — 테스트 스위트가 통과함으로써 실패 검출에 실패한 변이체를 식별하여 유효 검증 결함으로 보고합니다.
- **테스트 품질 판정 (Test Quality Critic)** — 생존 변이체를 정밀 분석하여 `real-gap`(실질 결함), `equivalent`(동치 변이), `low-value`(저가치)로 분류하고 구조화된 판정 결과(`verdict`, `rationale`, `suggested_test_intent`)를 산출합니다.
- **판정 원장 영속화 (`probe-ledger.yaml`)** — 이미 심의 완료된 변이체 분류 이력을 기록하여 반복 실행 시 신규 변이체만을 증분 심의함으로써 검증 비용을 최소화합니다.
- **미면제 실질 결함(Unwaived Real Gap) 지표화** — 단순 점수 수치가 아닌 배포 차단 대상인 미면제 실질 결함 건수를 핵심 품질 지표로 노출합니다.
- **CLI 명령어 체계** — `probe survey`(변이 수행 및 생존 변이체 목록 추출) 및 `probe absorb`(판정 결과의 원장 반영) 명령어를 제공합니다.

설치 및 실행 파라미터는 영문 참조 페이지([Probe](/tools/probe/))를 참고하십시오.
