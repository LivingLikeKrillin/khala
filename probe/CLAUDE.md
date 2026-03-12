# CLAUDE.md — Karax

> Karax는 프로덕트 팀의 개발 워크플로를 자동 검증하는 도구다.
> 칼라(Khala)의 맥락을 기반으로 PR 검증, 영향 분석, 규칙 집행을 수행한다.
> 스타크래프트 프로토스의 기술자 카락스에서 이름을 따왔다.

## 아키텍처

Karax는 **하이브리드 구조**다.

- `src/` — 코어 엔진. CI에서 `npx karax check`로 독립 실행 가능.
- `.claude/` — Claude Code 어댑터. hooks, agents, skills, rules로 구성. Claude Code 환경에서 코어 엔진을 실시간으로 활용.

코어 엔진이 모든 가치의 실체이고, `.claude/`는 그 엔진을 Claude Code에서 편하게 쓰게 해주는 레이어다.

## 기술 스택

- 런타임: Node.js (>=20)
- 언어: TypeScript (strict mode)
- 패키지 매니저: pnpm
- 테스트: vitest
- 빌드: tsup

## 현재 버전: v0.4

- **v0.1** — 플랫폼 인식 PR 범위 분석 (scope-analyzer + 3개 프로파일)
- **v0.2** — API 스펙 린트/diff (10개 룰) + PR 타입별 리뷰 체크리스트
- **v0.3** — MCP 서버 (Claude Code 네이티브 연동, 6개 도구)
- **v0.4** — 칼라 연동 (맥락 기반 리뷰 + 영향 분석)

각 버전 상세: `docs/karax-v{N}-scope.md`

## 로드맵

```
v0.1  PR 범위 분석 + 플랫폼 프로파일          ✅
v0.2  API 스펙 린트/diff + 리뷰 체크리스트     ✅
v0.3  MCP 서버 (Claude Code 연동)            ✅
v0.4  칼라 연동 — 맥락 기반 리뷰             ✅ 현재
v0.5+ UI 확장팩 (토큰/VRT/접근성) — 별도 플러그인
```

## 프로젝트 구조

```
karax/
├── src/                           ← 코어 엔진 (CI 독립 실행)
│   ├── core/                      ← 분석 오케스트레이션
│   │   ├── scope-analyzer.ts      ← PR 범위 + 응집 그룹 분석
│   │   ├── concern-drift.ts       ← 관심사 드리프트 감지
│   │   ├── api-analyzer.ts        ← API diff 해석
│   │   ├── api-linter.ts          ← API 린트 오케스트레이션
│   │   ├── review-checklist.ts    ← 리뷰 체크리스트 오케스트레이션
│   │   └── config-loader.ts       ← karax.config.ts 로더
│   ├── api/                       ← API 스펙 분석
│   │   ├── spec-linter.ts         ← 10개 룰 기반 린트
│   │   ├── spec-differ.ts         ← breaking change 감지
│   │   ├── openapi-parser.ts      ← OpenAPI 파서
│   │   ├── rules/                 ← 린트 룰 (nullable, naming 등)
│   │   ├── oasdiff-runner.ts      ← oasdiff 래퍼
│   │   └── spectral-runner.ts     ← spectral 래퍼
│   ├── review/                    ← 리뷰 체크리스트
│   │   ├── pr-type-detector.ts    ← PR 타입 추론
│   │   ├── checklist-generator.ts ← 체크리스트 생성
│   │   └── checklists/            ← 타입별 템플릿
│   ├── khala/                     ← 칼라 연동
│   │   ├── client.ts              ← 칼라 API 클라이언트
│   │   ├── context-enricher.ts    ← 규정/문서 맥락 보강
│   │   └── impact-analyzer.ts     ← 서비스 영향 분석
│   ├── profiles/                  ← 플랫폼 프로파일
│   │   ├── detector.ts            ← 프로파일 자동 감지
│   │   ├── spring-boot.ts
│   │   ├── nextjs.ts
│   │   └── react-spa.ts
│   ├── mcp/                       ← MCP 서버
│   │   ├── server.ts              ← 서버 진입점
│   │   ├── tools.ts               ← 6개 도구
│   │   ├── resources.ts           ← 3개 리소스
│   │   └── prompts.ts             ← 2개 프롬프트
│   ├── cli/                       ← CLI 진입점
│   │   ├── index.ts               ← npx karax check/api:lint/khala:*
│   │   ├── parse-args.ts          ← CLI 인자 파서
│   │   └── formatters.ts          ← 출력 포맷터 (markdown/json/brief)
│   └── utils/                     ← 공용 유틸
│       ├── logger.ts              ← 로깅 래퍼
│       ├── git.ts                 ← git 연동
│       └── glob-match.ts          ← 파일 글롭 매칭
├── .claude/                       ← Claude Code 어댑터
│   ├── settings.json              ← hooks 정의
│   ├── rules/                     ← 프롬프트 규칙
│   ├── agents/                    ← scope-guard, code-reviewer, test-writer
│   └── skills/                    ← check-scope, split-pr, state-matrix
├── scripts/                       ← hook/CI 공용 래퍼
├── .github/workflows/             ← CI 파이프라인
├── tests/                         ← 테스트 (13개 파일, 145개 케이스)
└── docs/                          ← 스코프 문서 + 규정 문서
```

