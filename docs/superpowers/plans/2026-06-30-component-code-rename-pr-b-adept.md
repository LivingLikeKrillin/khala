# PR-B: Adept (ken + ken-web → khala.adept + khala.adept_web) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the `ken` (cognitive-debt meter) and `ken-web` (its web product) components to **Adept** at the code-identifier level — namespace packages `khala.adept` / `khala.adept_web`, the npm `@khala/adept-web` frontend, the `ken`→`adept` CLI, `KEN_*`→`ADEPT_*` env, the Postgres/cookie identifiers, and the doc code-identifiers the doc-prose PRs kept — leaving `master` fully green.

**Architecture:** **PR-B** of the four-unit migration (spec: `docs/superpowers/specs/2026-06-30-component-code-rename-design.md`; PR-A Arbiter already merged). Mechanical rename — the **existing** test suite is the safety net (no new tests). Both packages move to the `khala/` namespace (`ken/`→`adept/src/khala/adept/`, `ken-web/api/`→`adept-web/api/src/khala/adept_web/`, `ken-web/web/`→`adept-web/web/` npm `@khala/adept-web`). `ken-web-api` imports the core package, so both rename together in this PR.

**Tech Stack:** Python 3.11+/3.13 (ken: setuptools, Typer CLI; ken-web-api: FastAPI), TypeScript/Vite frontend (vitest), Postgres (docker-compose), pytest. `ken` is a setuptools package (not hatchling) — namespace config differs from Arbiter's.

**Hard rules (from the spec):**
- Hard cutover — **no** aliases/shims; old `KEN_*`, `ken`/`ken-web-admin` CLIs, `ken_session` cookie are removed, not kept.
- **`ken` is a short, common token.** Use `\bken\b` (word boundary) discovery + human classification. NEVER touch substrings: `token`, `broken`, `taken`, `weaken`, `kenobi`, etc.
- **Keep (do NOT rename):**
  - The Scots-etymology note in the Adept docs (e.g. ``ken` (Scots: "to know")`) — it explains the English word, not the identifier.
  - **Adept's internal module `ken/src/ken/probe.py`** → moves to `adept/src/khala/adept/probe.py` but the module **name `probe` is RETAINED** (Adept-internal vocabulary; unrelated to the Observer/Probe tools — confirmed by audit). Do not rename the module to anything else.
  - `github.com/.../ken` source-repo URLs (none expected in docs after PR2, but if present they are deferred to **PR-D**).
- Do **not** touch historical records (accepted ADRs, `**/superpowers/**` except this plan, `specs/**`, `**/CHANGELOG.md`, `**/dogfood*`, `MIGRATION.md`, ADR-0004/0005).
- **DB migration:** the spec assumes the dogfood Postgres is reprovisionable, so this is a **config-only** rename (user/db/cookie names) — no `ALTER`/dump-restore. A fresh `adept`/`adept` DB is created on next `task up`.

---

## Chunk 1: ken → khala.adept (core package)

### Task 1: Pre-flight — branch and baseline green

- [ ] **Step 1: Branch off up-to-date master**

```bash
cd "C:/Users/Eisen/Desktop/Labs/[projects] khala"
git checkout master && git pull --ff-only
git checkout -b rename/pr-b-adept
```

- [ ] **Step 2: Baseline green (safety net)**

Run: `python -m pytest ken/tests -q` and `python -m pytest ken-web/api/tests -q` and `cd ken-web/web && npm test -- --run; cd ../..`
Expected: all pass. Record counts.

- [ ] **Step 3: Authoritative inventory (this grep is the source of truth)**

Run: `git grep -n -i -E "\bken\b|ken-web|ken_web|\bKEN_" -- ':!**/superpowers/**' ':!specs/**' ':!**/CHANGELOG.md' ':!**/dogfood*' ':!MIGRATION.md' ':!adr/**' ':!**/*.png'`
Every hit must be dispositioned. **Expected legitimate survivors (do NOT rename):** the Scots-etymology `ken` note in `adept/README.md`(+`docs/.../tools` if any); any `github.com/.../ken` repo URL (PR-D). Everything else is a rename target.

### Task 2: Move `ken/` and restructure to the `khala` namespace

**Files:** Move `ken/` → `adept/`, then `adept/src/ken/` → `adept/src/khala/adept/`

- [ ] **Step 1: Move + namespace restructure**

```bash
git mv ken adept
mkdir -p adept/src/khala
git mv adept/src/ken adept/src/khala/adept
```
Confirm there is **no** `adept/src/khala/__init__.py` (PEP 420 implicit namespace); `adept/src/khala/adept/__init__.py` stays (regular sub-package).

