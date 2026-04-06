# Probe v0.3 — 범위 정의

> **핵심 가치**: Claude Code에서 Probe의 모든 분석 기능을 자연어로 호출하고, 결과를 실시간으로 받아본다. MCP(Model Context Protocol) 서버로 Probe를 Claude Code의 도구로 등록한다.
> **v0.2와의 관계**: v0.2는 CLI로 실행하는 독립 도구다. v0.3는 그 도구를 Claude Code의 컨텍스트 안으로 끌어들인다.

---

## 0. v0.3가 하는 일 — 한 문장

**Probe의 분석 엔진을 MCP 서버로 노출하여, Claude Code가 자연어 대화 중에 PR 범위 분석/API 린트/리뷰 체크리스트를 도구로 호출할 수 있게 한다.**

---

## 1. 왜 필요한가

### 현재 구조의 한계

v0.1~v0.2의 Probe는 두 가지 방식으로 동작한다:
1. **CLI** — `npx probe check`, `npx probe api:lint` 등
2. **Claude Code skills/hooks** — `.claude/skills/`에서 `npx probe` 를 쉘로 호출

두 방식 모두 **프로세스를 fork하고 텍스트 출력을 파싱**한다. 이 구조의 문제:

```
현재: Claude Code → shell → npx probe → stdout 텍스트 → Claude Code가 텍스트 파싱
      (비효율: 프로세스 fork, 텍스트 직렬화/역직렬화, 에러 핸들링 복잡)

목표: Claude Code → MCP tool call → Probe 분석 엔진 → 구조화된 JSON 응답
      (효율: 단일 프로세스, 타입 안전, 네이티브 연동)
```

### MCP가 해결하는 것

| 현재 (CLI/hooks) | MCP 서버 |
|---------|----------|
| shell 호출 + 텍스트 파싱 | 구조화된 JSON 응답 |
| 매번 프로세스 fork | 상주 서버, 즉시 응답 |
| 에러 시 stderr 파싱 필요 | MCP 에러 프로토콜 |
| skill 프롬프트로 간접 호출 | Claude가 도구로 직접 호출 |
| 사용자가 `/check-scope` 입력 | Claude가 필요할 때 자동 호출 |
| 결과를 다시 해석해야 함 | JSON 구조 그대로 사용 |

### 사용자 경험 변화

**Before (v0.2):**
```
사용자: "PR 만들어줘"
Claude: /check-scope 실행 → 쉘에서 npx probe check → 텍스트 결과 읽기 → 해석 → 응답
```

**After (v0.3):**
```
사용자: "PR 만들어줘"
Claude: (자동으로 probe.analyzeScope 도구 호출) → 구조화된 결과 → 즉시 판단 → 응답
        (자동으로 probe.reviewChecklist 도구 호출) → 체크리스트 → 리뷰 포인트 포함
```

사용자가 명시적으로 커맨드를 입력하지 않아도, Claude가 맥락에 따라 Probe 도구를 **자동으로** 호출한다.

---

## 2. MCP 서버 설계

### 2.1 서버 구조

```
src/mcp/
├── server.ts          ← MCP 서버 메인 (stdio transport)
├── tools.ts           ← 도구 정의 (inputSchema, handler)
├── resources.ts       ← 리소스 정의 (프로파일, 설정)
└── prompts.ts         ← 프롬프트 템플릿
```

Probe MCP 서버는 **stdio transport**를 사용한다. Claude Code의 MCP 설정에 등록하면 상주 프로세스로 동작한다.

### 2.2 서버 등록

```json
// .claude/settings.json 또는 ~/.claude/settings.json
{
  "mcpServers": {
    "probe": {
      "command": "node",
      "args": ["./dist/mcp/server.js"],
      "env": {}
    }
  }
}
```

또는 빌드 없이 직접 실행:
```json
{
  "mcpServers": {
    "probe": {
      "command": "npx",
      "args": ["tsx", "./src/mcp/server.ts"]
    }
  }
}
```

