# UI 변경 운영 규정 v2 (Design Tokens · Components · Screens)

## 0. 목적

UI 변경을 **PR 단위로 안전하게** 흘려보내기 위해 다음을 보장한다.

* **단일 PR만 봐도** "무엇이 바뀌었고, 어디에 영향이 있는지, 결과가 안전한지"를 리뷰어가 판단 가능
* 토큰/컴포넌트/화면 변경이 쌓여도 **드리프트(디자인-코드 불일치)**를 자동 감지
* "리뷰 병목"을 최소화하도록 **증거(시각/정적 검사)를 자동 생성**

---

## 1. 용어 정의

* **Design Tokens(토큰)**: 색/타이포/spacing/radius/shadow/motion 등 "의미 기반" 스타일 값.
* **Foundations(토큰 갤러리)**: 토큰을 **자동 렌더링**하여 시각적으로 보여주는 Storybook 스토리 세트.

  * 예: `Foundations/Colors`, `Foundations/Typography`, `Foundations/Spacing`, `Foundations/Motion`
* **Component(컴포넌트)**: 재사용 가능한 UI 단위(variants/state 포함).
* **Screen(화면)**: 라우트/페이지 단위. 컴포넌트 조합의 결과물.
* **Screen Story**: 실제 라우트에 연결되지 않아도, Storybook에서 화면을 재현하는 스토리.
* **Screen Skeleton Story**: 신규 화면을 위한 "레이아웃/조합"만 가진 최소 Screen Story(기능 구현/데이터 연동 없이 더미 데이터로 렌더링). 실제 Screen이 완성되면 정식 Screen Story로 교체하고, Skeleton Story는 **해당 PR에서 삭제**한다.
* **VRT(시각 회귀)**: 브라우저가 실제로 렌더링한 스냅샷을 baseline과 비교해 `Expected/Actual/Diff`를 생성하는 검사.
* **Deprecated Token**: 향후 삭제 예정으로 표시된 토큰. `tokens.json`에 `"deprecated": true`와 `"replacement"` 필드를 포함하며, 린트에서 사용 시 경고를 발생시킨다.

---

## 2. Source of Truth(원본) & 산출물 규칙

### 2.1 기본 레포 구조(운영 기본값)

레포 구조가 다르면, 이 섹션만 수정한다.

* 토큰 산출물 위치

  * `src/design-tokens/tokens.json`
  * `src/design-tokens/tokens.css`
  * `src/design-tokens/theme.ts`
* Storybook 스토리 위치

  * Foundations: `src/storybook/foundations/**.stories.tsx`
  * Components: `src/storybook/components/**.stories.tsx`
  * Screens: `src/storybook/screens/**.stories.tsx`
* UI 컴포넌트 코드 위치: `src/ui/**`
* 화면(라우트/페이지) 코드 위치: `src/screens/**`
* Storybook 설정: `.storybook/**`

### 2.2 네이밍 규칙(운영 기본값)

* 토큰 키 네이밍(semantic)

  * 색상: `color.{role}.{name}` 예) `color.text.primary`, `color.bg.surface`, `color.border.default`, `color.status.success`
  * 간격: `space.{n}` 예) `space.1`, `space.2`, `space.4`, `space.8`
  * 라운드: `radius.{xs|sm|md|lg|xl}`
  * 그림자: `shadow.{sm|md|lg|xl}`
  * 타이포: `type.{display|h1|h2|body|caption}`
  * **모션**: `motion.duration.{fast|normal|slow}`, `motion.easing.{ease-in|ease-out|ease-in-out|spring}`
  * **브레이크포인트**: `breakpoint.{sm|md|lg|xl|2xl}` (뷰포트 기준 분기점)
* CSS 변수 네이밍

  * `--color-text-primary`, `--space-4`, `--radius-md`, `--motion-duration-fast`, `--breakpoint-md` (토큰 키를 kebab-case로 변환)

