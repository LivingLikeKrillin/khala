# 모노레포 통합 + Khala→Nexus 개명 + 공통 규약 (하위 프로젝트 B) — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 5개 repo(khala·probe·specledger·mutqa·khala-docs)를 이력 보존하며 단일 모노레포 `khala`로 통합하고, 지식베이스 컴포넌트 Khala→Nexus를 전체 개명하며, 공통 규약(정체·라이선스·버전·lint·CI)을 수립한다.

**Architecture:** 마이그레이션 작업(신규 기능 아님). 순서 = **Archon 머지 → 이력보존 통합(filter-repo) → 모노레포 내 원자적 개명 → 규약 → 발행(owner=사용자)**. 검증은 TDD가 아니라 **각 하위프로젝트 기존 테스트 스위트 green 유지 + grep 감사 + `git log --follow` 이력 확인**.

**Tech Stack:** git, `git-filter-repo`(pip), Python(pytest/ruff), Node≥20(pnpm/vitest), Astro(docs), Taskfile/Make, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-06-07-monorepo-consolidation-rename-design.md`

---

## 경로·환경 규약 (전 청크 공통)

- **원본 repo (불변, 작업 금지):**
  - khala: `C:/Users/Eisen/Desktop/Labs/[projects] khala-ecosystem/khala`
  - probe: `C:/Users/Eisen/Desktop/Labs/[projects] khala-ecosystem/probe`
  - khala-docs: `C:/Users/Eisen/Desktop/Labs/[projects] khala-ecosystem/khala-docs`
  - specledger: `C:/Users/Eisen/Desktop/Labs/[claude] mcp-tools/specledger`
  - mutqa: `C:/Users/Eisen/Desktop/Labs/[claude] skills/mutqa`
- **작업 영역(클론·모노레포 빌드):** `C:/Users/Eisen/Desktop/Labs/_bmono/` (신규, 격리). 클론은 `_bmono/clones/<name>`, 모노레포는 `_bmono/khala`.
- **최종 모노레포 배치:** B 검증 완료 후 owner=사용자가 `_bmono/khala`를 원하는 위치로 이동·원본 archive (P4). **원본은 B 전체 동안 보존**(롤백).
- 이 plan 문서 자체는 원본 khala-docs에 있음 — 실행자는 여기서 plan을 읽고, 통합엔 khala-docs의 **클론**을 쓴다.
- Bash 툴 사용(git-bash). Windows 경로 공백 → 따옴표 필수.
- 각 하위프로젝트 테스트 명령(검증 기준선):
  - nexus(khala): `python -m pytest -q` (단위). DB/Docker 통합테스트(test DB 5433)는 **owner=사용자**.
  - probe: `pnpm install && pnpm test:run` (vitest, 기준 ~205 통과).
  - specledger: `pip install -e ".[dev]" && python -m pytest -q` (기준 ~69 통과).
  - mutqa: `pip install -e . 2>/dev/null; python -m pytest -q` (기준 ~34 통과). cosmic-ray 실변이는 제외(단위만).
  - docs: `npm install && npm run build && npm run check && npm run linkcheck`.

---

## File Structure (최종 모노레포)

```
_bmono/khala/                 # 모노레포 루트
  README.md  LICENSE  .editorconfig  CONVENTIONS.md  Taskfile.yml
  .github/workflows/ci.yml
  assets/logo.svg
  nexus/      # 구 khala (P1 시점 top명=nexus, 내부 패키지는 P2에서 khala→nexus)
  probe/  specledger/  mutqa/
  docs/       # 구 khala-docs
