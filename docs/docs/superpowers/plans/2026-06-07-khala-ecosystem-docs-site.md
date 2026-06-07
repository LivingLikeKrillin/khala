# Khala 생태계 docs 사이트 (하위 프로젝트 A) — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Astro Starlight 기반 이중언어(EN 루트 / ko) 통합 docs 사이트를 빌드·배포해, Khala 생태계(Nexus·Archon·Probe·specledger·mutqa)의 목적·철학·사용법을 일관 템플릿으로 게시한다.

**Architecture:** 단일 Astro Starlight 정적 사이트. EN을 루트 로케일, ko를 `/ko`로 두는 i18n. 콘텐츠는 MD/MDX. 랜딩(splash)+철학+생태계가 내러티브 척추, 5개 도구 페이지가 동일 템플릿(개요→개념→Quickstart→How-to→레퍼런스). 깊은 레퍼런스의 진실원천은 각 도구 repo이고 사이트는 큐레이션·링크. Cloudflare Pages 배포.

**Tech Stack:** Astro, @astrojs/starlight, Pagefind(내장 검색), Mermaid(다이어그램), Node ≥20, pnpm 또는 npm, Cloudflare Pages.

**Spec:** `docs/superpowers/specs/2026-06-07-khala-ecosystem-docs-site-design.md`

**작업 디렉토리(repo 루트):** `C:\Users\Eisen\Desktop\Labs\[projects] khala-ecosystem\khala-docs` (git 초기화됨, spec 커밋 `5dd7049`)

**완료 게이트(spec §8/§11):** ko 최소 커버리지 = 랜딩·철학·도구별 개요 5개가 EN/ko 둘 다 존재. 나머지는 EN 선행 허용.

---

## 콘텐츠 소스 매핑 (executor가 사실을 캐오는 출처)

각 도구 페이지는 아래 repo의 README/docs/spec에서 사실을 가져온다. **새로 발명하지 말 것** — 큐레이션·요약·링크. 경로는 Labs 루트 기준.

| 도구 | 1차 소스 | 핵심 한 줄(정체성) |
|---|---|---|
| **Nexus** (구 Khala) | `[projects] khala-ecosystem/khala/README.md`, `khala/docs/` | 근거 기반 지식 검색(RAG+GraphRAG). 출처 없는 주장 차단. |
| **Archon** | khala repo 브랜치 `spec/domain-invariant-governance`; `khala/docs/superpowers/{specs,plans}/2026-06-06-*`; **Python 패키지 `khala/khala/claims/`** (루트 `khala/claims.yaml`은 seed 파일이지 패키지 아님) | 도메인 진실(값·불변식·권한)을 주재하는 권위 창구. "기계가 거짓말 안 함". |
| **Probe** | `[projects] khala-ecosystem/probe/README.md`, `probe/docs/` | 플랫폼 인지 PR 분석 + API 계약 검증 + 트러블슈팅 그라운딩. |
| **specledger** | `[claude] mcp-tools/specledger/README.md`, `specledger/BACKLOG.md` | AI 생성 ADR/Spec의 책임 리뷰 게이트(critique→issue-disposition→sign-off). 반(反)거수기. |
| **mutqa** | `[claude] skills/mutqa/SKILL.md`, `mutqa/docs/dogfood-*` | 뮤테이션 구동 테스트 품질 하네스. 어드바이저리가 놓친 행위검증 공백을 결정론적으로 강제. |

**철학/생태계 소스:** `[projects] khala-ecosystem` 밖의 `roadmap.md` "에코시스템 구조" 절(캘리브레이션 맵 표·두 실패 모드·핵심 관계). executor는 이 plan에 인라인된 표/문구(아래 Task 6·9)를 사용.

---

## File Structure

```
khala-docs/
  package.json                      — deps, scripts (dev/build/preview/check)
  astro.config.mjs                  — Starlight 설정: 제목·로고·i18n(en root/ko)·sidebar·mermaid
  tsconfig.json
  .gitignore                        — (이미 존재: node_modules/ dist/ .astro/)
  src/
    content.config.ts               — Starlight docs 컬렉션 로더+스키마
    assets/
      logo.png                      — khala/logo.png 재사용(생태계 로고)
    styles/
      custom.css                    — 최소 브랜드 토큰(선택)
    content/docs/                    — EN (루트 로케일)
      index.mdx                      — 랜딩(splash): hero + 두 실패 모드 + 5도구 카드 + CTA
      philosophy.md                  — 철학(척추): 두 실패 모드·캘리브레이션·맵 표
      start.md                       — 시작하기: 의도별 라우팅 + 전제조건
      ecosystem.md                   — 연결 구조 + Mermaid 다이어그램 + 캘리브레이션 맵
      contributing.md                — 경량 placeholder
      tools/
        nexus.md
        archon.md
        probe.md
        specledger.md
        mutqa.md
    content/docs/ko/                 — 한국어 로케일(미러)
      index.mdx                      — (필수)
      philosophy.md                  — (필수)
      tools/
        nexus.md  archon.md  probe.md  specledger.md  mutqa.md   — (개요 섹션 필수)
      (start/ecosystem/contributing ko는 EN 선행 허용 — 완료 게이트 아님)
  public/
    favicon.svg
```

