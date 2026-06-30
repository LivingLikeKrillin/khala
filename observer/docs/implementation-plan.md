# 안전망 툴킷 구현 계획서

> **목적**: 설계 문서 8개를 동작하는 소프트웨어로 바꾸는 구체적 계획
> **전제**: 팀 전원 Claude Code 사용, 로컬 + CI 이중 게이트
> **원칙**: 하나를 끝까지 돌게 만들고, 그 위에 얹는다

---

## 0. 현재 상태와 목표 상태

```
현재 상태                              목표 상태
──────────                            ──────────
설계 문서 8개                          동작하는 툴킷
규정은 있으나 실행 수단 없음              Claude Code가 규정을 자동 실행
사람이 규정을 읽고 따라야 함              도구가 알려주니까 자연스럽게 따름
검증 없는 PR                           PR 생성 시 자동 검증 + 머지 시 게이트
```

---

## 1. 구현 대상 전체 목록

설계 문서에서 도출된 구현물을 전부 나열한다. 그 다음에 우선순위를 매긴다.

### 1.1 Claude Code 설정

| 구현물 | 설명 | 난이도 |
|--------|------|--------|
| `CLAUDE.md` | 프로젝트 규칙 파일 — Claude Code 행동의 기반 | 낮음 |
| pre-commit hook | 직접 값 사용 탐지, 자동 생성 파일 편집 탐지 | 낮음 |
| pre-push hook | 스펙 동기화 확인, 스토리 존재 확인 | 낮음 |
| pr-create hook | DoD 자동 검증 + 템플릿 채움 + 라벨 제안 | 중간 |
| pr-review hook | VRT/Impact 요약 코멘트 자동 생성 | 중간 |
| /state-matrix 명령 | State Matrix 템플릿 자동 생성 | 낮음 |
| /api-check 명령 | API 변경 사항 분석 | 낮음 |
| /ui-check 명령 | UI 변경 사항 분석 | 낮음 |
| /impact 명령 | 토큰 영향 범위 분석 | 중간 |

### 1.2 CI 스크립트

| 구현물 | 설명 | 난이도 | 외부 도구 |
|--------|------|--------|-----------|
| api:generate | 코드 → OpenAPI 스펙 생성 | 낮음 | springdoc |
| api:lint | 스펙 품질 검증 | 낮음 | Spectral |
| api:diff | 스펙 변경 탐지 + breaking 판별 | 낮음 | oasdiff |
| api:compatibility | 호환성 상세 검사 | 낮음 | oasdiff |
| api:codegen | 스펙 → FE 타입 생성 | 낮음 | openapi-typescript |
| api:mock | Mock 서버 | 낮음 | Prism |
| ws:lint | AsyncAPI 스펙 검증 | 중간 | AsyncAPI CLI + 커스텀 |
| ws:codegen | AsyncAPI → FE 타입 생성 | 중간 | 커스텀 스크립트 |
| design:sync | Figma → 토큰 산출물 | 높음 | Figma API |
| lint:tokens | 토큰 검증 (네이밍/순환/대비) | 중간 | 커스텀 스크립트 |
| lint:a11y | 접근성 자동 검사 | 중간 | axe-playwright |
| vrt:run | VRT 실행 | 높음 | Chromatic |
| ui:impact | 영향 범위 분석 | 중간 | TS Compiler API |

### 1.3 MCP 서버

| 구현물 | 설명 | 난이도 |
|--------|------|--------|
| OpenAPI Diff MCP | oasdiff 래핑, API 변경 분석 | 중간 |
| Chromatic MCP | VRT 결과 조회 | 중간 |
| State Matrix MCP | 매트릭스 파싱 + 교차 검증 | 중간 |
| Figma MCP | Figma Variables API 래핑 | 높음 |

### 1.4 GitHub Actions

| 구현물 | 설명 | 난이도 |
|--------|------|--------|
| safety-net.yml | 통합 CI 워크플로 | 중간 |
| merge-gate.js | 최종 DoD 검증 → 머지 차단 | 중간 |

---

## 2. 의존 관계

무엇을 먼저 만들어야 다음 것을 만들 수 있는지.

