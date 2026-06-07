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
Expected: 비어있지 않은 출력 + exit 0. (버전이 semver 아닌 커밋 해시로 나올 수 있음 — 형식 단언 금지, 실행만 되면 OK. 실패 시 중단·보고.)

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
test "$(git rev-parse --abbrev-ref HEAD)" = "master" || { echo "NOT ON master — abort"; exit 1; }
git merge --no-ff spec/domain-invariant-governance -m "merge: Archon (domain-invariant-governance) into master for monorepo consolidation"
git rev-parse --abbrev-ref HEAD   # must print: master
```
Expected: 머지 성공, HEAD=master로 남음. (Task 4의 클론이 올바른 브랜치를 잡으려면 원본 HEAD가 master여야 함 — 이게 핵심 전제. 충돌 시 중단·보고. 이후 원본에서 다른 브랜치로 checkout 금지.)

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

- [ ] **Step 2: 전체 트리 일괄 치환 (md 포함)**

⚠️ **리뷰 반영(2차):** md를 제외하면 컴포넌트 의미 md(`docs/MCP_SERVER.md`·`docs/khala-mvp-design.md`·`docs/SLACK_BOT.md` 등 다수)가 미개명으로 남는다. → **md 포함 전체 텍스트 일괄 치환** 후, 생태계 의미 문자열(아래 Step 3)만 **복원**. 이렇게 해야 컴포넌트 일관(코드·compose·DB·web·문서) + 생태계 보존을 동시에 달성.

Run(검토 후):
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/nexus"
grep -rIl 'khala\|Khala\|KHALA' . --exclude-dir=.git | while read f; do sed -i 's/khala/nexus/g; s/Khala/Nexus/g; s/KHALA/NEXUS/g' "$f"; done
```
DB 자격(POSTGRES_*·DATABASE_URL)·web 자산·Dockerfile·init.sql·docs까지 nexus 정합. `archon_*`는 "khala" 문자열 없음 → 불변. 수동 확인: pyproject `name="nexus"`·CLI `nexus.cli:app`, MCP `nexus_search/answer/graph/suggest/diff/status`, compose DB=nexus.

- [ ] **Step 3: 생태계 문자열 복원 (URL·생태계명 → khala 되돌림)**

Step 2가 생태계 repo URL과 생태계명까지 nexus로 바꿨으므로 **알려진 생태계 문자열만 복원:**
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/nexus"
# 생태계 repo URL (B 후 새 모노레포 khala를 가리킴)
grep -rIl 'LivingLikeKrillin/nexus' . --exclude-dir=.git | xargs -r sed -i 's#LivingLikeKrillin/nexus#LivingLikeKrillin/khala#g'
# 생태계 제품명
grep -rIl 'Nexus Ecosystem\|Nexus 에코시스템\|Nexus 생태계' . --exclude-dir=.git | xargs -r sed -i 's/Nexus Ecosystem/Khala Ecosystem/g; s/Nexus 에코시스템/Khala 에코시스템/g; s/Nexus 생태계/Khala 생태계/g'
```
그 후 `README.md`·`ROADMAP.md`·`CLAUDE.md`를 **육안 1회**: 컴포넌트 의미(패키지·CLI·DB·env)는 nexus 유지, 생태계 의미("Khala 생태계"·생태계 URL)는 khala 복원됐는지 확인. (nexus/ROADMAP.md는 컴포넌트 스코프 문서로 취급 — 생태계 진실원천은 루트 README+docs 사이트.) 잔여 판정은 Task 13 allow-list로.

- [ ] **Step 4: 테스트**

Run: `cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/nexus" && pip install -e . 2>/dev/null; python -m pytest -q`
Expected: 단위 통과(기준선과 동수). MCP 도구명 단언 테스트(`tests/test_mcp.py`)가 `nexus_*`로 함께 바뀌어 통과해야 함. 실패 시 잔여 khala import·경로 수정 후 재실행. *주의: 단위테스트는 compose/init.sql/web을 검증 안 함 → 그건 Task13 감사 + owner Docker 실행이 안전망.*

- [ ] **Step 5: 커밋**

```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala" && git add -A && git commit -m "refactor(nexus)!: rename khala component → nexus (package, CLI, khala_* MCP tools)

BREAKING: CLI khala→nexus; MCP tools khala_*→nexus_*; package khala→nexus"
```

### Task 10: probe 개명 (nexus 클라이언트)

**Files:** Modify: `probe/**` (특히 `src/khala/`, `src/cli/index.ts`, `src/core/config-loader.ts`, `src/mcp/tools.ts`)

- [ ] **Step 1: 클라이언트 디렉토리 rename**

