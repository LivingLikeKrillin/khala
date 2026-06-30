# 안전망 도입 전략 — 자동화 아키텍처 & 정착 계획

> **전제**: 팀 전원 Claude Code 사용. 로컬(Claude Code hook) + CI(GitHub Actions) 이중 게이트.
> **목표**: 규정 문서를 팀에 던지는 것이 아니라, 도구가 규정을 실행하게 만든다.

---

## 0. 핵심 철학

```
규정을 읽고 외워서 따르게 하지 않는다.
도구가 알려주니까 자연스럽게 따르게 만든다.
```

팀원이 해야 할 일은 딱 하나다: **평소처럼 코드를 짜고 PR을 올린다.** 나머지는 도구가 잡는다.

---

## 1. 이중 게이트 아키텍처

```
개발자의 워크플로
│
├─ 로컬 (Claude Code Hooks) ─── 빠른 피드백, 가이드, 자동 생성
│   ├─ pre-commit     : 직접 값 사용 탐지 → 즉시 차단
│   ├─ pre-push       : 스펙 동기화 확인 → 경고 (차단 아님)
│   ├─ pr-create      : DoD 자동 검증 + 템플릿 자동 채움 + 라벨 제안
│   └─ pr-review      : VRT/Impact 요약 코멘트 자동 생성
│
├─ CI (GitHub Actions) ─── 확실한 게이트, 머지 차단
│   ├─ lint / typecheck / api:lint / lint:tokens / lint:a11y
│   ├─ storybook:build + vrt:run
│   ├─ api:diff + api:compatibility
│   ├─ ui:impact
│   └─ 최종 DoD 재검증 → 미충족 시 머지 차단
│
└─ MCP 서버 ─── Claude Code에 컨텍스트 제공
    ├─ Figma MCP        : 토큰 변경 내역
    ├─ Chromatic MCP     : VRT 결과
    ├─ OpenAPI Diff MCP  : API 스펙 변경 분석
    └─ State Matrix MCP  : 상태 매트릭스 파싱 + 교차 검증
```

### 1.1 로컬 vs CI — 역할 분리

| 구간 | 역할 | 속도 | 강도 |
|------|------|------|------|
| **로컬 (Claude Code)** | 가이드 + 빠른 차단 | 즉시 (초 단위) | 명백한 위반만 차단, 나머지는 경고/제안 |
| **CI (GitHub Actions)** | 확정 게이트 | 분 단위 | 모든 규칙 검증, 미충족 시 머지 차단 |

**원칙**: 로컬에서 80%를 잡고, CI에서 100%를 보장한다. 로컬에서 놓쳐도 CI에서 반드시 잡힌다.

### 1.2 왜 이중으로 거는가

로컬 hook만으로는 부족한 이유:
- VRT는 Chromatic 서버에서 돌아야 한다 (로컬에서 불가)
- `api:generate`는 BE 빌드가 필요하다 (FE 로컬에 BE 환경이 없을 수 있다)
- hook을 우회하거나 건너뛸 수 있다

CI만으로는 부족한 이유:
- 피드백이 느리다 (push 후 수 분 대기)
- "PR 올렸더니 실패, 고치고 다시 올리고, 또 실패" 반복은 생산성을 죽인다
- Claude Code가 로컬에서 바로 "이거 빠졌어요"라고 말해주면 반복을 줄인다

---

## 2. Claude Code Hook 상세 설계

### 2.1 Hook 설정 구조

```
.claude/
├── settings.json            ← Claude Code 프로젝트 설정
├── hooks/
│   ├── pre-commit.md        ← pre-commit 훅 프롬프트
│   ├── pre-push.md          ← pre-push 훅 프롬프트
│   ├── pr-create.md         ← PR 생성 훅 프롬프트
│   └── pr-review.md         ← PR 리뷰 훅 프롬프트
├── commands/
│   ├── state-matrix.md      ← /state-matrix 커스텀 명령
│   ├── api-check.md         ← /api-check 커스텀 명령
│   ├── ui-check.md          ← /ui-check 커스텀 명령
│   └── impact.md            ← /impact 커스텀 명령
└── mcp/
    └── servers.json         ← MCP 서버 연결 설정
```