- [ ] **Step 2: Convert `adept/pyproject.toml` (setuptools)**

- `name = "khala-adept"`; description updated.
- `[project.scripts]`: `adept = "khala.adept.cli:app"` (was `ken = "ken.cli:app"`).
- setuptools package discovery — use the **explicit** form (do NOT rely on namespace auto-discovery, which can ship an empty wheel): `[tool.setuptools] package-dir = {"" = "src"}` and `[tool.setuptools.packages] = ["khala.adept"]` (list every sub-package, or use `packages.find` with `namespaces = true`). **Critical (PR-A lesson):** the install must expose `khala.adept`, NOT a top-level `adept`.
- Update `[tool.pytest.ini_options]`/`pythonpath` if it referenced `ken` paths.
- **Verify by editable install, NOT just pytest** (local `pythonpath=["src"]` masks a packaging misconfig that only fails in CI): `pip install -e adept && python -c "import khala.adept; print('ok')" && (python -c "import adept" && echo "FAIL: top-level adept exists" || echo "ok: no top-level adept")`.

- [ ] **Step 3: Commit the structural move**

```bash
git add -A
git commit -m "refactor(adept): move ken/ → adept/src/khala/adept (namespace package)"
```

### Task 3: Rewrite ALL in-package `ken` identifiers

**Files:** `adept/src/khala/adept/*.py`, `adept/tests/*.py`, `adept/pyproject.toml`, `adept/docker-compose.yml`, `adept/db/*.sql`

- [ ] **Step 1: Case-insensitive discovery (match the gate)**

Run: `git grep -n -i -E "\bken\b|\bKEN_" -- adept/`
Classify: absolute imports; class/symbol names (grep `git grep -nE "class Ken|KenError|KenConfig"`); CLI name; env vars; DB identifiers; the Scots etymology (KEEP); the internal `probe.py` module (KEEP module name).

- [ ] **Step 2: Imports + CLI entry**

`from ken.<mod> import …` / `import ken.<mod>` → `khala.adept.<mod>`. Relative imports (`from .x`) untouched. The Typer app entry `ken.cli:app` is now `khala.adept.cli:app` (pyproject, Task 2). Update any `python -m ken…` → `python -m khala.adept…`.

- [ ] **Step 3: Classes/symbols → Adept (repo-wide callers)**

Rename any `KenConfig`/`KenError`/`Ken*` class or top-level symbol → `Adept*`, updating every reference (incl. `adept/tests/`, and `ken-web/api` callers handled in Chunk 2). Run `git grep -nE "\bKen[A-Za-z]+"` → expect zero after (outside historical).

- [ ] **Step 4: Env vars `KEN_*` → `ADEPT_*` (hard cutover)**

All nine: `KEN_AUTH`, `KEN_COOKIE_SECURE`, `KEN_DATABASE_URL`, `KEN_DATA_DIR`, `KEN_LEDGER`, `KEN_MANIFEST`, `KEN_N_QUESTIONS`, `KEN_QUESTIONS`, `KEN_TEST_DATABASE_URL` → `ADEPT_*`. No fallback read of the old name.

- [ ] **Step 5: DB identifiers (config-only, fresh DB)**

In `adept/docker-compose.yml` and `adept/db/init.sql`, flip **every** `ken` Postgres identifier together (a half-renamed compose breaks auth/healthcheck): `POSTGRES_DB: ken`→`adept`, `POSTGRES_USER: ken`→`adept`, `POSTGRES_PASSWORD: ken`→`adept`, the service/container name `ken-db`→`adept-db`, the volume `ken-db-data`→`adept-db-data`, the healthcheck `pg_isready -U ken -d ken`→`-U adept -d adept`, and the connection string `postgresql://ken:ken@…/ken` → `postgresql://adept:adept@…/adept` wherever it appears (compose comments, README handled in Chunk 3). No data migration (reprovisionable per spec).

- [ ] **Step 6: KEEP the internal `probe.py` module + Scots etymology**

Confirm `adept/src/khala/adept/probe.py` keeps its module name and that the only edits there are `ken`→`khala.adept` *import-path* changes (not the module name). Leave the etymology note in `adept/README.md` untouched.

- [ ] **Step 7: Run the core suite — green**