```

---

## Chunk 1: P0 — 준비 (브랜치 검증 · Archon 머지 · 클론)

목표: 미머지 작업 유실 없이 모든 소스를 작업 클론으로 확보. **원본 불변.**

### Task 1: 도구 설치 + 작업 영역 생성

**Files:** (없음 — 환경 준비)

- [ ] **Step 1: git-filter-repo 설치 확인**

Run: `pip install git-filter-repo && git filter-repo --version`
Expected: 버전 출력. (실패 시 중단·보고.)

- [ ] **Step 2: 작업 영역 생성**

Run: `mkdir -p "C:/Users/Eisen/Desktop/Labs/_bmono/clones"`
Expected: 디렉토리 생성.

### Task 2: 브랜치 무손실 검증 (게이트)

**Files:** (없음 — 검증)

- [ ] **Step 1: khala 브랜치 delta 확인**

Run:
```bash
cd "C:/Users/Eisen/Desktop/Labs/[projects] khala-ecosystem/khala"
for b in docs/slack-guide-readme-update feature/api-completion-ui-spec feature/mcp-server-integration-tests feature/tests-slack-bot spec/domain-invariant-governance; do echo "== $b =="; git log master..$b --oneline | wc -l; done
```
Expected: 처음 4개 = `0`, `spec/domain-invariant-governance` > 0 (약 25). **0이 아닌 게 Archon 외에 있으면 중단·보고**(유실 위험).

- [ ] **Step 2: probe 브랜치 delta 확인**

Run:
```bash
cd "C:/Users/Eisen/Desktop/Labs/[projects] khala-ecosystem/probe"
for b in feat/v0.2-api-analysis feat/v0.3-mcp-server feat/v0.4-khala-integration; do echo "== $b =="; git log main..$b --oneline | wc -l; done
```
Expected: 전부 `0`. 아니면 중단·보고.

### Task 3: Archon → khala master 머지

**Files:** Modify: 원본 khala repo의 master (예외적으로 원본 수정 — Archon 포착 필요)

- [ ] **Step 1: master 체크아웃 + 머지**

Run:
```bash
cd "C:/Users/Eisen/Desktop/Labs/[projects] khala-ecosystem/khala"
git checkout master
git merge --no-ff spec/domain-invariant-governance -m "merge: Archon (domain-invariant-governance) into master for monorepo consolidation"
```
Expected: 머지 성공(충돌 시 중단·보고).

- [ ] **Step 2: 머지 후 테스트(가능 범위)**

Run: `cd "C:/Users/Eisen/Desktop/Labs/[projects] khala-ecosystem/khala" && python -m pytest -q`
Expected: 단위 테스트 통과. (DB 통합테스트 실패는 Docker 미기동 탓일 수 있음 → owner=사용자 표기, 단위가 green이면 진행.) 결과 보고.

### Task 4: 5개 repo 작업 클론

**Files:** Create: `_bmono/clones/{nexus,probe,specledger,mutqa,docs}`

- [ ] **Step 1: 클론 (로컬 경로에서)**

Run:
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/clones"
git clone "C:/Users/Eisen/Desktop/Labs/[projects] khala-ecosystem/khala" nexus
git clone "C:/Users/Eisen/Desktop/Labs/[projects] khala-ecosystem/probe" probe
git clone "C:/Users/Eisen/Desktop/Labs/[claude] mcp-tools/specledger" specledger
git clone "C:/Users/Eisen/Desktop/Labs/[claude] skills/mutqa" mutqa
git clone "C:/Users/Eisen/Desktop/Labs/[projects] khala-ecosystem/khala-docs" docs
```
Expected: 5개 클론 생성. 각 `git -C <name> log --oneline -1`로 HEAD 확인. (nexus 클론은 master=Archon머지본인지 확인.)

- [ ] **Step 2: 커밋 불요(작업 영역)** — `_bmono`는 git 추적 대상 아님. 보고만.

---

## Chunk 2: P1 — 이력 보존 통합 (filter-repo)

목표: 5 클론을 서브디렉토리로 이력 보존 병합 → 단일 모노레포. 검증: 하위 테스트 + 이력.

### Task 5: 각 클론을 서브디렉토리로 재작성

**Files:** Modify: 각 `_bmono/clones/<name>` (filter-repo, 클론이므로 안전)

- [ ] **Step 1: filter-repo 적용 (서브디렉토리명=최종명)**

