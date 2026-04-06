# Probe v0.1 — 범위 정의

> **핵심 가치**: 개발 중에 "지금 이 작업이 PR 하나로 리뷰 가능한 범위인가?"를 알려준다.
> **차별점**: 플랫폼/프레임워크별 개발 패턴을 이해하고, 그 맥락에서 판단한다.

---

## 0. v0.1이 하는 일 — 한 문장

**개발자가 코드를 짜는 동안, 변경이 리뷰 가능한 PR 단위를 넘어서면 경고하고, 어떻게 쪼갤 수 있는지 제안한다.**

---

## 1. 왜 플랫폼별 인식이 필요한가

### 같은 "파일 7개 변경"이 다른 의미를 가진다

**Spring Boot — 사용자 CRUD 추가**
```
변경 파일:
  src/main/kotlin/entity/User.kt              (Entity)
  src/main/kotlin/repository/UserRepository.kt (Repository)
  src/main/kotlin/service/UserService.kt       (Service)
  src/main/kotlin/controller/UserController.kt (Controller)
  src/main/kotlin/dto/UserRequest.kt           (DTO)
  src/main/kotlin/dto/UserResponse.kt          (DTO)
  src/test/kotlin/service/UserServiceTest.kt   (Test)

→ 파일 7개, 하나의 논리적 변경. 완전히 정상적인 PR 크기.
```

**Next.js — 대시보드 페이지 + 인증 로직 + API 라우트**
```
변경 파일:
  app/dashboard/page.tsx                       (Page)
  app/dashboard/layout.tsx                     (Layout)
  app/api/dashboard/route.ts                   (API Route)
  components/dashboard/StatsCard.tsx            (Component)
  components/dashboard/Chart.tsx                (Component)
  lib/auth/middleware.ts                        (Auth)
  lib/auth/session.ts                           (Auth)

→ 파일 7개, 하지만 대시보드 UI + API + 인증이 섞여 있다.
  이건 2~3개 PR로 나눠야 한다.
```

**핵심**: 파일 수가 아니라 **변경의 논리적 응집도**가 PR 범위의 판단 기준이다.

---

## 2. 플랫폼 프로파일 (Platform Profile)

Probe는 프레임워크별 "개발 패턴"을 프로파일로 정의한다.
프로파일은 해당 프레임워크에서 하나의 논리적 변경이 통상 어떤 파일 패턴으로 나타나는지를 기술한다.

### 2.1 프로파일 구조

```typescript
interface PlatformProfile {
  /** 프로파일 이름 */
  name: string;  // 'spring-boot', 'nextjs', 'react-spa', etc.

  /** 파일 패턴 → 역할(role) 매핑 */
  fileRoles: FileRolePattern[];

  /** 논리적 변경 단위 (Cohesion Group) 정의 */
  cohesionGroups: CohesionGroup[];

  /** PR 크기 임계치 (이 프로파일 기준) */
  thresholds: PrThresholds;
}
```

### 2.2 Spring Boot 프로파일

```typescript
const springBoot: PlatformProfile = {
  name: 'spring-boot',

  // 파일 경로 → 역할 매핑
  fileRoles: [
    { pattern: '**/entity/**',       role: 'entity' },
    { pattern: '**/repository/**',   role: 'repository' },
    { pattern: '**/service/**',      role: 'service' },
    { pattern: '**/controller/**',   role: 'controller' },
    { pattern: '**/dto/**',          role: 'dto' },
    { pattern: '**/config/**',       role: 'config' },
    { pattern: '**/exception/**',    role: 'exception' },
    { pattern: '**/mapper/**',       role: 'mapper' },
    { pattern: '*test*/**',          role: 'test' },
    { pattern: '**/resources/db/migration/**', role: 'migration' },
    { pattern: '**/resources/application*',    role: 'config' },
  ],

  // 하나의 논리적 변경으로 인정되는 파일 역할 조합
  cohesionGroups: [
    {
      name: 'domain-crud',
      description: '도메인 엔티티 CRUD (정상적인 단일 PR)',
      roles: ['entity', 'repository', 'service', 'controller', 'dto', 'mapper', 'test'],
      // 하나의 도메인(User, Order 등)에 속하는 파일들이면 응집
      cohesionKey: 'domainName',  // 파일 경로에서 도메인명을 추출하여 그룹핑
      maxFiles: 15,
    },
    {
      name: 'config-change',
      description: '설정 변경',
      roles: ['config'],
      maxFiles: 5,
    },
    {
      name: 'migration',
      description: 'DB 마이그레이션',
      roles: ['migration', 'entity', 'repository'],
      maxFiles: 10,
    },
  ],

  thresholds: {
    // Spring Boot에서는 레이어별 파일이 많아지므로 임계치가 높다
    maxFilesPerPr: 20,
    maxDiffLinesPerPr: 800,
    // 2개 이상의 도메인이 섞이면 경고
    maxCohesionGroups: 2,
    // 이 조합이면 "쪼개세요" 경고
    mixedConcerns: [
      { roles: ['migration', 'controller'], reason: 'DB 마이그레이션과 API 변경은 분리하세요' },
      { roles: ['config', 'service'], reason: '설정 변경과 비즈니스 로직 변경은 분리하세요' },
    ],
  },
};
```

