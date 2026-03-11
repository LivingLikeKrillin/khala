<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://img.shields.io/badge/⚙️_Karax-PR_Scope_Analyzer-blue?style=for-the-badge&labelColor=1a1a2e&color=4361ee">
    <img alt="Karax" src="https://img.shields.io/badge/⚙️_Karax-PR_Scope_Analyzer-blue?style=for-the-badge&labelColor=f0f0f0&color=4361ee">
  </picture>
</p>

<p align="center">
  <strong>파일 수가 아니라 논리적 응집도로 PR 범위를 판단한다.</strong><br>
  <sub>칼라(Khala)의 기술자 — 프로덕트 개발 워크플로 자동 검증 도구</sub>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/version-0.1.0-4361ee" alt="version">
  <img src="https://img.shields.io/badge/node-%3E%3D20-339933" alt="node">
  <img src="https://img.shields.io/badge/typescript-strict-3178c6" alt="typescript">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="license">
</p>

---

## 문제

같은 "파일 7개 변경"이 완전히 다른 의미를 가진다.

```
Spring Boot — User CRUD 추가
  entity/User.kt, repository/UserRepository.kt, service/UserService.kt,
  controller/UserController.kt, dto/UserRequest.kt, dto/UserResponse.kt,
  test/UserServiceTest.kt

  → 7개 파일, 하나의 논리적 변경. 완전히 정상.
```

```
Next.js — 대시보드 + API + 인증
  app/dashboard/page.tsx, app/dashboard/layout.tsx,
  app/api/dashboard/route.ts, components/dashboard/StatsCard.tsx,
  components/dashboard/Chart.tsx, lib/auth/middleware.ts, lib/auth/session.ts

  → 7개 파일, 3개 관심사가 섞여 있다. 리뷰어가 놓칠 수밖에 없다.
```

기존 도구들은 **파일 수나 diff 라인**으로만 판단한다. Karax는 **프레임워크의 개발 패턴을 이해하고**, 변경이 하나의 논리적 단위인지를 판단한다.

---

## 어떻게 동작하는가

```
변경 파일 수집 (git diff)
       │
       ▼
플랫폼 프로파일로 각 파일에 역할(role) 부여
  controller/UserController.kt  →  controller
  entity/User.kt                →  entity
  lib/auth/middleware.ts         →  middleware
       │
       ▼
응집 그룹(Cohesion Group) 매칭
  같은 도메인/라우트에 속하는 파일들  →  하나의 논리적 변경
  서로 다른 관심사에 걸치는 파일들    →  관심사 혼재 감지
       │
       ▼
판단
  ✅ 정상      1~2개 그룹, 임계치 이내       아무 말도 안 함
  ⚠️ 주의      2개 그룹 + 관심사 혼재         "분리를 권장합니다"
  🔶 경고      3개 이상 그룹                  "분할을 고려하세요" + 분할 제안
  🔴 강력 경고  4개 이상 그룹 + diff 초과       "여러 PR로 나눠야 합니다"
```

**정상일 때는 아무 말도 하지 않는다.** 노이즈는 신뢰를 죽인다.

---

## 빠른 시작

### 설치

```bash
pnpm add -D karax
```

### 실행

```bash
# 현재 브랜치의 변경 범위 분석
npx karax check

# 기준 브랜치 지정
npx karax check --base origin/develop

# CI용 간략 출력
npx karax check --format brief --silent

# 에이전트/파이프라인용 JSON
npx karax check --format json
```

### 출력 예시

범위가 벗어났을 때:

```
🔶 Karax — PR 범위 경고

현재 변경이 3개의 서로 다른 관심사에 걸쳐 있습니다.

  그룹 1: domain-crud — User (6개 파일)
    - entity/User.kt, repository/UserRepository.kt, service/UserService.kt,
      controller/UserController.kt, dto/UserRequest.kt, dto/UserResponse.kt

  그룹 2: migration — migrationGroup (2개 파일)
    - resources/db/migration/V3__add_user_table.sql
    - resources/db/migration/V4__add_user_index.sql

  그룹 3: config-change — configGroup (2개 파일)
    - config/SecurityConfig.kt, config/JwtConfig.kt

제안하는 분할:
  PR 1: migration — migrationGroup (2개 파일)
  PR 2: config-change — configGroup (2개 파일)
  PR 3: domain-crud — User (6개 파일)
```

정상일 때: **아무 출력 없음.** (`--silent` 없이도 ok이면 간단한 요약만 출력)

---

## 설정

프로젝트 루트에 `karax.config.ts`를 만들면 된다.

```typescript
// karax.config.ts
export default {
  // 플랫폼 자동 감지 오버라이드
  platform: 'spring-boot',

  // 임계치 조정
  thresholds: {
    maxFilesPerPr: 25,
    maxDiffLinesPerPr: 1000,
  },

  // 분석에서 제외할 파일
  ignore: ['generated/', '*.lock'],

  // info 이상만 표시
  severity: {
    minLevel: 'info',
  },
};
```

설정 파일이 없으면 프로젝트 파일 구조를 보고 **플랫폼을 자동 감지**한다.

