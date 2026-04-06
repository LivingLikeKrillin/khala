<p align="center">
  <img src="https://img.shields.io/badge/TypeScript-strict-3178C6?style=for-the-badge&logo=typescript&logoColor=white" />
  <img src="https://img.shields.io/badge/Node.js-%3E%3D20-339933?style=for-the-badge&logo=node.js&logoColor=white" />
  <img src="https://img.shields.io/badge/MCP-Server-4361ee?style=for-the-badge" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" />
</p>

<h1 align="center">Probe</h1>

<p align="center">
  <strong>Platform-Aware PR Analyzer + API Contract Validator</strong><br/>
  플랫폼별 응집도 기반 PR 범위 분석, API 스펙 린트/diff, 리뷰 체크리스트 자동 생성
</p>

---

## What is Probe?

Probe는 PR의 범위, API 계약, 리뷰 체크리스트를 자동으로 검증하는 도구입니다.

코드 리뷰에서 반복되는 세 가지 문제를 해결합니다:

**1. "이 PR 범위가 적절한가?"**

같은 7개 파일이 Spring Boot에서는 정상이고 Next.js에서는 분할 대상이다. 파일 수로 판단하면 오판한다.

**2. "API 변경이 하위 호환인가?"**

nullable 누락, 에러 응답 불일치, breaking change가 리뷰에서 빠진다.

**3. "이 변경이 규정에 맞는가?"**

조직의 가이드라인이 있어도 리뷰어가 매번 기억하고 대조하기 어렵다.

---

## Probe가 하는 일

```
변경 파일 수집 (git diff)
       ↓
플랫폼 프로파일로 역할 부여                    ← v0.1
  controller/UserController.kt → controller
  lib/auth/middleware.ts        → middleware
       ↓
응집 그룹 매칭 → severity 판단 → 분할 제안      ← v0.1
       ↓
API 스펙 린트 (10개 룰) + diff (breaking 감지)  ← v0.2
       ↓
PR 타입 추론 → DoD 체크리스트 자동 생성          ← v0.2
       ↓
MCP 서버로 Claude Code에 도구 노출              ← v0.3
       ↓
칼라 연동: 규정 검색 + 영향 분석 + 설계-관측 갭   ← v0.4
```

---

## 빠른 시작

### 설치

```bash
pnpm add -D probe
```

### 핵심 명령어

```bash
# PR 범위 분석 + 리뷰 체크리스트
npx probe check

# API 스펙 린트 (10개 내장 룰)
npx probe api:lint api/openapi.json

# API 스펙 diff (breaking change 감지)
npx probe api:diff --base origin/main

# 리뷰 체크리스트 생성
npx probe review

# 칼라 지식베이스 검색
npx probe khala:search "payment-service 규정"

# 서비스 영향 분석
npx probe khala:impact

# 칼라 연결 상태
npx probe khala:status
```

### 출력 포맷

```bash
npx probe check                  # markdown (기본)
npx probe check --format json    # JSON (에이전트/파이프라인용)
npx probe check --format brief   # 한 줄 요약 (CI용)
npx probe check --silent         # 정상이면 출력 없음
```

---

## 사용 시나리오

### "PR 올리기 전에 범위 확인하고 싶다"

```bash
npx probe check
```

변경 파일을 플랫폼에 맞게 분석해서, 관심사가 섞여 있으면 분할을 제안한다.
정상이면 아무 말도 안 한다.

### "API 스펙 바꿨는데 빠뜨린 게 없나 확인하고 싶다"

```bash
npx probe api:lint api/openapi.json     # 스펙 자체 검사 (nullable, 네이밍 등)
npx probe api:diff --base origin/main   # main 대비 breaking change 감지
```

### "PR 리뷰 올릴 때 체크리스트를 자동으로 만들고 싶다"

```bash
npx probe review
```

변경 파일의 역할(CRUD, 마이그레이션, UI 등)을 보고 PR 타입을 추론한 뒤, 해당 타입에 맞는 리뷰 체크리스트를 생성한다.

### "Claude Code에서 대화하면서 자동으로 검증받고 싶다"