---

## 3. 도구 (Tools) 정의

### 3.1 `probe.analyzeScope`

PR 범위를 분석한다. v0.1 코어 엔진 직접 호출.

```typescript
{
  name: "probe.analyzeScope",
  description: "변경 파일 목록으로 PR 범위를 분석한다. 응집 그룹, 관심사 혼재, 분할 제안을 반환한다.",
  inputSchema: {
    type: "object",
    properties: {
      base: {
        type: "string",
        description: "기준 브랜치 (기본: origin/main)",
        default: "origin/main"
      },
      files: {
        type: "array",
        items: { type: "string" },
        description: "분석할 파일 목록 (미지정 시 git diff로 자동 수집)"
      }
    }
  }
}
```

**반환**: `ScopeAnalysisResult` JSON

### 3.2 `probe.lintApiSpec`

OpenAPI 스펙을 린트한다. v0.2 내장 린트 엔진 직접 호출.

```typescript
{
  name: "probe.lintApiSpec",
  description: "OpenAPI 스펙 파일의 품질을 검증한다. 10개 내장 룰로 필드 타입, nullable, 에러 응답, 네이밍 규칙을 검사한다.",
  inputSchema: {
    type: "object",
    properties: {
      specPath: {
        type: "string",
        description: "OpenAPI 스펙 파일 경로 (기본: api/openapi.json)"
      }
    }
  }
}
```

**반환**: `ApiLintResult` JSON

### 3.3 `probe.diffApiSpecs`

두 버전의 API 스펙을 비교한다.

```typescript
{
  name: "probe.diffApiSpecs",
  description: "기준 브랜치와 현재 브랜치의 API 스펙을 비교한다. breaking 변경, additive 변경, deprecation을 분류한다.",
  inputSchema: {
    type: "object",
    properties: {
      base: {
        type: "string",
        description: "기준 브랜치 (기본: origin/main)",
        default: "origin/main"
      },
      specPath: {
        type: "string",
        description: "스펙 파일 경로 (기본: api/openapi.json)"
      }
    }
  }
}
```

**반환**: `ApiDiffResult` JSON

### 3.4 `probe.reviewChecklist`

리뷰 체크리스트를 생성한다.

```typescript
{
  name: "probe.reviewChecklist",
  description: "변경 내용을 분석하여 PR 타입을 추론하고, 해당 타입의 리뷰 체크리스트를 생성한다.",
  inputSchema: {
    type: "object",
    properties: {
      base: {
        type: "string",
        description: "기준 브랜치 (기본: origin/main)",
        default: "origin/main"
      }
    }
  }
}
```

**반환**: `ReviewChecklist` JSON

### 3.5 `probe.detectPlatform`

프로젝트의 플랫폼을 감지한다.

```typescript
{
  name: "probe.detectPlatform",
  description: "프로젝트 파일 구조를 분석하여 플랫폼(spring-boot, nextjs, react-spa)을 감지한다.",
  inputSchema: {
    type: "object",
    properties: {}
  }
}
```

**반환**: `{ platform: string, profile: PlatformProfile }`

---

## 4. 리소스 (Resources) 정의

MCP 리소스는 Claude에게 참조 데이터를 제공한다.

### 4.1 `probe://profiles/{platform}`

플랫폼 프로파일 정보를 제공한다.

```
probe://profiles/spring-boot  → Spring Boot 프로파일 JSON
probe://profiles/nextjs        → Next.js 프로파일 JSON
probe://profiles/react-spa     → React SPA 프로파일 JSON
```

### 4.2 `probe://config`

현재 프로젝트의 probe 설정을 제공한다.

```
probe://config  → 로드된 ProbeConfig JSON
```

### 4.3 `probe://guidelines/{name}`

규정 문서를 텍스트로 제공한다.

