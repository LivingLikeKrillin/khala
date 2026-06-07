# Probe v0.2 — 범위 정의

> **핵심 가치**: PR에 API 스펙 변경이 포함되면, 그 변경이 호환인지 비호환인지 자동으로 판별하고, PR 타입에 맞는 리뷰 체크리스트를 생성한다.
> **v0.1과의 관계**: v0.1은 "PR 범위가 리뷰 가능한 단위인가"를 판단했다. v0.2는 "PR 내용이 품질 기준을 충족하는가"를 판단한다.

---

## 0. v0.2가 하는 일 — 한 문장

**PR의 변경 내용을 분석하여 API 계약 위반을 탐지하고, PR 타입별 리뷰 체크리스트를 자동 생성한다.**

---

## 1. 왜 필요한가

### v0.1만으로는 부족한 것

v0.1은 "이 PR의 범위가 적절한가"를 판단한다. 하지만 범위가 적절해도 **내용이 불량**할 수 있다.

```
✅ v0.1 — 범위 정상 (단일 도메인 CRUD, 7개 파일)
❌ v0.2 — 내용 문제:
  - UserResponse.nickname이 nullable인데 스펙에 nullable: true가 없다
  - 에러 응답이 ErrorResponse 스키마를 따르지 않는다
  - 테스트가 없다
```

v0.1이 "크기"를 본다면, v0.2는 "품질"을 본다. 둘 다 있어야 리뷰어가 안심하고 승인할 수 있다.

### 반복되는 문제

| 상황 | 근본 원인 |
|------|-----------|
| "이 필드 nullable인지 아닌지 모르겠어요" | 스펙에 nullable 표시 없음 |
| "스웨거랑 실제 응답이 달라요" | 스펙이 코드와 동기화되지 않음 |
| "에러 형태가 엔드포인트마다 달라요" | 에러 응답 구조가 통일되지 않음 |
| "이 API 바뀐 거 언제 알려줬어요?" | 변경 전파 체계 없음 |
| "리뷰어가 뭘 봐야 하는지 모르겠어요" | PR 타입별 체크리스트 없음 |

---

## 2. Probe의 역할 — 래퍼이자 오케스트레이터

Probe는 외부 도구를 직접 대체하지 않는다. **래퍼로 감싸서** 일관된 인터페이스를 제공하고, 결과를 Probe의 분석 체계에 통합한다.

```
외부 도구                     Probe 래퍼                    Probe 출력
─────────                   ──────────                   ──────────
Spectral (API 린트)     →   api-linter.ts            →   통합 리포트
oasdiff (API diff)      →   api-analyzer.ts          →   (scope-analyzer와 결합)
(없음)                  →   review-checklist.ts      →   PR 타입별 DoD
```

### 외부 도구가 없어도 동작한다

Spectral이나 oasdiff가 설치되지 않은 환경에서도 Probe는 동작해야 한다:
- 외부 도구가 없으면 → 해당 기능은 skip하고 나머지만 실행
- 경고: "Spectral이 설치되지 않아 API 린트를 건너뜁니다 (Spectral not found, skipping API lint)"
- `probe check`는 v0.1 범위 분석 + v0.2 리뷰 체크리스트를 모두 실행

---

## 3. 기능 상세

### 3.1 API 린터 (`api-linter.ts`)

OpenAPI 스펙 파일의 품질을 검증한다. Spectral을 래핑하되, 팀 규정(규정 ②)에 맞는 기본 룰셋을 내장한다.

#### 입력
- OpenAPI 스펙 파일 경로 (기본: `api/openapi.json`)

#### 내장 룰셋 (규정 ② 2.2~2.4 기반)