### 2.3 Next.js 프로파일

```typescript
const nextjs: PlatformProfile = {
  name: 'nextjs',

  fileRoles: [
    { pattern: 'app/**/page.tsx',       role: 'page' },
    { pattern: 'app/**/layout.tsx',     role: 'layout' },
    { pattern: 'app/**/loading.tsx',    role: 'loading' },
    { pattern: 'app/**/error.tsx',      role: 'error' },
    { pattern: 'app/api/**',           role: 'api-route' },
    { pattern: 'components/**',        role: 'component' },
    { pattern: 'lib/**',              role: 'lib' },
    { pattern: 'hooks/**',            role: 'hook' },
    { pattern: 'styles/**',           role: 'style' },
    { pattern: '**/*.stories.*',       role: 'story' },
    { pattern: '**/*.test.*',          role: 'test' },
    { pattern: '**/middleware.*',       role: 'middleware' },
  ],

  cohesionGroups: [
    {
      name: 'page-feature',
      description: '페이지 단위 기능 (page + 전용 component + hook)',
      roles: ['page', 'layout', 'loading', 'error', 'component', 'hook', 'style', 'story', 'test'],
      cohesionKey: 'routeSegment',  // app/ 하위 경로로 그룹핑
      maxFiles: 12,
    },
    {
      name: 'shared-component',
      description: '공유 컴포넌트 변경',
      roles: ['component', 'story', 'test', 'style'],
      maxFiles: 6,
    },
    {
      name: 'api-route',
      description: 'API 라우트',
      roles: ['api-route', 'lib', 'test'],
      maxFiles: 5,
    },
  ],

  thresholds: {
    // 프론트엔드는 파일당 변경량이 적은 대신 파일 수가 적어도 범위가 넓을 수 있음
    maxFilesPerPr: 15,
    maxDiffLinesPerPr: 600,
    maxCohesionGroups: 2,
    mixedConcerns: [
      { roles: ['api-route', 'page'], reason: 'API 라우트와 페이지 UI 변경은 분리를 권장합니다' },
      { roles: ['middleware', 'component'], reason: '인증/미들웨어와 UI 컴포넌트는 분리하세요' },
      { roles: ['lib', 'page'], reason: '공유 라이브러리 변경과 페이지 변경은 분리를 권장합니다' },
    ],
  },
};
```

### 2.4 React SPA 프로파일

```typescript
const reactSpa: PlatformProfile = {
  name: 'react-spa',

  fileRoles: [
    { pattern: 'src/pages/**',         role: 'page' },
    { pattern: 'src/components/**',    role: 'component' },
    { pattern: 'src/hooks/**',         role: 'hook' },
    { pattern: 'src/api/**',           role: 'api-client' },
    { pattern: 'src/store/**',         role: 'store' },
    { pattern: 'src/utils/**',         role: 'util' },
    { pattern: 'src/styles/**',        role: 'style' },
    { pattern: 'src/design-tokens/**', role: 'token' },
    { pattern: '**/*.stories.*',       role: 'story' },
    { pattern: '**/*.test.*',          role: 'test' },
  ],

  cohesionGroups: [
    {
      name: 'feature',
      description: '기능 단위 (page + components + hook + store)',
      roles: ['page', 'component', 'hook', 'store', 'style', 'story', 'test'],
      cohesionKey: 'featureName',
      maxFiles: 12,
    },
    {
      name: 'design-system',
      description: '디자인 시스템 변경 (토큰 + 컴포넌트 + 스토리)',
      roles: ['token', 'component', 'story', 'style'],
      maxFiles: 10,
    },
    {
      name: 'api-layer',
      description: 'API 클라이언트 변경',
      roles: ['api-client', 'test'],
      maxFiles: 5,
    },
  ],

  thresholds: {
    maxFilesPerPr: 15,
    maxDiffLinesPerPr: 500,
    maxCohesionGroups: 2,
    mixedConcerns: [
      { roles: ['token', 'page'], reason: '토큰 변경과 화면 변경은 분리하세요 (Additive-first)' },
      { roles: ['store', 'component'], reason: '상태 관리 변경과 UI 변경은 분리를 권장합니다' },
    ],
  },
};
```