Run:
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/clones/nexus" && git filter-repo --force --to-subdirectory-filter nexus
cd "C:/Users/Eisen/Desktop/Labs/_bmono/clones/probe" && git filter-repo --force --to-subdirectory-filter probe
cd "C:/Users/Eisen/Desktop/Labs/_bmono/clones/specledger" && git filter-repo --force --to-subdirectory-filter specledger
cd "C:/Users/Eisen/Desktop/Labs/_bmono/clones/mutqa" && git filter-repo --force --to-subdirectory-filter mutqa
cd "C:/Users/Eisen/Desktop/Labs/_bmono/clones/docs" && git filter-repo --force --to-subdirectory-filter docs
```
Expected: 각 repo의 전체 트리가 `<name>/` 하위로 이동(이력 보존). `git -C nexus ls-files | head`로 `nexus/...` 확인.

### Task 6: 모노레포 생성 + 5개 병합

**Files:** Create: `_bmono/khala` (git repo)

- [ ] **Step 1: 모노레포 init**

Run:
```bash
mkdir -p "C:/Users/Eisen/Desktop/Labs/_bmono/khala" && cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala" && git init -q && git commit -q --allow-empty -m "chore: init khala monorepo"
```
Expected: 빈 repo + 초기 커밋.

- [ ] **Step 2: 각 클론을 unrelated-history 병합** (probe는 기본브랜치 main, 나머지 master)

Run:
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala"
for n in nexus probe specledger mutqa docs; do
  git remote add $n "C:/Users/Eisen/Desktop/Labs/_bmono/clones/$n"
  git fetch -q $n
  B=$(git -C "C:/Users/Eisen/Desktop/Labs/_bmono/clones/$n" symbolic-ref --short HEAD)
  git merge -q --allow-unrelated-histories --no-edit "$n/$B"
  git remote remove $n
done
git log --oneline | head -8
```
Expected: 5개 머지 커밋. 루트에 `nexus/ probe/ specledger/ mutqa/ docs/` 존재(`ls`).

### Task 7: 통합 검증 (하위 테스트 + 이력)

**Files:** (없음 — 검증)

- [ ] **Step 1: 이력 보존 확인**

Run:
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala"
git log --follow --oneline -- nexus/README.md | wc -l
git log --follow --oneline -- probe/package.json | wc -l
git log --follow --oneline -- docs/package.json | wc -l
```
Expected: 각 > 1 (이력 보존됨). 1이면 이력 손실 → 보고.

- [ ] **Step 2: 하위 테스트(이동 후 동작)**

각 하위에서 §공통 테스트 명령 실행. (probe: `cd probe && pnpm install && pnpm test:run`; specledger: `cd specledger && pip install -e ".[dev]" && python -m pytest -q`; mutqa: `cd mutqa && python -m pytest -q`; docs: `cd docs && npm install && npm run build && npm run check && npm run linkcheck`; nexus: `cd nexus && python -m pytest -q` 단위.)
Expected: 각 기준선과 동일 통과(개명 전이므로 이름 변화 없음). 실패는 보고(경로 의존 깨짐 의심).

- [ ] **Step 3: 통합 커밋 상태 보고** — 이미 머지 커밋들로 기록됨. `git log --oneline | head`.

---

## Chunk 3: P2 — Khala→Nexus 개명 (모노레포 내 원자적, sense-aware)

목표: 코드 repo의 khala(=지식베이스)를 전부 nexus로. docs는 생태계 "Khala" 유지·컴포넌트만 갱신. 검증: 전 하위 테스트 green + grep 감사.

**원칙:** 개명은 도구별로 하고 **각 도구 테스트로 즉시 검증**(테스트가 안전망). 작업 브랜치 `b/rename`에서.

### Task 8: 개명 작업 브랜치

- [ ] **Step 1:** `cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala" && git checkout -b b/rename`

### Task 9: nexus 패키지 개명

**Files:** Modify: `nexus/**`

- [ ] **Step 1: 패키지 디렉토리 rename**

Run: `cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala" && git mv nexus/khala nexus/nexus`
Expected: `nexus/nexus/` 존재(`__init__.py` 등). (실 하위경로는 `ls nexus`로 확인 후 조정.)

- [ ] **Step 2: 식별자·import·MCP 도구·pyproject 치환**

Run(검토 후 적용):
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/nexus"
# 패키지/모듈 참조
grep -rl --include=*.py --include=*.toml --include=*.cfg --include=*.md 'khala' . | while read f; do sed -i 's/khala/nexus/g' "$f"; done
```
주의: nexus/ 내 모든 "khala"는 지식베이스 의미라 blanket 안전. **단 `archon_*`는 "khala" 문자열 없음 → 불변.** 치환 후 수동 확인 포인트: pyproject `name = "nexus"`, `[project.scripts] nexus = "nexus.cli:app"`, MCP 도구 `nexus_search/answer/graph/suggest/diff/status`.

- [ ] **Step 3: 테스트**

Run: `cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/nexus" && pip install -e . 2>/dev/null; python -m pytest -q`
Expected: 단위 통과(기준선과 동수). 실패 시 잔여 khala import·경로 수정 후 재실행.