### 2.2 `pre-commit` — 즉시 차단

**목적**: 커밋 전에 명백한 위반을 즉시 잡는다. 빠르게 돌아야 하므로 검사 범위를 최소화.

```markdown
# .claude/hooks/pre-commit.md

## 트리거
staged 파일에 대해서만 검사한다.

## 검사 항목 (전부 즉시 차단)

### 1. 직접 값 사용 탐지
staged 파일 중 `.tsx`, `.ts`, `.css`, `.scss` 파일에서:
- `#[0-9a-fA-F]{3,8}` (색상 직접값) → 차단
- `rgb(`, `rgba(`, `hsl(`, `hsla(` → 차단
- `box-shadow:` 뒤에 `var(` 없이 직접 값 → 차단
- `px` 하드코딩 (예외: `1px`, `0px`, `0.5px`) → 차단
- `transition-duration:`, `animation-duration:` 뒤에 `var(` 없이 직접 값 → 차단

허용 예외:
- `calc()` 내에서 토큰과 함께 사용
- `.stories.tsx` 파일 (스토리 자체는 예외)
- 주석 내 코드

### 2. 토큰 산출물 수작업 편집 탐지
staged 파일에 아래가 포함되면 차단:
- `src/design-tokens/tokens.json`
- `src/design-tokens/tokens.css`
- `src/design-tokens/theme.ts`

메시지: "토큰 산출물은 수작업 편집이 금지됩니다. `pnpm design:sync`를 사용하세요."

### 3. API 스펙 수작업 편집 탐지
staged 파일에 아래가 포함되면 차단:
- `api/openapi.json`
- `api/asyncapi.json`

메시지: "API 스펙은 코드에서 자동 생성됩니다. `pnpm api:generate`를 사용하세요."

### 4. 자동 생성 파일 수작업 편집 탐지
staged 파일에 아래가 포함되면 차단:
- `src/api/types.ts`
- `src/api/client.ts`
- `src/api/ws-types.ts`

메시지: "이 파일은 자동 생성됩니다. 직접 편집하지 마세요."

## 출력 형식
위반 발견 시:
```
❌ pre-commit 차단
  파일: src/ui/Button/Button.tsx:42
  위반: 직접 색상값 사용 (#3B82F6)
  수정: var(--color-primary) 또는 해당하는 토큰을 사용하세요
```
```

### 2.3 `pre-push` — 경고 (차단 아님)

**목적**: push 전에 스펙 동기화 상태를 확인한다. CI에서 잡히겠지만 미리 알려준다.

```markdown
# .claude/hooks/pre-push.md

## 트리거
push 대상 커밋의 변경 파일을 분석한다.

## 검사 항목 (모두 경고, 차단하지 않음)

### 1. 토큰 변경 시 Foundations 스토리 존재 확인
`src/design-tokens/` 변경 → `src/storybook/foundations/` 에 관련 스토리가 있는지 확인
없으면 경고: "토큰이 변경되었는데 Foundations 스토리가 업데이트되지 않았을 수 있습니다."

### 2. 컴포넌트 변경 시 스토리 동반 확인
`src/ui/ComponentName/` 변경 → `src/storybook/components/ComponentName.stories.tsx` 존재 확인
없으면 경고: "컴포넌트가 변경되었는데 스토리가 업데이트되지 않았습니다."

### 3. 화면 변경 시 Screen Story 존재 확인
`src/screens/ScreenName/` 변경 → `src/storybook/screens/ScreenName.stories.tsx` 존재 확인
없으면 경고: "화면이 변경되었는데 Screen Story가 없습니다."

### 4. API 관련 코드 변경 시 스펙 동기화 확인
컨트롤러/라우터 파일 변경 → "pnpm api:generate 후 스펙이 최신인지 확인하세요."