| 규칙 ID | 심각도 | 설명 | 규정 근거 |
|---------|--------|------|-----------|
| `probe/field-type-required` | error | 모든 필드에 type 필수 | § 2.2 |
| `probe/nullable-explicit` | error | nullable 필드는 `nullable: true` 명시 | § 2.3.1 |
| `probe/no-nullable-optional` | warn | nullable + optional 동시 적용 금지 | § 2.3.1 |
| `probe/error-response-schema` | error | 4xx/5xx → ErrorResponse 스키마 참조 | § 2.3.2 |
| `probe/pagination-required` | warn | 배열 응답에 페이지네이션 필수 | § 2.3.3 |
| `probe/path-naming` | error | 엔드포인트 kebab-case | § 3.1 |
| `probe/property-naming` | error | 필드명 camelCase | § 3.1 |
| `probe/enum-required` | warn | 값이 유한 집합이면 enum 사용 | § 2.4.1 |
| `probe/example-required` | warn | 날짜/금액/ID에 example 필수 | § 2.4.2 |
| `probe/deprecated-lifecycle` | error | deprecated 표시 없이 삭제 금지 | § 2.4.3 |

#### 출력

```typescript
interface ApiLintResult {
  /** 스펙 파일 경로 */
  specPath: string;

  /** 린트 결과 요약 */
  summary: {
    errors: number;
    warnings: number;
    passed: number;
  };

  /** 위반 목록 */
  violations: ApiLintViolation[];
}

interface ApiLintViolation {
  /** 규칙 ID */
  ruleId: string;

  /** 심각도 */
  severity: 'error' | 'warn';

  /** 위반 위치 (JSON path) */
  path: string;

  /** 메시지 (한국어 + 영어) */
  message: string;

  /** 수정 가이드 */
  fix?: string;
}
```

#### Spectral이 없을 때

Probe는 자체 경량 린트 엔진을 내장한다. OpenAPI JSON을 직접 파싱하여 위 10개 규칙을 검사한다. Spectral이 있으면 Spectral을 사용하고, 없으면 내장 엔진으로 폴백한다.

```
Spectral 설치됨?
  ├─ Yes → Spectral 실행 (probe 내장 .spectral.yaml 주입) → 결과를 ApiLintResult로 변환
  └─ No  → 내장 경량 린트 엔진 실행 → 동일한 ApiLintResult 반환
```

---

### 3.2 API 분석기 (`api-analyzer.ts`)

두 버전의 OpenAPI 스펙을 비교하여 변경 사항을 분류한다.

#### 입력
- 기준 스펙 (base, 보통 origin/main의 스펙)
- 현재 스펙 (head, 현재 브랜치의 스펙)

#### 변경 분류 (규정 ② 4.1 기반)

| 변경 유형 | 판정 기준 | 라벨 |
|-----------|-----------|------|
| **추가 (additive)** | 새 엔드포인트, optional 필드 추가, 새 optional 파라미터 | `api:additive` |
| **비호환 (breaking)** | 필드 타입 변경, required↔optional 변경, 구조 변경, 삭제 | `api:breaking` |
| **폐기 예고 (deprecation)** | deprecated: true 추가 | `api:deprecation` |

#### 출력

```typescript
interface ApiDiffResult {
  /** 변경 요약 */
  summary: {
    added: number;
    modified: number;
    removed: number;
    deprecated: number;
    hasBreaking: boolean;
  };

  /** 엔드포인트별 변경 내역 */
  changes: ApiChange[];

  /** 권장 PR 라벨 */
  suggestedLabel: 'api:additive' | 'api:breaking' | 'api:deprecation' | null;
}

interface ApiChange {
  /** HTTP 메서드 + 경로 */
  endpoint: string;

  /** 변경 유형 */
  type: 'added' | 'modified' | 'removed' | 'deprecated';

  /** breaking 여부 */
  breaking: boolean;

  /** 변경 상세 */
  details: string[];
}
```

#### oasdiff가 없을 때

Probe는 자체 경량 diff 엔진을 내장한다. 두 OpenAPI JSON을 비교하여 엔드포인트/필드 수준의 변경을 탐지한다. oasdiff가 있으면 더 정밀한 분석을 제공하고, 없으면 내장 엔진으로 기본 탐지를 수행한다.