| 감지 기준 | 플랫폼 |
|-----------|--------|
| `build.gradle.kts` / `pom.xml` | Spring Boot |
| `next.config.*` | Next.js |
| `vite.config.*` + `src/pages/` | React SPA |
| `package.json` dependencies | 추가 판단 |

---

## 플랫폼 프로파일

각 프로파일은 "이 프레임워크에서 하나의 논리적 변경이 어떤 파일 패턴으로 나타나는가"를 정의한다.

### Spring Boot

| 응집 그룹 | 구성 역할 | 경고하지 않는 예 |
|-----------|-----------|-----------------|
| **domain-crud** | entity, repository, service, controller, dto, mapper, exception, test | User CRUD 7개 파일 |
| **config-change** | config | SecurityConfig + JwtConfig |
| **migration** | migration, entity, repository | V3, V4 마이그레이션 + Entity |

혼재 경고: `migration + controller`, `config + service`

### Next.js

| 응집 그룹 | 구성 역할 | 경고하지 않는 예 |
|-----------|-----------|-----------------|
| **page-feature** | page, layout, loading, error, component, hook, style, story, test | 대시보드 페이지 + 전용 컴포넌트 |
| **shared-component** | component, story, test, style | Button 컴포넌트 + 스토리 |
| **api-route** | api-route, lib, test | /api/users 라우트 + 헬퍼 |

혼재 경고: `api-route + page`, `middleware + component`, `lib + page`

### React SPA

| 응집 그룹 | 구성 역할 | 경고하지 않는 예 |
|-----------|-----------|-----------------|
| **feature** | page, component, hook, store, style, story, test | 대시보드 기능 전체 |
| **design-system** | token, component, story, style | 디자인 토큰 + 컴포넌트 |
| **api-layer** | api-client, test | API 클라이언트 변경 |

혼재 경고: `token + page`, `store + component`

---

## CI 연동

### GitHub Actions

```yaml
name: PR Scope Check
on: [pull_request]

jobs:
  scope-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: pnpm/action-setup@v4
      - run: pnpm install
      - run: npx karax check --base origin/main --format brief --silent
```

`--silent`을 붙이면 정상 PR은 아무 출력 없이 통과하고, 범위가 벗어난 PR만 실패한다.

### Claude Code

```
/check-scope     — 현재 변경의 PR 범위 확인
/split-pr        — PR 분할 가이드
/state-matrix    — State Matrix 생성
```

Claude Code의 hooks를 통해 작업 중 실시간으로 범위를 감시한다. PR을 만들기 직전에 자동 검증도 수행한다.

---

## 설계 원칙

1. **파일 수가 아니라 논리적 응집도로 판단한다** — 같은 7개 파일이라도 Spring Boot에서는 정상이고 Next.js에서는 비정상일 수 있다.
2. **정상일 때는 아무 말도 하지 않는다** — 노이즈는 신뢰를 죽인다.
3. **경고할 때는 분할 방법까지 제안한다** — "크다"만 말하면 쓸모없다.
4. **코드로 강제할 수 있는 건 hook으로, 나머지만 프롬프트로** — 3계층 원칙.

---

## 아키텍처

```
karax/
├── src/                     코어 엔진 (CI 독립 실행)
│   ├── core/
│   │   ├── scope-analyzer   PR 범위 + 응집 그룹 분석
│   │   └── config-loader    karax.config.ts 로더
│   ├── profiles/
│   │   ├── spring-boot      Spring Boot 프로파일
│   │   ├── nextjs           Next.js 프로파일
│   │   ├── react-spa        React SPA 프로파일
│   │   └── detector         플랫폼 자동 감지
│   ├── cli/                 npx karax check
│   └── utils/               Logger, glob 매칭
├── .claude/                 Claude Code 어댑터
│   ├── hooks, agents, skills, rules
└── tests/                   34개 테스트
```

**하이브리드 구조**: 코어 엔진(`src/`)이 모든 가치의 실체이고, `.claude/`는 그 엔진을 Claude Code에서 편하게 쓰게 해주는 레이어다.

---

## 로드맵

| 버전 | 핵심 기능 | 상태 |
|------|-----------|------|
| **v0.1** | PR 범위 분석 + 플랫폼 프로파일 | **현재** |
| v0.2 | API 스펙 린트/diff + 테스트/리뷰 서브에이전트 | |
| v0.3 | MCP 서버 (Claude Code 연동 강화) | |
| v0.4 | 칼라 연동 — 맥락 기반 리뷰/트러블슈팅 | |
| v0.5+ | UI 확장팩 (토큰/VRT/접근성) | |

---

## 개발

```bash
pnpm install          # 의존성 설치
pnpm test             # 테스트 (watch)
pnpm test:run         # 테스트 (1회)
pnpm typecheck        # 타입 체크
pnpm build            # 빌드
```

---

## 이름의 유래

> 카락스(Karax)는 스타크래프트 프로토스의 위상 기술자(Phase-smith)다.
> 전장에서 구조물을 수리하고, 시스템을 진단하고, 기술적 문제를 해결한다.
>
> 이 도구도 같은 일을 한다 — 코드베이스의 구조적 건강을 진단하고,
> 문제가 커지기 전에 알려준다.

---

## 라이선스

MIT