## 출력 형식
경고 발견 시:
```
⚠️ pre-push 경고 (push는 계속됩니다)
  - 컴포넌트 Button이 변경되었는데 스토리가 업데이트되지 않았습니다
  - CI에서 실패할 수 있습니다. 미리 확인하시겠습니까?
```
```

### 2.4 `pr-create` — 핵심 Hook

**목적**: PR 생성 시 자동으로 DoD를 검증하고, 템플릿을 채우고, 라벨을 제안한다. 이 hook이 팀이 처음 체감하는 가치다.

```markdown
# .claude/hooks/pr-create.md

## 트리거
PR 생성 시 자동 실행

## 동작 순서

### Step 1: PR 타입 추론
변경 파일 경로를 분석하여 PR 타입을 자동 추론한다.

| 변경 파일 경로 | 추론 타입 |
|----------------|-----------|
| `src/design-tokens/` | `ui:tokens` |
| `src/ui/` + `src/storybook/components/` | `ui:components` |
| `src/screens/` + `src/storybook/screens/` | `ui:screens` |
| 컨트롤러/라우터 + `api/openapi.json` | `api:additive` 또는 `api:breaking` |
| `api/asyncapi.json` | `api:additive` (WebSocket) |
| 위 패턴이 혼합 | 복합 PR → 통합 템플릿 제안 |

### Step 2: DoD 자동 검증
추론된 PR 타입에 해당하는 DoD 체크리스트를 검증한다.

#### ui:tokens DoD 검증
- [ ] `src/design-tokens/tokens.(json|css|ts)` 변경이 포함되어 있는가?
- [ ] Foundations 스토리 파일이 존재하는가?
- [ ] PR 본문에 `origin: figma|code`가 있는가?

#### ui:components DoD 검증
- [ ] 변경된 컴포넌트에 대응하는 스토리 파일이 존재하는가?
- [ ] 스토리에 주요 variants/state가 포함되어 있는가?

#### ui:screens DoD 검증
- [ ] Screen Story가 최소 1개 존재하는가?
- [ ] loading 상태 스토리가 있는가?
- [ ] empty 또는 error 상태 스토리가 있는가?

#### api:* DoD 검증
- [ ] api/openapi.json 변경이 포함되어 있는가?
- [ ] 에러 응답이 ErrorResponse 스키마를 따르는가?
- [ ] (breaking이면) 마이그레이션 가이드가 PR 본문에 있는가?

### Step 3: PR 템플릿 자동 채움
누락된 섹션을 자동으로 채워서 PR 본문을 업데이트한다.

- Impact 섹션: 변경된 토큰/컴포넌트/화면 목록을 자동 기입
- Risk 섹션: scope(wide/local), breaking(yes/no) 자동 판단
- Checklist: 해당 타입의 체크리스트를 자동 삽입

### Step 4: 라벨 자동 부여
추론된 타입에 해당하는 라벨을 자동으로 부여한다.
breaking 여부는 api:diff 또는 변경 파일 분석으로 판단한다.

### Step 5: 누락 항목 코멘트
DoD 미충족 항목을 PR 코멘트로 남긴다.

## 출력 형식
```
## 🔍 PR 자동 분석 결과

**추론된 타입**: `ui:components`
**자동 부여 라벨**: `ui:components`

### DoD 검증
✅ 컴포넌트 코드 변경 감지: `src/ui/Card/Card.tsx`
✅ 스토리 파일 존재: `src/storybook/components/Card.stories.tsx`
⚠️ Screen Story에서 이 컴포넌트를 사용하는 화면: `Dashboard`, `UserProfile`
❌ VRT 리포트 링크가 PR 본문에 없습니다

### 자동 채움
- Impact → Affected components: `Card`
- Impact → Affected screens: `Dashboard`, `UserProfile`
- Risk → scope: local, breaking: no

### 다음 단계
1. CI에서 VRT가 완료되면 리포트 링크를 PR 본문에 추가하세요
2. VRT diff가 있으면 리뷰어 승인이 필요합니다
```
```

### 2.5 `pr-review` — VRT/Impact 요약

**목적**: CI 결과가 나온 후, 리뷰어가 판단하기 쉽도록 결과를 요약한다.

```markdown
# .claude/hooks/pr-review.md