```
oasdiff 설치됨?
  ├─ Yes → oasdiff 실행 → 결과를 ApiDiffResult로 변환
  └─ No  → 내장 경량 diff 엔진 → 동일한 ApiDiffResult 반환 (정밀도는 낮을 수 있음)
```

내장 엔진이 탐지하는 breaking 변경:
- 엔드포인트 삭제
- 필드 삭제 (응답)
- required 필드 추가 (요청)
- 필드 타입 변경
- enum 값 제거

---

### 3.3 리뷰 체크리스트 생성기 (`review-checklist.ts`)

변경 파일 목록과 v0.1의 scope 분석 결과를 기반으로, PR 타입을 추론하고 해당 타입의 DoD(Definition of Done) 체크리스트를 생성한다.

#### PR 타입 추론

```
변경 파일의 역할(role)을 집계하여 PR 타입을 결정:

  entity + service + controller + dto           → domain-crud
  controller + dto + openapi 스펙 변경           → api-change
  config + application.*                        → config-change
  migration                                     → db-migration
  page + component + hook                       → ui-feature
  component + story + test                      → ui-component
  token + style                                 → design-system
  test만                                        → test-only
  docs만                                        → docs-only
  위 조합에 해당 없음                              → general
```

#### 타입별 체크리스트

```typescript
interface ReviewChecklist {
  /** 추론된 PR 타입 */
  prType: PrType;

  /** 체크리스트 항목 */
  items: ChecklistItem[];

  /** 자동 검증된 항목 (probe가 확인 가능한 것) */
  autoVerified: VerifiedItem[];

  /** 수동 확인 필요 항목 */
  manualRequired: ChecklistItem[];
}

interface ChecklistItem {
  /** 항목 ID */
  id: string;

  /** 설명 */
  description: string;

  /** 자동 검증 가능 여부 */
  automatable: boolean;

  /** 규정 근거 */
  guidelineRef?: string;
}
```

##### domain-crud 체크리스트

```markdown
## 필수
- [ ] 엔티티 필드의 nullable/required가 스펙에 정확히 반영됨 (규정 ② 2.3.1)
- [ ] 에러 응답이 ErrorResponse 스키마를 따름 (규정 ② 2.3.2)
- [ ] 서비스 레이어에 비즈니스 로직 테스트가 있음
- [ ] 컨트롤러에 통합 테스트 또는 API 스펙 테스트가 있음

## 권장
- [ ] DTO에 validation 어노테이션이 있음
- [ ] 페이지네이션이 필요한 목록 API에 cursor/offset이 구현됨 (규정 ② 2.3.3)
```

##### api-change 체크리스트

```markdown
## 필수
- [ ] API 스펙이 코드에서 자동 생성됨 (수작업 편집 아님) (규정 ② 1.1)
- [ ] nullable/required 정확히 표시됨 (규정 ② 2.3.1)
- [ ] 에러 응답이 ErrorResponse 스키마를 따름 (규정 ② 2.3.2)
- [ ] (breaking 시) FE와 사전 합의 완료 (규정 ② 4.3)
- [ ] (breaking 시) 마이그레이션 가이드 포함 (규정 ② 4.5)

## 권장
- [ ] PR 라벨: api:additive | api:breaking | api:deprecation
- [ ] 영향받는 FE 코드/화면 목록 기재
```

##### ui-feature 체크리스트

```markdown
## 필수
- [ ] 4가지 필수 상태 구현: loading, empty, success, error (규정 ① 필수 상태)
- [ ] 에러 상태에 구체적 UI 명시 (규정 ① "적절히 처리" 금지)

## 권장
- [ ] 스토리 파일이 존재함
- [ ] 반응형 레이아웃 확인 (mobile/desktop)
```

##### ui-component 체크리스트

```markdown
## 필수
- [ ] 스토리 파일이 존재함 (규정 ③)
- [ ] 주요 variant/상태가 스토리에 포함됨

## 권장
- [ ] 접근성 고려 (키보드 네비게이션, aria 속성)
```