```
probe://guidelines/api-contract      → 규정 ② API 계약 가이드라인
probe://guidelines/state-matrix      → 규정 ① State Matrix 가이드라인
probe://guidelines/ui-change         → 규정 ③ UI 변경 가이드라인
```

---

## 5. 프롬프트 (Prompts) 정의

MCP 프롬프트는 사전 정의된 상호작용 템플릿이다.

### 5.1 `probe.prReview`

PR 리뷰를 수행하는 프롬프트.

```typescript
{
  name: "probe.prReview",
  description: "현재 변경에 대해 probe 분석 결과를 기반으로 구조화된 코드 리뷰를 수행한다.",
  arguments: [
    { name: "base", description: "기준 브랜치", required: false }
  ]
}
```

프롬프트 생성 시 `probe.analyzeScope`와 `probe.reviewChecklist` 결과를 포함한 리뷰 지시 프롬프트를 반환한다.

### 5.2 `probe.splitPr`

PR 분할을 안내하는 프롬프트.

```typescript
{
  name: "probe.splitPr",
  description: "현재 변경을 여러 PR로 분할하는 방법을 안내한다.",
  arguments: []
}
```

---

## 6. 기존 `.claude/` 어댑터와의 관계

### 공존 전략

MCP 서버가 도입되어도 기존 skills/hooks/agents는 유지한다:

| 기존 | MCP 대응 | 공존 |
|------|----------|------|
| `/check-scope` skill | `probe.analyzeScope` 도구 | skill은 MCP 미지원 환경 폴백 |
| `/split-pr` skill | `probe.splitPr` 프롬프트 | 동일 |
| `/state-matrix` skill | (없음, v0.4 범위) | skill 유지 |
| PostToolUse hook | (유지) | hook은 자동 실행, MCP는 요청 시 |
| code-reviewer agent | `probe.prReview` 프롬프트 | agent가 MCP 도구를 호출하도록 개선 |
| test-writer agent | (유지) | agent 자체는 MCP 불필요 |

### Skills → MCP 마이그레이션

기존 skills는 내부적으로 `npx probe` 쉘 호출을 하지만, MCP가 활성화된 환경에서는 Claude가 MCP 도구를 우선 사용한다. Skills는 MCP가 없는 환경의 폴백으로 유지.

---

## 7. 구현 상세

### 7.1 의존성

```json
{
  "dependencies": {
    "@modelcontextprotocol/sdk": "^1.0.0"
  }
}
```

MCP SDK만 추가. 나머지는 기존 코어 엔진을 그대로 사용.

### 7.2 서버 메인 (`server.ts`)

```typescript
// 핵심 구조
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';

const server = new McpServer({
  name: 'probe',
  version: '0.3.0',
});

// 도구 등록
registerTools(server);

// 리소스 등록
registerResources(server);

// 프롬프트 등록
registerPrompts(server);

// stdio transport로 실행
const transport = new StdioServerTransport();
await server.connect(transport);
```

### 7.3 도구 핸들러 패턴

각 도구는 기존 코어 함수를 직접 호출한다. CLI처럼 프로세스를 fork하지 않는다.

```typescript
// 예: analyzeScope 도구
server.tool(
  'probe.analyzeScope',
  { base: z.string().optional(), files: z.array(z.string()).optional() },
  async ({ base, files }) => {
    const config = await loadConfigAsync();
    const profile = resolveProfile(config);
    const changedFiles = files ?? getChangedFiles(base ?? 'origin/main');
    const diffLines = getDiffLines(base ?? 'origin/main');
    const result = analyzeScope(changedFiles, profile, diffLines);

    return {
      content: [{ type: 'text', text: JSON.stringify(result, null, 2) }],
    };
  },
);
```

### 7.4 Git 연동 함수 분리

현재 git 관련 함수(`getChangedFiles`, `getDiffLines`)는 `cli/index.ts`에 있다. MCP 서버에서도 사용하므로, 공용 유틸로 분리한다.