- [ ] **Step 4: 커밋**

```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala" && git add -A && git commit -m "refactor(nexus)!: rename khala component → nexus (package, CLI, khala_* MCP tools)

BREAKING: CLI khala→nexus; MCP tools khala_*→nexus_*; package khala→nexus"
```

### Task 10: probe 개명 (nexus 클라이언트)

**Files:** Modify: `probe/**` (특히 `src/khala/`, `src/cli/index.ts`, `src/core/config-loader.ts`, `src/mcp/tools.ts`)

- [ ] **Step 1: 클라이언트 디렉토리 rename**

Run: `cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala" && git mv probe/src/khala probe/src/nexus`

- [ ] **Step 2: 식별자·CLI·env·config·문자열 치환**

Run(검토 후):
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/probe/src"
# 코드 식별자/경로 (대소문자 분리)
grep -rl 'khala' . | while read f; do sed -i 's/khala/nexus/g; s/Khala/Nexus/g; s/KHALA/NEXUS/g' "$f"; done
# 한국어 UI "칼라" → "Nexus"
grep -rl '칼라' . | while read f; do sed -i 's/칼라/Nexus/g' "$f"; done
```
결과 주요 변경(수동 확인): CLI `nexus:search/impact/status`, env `NEXUS_BASE_URL`, config `nexus.baseUrl`, import `../nexus/...`. (probe README/docs의 khala 언급도 동일 치환 — `cd probe && grep -rl 'khala\|칼라' . | ...`.)

- [ ] **Step 3: 테스트**

Run: `cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/probe" && pnpm install && pnpm test:run`
Expected: 기준선(~205) 통과. 실패 시 잔여 참조 수정.

- [ ] **Step 4: 커밋**

```bash
git add -A && git commit -m "refactor(probe)!: rename khala→nexus client (CLI nexus:*, NEXUS_BASE_URL)

BREAKING: CLI khala:*→nexus:*; env KHALA_BASE_URL→NEXUS_BASE_URL; config khala→nexus"
```

### Task 11: specledger 개명 (NexusSink)

**Files:** Modify: `specledger/**` (특히 `src/specledger/publish.py`, `config.py`)

- [ ] **Step 1: 식별자 치환**

Run(검토 후):
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/specledger"
grep -rl --include=*.py --include=*.md 'khala\|Khala' . | while read f; do sed -i 's/KhalaHttpSink/NexusHttpSink/g; s/KhalaSink/NexusSink/g; s/khala/nexus/g; s/Khala/Nexus/g' "$f"; done
```
수동 확인: `NexusSink`/`NexusHttpSink`, config 키 `nexus`, publish 로직.

- [ ] **Step 2: 테스트**

Run: `cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/specledger" && pip install -e ".[dev]" && python -m pytest -q`
Expected: 기준선(~69) 통과.

- [ ] **Step 3: 커밋**

```bash
git add -A && git commit -m "refactor(specledger)!: rename KhalaSink→NexusSink, config khala→nexus

BREAKING: public sink class names + config key renamed"
```

### Task 12: docs 개명 (sense-aware — 생태계 Khala 유지)

**Files:** Modify: `docs/src/content/docs/tools/{nexus,archon,probe}.md` + `ko/` 미러, `docs/src/content/docs/start.md`

- [ ] **Step 1: Nexus 페이지 — 콜아웃 제거 + 경로/도구/CLI 갱신 (EN+ko)**

`docs/src/content/docs/tools/nexus.md` 및 `docs/src/content/docs/ko/tools/nexus.md`:
- `:::caution[Naming] … :::` 블록 **제거**.
- 설치/clone 경로 `khala`→`nexus`, CLI `khala …`→`nexus …`, MCP 도구 `khala_*`→`nexus_*`.

- [ ] **Step 2: Archon 페이지 — repo 경로 갱신 (EN+ko)**

`tools/archon.md`(+ko): `khala/claims`→`nexus/claims`, 브랜치/패키지 경로의 khala→nexus. **생태계 "Khala" 언급은 유지.** `archon_*` 도구명 유지.

