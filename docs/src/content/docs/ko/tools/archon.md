---
title: Archon
description: 도메인 불변식 및 비즈니스 상수에 대한 권위 창(Authority Window) 인터페이스.
---

:::note[아키텍처 구성]
Archon은 독립 실행형 서비스가 아니며, Nexus 코어 저장소 내 `nexus/claims/` 패키지로 탑재되어 있습니다. Nexus CLI(`nexus claim-seed`, `nexus claim-value`, `nexus grade-authority`), HTTP REST API(`GET /claims/value`, `GET /claims/grade-authority`), 그리고 2개의 MCP 도구 인터페이스를 통해 접근할 수 있습니다.
:::

Archon은 도메인 진실(Domain Truth)에 대한 **단일 권위 창(Authority Window)** 인터페이스를 제공합니다. 소프트웨어 엔지니어 및 자율 에이전트가 시스템의 핵심 제약 조건, 한도, 비즈니스 불변식을 질의할 때, 정적 코드베이스 상수를 런타임에 직접 역참조하여 검증된 정본 값을 산출합니다.

문서화된 사양과 실제 소스코드 간의 괴리를 방지하기 위해, Archon은 사전에 정의된 도메인 클레임(Claim)을 소스코드 심볼에 바인딩하고, 질의 시점에 소스 파일의 AST/상수 값을 실시간 평가합니다. 근거가 부재하거나 정합성이 검증되지 않은 항목에 대해서는 응답을 기각함으로써 환각 생성을 억제합니다.

<svg class="kh-fig" viewBox="0 0 560 210" role="img" aria-label="Archon 상수 조회 및 검증 다이어그램: 질의 시점에 소스코드 상수 config/limits.py:12 (MAX_RETRIES = 5)를 읽고, content_hash가 사전 승인 해시와 일치함을 검증한 후 보정된 인용 답변(MAX_RETRIES = 5)을 반환함.">
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

## 핵심 아키텍처 및 기능 명세

- **엔티티 레지스트리 기반 클레임 모델** — 용어, 액터, 시스템 불변식을 표준 도메인 엔티티로 등록하고, 세부 수치와 제약 조건을 해당 엔티티를 참조하는 클레임(Claim) 객체로 구조화합니다.
- **포인터 기반 실시간 평가 (Dynamic Dereferencing)** — 수치 데이터를 정적 데이터베이스에 단순 복제하지 않고 소스코드 심볼 경로를 참조(포인터)로 유지하여, 질의 시점의 최신 코드 값을 동적으로 평가합니다.
- **코드 드리프트 감지 (Claim-to-Code Drift)** — 대상 코드 심볼의 파일 경로 및 구문 해시가 마지막 검증 커밋 대비 변경된 경우 해당 클레임에 드리프트 상태를 마킹합니다.
- **결정론적 판정 및 LLM 서술 분리 (System Decides, LLM Narrates)** — 분류, 불변식 판정, 권한 검증은 결정론적 코드로 강제하며, 언어 모델은 검증 완료된 결과에 대한 요약 및 표현만을 담당합니다.

CLI 및 MCP 도구 상세 명세는 영문 참조 페이지([Archon](/tools/archon/))를 확인하십시오.