## 트리거
CI 체크가 완료된 후 자동 실행 (또는 리뷰어가 `/review` 코멘트 시)

## 동작
MCP 서버에서 가져온 정보를 종합하여 리뷰 요약을 생성한다.

### 수집 정보
- Chromatic MCP → VRT diff 목록 + 스냅샷 수
- OpenAPI Diff MCP → API 변경 요약
- ui:impact 결과 → 영향 범위
- lint 결과 → 위반 항목

### 출력 형식
```
## 📋 리뷰 요약

### 변경 범위
- 토큰 2개 변경 (`color.text.primary`, `color.bg.surface`)
- 컴포넌트 3개 영향 (`Button`, `Card`, `Input`)
- 화면 1개 영향 (`Dashboard`)

### VRT 결과
- 변경된 스냅샷: 8개 (light 4 + dark 4)
- 추가된 스냅샷: 0개
- 승인 상태: ❌ 미승인 → [Chromatic에서 확인](link)

### API 변경
- 변경 없음

### 리뷰 포인트
1. `color.text.primary` 값 변경 → Button, Card, Input의 텍스트 색상이 바뀝니다
2. VRT diff 8개를 Chromatic에서 확인하고 승인해주세요
3. scope=local, breaking=no → FE 리뷰어 1명 승인 필요
```
```

### 2.6 커스텀 명령어

팀원이 Claude Code에서 직접 호출할 수 있는 명령어.

```markdown
# .claude/commands/state-matrix.md
# 사용: /state-matrix [기능명]

이 기능의 State Matrix를 생성합니다.
1. 기능명과 설명을 기반으로 Layer 1(필수 4종) 초안을 생성
2. Layer 2~4 해당 여부를 질문
3. 완성된 매트릭스를 docs/state-matrices/{기능명}.md에 저장
```

```markdown
# .claude/commands/api-check.md
# 사용: /api-check

현재 브랜치의 API 변경 사항을 분석합니다.
1. api:generate를 실행하여 스펙이 최신인지 확인
2. main 브랜치와 비교하여 변경 요약 생성
3. breaking 여부 판별
4. 영향받는 FE 코드 목록 출력
```

```markdown
# .claude/commands/ui-check.md
# 사용: /ui-check

현재 브랜치의 UI 변경 사항을 분석합니다.
1. 변경된 토큰/컴포넌트/화면 탐지
2. 스토리 존재 여부 확인
3. 직접 값 사용 위반 탐지
4. DoD 체크리스트 검증 결과 출력
```

```markdown
# .claude/commands/impact.md
# 사용: /impact