```
CLAUDE.md (의존 없음)
    │
    ├─► pre-commit hook (CLAUDE.md의 규칙을 강제)
    │
    ├─► pre-push hook (CLAUDE.md의 규칙을 강제)
    │
    └─► pr-create hook (CLAUDE.md 기반 + 아래 스크립트 결과 활용)
            │
            ├── api:generate ← springdoc 설정 (BE 빌드 환경 필요)
            │       │
            │       ├─► api:lint ← .spectral.yaml 룰셋
            │       ├─► api:diff ← oasdiff 설치
            │       ├─► api:codegen ← openapi-typescript 설치
            │       └─► api:mock ← Prism 설치
            │
            ├── lint:tokens ← tokens.json 구조 확정
            │       │
            │       └─► ui:impact ← lint:tokens + TS Compiler API
            │
            ├── storybook:build ← Storybook 설정
            │       │
            │       ├─► lint:a11y ← axe-playwright
            │       └─► vrt:run ← Chromatic 계정/설정
            │
            └── design:sync ← Figma API 접근권한
                    │
                    └─► Figma MCP

OpenAPI Diff MCP ← api:diff 동작 확인 후
Chromatic MCP ← vrt:run 동작 확인 후
State Matrix MCP ← State Matrix 템플릿 정착 후

safety-net.yml ← 위 스크립트들이 개별 동작 확인된 후
merge-gate.js ← safety-net.yml 안정화 후

pr-review hook ← MCP 서버 1개 이상 동작 확인 후
```

---

## 3. 구현 스프린트 계획

### Sprint 0: 기반 (1주)

> **목표**: Claude Code가 이 프로젝트를 이해하고 규정에 맞게 행동하는 상태

| 작업 | 산출물 | 검증 기준 |
|------|--------|-----------|
| CLAUDE.md 작성 | `CLAUDE.md` | Claude Code에게 "Button 컴포넌트 만들어줘"라고 했을 때, 직접 색상값 대신 토큰을 사용하는지 확인 |
| 프로젝트 구조 세팅 | `.claude/`, `scripts/`, `docs/`, `api/` 디렉토리 | 구조가 adoption-strategy.md의 폴더 구조와 일치 |
| State Matrix 템플릿 커밋 | `docs/state-matrices/_template.md` | Claude Code에서 `/state-matrix` 명령 시 템플릿 기반으로 생성 |
| PR 템플릿 커밋 | `.github/PULL_REQUEST_TEMPLATE/` | GitHub에서 PR 생성 시 템플릿이 자동으로 뜸 |

**CLAUDE.md에 들어갈 핵심 규칙**:

```
1. 직접 값 사용 금지 (색상, px, shadow, motion duration)
2. 토큰 산출물/API 스펙/codegen 파일은 수작업 편집 금지
3. PR 작성 시 Impact 섹션 필수, 라벨 필수
4. 컴포넌트 변경 시 스토리 동반 필수
5. 화면 변경 시 Screen Story에 loading + (empty|error) 필수
6. API 변경 시 breaking 여부 명시 필수
7. State Matrix 필수 상태: loading, empty, error, success
```

**검증 방법**: Claude Code에게 실제 작업을 시켜보고, 규칙을 자연스럽게 따르는지 확인. 안 따르면 CLAUDE.md 문구를 조정.

---

### Sprint 1: 로컬 Hook + 기본 CI (2주)

> **목표**: 커밋/PR 시점에 자동 피드백이 동작하는 상태

#### Week 1: pre-commit hook + api:generate + api:lint

| 작업 | 산출물 | 검증 기준 |
|------|--------|-----------|
| pre-commit hook 작성 | `.claude/hooks/pre-commit.md` | `#FF0000` 포함 파일 커밋 시 차단됨 |
| springdoc 설정 | `build.gradle.kts` 수정 | `./gradlew generateOpenApiDocs`로 `api/openapi.json` 생성됨 |
| api:generate 스크립트 | `package.json` script | `pnpm api:generate`로 스펙 파일 갱신됨 |
| Spectral 룰셋 작성 | `.spectral.yaml` | `pnpm api:lint`로 네이밍/에러스키마/nullable 검사 동작 |
| CI에 api:lint 추가 | `.github/workflows/safety-net.yml` | PR에 api:lint 결과가 표시됨 (경고만, 차단 아님) |

**api:lint 룰셋 최소 범위 (Week 1)**:

```
- 엔드포인트 경로 kebab-case 검사
- 필드명 camelCase 검사
- 4xx/5xx 응답에 ErrorResponse 스키마 참조 검사
- nullable + optional 동시 적용 경고
```

#### Week 2: pr-create hook + api:diff

| 작업 | 산출물 | 검증 기준 |
|------|--------|-----------|
| pr-create hook 작성 | `.claude/hooks/pr-create.md` | PR 생성 시 타입 추론 + DoD 검증 + 라벨 제안 코멘트가 달림 |
| oasdiff 설치 + api:diff | `package.json` script | `pnpm api:diff`로 main 대비 변경 요약이 출력됨 |
| CI에 api:diff 추가 | `.github/workflows/safety-net.yml` | PR 코멘트에 API 변경 요약이 자동 게시됨 |
| api:lint CI 강제화 | `.github/workflows/safety-net.yml` | api:lint 실패 시 CI 실패 (경고 → 차단 전환) |

**pr-create hook MVP 범위**:

```
Step 1: 변경 파일 분석 → PR 타입 추론
Step 2: 해당 타입의 필수 항목 검사
  - ui:components → 스토리 파일 존재 여부
  - ui:screens → Screen Story + 필수 상태
  - api:* → 스펙 파일 변경 포함 여부
Step 3: PR 본문에 Impact 섹션이 있는지 확인
Step 4: 누락 항목을 코멘트로 남김 (차단 아님)
```

**Sprint 1 종료 시 팀이 체감하는 것**:
- 커밋할 때 직접 색상값 쓰면 막힌다
- PR 올리면 Claude Code가 "이건 ui:components PR인 것 같고, 스토리가 없어요"라고 알려준다
- API 스펙이 변경되면 PR 코멘트에 자동으로 변경 요약이 붙는다

---

### Sprint 2: API 계약 자동화 (2주)

> **목표**: FE가 스웨거만 보고 연동할 수 있는 환경 + 타입 자동 생성

#### Week 3: api:codegen + api:mock + api:compatibility

| 작업 | 산출물 | 검증 기준 |
|------|--------|-----------|
| openapi-typescript 설정 | `package.json` script + 설정 파일 | `pnpm api:codegen` → `src/api/types.ts` 생성 |
| Prism 설정 | `package.json` script | `pnpm api:mock` → localhost:4010에서 Mock 서버 동작 |
| api:compatibility 설정 | `package.json` script | `pnpm api:compatibility` → breaking 변경 시 exit 1 |
| ErrorResponse 공통 스키마 정의 | BE 코드 + springdoc 어노테이션 | 모든 4xx/5xx가 ErrorResponse를 참조함 |

#### Week 4: nullable 전수 점검 + WebSocket 기반 (해당 시)

| 작업 | 산출물 | 검증 기준 |
|------|--------|-----------|
| 기존 API nullable/required 전수 점검 | BE 코드 수정 | api:lint에서 nullable 경고 0건 |
| (WebSocket 사용 시) AsyncAPI 도입 판단 | 결정 문서 | 이벤트 수 기준으로 AsyncAPI 도입 여부 확정 |
| (AsyncAPI 도입 시) Springwolf 설정 | `build.gradle.kts` | `api/asyncapi.json` 생성됨 |
| (AsyncAPI 미도입 시) events.md + types.ts | `api/websocket/` | 이벤트 목록 + 공유 타입 작성됨 |
| CI: api:compatibility → breaking PR 차단 | workflow 수정 | `api:breaking` 라벨 PR에서 호환성 검사 실패 시 머지 불가 |

**Sprint 2 종료 시 팀이 체감하는 것**:
- `pnpm api:codegen` 한 번이면 FE 타입이 자동으로 나온다
- BE API가 아직 안 만들어져도 Mock 서버로 FE 개발 가능
- API breaking 변경은 FE 리뷰어 승인 없이 머지 불가

---

### Sprint 3: UI 품질 자동화 (2주)

> **목표**: 토큰/컴포넌트/화면 변경의 영향 범위를 자동으로 알 수 있는 상태

#### Week 5: lint:tokens + design:sync 기반

