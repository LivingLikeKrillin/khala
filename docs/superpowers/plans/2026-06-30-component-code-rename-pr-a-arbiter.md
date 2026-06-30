# PR-A: Arbiter (specledger → khala.arbiter) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the `specledger` component to **Arbiter** at the code-identifier level — directory, namespace package, env vars, MCP key, all cross-references, and the doc code-identifiers/asset that the doc-prose PRs deliberately kept — leaving `master` fully green.

**Architecture:** This is **PR-A** of the four-unit migration designed in
`docs/superpowers/specs/2026-06-30-component-code-rename-design.md` (read it first). It is a
mechanical rename, so the safety net is the **existing** test suite (no new tests are
written); each task makes a change and re-runs the existing suite, which must stay green.
`specledger` becomes a PEP 420 namespace package under `khala/` (`src/khala/arbiter/`, import
`khala.arbiter`, dist `khala-arbiter`). Nexus does **not** import specledger — its references
are prose/comments naming the tool — so this PR has no functional coupling into nexus, only
naming updates.

**Tech Stack:** Python 3.11+, hatchling, pytest (`pythonpath=["src","tests"]`), MCP server,
PreToolUse hook. Cross-refs touch TypeScript (probe), YAML/SQL/JS (nexus, configs), Markdown
(docs), and an SVG/excalidraw asset.

**Hard rules (from the spec):**
- Hard cutover — **no** aliases/shims; old `SPECLEDGER_*` / MCP key `specledger` are removed, not kept.
- Do **not** touch historical records: accepted ADRs, `**/superpowers/**` (except this plan/spec), `specs/**`, `**/CHANGELOG.md`, `**/dogfood*`, `MIGRATION.md`. They keep the old name by design.
- GitHub source-repo URLs (`github.com/.../specledger`) are **deferred to PR-D** — do not change them here; they are expected grep-gate survivors.

---

## Chunk 1: Package move, namespace restructure, and internal verification

### Task 1: Pre-flight — branch and baseline green

**Files:** none (verification only)

- [ ] **Step 1: Create the execution branch from up-to-date master**

```bash
cd "C:/Users/Eisen/Desktop/Labs/[projects] khala"
git checkout master && git pull --ff-only
git checkout -b rename/pr-a-arbiter
```

- [ ] **Step 2: Establish the baseline — specledger suite is green BEFORE any change**

Run: `python -m pytest specledger/tests -q`
Expected: all pass (this is the safety net the rename must preserve).

- [ ] **Step 3: Record the cross-reference inventory (re-derive per spec)**

Run: `git grep -n -i "specledger" -- ':!**/superpowers/**' ':!specs/**' ':!**/CHANGELOG.md' ':!**/dogfood*' ':!MIGRATION.md' ':!adr/ADR-000[1-3]*'`
Expected: a list dominated by `specledger/` itself plus the cross-refs (nexus comments, `probe/src/nexus/types.ts`, `mutqa/tests/fixtures/*`, `ken.manifest.yaml`, root configs, `docs/...`). Keep this list open; it is the work checklist for Tasks 7–10.

### Task 2: Move directory and restructure to the `khala` namespace

**Files:**
- Move: `specledger/` → `arbiter/`
- Move: `arbiter/src/specledger/` → `arbiter/src/khala/arbiter/`

- [ ] **Step 1: Move the component directory**

```bash
git mv specledger arbiter
```

- [ ] **Step 2: Restructure into the namespace layout (no `khala/__init__.py` — PEP 420 implicit namespace)**

```bash
mkdir -p arbiter/src/khala
git mv arbiter/src/specledger arbiter/src/khala/arbiter
```

- [ ] **Step 3: Verify the tree shape**

Run: `ls arbiter/src/khala/arbiter` (expect the module files: `server.py`, `review.py`, `gate.py`, …) and confirm **no** `arbiter/src/khala/__init__.py` exists.

### Task 3: Convert `pyproject.toml` to the namespace package

**Files:**
- Modify: `arbiter/pyproject.toml`

- [ ] **Step 1: Update name, description, and wheel package path**