##### config-change / db-migration / test-only / docs-only / general

각각 타입에 맞는 간결한 체크리스트를 제공한다. 상세는 구현 시 확정.

---

### 3.4 CLI 확장

기존 `probe check`에 v0.2 기능을 통합하고, 새 서브커맨드를 추가한다.

#### 기존 커맨드 확장

```bash
# v0.1: 범위 분석만
# v0.2: 범위 분석 + API 분석 + 리뷰 체크리스트 통합
probe check [--base <ref>] [--format <markdown|json|brief>] [--silent]
```

`probe check`의 출력이 확장된다:

```
✅ Probe — 정상 범위

현재 변경: domain-crud (User) (7개 파일, +280줄)
응집도: 높음 (단일 도메인, 단일 관심사)
PR 크기: 정상 범위

📋 리뷰 체크리스트 (domain-crud):
  ✅ 테스트 파일 존재 (UserServiceTest.kt)
  ⬜ 에러 응답 ErrorResponse 준수 여부 — 수동 확인 필요
  ⬜ nullable/required 스펙 반영 — 수동 확인 필요
```

#### 새 서브커맨드

```bash
# API 스펙 린트
probe api:lint [spec-path] [--format <markdown|json|brief>]

# API 스펙 diff
probe api:diff [--base <ref>] [--spec <path>] [--format <markdown|json|brief>]

# 리뷰 체크리스트만 생성
probe review [--base <ref>] [--format <markdown|json|brief>]
```

---

### 3.5 서브에이전트 구현

#### code-reviewer 에이전트

`probe check --json` 결과를 기반으로 구조화된 코드 리뷰를 수행한다.

```
입력:
  - probe check --json 결과 (범위 분석 + 리뷰 체크리스트)
  - probe api:lint --json 결과 (API 린트, 해당 시)
  - probe api:diff --json 결과 (API diff, 해당 시)

리뷰 순서:
  1. PR 타입과 범위를 먼저 요약한다
  2. 자동 검증된 항목은 결과만 보고한다
  3. 수동 확인 필요 항목에 대해 코드를 읽고 판단한다
  4. API 린트 위반이 있으면 수정 가이드와 함께 피드백한다
  5. API diff가 있으면 breaking 여부와 영향 범위를 분석한다

출력:
  - 구조화된 리뷰 코멘트 (마크다운)
  - 심각도별 분류 (blocker / suggestion / nit)
```

#### test-writer 에이전트

변경된 코드에 대해 누락된 테스트를 식별하고 작성한다.

```
입력:
  - 변경 파일 목록 (git diff)
  - 기존 테스트 파일 패턴 (프로젝트별 학습)
  - probe check --json 결과 (PR 타입)

분석 순서:
  1. 변경된 소스 파일에 대응하는 테스트 파일이 있는지 확인
  2. 기존 테스트 파일 2~3개를 읽어 프로젝트의 테스트 패턴을 학습
  3. 누락된 테스트 케이스를 도출
  4. 기존 패턴과 일관된 테스트 코드를 생성

원칙:
  - 테스트 프레임워크, 디렉토리 구조, 네이밍 규칙을 기존 코드에서 학습
  - 해피 패스뿐 아니라 에러 케이스도 커버
  - API 엔드포인트가 변경되었으면 API 테스트 생성
```

---

## 4. v0.2 전체 기능 범위

### 4.1 포함 (v0.2)