```
src/utils/git.ts  ← NEW (cli/index.ts에서 추출)
  - getChangedFiles(base: string): string[]
  - getDiffLines(base: string): number
  - getBaseFileContent(base: string, filePath: string): string | undefined
```

---

## 8. 프로젝트 구조 변경

```
probe/
├── src/
│   ├── core/                    ← 변경 없음
│   ├── api/                     ← 변경 없음
│   ├── review/                  ← 변경 없음
│   ├── profiles/                ← 변경 없음
│   ├── cli/
│   │   └── index.ts             ← 리팩터: git 함수를 utils/git.ts로 이동
│   ├── mcp/                     ← v0.3 NEW
│   │   ├── server.ts            ← MCP 서버 메인
│   │   ├── tools.ts             ← 5개 도구 핸들러
│   │   ├── resources.ts         ← 3개 리소스 핸들러
│   │   └── prompts.ts           ← 2개 프롬프트 핸들러
│   └── utils/
│       ├── logger.ts            ← 변경 없음
│       ├── glob-match.ts        ← 변경 없음
│       └── git.ts               ← v0.3 NEW (cli에서 추출)
├── tests/
│   ├── mcp-tools.test.ts        ← v0.3 NEW
│   └── ...
└── .claude/
    └── settings.json            ← mcpServers 설정 추가
```

---

## 9. 빌드 설정 변경

```typescript
// tsup.config.ts — entry 추가
export default defineConfig({
  entry: {
    index: 'src/index.ts',
    'cli/index': 'src/cli/index.ts',
    'mcp/server': 'src/mcp/server.ts',  // NEW
  },
  // ...
});
```

```json
// package.json — bin 추가
{
  "bin": {
    "probe": "dist/cli/index.js",
    "probe-mcp": "dist/mcp/server.js"
  }
}
```

---

## 10. 사용자 경험 시나리오

### 시나리오 1: Claude Code에서 자연어로 PR 리뷰

```
사용자: "이 코드 리뷰해줘"

Claude: (내부적으로 probe.analyzeScope 호출)
        (내부적으로 probe.reviewChecklist 호출)
        (내부적으로 probe.lintApiSpec 호출 — API 스펙 변경 감지 시)

        "PR 리뷰 결과입니다.

        **범위**: ✅ 정상 — domain-crud (User), 7개 파일
        **PR 타입**: domain-crud

        ### 리뷰 포인트
        - ✅ 테스트 파일 존재 (UserServiceTest.kt)
        - ⬜ nullable/required 스펙 반영 — UserResponse.nickname이 nullable인데
          nullable: true가 없습니다 (API 린트에서 감지)
        - ⬜ 에러 응답 ErrorResponse 준수 여부 확인 필요

        ### API 린트 결과
        - ERROR: UserResponse.nickname — nullable 미표시 (규정 ② § 2.3.1)"
```

### 시나리오 2: PR 생성 직전 자동 검증

```
사용자: "PR 만들어줘"

Claude: (PR 생성 전에 probe.analyzeScope 자동 호출)
        (결과: severity=warn, 3개 그룹)

        "PR을 만들기 전에 범위를 확인했습니다.

        🔶 현재 변경이 3개 관심사에 걸쳐 있습니다:
        1. domain-crud (User) — 4개 파일
        2. config-change — 2개 파일
        3. migration — 1개 파일

        분할을 권장합니다:
        PR 1: migration (V3__add_user.sql)
        PR 2: config-change (SecurityConfig.kt, JwtConfig.kt)
        PR 3: domain-crud (User CRUD 4개 파일)

        그래도 하나의 PR로 진행할까요, 분할할까요?"
```

### 시나리오 3: 규정 참조