Change:
```toml
[project]
name = "khala-arbiter"
description = "Arbiter — ADR/SDD recording & accountable-review governance MCP"
...
[tool.hatch.build.targets.wheel]
packages = ["src/khala/arbiter"]
```
(Leave `[tool.pytest.ini_options] pythonpath = ["src","tests"]` and `[tool.ruff]` as-is — `src` is still the root; `from khala.arbiter…` now resolves under it.)

- [ ] **Step 2: Commit the structural move**

```bash
git add -A
git commit -m "refactor(arbiter): move specledger/ → arbiter/src/khala/arbiter (namespace package)"
```

### Task 4: Rewrite absolute imports and entry-point module paths

**Files:**
- Modify: `arbiter/src/khala/arbiter/*.py` (only files with **absolute** `specledger.` imports — relative `from .x` imports are unaffected)
- Modify: `arbiter/tests/*.py` (tests use absolute imports)
- Modify: `arbiter/hooks/pretooluse_gate.py`
- Modify: `arbiter/tests/conftest.py`, `arbiter/tests/helpers.py`

- [ ] **Step 1: Find every absolute `specledger` import / module reference inside `arbiter/`**

Run: `git grep -n -E "specledger" -- arbiter/`
Inspect each hit: classify as (a) absolute import `from specledger.x` / `import specledger.x` / `python -m specledger.x`, or (b) a string/comment naming the tool.

- [ ] **Step 2: Rewrite absolute imports `specledger` → `khala.arbiter`**

For every `from specledger.<mod> import …` → `from khala.arbiter.<mod> import …`; every `import specledger.<mod>` → `import khala.arbiter.<mod>`; `python -m specledger.server` → `python -m khala.arbiter.server` (in the hook and any docstring usage). Relative imports (`from .errors import …`) are left untouched.

- [ ] **Step 3: Run the suite — must still be green**

