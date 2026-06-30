# PR-C: Observer + Probe atomic swap Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** In ONE atomic PR, perform the **name swap**: the PR/code-review tool `probe` (TypeScript) → **Observer** (`@khala/observer`), AND the mutation tool `mutqa` (Python) → **Probe** (`khala.probe`) — taking over the freed `probe` name. Leave `master` fully green.

**Architecture:** **PR-C** of the four-unit migration (spec: `docs/superpowers/specs/2026-06-30-component-code-rename-design.md`; PR-A Arbiter + PR-B Adept already merged). Mechanical rename; existing tests are the safety net. The collision is handled by **ordered moves in a single PR**: `probe/`→`observer/` **first** (frees the `probe` name), then `mutqa/`→`probe/`. Two tech stacks: Observer is npm/TypeScript (vitest, tsup); Probe(mutation) is a Python setuptools package → namespace `khala.probe` (mirror PR-B's explicit setuptools config).

**Tech Stack:** TypeScript/Node (probe→observer: pnpm, vitest, tsup, has its OWN CI workflow `probe/.github/workflows/probe.yml`); Python 3.11 (mutqa→probe: setuptools, pytest, a Claude Code SKILL).

**Hard rules (from the spec):**
- Hard cutover — no aliases. Old npm name `probe`, bins `probe`/`probe-mcp`, MCP key `probe`, rule ids `probe/<rule>`, env `PROBE_NEXUS_*` are removed (→observer); old `mutqa` package/skill/ledger removed (→probe).
- **The collision is the whole point.** After this PR, the bare token `probe` is **legitimately** the mutation tool (`khala.probe`, `probe/` dir, `probe-ledger.yaml`, the `tools/probe.md` page). So the Observer-half gate must NOT grep bare `probe`; it greps the **old review-tool-specific identifiers** (see Task 9).
- **KEEP (do NOT touch):**
  - **Adept's internal module `adept/src/khala/adept/probe.py`** (`khala.adept.probe`) — unrelated to either tool. Zero edits.
  - `probe/.claude/skills/` skill names `check-scope`, `split-pr`, `state-matrix` (they do not contain "probe"/"mutqa"; they move with the dir to `observer/.claude/skills/` but keep their names).
  - `github.com/.../probe` and `.../mutqa` repo URLs → deferred to **PR-D**.
  - Historical records (accepted ADRs, `**/superpowers/**` except this plan, `specs/**`, `**/CHANGELOG.md`, `**/dogfood*`, `**/e2e-2026*`, `MIGRATION.md`, ADR-0004/0005).
- **mutqa has NO env vars** (verified — only the review tool has `PROBE_NEXUS_TOKEN`/`PROBE_NEXUS_TRANSPORT`), so there is no `MUTQA_*`→`PROBE_*` env collision; only `PROBE_*`→`OBSERVER_*` (review tool).

---

## Chunk 1: probe (TS review tool) → Observer  [FIRST — frees the `probe` name]

### Task 1: Pre-flight — branch and baseline green

- [ ] **Step 1: Branch off up-to-date master**

```bash
cd "C:/Users/Eisen/Desktop/Labs/[projects] khala"
git checkout master && git pull --ff-only
git checkout -b rename/pr-c-observer-probe
```

- [ ] **Step 2: Baseline green (safety net)**

Run: `cd probe && pnpm install --frozen-lockfile && pnpm run test:run; cd ..` and `python -m pytest mutqa/tests -q`
Expected: probe vitest all pass; mutqa all pass. Record counts.

- [ ] **Step 3: Authoritative inventory (source of truth)**

Run: `git grep -n -i -E "\bmutqa\b|\bprobe\b|PROBE_|probe-mcp" -- ':!**/superpowers/**' ':!specs/**' ':!**/CHANGELOG.md' ':!**/dogfood*' ':!**/e2e-2026*' ':!MIGRATION.md' ':!adr/**' ':!**/*.png' ':!adept/**'`
(`:!adept/**` excludes Adept's internal `probe.py`/`probe` vocabulary, which is KEEP.) Every other hit must be dispositioned. Expected survivors: `github.com/.../probe`|`/mutqa` repo URLs (PR-D).

### Task 2: Move `probe/` → `observer/` and rename the npm package

**Files:** Move `probe/` → `observer/`; `observer/package.json`

- [ ] **Step 1: Move the directory (this frees the `probe` name for Chunk 2)**

```bash
git mv probe observer
```

- [ ] **Step 2: Rename the npm package + bins**

`observer/package.json`: `"name": "probe"` → `"@khala/observer"`; `"bin"`: `"probe"`→`"observer"`, `"probe-mcp"`→`"observer-mcp"` (point at the same `dist/cli/index.js` / `dist/mcp/server.js`). Update `description` brand prose. Keep `check-scope`/`split-pr`/`state-matrix` skill names under `observer/.claude/skills/`.

- [ ] **Step 3: Commit the move**

```bash
git add -A
git commit -m "refactor(observer): move probe/ → observer/, npm probe → @khala/observer"
```

### Task 3: Rename Observer's in-package identifiers (TS)

**Files:** `observer/src/**`, `observer/.github/workflows/probe.yml`, `observer/.claude/**`, `observer/scripts/**`, `observer/tsup.config.*`, `observer/README.md`/`CLAUDE.md`

- [ ] **Step 1: Discovery grep**

Run: `git grep -n -i -E "\bprobe\b|PROBE_|probe-mcp" -- observer/`
Classify: MCP server key/name, rule ids (`probe/<rule>`), env `PROBE_NEXUS_*`, CLI/bin self-references, the `probe.yml` workflow, brand prose, dist/script paths.

- [ ] **Step 2: Rename identifiers**

- MCP server key/name `probe` → `observer` (server registration in `src/mcp/server.ts` + any `.mcp.json` example).
- API-lint **rule ids** `probe/<rule>` → `observer/<rule>` (e.g. `probe/nullable`, `probe/error-response`, … in `src/api/rules/*` and tests).
- env `PROBE_NEXUS_TOKEN`/`PROBE_NEXUS_TRANSPORT` → `OBSERVER_NEXUS_*`.
- CLI self-refs (`probe check`, `npx probe`) → `observer`; bin paths already in package.json (Task 2).
- Brand prose in `observer/README.md`, `observer/CLAUDE.md` → Observer.
- Rename the workflow file: `git mv observer/.github/workflows/probe.yml observer/.github/workflows/observer.yml` and update its `name:`/paths inside.

- [ ] **Step 3: Build + test (green)**

Run: `cd observer && pnpm run build && pnpm run test:run; cd ..`
Expected: tsup build OK, vitest all pass. Then `git grep -n -i -E "\bprobe\b|PROBE_|probe-mcp" -- observer/` → only legitimate residue (e.g. a `github.com/.../probe` repo URL, deferred), NOT bins/rule-ids/MCP-key/env.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(observer)!: rename probe→observer identifiers (MCP key, rule ids, PROBE_*→OBSERVER_*, bins, workflow)"
```

---

## Chunk 2: mutqa (Python mutation tool) → Probe  [SECOND — takes the freed name]

### Task 4: Move `mutqa/` → `probe/` and restructure to `khala.probe`

**Files:** Move `mutqa/` → `probe/`, `probe/src/mutqa/` → `probe/src/khala/probe/`

- [ ] **Step 1: Move + namespace restructure (the `probe/` dir is now free after Task 2)**

```bash
git mv mutqa probe
mkdir -p probe/src/khala
git mv probe/src/mutqa probe/src/khala/probe
```
Confirm no `probe/src/khala/__init__.py` (PEP 420); `probe/src/khala/probe/__init__.py` stays.

- [ ] **Step 2: `probe/pyproject.toml` (setuptools — mirror PR-B/Adept's PROVEN explicit config)**

`name = "khala-probe"`; explicit `[tool.setuptools] package-dir = {"" = "src"}` + `packages = ["khala.probe"]` (or `packages.find where=["src"] namespaces=true`). If mutqa had a `[project.scripts]`, repoint to `khala.probe.*`. **Verify by editable install** (not just pytest): `pip install -e probe && python -c "import khala.probe; print('ok')" && (python -c "import probe" && echo FAIL || echo "ok: no top-level probe") && (python -c "import mutqa" && echo FAIL || echo "ok: mutqa gone")`.

- [ ] **Step 3: Commit the move**

```bash
git add -A
git commit -m "refactor(probe): move mutqa/ → probe/src/khala/probe (namespace package, takes the freed name)"
```

### Task 5: Rename Probe(mutation)'s in-package identifiers

**Files:** `probe/src/khala/probe/*.py`, `probe/tests/*.py`, `probe/SKILL.md`, `probe/references/**`, `probe/pyproject.toml`, the ledger file

- [ ] **Step 1: Discovery grep**

Run: `git grep -n -i "\bmutqa\b" -- probe/`
Classify: imports, SKILL `name:` field, `mutqa-ledger.yaml` filename + references, prose, fixture subject strings.

- [ ] **Step 2: Rename identifiers**

- Imports: `from mutqa.<mod> import …` / `import mutqa.<mod>` → `khala.probe.<mod>` (relative imports untouched).
- **SKILL `name:` field** (`probe/SKILL.md`): `name: mutqa` → `name: probe` (user-facing skill invocation handle — renamed per Decision #1; supersedes PR2's doc-phase `name: mutqa` retention).
- Ledger file: `git mv probe/<path>/mutqa-ledger.yaml …/probe-ledger.yaml` if a committed sample exists; rename the `mutqa-ledger.yaml` string in code (`ledger.py`) + tests + fixtures → `probe-ledger.yaml`.
- Fixture subject strings / prose `mutqa` → Probe (brand) or `khala.probe` (module path), as the kind dictates.

- [ ] **Step 3: Test (green)**

Run: `python -m pytest probe/tests -q`
Expected: all pass. Then `git grep -n -i "\bmutqa\b" -- probe/` → zero (outside historical).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(probe)!: rename mutqa→khala.probe identifiers (imports, SKILL name, ledger filename)"
```

---

## Chunk 3: CI, docs, diagram-asset swap, cross-refs, and the collision-aware gate

### Task 6: Root CI + tooling

**Files:** `.github/workflows/ci.yml`, `.gitignore`, `Taskfile.yml`, `ruff.toml`

- [ ] **Step 1: Discovery + rename**

Run: `git grep -n -i -E "\bmutqa\b|\bprobe\b|PROBE_" -- .github/ .gitignore Taskfile.yml ruff.toml`. Then:
- `ci.yml`: the **review-tool** `probe` job/working-dir/paths → `observer`; the **mutation** `mutqa` job → `probe` (working-dir `mutqa/`→`probe/`, `python -m pytest mutqa/tests`→`probe/tests`); env `PROBE_*`→`OBSERVER_*` for the observer job.
- `.gitignore`/`ruff.toml`/`Taskfile.yml`: repoint `probe/`(review)→`observer/` and `mutqa/`→`probe/` paths. **Order-sensitive:** apply the `probe→observer` substitution BEFORE introducing `mutqa→probe`, so the rule for the old review tool doesn't accidentally catch the new mutation `probe/`.

- [ ] **Step 2: Commit**

```bash
git add -A
git commit -m "ci: rename probe→observer + mutqa→probe jobs/paths (ordered)"
```

### Task 7: Docs identifiers + diagram-asset swap (ordered)

**Files:** `docs/src/content/docs/tools/observer.md`(+ko), `docs/src/content/docs/tools/probe.md`(+ko); diagram assets

- [ ] **Step 1: observer.md (was the review tool's page, already Observer-branded in PR2)**

Update kept code-identifiers: `npx probe`/`pnpm add -D probe` → `observer` / `@khala/observer`; bins `probe`/`probe-mcp` → `observer`/`observer-mcp`; rule ids `probe/<rule>` → `observer/<rule>`; MCP key `probe` → `observer`; `probe-v{N}-scope.md` doc-path refs as appropriate. **Keep** the `github.com/.../probe` repo URL (PR-D).

- [ ] **Step 2: probe.md (the mutation tool's page, already Probe-branded in PR2)**

Update kept code-identifiers: `mutqa.scope`/`mutqa.run`/`mutqa.ledger`/`mutqa.report` → `khala.probe.*`; `mutqa-ledger.yaml` → `probe-ledger.yaml`; package mention `mutqa` → `khala-probe`. **Keep** the `github.com/.../mutqa` repo URL (PR-D).

- [ ] **Step 3: Diagram-asset swap — ORDERED to avoid the `probe.svg` filename collision**

```bash
# 1) review tool's diagram first (frees probe.svg)
git mv docs/public/diagrams/probe.svg docs/public/diagrams/observer.svg
git mv docs/src/diagrams/probe.excalidraw docs/src/diagrams/observer.excalidraw
# 2) then the mutation tool's diagram takes probe.svg
git mv docs/public/diagrams/mutqa.svg docs/public/diagrams/probe.svg
git mv docs/src/diagrams/mutqa.excalidraw docs/src/diagrams/probe.excalidraw
```
Then update the `img src` in `observer.md`(+ko) → `/diagrams/observer.svg` and in `probe.md`(+ko) → `/diagrams/probe.svg`. (Per the diagram audit, these per-tool SVGs carry **no internal brand-name label**, so only filenames + `img src` change — no label edit.)

- [ ] **Step 4: Build docs (green)**

Run: `npm --prefix docs run build`
Expected: build succeeds, no broken-asset errors.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs: observer/probe code-identifiers + ordered diagram-asset swap (probe→observer, mutqa→probe)"
```

### Task 8: Other cross-refs

- [ ] **Step 1: Find any remaining non-historical refs**

Run the Task 1 Step 3 inventory grep again. Disposition anything not yet handled, with these specific calls (verified to exist on master):
- **nexus prose naming the REVIEW tool "Probe" → Observer** (NOT the new mutation Probe): `nexus/ROADMAP.md` (the "Probe" rows describing "PR 분석 + API 검증 … TypeScript/Node/MCP"), `nexus/nexus/a2a/mapping.py:85` ("Probe's `SpecRef.approvedHash`"), and the `nexus/tests/test_a2a_provenance_db.py` / `test_approved_hash_provenance.py` "Probe" mentions. These describe the review tool → **Observer**. nexus imports neither package, so these are prose/comment edits only.
- **`adept.manifest.yaml`** (root): `path: probe/src/core/concern-drift.ts` → `observer/src/core/concern-drift.ts` (a REVIEW-tool source path; **name it explicitly** — the collision-aware Observer gate deliberately does NOT flag bare `probe/src`, since that path is now the mutation tool, so this straggler must be handled here).
- **KEEP (generic vocabulary, NOT a tool):** `nexus/tests/test_auth_deps.py` `/probe` test route + `def probe(...)` — unrelated to either tool; leave intact.
- `INDEX.md` / any other `probe`(review)/`mutqa` brand prose → Observer / Probe per kind.
Confirm Adept's `adept/src/khala/adept/probe.py` (+ `models.py`/`service.py`/`test_cli_v1.py` Adept-internal `probe` vocabulary) is **untouched** (`git diff --name-only master..HEAD | grep '^adept/src'` → empty).

- [ ] **Step 2: Commit (if any changes)**

```bash
git add -A
git commit -m "refactor: remaining probe→observer / mutqa→probe naming references"
```

### Task 9: Collision-aware residual gate + full verification + push

- [ ] **Step 1: mutqa gate (plain — must be zero)**

Run: `git grep -n -i "\bmutqa\b" -- ':!**/superpowers/**' ':!specs/**' ':!**/CHANGELOG.md' ':!**/dogfood*' ':!**/e2e-2026*' ':!MIGRATION.md' ':!adr/**'`
Expected: only `github.com/.../mutqa` repo URLs (PR-D). Anything else = straggler.

- [ ] **Step 2: Observer gate (collision-aware — do NOT grep bare `probe`)**

The bare token `probe` is now legitimately the mutation tool + `khala.adept.probe`. So grep only the **old review-tool-specific identifiers**, which must ALL be gone (→observer):
```bash
git grep -n -E "probe-mcp|PROBE_NEXUS|\"name\": \"probe\"|probe/(nullable-explicit|no-nullable-optional|error-response-schema|field-type-required|deprecated-lifecycle|enum-required|path-naming|pagination-required|property-naming|example-required)|workflows/probe\.yml" -- ':!**/superpowers/**' ':!specs/**' ':!adr/**' ':!**/dogfood*' ':!**/e2e-2026*'
```
Expected: **zero**. (These tokens uniquely identified the old review tool; the new mutation `probe` package uses none of them.)

- [ ] **Step 3: Adept-internal probe untouched**

Run: `git diff --name-only master..HEAD | grep '^adept/' || echo "adept/ untouched ✓"`
Expected: no `adept/` source files changed (a doc mention is acceptable only if it referenced the review tool by name).

- [ ] **Step 4: Full matrix green (run individually)**

Run: `cd observer && pnpm run test:run; cd ..`; `python -m pytest probe/tests -q`; `python -m pytest adept/tests adept-web/api/tests arbiter/tests nexus/tests -q`; root `tests/`; `npm --prefix docs run build`.
Expected: all green.

- [ ] **Step 5: Push + PR (controller merges after review + CI)**

```bash
git push -u origin rename/pr-c-observer-probe
gh pr create --base master --title "refactor!: swap probe→Observer (@khala/observer) and mutqa→Probe (khala.probe)" --body "PR-C of the component code-rename migration — the atomic name swap. Hard cutover. Review tool probe→Observer (npm @khala/observer, bins observer/observer-mcp, MCP key observer, rule ids observer/*, PROBE_*→OBSERVER_*, workflow observer.yml). Mutation tool mutqa→Probe (khala.probe namespace pkg, SKILL name probe, probe-ledger.yaml). Ordered moves (probe→observer first). Adept-internal probe.py untouched; repo URLs deferred to PR-D."
```

- [ ] **Step 6: Confirm CI green before merge** (hard cutover — no half-green merge).

---

## Done criteria for PR-C

- `observer/` (npm `@khala/observer`, bins `observer`/`observer-mcp`, MCP key `observer`, rule ids `observer/*`, `OBSERVER_*` env, `observer.yml` workflow) — no `probe`/`probe-mcp` review-tool identifiers remain.
- `probe/src/khala/probe/` (`import khala.probe`, dist `khala-probe`, SKILL `name: probe`, `probe-ledger.yaml`) — no `mutqa` remains; `import mutqa` fails; no top-level `probe` Python package.
- Adept-internal `khala.adept.probe` untouched; both suites + docs build + CI green.
- Next: **PR-D** — rename archived GitHub repos + update all deferred source-repo URLs.