**경계:** 각 콘텐츠 파일 = 한 페이지 한 책임. 설정(astro.config) = 사이트 구조·네비의 단일 진실원천. 콘텐츠와 설정 분리.

---

## Chunk 1: 스캐폴드 + 설정 + 배포 골격

목표: `npm run build`가 통과하고 EN/ko 빈 골격이 렌더되는 배포 가능한 Starlight 사이트.

### Task 1: Astro Starlight 스캐폴드

**Files:**
- Create: `package.json`, `astro.config.mjs`, `tsconfig.json`, `src/content.config.ts`, `public/favicon.svg`

- [ ] **Step 1: Node ≥20 확인**

Run: `node -v`
Expected: `v20.x` 이상. 아니면 중단·보고.

- [ ] **Step 2: `package.json` 작성**

```json
{
  "name": "khala-docs",
  "type": "module",
  "version": "0.0.1",
  "private": true,
  "scripts": {
    "dev": "astro dev",
    "build": "astro build",
    "preview": "astro preview",
    "check": "astro check"
  },
  "dependencies": {
    "astro": "^5.0.0",
    "@astrojs/starlight": "^0.30.0",
    "sharp": "^0.33.5"
  },
  "devDependencies": {
    "@astrojs/check": "^0.9.4",
    "typescript": "^5.6.0"
  }
}
```
(`check` 스크립트가 `@astrojs/check`+`typescript`를 요구하므로 devDependencies에 포함. Mermaid·linkinator 의존은 해당 청크에서 추가.)

- [ ] **Step 3: `tsconfig.json` 작성**

```json
{
  "extends": "astro/tsconfigs/strict",
  "include": [".astro/types.d.ts", "**/*"],
  "exclude": ["dist"]
}
```

- [ ] **Step 4: `src/content.config.ts` 작성**

```ts
import { defineCollection } from 'astro:content';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

export const collections = {
  docs: defineCollection({ loader: docsLoader(), schema: docsSchema() }),
};
```

- [ ] **Step 5: `public/favicon.svg` 작성** (임시 — 단색 마름모, 추후 로고로 교체)

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><path d="M16 2l14 14-14 14L2 16z" fill="#4361ee"/></svg>
```

- [ ] **Step 6: 의존성 설치**

Run: `npm install`
Expected: 에러 없이 완료, `node_modules/` 생성.

- [ ] **Step 7: 커밋**

```bash
git add package.json package-lock.json tsconfig.json src/content.config.ts public/favicon.svg
git commit -m "feat: scaffold Astro Starlight project"
```

### Task 2: i18n + sidebar 설정 (사이트 구조의 단일 진실원천)

**Files:**
- Create: `astro.config.mjs`
- Create: `src/assets/logo.png` (복사)

- [ ] **Step 1: assets 디렉토리 생성 + 로고 복사**

Run (Bash 툴): `mkdir -p src/assets && cp "../khala/logo.png" "src/assets/logo.png"`
(PowerShell이면: `New-Item -ItemType Directory -Force src/assets; Copy-Item ../khala/logo.png src/assets/logo.png`)
Expected: `src/assets/logo.png` 존재. (소스 로고 없으면 favicon만 쓰고 `logo` 설정 생략 후 보고.)

- [ ] **Step 2: `astro.config.mjs` 작성**

```js
// @ts-check
import { defineConfig } from 'astro/config';
import starlight from '@astrojs/starlight';

