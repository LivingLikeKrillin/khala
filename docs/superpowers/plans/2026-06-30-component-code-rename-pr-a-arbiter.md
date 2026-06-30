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

- [ ] **Step 3: Record the cross-reference inventory — this grep is the AUTHORITATIVE checklist**

Run: `git grep -n -i "specledger" -- ':!**/superpowers/**' ':!specs/**' ':!**/CHANGELOG.md' ':!**/dogfood*' ':!MIGRATION.md' ':!adr/ADR-000[1-3]*'`

Every hit must be **dispositioned** by end of this PR (renamed, or confirmed an expected survivor). The per-task file lists below are a guide, but this grep is the source of truth. Expect these groups (verified against current master):
- `specledger/` package itself (Tasks 2–6) and `arbiter/` after the move.
- **Functional importers** (Task 8): root `tests/test_a2a_e2e_external_spec.py`, `tests/test_a2a_e2e_specledger_to_nexus.py`, and `ken/tests/test_hashing_parity.py` — these literally `from specledger… import`/`importorskip("specledger")` and **break on the move**.
- Naming references in `nexus/` (Task 7), `probe/src/nexus/types.ts`, `mutqa/tests/**` + `mutqa/references/critic-eval.md`, `ken.manifest.yaml` (Task 8).
- Top-level docs with functional links/titles (Task 8): `README.md`, `adr/README.md`, `CONVENTIONS.md`, `INDEX.md`.
- Root config (Task 9) and Arbiter docs + asset (Task 10).
- **Expected survivors (do NOT rename in this PR — gate carve-out, Task 11):** `github.com/.../specledger` source-repo URLs (PR-D); `docs/astro.config.mjs` redirect entries `'/tools/specledger' → '/tools/arbiter'` (+ko) which intentionally keep old doc URLs working; the transitional gloss "Arbiter (formerly specledger)" / "(옛 specledger)" in `arbiter.md`(+ko).

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
Expected set (verify against output): `SPECLEDGER_ROOT`, `SPECLEDGER_DOCS`, `SPECLEDGER_NEXUS_TOKEN`, `SPECLEDGER_NEXUS_TRANSPORT`, and any others the grep surfaces.

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

### Task 8: Functional cross-refs — importers, doc links, fixtures, manifest

This task fixes the references that **break on the move** (real importers + functional doc
links) plus the data/string references. Order matters: do the importers first so the test
matrix can validate.

**Files:**
- Modify (importers — break on move): `tests/test_a2a_e2e_external_spec.py`, `tests/test_a2a_e2e_specledger_to_nexus.py` (root), `ken/tests/test_hashing_parity.py`, `ken/src/ken/hashing.py` (docstring)
- Rename: `tests/test_a2a_e2e_specledger_to_nexus.py` → `tests/test_a2a_e2e_arbiter_to_nexus.py`
- Modify (functional doc links/titles): `README.md`, `adr/README.md`, `CONVENTIONS.md`, `INDEX.md`
- Modify (naming/strings): `probe/src/nexus/types.ts`, `mutqa/references/critic-eval.md`, `mutqa/tests/test_extract.py`, `mutqa/tests/test_run_config.py`, `mutqa/tests/test_run_session.py`, `mutqa/tests/test_ledger_integration.py`, `ken.manifest.yaml`
- Rename: `mutqa/tests/fixtures/cr_dump_specledger.jsonl` → `cr_dump_arbiter.jsonl`; edit `mutqa/tests/fixtures/cr_dump_sample.jsonl` path strings

- [ ] **Step 1: Repoint the root e2e importers (they `from specledger… import`)**

In `tests/test_a2a_e2e_external_spec.py` and `tests/test_a2a_e2e_specledger_to_nexus.py`:
rewrite `from specledger.<mod> import …` → `from khala.arbiter.<mod> import …`,
`pytest.importorskip("specledger")` → `importorskip("khala.arbiter")`, and any
`specledger/src` sys.path / path strings → `arbiter/src`. Then rename the file:
`git mv tests/test_a2a_e2e_specledger_to_nexus.py tests/test_a2a_e2e_arbiter_to_nexus.py`.