Run: `cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala" && git mv probe/src/khala probe/src/nexus`

- [ ] **Step 2: 식별자·CLI·env·config·문자열 치환 (src + tests 둘 다 — 마크다운 제외)**

⚠️ **리뷰 반영:** `probe/src`만 치환하면 `probe/tests/`(31파일, `../src/khala/` import·`KhalaClient`·`enrichWithKhala` 등)가 죽은 import로 **전멸**한다(테스트=안전망이 무력화). → **probe/ 전체(src+tests) 치환**(node_modules/dist/.md 제외).

Run(검토 후):
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/probe"
grep -rIl 'khala\|Khala\|KHALA\|칼라' . --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=dist | while read f; do sed -i 's/khala/nexus/g; s/Khala/Nexus/g; s/KHALA/NEXUS/g; s/칼라/Nexus/g' "$f"; done
```
src+tests+md(`docs/probe-v0.4-scope.md` 등 컴포넌트 의미) 전부 치환. 결과(수동 확인): CLI `nexus:search/impact/status`, env `NEXUS_BASE_URL`, config `nexus.baseUrl`, import `../nexus/...`, **MCP 도구 `probe.queryKhala`→`probe.queryNexus`**(공개 surface — 의도적, CHANGELOG 기재).

- [ ] **Step 3: 생태계 문자열 복원 (URL → khala)**

```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/probe"
grep -rIl 'LivingLikeKrillin/nexus' . --exclude-dir=.git --exclude-dir=node_modules | xargs -r sed -i 's#LivingLikeKrillin/nexus#LivingLikeKrillin/khala#g'
grep -rIl 'Nexus Ecosystem\|Nexus 에코시스템\|Nexus 생태계' . --exclude-dir=.git --exclude-dir=node_modules | xargs -r sed -i 's/Nexus Ecosystem/Khala Ecosystem/g; s/Nexus 에코시스템/Khala 에코시스템/g; s/Nexus 생태계/Khala 생태계/g'
```
`README.md`·`CLAUDE.md`의 생태계 ROADMAP URL이 khala로 복원됐는지 육안 확인.

- [ ] **Step 4: 테스트**

Run: `cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/probe" && pnpm install && pnpm test:run`
Expected: 기준선(~205) 통과. 실패 시 잔여 참조 수정.

- [ ] **Step 5: 커밋**

```bash
git add -A && git commit -m "refactor(probe)!: rename khala→nexus client (CLI nexus:*, NEXUS_BASE_URL, probe.queryNexus)

BREAKING: CLI khala:*→nexus:*; env KHALA_BASE_URL→NEXUS_BASE_URL; config khala→nexus; MCP tool probe.queryKhala→probe.queryNexus"
```

### Task 11: specledger 개명 (NexusSink)

**Files:** Modify: `specledger/**` (특히 `src/specledger/publish.py`, `config.py`)

- [ ] **Step 1: 식별자 치환**