| 작업 | 산출물 | 검증 기준 |
|------|--------|-----------|
| tokens.json 구조 확정 | `src/design-tokens/tokens.json` | 네이밍 규칙, 모드(light/dark), alias, deprecated 필드 포함 |
| lint:tokens 구현 | `scripts/lint-tokens.js` | 네이밍 위반, 순환 alias, 모드 누락, WCAG 대비 미달 탐지 |
| design:sync 구현 | `scripts/design-sync.js` | Figma Variables → tokens.json/css/ts 생성 (또는 Tokens Studio export 기반) |
| CI에 lint:tokens 추가 | workflow 수정 | 토큰 변경 PR에서 lint:tokens 실패 시 CI 실패 |

#### Week 6: lint:a11y + ui:impact

| 작업 | 산출물 | 검증 기준 |
|------|--------|-----------|
| Storybook addon-a11y 설정 | `.storybook/` 설정 | Storybook에서 a11y 패널 동작 |
| lint:a11y 구현 | `scripts/a11y-audit.js` | `pnpm lint:a11y` → critical/serious 위반 탐지 |
| ui:impact 구현 | `scripts/ui-impact.js` | 토큰 변경 → 영향받는 컴포넌트/화면 목록 출력 |
| CI에 lint:a11y + ui:impact 추가 | workflow 수정 | PR 코멘트에 영향 범위 리포트 자동 게시 |
| /impact 커스텀 명령 | `.claude/commands/impact.md` | Claude Code에서 `/impact` → 영향 분석 결과 |

**Sprint 3 종료 시 팀이 체감하는 것**:
- 토큰 바꾸면 "이 토큰을 쓰는 컴포넌트 3개, 화면 1개"가 자동으로 나온다
- 접근성 위반이 CI에서 자동으로 잡힌다
- Figma에서 토큰 바꾸면 `pnpm design:sync` 한 번으로 코드에 반영

---

### Sprint 4: VRT + Storybook 체계 (2주)

> **목표**: 시각적 변경을 자동으로 감지하고, 승인 워크플로가 동작하는 상태

#### Week 7: Storybook 체계 + Chromatic 설정

| 작업 | 산출물 | 검증 기준 |
|------|--------|-----------|
| Foundations 3종 자동 렌더 구현 | `src/storybook/foundations/` | Colors/Typography/Spacing 스토리가 토큰 파일을 순회하여 자동 렌더 |
| Chromatic 계정 + 프로젝트 설정 | Chromatic 대시보드 | `pnpm vrt:run` → Chromatic에 빌드 올라감 |
| 모드/뷰포트 매트릭스 설정 | `.storybook/preview.ts` | light/dark × mobile/desktop 스냅샷 생성 확인 |
| TurboSnap 설정 | Chromatic 설정 | 변경된 스토리만 스냅샷 캡처 (비용 최적화) |

#### Week 8: VRT CI 게이트 + pr-review hook

| 작업 | 산출물 | 검증 기준 |
|------|--------|-----------|
| vrt:run CI 통합 | workflow 수정 | PR에 Chromatic 빌드 링크 자동 첨부 |
| VRT 승인 게이트 | workflow 수정 | VRT 미승인 시 머지 불가 |
| pre-push hook 작성 | `.claude/hooks/pre-push.md` | push 전 스토리 존재 여부 경고 |
| pr-review hook 작성 | `.claude/hooks/pr-review.md` | CI 완료 후 VRT/Impact 종합 요약 코멘트 자동 생성 |

**Sprint 4 종료 시 팀이 체감하는 것**:
- 컴포넌트 수정하면 light/dark 모드의 시각적 변화가 자동으로 스냅샷됨
- VRT diff를 승인하지 않으면 머지할 수 없음
- PR에 리뷰 요약이 자동으로 달림

---

### Sprint 5: MCP 서버 + 통합 게이트 (2주)

> **목표**: Claude Code가 풍부한 컨텍스트로 분석하고, 최종 머지 게이트가 동작하는 상태

#### Week 9: OpenAPI Diff MCP + State Matrix MCP

| 작업 | 산출물 | 검증 기준 |
|------|--------|-----------|
| OpenAPI Diff MCP 구현 | `mcp-servers/openapi-diff/` | Claude Code에서 API 변경 분석 시 MCP tool 호출 확인 |
| State Matrix MCP 구현 | `mcp-servers/state-matrix/` | Claude Code에서 State Matrix 교차 검증 가능 |
| MCP 서버 연결 설정 | `.claude/mcp/servers.json` | Claude Code 실행 시 MCP 서버 자동 연결 |