- [ ] **Step 2: Repoint `ken/tests/test_hashing_parity.py` (forced by PR-A's move)**

This test does `SPEC_SRC = parents[2] / "specledger" / "src"` + `from specledger.hashing import content_hash` to assert ken↔arbiter hash parity. Update the path to `parents[2] / "arbiter" / "src"` and the import to `from khala.arbiter.hashing import content_hash`. Also fix the `specledger` mention in `ken/src/ken/hashing.py`'s docstring → `Arbiter`. (This is a forced cross-ref repoint caused by PR-A's directory move — **not** the PR-B `ken→adept` brand rename, which stays out of scope.)

- [ ] **Step 3: Run the importer safety net**

Run: `python -m pytest tests/test_a2a_e2e_arbiter_to_nexus.py tests/test_a2a_e2e_external_spec.py ken/tests/test_hashing_parity.py -q`
Expected: all pass (or skip cleanly if a DB/Docker `importorskip` guard trips — confirm it is the guard, not an import error).

- [ ] **Step 4: Functional doc links + titles**

Update relative links and titles that break on the move:
- `README.md`: `[./specledger](./specledger)` → `[./arbiter](./arbiter)` (+ any prose path).
- `adr/README.md`: `[Arbiter](../specledger)` → `[Arbiter](../arbiter)` (the link path; brand text already "Arbiter").
- `CONVENTIONS.md`: the `specledger/` directory-name example → `arbiter/`.
- `INDEX.md`: `# Specledger Index` / `specledger` entries → `# Arbiter Index` / `arbiter`.

- [ ] **Step 5: Naming/string references (probe TS, mutqa, ken.manifest)**

- `probe/src/nexus/types.ts`: `specledger` label/string/comment → `arbiter`/Arbiter per kind. Run `cd probe && pnpm test`; expected: pass.
- `mutqa/` strings: the cosmic-ray subject path `src/specledger/review.py` (in `cr_dump_*.jsonl` fixtures, `critic-eval.md`, and the `test_extract/run_config/run_session/ledger_integration` assertions) → `src/khala/arbiter/review.py`; rename `cr_dump_specledger.jsonl` → `cr_dump_arbiter.jsonl` and update any test loading it by name. Run `python -m pytest mutqa/tests -q`; expected: pass.
- `ken.manifest.yaml`: the `specledger` path/label entry → `arbiter`. Verify parse: `python -c "import yaml; yaml.safe_load(open('ken.manifest.yaml'))"`.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor: repoint specledger→khala.arbiter importers, doc links, fixtures, manifest"
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

Run: `task --list` (expect no error; the arbiter task is listed) and the full Python matrix
`python -m pytest arbiter/tests nexus/tests mutqa/tests ken/tests tests/ -q` (expect all
green — note `ken/tests` and root `tests/` are included because Task 8 repointed importers there).

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
Expected: the only surviving hits are the **declared expected survivors** — `github.com/.../specledger` source-repo URLs (PR-D), `docs/astro.config.mjs` redirect entries (`'/tools/specledger' → '/tools/arbiter'`, +ko — they intentionally keep old doc URLs alive, the same deferral rationale as the repo URLs), and the transitional gloss "Arbiter (formerly specledger)" / "(옛 specledger)" in `arbiter.md`(+ko). **Any hit outside that set is a straggler** — fix it and re-run. (ADR-0004/0005 already excluded above as mapping records.)

- [ ] **Step 2: No-shim assertion**

Run: `git grep -n -E "SPECLEDGER_|\"specledger\"" -- ':!**/superpowers/**' ':!specs/**' ':!adr/**'`
Expected: **zero** hits — confirms the old env vars and MCP key are gone, not aliased.

- [ ] **Step 3: Full local test + build matrix green**

Run: `python -m pytest arbiter/tests nexus/tests mutqa/tests ken/tests tests/ -q` and `cd probe && pnpm test` and `npm --prefix docs run build`.
Expected: all green (full matrix — every suite that imports the renamed package or a repointed cross-ref).

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