### 2.3 직접 값 사용 금지 규칙(운영 기본값)

* 금지(코드/스타일)

  * 색상: `#RRGGBB`, `rgb()/hsl()` 직접 사용 금지
  * 길이: `px/rem/em` 직접 하드코딩 금지
  * 그림자: `box-shadow` 직접 하드코딩 금지
  * **모션**: `transition-duration`, `animation-duration`, `transition-timing-function` 직접 값 금지
* 허용 예외(이 문서에서 명시된 범위로만 허용)

  * 1px hairline: `1px` (border/outline에 한정)
  * 0 값: `0`
  * 레이아웃 계산용: `calc()`는 사용 가능하되 **토큰을 반드시 포함**해야 함(예: `calc(var(--space-4) * 2)`)
  * 미디어쿼리 내 브레이크포인트: 토큰 값을 직접 참조할 수 없는 경우 `tokens.ts`에서 export한 상수 사용

### 2.4 접근성(최소) 대비 기준(운영 기본값)

* 텍스트 대비(WCAG AA)

  * 일반 텍스트: **4.5:1 이상**
  * 큰 텍스트(18pt/24px 이상 또는 굵은 14pt/18.66px 이상): **3:1 이상**
* 비텍스트(UI 컴포넌트 경계/아이콘 등): **3:1 이상**
* **대비 검증 자동화**: `pnpm lint:tokens` 실행 시 `color.text.*` ↔ `color.bg.*` 쌍에 대해 WCAG AA 대비를 자동 검사한다. 위반 시 CI 실패.

### 2.5 원본(SoT) 원칙

* **디자인 원본(설계)**: Figma(Variables/Components)
* **코드 원본(실행/배포)**: Repository의 `tokens.*`, `src/ui/**`, `src/screens/**`
* 분쟁 시:

  * 런타임 동작/버그: 코드 기준
  * 토큰 의미/네이밍/variant 정의: 디자이너-개발자 합의 기준

### 2.6 토큰 산출물(Generated Artifacts)

토큰은 아래 파일들로 레포에 반영된다.

* `src/design-tokens/tokens.json` (열거/메타/모드/alias 포함) — 갤러리/검증/영향분석에 사용
* `src/design-tokens/tokens.css` (CSS variables) — 런타임 스타일 적용
* `src/design-tokens/theme.ts` (JS/TS theme 객체) — 애플리케이션/Storybook 공통 주입

**규칙(필수)**

* 위 3개 파일은 **수작업 편집 금지** (동기화 스크립트로만 변경)
* PR에는 토큰 변경의 원인을 반드시 적는다.

  * `origin: figma` (Figma Variables/Components 변경 반영)
  * `origin: code` (코드 정책/변환 로직 변경)
* `origin: figma`인 경우, PR 본문에 Figma 변경 요약(토큰 그룹/모드/alias 중심)을 3줄 이내로 적는다.

### 2.7 Figma↔코드 동기화 프로세스

**동기화 소스**: Figma Variables API(REST API v2)를 통해 직접 추출한다. Figma Tokens Studio 등 서드파티 플러그인에 의존하지 않는다.

**동기화 트리거 & 주체**:

| 트리거 | 주체 | 절차 |
|--------|------|------|
| Figma Variables 변경 후 수동 실행 | FE(또는 Design Engineer) | 로컬에서 `pnpm design:sync` 실행 → 변경사항 확인 → PR 생성 |
| 정기 동기화 (주 1회, 월요일) | CI(scheduled job) | CI가 `pnpm design:sync` 실행 → diff 발생 시 자동 PR 생성 → 리뷰 요청 |

**`pnpm design:sync` 동작 명세**:

1. Figma Variables API에서 현재 프로젝트의 모든 Variable Collection을 조회
2. Variable을 `tokens.json` 스키마로 변환 (모드별 값, alias 참조, 메타데이터 포함)
3. `tokens.json` → `tokens.css` 변환 (CSS custom properties 생성)
4. `tokens.json` → `theme.ts` 변환 (TypeScript theme 객체 생성)
5. 변환 결과를 기존 파일과 비교하여 diff 요약을 stdout에 출력