| 기능 | 설명 | 형태 |
|------|------|------|
| **API 린터** | 내장 경량 린트 + Spectral 래퍼 | 코어 로직 |
| **API 분석기** | 내장 경량 diff + oasdiff 래퍼 | 코어 로직 |
| **리뷰 체크리스트** | PR 타입 추론 → DoD 체크리스트 생성 | 코어 로직 |
| **CLI: `probe api:lint`** | API 스펙 린트 실행 | CLI |
| **CLI: `probe api:diff`** | API 스펙 diff 실행 | CLI |
| **CLI: `probe review`** | 리뷰 체크리스트 생성 | CLI |
| **CLI: `probe check` 확장** | 범위 분석 + 리뷰 체크리스트 통합 출력 | CLI |
| **code-reviewer 에이전트** | probe 결과 기반 구조화 리뷰 | 에이전트 |
| **test-writer 에이전트** | 누락 테스트 식별 + 생성 | 에이전트 |

### 4.2 미포함 (v0.3 이후)

| 기능 | 이유 | 예정 버전 |
|------|------|-----------|
| api:codegen (타입 생성) | 프로젝트별 설정 의존도 높음 | v0.3+ |
| api:mock (Mock 서버) | Prism/MSW 직접 연동은 프로젝트별 | v0.3+ |
| ws:lint (AsyncAPI 검증) | AsyncAPI 도입 팀 한정 | v0.3+ |
| MCP 서버 | v0.3 범위 | v0.3 |
| 칼라 연동 | v0.4 범위 | v0.4 |

---

## 5. 프로젝트 구조 변경

```
probe/
├── src/
│   ├── core/
│   │   ├── scope-analyzer.ts      ← v0.1 (변경 없음)
│   │   ├── config-loader.ts       ← v0.1 (확장: api/review 설정 추가)
│   │   ├── api-linter.ts          ← v0.2 NEW
│   │   ├── api-analyzer.ts        ← v0.2 NEW
│   │   └── review-checklist.ts    ← v0.2 NEW
│   ├── api/                       ← v0.2 NEW
│   │   ├── openapi-parser.ts      ← OpenAPI JSON 파서
│   │   ├── spec-differ.ts         ← 내장 경량 diff 엔진
│   │   ├── spec-linter.ts         ← 내장 경량 린트 엔진
│   │   ├── spectral-runner.ts     ← Spectral 래퍼 (설치 시에만)
│   │   ├── oasdiff-runner.ts      ← oasdiff 래퍼 (설치 시에만)
│   │   └── rules/                 ← 내장 린트 룰
│   │       ├── types.ts           ← 룰 인터페이스
│   │       ├── field-type.ts
│   │       ├── nullable.ts
│   │       ├── error-response.ts
│   │       ├── naming.ts
│   │       └── index.ts           ← 전체 룰 레지스트리
│   ├── review/                    ← v0.2 NEW
│   │   ├── pr-type-detector.ts    ← PR 타입 추론
│   │   ├── checklist-generator.ts ← 체크리스트 생성
│   │   └── checklists/            ← 타입별 체크리스트 정의
│   │       ├── domain-crud.ts
│   │       ├── api-change.ts
│   │       ├── ui-feature.ts
│   │       ├── ui-component.ts
│   │       └── index.ts
│   ├── profiles/                  ← v0.1 (변경 없음)
│   ├── cli/
│   │   └── index.ts               ← 확장: api:lint, api:diff, review 커맨드
│   └── utils/
├── tests/
│   ├── scope-analyzer.test.ts     ← v0.1 (변경 없음)
│   ├── api-linter.test.ts         ← v0.2 NEW
│   ├── api-analyzer.test.ts       ← v0.2 NEW
│   ├── review-checklist.test.ts   ← v0.2 NEW
│   └── ...
└── .claude/
    ├── agents/
    │   ├── code-reviewer.md       ← v0.2 구현
    │   └── test-writer.md         ← v0.2 구현
    └── ...
```

---

## 6. 설정 확장 (`probe.config.ts`)