변경된 토큰의 영향 범위를 분석합니다.
1. git diff에서 변경된 토큰 키 추출
2. 컴포넌트/화면에서 해당 토큰 참조 검색
3. 영향 범위 리포트를 Markdown으로 출력
```

---

## 3. CI (GitHub Actions) 상세 설계

### 3.1 워크플로 구조

```yaml
# .github/workflows/safety-net.yml
name: Safety Net

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  # ─── 공통 ───
  setup:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v2
      - run: pnpm install --frozen-lockfile

  # ─── 정적 분석 (병렬) ───
  static-analysis:
    needs: setup
    runs-on: ubuntu-latest
    strategy:
      matrix:
        check: [typecheck, lint]
    steps:
      - run: pnpm ${{ matrix.check }}

  # ─── 규정 ③: UI 검증 ───
  ui-checks:
    needs: setup
    if: contains(github.event.pull_request.labels.*.name, 'ui:')
        || contains(steps.detect.outputs.changed_paths, 'src/design-tokens/')
        || contains(steps.detect.outputs.changed_paths, 'src/ui/')
        || contains(steps.detect.outputs.changed_paths, 'src/screens/')
    runs-on: ubuntu-latest
    steps:
      - name: Token lint
        if: contains(steps.detect.outputs.changed_paths, 'src/design-tokens/')
        run: pnpm lint:tokens

      - name: Storybook build
        run: pnpm storybook:build

      - name: Accessibility lint
        run: pnpm lint:a11y

      - name: VRT
        run: pnpm vrt:run

      - name: UI Impact
        run: |
          REPORT=$(pnpm ui:impact --format markdown)
          gh pr comment ${{ github.event.pull_request.number }} --body "$REPORT"

  # ─── 규정 ②: API 검증 ───
  api-checks:
    needs: setup
    if: contains(steps.detect.outputs.changed_paths, 'api/')
        || contains(github.event.pull_request.labels.*.name, 'api:')
    runs-on: ubuntu-latest
    steps:
      - name: API lint
        run: pnpm api:lint

      - name: WebSocket lint
        if: contains(steps.detect.outputs.changed_paths, 'api/asyncapi')
        run: pnpm ws:lint

      - name: API diff
        run: |
          DIFF=$(pnpm api:diff --format markdown)
          gh pr comment ${{ github.event.pull_request.number }} --body "$DIFF"

      - name: API compatibility
        if: contains(github.event.pull_request.labels.*.name, 'api:breaking')
        run: pnpm api:compatibility

  # ─── 최종 게이트 ───
  merge-gate:
    needs: [static-analysis, ui-checks, api-checks]
    if: always()
    runs-on: ubuntu-latest
    steps:
      - name: DoD 최종 검증
        run: node scripts/ci/merge-gate.js
        env:
          PR_NUMBER: ${{ github.event.pull_request.number }}
          PR_LABELS: ${{ toJSON(github.event.pull_request.labels.*.name) }}
```

### 3.2 `merge-gate.js` — 최종 게이트 로직

```javascript
// scripts/ci/merge-gate.js
const labels = JSON.parse(process.env.PR_LABELS);
const errors = [];

// ui:tokens PR인데 lint:tokens 미통과
if (labels.includes('ui:tokens')) {
  // lint:tokens 결과 확인
  // VRT에 Foundations 변경 반영 확인
  // origin: figma|code 명시 확인
}

// ui:screens PR인데 Screen Story 부재
if (labels.includes('ui:screens')) {
  // Screen Story 존재 확인
  // loading + (empty|error) 상태 확인
}

// api:breaking인데 FE 리뷰어 미승인
if (labels.includes('api:breaking')) {
  // FE 리뷰어 승인 확인
  // 마이그레이션 가이드 존재 확인
}

// VRT 미승인
// Chromatic API로 승인 상태 확인

if (errors.length > 0) {
  console.error('❌ 머지 차단 — DoD 미충족');
  errors.forEach(e => console.error(`  - ${e}`));
  process.exit(1);
}

console.log('✅ 머지 가능');
```

---

## 4. MCP 서버 설계

### 4.1 MCP 서버 목록 및 우선순위

| MCP 서버 | 역할 | 소비자 | 우선순위 |
|----------|------|--------|----------|
| **OpenAPI Diff MCP** | API 스펙 변경 분석, breaking 판별 | pr-create hook, pr-review hook | **P0** |
| **Chromatic MCP** | VRT 결과 조회, diff 목록, 승인 상태 | pr-review hook, merge-gate | **P1** |
| **State Matrix MCP** | State Matrix 파싱, 필수 상태 검증, API 에러 코드 교차 검증 | pr-create hook, CI | **P2** |
| **Figma MCP** | Figma Variables 조회, 토큰 변경 내역 | design:sync, pr-create hook | **P3** |

### 4.2 OpenAPI Diff MCP (P0)

```
역할: Claude Code가 API 스펙 변경을 이해할 수 있게 컨텍스트를 제공
```

**제공하는 Tool**:

| Tool | 입력 | 출력 |
|------|------|------|
| `api_diff` | `base_ref` (기본: origin/main) | 변경된 엔드포인트 목록, 필드 변경, breaking 여부 |
| `api_breaking_check` | `base_ref` | breaking 변경 상세 + 영향받는 클라이언트 코드 |
| `api_spec_validate` | — | api:lint 결과 (위반 항목 목록) |

**구현 방식**: oasdiff를 래핑하는 MCP 서버

```typescript
// mcp-servers/openapi-diff/index.ts
import { Server } from "@modelcontextprotocol/sdk/server";