`.mcp.json`에 Probe MCP 서버를 등록하면, Claude Code가 대화 맥락에 따라 범위 분석·API 린트·체크리스트를 알아서 호출한다. 자세한 설정은 [CI 연동 > Claude Code](#claude-code) 참조.

### "칼라 지식베이스에서 관련 규정을 찾고 싶다"

```bash
npx probe khala:search "결제 서비스 에러 처리 규정"
npx probe khala:impact   # 현재 변경이 영향을 주는 서비스 분석
```

칼라가 연결되어 있으면 리뷰 결과에 관련 규정과 영향 범위가 자동으로 붙는다. 칼라 없이도 나머지 기능은 전부 동작한다.

---

## 기능 상세

### v0.1 — PR 범위 분석

변경 파일을 플랫폼별 패턴으로 분류하고, 논리적 응집도로 PR 범위를 판단한다.

```
🔶 Probe — PR 범위 경고

현재 변경이 3개의 서로 다른 관심사에 걸쳐 있습니다.

  그룹 1: domain-crud — User (6개 파일)
  그룹 2: migration — migrationGroup (2개 파일)
  그룹 3: config-change — configGroup (2개 파일)

제안하는 분할:
  PR 1: migration — migrationGroup (2개 파일)
  PR 2: config-change — configGroup (2개 파일)
  PR 3: domain-crud — User (6개 파일)
```

**정상일 때는 아무 말도 하지 않는다.** 노이즈는 신뢰를 죽인다.

### v0.2 — API 계약 검증 + 리뷰 체크리스트

**10개 내장 린트 룰:**

| 룰 | 검사 내용 |
|----|----------|
| `probe/field-type` | 필드 타입 정합성 |
| `probe/nullable` | nullable 명시 여부 |
| `probe/error-response` | 에러 응답 스키마 준수 |
| `probe/path-naming` | 경로 kebab-case 규칙 |
| `probe/field-naming` | 필드 camelCase 규칙 |
| `probe/pagination` | 목록 API 페이지네이션 |
| `probe/example-required` | example 값 존재 |
| `probe/enum-example` | enum 정의 + example |
| `probe/deprecated` | deprecated 라이프사이클 |
| `probe/request-body-type` | request body 타입 |

**PR 타입별 체크리스트 자동 생성:**

```
📋 리뷰 체크리스트 (domain-crud):
  ✅ 서비스 테스트 존재 (자동 검증 통과)
  ☐ Entity 필드와 DTO 필드 매핑 확인
  ☐ Repository 쿼리 성능 검토
  ☐ Controller 입력 검증 확인
```

10개 PR 타입 지원: `domain-crud`, `api-change`, `ui-feature`, `ui-component`, `config-change`, `db-migration`, `design-system`, `test-only`, `docs-only`, `general`

### v0.3 — MCP 서버

Claude Code에서 자연어 대화 중 Probe 분석을 **자동으로** 호출한다.

```json
// .mcp.json
{
  "mcpServers": {
    "probe": {
      "command": "node",
      "args": ["dist/mcp/server.js"],
      "cwd": "."
    }
  }
}
```

**6개 MCP 도구:**

| 도구 | 설명 |
|------|------|
| `probe.analyzeScope` | PR 범위 분석 |
| `probe.lintApiSpec` | API 스펙 린트 |
| `probe.diffApiSpecs` | API 스펙 diff |
| `probe.reviewChecklist` | 리뷰 체크리스트 생성 |
| `probe.detectPlatform` | 플랫폼 감지 |
| `probe.queryKhala` | 칼라 지식베이스 질의 |

**3개 리소스:** 프로파일 정보, 설정, 가이드라인
**2개 프롬프트:** 구조화된 PR 리뷰, PR 분할 가이드

### v0.4 — 칼라(Khala) 연동

칼라 RAG 시스템과 연동하여 리뷰에 맥락을 추가한다.

```
사용자: "PR 리뷰해줘"

Probe:
  범위 OK, API 린트 통과, 체크리스트 5개 항목
  + 📎 관련 규정: "nullable 필드 표기 의무" (규정 ② 2.3.1)
  + 📎 영향 서비스: order-service, notification-service
  + ⚠️ 설계-관측 갭: payment → inventory 호출이 트레이스에 없음
```

**칼라가 없어도 기존 기능은 100% 동작한다.** 칼라가 있으면 결과가 풍부해진다.

---

## 설정

```typescript
// probe.config.ts
export default {
  // 플랫폼 (자동 감지 오버라이드)
  platform: 'spring-boot',

  // 임계치 조정
  thresholds: {
    maxFilesPerPr: 25,
    maxDiffLinesPerPr: 1000,
  },

  // 분석 제외
  ignore: ['generated/', '*.lock'],

  // API 설정
  api: {
    specPath: 'api/openapi.json',
    disableRules: ['probe/example-required'],
  },

  // 리뷰 설정
  review: {
    disableChecklists: ['docs-only'],
  },

  // 칼라 연동
  khala: {
    baseUrl: 'http://localhost:8000',
    timeoutMs: 3000,
    disabled: false,
  },
};
```

**환경 변수로도 칼라 연동 가능:**

```
KHALA_BASE_URL=http://localhost:8000
KHALA_TIMEOUT_MS=3000
KHALA_DISABLED=false
```

---

## 플랫폼 프로파일

### Spring Boot

| 응집 그룹 | 구성 역할 |
|-----------|-----------|
| **domain-crud** | entity, repository, service, controller, dto, mapper, exception, test |
| **config-change** | config |
| **migration** | migration, entity, repository |

### Next.js

| 응집 그룹 | 구성 역할 |
|-----------|-----------|
| **page-feature** | page, layout, loading, error, component, hook, style, story, test |
| **shared-component** | component, story, test, style |
| **api-route** | api-route, lib, test |

### React SPA

| 응집 그룹 | 구성 역할 |
|-----------|-----------|
| **feature** | page, component, hook, store, style, story, test |
| **design-system** | token, component, story, style |
| **api-layer** | api-client, test |

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
      - run: npx probe check --base origin/main --format brief --silent
```

### Claude Code

MCP 서버로 등록하면 Claude Code가 맥락에 따라 Probe 도구를 자동으로 호출한다.

**자동 훅 (파일 편집 시마다 실행):**

파일을 편집할 때마다 관심사 드리프트를 감지한다. 기존 변경과 다른 관심사의 파일을 추가하면 즉시 경고한다.

```
⚠️ 현재 변경(User domain-crud)과 다른 관심사(config-change)입니다. 별도 PR로 분리할까요?
```

**수동 스킬:**

```
/check-scope     — 현재 변경의 PR 범위 확인
/split-pr        — PR 분할 가이드 (cherry-pick, base 조정, rebase)
/state-matrix    — State Matrix 생성
```

---

## 아키텍처

```
probe/
├── src/                           코어 엔진 (CI 독립 실행)
│   ├── core/                      범위 분석, 관심사 드리프트, API 린트, 체크리스트
│   ├── api/                       OpenAPI 파서, 린트 룰, diff 엔진
│   ├── profiles/                  Spring Boot, Next.js, React SPA
│   ├── review/                    PR 타입 추론, 체크리스트 생성
│   ├── khala/                     칼라 클라이언트, 컨텍스트 보강, 영향 분석
│   ├── mcp/                       MCP 서버 (도구, 리소스, 프롬프트)
│   ├── cli/                       npx probe check
│   └── utils/                     Logger, git, glob
├── .claude/                       Claude Code 어댑터
│   ├── agents/                    code-reviewer, test-writer
│   ├── skills/                    check-scope, split-pr, state-matrix
│   └── rules/                     pr-scope, state-matrix
├── tests/                         145개 테스트
└── docs/                          스코프 문서, 규정 문서
```

**하이브리드 구조**: 코어 엔진(`src/`)이 가치의 실체이고, `.claude/`는 Claude Code에서 편하게 쓰게 해주는 레이어다.

---

## 설계 원칙

1. **파일 수가 아니라 논리적 응집도로 판단한다** — 같은 7개 파일이라도 프레임워크마다 의미가 다르다.
2. **정상일 때는 아무 말도 하지 않는다** — 노이즈는 신뢰를 죽인다.
3. **경고할 때는 분할 방법까지 제안한다** — "크다"만 말하면 쓸모없다.
4. **칼라는 선택적이다** — 없어도 동작하고, 있으면 풍부해진다.

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

## License

MIT

---

<p align="center">
  <sub>Built with Claude Code</sub>
</p>