export default defineConfig({
  site: 'https://khala-docs.pages.dev', // Cloudflare Pages 기본 도메인(프로젝트명 khala-docs 기준, 추후 커스텀 교체)
  integrations: [
    starlight({
      title: 'Khala',
      tagline: 'AI 시대의 캘리브레이션 — 도구들의 연합',
      logo: { src: './src/assets/logo.png', alt: 'Khala' },
      defaultLocale: 'root',
      locales: {
        root: { label: 'English', lang: 'en' },
        ko: { label: '한국어', lang: 'ko' },
      },
      social: [
        { icon: 'github', label: 'GitHub', href: 'https://github.com/LivingLikeKrillin' },
      ],
      sidebar: [
        {
          label: 'Overview',
          translations: { ko: '개요' },
          items: [
            { label: 'What is Khala?', slug: 'index' },
            { label: 'Philosophy', translations: { ko: '철학' }, slug: 'philosophy' },
            { label: 'Getting Started', translations: { ko: '시작하기' }, slug: 'start' },
            { label: 'Ecosystem', translations: { ko: '생태계' }, slug: 'ecosystem' },
          ],
        },
        {
          label: 'Tools',
          translations: { ko: '도구' },
          items: [
            { label: 'Nexus', slug: 'tools/nexus' },
            { label: 'Archon', slug: 'tools/archon' },
            { label: 'Probe', slug: 'tools/probe' },
            { label: 'specledger', slug: 'tools/specledger' },
            { label: 'mutqa', slug: 'tools/mutqa' },
          ],
        },
        {
          label: 'Contributing',
          translations: { ko: '기여' },
          items: [{ label: 'Contributing', slug: 'contributing' }],
        },
      ],
    }),
  ],
});
```

참고: sidebar `slug: 'index'`는 루트 랜딩을 가리킨다. ko 페이지는 동일 slug로 자동 매핑된다(`src/content/docs/ko/...`).

- [ ] **Step 3: 커밋**

```bash
git add astro.config.mjs src/assets/logo.png
git commit -m "feat: configure i18n (en root, ko) and sidebar"
```

### Task 3: 최소 placeholder 페이지로 빌드 통과 검증

**Files:**
- Create: `src/content/docs/index.mdx`, `philosophy.md`, `start.md`, `ecosystem.md`, `contributing.md`, `tools/{nexus,archon,probe,specledger,mutqa}.md`
- Create: `src/content/docs/ko/index.mdx`, `ko/philosophy.md`, `ko/tools/{...}.md`

- [ ] **Step 1: EN placeholder 페이지 작성** (각 파일 frontmatter + 한 줄 본문)

예) `src/content/docs/philosophy.md`:
```md
---
title: Philosophy
description: The calibration thesis behind Khala.
---

_(content coming in Chunk 2)_
```
나머지 EN 페이지도 동일 패턴(title/description + placeholder). 랜딩 `index.mdx`:
```mdx
---
title: Khala
description: An alliance of tools that calibrates the AI era.
template: splash
---

_(landing coming in Chunk 2)_
```

- [ ] **Step 2: ko 필수 placeholder 작성** (index, philosophy, tools/5개)

예) `src/content/docs/ko/philosophy.md` — title을 한국어로, 나머지 동일.

- [ ] **Step 3: 빌드**

Run: `npm run build`
Expected: PASS. `dist/` 생성. EN/ko 라우트 모두 생성됨.

- [ ] **Step 4: 라우트 산출 자동 검증 (게이트)**

Run (Bash): `test -f dist/index.html && test -f dist/ko/index.html && echo OK`
Expected: `OK`. (EN 루트 + ko 라우트가 실제로 생성됐는지 자동 확인 — 이게 통과 게이트.)
*선택(육안):* `npm run dev` → `http://localhost:4321/`·`/ko/` 언어 토글 확인 후 종료. (subagent 실행 시 이 육안 단계는 owner=사용자, 차단·위장 금지.)

- [ ] **Step 5: 커밋**

```bash
git add src/content/docs
git commit -m "feat: add bilingual page skeleton, build green"
```

### Task 4: Cloudflare Pages 배포 골격

**Files:**
- Create: `README.md` (repo 루트 — 빌드·배포 방법 명시)

- [ ] **Step 1: GitHub 리모트 생성·푸시**

Run:
```bash
gh repo create khala-docs --private --source=. --remote=origin --push
```
Expected: private repo 생성, master 푸시. (gh 미인증 시 사용자에게 `! gh auth login` 안내 후 중단.)

- [ ] **Step 2: `README.md` 작성** (빌드/배포 절차)

```md
# Khala — Ecosystem Docs

Astro Starlight site. EN (root) + ko.

## Dev
\`\`\`bash
npm install
npm run dev      # http://localhost:4321
npm run build    # → dist/
\`\`\`

## Deploy (Cloudflare Pages)
Connect this repo in the Cloudflare Pages dashboard:
- Framework preset: Astro
- Build command: \`npm run build\`
- Build output directory: \`dist\`
```

- [ ] **Step 3: Cloudflare Pages 연결** (사용자 영역)

Cloudflare Pages 대시보드에서 repo 연결(빌드 명령 `npm run build`, 출력 `dist`). **owner = 사용자** (대시보드 인증 필요). executor는 README에 절차만 남기고 보고.

- [ ] **Step 4: 커밋·푸시**

```bash
git add README.md
git commit -m "docs: add build/deploy README for Cloudflare Pages"
git push
```

---

## Chunk 2: 정체성 + 내러티브 척추 (랜딩 · 철학 · 생태계)

목표: 사이트의 "왜"가 완성. EN 전부 + 랜딩·철학 ko 필수.

### Task 5: 랜딩 페이지 (splash + hero + 두 실패 모드 + 5도구 카드)

**Files:**
- Modify: `src/content/docs/index.mdx`
- Reference skill: @frontend-design:frontend-design (hero·카드 폴리시)

- [ ] **Step 1: EN 랜딩 작성** — splash 템플릿 hero + CardGrid