**환경 변수**: `FIGMA_FILE_KEY`, `FIGMA_ACCESS_TOKEN` (CI에서는 시크릿으로 관리)

---

## 3. 브랜치/PR 기본 원칙

### 3.1 PR은 "리뷰 가능한 최소 단위"

* 한 PR에는 가능한 한 **한 목적**(토큰 / 컴포넌트 / 화면 / 청소)을 담는다.
* 신규 화면을 위한 토큰 변경이지만 아직 화면 코드가 없다면, **Screen Skeleton Story**를 함께 포함해 VRT가 가능하도록 한다.

### 3.2 Additive-first(추가 우선) 전략

변경이 크면 다음 순서로 쪼갠다.

1. 토큰 **추가**(기존 유지)
2. 컴포넌트가 새 토큰 사용
3. 화면이 새 컴포넌트 사용
4. 구 토큰/구 변형 제거(청소 PR)

---

## 4. PR 타입 분류 & 라벨 규정

모든 PR은 아래 중 하나 라벨을 반드시 가진다.

| 라벨 | 의미 |
|------|------|
| `ui:tokens` | 토큰 변경(추가/수정/삭제/alias 변경/deprecation) |
| `ui:components` | 컴포넌트 구현/variants/state 변경 |
| `ui:screens` | 화면(라우트/페이지) 변경 |
| `ui:cleanup` | 구토큰/구변형 제거, 정리 |
| `ui:breaking` | 호환성 깨짐(삭제/rename/props 변경 등) |
| `ui:exception` | 예외 허용(9절 조건 충족 시에만 사용) |

---

## 5. PR 타입별 DoD(완료 조건)

### 5.1 공통 DoD(모든 UI PR)

* [ ] 변경 목적이 1~2문장으로 명확히 설명됨(왜 바꾸는지)
* [ ] PR 라벨이 정확히 부여됨: `ui:tokens | ui:components | ui:screens | ui:cleanup` (breaking이면 `ui:breaking` 추가)
* [ ] VRT 리포트 링크가 PR 본문에 포함됨(예외는 9절)
* [ ] `Impact` 섹션이 포함됨(아래 포맷 준수)

### 5.2 Impact 섹션 포맷(필수, 복붙용)

```md
## Impact
### Changed tokens
- (없으면 `- none`)

### Affected components
- (없으면 `- none`)

### Affected screens/routes
- (없으면 `- none`)

### Risk
- scope: wide|local
- breaking: yes|no
- notes:
```

### 5.3 리스크 레벨 기준(필수)

* **scope=wide(광역)**: typography scale / base spacing scale / 전역 text/bg/border 기본색 / radius·shadow 스케일 변경 / 모션 기본값 변경 / 브레이크포인트 변경
* **scope=local(국소)**: 특정 도메인/컴포넌트 전용 토큰 또는 제한된 그룹(`color.status.*`)만 변경
* **breaking=yes**: 삭제/rename/alias 대변경, props 삭제/rename/의미 변경

### 5.4 `ui:tokens` (디자인 토큰 PR)

**반드시 포함**

* [ ] `pnpm design:sync`로 생성된 `src/design-tokens/tokens.(json|css|ts)` 변경사항 커밋
* [ ] Foundations 갤러리에서 변경이 자동 반영됨

  * Foundations 스토리는 토큰 파일을 순회 렌더링하며, 목록 하드코딩 금지
* [ ] VRT 리포트에서 변경이 확인됨 (**모든 활성 모드에서**)

  * 최소: `Foundations/Colors`, `Foundations/Typography`, `Foundations/Spacing` 중 관련 항목이 `added/changed`로 나타남
  * **라이트/다크 모드 모두** VRT 스냅샷이 존재해야 함