### 2.5 프로파일 자동 감지

Probe는 프로젝트 루트의 파일을 보고 프로파일을 자동으로 추론한다.

```
build.gradle.kts 또는 pom.xml    → spring-boot
next.config.*                     → nextjs
vite.config.* + src/pages/        → react-spa
package.json의 dependencies 분석  → 추가 판단
```

수동 지정도 가능:
```typescript
// probe.config.ts
export default {
  platform: 'spring-boot',  // 또는 'nextjs', 'react-spa', 'custom'
  // ...
};
```

---

## 3. PR 범위 분석 로직

### 3.1 분석 단계

```
1. 변경 파일 목록 수집 (git diff / staged files)
       │
2. 플랫폼 프로파일로 각 파일에 역할(role) 부여
       │
3. 응집 그룹(Cohesion Group) 매칭
       │
       ├─ 같은 그룹에 속하는 파일들 → 하나의 논리적 변경
       └─ 여러 그룹에 걸치는 파일들 → 관심사 혼재 감지
       │
4. 판단
       ├─ 정상: 1~2개 그룹, 임계치 이내
       ├─ 경고: 2개 그룹 + mixedConcerns 해당
       └─ 강력 경고: 3개 이상 그룹 또는 임계치 초과
       │
5. 분할 제안 생성
       └─ "이 파일들은 별도 PR로 분리할 수 있습니다"
```

### 3.2 경고 레벨

| 레벨 | 조건 | 메시지 톤 |
|------|------|-----------|
| ✅ 정상 | 1~2개 cohesion group, 임계치 이내 | 없음 (아무 말 안 함) |
| ⚠️ 주의 | 2개 group + mixedConcerns 해당 | "분리를 권장합니다" |
| 🔶 경고 | 3개 이상 group 또는 파일 수 임계치 초과 | "리뷰가 어려울 수 있습니다. 분할을 고려하세요" |
| 🔴 강력 경고 | 4개 이상 group + diff 라인 임계치 초과 | "이 변경은 여러 PR로 나눠야 합니다" |

### 3.3 분할 제안 예시

```
🔶 Probe — PR 범위 경고

현재 변경이 3개의 서로 다른 관심사에 걸쳐 있습니다.

  그룹 1: User 도메인 CRUD (6개 파일)
    - entity/User.kt, repository/UserRepository.kt, service/UserService.kt,
      controller/UserController.kt, dto/UserRequest.kt, dto/UserResponse.kt

  그룹 2: DB 마이그레이션 (2개 파일)
    - resources/db/migration/V3__add_user_table.sql
    - resources/db/migration/V4__add_user_index.sql

  그룹 3: 인증 설정 변경 (2개 파일)
    - config/SecurityConfig.kt
    - config/JwtConfig.kt

제안하는 분할:
  PR 1: DB 마이그레이션 (V3, V4) — 먼저 머지
  PR 2: User 도메인 CRUD — 마이그레이션 이후
  PR 3: 인증 설정 변경 — 독립적으로 분리 가능
```

---

## 4. v0.1 전체 기능 범위

### 4.1 포함 (v0.1)

| 기능 | 설명 | 형태 |
|------|------|------|
| **플랫폼 프로파일** | spring-boot, nextjs, react-spa 3종 내장 | 코어 로직 |
| **프로파일 자동 감지** | 프로젝트 파일 기반 플랫폼 추론 | 코어 로직 |
| **PR 범위 분석** | 변경 파일 → 역할 부여 → 응집 분석 → 경고/제안 | 코어 로직 |
| **Claude Code hook: 실시간 모니터** | 작업 중 변경 파일이 쌓일 때 범위 경고 | hook |
| **Claude Code hook: pr-create** | PR 생성 시 최종 범위 검증 + DoD 체크 | hook |
| **CLI: `probe check`** | 현재 브랜치의 변경을 분석하여 리포트 출력 | CLI |
| **설정: `probe.config.ts`** | 플랫폼, 경로, 임계치 커스터마이징 | 설정 파일 |

### 4.2 미포함 (v0.2 이후)

| 기능 | 예정 버전 |
|------|-----------|
| api:lint (Spectral 연동) | v0.2 |
| api:diff (oasdiff 연동) | v0.2 |
| lint:tokens (토큰 검증) | v0.3 |
| ui:impact (영향 범위 분석) | v0.3 |
| MCP 서버 | v0.4 |
| VRT 연동 | v0.5 |
| 칼라 연동 | v1.0 |

### 4.3 미포함이지만 인터페이스만 정의 (v0.1)

| 인터페이스 | 이유 |
|------------|------|
| `KhalaClient` | 칼라 연동 구조를 미리 확보. 구현은 mock/stub |
| `McpToolSchema` | MCP 서버 tool 스키마 미리 확보. 실제 서버는 v0.4 |
| `PlatformProfile` | 커스텀 프로파일 추가를 위한 인터페이스 공개 |

