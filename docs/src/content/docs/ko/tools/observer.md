---
title: Observer
description: 플랫폼 프로파일 기반 PR 범위 분석기이자 API 하위 호환성 계약 검증 엔진.
---

Observer는 Pull Request의 변경 범위를 아키텍처 응집도, API 명세 계약, 조직 엔지니어링 규정에 대조하여 결정론적으로 평가하는 정적 분석 엔진입니다:

1. **PR 변경 범위의 아키텍처 응집도 평가**: 단순 변경 라인 수나 파일 수가 아닌, 대상 프레임워크(Spring Boot, Next.js 등)의 플랫폼 프로파일에 기반하여 파일별 아키텍처 역할과 결합도를 계산합니다.
2. **API 하위 호환성 및 스키마 검증**: OpenAPI/JSON 스키마 린트 및 베이스 브랜치 대비 diff 분석을 통해 필드 nullable 누락, 에러 응답 불일치, 하위 호환성 파괴(Breaking Change)를 사전 검출합니다.
3. **규정 준수 및 리뷰 체크리스트 자동 합성**: PR의 커밋 및 diff 특성을 분석하여 적합한 검토 체크리스트를 생성하며, Nexus 연동 시 사내 아키텍처 규정 및 영향도 분석 데이터를 결합하여 제공합니다.

Observer는 결함이나 불일치가 검출되지 않은 정상 상태에서는 출력을 최소화(Silent on Clean)하여 검토 노이즈를 억제하며, 범위 분리가 필요한 경우 안전한 병합 순서를 포함한 분할 계획을 생성합니다.

<svg class="kh-fig" viewBox="0 0 560 220" role="img" aria-label="Observer 변경 범위 분석 다이어그램: 3개 변경 파일에 대해 역할(api, data)을 분류하고, 복수 도메인 관심사가 혼재되었음을 탐지하여 병합 순서가 보존된 2개 단위 PR(PR-a: api, PR-b: data)로의 분할 계획을 제안함.">
<defs><marker id="ob-a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="kh-fig-ah" d="M0 0 L10 5 L0 10 z"/></marker></defs>
<rect class="kh-fig-panel" x="24" y="28" width="284" height="168" rx="8"/>
<text class="kh-fig-h" x="42" y="52">SCOPE · 3 FILES</text>
<line class="kh-fig-rule" x1="42" y1="64" x2="290" y2="64"/>
<text class="kh-fig-h" x="42" y="88">API</text>
<text class="kh-fig-d" x="88" y="88">routes/pay.py</text>
<text class="kh-fig-d" x="88" y="108">schemas/pay.py</text>
<text class="kh-fig-h" x="42" y="140">DATA</text>
<text class="kh-fig-d" x="88" y="140">models/ledger.py</text>
<text class="kh-fig-s" x="42" y="176">cohesion scored · roles matched</text>
<path class="kh-fig-line-acc" d="M308 112 L334 112" marker-end="url(#ob-a)"/>
<rect class="kh-fig-panel" x="334" y="28" width="202" height="168" rx="8"/>
<text class="kh-fig-h" x="352" y="52">VERDICT</text>
<line class="kh-fig-rule" x1="352" y1="64" x2="518" y2="64"/>
<text class="kh-fig-ans" x="352" y="92">mixed · 2 roles</text>
<text class="kh-fig-d" x="352" y="122">propose split</text>
<text class="kh-fig-d" x="352" y="146">› PR-a  api</text>
<text class="kh-fig-d" x="352" y="166">› PR-b  data</text>
<text class="kh-fig-s" x="352" y="186">merge order preserved</text>
</svg>

## 핵심 기능 명세

- **플랫폼 프로파일 (Platform Profiles)** — 프레임워크별 파일 경로 패턴을 아키텍처 역할에 매핑하고 논리적 응집 그룹을 정의합니다.
- **범위 및 관심사 분리 분석 (Scope & Cohesion Analysis)** — 수정 파일의 역할을 식별하고, 이기종 관심사가 혼재된 경우 심각도(Severity) 판정과 함께 순서 보존 분할 방안을 제시합니다.
- **실시간 관심사 드리프트 감지** — 단일 작업 세션 중 초기 변경 범위를 벗어나는 파일 수정 발생 시 즉시 경고를 발생시킵니다.
- **API 계약 린트 및 변경 diff (API Contract Linting)** — 10대 내장 린트 규칙(`observer/nullable`, `observer/error-response` 등)을 적용하여 명세를 검증하고 베이스라인 대비 브레이킹 체인지를 추출합니다.
- **체크리스트 매핑** — PR 변경 유형에 대응하는 10개 정형 검토 체크리스트를 자동 조합합니다.
- **모듈 결합도 분리** — Nexus 지식 기판 연결 여부와 무관하게 독립 실행 가능하며, 연동 시 규정 및 텔레메트리 기반 심층 분석이 보강됩니다.

빌드 및 CLI 실행 명세는 영문 참조 페이지([Observer](/tools/observer/))를 확인하십시오.