* [ ] PR 본문에 `origin: figma|code` 명시
* [ ] `Impact` 섹션에 changed tokens 기재

**토큰 변경 유형별 추가 DoD(필수)**

* 값 변경(value change)

  * [ ] before/after 값이 `Changed tokens`에 명시됨
* 추가(add)

  * [ ] Foundations에 신규 토큰이 자동으로 나타남(added)
* **Deprecation(폐기 예고)**

  * [ ] `tokens.json`에 `"deprecated": true` 및 `"replacement": "대체토큰키"` 추가
  * [ ] `pnpm lint:tokens`가 deprecated 토큰 사용처에 대해 warning 출력(CI 실패는 아님)
  * [ ] PR 본문에 폐기 예정 일정을 명시 (예: "2 스프린트 후 삭제 예정, 추적 이슈: #123")
* 삭제/rename(remove/rename)

  * [ ] `ui:breaking` 라벨 + 마이그레이션 가이드
  * [ ] 삭제 대상이 **최소 1 스프린트 이상 deprecated 상태**였음을 확인 (긴급 삭제 시 9절 예외 절차 적용)
  * [ ] "대체 토큰 추가 → 단계적 제거" 또는 "전부 고치고 머지" 중 하나로 수행
* alias/참조 변경(alias change)

  * [ ] `pnpm lint:tokens`로 순환(alias cycle) 없음이 보장됨
  * [ ] `Impact`의 Risk.notes에 영향 범위를 명시(예: `may widen scope via alias`)

**신규 화면용 토큰인데 아직 사용 코드가 없다면(둘 중 1개 필수)**

* [ ] Foundations에 자동 반영(added)됨
* [ ] Screen Skeleton Story를 추가하여 신규 화면 시나리오를 VRT로 캡처 가능하게 함

### 5.5 `ui:components` (컴포넌트 PR)

**반드시 포함**

* [ ] 컴포넌트 구현 변경(variants/state 포함)
* [ ] 해당 컴포넌트의 Storybook 스토리 업데이트

  * variants/state가 늘거나 바뀌면 스토리도 반드시 동기화
* [ ] VRT 리포트에서 변경 사항 확인 가능(변경된 스토리만 diff, **라이트/다크 모드 모두**)
* [ ] 직접 값 사용 금지 규칙(2.3)을 위반하지 않음
* [ ] 접근성(최소) 준수(아래 체크리스트 모두 적용)

  * [ ] 키보드만으로 주요 인터랙션 가능(Tab 이동, Enter/Space 활성화)
  * [ ] 포커스 표시가 명확함(focus ring/outline 제거 금지)
  * [ ] `aria-label`/`aria-labelledby`/`aria-describedby` 등 라벨링이 적절함(아이콘 버튼, 입력 필드 등)
  * [ ] 역할(role)과 상태(aria-pressed, aria-expanded 등)가 실제 동작과 일치
  * [ ] 대화상자/드로어는 포커스 트랩 및 ESC 닫기 지원(해당 컴포넌트일 때)
  * [ ] disabled 상태가 시각/동작 모두 일관(클릭/키보드 차단)
  * [ ] 대비 기준(2.4)을 만족
* [ ] `pnpm lint:a11y` 통과 (CI 자동 검사, 6.1 참조)

**Breaking props 변경(삭제/rename/의미 변경)**

* [ ] `ui:breaking` 라벨
* [ ] 마이그레이션 가이드(before/after 한 줄 예시)

### 5.6 `ui:screens` (화면 PR)

**반드시 포함**

* [ ] 화면 코드(라우트/페이지)
* [ ] Screen Story 최소 1개 제공

  * 위치: `src/storybook/screens/**.stories.tsx`
  * 네이밍: `Screens/<RouteOrPageName>`
* [ ] 최소 상태 케이스 2개 제공(필수)

  * [ ] `loading`
  * [ ] `empty` 또는 `error` 중 1개