Run: `python -m pytest arbiter/tests -q`
Expected: all pass. A failure here means a missed import — fix before continuing.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(arbiter): rewrite absolute imports specledger → khala.arbiter"
```

---

## Chunk 2: Interface identifiers (env, MCP key) and the residual references

### Task 5: Env vars `SPECLEDGER_*` → `ARBITER_*` (hard cutover)

**Files:**
- Modify: `arbiter/src/khala/arbiter/config.py` (and any module reading env), `arbiter/hooks/pretooluse_gate.py`, `arbiter/tests/*` referencing the vars, `arbiter/README.md`

- [ ] **Step 1: Enumerate the env vars**

Run: `git grep -n -E "SPECLEDGER_[A-Z_]+" -- arbiter/`
Expected set (verify against output): `SPECLEDGER_ROOT`, `SPECLEDGER_DOCS`, and any `SPECLEDGER_NEXUS_TOKEN` / others.

- [ ] **Step 2: Rename each to the `ARBITER_` prefix (no alias kept)**

Replace every `SPECLEDGER_<X>` → `ARBITER_<X>` across `arbiter/`. Do **not** leave a fallback read of the old name (hard cutover).

- [ ] **Step 3: Run the suite**

Run: `python -m pytest arbiter/tests -q`
Expected: all pass (tests that set the env vars now use the new names).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(arbiter)!: rename SPECLEDGER_* env vars to ARBITER_* (hard cutover)"
```

### Task 6: MCP server key + marker dir

**Files:**
- Modify: any code/config registering the MCP server name; `arbiter/.gitignore` (the `.specledger/` marker)

- [ ] **Step 1: Find the MCP key and marker-dir references**

Run: `git grep -n -E "\"specledger\"|\.specledger/" -- arbiter/`
The MCP server key `"specledger"` (in server registration and example configs) → `"arbiter"`. The runtime marker directory `.specledger/` → `.arbiter/` (update the constant that defines it + `.gitignore`).

- [ ] **Step 2: Rename the MCP key and marker dir**

`"specledger"` MCP key → `"arbiter"`; `.specledger/` → `.arbiter/` in the defining constant and `.gitignore`.

- [ ] **Step 3: Run the suite**

Run: `python -m pytest arbiter/tests -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "feat(arbiter)!: MCP key specledger→arbiter, marker dir .specledger→.arbiter"
```

### Task 7: Cross-references in `nexus/` (prose/comments + module-path mentions)

**Files (from the audit; re-verify with grep):**
- Modify: `nexus/nexus/a2a/external_ingest_skill.py`, `nexus/nexus/a2a/mapping.py`, `nexus/nexus/auth/principal.py`, `nexus/nexus/ingest/pipeline.py`, `nexus/nexus/web/js/doctype-signal.js`, `nexus/init.sql`, `nexus/tests/test_a2a_provenance_db.py`

- [ ] **Step 1: List the nexus hits**

Run: `git grep -n -i "specledger" -- nexus/`

- [ ] **Step 2: Update each by kind**

- **Prose/comments naming the tool** ("specledger 거버넌스", "upstream governance tool (specledger)") → brand **Arbiter**.
- **Module/path references** (`specledger.promote_external`, "specledger `document_types.yaml`") → `khala.arbiter.promote_external`, "Arbiter's `document_types.yaml`".
- **Test stamp values** in `test_a2a_provenance_db.py` (`"sha256:specledger-stamp-…"`) → `"sha256:arbiter-stamp-…"` (arbitrary fixture value; rename for coherence).
- **Historical spec id** `SPEC-specledger-a2a-publish-phase3` (a comment referencing a `specs/` doc) → **leave as-is** (names an immutable historical artifact).

- [ ] **Step 3: Run nexus tests (cross-ref safety)**

Run: `python -m pytest nexus/tests -q`
Expected: all pass (nexus has no import dependency on the package, so only the edited test's string values matter).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(nexus): update specledger→Arbiter naming references (no functional change)"
```

### Task 8: Remaining cross-refs — probe (TS), mutqa fixtures, ken.manifest

**Files:**
- Modify: `probe/src/nexus/types.ts`
- Rename + edit: `mutqa/tests/fixtures/cr_dump_specledger.jsonl` → `cr_dump_arbiter.jsonl` (and any test referencing the filename)
- Modify: `ken.manifest.yaml`

- [ ] **Step 1: probe TS reference**

Run: `git grep -n -i "specledger" -- probe/`. Update the `specledger` mentions in `probe/src/nexus/types.ts` (a label/string/comment) → `arbiter`/Arbiter as the kind dictates. Then run `cd probe && pnpm test` (or `npm test`); expected: pass.

- [ ] **Step 2: mutqa test fixture**

Run: `git grep -n -i "specledger" -- mutqa/`. The fixture `mutqa/tests/fixtures/cr_dump_specledger.jsonl` is a captured cosmic-ray dump *of the specledger subject*. Rename the file → `cr_dump_arbiter.jsonl`, update its internal path strings and any test that loads it by name. Run `python -m pytest mutqa/tests -q`; expected: pass.

- [ ] **Step 3: ken.manifest.yaml**

Update the `specledger`/path entries in `ken.manifest.yaml` (a registry of artifacts; the path/label `specledger` → `arbiter`). This is data, not code — no test, but verify YAML still parses: `python -c "import yaml,sys; yaml.safe_load(open('ken.manifest.yaml'))"`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor: update specledger→arbiter cross-refs (probe types, mutqa fixture, ken.manifest)"
```

### Task 9: Root build/config

**Files:**
- Modify: `Taskfile.yml`, `.github/workflows/ci.yml`, `ruff.toml`, `.gitignore`

- [ ] **Step 1: Find root-config hits**

Run: `git grep -n -i "specledger" -- Taskfile.yml .github/ ruff.toml .gitignore`

- [ ] **Step 2: Update paths and job names**

- `Taskfile.yml`: task paths `specledger/` → `arbiter/`, any `python -m specledger.server` → `python -m khala.arbiter.server`.
- `.github/workflows/ci.yml`: the specledger job's `working-directory` / paths / cache keys `specledger` → `arbiter`.
- `ruff.toml`: `specledger` path globs → `arbiter`.
- `.gitignore`: `specledger/`-relative ignores → `arbiter/`.

- [ ] **Step 3: Validate config locally**

Run: `task --list` (expect no error; the arbiter task is listed) and `python -m pytest arbiter/tests nexus/tests mutqa/tests -q` (expect all green).

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "ci: update specledger→arbiter paths in Taskfile, CI, ruff, gitignore"
```

---

## Chunk 3: Docs identifiers, diagram asset, and the gate

### Task 10: Doc code-identifiers + diagram asset rename

**Files:**
- Modify: `docs/src/content/docs/tools/arbiter.md`, `docs/src/content/docs/ko/tools/arbiter.md`
- Rename: `docs/public/diagrams/specledger.svg` → `arbiter.svg`; `docs/src/diagrams/specledger.excalidraw` → `arbiter.excalidraw`

- [ ] **Step 1: Update the kept code-identifiers in the Arbiter tool pages**

In `arbiter.md` (+ko): `SPECLEDGER_DOCS`/`SPECLEDGER_ROOT` → `ARBITER_DOCS`/`ARBITER_ROOT`; `specledger.server` → `khala.arbiter.server`; MCP key `"specledger"` → `"arbiter"`; `.specledger/` → `.arbiter/`; hook path `specledger/hooks/...` → `arbiter/hooks/...`. **Do NOT** change the `github.com/.../specledger` source-repo URL (deferred to PR-D).

- [ ] **Step 2: Rename the diagram asset + update the `img src`**

```bash
git mv docs/public/diagrams/specledger.svg docs/public/diagrams/arbiter.svg
git mv docs/src/diagrams/specledger.excalidraw docs/src/diagrams/arbiter.excalidraw
```
Then in `arbiter.md` (+ko) change `src="/diagrams/specledger.svg"` → `src="/diagrams/arbiter.svg"`. (The `specledger.svg` had no brand label inside per the diagram audit, so no label edit is needed — only the filename + reference.)

- [ ] **Step 3: Build the docs site to verify**

Run: `npm --prefix docs run build`
Expected: build succeeds, no broken-asset/page errors.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "docs(arbiter): update kept code-identifiers + rename diagram asset specledger→arbiter"
```

### Task 11: Residual-grep gate + full verification + push

**Files:** none (verification + final push)

- [ ] **Step 1: Residual-grep gate — zero non-historical, non-repo-URL `specledger`**

Run:
```bash
git grep -n -i "specledger" -- ':!**/superpowers/**' ':!specs/**' ':!**/CHANGELOG.md' ':!**/dogfood*' ':!MIGRATION.md' ':!adr/ADR-000[1-3]*' ':!adr/ADR-000[4-5]*'
```
Expected: the **only** surviving hits are `github.com/.../specledger` source-repo URLs (deferred to PR-D). Any other hit is a straggler — fix it and re-run. (ADR-0004/0005 are excluded: they are the mapping records.)

- [ ] **Step 2: No-shim assertion**

Run: `git grep -n -E "SPECLEDGER_|\"specledger\"" -- ':!**/superpowers/**' ':!specs/**' ':!adr/**'`
Expected: **zero** hits — confirms the old env vars and MCP key are gone, not aliased.

- [ ] **Step 3: Full local test + build matrix green**

Run: `python -m pytest arbiter/tests nexus/tests mutqa/tests -q` and `cd probe && pnpm test` and `npm --prefix docs run build`.
Expected: all green.

- [ ] **Step 4: Push and open the PR**

```bash
git push -u origin rename/pr-a-arbiter
gh pr create --base master --title "refactor(arbiter)!: rename specledger → khala.arbiter (code, env, MCP, docs)" --body "PR-A of the component code-rename migration (spec: docs/superpowers/specs/2026-06-30-component-code-rename-design.md). Hard cutover: SPECLEDGER_*→ARBITER_*, MCP key specledger→arbiter, namespace package khala.arbiter. Repo URL rename deferred to PR-D. Residual-grep gate: only repo-URL survivors remain."
```

- [ ] **Step 5: Confirm CI green on the PR before merge**

Wait for the full CI matrix to pass on the PR. A red check is a blocker (hard cutover — no half-green merge). Merge only when green.

---

## Done criteria for PR-A

- `master` (after merge) has `arbiter/src/khala/arbiter/`, import `khala.arbiter`, dist `khala-arbiter`.
- `ARBITER_*` env vars and MCP key `arbiter` in force; **no** `SPECLEDGER_*` / `specledger` MCP key anywhere outside historical records and the (PR-D-deferred) repo URLs.
- All suites + docs build green; CI green.
- Next: plan **PR-B (Adept)** against the updated `master`.