```mdx
---
title: Khala
description: An alliance of tools that calibrates the AI era.
template: splash
hero:
  tagline: Two failure modes of the AI era — the machine lies, and the human stops judging. Khala answers both with deterministic grounding, not advice.
  image:
    file: ../../assets/logo.png
  actions:
    - text: Get Started
      link: /start/
      icon: right-arrow
    - text: Philosophy
      link: /philosophy/
      variant: minimal
---

import { Card, CardGrid, LinkCard } from '@astrojs/starlight/components';

## The two failure modes

<CardGrid>
  <Card title="The machine lies" icon="warning">
    Stale or wrong, asserted with confidence. **Archon** + **Nexus** defend by grounding answers in verifiable sources — never asserting soft answers.
  </Card>
  <Card title="The human stops judging" icon="approve-check">
    AI output rubber-stamped without reading. **specledger** defends by making accountable review a gate before code is written.
  </Card>
</CardGrid>

## The tools

<CardGrid>
  <LinkCard title="Nexus" href="/tools/nexus/" description="Grounded knowledge — RAG + GraphRAG over your docs & telemetry." />
  <LinkCard title="Archon" href="/tools/archon/" description="Domain truth governance — values, invariants, authority, calibrated." />
  <LinkCard title="Probe" href="/tools/probe/" description="Grounded code review — PR scope, API contracts, troubleshooting." />
  <LinkCard title="specledger" href="/tools/specledger/" description="Decision accountability — anti-rubber-stamp spec/ADR gate." />
  <LinkCard title="mutqa" href="/tools/mutqa/" description="Test quality — mutation-driven, catches what advisory review misses." />
</CardGrid>
```
(failure-mode `Card`의 `warning`·`approve-check` 아이콘은 Starlight 내장 확인됨. 도구 카드는 `LinkCard`(제목=링크)로 내비게이션 보장 — raw `<a>` 회피. 만약 아이콘명 미존재로 빌드 에러 시 가까운 내장 아이콘으로 교체.)

- [ ] **Step 2: ko 랜딩 작성** — 동일 구조, 한국어. tagline = "AI 시대의 두 실패 모드 — 기계가 거짓말하고, 사람이 판단을 포기한다. Khala는 조언이 아니라 결정론적 그라운딩으로 둘 다에 답한다." 링크는 `/ko/...`.

- [ ] **Step 3: 빌드 + 검증**

Run: `npm run build`
Expected: PASS, **unknown-icon 에러 없음**(아이콘 오타 시 Starlight가 빌드 실패시킴 — 이게 명시 체크). dist에 `index.html`·`ko/index.html` 존재. (선택 육안: dev로 hero·LinkCard 내비게이션·언어 토글.)

- [ ] **Step 4: 커밋**

```bash
git add src/content/docs/index.mdx src/content/docs/ko/index.mdx
git commit -m "feat: landing page (EN+ko) with two failure modes and tool cards"
```

### Task 6: 철학 페이지 (척추) + 캘리브레이션 맵 표

**Files:**
- Modify: `src/content/docs/philosophy.md`, `src/content/docs/ko/philosophy.md`

- [ ] **Step 1: EN 철학 작성** — 아래 내러티브 + 표를 본문으로

본문 골자(spec §6):
1. Khala(the link)가 AI 시대 *miscalibration*에 맞서 도구들을 묶는다.
2. 실패① 기계가 거짓말 → Archon(+Nexus 그라운딩).
3. 실패② 사람이 판단 포기(거수기) → specledger.
4. 사각지대: AI 생성 테스트가 그럴듯하나 행위검증 0 → mutqa(결정론적 강제).
5. 통합 명제 **Calibration**: 정답 보장이 아니라 soft/낡은 답을 단정하지 않음. 어드바이저리가 포화된 곳에 결정론적 그라운딩/강제.

캘리브레이션 맵 표(인라인, EN):
```md
| Tool | Identity | Calibrates | Audience | Khala relation | Timing |
|---|---|---|---|---|---|
| Nexus | Shared grounded-knowledge base | Grounded knowledge (no source → blocked) | Everyone | The body | Always |
| Archon | Authority window over domain truth | The machine's truthfulness | Planners + devs + agents | Producer + read window | Always |
| specledger | Human-judgment accountability ledger | The human's judgment | Decision-makers | Producer (approved specs) | Decision gate (pre-code) |
| Probe | Grounding agent | Engineering output (review/troubleshoot) | Engineers + AI | Consumer | Post-code + runtime |
| mutqa | Mutation-driven test-quality harness | The claim "these tests verify behavior" | Devs writing/reviewing tests | Independent (deterministic) | Pre-commit (gate, roadmap M3) |
```
핵심 관계 문단: 생산 도구는 서로 직접 호출 안 하고 **오직 Khala를 통해** 연결. Probe=소비자, Archon=사람·에이전트가 도메인 진실을 물으러 오는 단일 권위 창구.