---

## 5. probe.config.ts 최소 스펙 (v0.1)

```typescript
export interface ProbeConfig {
  /** 플랫폼 프로파일 (자동 감지 또는 수동 지정) */
  platform?: 'spring-boot' | 'nextjs' | 'react-spa' | 'custom';

  /** 커스텀 프로파일 (platform: 'custom' 시) */
  customProfile?: PlatformProfile;

  /** 프로파일 임계치 오버라이드 */
  thresholds?: Partial<PrThresholds>;

  /** 무시할 파일 패턴 */
  ignore?: string[];

  /** 경고 레벨 설정 */
  severity?: {
    /** 범위 경고 최소 레벨 (이 레벨 이상만 표시) */
    minLevel?: 'info' | 'warn' | 'error';
  };
}
```

---

## 6. 사용자 경험 시나리오

### 시나리오 1: Spring Boot 개발자가 작업 중 범위를 넘어감

```
개발자: (User CRUD를 만들다가 SecurityConfig도 고치기 시작)

⚙️ Probe: 현재 작업이 2개 관심사에 걸쳐 있습니다.
  - User 도메인 CRUD (6개 파일)
  - 인증 설정 변경 (1개 파일)
  인증 설정 변경은 별도 PR로 분리하는 것을 권장합니다.

개발자: (무시하고 계속 작업, Order 도메인도 건드리기 시작)

🔶 Probe: PR 범위 경고 — 3개 관심사가 섞여 있습니다.
  1. User 도메인 CRUD (6개 파일)
  2. 인증 설정 변경 (1개 파일)
  3. Order 도메인 변경 (2개 파일)
  이 변경은 리뷰어가 한 번에 파악하기 어렵습니다.
  제안: User CRUD → 인증 설정 → Order 변경 순으로 3개 PR로 분할
```

### 시나리오 2: Next.js 개발자가 페이지 + API + 미들웨어를 한 번에

```
개발자: (대시보드 페이지를 만들면서 API 라우트와 인증 미들웨어도 수정)

⚠️ Probe: API 라우트와 페이지 UI 변경은 분리를 권장합니다.
  - 대시보드 페이지 (page.tsx, layout.tsx, StatsCard.tsx) — 4개 파일
  - API 라우트 (app/api/dashboard/route.ts) — 1개 파일
  - 인증 미들웨어 (middleware.ts, lib/auth/session.ts) — 2개 파일
  제안: 미들웨어 → API 라우트 → 페이지 UI 순으로 분할
```

### 시나리오 3: 정상 범위 — 아무 말도 안 함

```
개발자: (User CRUD만 깔끔하게 작업)

(Probe: 아무 경고 없음. 정상 범위.)

개발자: probe check

✅ 현재 변경: User 도메인 CRUD (7개 파일, +280줄)
   응집도: 높음 (단일 도메인, 단일 관심사)
   PR 크기: 정상 범위
```

---

## 7. 구현 우선순위

| 순서 | 구현 대상 | 예상 코드량 |
|------|-----------|-------------|
| 1 | `PlatformProfile` 타입 정의 + 3종 내장 프로파일 | ~300줄 |
| 2 | 프로파일 자동 감지 로직 | ~100줄 |
| 3 | 파일 → 역할 매핑 엔진 | ~150줄 |
| 4 | 응집 그룹 분석 엔진 | ~300줄 |
| 5 | 경고 레벨 판단 + 분할 제안 생성 | ~200줄 |
| 6 | CLI: `probe check` | ~100줄 |
| 7 | Claude Code hook: pr-create | ~150줄 (프롬프트) |
| 8 | Claude Code hook: 실시간 모니터 | ~100줄 (프롬프트) |
| 9 | `probe.config.ts` 로더 | ~100줄 |
| 10 | 테스트 (core 로직) | ~400줄 |

**총 예상**: ~1,900줄 (테스트 포함)

---

## 8. 로드맵 (v0.1 이후)

```
v0.1  PR 범위 분석 + 플랫폼 프로파일          ← 지금
v0.2  API 스펙 린트 + diff (Spectral, oasdiff)
v0.3  토큰 린트 + UI 영향 분석
v0.4  MCP 서버 (Claude Code 연동 강화)
v0.5  VRT 연동 + 접근성 검사
v1.0  칼라 연동 — 맥락 기반 리뷰/트러블슈팅
```

---

## 변경 이력

| 버전 | 날짜 | 변경 |
|------|------|------|
| v0.1-draft | 2025-03-08 | 초안 — 플랫폼 인식 PR 범위 분석 중심으로 재정의 |