```typescript
export default {
  // v0.1 설정 (변경 없음)
  platform: 'spring-boot',
  thresholds: { maxFilesPerPr: 25 },
  ignore: ['generated/'],

  // v0.2 설정 — NEW
  api: {
    /** OpenAPI 스펙 파일 경로 */
    specPath: 'api/openapi.json',

    /** Spectral 사용 여부 (설치 시 자동 감지, 명시 오버라이드 가능) */
    useSpectral: 'auto',

    /** oasdiff 사용 여부 (설치 시 자동 감지, 명시 오버라이드 가능) */
    useOasdiff: 'auto',

    /** 커스텀 린트 룰 비활성화 */
    disableRules: [],

    /** 린트 심각도 오버라이드 */
    ruleSeverity: {
      'probe/example-required': 'off',
    },
  },

  review: {
    /** 리뷰 체크리스트 비활성화할 PR 타입 */
    disableChecklists: [],

    /** 커스텀 체크리스트 항목 추가 */
    customItems: {
      'domain-crud': [
        { id: 'custom-audit-log', description: '감사 로그가 기록되는지 확인' },
      ],
    },
  },
};
```

---

## 7. 사용자 경험 시나리오

### 시나리오 1: Spring Boot 개발자가 User CRUD를 만들었을 때

```bash
$ probe check

✅ Probe — 정상 범위

현재 변경: domain-crud (User) (7개 파일, +280줄)
응집도: 높음 (단일 도메인, 단일 관심사)
PR 크기: 정상 범위

📋 리뷰 체크리스트 (domain-crud):
  ✅ 테스트 파일 존재 (UserServiceTest.kt)
  ⬜ 에러 응답 ErrorResponse 준수 — 수동 확인 필요
  ⬜ nullable/required 스펙 반영 — 수동 확인 필요
  ⬜ DTO validation 어노테이션 — 수동 확인 필요
```

### 시나리오 2: API 스펙에 breaking 변경이 포함된 PR

```bash
$ probe api:diff

🔴 API 변경 감지 — breaking 변경 포함

변경 요약: 2개 수정, 1개 삭제

  ⚠️ POST /users
    - 요청: currency 필드가 optional → required로 변경
    - breaking: 기존 클라이언트가 currency를 안 보내면 400 에러

  ✅ GET /users
    - 응답: lastLoginAt 필드 추가 (optional, nullable)
    - 호환 변경

  🔴 DELETE /users/{id}/avatar
    - 엔드포인트 삭제
    - breaking: 해당 API를 호출하는 클라이언트 실패

권장 PR 라벨: api:breaking
필수 조치:
  - FE와 사전 합의 (규정 ② 4.3)
  - 마이그레이션 가이드 포함 (규정 ② 4.5)
  - FE 리뷰어 승인 필수
```

### 시나리오 3: API 스펙 린트 실행

```bash
$ probe api:lint

🔶 API 린트 — 3개 에러, 2개 경고

  ERROR probe/error-response-schema
    paths./users.post.responses.400
    → 4xx 응답이 ErrorResponse를 참조하지 않습니다
    → 수정: @ApiResponse에 ErrorResponse.class를 content로 지정하세요

  ERROR probe/nullable-explicit
    components.schemas.UserResponse.properties.nickname
    → nullable 필드에 nullable: true가 없습니다
    → 수정: @Schema(nullable = true)를 추가하세요

  ERROR probe/path-naming
    paths./getUserList
    → 엔드포인트 경로가 kebab-case가 아닙니다
    → 수정: /user-list 또는 /users로 변경하세요

  WARN probe/example-required
    components.schemas.UserResponse.properties.createdAt
    → 날짜 필드에 example이 없습니다

  WARN probe/pagination-required
    paths./users.get.responses.200
    → 배열 응답에 페이지네이션이 없습니다
```

### 시나리오 4: 외부 도구 없이 실행

```bash
$ probe api:lint

ℹ️ Spectral이 설치되지 않아 내장 린트 엔진을 사용합니다
   (Spectral not found, using built-in linter)
   더 정밀한 분석을 원하면: npm install -g @stoplight/spectral-cli

✅ API 린트 — 0개 에러, 0개 경고
```

---

## 8. 구현 우선순위

