# CI 스크립트 구현 가이드

> 프레임워크 부속 문서. 각 규정에서 요구하는 자동화 스크립트의 구현 방법.
> "무엇을 만들어야 하는지"는 규정에 있고, 이 문서는 "어떻게 만드는지"를 다룬다.

---

## 0. 전체 스크립트 맵

```
package.json scripts
│
├─ 규정 ① (State Matrix)
│   └─ (CI 스크립트 없음 — Kick-off 체크리스트는 Claude Code hook으로 처리)
│
├─ 규정 ② (API 계약)
│   ├─ api:generate    코드 → OpenAPI/AsyncAPI 스펙 생성
│   ├─ api:lint        스펙 품질 검증
│   ├─ api:diff        스펙 변경 탐지 + breaking 판별
│   ├─ api:compatibility  이전 버전과 호환성 검사
│   ├─ api:codegen     스펙 → FE 타입/클라이언트 생성
│   ├─ api:mock        스펙 기반 Mock 서버
│   ├─ ws:lint         AsyncAPI 스펙 검증
│   └─ ws:codegen      AsyncAPI → FE 이벤트 타입 생성
│
├─ 규정 ③ (UI 변경)
│   ├─ design:sync     Figma → 토큰 산출물 생성
│   ├─ lint:tokens     토큰 네이밍/순환/대비 검증
│   ├─ lint:a11y       Storybook 기반 접근성 검사
│   ├─ vrt:run         VRT 실행 (Chromatic)
│   └─ ui:impact       토큰 → 컴포넌트 → 화면 영향 분석
│
└─ 공통
    ├─ typecheck       TypeScript 타입체크
    ├─ lint            ESLint/Stylelint
    └─ storybook:build Storybook 빌드
```

---

## 1. 규정 ② 스크립트

### 1.1 `api:generate` — 코드에서 스펙 생성

**목적**: 코드의 어노테이션/데코레이터에서 OpenAPI(+ AsyncAPI) 스펙을 자동 생성하여 레포에 커밋

#### Spring/Kotlin 구현

```bash
# package.json
"api:generate": "cd backend && ./gradlew generateOpenApiDocs && cp build/openapi.json ../api/openapi.json"
```

**필요 의존성**:

```kotlin
// build.gradle.kts
dependencies {
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:2.x.x")
    // WebSocket 사용 시
    implementation("io.github.springwolf:springwolf-core:x.x.x")
    implementation("io.github.springwolf:springwolf-ui:x.x.x")
}
```

**springdoc 설정**:

```yaml
# application.yaml
springdoc:
  api-docs:
    path: /v3/api-docs
  swagger-ui:
    path: /swagger-ui.html
  default-produces-media-type: application/json
```

**컨트롤러 어노테이션 예시**:

```kotlin
@Operation(summary = "사용자 목록 조회", description = "관리자 권한 필요")
@ApiResponses(value = [
    ApiResponse(responseCode = "200", description = "성공",
        content = [Content(schema = Schema(implementation = UserListResponse::class))]),
    ApiResponse(responseCode = "401", description = "인증 필요",
        content = [Content(schema = Schema(implementation = ErrorResponse::class))]),
    ApiResponse(responseCode = "403", description = "권한 없음",
        content = [Content(schema = Schema(implementation = ErrorResponse::class))])
])
@GetMapping("/users")
fun getUsers(@RequestParam cursor: String?, @RequestParam limit: Int = 20): UserListResponse
```

**핵심**: 어노테이션을 성실하게 다는 것이 스펙 품질의 전부다. 자동 생성 도구는 어노테이션에 있는 것만 뽑는다.

#### CI에서 스펙 동기화 확인

```bash
# CI step: 스펙이 코드와 일치하는지 확인
pnpm api:generate
git diff --exit-code api/openapi.json || (echo "❌ 스펙 파일이 코드와 불일치합니다. pnpm api:generate 후 커밋하세요." && exit 1)
```

---

### 1.2 `api:lint` — 스펙 품질 검증

**목적**: OpenAPI 스펙이 팀 규칙(Level 2~3)을 준수하는지 자동 검사