- [ ] **Step 3: probe/start 경로 갱신 (EN+ko 해당분)**

`tools/probe.md`·`start.md`의 설치/prereq khala 경로·`khala:*` CLI·`KHALA_BASE_URL`→nexus 대응.

- [ ] **Step 4: 빌드·링크·생태계명 보존 검증**

Run:
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/docs" && npm install && npm run build && npm run check && npm run linkcheck
# 생태계 "Khala"는 남아야 정상(랜딩/철학), 컴포넌트 khala 경로는 0
grep -ric 'khala' src/content/docs | head
```
Expected: build/check/linkcheck PASS. 랜딩·철학에 생태계 "Khala" 잔존(정상), 도구 페이지의 *컴포넌트/경로* khala는 nexus로 치환됨.

- [ ] **Step 5: 커밋**

```bash
git add -A && git commit -m "docs: rename Nexus component refs khala→nexus; keep ecosystem name Khala (EN+ko)"
```

### Task 13: 개명 완전성 감사 + 머지

**Files:** (없음 — 검증)

- [ ] **Step 1: 코드 잔여 khala 감사**

Run:
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala"
echo "=== code residual (should be ~0, ignore archon_*/comments) ==="
grep -rni 'khala' nexus probe specledger mutqa --include=*.py --include=*.ts --include=*.toml --include=*.json | grep -vi 'archon' | head -30
```
Expected: 0에 수렴(남으면 의미 확인 후 처리 — 생태계 의미면 유지, 컴포넌트면 치환). 보고.

- [ ] **Step 2: 전 하위 테스트 재확인** — Task 7 Step 2와 동일하게 5개 재실행, 전부 green.

- [ ] **Step 3: 개명 브랜치 머지**

Run: `cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala" && git checkout master && git merge --no-ff b/rename -m "merge: Khala→Nexus rename" && git branch -d b/rename`

---

## Chunk 4: P3 — 공통 규약

목표: 루트 메타·라이선스·lint·버전·CI. 각 파일은 단일 책임.

### Task 14: 루트 README + LICENSE + .editorconfig + CONVENTIONS.md

**Files:** Create: `README.md`, `LICENSE`, `.editorconfig`, `CONVENTIONS.md`, `assets/logo.svg`

- [ ] **Step 1: 로고 복사** — `cp docs/src/assets/logo.svg assets/logo.svg` (A의 SVG 재사용).

- [ ] **Step 2: 루트 README.md** — 생태계 소개(두 실패 모드 1줄) + 도구 맵 표(nexus/probe/specledger/mutqa/docs 한 줄 + 각 디렉토리 링크) + "docs 사이트" 링크. (docs의 랜딩 카피 재사용, 중복 최소.)

- [ ] **Step 3: LICENSE (MIT)** — `MIT License\n\nCopyright (c) 2026 LivingLikeKrillin` 표준 전문. (probe·nexus 기존 MIT와 동일 문구 정렬; specledger·mutqa·docs는 이 루트 라이선스로 커버.)

- [ ] **Step 4: .editorconfig** — UTF-8, LF, trim trailing whitespace, py=4 spaces, ts/js/md/astro=2 spaces.

- [ ] **Step 5: CONVENTIONS.md** — 네이밍(소문자 디렉토리=도구), **버전=도구별 독립 semver + 각 하위 CHANGELOG.md**, 기여 흐름(브랜치·커밋 conventional), "생태계=Khala / 컴포넌트=Nexus" 용어 규약.

- [ ] **Step 6: 커밋** — `git add README.md LICENSE .editorconfig CONVENTIONS.md assets && git commit -m "chore: root README, MIT LICENSE, editorconfig, CONVENTIONS"`

### Task 15: 하위 CHANGELOG (개명 breaking 기재)

**Files:** Create: `nexus/CHANGELOG.md`, `probe/CHANGELOG.md`, `specledger/CHANGELOG.md`

- [ ] **Step 1:** 각 CHANGELOG에 `## [Unreleased] — BREAKING: Khala→Nexus rename` 항목 — nexus(CLI·`khala_*` MCP·pyproject), probe(CLI `khala:*`·`KHALA_BASE_URL`·config), specledger(`KhalaSink`/`KhalaHttpSink`·config). mutqa/docs는 breaking 없음(생략 또는 note).