## 코딩 규칙

### 필수
- TypeScript strict mode
- 모든 public 함수에 JSDoc 주석
- 에러 메시지는 한국어 우선, 영어 병기
  - 예: `"⚠️ 관심사 혼재 감지 (Mixed concerns detected)"`
- core/ 변경 시 테스트 필수
- 외부 도구(oasdiff, spectral 등)는 래퍼로 감싸서 호출

### 금지
- any 타입 금지 (unknown + 타입 가드)
- console.log 직접 사용 금지 (Logger 유틸)
- 하드코딩 파일 경로 금지 (config에서 읽기)

### 네이밍
- 파일: kebab-case (`scope-analyzer.ts`)
- 타입/인터페이스: PascalCase (`PlatformProfile`)
- 함수/변수: camelCase (`analyzeScope`)
- 상수: UPPER_SNAKE_CASE (`MAX_FILES_PER_PR`)

### 커밋
```
feat: 새 기능
fix: 버그 수정
refactor: 리팩터링
docs: 문서
test: 테스트
chore: 빌드/설정
```

## 핵심 설계 원칙

1. **파일 수가 아니라 논리적 응집도로 판단한다** — 같은 7개 파일이라도 Spring Boot에서는 정상이고 Next.js에서는 비정상일 수 있다.
2. **정상일 때는 아무 말도 하지 않는다** — 노이즈는 신뢰를 죽인다.
3. **경고할 때는 분할 방법까지 제안한다** — "크다"만 말하면 쓸모없다.
4. **코드로 강제할 수 있는 건 hook으로, 나머지만 프롬프트로** — 3계층 원칙.
5. **칼라는 선택적이다** — 없어도 모든 기능이 동작하고, 있으면 결과가 풍부해진다.

## 관련 규정 문서

Karax가 검증하는 규칙의 근거:
- `docs/guidelines/product-change-safety-net-framework.md` — 전체 프레임워크
- `docs/guidelines/state-matrix-guidelines.md` — 규정 ①
- `docs/guidelines/api-contract-guidelines.md` — 규정 ②
- `docs/guidelines/ui-change-guidelines-v2.md` — 규정 ③

코드에서 규칙을 구현할 때, 해당 규정의 절 번호를 주석으로 남긴다.
```typescript
// 규정 ② 2.3.1: nullable 정확히 표시
function checkNullableFields(schema: OpenAPISchema): LintResult[] {
```