Run: `python -m pytest adept/tests -q` ; then `git grep -n -i -E "\bken\b|\bKEN_" -- adept/` → only the Scots etymology survives.
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(adept)!: rename all in-package ken identifiers → adept (imports, CLI, classes, KEN_* env, DB names)"
```

---

## Chunk 2: ken-web → adept-web (api + frontend)

### Task 4: Move ken-web → adept-web and rename the API package

**Files:** Move `ken-web/` → `adept-web/`; `adept-web/api/src/ken_web_api/` → `adept-web/api/src/khala/adept_web/`

- [ ] **Step 1: Move + namespace restructure (API)**

```bash
git mv ken-web adept-web
mkdir -p adept-web/api/src/khala
git mv adept-web/api/src/ken_web_api adept-web/api/src/khala/adept_web
```

- [ ] **Step 2: API `pyproject.toml` (incl. the core-package dependency)**

First run a discovery grep so nothing is missed: `git grep -n -i -E "\bken\b|\bKEN_|ken_web" -- adept-web/`. Then:
- `name = "khala-adept-web"`; `[project.scripts] adept-web-admin = "khala.adept_web.admin:main"` (was `ken-web-admin = "ken_web_api.admin:main"`); explicit setuptools discovery exposing `khala.adept_web` (same form as Task 2 Step 2).
- **The `ken` core dependency** (master-red if missed): `dependencies = ["ken", …]` → `["khala-adept", …]`, and `[tool.uv.sources] ken = { path = "../../ken", editable = true }` → `khala-adept = { path = "../../adept", editable = true }` (the dist name + the path both change). Update any comments naming these.
- Verify by editable install: `pip install -e adept -e adept-web/api && python -c "import khala.adept_web; print('ok')"`.

- [ ] **Step 3: Rewrite API imports**

`from ken_web_api.<mod> import …` → `from khala.adept_web.<mod> import …`. **Also** the API imports the core package: `from ken.<mod> import …` → `from khala.adept.<mod> import …` (cross-package; both renamed in this PR).

- [ ] **Step 4: API interface identifiers**

`KEN_*` env in the API → `ADEPT_*`; cookie `SESSION_COOKIE = "ken_session"` (`deps.py:42`) → `"adept_session"`; any `Ken*` class/symbol → `Adept*`; DB connection strings → `adept`.

- [ ] **Step 5: Run the API suite — green**

Run: `python -m pytest adept-web/api/tests -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(adept-web)!: rename ken-web-api → khala.adept_web (imports, CLI, cookie, env, DB)"
```

### Task 5: Rename the frontend to `@khala/adept-web`

**Files:** `adept-web/web/package.json`, `adept-web/web/src/**`, `adept-web/web/index.html`, vite/styles

- [ ] **Step 1: package.json + any ken identifiers**

`"name": "ken-web"` → `"@khala/adept-web"`. Then `git grep -n -i "\bken\b" -- adept-web/web/` and rewrite product-brand/identifier `ken` references in `src/api/client.ts`, `src/types.ts`, `src/styles.css`, `index.html`, components (e.g. `ken_session` reads, any `ken`-named var/route) → `adept`. Keep substrings like `token` intact.

- [ ] **Step 2: Run the frontend tests + build**

Run: `cd adept-web/web && npm test -- --run && npm run build; cd ../..`
Expected: tests pass, build succeeds.

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor(adept-web)!: rename frontend ken-web → @khala/adept-web"
```

---

## Chunk 3: Cross-refs, docs, manifest, and the gate

### Task 6: Manifest rename + root config + cross-refs

**Files:** Rename `ken.manifest.yaml` → `adept.manifest.yaml`; modify `.github/workflows/ci.yml`, `.gitignore`, `Taskfile.yml`, `ruff.toml`

- [ ] **Step 1: Manifest file rename + the env var that points to it**

```bash
git mv ken.manifest.yaml adept.manifest.yaml
```
The `ADEPT_MANIFEST` default path (renamed from `KEN_MANIFEST` in Task 3) must point to `adept.manifest.yaml`. Verify parse: `python -c "import yaml; yaml.safe_load(open('adept.manifest.yaml'))"`.

- [ ] **Step 2: CI workflow**

`.github/workflows/ci.yml`: the `ken`, `ken-web`, `ken-web-api` jobs → `adept`, `adept-web`, `adept-web-api`; `working-directory`/paths `ken/`→`adept/`, `ken-web/`→`adept-web/`; the Postgres service env (`POSTGRES_DB/USER: ken`→`adept`) and `KEN_*`/`ADEPT_*`; cache keys. Keep the matrix structure (each suite its own job).

- [ ] **Step 3: `.gitignore`, `Taskfile.yml`, `ruff.toml`**

Run `git grep -n -i "\bken\b" -- .gitignore Taskfile.yml ruff.toml` and repoint `ken`/`ken-web` paths → `adept`/`adept-web`.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "ci: rename ken→adept, ken-web→adept-web in CI/Taskfile/ruff/gitignore + manifest file"
```

### Task 7: Doc code-identifiers (READMEs, review-protocol)

**Files:** `adept/README.md`, `adept-web/README.md`, `adept/docs/review-protocol.md`

- [ ] **Step 1: Update kept code-identifiers**

In these docs, update the CLI/env/DB/path identifiers the doc-prose PR (#74/#76) kept: `ken …` CLI commands → `adept …`; `ken-web-admin` → `adept-web-admin`; `KEN_*` → `ADEPT_*`; `postgresql://ken:ken@…/ken` → `adept`; `ken_session` → `adept_session`; `ken/…`/`ken-web/…` paths → `adept/…`/`adept-web/…`; `ken.manifest.yaml` → `adept.manifest.yaml`. **KEEP** the Scots-etymology `ken` note and any `github.com/.../ken` repo URL (PR-D).

- [ ] **Step 2: Build docs (the site references nothing ken, but build catches asset breaks)**

Run: `npm --prefix docs run build`
Expected: build succeeds. (Adept has no docs-site tool page or diagram asset to rename.)

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "docs(adept): update kept code-identifiers ken→adept in READMEs + review-protocol"
```

### Task 8: Residual-grep gate + full verification + push

- [ ] **Step 1: Residual-grep gate — only legitimate survivors**

Run:
```bash
git grep -n -i -E "\bken\b|ken-web|ken_web|\bKEN_" -- ':!**/superpowers/**' ':!specs/**' ':!**/CHANGELOG.md' ':!**/dogfood*' ':!MIGRATION.md' ':!adr/**' ':!**/*.png'
```
Expected survivors only: the Scots-etymology `ken` note (`adept/README.md`), and any `github.com/.../ken` repo URL (PR-D). **Anything else is a straggler** — fix and re-run. Watch for false-positive substrings (`token`, `broken`) — those are fine and won't match `\bken\b`.

- [ ] **Step 2: No-shim assertion**

Run: `git grep -n -E "\bKEN_|\"ken\"|ken-web-admin|ken_session" -- ':!**/superpowers/**' ':!specs/**' ':!adr/**'`
Expected: zero — old env vars, CLI, cookie are gone, not aliased.

- [ ] **Step 3: Full matrix green (run suites individually — combined invocation hits a pre-existing basename collision)**

Run separately: `python -m pytest adept/tests -q`; `python -m pytest adept-web/api/tests -q`; `cd adept-web/web && npm test -- --run && npm run build; cd ../..`; `npm --prefix docs run build`. Also re-run the suites that could be affected: `python -m pytest nexus/tests -q`, the root `tests/`, and `arbiter/tests`. Note the hashing-parity test moved **with** ken to `adept/tests/test_hashing_parity.py`; it imports `khala.adept.hashing` (renamed in Task 3) **and** `khala.arbiter.hashing` (untouched, stays valid) — confirm it passes.
Expected: all green.

- [ ] **Step 4: Push + PR (controller does the merge after review + CI)**

```bash
git push -u origin rename/pr-b-adept
gh pr create --base master --title "refactor(adept)!: rename ken + ken-web → khala.adept + khala.adept_web (code, CLI, env, DB)" --body "PR-B of the component code-rename migration. Hard cutover: KEN_*→ADEPT_*, CLI ken→adept / ken-web-admin→adept-web-admin, cookie ken_session→adept_session, DB user/db ken→adept (config-only, reprovisionable). Namespace packages khala.adept / khala.adept_web; frontend @khala/adept-web. Adept-internal probe.py module name retained; Scots-etymology ken note kept; repo URL rename deferred to PR-D."
```

- [ ] **Step 5: Confirm CI green before merge** (hard cutover — no half-green merge).

---

## Done criteria for PR-B

- `adept/src/khala/adept/` + `adept-web/api/src/khala/adept_web/` + `adept-web/web/` (`@khala/adept-web`); `import khala.adept` / `import khala.adept_web` work; no top-level `adept`/`adept_web` packages; `import ken` fails.
- `ADEPT_*` env, `adept`/`adept-web-admin` CLIs, `adept_session` cookie, `adept`/`adept` Postgres in force; **no** `KEN_*` / `ken` CLI / `ken_session` outside historical records and (PR-D-deferred) repo URLs and the Scots etymology.
- Adept-internal `probe.py` intact; all suites + docs build + CI green.
- Next: plan **PR-C (Observer + Probe atomic swap)** against the updated `master`.