- [ ] **Step 2: ko 철학 작성** — 동일 내용 한국어, 표 헤더/셀 번역.

- [ ] **Step 3: 빌드 + 링크 확인**

Run: `npm run build` → PASS. EN/ko 렌더·표·내부 링크 확인.

- [ ] **Step 4: 커밋**

```bash
git add src/content/docs/philosophy.md src/content/docs/ko/philosophy.md
git commit -m "feat: philosophy page (EN+ko) — calibration thesis + map table"
```

### Task 7: 생태계 페이지 + Mermaid 다이어그램

**Files:**
- Modify: `src/content/docs/ecosystem.md`
- Modify: `astro.config.mjs` (Mermaid 지원 추가)
- Add dep: `rehype-mermaid`

**중요(리뷰 반영):** `img-svg`/`inline-svg` 전략은 **빌드 시 Playwright+Chromium**을 요구하며 Cloudflare Pages 빌드 이미지엔 없으므로 **로컬 빌드는 통과해도 배포가 깨진다**. → **브라우저 불필요한 `pre-mermaid`(서버는 `<pre class="mermaid">`만 출력) + client-side(CDN) 렌더링**을 쓴다. 로컬 `mermaid` 번들 의존도 불필요(CDN import).

- [ ] **Step 1: Mermaid 통합 추가 (browser-free, client-side 렌더)**

`package.json` deps에 `"rehype-mermaid": "^3.0.0"` 추가 후 `npm install`. `astro.config.mjs` 수정 — (a) markdown rehype `pre-mermaid`, (b) Starlight `head`에 client-side mermaid 초기화(CDN):
```js
import rehypeMermaid from 'rehype-mermaid';

export default defineConfig({
  site: 'https://khala-docs.pages.dev',
  markdown: {
    rehypePlugins: [[rehypeMermaid, { strategy: 'pre-mermaid' }]],
  },
  integrations: [
    starlight({
      // ...기존 title/logo/i18n/sidebar...
      head: [
        {
          tag: 'script',
          attrs: { type: 'module' },
          content:
            "import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs'; mermaid.initialize({ startOnLoad: true });",
        },
      ],
    }),
  ],
});
```
`pre-mermaid`는 ```mermaid 펜스를 `<pre class="mermaid">…</pre>`로만 변환(브라우저 불필요 → CF 빌드 안전). 실제 렌더는 head의 client-side 스크립트가 수행.
(폴백: 그래도 문제 시 mermaid 제거하고 다이어그램을 정적 SVG/ASCII로 — 다이어그램은 nice-to-have, 빌드 차단 금지.)

- [ ] **Step 2: EN 생태계 페이지 작성** — 연결 구조 설명 + 다이어그램 + 캘리브레이션 맵 재게재(또는 철학으로 링크)

```md
---
title: Ecosystem
description: How the tools connect — only through Khala.
---

The three producer tools never call each other directly. They connect **only through Khala**.

\`\`\`mermaid
graph TD
  subgraph Khala["Khala (the link)"]
    Nexus[Nexus<br/>grounded knowledge]
  end
  Archon -->|claims / values| Nexus
  specledger -->|approved specs| Nexus
  Probe -->|queries| Nexus
  Dev[Developer] --> Archon
  Agent[Agent / Probe] --> Archon
\`\`\`

- **Archon** is the single authority window: people and agents come to it to ask for domain truth.
- **Probe** is one client of that window, alongside developers.
- **specledger** publishes approved specs into Khala; it is not the source of truth (frontmatter is).
```

- [ ] **Step 3: 빌드 + 산출 검증**

Run: `npm run build`
Expected: PASS (Playwright 불필요). `dist/ecosystem/index.html`에 `<pre class="mermaid">` 존재(`grep -q 'class="mermaid"' dist/ecosystem/index.html && echo OK` → `OK`). *client-side 시각 렌더 확인은 dev/배포본에서 owner=사용자(빌드로는 검증 불가).*

- [ ] **Step 4: 커밋**

```bash
git add src/content/docs/ecosystem.md astro.config.mjs package.json package-lock.json
git commit -m "feat: ecosystem page with connection diagram"
```

---

## Chunk 3: 도구 페이지(5) + 시작하기 + 기여

목표: 5개 도구가 동일 템플릿으로 게시, 의도별 온보딩 동작. EN 전부 + 도구 개요 ko 필수.

### Task 8: 도구 페이지 템플릿 확정 + Nexus(완전 예시)

**Files:**
- Modify: `src/content/docs/tools/nexus.md`, `src/content/docs/ko/tools/nexus.md`

**템플릿(모든 도구 공통):** 섹션 순서 = `## Overview` → `## Core concepts` → `## Quickstart` → `## How-to` → `## Reference`. 각 페이지 하단에 `:::note 마지막 검증일: YYYY-MM-DD` 표기.

- [ ] **Step 1: Nexus EN 페이지 작성** (소스: `khala/README.md`)