#### Week 10: Chromatic MCP + merge-gate + 전체 통합

| 작업 | 산출물 | 검증 기준 |
|------|--------|-----------|
| Chromatic MCP 구현 | `mcp-servers/chromatic/` | pr-review hook에서 VRT 결과 요약 가능 |
| merge-gate.js 구현 | `scripts/ci/merge-gate.js` | DoD 미충족 PR 머지 시도 시 차단 |
| safety-net.yml 최종 통합 | `.github/workflows/safety-net.yml` | 전체 CI 파이프라인 한 번에 동작 |
| pr-create hook 고도화 | hook 수정 | MCP 서버 데이터를 활용한 정밀 분석 |

**Sprint 5 종료 시 팀이 체감하는 것**:
- 전체 안전망이 동작함
- Claude Code가 VRT 결과, API 변경, State Matrix를 종합하여 리뷰 요약을 제공
- DoD 미충족 PR은 물리적으로 머지 불가

---

### Sprint 6: 안정화 + 회고 (1주)

> **목표**: 전체 시스템 안정화, 불필요한 규칙 제거, 팀 피드백 반영

| 작업 | 내용 |
|------|------|
| 전체 회고 | 팀 전원 참여, 규칙별 유용성/불편함 투표 |
| false positive 정리 | CI에서 불필요하게 실패하는 케이스 수집 + 룰셋 조정 |
| 규칙 경량화 | 1 스프린트 동안 한 번도 트리거 안 된 체크 제거 후보 |
| 문서 업데이트 | 구현 과정에서 변경된 규정을 문서에 반영 |
| 성과 측정 | 도입 전/후 지표 비교 (API 불일치 빈도, PR 리뷰 시간 등) |

---

## 4. 스프린트별 검증 체크포인트

각 스프린트 끝에 반드시 확인하는 것.

| 스프린트 | 체크포인트 | 실패 시 |
|----------|------------|---------|
| Sprint 0 | Claude Code가 CLAUDE.md 규칙을 따르는가? | CLAUDE.md 문구 조정 |
| Sprint 1 | pr-create hook이 실제 PR에 유용한 코멘트를 남기는가? | hook 프롬프트 조정 또는 범위 축소 |
| Sprint 2 | FE가 실제로 api:codegen으로 생성된 타입을 사용하는가? | codegen 설정 조정 |
| Sprint 3 | ui:impact 리포트가 실제 영향 범위를 정확히 잡는가? | 탐지 로직 보강 또는 수동 보완 안내 |
| Sprint 4 | VRT가 의도치 않은 변경을 실제로 잡아내는가? | 스냅샷 전략 조정 (TurboSnap 범위 등) |
| Sprint 5 | 전체 파이프라인이 PR당 10분 이내에 완료되는가? | 병렬화 / 캐시 최적화 |
| Sprint 6 | 팀이 "이 도구가 도움이 된다"고 느끼는가? | 규칙 경량화 또는 접근 방식 전환 |

---

## 5. 리스크와 대응

### 5.1 기술 리스크

| 리스크 | 확률 | 영향 | 대응 |
|--------|------|------|------|
| Figma Variables API 접근 불가 (플랜 제한) | 중 | design:sync 구현 불가 | Tokens Studio JSON export로 대체 |
| Chromatic 비용이 예상보다 높음 | 중 | VRT 운영 비용 부담 | TurboSnap으로 스냅샷 수 최소화, 또는 Percy/Playwright VRT로 대체 |
| Claude Code hook이 너무 느림 | 낮 | 개발 경험 저하 | hook 범위 축소, 비동기 처리, 캐시 활용 |
| springdoc 자동 생성 스펙이 부정확 | 중 | api:lint false positive | 어노테이션 가이드 보강 + 린트 룰 조정 |
| oasdiff가 모든 breaking 변경을 탐지하지 못함 | 낮 | 동작 변경(behavioral) 누락 | PR 템플릿에 동작 변경 수동 체크 항목 유지 |

### 5.2 조직 리스크