Run(검토 후):
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/specledger"
grep -rIl 'khala\|Khala\|KHALA' . --exclude-dir=.git | while read f; do sed -i 's/KhalaHttpSink/NexusHttpSink/g; s/KhalaSink/NexusSink/g; s/khala/nexus/g; s/Khala/Nexus/g; s/KHALA/NEXUS/g' "$f"; done
```
specledger의 khala는 전부 **publish 대상(=Nexus) 의미** → 생태계-URL/제품명 없음, blanket 안전(전체 트리). `KhalaHttpSink`/`KhalaSink`를 lowercase 규칙보다 **먼저** 치환(순서 중요). 수동 확인: `NexusSink`/`NexusHttpSink`, config 키 `nexus`, publish.py, README의 config 예시·`"nexus not configured"` 문자열.

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

- [ ] **Step 3: probe/specledger/start 경로 갱신 (EN+ko 해당분)**

- `tools/probe.md`(+ko): 설치/prereq khala 경로·`khala:*` CLI·`KHALA_BASE_URL`→nexus 대응.
- `tools/specledger.md`(+ko): publish **config 블록 `khala:`→`nexus:`**, `url: …/ingest` 설명, `"khala not configured"`→`"nexus not configured"`(코드 Task 11과 정합). "Khala/Nexus" prose는 생태계/컴포넌트 의미에 맞게.
- `start.md`(+ko 있으면): prereq의 khala 경로·env 대응.

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

- [ ] **Step 1: 잔여 khala 감사 (전 파일형식 — 좁은 glob 사각 제거)**

⚠️ **리뷰 반영:** 좁은 glob(py/ts/toml/json)은 yml/sql/Dockerfile/env/js/html/md를 못 봐 Step9·10의 사각과 동일 blind spot. 전 텍스트 파일 감사:
**허용 잔여(allow-list) — 이것만 남아야 정상:** ① 생태계 repo URL `github.com/LivingLikeKrillin/khala`, ② 생태계명 `Khala Ecosystem`/`Khala 에코시스템`/`Khala 생태계`, ③ docs 사이트 생태계 페이지(`index.mdx`·`philosophy.md`·`ecosystem.mdx`·`contributing.md` 및 ko)의 생태계 "Khala". **그 외 모든 khala = 컴포넌트 잔여 = 치환 대상.**

```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala"
ALLOW='archon|github\.com/LivingLikeKrillin/khala|Khala Ecosystem|Khala 에코시스템|Khala 생태계'
echo "=== CODE residual (target: EMPTY) ==="
grep -rIni 'khala' nexus probe specledger mutqa --exclude-dir=.git --exclude-dir=node_modules --exclude-dir=dist | grep -viE "$ALLOW" | head -40
echo "=== DOCS residual (생태계 4페이지 외 컴포넌트 khala = target EMPTY) ==="
grep -rIni 'khala' docs/src --exclude-dir=node_modules | grep -viE "$ALLOW" | grep -viE 'docs/(ko/)?(index|philosophy|ecosystem|contributing)' | head -40
```
Expected: 두 블록 **모두 빈 출력**. 비면 개명 완전. 남으면 그 줄을 위 규칙으로 판정(컴포넌트면 치환·재실행). *기억: 단위테스트는 compose/init.sql/web 자산을 검증 안 하므로, 이 감사 + owner Docker 실행이 그 부분의 실질 안전망.*

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

- [ ] **Step 6: 검증** — 파일 존재 + README 내부 디렉토리 링크 해소 확인:
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala"
for f in README.md LICENSE .editorconfig CONVENTIONS.md assets/logo.svg; do test -e "$f" && echo "OK $f" || echo "MISSING $f"; done
# README의 도구 디렉토리 링크(./nexus 등)가 실제 디렉토리인지
for d in nexus probe specledger mutqa docs; do test -d "$d" && echo "dir $d OK"; done
```
Expected: 전부 OK.

- [ ] **Step 7: 커밋** — `git add README.md LICENSE .editorconfig CONVENTIONS.md assets && git commit -m "chore: root README, MIT LICENSE, editorconfig, CONVENTIONS"`

### Task 15: 하위 CHANGELOG (개명 breaking 기재)

**Files:** Create: `nexus/CHANGELOG.md`, `probe/CHANGELOG.md`, `specledger/CHANGELOG.md`, `mutqa/CHANGELOG.md`, `docs/CHANGELOG.md` (스펙 "하위별 CHANGELOG" 일관 → **5개 전부**)

- [ ] **Step 1:** 각 CHANGELOG에 `## [Unreleased]` 항목:
  - nexus — `BREAKING: Khala→Nexus rename`: CLI `khala`→`nexus`, MCP `khala_*`→`nexus_*`, pyproject name, DB/compose 자격.
  - probe — `BREAKING`: CLI `khala:*`→`nexus:*`, env `KHALA_BASE_URL`→`NEXUS_BASE_URL`, config `khala`→`nexus`, **MCP tool `probe.queryKhala`→`probe.queryNexus`**.
  - specledger — `BREAKING`: `KhalaSink`/`KhalaHttpSink`→`NexusSink`/`NexusHttpSink`, config 키 `khala`→`nexus`.
  - mutqa — `Changed: moved into khala monorepo; no breaking API changes.`
  - docs — `Changed: Nexus component refs updated (khala→nexus); ecosystem name Khala unchanged.`

- [ ] **Step 2: 커밋** — `git add nexus/CHANGELOG.md probe/CHANGELOG.md specledger/CHANGELOG.md mutqa/CHANGELOG.md docs/CHANGELOG.md && git commit -m "docs: per-tool CHANGELOGs documenting Khala→Nexus breaking changes"`

### Task 16: 공유 lint/format (add-only, 절대 reformat 금지)

**Files:** Create: root `ruff.toml`, root `.prettierrc.json`; Modify: 없음(기존 소스 미변경)

⚠️ **리뷰 반영(중요):** 공유 설정이 하위의 *기존 통과* lint을 깨거나 대량 reformat을 유발하면 Chunk 3의 "테스트 green" 보장이 무력화된다. → **(a) 설정 도입 전 baseline 캡처, (b) 루트 설정은 하위가 *이미 만족하는* 공통 디폴트만, (c) 절대 `ruff format`/`prettier --write` 금지(`--check`만), (d) 성공기준 = baseline 대비 차이 없음 + 소스 파일 변경 0.** eslint는 범위에서 **제외**(probe 기존 설정 유지) — 공유는 ruff(Python)·prettier(TS/MD) `--check`만.