골자:
- Overview: 근거 기반 지식 검색(RAG+GraphRAG). 출처 없는 주장 차단, confidence + 출처/trace 포인터 반환. *Nexus 개명 콜아웃 포함*:
  ```md
  :::caution[Naming]
  Nexus is the knowledge-base component, formerly called "Khala". The ecosystem now carries the name **Khala**; the code/repo rename lands in sub-project B. Install paths below still reference the current `khala` repo.
  :::
  ```
- Core concepts: BM25(한국어 형태소)+Vector(768d)+Graph(2-hop), grounded answer, confidence.
- Quickstart(중간 깊이): repo clone, `docker compose up`(Postgres+services), 기동 확인. (정확 명령은 `khala/README.md`·compose 파일에서 확인해 전사.)
- How-to(2~3): 예) "문서 인덱싱", "질의 날리기". (README에서.)
- Reference: `khala/README.md`·`khala/docs/`로 링크.

- [ ] **Step 2: Nexus ko 페이지 작성** — 최소 **Overview 섹션 필수**(완료 게이트). 나머지 섹션은 EN 링크 또는 ko 작성(여유 시).

- [ ] **Step 3: 빌드 + 링크 확인**

Run: `npm run build` → PASS. 콜아웃·섹션·repo 링크 확인.

- [ ] **Step 4: 커밋**

```bash
git add src/content/docs/tools/nexus.md src/content/docs/ko/tools/nexus.md
git commit -m "feat: Nexus tool page (EN full + ko overview), template established"
```

### Task 9: 나머지 도구 페이지 4개 (Archon · Probe · specledger · mutqa)

**Files:**
- Modify: `src/content/docs/tools/{archon,probe,specledger,mutqa}.md`
- Modify: `src/content/docs/ko/tools/{archon,probe,specledger,mutqa}.md` (Overview 필수)

각 도구를 Task 8 템플릿으로. 소스·핵심 사실:

- [ ] **Step 1: Archon** (소스: khala `spec/domain-invariant-governance`, `khala/claims/`)
  - Overview: 도메인 진실(값·불변식·권한) 권위 창구. "신뢰성=캘리브레이션"(soft/낡은 답 단정 안 함). 기획자가 자연어로 묻고 코드앵커로 답.
  - Concepts: claim 모델, 코드값 resolver, 권한 게이트 추출(tree-sitter), 등급 여집합 도출.
  - Quickstart: `khala claim-seed claims.yaml` → `khala claim-value <용어>`; MCP `archon_claim_value`. (정확 CLI는 소스에서 전사.)
  - How-to: "코드 상수 질의", "권한 등급 차단 도출(grade-authority)".
  - Reference: khala docs/specs 링크 + 콜아웃(Archon은 현재 khala repo 브랜치).

- [ ] **Step 2: Probe** (소스: `probe/README.md` **전문** + `probe/docs/` + `probe/package.json`의 `bin`/`scripts`)
  - Overview: "Platform-Aware PR Analyzer + API Contract Validator". 코드리뷰의 세 반복문제 해결 — ①PR 범위 적절성(플랫폼별 응집도로 판단, 파일 수 아님), ②API 변경 하위호환(nullable 누락·에러 응답 불일치·breaking change), ③조직 가이드라인 대조. Khala 창구의 소비자.
  - Concepts: 플랫폼별 응집도 기반 범위, API spec lint/diff, 리뷰 체크리스트 자동 생성. (정확 용어는 README에서.)
  - Quickstart(중간): `probe/README.md`의 실제 설치(pnpm/npm)·**MCP 서버 등록 블록(`.mcp.json` 또는 실행 커맨드)**·첫 PR 분석 호출을 **그대로 전사**. (TS/Node≥20 MCP 서버 — 정확한 등록 JSON·바이너리명은 README/`package.json`에서 확인. 발명 금지.)
  - How-to(2~3): README의 실제 사용 시나리오에서 제목 채택 — 최소 "PR 범위 분석", "API 계약 diff/lint" + (있으면) "트러블슈팅 그라운딩".
  - Reference: `probe/README.md`·`probe/docs/` 링크.
  - *주의: 다른 4개 도구 대비 plan에 인라인된 구체 명령이 적음 → executor는 반드시 `probe/README.md`를 먼저 정독해 실제 커맨드를 확보할 것.*

- [ ] **Step 3: specledger** (소스: `specledger/README.md`)
  - Overview: AI 생성 ADR/Spec를 일관 포맷 기록 + 책임 리뷰 게이트(critique→issue-disposition→sign-off). 승인·해시 스탬프 전까지 Write/Edit 차단. 반거수기.
  - Concepts: MCP 서버 + PreToolUse 훅, `begin/end_implementation`, frontmatter=진실원천, 옵셔널 Khala publish.
  - Quickstart(README 전사): `pip install -e ".[dev]"` → `.mcp.json` 등록(SPECLEDGER_ROOT/DOCS/ANTHROPIC_API_KEY) → `.claude/settings.json` PreToolUse 훅 등록.
  - How-to: "스펙 기록·critique", "사인오프 후 구현 게이트 해제".
  - Reference: `specledger/README.md`·BACKLOG.md, GitHub `LivingLikeKrillin/specledger`.