| 리스크 | 확률 | 영향 | 대응 |
|--------|------|------|------|
| 팀이 도구를 귀찮아함 | 중 | 형식적 준수 또는 우회 | Phase 1에서 차단 아닌 제안으로 시작, 가치 체감 후 강화 |
| false positive가 잦아 신뢰 하락 | 중 | hook/lint 무시 | Sprint 6 회고에서 적극적 경량화, 룰셋 지속 조정 |
| State Matrix 작성이 오버헤드로 느껴짐 | 높 | 형식적 작성 또는 미작성 | 최초 2~3개는 함께 작성하여 습관화, /state-matrix 명령으로 초안 자동 생성 |
| 규정 문서가 너무 많아서 아무도 안 읽음 | 높 | 규정 무시 | 1장 요약만 공유, 나머지는 도구가 실행, 필요할 때 참조 문서로 안내 |

---

## 6. 기술 스택 요약

### 6.1 외부 도구/서비스

| 도구 | 용도 | 비용 | 대안 |
|------|------|------|------|
| Spectral | API 린트 | 무료 (OSS) | — |
| oasdiff | API diff + breaking 탐지 | 무료 (OSS) | optic, openapi-diff |
| openapi-typescript | 스펙 → FE 타입 | 무료 (OSS) | orval |
| Prism | Mock 서버 | 무료 (OSS) | MSW |
| Chromatic | VRT | 유료 (무료 티어 있음) | Percy, Playwright VRT |
| springdoc | OpenAPI 자동 생성 | 무료 (OSS) | — |
| Springwolf | AsyncAPI 자동 생성 | 무료 (OSS) | — |
| axe-playwright | 접근성 검사 | 무료 (OSS) | — |
| AsyncAPI CLI | AsyncAPI 검증 | 무료 (OSS) | — |

### 6.2 자체 구현

| 스크립트 | 언어 | 예상 코드량 |
|----------|------|-------------|
| lint-tokens.js | Node.js | ~200줄 |
| ui-impact.js | Node.js (TS Compiler API) | ~300줄 |
| a11y-audit.js | Node.js (Playwright) | ~150줄 |
| design-sync.js | Node.js (Figma API) | ~400줄 |
| ws-lint-custom.js | Node.js | ~100줄 |
| ws-codegen.js | Node.js | ~150줄 |
| merge-gate.js | Node.js | ~200줄 |
| MCP 서버 4종 | TypeScript | 각 ~200줄 |

**총 자체 구현량**: 약 2,300줄 (MCP 서버 포함)

---

## 7. 타임라인 요약

```
Week 0        Week 2        Week 4        Week 6        Week 8        Week 10       Week 11
  │             │             │             │             │             │             │
  ▼             ▼             ▼             ▼             ▼             ▼             ▼
Sprint 0     Sprint 1      Sprint 2      Sprint 3      Sprint 4      Sprint 5     Sprint 6
CLAUDE.md    Hook + CI     API 자동화     UI 자동화     VRT 체계      MCP + 통합    안정화
기반 설정     기본 게이트    타입 생성     토큰/a11y    Chromatic     최종 게이트    회고
             pre-commit     codegen      lint:tokens   VRT 승인      merge-gate
             pr-create      api:mock     ui:impact     pr-review     전체 통합
             api:lint       nullable     lint:a11y     모드 매트릭스
             api:diff       점검

         ◄─ Phase 1 ─►◄──── Phase 2 ────►◄──── Phase 3 ────►
           (제안만)        (점진적 강제)      (전체 가동)
```

---

## 8. 성공의 정의

11주 후 아래가 모두 참이면 성공이다.

- [ ] Claude Code에서 코드를 짜면 직접 값 대신 토큰이 사용된다
- [ ] PR을 올리면 10초 이내에 DoD 검증 코멘트가 달린다
- [ ] API가 변경되면 FE 타입이 자동으로 갱신된다
- [ ] 토큰을 바꾸면 영향받는 컴포넌트/화면 목록이 자동으로 나온다
- [ ] VRT 미승인 PR은 머지할 수 없다
- [ ] api:breaking PR은 FE 리뷰어 승인 없이 머지할 수 없다
- [ ] 팀원 과반수가 "이 도구가 도움이 된다"고 답한다
- [ ] "이 필드 nullable이에요?" 같은 질문이 도입 전 대비 절반 이하로 줄었다

---

## 변경 이력

| 버전 | 날짜 | 변경 요약 |
|------|------|-----------|
| v1.0 | 2025-03-08 | 초안 — 6 스프린트 구현 계획, 의존 관계, 리스크, 검증 체크포인트 |