- [ ] **Step 2: 커밋** — `git add **/CHANGELOG.md && git commit -m "docs: changelogs documenting Khala→Nexus breaking changes"`

### Task 16: 공유 lint/format

**Files:** Create: root `ruff.toml`(또는 `pyproject.toml [tool.ruff]`), root `.prettierrc`, root `eslint` 공유 설정(가능 시); Modify: 각 하위가 루트 설정 상속

- [ ] **Step 1: Python ruff** — 루트 `ruff.toml` 공통 규칙. nexus/specledger/mutqa가 상속(각 기존 ruff 설정과 충돌 없게; 기존 통과 라인 유지). Run `ruff check nexus specledger mutqa` → 신규 에러 0(기존 기준선 유지).

- [ ] **Step 2: TS prettier/eslint** — 루트 `.prettierrc`(2 spaces, single quote 등 probe 기존 맞춤). probe/docs 적용. Run probe `pnpm lint`(있으면) 또는 `pnpm test:run` 재확인 green.

- [ ] **Step 3: 커밋** — `git add ruff.toml .prettierrc* eslint* && git commit -m "chore: shared lint/format config (ruff, prettier)"`

### Task 17: 루트 Taskfile + CI 워크플로

**Files:** Create: `Taskfile.yml`, `.github/workflows/ci.yml`

- [ ] **Step 1: Taskfile.yml** — task `test`(각 하위 테스트 위임), `build`(docs build 등), `lint`. 위 §공통 명령을 태스크로 래핑.

- [ ] **Step 2: ci.yml** — GitHub Actions: 하위별 job(nexus pytest, probe pnpm test, specledger pytest, mutqa pytest, docs build+linkcheck). **push 전엔 비활성(설정만)** — YAGNI: 실제 실행은 P4 push 후 owner=사용자.

- [ ] **Step 3: 커밋** — `git add Taskfile.yml .github && git commit -m "chore: root Taskfile + CI workflow (activates on push)"`

---

## Chunk 5: P4 — 발행 (owner=사용자, 문서화만)

목표: 비가역·인증 필요 단계를 **실행하지 않고** 정확한 절차로 문서화 + 최종 검증.

### Task 18: 최종 검증 + 발행 절차 문서

**Files:** Create: `_bmono/khala/MIGRATION.md` (발행 체크리스트)

- [ ] **Step 1: 전체 최종 검증** — 5개 하위 테스트 + 개명 감사(Chunk3 Task13) 재실행, 전부 green/clean. 결과 표로 보고.

- [ ] **Step 2: MIGRATION.md 작성 (owner=사용자 절차)**:
  1. `_bmono/khala`를 최종 위치로 이동(예: `[projects] khala/`).
  2. 새 GitHub repo `khala` 생성 + `git remote add origin … && git push -u origin master`.
  3. 옛 repo: `khala`→rename `nexus-legacy` + archive; `probe`·`specledger` archive(read-only). (GitHub 설정, 삭제 금지.)
  4. Cloudflare Pages: `docs/` 서브디렉토리 기준 재연결(build cmd `npm --prefix docs run build` 또는 루트 조정, output `docs/dist`).
  5. 원본 5개 디렉토리는 모노레포 검증·푸시 확인 후 archive/삭제(owner 판단).

- [ ] **Step 3: 커밋** — `git add MIGRATION.md && git commit -m "docs: owner publish/migration checklist"`

- [ ] **Step 4: 완료 보고** — 모노레포 위치, 하위 테스트 결과, 개명 감사 결과, 남은 owner=사용자 단계(P4 1~5).

---

## 검증 철학 (이 plan의 "테스트")
신규 코드 TDD 아님 → ① 각 하위 **기존 테스트 스위트 green 유지**(이동 후·개명 후 2회)가 핵심 안전망, ② `git log --follow` 이력 보존, ③ `grep` 개명 완전성(코드 0, docs 생태계-의미만), ④ docs build+linkcheck. @superpowers:verification-before-completion 준수 — 실제 명령 출력 확인 후에만 "완료". 파괴적 작업은 **클론에서만**, 원본·옛 remote 보존.

## 후속 (C/D)
B 완료 후 C(통합 설치)·D(버스 배선) 착수 여부 + "배포단위 vs 내러티브단위" 가치 재검증. nexus 개명이 docs와 정합 → A 콜아웃 제거 완료 상태.