- [ ] **Step 4: mutqa** (소스: `mutqa/SKILL.md`)
  - Overview: 뮤테이션 구동 테스트 품질 하네스. 어드바이저리(TDD 스킬·LLM 리뷰어)가 놓친 행위검증 공백을 변이 생존으로 결정론적으로 드러냄. 결정론(러너) vs 판단(Critic) 분리.
  - Concepts: cosmic-ray 변이, survivor, Test Quality Critic triage(real-gap vs equivalent), 원장(`mutqa-ledger.yaml`), 재실행 시 새 survivor만 재심의.
  - Quickstart(SKILL.md 전사): `pip install cosmic-ray` → 대상 repo(green 스위트) → `changed_source_modules`+`run_mutation`→`survivors.json`→Critic triage→리포트.
  - How-to: "변경 모듈 변이 실행", "survivor triage·원장 흡수".
  - Reference: `mutqa/SKILL.md`·dogfood 문서.

- [ ] **Step 5: 각 도구 ko Overview 작성**(4개, 완료 게이트).

- [ ] **Step 6: 빌드 + 링크 확인**

Run: `npm run build` → PASS. 4페이지 + ko Overview 렌더·repo 링크 확인.

- [ ] **Step 7: 커밋**

```bash
git add src/content/docs/tools src/content/docs/ko/tools
git commit -m "feat: Archon/Probe/specledger/mutqa tool pages (EN full + ko overview)"
```

### Task 10: 시작하기(의도별 라우팅) + 기여 placeholder

**Files:**
- Modify: `src/content/docs/start.md`, `src/content/docs/contributing.md`

- [ ] **Step 1: EN `start.md` 작성** — 의도별 라우팅 표 + 전제조건 + 5분 투어

```md
---
title: Getting Started
description: Pick your goal; it routes you to the right tool.
---

## Pick your goal
| I want to… | → Tool |
|---|---|
| get grounded answers about my codebase/domain | [Nexus](/tools/nexus/) / [Archon](/tools/archon/) |
| ground my PRs & troubleshooting in org context | [Probe](/tools/probe/) |
| stop rubber-stamping specs | [specledger](/tools/specledger/) |
| make AI-generated tests actually verify behavior | [mutqa](/tools/mutqa/) |

## 5-minute tour
[What is Khala?](/) → [Philosophy](/philosophy/) → [Ecosystem](/ecosystem/)

## Prerequisites
- Common: git, a recent runtime.
- Nexus: Docker + Postgres. Probe: Node ≥20. specledger / mutqa: Python (mutqa needs `cosmic-ray`).
```

- [ ] **Step 2: `contributing.md` 경량 작성** — 2차 청중용 placeholder(repo 링크·이슈·규약은 B에서 확장 예정 명시).

- [ ] **Step 3: 빌드 + 라우팅 링크 클릭 확인**

Run: `npm run build` → PASS. 표의 모든 링크가 실 페이지로 연결되는지 확인.

- [ ] **Step 4: 커밋**

```bash
git add src/content/docs/start.md src/content/docs/contributing.md
git commit -m "feat: getting-started intent routing + contributing placeholder"
```

---

## Chunk 4: 검증 · 폴리시 · 배포 확정

목표: 깨진 링크 0, 양 로케일 완료 게이트 충족, 배포 확인.

### Task 11: 링크체커 + 빌드 검증 (spec §10)

**Files:**
- Modify: `package.json` (link check 스크립트)

- [ ] **Step 1: 링크체커 추가 (정책을 명령에 인코딩)**

`package.json` devDependencies에 `"linkinator": "^6.1.2"` 추가, scripts에 아래 추가 후 `npm install`:
```json
"linkcheck": "linkinator ./dist --recurse --skip \"github\\.com|pages\\.dev|astro\\.build|cloudflare\\.com|jsdelivr\\.net\""
```
**왜 이렇게:**
- 디렉토리(`./dist`)를 주면 linkinator가 **자동으로 정적 웹서버를 띄워 그 디렉토리를 웹 루트로 서빙**한다 → 루트-절대 링크(`/tools/nexus/`, `/ko/...`)가 `http://localhost:<port>/`에서 정상 해소(별도 `--server-root` 불필요·금지: 값 없이 쓰면 다음 토큰을 경로로 먹어 명령이 깨짐).
- `--skip` — 외부/사설 호스트(GitHub 사설 repo 401, CDN 등)를 **검사 제외**(빌드 실패 유발 방지). 정책="내부 엄격, 외부 관대"를 명령으로 구현. 점은 이스케이프(`github\.com`), `localhost`/`127.0.0.1`은 skip에 없어 내부 링크는 계속 검사됨.