**추천 도구**: [Spectral](https://github.com/stoplightio/spectral) (OpenAPI 전용 린터)

```bash
# 설치
npm install -g @stoplight/spectral-cli

# package.json
"api:lint": "spectral lint api/openapi.json --ruleset .spectral.yaml"
```

**커스텀 룰셋 (`.spectral.yaml`)**:

```yaml
extends: ["spectral:oas"]

rules:
  # Level 1 — 기본
  oas3-schema: error
  typed-enum: error

  # Level 2 — 연동 가능
  no-ambiguous-nullable:
    description: "nullable과 optional 동시 적용 금지"
    severity: warn
    given: "$.components.schemas..properties.*"
    then:
      function: schema
      functionOptions:
        schema:
          not:
            required: ["nullable"]
            # optional인 동시에 nullable인 필드 탐지

  error-response-schema:
    description: "4xx/5xx 응답은 ErrorResponse 스키마를 따라야 함"
    severity: error
    given: "$.paths.*.*.responses[?(@property >= '400')]"
    then:
      field: "content.application/json.schema.$ref"
      function: pattern
      functionOptions:
        match: "ErrorResponse"

  pagination-required:
    description: "배열 응답에 페이지네이션 필수"
    severity: warn
    given: "$.paths.*.get.responses.200.content.application/json.schema"
    then:
      function: schema
      functionOptions:
        schema:
          # items가 array인 경우 cursor/total 존재 확인
          required: ["properties"]

  # Level 3 — 유지보수 가능
  require-description:
    description: "주요 필드에 description 권장"
    severity: warn
    given: "$.components.schemas..properties.*"
    then:
      field: "description"
      function: truthy

  require-example-for-dates:
    description: "날짜/금액 필드에 example 필수"
    severity: warn
    given: "$.components.schemas..properties[?(@.format == 'date-time')]"
    then:
      field: "example"
      function: truthy

  naming-convention-paths:
    description: "엔드포인트 경로는 kebab-case"
    severity: error
    given: "$.paths"
    then:
      field: "@key"
      function: pattern
      functionOptions:
        match: "^(/[a-z0-9-{}]+)+$"

  naming-convention-properties:
    description: "필드명은 camelCase"
    severity: error
    given: "$.components.schemas..properties"
    then:
      field: "@key"
      function: casing
      functionOptions:
        type: camel
```

**참고**: 위 룰셋은 출발점이다. `no-ambiguous-nullable`과 `error-response-schema`는 Spectral 커스텀 함수로 더 정교하게 구현해야 할 수 있다. 핵심은 팀 규칙을 코드로 표현해서 리뷰어가 매번 수동으로 확인하지 않게 하는 것이다.

---

### 1.3 `api:diff` — 스펙 변경 탐지 + breaking 판별

**목적**: PR에서 API 스펙이 어떻게 변경되었는지 자동 분석하고, breaking 여부를 판별

**추천 도구**: [oasdiff](https://github.com/Tufin/oasdiff)

```bash
# 설치
go install github.com/tufin/oasdiff@latest
# 또는 npm
npm install -g oasdiff

# package.json
"api:diff": "oasdiff diff api/openapi.json api/openapi.json --base-ref origin/main --format markdown",
"api:diff:breaking": "oasdiff breaking api/openapi.json api/openapi.json --base-ref origin/main"
```

**CI에서 PR 코멘트로 게시**:

```bash
# CI step
DIFF_RESULT=$(oasdiff changelog \
  <(git show origin/main:api/openapi.json) \
  api/openapi.json \
  --format markdown)

BREAKING_RESULT=$(oasdiff breaking \
  <(git show origin/main:api/openapi.json) \
  api/openapi.json \
  --format markdown 2>&1 || true)

# GitHub PR 코멘트로 게시
gh pr comment $PR_NUMBER --body "## API Diff Report
${DIFF_RESULT}

### Breaking Changes
${BREAKING_RESULT:-✅ No breaking changes detected}"
```

**oasdiff가 탐지하는 breaking 변경**:
- 엔드포인트 삭제
- required 필드 추가 (요청)
- 필드 타입 변경
- enum 값 제거
- 응답 필드 삭제

---

### 1.4 `api:compatibility` — 호환성 상세 검사

**목적**: `api:breaking` 라벨 PR에서 이전 버전과의 호환성을 상세 검사

```bash
# oasdiff의 breaking 검사를 엄격 모드로 실행
"api:compatibility": "oasdiff breaking <(git show origin/main:api/openapi.json) api/openapi.json --fail-on ERR"
```

`--fail-on ERR`은 breaking 변경이 있으면 exit code 1을 반환하여 CI를 실패시킨다. `api:breaking` 라벨이 붙은 PR에서는 이 실패를 **예상된 것으로 간주**하고, 마이그레이션 가이드 존재 여부로 게이트한다.

---

### 1.5 `api:codegen` — FE 타입/클라이언트 자동 생성

**목적**: OpenAPI 스펙에서 FE 타입과 API 호출 함수를 자동 생성

**추천 도구**: [openapi-typescript](https://github.com/drwpow/openapi-typescript) (타입만) 또는 [orval](https://github.com/anymaniax/orval) (타입 + 클라이언트)

#### openapi-typescript (경량, 타입만)

```bash
npm install -D openapi-typescript

# package.json
"api:codegen": "openapi-typescript api/openapi.json -o src/api/types.ts"
```

#### orval (타입 + API 클라이언트 + React Query 훅)

```bash
npm install -D orval

# package.json
"api:codegen": "orval"
```

```typescript
// orval.config.ts
export default {
  api: {
    input: './api/openapi.json',
    output: {
      target: './src/api/client.ts',
      schemas: './src/api/types',
      client: 'react-query',  // 또는 'axios', 'fetch'
      mode: 'tags-split',
    },
  },
};
```

**생성물 예시**:

```typescript
// src/api/types.ts (자동 생성 — 수작업 편집 금지)
export interface UserListResponse {
  items: User[];
  cursor: string | null;
  total: number;
}

export interface User {
  id: string;
  name: string;
  email: string;
  nickname: string | null;  // nullable이 정확히 반영됨
  status: 'ACTIVE' | 'INACTIVE' | 'SUSPENDED';  // enum이 union type으로
}

export interface ErrorResponse {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown> | null;
  };
}
```

---

### 1.6 `api:mock` — Mock 서버

**목적**: API 스펙 기반으로 Mock 응답을 반환하는 서버 실행

**추천 도구**: [Prism](https://github.com/stoplightio/prism) (스펙 기반) 또는 [MSW](https://mswjs.io/) (FE 내장)

#### Prism (독립 Mock 서버)

```bash
npm install -D @stoplight/prism-cli

# package.json
"api:mock": "prism mock api/openapi.json --port 4010"
```

Prism은 스펙의 example이 있으면 example을 반환하고, 없으면 스키마 기반으로 랜덤 데이터를 생성한다.

#### MSW (FE 코드 내 Mock)

```bash
npm install -D msw
```

MSW는 FE 코드 내에서 Service Worker로 API를 가로채는 방식이다. 스펙에서 직접 생성하려면 `msw` + `@mswjs/data` + 커스텀 스크립트가 필요하다. Prism보다 설정이 복잡하지만 FE 테스트와 통합하기 좋다.

**권장**: 처음에는 Prism으로 시작하고, FE 테스트 통합이 필요해지면 MSW로 전환.

---

### 1.7 `ws:lint` — AsyncAPI 스펙 검증

**목적**: AsyncAPI 스펙이 팀 규칙(메시지 봉투, 네이밍, 필수 이벤트)을 준수하는지 검사

**추천 도구**: [AsyncAPI CLI](https://github.com/asyncapi/cli)

```bash
npm install -g @asyncapi/cli

# package.json
"ws:lint": "asyncapi validate api/asyncapi.json && node scripts/ws-lint-custom.js"
```

**커스텀 검증 스크립트 (`scripts/ws-lint-custom.js`)**:

```javascript
const fs = require('fs');
const spec = JSON.parse(fs.readFileSync('api/asyncapi.json', 'utf-8'));

const errors = [];

// 1. 메시지 봉투 검증 — 모든 메시지에 eventType, timestamp 필수
for (const [channelName, channel] of Object.entries(spec.channels || {})) {
  const messages = [
    ...(channel.subscribe?.message ? [channel.subscribe.message] : []),
    ...(channel.publish?.message ? [channel.publish.message] : []),
  ];

  for (const msg of messages) {
    const payload = msg.payload || (msg.$ref ? resolveRef(msg.$ref, spec) : {});
    const required = payload.required || [];
    if (!required.includes('eventType')) {
      errors.push(`${channelName}: 메시지에 eventType이 required가 아닙니다`);
    }
    if (!required.includes('timestamp')) {
      errors.push(`${channelName}: 메시지에 timestamp가 required가 아닙니다`);
    }
  }
}

// 2. eventType 네이밍 — UPPER_SNAKE_CASE
for (const [name, schema] of Object.entries(spec.components?.schemas || {})) {
  const eventType = schema.properties?.eventType;
  if (eventType?.enum) {
    for (const val of eventType.enum) {
      if (!/^[A-Z][A-Z0-9_]*$/.test(val)) {
        errors.push(`${name}: eventType "${val}"이 UPPER_SNAKE_CASE가 아닙니다`);
      }
    }
  }
}

// 3. 연결 상태 이벤트 필수 확인
const allEventTypes = [];
for (const schema of Object.values(spec.components?.messages || {})) {
  const payload = schema.payload || {};
  if (payload.properties?.eventType?.enum) {
    allEventTypes.push(...payload.properties.eventType.enum);
  }
}
const requiredEvents = ['CONNECTED', 'DISCONNECTED', 'ERROR'];
for (const evt of requiredEvents) {
  if (!allEventTypes.includes(evt)) {
    errors.push(`필수 연결 상태 이벤트 "${evt}"가 정의되지 않았습니다`);
  }
}

if (errors.length > 0) {
  console.error('❌ ws:lint 실패');
  errors.forEach(e => console.error(`  - ${e}`));
  process.exit(1);
} else {
  console.log('✅ ws:lint 통과');
}

function resolveRef(ref, spec) {
  const path = ref.replace('#/', '').split('/');
  return path.reduce((obj, key) => obj?.[key], spec) || {};
}
```

---

### 1.8 `ws:codegen` — FE 이벤트 타입 생성

**목적**: AsyncAPI 스펙에서 FE 이벤트 타입을 자동 생성

**추천 도구**: [AsyncAPI Generator](https://github.com/asyncapi/generator) + TypeScript 템플릿

```bash
npm install -g @asyncapi/generator

# package.json
"ws:codegen": "ag api/asyncapi.json @asyncapi/typescript-nats-template -o src/api/ws-generated/ --force-write"
```

**현실적 대안**: AsyncAPI Generator의 TypeScript 템플릿이 팀 요구에 안 맞으면 간단한 커스텀 스크립트로 대체.

```javascript
// scripts/ws-codegen.js
const fs = require('fs');
const spec = JSON.parse(fs.readFileSync('api/asyncapi.json', 'utf-8'));

let output = `// 자동 생성 파일 — 수작업 편집 금지\n// 생성 시점: ${new Date().toISOString()}\n\n`;

// eventType enum 생성
const eventTypes = new Set();
for (const msg of Object.values(spec.components?.messages || {})) {
  const enums = msg.payload?.properties?.eventType?.enum || [];
  enums.forEach(e => eventTypes.add(e));
}
output += `export type WsEventType = ${[...eventTypes].map(e => `'${e}'`).join(' | ')};\n\n`;

// 메시지별 페이로드 타입 생성
for (const [name, msg] of Object.entries(spec.components?.messages || {})) {
  const props = msg.payload?.properties?.data?.properties || {};
  const required = msg.payload?.properties?.data?.required || [];
  output += `export interface ${name}Payload {\n`;
  for (const [field, schema] of Object.entries(props)) {
    const optional = required.includes(field) ? '' : '?';
    const type = mapType(schema);
    output += `  ${field}${optional}: ${type};\n`;
  }
  output += `}\n\n`;
}

// 공통 메시지 래퍼
output += `export interface WsMessage<T = unknown> {
  eventType: WsEventType;
  data: T;
  timestamp: string;
  correlationId?: string;
}\n\n`;

output += `export interface WsError {
  eventType: 'ERROR';
  error: { code: string; message: string };
  timestamp: string;
}\n`;

fs.writeFileSync('src/api/ws-types.ts', output);
console.log('✅ ws:codegen 완료 → src/api/ws-types.ts');

function mapType(schema) {
  if (schema.type === 'string') return schema.nullable ? 'string | null' : 'string';
  if (schema.type === 'integer' || schema.type === 'number') return 'number';
  if (schema.type === 'boolean') return 'boolean';
  if (schema.type === 'array') return `${mapType(schema.items)}[]`;
  if (schema.type === 'object') return 'Record<string, unknown>';
  return 'unknown';
}
```

---

## 2. 규정 ③ 스크립트

### 2.1 `design:sync` — Figma → 토큰 산출물 생성

**목적**: Figma Variables API에서 토큰을 추출하여 `tokens.json`, `tokens.css`, `theme.ts`를 생성

**구현 개요**:

```bash
# package.json
"design:sync": "node scripts/design-sync.js"
```

```javascript
// scripts/design-sync.js (뼈대)
const FIGMA_FILE_KEY = process.env.FIGMA_FILE_KEY;
const FIGMA_TOKEN = process.env.FIGMA_ACCESS_TOKEN;

async function main() {
  // 1. Figma Variables API 호출
  const variables = await fetchFigmaVariables(FIGMA_FILE_KEY, FIGMA_TOKEN);

  // 2. tokens.json 생성 (모드별 값, alias, 메타데이터)
  const tokensJson = transformToTokensJson(variables);
  writeFileSync('src/design-tokens/tokens.json', JSON.stringify(tokensJson, null, 2));

  // 3. tokens.css 생성 (CSS custom properties)
  const tokensCss = generateCssVariables(tokensJson);
  writeFileSync('src/design-tokens/tokens.css', tokensCss);

  // 4. theme.ts 생성 (TypeScript theme 객체)
  const themeTs = generateThemeTs(tokensJson);
  writeFileSync('src/design-tokens/theme.ts', themeTs);

  // 5. diff 요약 출력
  console.log(generateDiffSummary());
}

async function fetchFigmaVariables(fileKey, token) {
  const res = await fetch(
    `https://api.figma.com/v1/files/${fileKey}/variables/local`,
    { headers: { 'X-Figma-Token': token } }
  );
  return res.json();
}

// ... 변환 로직 구현
```

**참고**: Figma Variables API는 Enterprise/Organization 플랜에서만 사용 가능할 수 있다. 무료 플랜이면 [Tokens Studio](https://tokens.studio/) 플러그인의 JSON export를 대안으로 사용.

---

### 2.2 `lint:tokens` — 토큰 검증

**목적**: 토큰 네이밍 규칙, 순환 alias, 모드 일관성, WCAG 대비를 자동 검사

```bash
# package.json
"lint:tokens": "node scripts/lint-tokens.js"
```

**구현 핵심 검사 항목**:

```javascript
// scripts/lint-tokens.js (핵심 로직)
const tokens = require('../src/design-tokens/tokens.json');

const errors = [];
const warnings = [];

// 1. 네이밍 규칙 검사
for (const key of Object.keys(tokens)) {
  if (key.startsWith('color.') && !/^color\.(text|bg|border|status)\.\w+$/.test(key)) {
    errors.push(`네이밍 위반: "${key}" — color.{role}.{name} 형식이어야 합니다`);
  }
  // space, radius, shadow, type, motion 도 동일 패턴
}

// 2. 순환 alias 검사
function detectCycle(key, visited = new Set()) {
  if (visited.has(key)) return true;
  visited.add(key);
  const value = tokens[key];
  if (value?.alias) return detectCycle(value.alias, visited);
  return false;
}
for (const key of Object.keys(tokens)) {
  if (detectCycle(key)) errors.push(`순환 alias: "${key}"`);
}

// 3. 모드 일관성 검사 (light/dark 모드 간 키 누락)
const lightKeys = new Set(Object.keys(tokens.modes?.light || {}));
const darkKeys = new Set(Object.keys(tokens.modes?.dark || {}));
for (const key of lightKeys) {
  if (!darkKeys.has(key)) errors.push(`모드 누락: "${key}"가 dark 모드에 없습니다`);
}
for (const key of darkKeys) {
  if (!lightKeys.has(key)) errors.push(`모드 누락: "${key}"가 light 모드에 없습니다`);
}

// 4. WCAG AA 대비 검사
// color.text.* ↔ color.bg.* 쌍에 대해 대비 비율 계산
// 라이브러리: wcag-contrast 또는 직접 구현
const { getContrastRatio } = require('./contrast-utils');
const textTokens = Object.entries(tokens).filter(([k]) => k.startsWith('color.text.'));
const bgTokens = Object.entries(tokens).filter(([k]) => k.startsWith('color.bg.'));
for (const [textKey, textVal] of textTokens) {
  for (const [bgKey, bgVal] of bgTokens) {
    const ratio = getContrastRatio(resolveValue(textVal), resolveValue(bgVal));
    if (ratio < 4.5) {
      errors.push(`대비 미달: ${textKey}(${textVal}) on ${bgKey}(${bgVal}) = ${ratio.toFixed(2)}:1 (최소 4.5:1)`);
    }
  }
}

// 5. deprecated 토큰 사용 경고
for (const [key, val] of Object.entries(tokens)) {
  if (val.deprecated) {
    warnings.push(`deprecated: "${key}" — 대체: "${val.replacement}" (${val.deprecatedSince}부터)`);
  }
}

// 결과 출력
if (errors.length > 0) {
  console.error(`❌ lint:tokens 실패 (${errors.length}건)`);
  errors.forEach(e => console.error(`  ERROR: ${e}`));
  process.exit(1);
}
if (warnings.length > 0) {
  warnings.forEach(w => console.warn(`  WARN: ${w}`));
}
console.log('✅ lint:tokens 통과');
```

---

### 2.3 `lint:a11y` — 접근성 자동 검사

**목적**: Storybook 스토리를 대상으로 axe-core 기반 접근성 위반을 자동 탐지

**추천 도구**: [@storybook/addon-a11y](https://storybook.js.org/addons/@storybook/addon-a11y) + [axe-playwright](https://github.com/nicholasXor[storybook-testing-library)

```bash
npm install -D @storybook/addon-a11y axe-playwright @playwright/test

# package.json
"lint:a11y": "pnpm storybook:build && node scripts/a11y-audit.js"
```

**구현 방식**:

```javascript
// scripts/a11y-audit.js
const { chromium } = require('playwright');
const { injectAxe, checkA11y, getViolations } = require('axe-playwright');

async function main() {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  // Storybook의 stories.json에서 모든 스토리 목록 가져오기
  await page.goto('http://localhost:6006/stories.json');
  const stories = await page.evaluate(() => document.body.textContent);
  const storyList = JSON.parse(stories);

  const violations = [];

  for (const story of Object.values(storyList.stories)) {
    const url = `http://localhost:6006/iframe.html?id=${story.id}`;
    await page.goto(url);
    await injectAxe(page);

    try {
      const results = await getViolations(page);
      const criticalOrSerious = results.filter(v =>
        v.impact === 'critical' || v.impact === 'serious'
      );

      if (criticalOrSerious.length > 0) {
        violations.push({
          story: story.id,
          issues: criticalOrSerious.map(v => ({
            id: v.id,
            impact: v.impact,
            description: v.description,
            nodes: v.nodes.length,
          })),
        });
      }
    } catch (e) {
      console.warn(`⚠️ ${story.id}: 검사 실패 (${e.message})`);
    }
  }

  await browser.close();

  if (violations.length > 0) {
    console.error(`❌ lint:a11y 실패 — ${violations.length}개 스토리에서 위반 발견`);
    for (const v of violations) {
      console.error(`\n  ${v.story}:`);
      v.issues.forEach(i => console.error(`    [${i.impact}] ${i.id}: ${i.description} (${i.nodes}개 노드)`));
    }
    process.exit(1);
  }

  console.log('✅ lint:a11y 통과');
}

main();
```

---

### 2.4 `ui:impact` — 영향 분석

**목적**: 변경된 토큰이 어떤 컴포넌트/화면에 영향을 미치는지 자동 추적

**추천 도구**: TypeScript Compiler API 기반 자체 구현

```bash
# package.json
"ui:impact": "node scripts/ui-impact.js"
```

**구현 핵심**:

```javascript
// scripts/ui-impact.js (핵심 로직)
const ts = require('typescript');
const { execSync } = require('child_process');

// 1. 변경된 토큰 키 추출 (git diff)
const diff = execSync('git diff origin/main -- src/design-tokens/tokens.json').toString();
const changedTokens = parseChangedTokenKeys(diff);

if (changedTokens.length === 0) {
  console.log('✅ 토큰 변경 없음');
  process.exit(0);
}

// 2. 소스 파일에서 토큰 참조 검색
const componentDir = 'src/ui';
const screenDir = 'src/screens';

const affectedComponents = findReferences(componentDir, changedTokens);
const affectedScreens = findReferences(screenDir, changedTokens);

// 3. 리포트 생성 (Markdown)
const report = generateReport(changedTokens, affectedComponents, affectedScreens);
console.log(report);

// GitHub PR 코멘트로 게시
if (process.env.CI) {
  execSync(`gh pr comment $PR_NUMBER --body "${report.replace(/"/g, '\\"')}"`);
}

function findReferences(dir, tokenKeys) {
  const results = [];
  const files = getAllTsFiles(dir);

  for (const file of files) {
    const content = readFileSync(file, 'utf-8');
    const matched = tokenKeys.filter(key => {
      const cssVar = `--${key.replace(/\./g, '-')}`;  // color.text.primary → --color-text-primary
      const themeRef = `theme.${key}`;                  // theme.color.text.primary
      return content.includes(cssVar) || content.includes(themeRef);
    });

    if (matched.length > 0) {
      results.push({ file, tokens: matched });
    }
  }
  return results;
}
```

**한계**: 동적 토큰 조합(예: `` theme[`color.${role}`] ``)은 탐지 불가. 이 경우 PR의 `Risk.notes`에 수동 기재.

---

## 3. Claude Code Hook 설정

### 3.1 Hook 설치 위치

```
.claude/
├── hooks/
│   ├── pre-commit.js       ← 직접 값 사용 탐지
│   ├── pr-create.js        ← DoD 자동 검증 + 라벨 제안
│   └── pr-merge.js         ← 최종 DoD 재검증
└── config.json             ← Hook 설정
```

### 3.2 `pre-commit` — 직접 값 사용 탐지

```javascript
// .claude/hooks/pre-commit.js
// staged 파일에서 직접 색상값(#RGB, rgb()), 하드코딩 px 등을 탐지

const patterns = [
  { regex: /#[0-9a-fA-F]{3,8}\b/, message: '직접 색상값 사용 금지 — 토큰을 사용하세요' },
  { regex: /rgb\(|hsl\(/, message: '직접 색상함수 사용 금지 — 토큰을 사용하세요' },
  { regex: /:\s*\d+px(?!\s*\/\*)/, message: '하드코딩 px 사용 금지 — spacing 토큰을 사용하세요', except: /1px|0px/ },
  { regex: /box-shadow:\s*[^v]/, message: '직접 box-shadow 사용 금지 — shadow 토큰을 사용하세요' },
];
// 1px hairline, 0값은 예외
```

### 3.3 `pr-create` — DoD 자동 검증

```javascript
// .claude/hooks/pr-create.js
// PR 생성 시 자동으로 실행

// 1. 변경 파일 기반으로 PR 타입 추론
// 2. 해당 타입의 DoD 체크리스트에서 누락 항목 탐지
// 3. PR 라벨 자동 제안
// 4. Impact 섹션 초안 생성
// 5. 누락 시 경고 코멘트 (차단하지 않음)
```

### 3.4 `pr-merge` — 최종 게이트

```javascript
// .claude/hooks/pr-merge.js
// 머지 시도 시 자동으로 실행

// 1. DoD 체크리스트 최종 재검증
// 2. VRT 미승인 확인 → 차단
// 3. ui:exception 라벨 시 후속 이슈 자동 생성
// 4. api:breaking 시 FE 리뷰어 승인 확인 → 미승인이면 차단
```

---

## 4. 도입 우선순위 요약

| 우선순위 | 스크립트 | 난이도 | 의존성 |
|----------|----------|--------|--------|
| **P0** | `api:lint` (Spectral) | 낮음 | 없음 |
| **P0** | `api:diff` (oasdiff) | 낮음 | 없음 |
| **P0** | `api:generate` (springdoc 설정) | 낮음 | BE 빌드 |
| **P1** | `api:codegen` (openapi-typescript) | 낮음 | `api:generate` |
| **P1** | `lint:tokens` | 중간 | 토큰 구조 확정 |
| **P1** | `lint:a11y` | 중간 | Storybook 빌드 |
| **P2** | `ui:impact` | 중간 | `lint:tokens` |
| **P2** | `design:sync` | 높음 | Figma API 접근권한 |
| **P2** | `api:mock` (Prism) | 낮음 | `api:generate` |
| **P3** | `ws:lint` | 중간 | AsyncAPI 도입 |
| **P3** | `ws:codegen` | 중간 | AsyncAPI 도입 |
| **P3** | `vrt:run` (Chromatic) | 높음 | Storybook 전체 구축 |
| **P3** | Claude Code hooks | 중간 | 전체 스크립트 |