- [ ] **Step 1: baseline 캡처(설정 도입 전)**

Run:
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala"
( ruff check nexus specledger mutqa || true ) > /tmp/ruff-baseline.txt 2>&1
echo "baseline lines: $(wc -l < /tmp/ruff-baseline.txt)"
```

- [ ] **Step 2: 루트 ruff.toml 작성(공통 디폴트만)** — line-length 등 하위 다수가 이미 만족하는 값. 하위에 자체 `[tool.ruff]`가 있으면 그것이 authoritative(루트는 미설정 하위의 기본값 역할).

- [ ] **Step 3: ruff 재확인 — baseline 대비 무증가 + reformat 0**

Run:
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala"
( ruff check nexus specledger mutqa || true ) > /tmp/ruff-after.txt 2>&1
diff /tmp/ruff-baseline.txt /tmp/ruff-after.txt && echo "NO NEW LINT" || echo "DIFF — 조정 필요"
git status --porcelain | grep -vE 'ruff.toml|.prettierrc' && echo "SOURCE CHURN — 금지" || echo "no source churn OK"
```
Expected: `NO NEW LINT` + `no source churn OK`. 신규 lint 나오면 루트 설정을 더 보수적으로(해당 룰 미적용). **소스 reformat 발견 시 되돌림.**

- [ ] **Step 4: 루트 .prettierrc.json (probe 기존 스타일 매칭) + --check만**

Run:
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala/probe" && pnpm exec prettier --check "src/**/*.ts" 2>&1 | tail -5 || true
```
Expected: 기존 통과 유지(불일치 다수면 .prettierrc를 probe 기존 스타일에 맞춰 조정 — **--write 금지**). prettier가 probe devDep에 없으면 이 단계 생략·보고(루트 .prettierrc만 둠).

- [ ] **Step 5: 커밋** — `git add ruff.toml .prettierrc.json && git commit -m "chore: shared ruff/prettier config (check-only, add-only; no reformat)"`

### Task 17: 루트 Taskfile + CI 워크플로

**Files:** Create: `Taskfile.yml`, `.github/workflows/ci.yml`

- [ ] **Step 1: Taskfile.yml** — task `test`(각 하위 테스트 위임), `build`(docs build 등), `lint`. 위 §공통 명령을 태스크로 래핑.

- [ ] **Step 2: ci.yml** — GitHub Actions: 하위별 job(nexus pytest, probe pnpm test, specledger pytest, mutqa pytest, docs build+linkcheck). **push 전엔 비활성(설정만)** — YAGNI: 실제 실행은 P4 push 후 owner=사용자.

- [ ] **Step 3: 정적 검증(실행 아님 — 형식만)**

Run:
```bash
cd "C:/Users/Eisen/Desktop/Labs/_bmono/khala"
python -c "import yaml" 2>/dev/null && python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); yaml.safe_load(open('Taskfile.yml')); print('YAML OK')" || echo "(PyYAML 미설치 — pip install pyyaml 후 재시도 또는 owner 검증)"
command -v task >/dev/null && task --list || echo "(task CLI 미설치 — Taskfile YAML 유효성만 확인)"
```
Expected: `YAML OK`(PyYAML 있을 때). 없으면 graceful 메시지 — 차단 아님, 보고. (Taskfile/CI는 *형식 유효*만 검증 — 실제 CI 실행은 push 후 owner=사용자.)

- [ ] **Step 4: 커밋** — `git add Taskfile.yml .github && git commit -m "chore: root Taskfile + CI workflow (configured, activates on push)"`

---

## Chunk 5: P4 — 발행 (owner=사용자, 문서화만)

목표: 비가역·인증 필요 단계를 **실행하지 않고** 정확한 절차로 문서화 + 최종 검증.

### Task 18: 최종 검증 + 발행 절차 문서

**Files:** Create: `_bmono/khala/MIGRATION.md` (발행 체크리스트)

- [ ] **Step 0: 비파괴 경계 확인 (implementer는 아무것도 발행/삭제하지 않음)**

이 청크에서 implementer는 **git push / gh repo / Cloudflare / 원본·옛 remote 삭제·rename을 절대 실행하지 않는다.** 5개 원본 디렉토리 + 옛 GitHub remote 3개는 **그대로 보존**. 이 Task는 MIGRATION.md 문서화 + 보고만. (확인: `git -C "C:/Users/Eisen/Desktop/Labs/[projects] khala-ecosystem/khala" remote -v`로 옛 remote 살아있음 확인 — 변경 금지.)

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