* [ ] VRT 리포트 제공 (**라이트/다크 모드 모두**)
* [ ] 직접 값 사용 금지 규칙(2.3)을 위반하지 않음
* [ ] **반응형 VRT**: 최소 2개 뷰포트(mobile: 375px, desktop: 1280px)에서 스냅샷 제공

### 5.7 `ui:cleanup` (정리 PR)

**반드시 포함**

* [ ] 제거/정리 대상의 사용처가 0개임을 증명

  * 방법은 아래 중 하나로 고정한다.

    * [ ] `pnpm ui:impact` 결과에서 Affected components/screens가 `none`
    * [ ] 또는 레포 검색 결과(명령/결과 로그)를 PR에 첨부
* [ ] VRT에서 변화가 의도된 변경임이 확인됨(또는 무변화)
* [ ] **Screen Skeleton Story 정리**: 실제 Screen Story로 교체된 Skeleton이 남아있지 않음을 확인

---

## 6. 자동화 — 로컬/CI 공통 규칙

아래 명령은 레포에 스크립트로 고정한다.

### 6.1 필수 스크립트

| 스크립트 | 설명 |
|----------|------|
| `pnpm design:sync` | Figma Variables API에서 토큰을 추출하여 `src/design-tokens/tokens.*`로 생성/갱신 (2.7 참조) |
| `pnpm lint:tokens` | 토큰 네이밍/중복/순환 alias/삭제·rename 규칙/deprecated 사용처 경고/**대비 검증(2.4)** 검사 |
| `pnpm lint:a11y` | **Storybook 스토리 기반 접근성 자동 검사** (axe-core). 위반 시 CI 실패 |
| `pnpm typecheck` | TypeScript 타입체크 |
| `pnpm lint` | eslint/stylelint 등 정적 규칙 검사 |
| `pnpm storybook:build` | 스토리북 빌드 |
| `pnpm vrt:run` | VRT 실행 (Chromatic, **모든 활성 모드 × 뷰포트 매트릭스**) |
| `pnpm ui:impact` | 토큰→컴포넌트→화면 영향 범위 리포트 생성 (6.5 참조) |

### 6.2 VRT 도구(운영 기본값)

* VRT는 **Storybook + Chromatic**만 사용한다.
* Screen VRT도 Screen Story를 Storybook에서 캡처하여 Chromatic으로 처리한다.

**모드/뷰포트 매트릭스(필수)**:

| 차원 | 값 | 적용 대상 |
|------|-----|-----------|
| 테마 모드 | `light`, `dark` | 모든 스토리 |
| 뷰포트 | `375px` (mobile), `1280px` (desktop) | Screen Stories만 (Components/Foundations는 desktop만) |

Chromatic 설정 예시 (`.storybook/preview.ts`에서 modes 설정):
```ts
// Storybook의 globalTypes 또는 Chromatic modes config로
// light/dark × mobile/desktop 매트릭스를 선언
```

### 6.3 토큰 린트 규칙(운영 기본값)

* 의미 기반 네이밍: `color.text.primary`, `color.bg.surface`, `space.4`, `radius.md`, `motion.duration.fast` 등
* 직접 값 사용 금지: 2.3 규칙 위반 시 CI 실패
* 삭제/rename는 breaking: `ui:breaking` 라벨 + 마이그레이션 없으면 CI 실패
* alias 순환 금지: cycle 발견 시 CI 실패
* 모드 일관성: 라이트/다크(또는 브랜드 스킨) 모드 간 누락 키가 있으면 CI 실패
* **대비 검증**: `color.text.*` ↔ `color.bg.*` 쌍의 WCAG AA 기준 미달 시 CI 실패
* **deprecated 경고**: deprecated 토큰을 참조하는 코드에 lint warning 출력 (CI 실패는 아님, 단 삭제 예정일 초과 시 CI 실패로 전환)

### 6.4 접근성 자동 검사 규칙(운영 기본값)

* **도구**: `@storybook/addon-a11y` (axe-core 기반)
* **검사 범위**: `pnpm storybook:build` 후 모든 스토리에 대해 axe-core 실행
* **CI 실패 조건**: critical 또는 serious 위반이 1건 이상 발생 시
* **허용 예외**: 의도적 예외는 스토리 파일에 `a11y: { disable: true }` 파라미터와 함께 사유 주석을 남긴다

### 6.5 `pnpm ui:impact` 동작 명세

**목적**: 토큰 변경이 어떤 컴포넌트/화면에 영향을 미치는지 자동 추적

**동작 방식**:

1. **입력**: Git diff에서 변경된 토큰 키 목록을 추출 (`tokens.json` diff 파싱)
2. **분석 방법**: AST 정적 분석 (TypeScript Compiler API)
   * `src/ui/**`와 `src/screens/**`의 모든 파일을 파싱
   * CSS variable 참조 (`var(--token-name)`) 및 theme 객체 참조 (`theme.color.text.primary`) 추적
   * alias를 재귀적으로 펼쳐서 간접 참조도 탐지
3. **출력 포맷**: Markdown (PR 코멘트로 게시)

```md
## ui:impact Report
### Changed Tokens (3)
| Token | Change Type |
|-------|-------------|
| `color.text.primary` | value changed |
| `color.bg.surface` | value changed |
| `space.6` | added |

### Affected Components (2)
- `src/ui/Button/Button.tsx` — uses `color.text.primary`
- `src/ui/Card/Card.tsx` — uses `color.bg.surface`

### Affected Screens (1)
- `src/screens/Dashboard/Dashboard.tsx` — uses `Card` (transitive)

### Unaffected
- 42 components, 12 screens — no references to changed tokens
```

4. **한계**: 동적으로 토큰 키를 조합하는 패턴(예: `theme[color + '.' + role]`)은 탐지하지 못한다. 이 경우 `Risk.notes`에 수동 기재한다.

### 6.6 VRT 리포트 요구사항

* PR 본문 또는 PR 코멘트에 VRT 리포트 링크를 남긴다.
* 리포트에는 최소 다음이 포함되어야 한다.

  * 변경된 스냅샷 목록(changed/added) — **모드별, 뷰포트별 분류 포함**
  * 각 항목의 `Expected / Actual / Diff`
  * 승인 상태(approved/needs changes)

---

## 7. CI 게이트(머지 조건)

PR은 아래 체크를 모두 통과해야 머지 가능하다.

### 7.1 CI 단계(운영 기본값)

1. `pnpm install --frozen-lockfile`
2. `pnpm typecheck`
3. `pnpm lint`
4. `pnpm lint:tokens` (라벨이 `ui:tokens`이거나 `src/design-tokens/tokens.*` 변경 시)
5. `pnpm lint:a11y`
6. `pnpm storybook:build`
7. `pnpm vrt:run`
8. `pnpm ui:impact` (PR 코멘트로 게시)

### 7.2 공통 체크

* [ ] 타입체크/린트 통과
* [ ] **접근성 린트 통과** (`pnpm lint:a11y` — critical/serious 위반 없음)
* [ ] Storybook 빌드 통과(스토리 누락/에러 없음)
* [ ] VRT 정책을 만족

### 7.3 VRT 정책(운영 기본값)

* `changed/added` 스냅샷이 존재하면 **승인(approve)** 전까지 머지 불가
* **모든 활성 모드(light/dark)의 스냅샷이 존재**해야 머지 가능
* 예외는 9절의 `ui:exception` 조건을 따른다.

### 7.4 PR 타입별 추가 체크

#### 7.4.1 `ui:tokens`

* [ ] `pnpm design:sync`로 산출물이 최신임
* [ ] `pnpm lint:tokens` 통과 (대비 검증 포함)
* [ ] Foundations 3종(Colors/Typography/Spacing)이 빌드에 포함됨
* [ ] VRT에 `Foundations/*` 변경이 **모든 모드에서** 반영됨

#### 7.4.2 `ui:components`

* [ ] 변경된 컴포넌트에 대응하는 스토리 파일이 존재
* [ ] variants/state 변경 시 스토리가 함께 변경됨
* [ ] `pnpm lint:a11y` 통과

#### 7.4.3 `ui:screens`

* [ ] Screen Story 1개 이상 존재
* [ ] `loading` + (`empty` 또는 `error`) 상태가 Screen Story에 포함
* [ ] **mobile + desktop 뷰포트 VRT 스냅샷 존재**

#### 7.4.4 `ui:cleanup`

* [ ] 사용처 0개 증거가 PR에 포함
* [ ] **Skeleton Story 잔존 여부 확인** (정식 Screen Story로 교체된 것만 삭제)

### 7.5 실패 메시지(운영 기본값)

CI 실패 시 PR 코멘트에 아래를 남긴다.

* 실패 단계(예: lint:tokens / lint:a11y / storybook:build / vrt:run)
* 실패 원인 요약(1~3줄)
* 수정 가이드(가능하면 자동 패치 제안)

---

## 8. 리뷰 정책 & PR 템플릿

### 8.1 리뷰어 승인 매트릭스

| 조건 | 최소 리뷰어 | 필수 승인자 |
|------|-------------|-------------|
| `scope=local`, `breaking=no` | FE 1명 | — |
| `scope=local`, `breaking=yes` | FE 1명 | — |
| `scope=wide`, `breaking=no` | FE 1명 + Designer 1명 | Designer |
| `scope=wide`, `breaking=yes` | FE Lead + Designer | FE Lead + Designer |
| `ui:tokens` (모든 경우) | FE 1명 + Designer 1명 | Designer (토큰 의미/네이밍 검증) |
| VRT diff 20개 초과 | 기존 조건 + FE Lead | FE Lead (광역 영향 확인) |

**VRT 승인 권한**: VRT diff의 "Approve" 버튼은 위 매트릭스에 해당하는 리뷰어만 클릭할 수 있다(Chromatic 팀 권한으로 제어).

### 8.2 공통 체크리스트(PR 본문 필수 기재)

* [ ] PR 타입: `ui:tokens | ui:components | ui:screens | ui:cleanup` (breaking이면 `ui:breaking` 추가)
* [ ] 변경 의도 1~2문장
* [ ] VRT 결과 링크
* [ ] Impact 섹션 포함(5.2 포맷)

### 8.3 PR 본문 예시(복붙용)

```md
## What
- 

## Why
- 

## Evidence
- VRT: <link>

## Impact
### Changed tokens
- none

### Affected components
- none

### Affected screens/routes
- none

### Risk
- scope: local
- breaking: no
- notes:

## Checklist
- [ ] ui:tokens | ui:components | ui:screens | ui:cleanup
- [ ] VRT approved (light + dark)
- [ ] a11y lint passed
```

---

## 9. 예외 처리(운영 현실 반영)

예외는 오직 아래 조건을 모두 만족할 때만 허용한다.

* [ ] PR 라벨에 `ui:exception` 포함
* [ ] 예외 사유를 2줄 이내로 작성
* [ ] 후속 PR 링크 또는 이슈 키를 반드시 포함
* [ ] 후속 PR에서 VRT/스토리/토큰 규칙을 정상화해야 한다.
* [ ] **후속 PR 기한**: 예외 PR 머지 후 **2 스프린트 이내**에 정상화 PR이 머지되어야 한다. 초과 시 Jira/GitHub 이슈에 자동 escalation 라벨 부여.

---

## 10. 토큰 Deprecation 생명주기

토큰 삭제는 반드시 아래 단계를 거친다.

### 10.1 단계별 절차

```
[Active] → [Deprecated] → [Removed]
```

| 단계 | 상태 | `tokens.json` 표시 | 린트 동작 | 최소 유지 기간 |
|------|------|---------------------|-----------|----------------|
| 1. Active | 정상 사용 | — | — | — |
| 2. Deprecated | 사용 가능하나 경고 | `"deprecated": true`, `"replacement": "대체키"`, `"deprecatedSince": "YYYY-MM-DD"` | warning (CI 통과) | **1 스프린트** |
| 3. Removed | 삭제 완료 | 키 제거 | 참조 시 CI 실패 | — |

### 10.2 Deprecation PR 규칙

* `ui:tokens` 라벨 사용 (breaking이 아님 — 아직 삭제가 아니므로)
* PR 본문에 폐기 사유, 대체 토큰, 삭제 예정 시점, 추적 이슈 번호를 기재
* `pnpm lint:tokens`가 deprecated 토큰 사용처 목록을 warning으로 출력

### 10.3 삭제 PR 규칙

* `ui:tokens` + `ui:breaking` + `ui:cleanup` 라벨
* deprecated 기간이 최소 1 스프린트 이상 경과했음을 확인
* 사용처가 0개임을 `pnpm ui:impact` 또는 레포 검색으로 증명
* 긴급 삭제(deprecated 기간 미준수)는 9절 예외 절차 적용

---

## 11. 책임/역할

| 역할 | 책임 범위 |
|------|-----------|
| **Designer** | 토큰 의미/네이밍/모드 정책, 컴포넌트 UX 규칙(variants 방향), VRT diff 중 시각 디자인 의도 승인 |
| **FE(또는 Design Engineer)** | 토큰 산출물/갤러리 자동 렌더/컴포넌트 구현/접근성 구현/테스트 및 VRT 운영, `design:sync` 실행 |
| **FE Lead** | `scope=wide` + `breaking=yes` PR 최종 승인, 광역 VRT diff 확인 |
| **Reviewer** | PR 증거(VRT/Impact/a11y)를 보고 "의도된 변화"인지 승인, 8.1 매트릭스에 따라 승인 |

---

## 12. 운영 시작 체크리스트(도입 순서)

1. `tokens.json + tokens.css + theme.ts` 산출물 고정(수작업 금지)
2. `pnpm design:sync` 스크립트 구현 및 Figma API 연동 확인
3. Foundations 3종(Colors/Typography/Spacing) + Motion 자동 렌더 구현
4. `pnpm lint:tokens` 구현 (네이밍/순환/모드일관성/**대비검증** 포함)
5. `pnpm lint:a11y` 구현 (axe-core 기반 Storybook 스토리 검사)
6. `pnpm ui:impact` 구현 (AST 정적 분석 기반 영향 추적)
7. Components 스토리 작성 규칙 도입(variants/state 변경 시 스토리 동반)
8. Screens용 Screen Story 규칙 도입(loading+empty/error 포함)
9. VRT 모드/뷰포트 매트릭스 설정 (light/dark × mobile/desktop)
10. CI에 Storybook build + lint:a11y + Chromatic VRT + ui:impact 게시 고정
11. 리뷰어 승인 매트릭스(8.1) 적용 및 Chromatic 팀 권한 설정
12. Claude Code 훅: DoD 미충족 시 PR 생성/머지 단계에서 차단 + 자동 수정 제안

---

## 부록 A. 변경 이력

| 버전 | 날짜 | 변경 요약 |
|------|------|-----------|
| v1 | — | 초안 |
| v2 | 2025-03-05 | 다크모드/멀티테마 VRT 정책 추가, 접근성 자동 검사(`lint:a11y`) 도입, `ui:impact` 동작 명세 추가, Figma↔코드 동기화 프로세스 구체화, Screen Skeleton Story 생명주기 관리, 토큰 Deprecation 생명주기(10절) 신설, 리뷰어 승인 매트릭스(8.1) 추가, 모션/브레이크포인트 토큰 추가, 반응형 VRT 뷰포트 매트릭스 도입 |