const server = new Server({ name: "openapi-diff" });

server.tool("api_diff", async ({ base_ref = "origin/main" }) => {
  const result = execSync(
    `oasdiff changelog <(git show ${base_ref}:api/openapi.json) api/openapi.json --format json`
  );
  return JSON.parse(result.toString());
});

server.tool("api_breaking_check", async ({ base_ref = "origin/main" }) => {
  const breaking = execSync(
    `oasdiff breaking <(git show ${base_ref}:api/openapi.json) api/openapi.json --format json`
  );
  return JSON.parse(breaking.toString());
});
```

### 4.3 Chromatic MCP (P1)

```
역할: VRT 결과를 Claude Code가 해석할 수 있게 제공
```

**제공하는 Tool**:

| Tool | 입력 | 출력 |
|------|------|------|
| `vrt_status` | `build_id` 또는 `branch` | 전체 요약 (변경/추가/제거 스냅샷 수, 승인 상태) |
| `vrt_changes` | `build_id` | 변경된 스냅샷 목록 (스토리 이름, diff URL) |
| `vrt_approve_status` | `build_id` | 스냅샷별 승인/미승인 상태 |

**구현 방식**: Chromatic GraphQL API를 래핑하는 MCP 서버

### 4.4 State Matrix MCP (P2)

```
역할: 레포의 State Matrix 문서를 파싱하여 교차 검증에 사용
```

**제공하는 Tool**:

| Tool | 입력 | 출력 |
|------|------|------|
| `matrix_get` | `feature_name` | 해당 기능의 State Matrix (파싱된 JSON) |
| `matrix_validate` | `feature_name` | 필수 상태 누락 여부, Layer 해당성 검증 |
| `matrix_cross_check` | `feature_name` | State Matrix 에러 코드 vs API 스펙 에러 enum 교차 검증 |
| `matrix_screen_check` | `screen_name` | State Matrix 필수 상태 vs Screen Story 케이스 교차 검증 |

**구현 방식**: Markdown 파서로 State Matrix 파일을 읽고, 테이블을 JSON으로 변환

### 4.5 Figma MCP (P3)

```
역할: Figma Variables API를 래핑하여 토큰 변경 내역을 제공
```

**제공하는 Tool**:

| Tool | 입력 | 출력 |
|------|------|------|
| `figma_variables` | `file_key` | 현재 Figma Variables 전체 목록 |
| `figma_diff` | `file_key` | 레포의 tokens.json과 Figma의 차이 |

### 4.6 MCP 서버 연결 설정

```json
// .claude/mcp/servers.json
{
  "servers": [
    {
      "name": "openapi-diff",
      "command": "node",
      "args": ["mcp-servers/openapi-diff/index.js"],
      "enabled": true
    },
    {
      "name": "chromatic",
      "command": "node",
      "args": ["mcp-servers/chromatic/index.js"],
      "env": {
        "CHROMATIC_TOKEN": "${CHROMATIC_TOKEN}"
      },
      "enabled": true
    },
    {
      "name": "state-matrix",
      "command": "node",
      "args": ["mcp-servers/state-matrix/index.js"],
      "enabled": true
    },
    {
      "name": "figma",
      "command": "node",
      "args": ["mcp-servers/figma/index.js"],
      "env": {
        "FIGMA_ACCESS_TOKEN": "${FIGMA_ACCESS_TOKEN}",
        "FIGMA_FILE_KEY": "${FIGMA_FILE_KEY}"
      },
      "enabled": true
    }
  ]
}
```

---

## 5. 정착 전략 — 3단계

### Phase 1: 보이지 않게 시작 (Week 1~3)

**목표**: 팀이 인지하기 전에 도구를 먼저 넣는다. 차단하지 않고 관찰한다.

| 작업 | 내용 | 차단 여부 |
|------|------|-----------|
| pre-commit hook 배포 | 직접 값 사용 탐지만 | **차단** (명백한 위반) |
| pr-create hook 배포 | DoD 검증 + 라벨 제안 + 템플릿 채움 | **제안만** (차단 아님) |
| CI: typecheck + lint | 기존에 이미 있을 것 | 기존 유지 |
| CI: api:lint 추가 | Spectral로 스펙 품질 검증 | **경고만** (차단 아님) |

**팀에게 전달하는 것**:
- 1장 요약 공유 (5분 발표)
- "Claude Code가 PR에 코멘트를 남기기 시작합니다. 참고용이니 무시해도 됩니다."
- 이 단계에서는 규정 전문을 공유하지 않는다

**수집하는 데이터**:
- pr-create hook이 잡은 누락 항목 빈도
- api:lint 경고 빈도
- 팀원 반응 (유용하다 / 귀찮다 / 무시한다)

### Phase 2: 점진적 강화 (Week 4~8)

**목표**: Phase 1에서 효과가 확인된 체크를 차단으로 전환한다. 규정 문서를 공유한다.

| 주차 | 차단으로 전환하는 것 | 새로 추가하는 것 |
|------|----------------------|------------------|
| Week 4 | api:lint → CI 필수 | api:diff (PR 코멘트) |
| Week 5 | — | api:codegen (FE 타입 자동 생성) |
| Week 6 | lint:tokens → CI 필수 | lint:a11y (경고만) |
| Week 7 | Storybook build → CI 필수 | vrt:run (경고만) |
| Week 8 | lint:a11y → CI 필수 | ui:impact (PR 코멘트) |

**팀에게 전달하는 것**:
- 규정 전문 공유 (PR 가이드 문서로)
- "이번 스프린트부터 api:lint가 CI 필수입니다. 통과 안 되면 머지 안 됩니다."
- State Matrix 템플릿 공유 → 다음 신규 기능부터 적용

**수집하는 데이터**:
- CI 실패율 (너무 높으면 규칙 완화)
- PR 리뷰 소요 시간 변화
- "이거 어떻게 되는 거예요?" 질문 빈도 변화

### Phase 3: 전체 가동 (Week 9~12)

**목표**: 모든 게이트가 활성화되고, MCP 서버가 연동되어 풍부한 컨텍스트를 제공한다.

| 주차 | 활성화하는 것 |
|------|---------------|
| Week 9 | VRT → 승인 필수 (머지 차단) |
| Week 10 | merge-gate.js (최종 DoD 검증 → 머지 차단) |
| Week 11 | MCP 서버 연동 (OpenAPI Diff, Chromatic) |
| Week 12 | 전체 회고 → 규정 경량화/강화 판단 |

**팀에게 전달하는 것**:
- "이번 스프린트부터 VRT 미승인 PR은 머지할 수 없습니다."
- 회고: "이 규칙 중 불필요한 거 있나요?"

---

## 6. 정착 성공 판단 기준

### 6.1 정량 지표

| 지표 | Phase 1 끝 | Phase 2 끝 | Phase 3 끝 |
|------|------------|------------|------------|
| 직접 값 사용 빈도 | 50% 감소 | 80% 감소 | 95% 감소 |
| API 불일치 질문 빈도 | — | 30% 감소 | 60% 감소 |
| PR 리뷰 첫 코멘트 시간 | — | 변화 없음 | 24시간 이내 |
| State Discovery 빈도 | — | — | 기능당 2건 이하 |
| VRT 미의도 변경 발견 | — | 측정 시작 | 월 1건 이하 |

### 6.2 정성 판단

- **성공**: "Claude Code 코멘트가 유용하다", "PR 템플릿이 자동으로 채워져서 편하다"
- **경고**: "체크가 너무 많아서 PR 올리기 귀찮다", "false positive가 자주 나온다"
- **실패**: "hook을 끄는 방법을 찾았다", "CI 통과시키려고 형식적으로 채운다"

경고/실패 신호가 보이면 즉시 규칙을 완화한다. 도구가 팀을 서빙하는 것이지, 팀이 도구를 서빙하는 게 아니다.

---

## 7. 폴더 구조 전체 요약

```
project-root/
├── .claude/
│   ├── settings.json
│   ├── hooks/
│   │   ├── pre-commit.md
│   │   ├── pre-push.md
│   │   ├── pr-create.md
│   │   └── pr-review.md
│   ├── commands/
│   │   ├── state-matrix.md
│   │   ├── api-check.md
│   │   ├── ui-check.md
│   │   └── impact.md
│   └── mcp/
│       └── servers.json
│
├── .github/
│   └── workflows/
│       └── safety-net.yml
│
├── mcp-servers/
│   ├── openapi-diff/
│   │   ├── index.ts
│   │   └── package.json
│   ├── chromatic/
│   │   ├── index.ts
│   │   └── package.json
│   ├── state-matrix/
│   │   ├── index.ts
│   │   └── package.json
│   └── figma/
│       ├── index.ts
│       └── package.json
│
├── scripts/
│   ├── ci/
│   │   └── merge-gate.js
│   ├── design-sync.js
│   ├── lint-tokens.js
│   ├── a11y-audit.js
│   ├── ui-impact.js
│   ├── ws-lint-custom.js
│   └── ws-codegen.js
│
├── api/
│   ├── openapi.json          ← 자동 생성 (수작업 금지)
│   ├── asyncapi.json         ← 자동 생성 (수작업 금지, WebSocket 사용 시)
│   └── websocket/
│       ├── events.md         ← AsyncAPI 미도입 시 대안
│       └── types.ts
│
├── docs/
│   ├── framework/
│   │   └── product-change-safety-net.md
│   ├── guidelines/
│   │   ├── ui-change-guidelines.md
│   │   ├── api-contract-guidelines.md
│   │   └── state-matrix-guidelines.md
│   ├── state-matrices/
│   │   ├── _template.md
│   │   └── (feature-name).md
│   └── templates/
│       ├── pr-template-ui.md
│       ├── pr-template-api.md
│       └── pr-template-combined.md
│
├── src/
│   ├── design-tokens/
│   │   ├── tokens.json       ← 자동 생성 (수작업 금지)
│   │   ├── tokens.css        ← 자동 생성 (수작업 금지)
│   │   └── theme.ts          ← 자동 생성 (수작업 금지)
│   ├── api/
│   │   ├── types.ts          ← 자동 생성 (수작업 금지)
│   │   ├── client.ts         ← 자동 생성 (수작업 금지)
│   │   ├── errors.ts         ← 자동 생성 (수작업 금지)
│   │   ├── ws-types.ts       ← 자동 생성 (수작업 금지)
│   │   └── ws-events.ts      ← 자동 생성 (수작업 금지)
│   ├── ui/
│   ├── screens/
│   └── storybook/
│       ├── foundations/
│       ├── components/
│       └── screens/
│
└── .spectral.yaml            ← API lint 룰셋
```

---

## 변경 이력

| 버전 | 날짜 | 변경 요약 |
|------|------|-----------|
| v1.0 | 2025-03-08 | 초안 — 이중 게이트 아키텍처, Claude Code hook 설계, MCP 서버 설계, 3단계 정착 전략 |