- [ ] **Step 2: 빌드 후 링크체크**

Run: `npm run build && npm run linkcheck`
Expected: 빌드 PASS. linkinator 요약 마지막 줄에 `0 broken`(또는 `Successfully scanned N links ... 0 broken`). **broken > 0이면 내부 링크 깨짐 → 수정**(외부는 이미 skip이라 여기 안 잡힘). exit code 0.

- [ ] **Step 3: 완료 게이트 확인(ko 최소 커버리지)**

확인: `src/content/docs/ko/index.mdx`, `ko/philosophy.md`, `ko/tools/{nexus,archon,probe,specledger,mutqa}.md`(각 Overview 존재) 7개 파일 존재 + 빌드 시 ko 라우트 생성.

- [ ] **Step 4: 커밋**

```bash
git add package.json package-lock.json
git commit -m "chore: add linkinator link checking; verify bilingual completion gate"
```

### Task 12: Quickstart 실행 검증 표기 (spec §5/§10, owner 분리)

**Files:**
- Modify: 각 `tools/*.md`의 "마지막 검증일" note

**도구별 검증 소유(명시적 — 누락·위장 방지):**

| 도구 | 전제 | 소유 | A에서의 처리 |
|---|---|---|---|
| mutqa | Python + `pip install cosmic-ray` | **executor 검증** | `pip install cosmic-ray` 동작 확인 → note `검증일: 2026-06-07` |
| specledger | Python + `pip install -e ".[dev]"` | **executor 검증** | 소스 repo에서 설치 dry 확인 → note `검증일: 2026-06-07` |
| Probe | Node ≥20 + `pnpm/npm install` | **executor 검증** | 소스 repo에서 의존 설치 확인 → note `검증일: 2026-06-07` |
| Archon | Python + DB(claim-value는 DB 필요) | **부분/owner=사용자** | 설치까지만 executor, DB 의존 질의는 owner=사용자 표기 |
| Nexus | Docker + Postgres(전체 스택) | **owner=사용자** | 사이트 재실행 검증 대기 표기 |

- [ ] **Step 1: executor 검증 도구 실행 (mutqa·specledger·Probe)**

각 소스 repo에서 Quickstart의 설치/최초 동작을 실제 실행. 성공분만 해당 `tools/*.md` note를 `:::note 마지막 검증일: 2026-06-07 (executor 실행 확인):::`로. **실패하면 실패로 보고**(위장 금지).

- [ ] **Step 2: 무거운 전제 도구 owner=사용자 표기 (Nexus·Archon DB부)**

해당 note: `:::note 마지막 검증일: 소스 repo README 기준 — 사이트 재실행 검증 대기 (owner: 사용자):::`. **거짓 검증 주장 절대 금지**(@superpowers:verification-before-completion).

- [ ] **Step 3: 커밋**

```bash
git add src/content/docs/tools
git commit -m "docs: mark per-tool quickstart verification status"
```

### Task 13: 최종 빌드·배포·완료 보고

- [ ] **Step 1: 클린 빌드**

Run (Bash): `npm run build && npm run linkcheck`
(Astro는 빌드 시 `dist`를 자동 정리하므로 별도 `rm` 불필요. 굳이 비우려면 — Bash: `rm -rf dist` / PowerShell: `Remove-Item -Recurse -Force dist`.)
Expected: 빌드 PASS, linkcheck `0 broken`, exit code 0.

- [ ] **Step 2: 푸시**

```bash
git push
```

- [ ] **Step 3: Cloudflare Pages 배포 확인** (owner=사용자)

Cloudflare가 push에 빌드 트리거 → 배포 URL 접속해 EN/ko 렌더 확인. (대시보드 미연결 시 Task 4 Step 3 절차 안내.)

- [ ] **Step 4: 완료 보고** — 라이브 URL, 게이트 충족 여부(ko 7파일), 미검증 Quickstart 목록(owner=사용자) 명시.

---

## 검증 철학 (이 plan의 "테스트")

docs 사이트라 단위테스트가 아니라: ① `npm run build` 무에러 ② 양 로케일 렌더 ③ 내부 링크 0 깨짐 ④ ko 완료 게이트 7파일 ⑤ Quickstart 실행 검증(가능분) + 미검증분 정직 표기. @superpowers:verification-before-completion 준수 — 빌드/링크/렌더는 실제 명령 출력으로 확인 후에만 "완료" 주장.

## 후속(B/C/D 핸드오프)
- B: 코드 개명 Khala→Nexus 반영 → 도구 페이지 콜아웃 제거, 설치 경로 갱신.
- C/D: 통합 설치·버스 배선 실재화 시 `/ecosystem`·`/start` 갱신. A에서 관찰된 "내러티브 단위 vs 배포 단위" 신호로 C·D 범위 재조정.