```
사용자: "에러 응답 규정이 어떻게 되지?"

Claude: (probe://guidelines/api-contract 리소스 참조)

        "규정 ② § 2.3.2에 따르면, 모든 4xx/5xx 응답은 ErrorResponse 스키마를
        참조해야 합니다. 구조는:
        - code: 에러 코드 (string)
        - message: 사용자용 메시지 (string)
        - details: 상세 정보 (optional, array)
        ..."
```

---

## 11. v0.3 전체 기능 범위

### 포함 (v0.3)

| 기능 | 설명 | 형태 |
|------|------|------|
| **MCP 서버** | stdio transport, 상주 프로세스 | 서버 |
| **5개 도구** | analyzeScope, lintApiSpec, diffApiSpecs, reviewChecklist, detectPlatform | MCP Tool |
| **3개 리소스** | profiles, config, guidelines | MCP Resource |
| **2개 프롬프트** | prReview, splitPr | MCP Prompt |
| **git 유틸 분리** | cli → utils/git.ts 리팩터 | 리팩터 |
| **빌드 설정** | mcp/server entry 추가 | 설정 |

### 미포함 (v0.4 이후)

| 기능 | 이유 | 예정 버전 |
|------|------|-----------|
| 칼라(Khala) 연동 | 설계 맥락 기반 리뷰는 v0.4 | v0.4 |
| MCP sampling | Claude ↔ Probe 양방향 호출은 과도 | v0.4+ |
| SSE transport | 로컬 사용이 주 용도, SSE 불필요 | 미정 |
| 커스텀 도구 등록 API | 사용자가 MCP 도구를 확장하는 기능 | v0.5+ |

---

## 12. 구현 우선순위

| 순서 | 구현 대상 | 예상 코드량 |
|------|-----------|-------------|
| 1 | `utils/git.ts` — cli에서 git 함수 추출 | ~100줄 |
| 2 | `mcp/tools.ts` — 5개 도구 핸들러 | ~200줄 |
| 3 | `mcp/resources.ts` — 3개 리소스 핸들러 | ~100줄 |
| 4 | `mcp/prompts.ts` — 2개 프롬프트 핸들러 | ~80줄 |
| 5 | `mcp/server.ts` — 서버 메인 + transport | ~60줄 |
| 6 | CLI 리팩터 — git 함수를 utils/git.ts에서 import | ~20줄 |
| 7 | 빌드/패키지 설정 | ~10줄 |
| 8 | `.claude/settings.json` — mcpServers 등록 | ~5줄 |
| 9 | 테스트 | ~300줄 |

**총 예상**: ~875줄 (테스트 포함)

v0.3는 **기존 코어 엔진을 감싸는 얇은 레이어**이므로, v0.2보다 코드량이 적다.

---

## 13. 테스트 계획

### MCP 도구 테스트

```
- analyzeScope: 파일 목록 직접 전달 → ScopeAnalysisResult 반환 확인
- analyzeScope: 빈 파일 목록 → ok 반환
- lintApiSpec: 유효한 스펙 → 린트 결과 반환
- lintApiSpec: 존재하지 않는 경로 → 빈 결과 반환
- diffApiSpecs: 동일한 스펙 → 빈 변경 목록
- reviewChecklist: 파일 역할 기반 PR 타입 추론 확인
- detectPlatform: 프로파일 반환 확인
```

### MCP 리소스 테스트

```
- profiles/{platform}: 올바른 프로파일 JSON 반환
- config: 현재 설정 반환
- guidelines/{name}: 규정 텍스트 반환
```

### 통합 테스트

```
- MCP 서버 시작 → 도구 목록 조회 → 도구 호출 → 응답 검증
- 설정 변경 후 도구 호출 → 오버라이드 반영 확인
```

---

## 변경 이력

| 버전 | 날짜 | 변경 |
|------|------|------|
| v0.3-draft | 2026-03-11 | 초안 — MCP 서버 설계, 도구/리소스/프롬프트 정의 |