| 순서 | 구현 대상 | 예상 코드량 |
|------|-----------|-------------|
| 1 | `ApiLintResult`, `ApiDiffResult`, `ReviewChecklist` 타입 정의 | ~150줄 |
| 2 | 내장 경량 린트 엔진 (OpenAPI JSON 직접 파싱) | ~400줄 |
| 3 | 내장 경량 diff 엔진 (두 OpenAPI JSON 비교) | ~350줄 |
| 4 | PR 타입 추론 + 체크리스트 생성 | ~300줄 |
| 5 | Spectral 래퍼 (외부 도구 연동) | ~150줄 |
| 6 | oasdiff 래퍼 (외부 도구 연동) | ~150줄 |
| 7 | CLI 확장 (api:lint, api:diff, review) | ~200줄 |
| 8 | `probe check` 통합 출력 | ~100줄 |
| 9 | code-reviewer 에이전트 프롬프트 | ~100줄 |
| 10 | test-writer 에이전트 프롬프트 | ~100줄 |
| 11 | 테스트 | ~500줄 |

**총 예상**: ~2,500줄 (테스트 포함)

---

## 9. 설정 확장 타입

```typescript
// config-loader.ts에 추가
export interface ProbeConfig {
  // v0.1 (기존)
  platform?: 'spring-boot' | 'nextjs' | 'react-spa' | 'custom';
  customProfile?: PlatformProfile;
  thresholds?: Partial<PrThresholds>;
  ignore?: string[];
  severity?: { minLevel?: 'info' | 'warn' | 'error' };

  // v0.2 (신규)
  api?: ApiConfig;
  review?: ReviewConfig;
}

interface ApiConfig {
  /** OpenAPI 스펙 파일 경로 (기본: 'api/openapi.json') */
  specPath?: string;

  /** Spectral 사용 여부 ('auto' | true | false) */
  useSpectral?: 'auto' | boolean;

  /** oasdiff 사용 여부 ('auto' | true | false) */
  useOasdiff?: 'auto' | boolean;

  /** 비활성화할 린트 룰 ID 목록 */
  disableRules?: string[];

  /** 룰별 심각도 오버라이드 */
  ruleSeverity?: Record<string, 'error' | 'warn' | 'off'>;
}

interface ReviewConfig {
  /** 체크리스트 비활성화할 PR 타입 */
  disableChecklists?: string[];

  /** 타입별 커스텀 체크리스트 항목 */
  customItems?: Record<string, Array<{ id: string; description: string }>>;
}
```

---

## 10. 테스트 계획

### api-linter 테스트

```
- 올바른 스펙은 에러 0건
- nullable 미표시 필드 탐지
- ErrorResponse 미참조 4xx 응답 탐지
- kebab-case 위반 경로 탐지
- camelCase 위반 필드명 탐지
- nullable + optional 동시 적용 경고
- 룰 비활성화(disableRules) 동작 확인
- 심각도 오버라이드(ruleSeverity) 동작 확인
```

### api-analyzer 테스트

```
- 엔드포인트 추가 → additive
- optional 필드 추가 → additive
- 엔드포인트 삭제 → breaking
- required 필드 추가 (요청) → breaking
- 필드 타입 변경 → breaking
- enum 값 제거 → breaking
- deprecated 추가 → deprecation
- 변경 없음 → 빈 결과
- breaking + additive 혼재 → hasBreaking: true
```

### review-checklist 테스트

```
- entity + service + controller + dto → domain-crud 추론
- controller + openapi 변경 → api-change 추론
- page + component → ui-feature 추론
- 타입별 필수 항목이 체크리스트에 포함됨
- 커스텀 항목 추가가 반영됨
- 자동 검증 가능 항목(테스트 파일 존재 등)이 올바르게 판정됨
```

---

## 변경 이력

| 버전 | 날짜 | 변경 |
|------|------|------|
| v0.2-draft | 2026-03-11 | 초안 — API 린트/diff + 리뷰 체크리스트 중심으로 정의 |
