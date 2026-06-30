---
title: Component code rename — khala namespace migration
status: design
date: 2026-06-30
related: ADR-0005
---

# Component code rename — `khala.*` namespace migration

## Context

[[ADR-0005]] renamed the ecosystem's components (specledger→Arbiter, mutqa→Probe,
ken→Adept, the review tool Probe→Observer) and was applied to **documentation prose**
across four merged PRs (#73–#76). A repo-wide audit (2026-06-30) confirmed the doc-prose
rename is complete; the only remaining old names are **code identifiers** (~1,140
occurrences: directories, packages, imports, CLI, env vars, MCP keys, DB strings, asset
filenames, repo URLs) and **historical records** (intentionally immutable).

This spec designs the **code identifier migration** — the second, deliberately-deferred
gate named in ADR-0005's out-of-scope. It does **not** touch historical records (accepted
ADRs, `**/superpowers/**`, `specs/**`, `**/CHANGELOG.md`, `**/dogfood*`, `MIGRATION.md`),
which retain old names by design.

## Decisions (settled in brainstorming)

1. **Scope: maximal.** Rename internal identifiers (dirs, packages, imports, modules)
   **and** the user-facing interface (env vars, CLI commands, MCP server keys) **and** the
   archived GitHub repos.
2. **Cutover: hard.** No compatibility shims/aliases. Old env vars, CLI names, MCP keys are
   removed immediately, not deprecated. Justified because the ecosystem is pre-launch; the
   one live consumer (PFPlay dogfood) is handed a migration note and updates config in lockstep.
3. **Sequencing: incremental, one component group per PR, fixed order A → B → C → D**
   (defined under "Migration units"). Each PR leaves `master` fully green (all tests + CI
   pass). No half-renamed intermediate state on `master`. The per-PR cross-reference lists
   below are the audit snapshot of *current* `master`; the residual-grep gate re-derives the
   actual reference set at execution time, so the lists stay valid even if `master` drifts.
4. **Namespace: `khala.*` namespace packages now.** Full ADR-0005 §4 compliance — Python
   tools become namespace packages under `khala.<tool>`; npm tools move to the `@khala/*`
   scope. This is the most invasive option (every import statement changes shape, not just
   the name) and is chosen deliberately for one-time correctness.

## Target identifier scheme

### Python tools → `src/khala/<tool>/` namespace layout

| Old package | New import | Dist name | New directory |
|---|---|---|---|
| `specledger` | `khala.arbiter` | `khala-arbiter` | `arbiter/src/khala/arbiter/` |
| `ken` | `khala.adept` | `khala-adept` | `adept/src/khala/adept/` |
| `mutqa` | `khala.probe` | `khala-probe` | `probe/src/khala/probe/` |
| `ken_web_api` | `khala.adept_web` | `khala-adept-web` | `adept-web/api/src/khala/adept_web/` |

Each `pyproject.toml` declares a namespace package (PEP 420 implicit namespace under
`khala/`, no `khala/__init__.py`), dist name `khala-<tool>`, and updated
`[project.scripts]` entry points.

### npm tools → `@khala/*` scope

| Old package | New package | New bins |
|---|---|---|
| `probe` (review analyzer, TS) | `@khala/observer` | `observer`, `observer-mcp` |
| `ken-web/web` (frontend) | `@khala/adept-web` | — |

### Interface identifiers (hard cutover)

| Surface | Old → New |
|---|---|
| Python CLI | `ken` → `adept`; `ken-web-admin` → `adept-web-admin` |
| npm bins | `probe`/`probe-mcp` → `observer`/`observer-mcp` |
| Env var prefixes | `SPECLEDGER_*` → `ARBITER_*`; `KEN_*` → `ADEPT_*`; `MUTQA_*` → `PROBE_*`; `PROBE_*` → `OBSERVER_*` |
| MCP server keys | `specledger` → `arbiter`; `probe` → `observer` |
| API-lint rule ids | `probe/<rule>` → `observer/<rule>` |
| Diagram asset files | `/diagrams/specledger.svg` → `arbiter.svg`; `probe.svg` → `observer.svg`; `mutqa.svg` → `probe.svg` |
| Archived GitHub repos | `specledger` → `arbiter`; `probe` → `observer`; (and `mutqa`/`ken` if present) → `probe`/`adept` |

## The Probe-name collision

"Probe" is reassigned: the **review** tool (TS, `probe/`) becomes **Observer**, while the
**mutation** tool (Python, `mutqa/`) **takes** the name **Probe**. At the filesystem and
package level this is a swap through a shared name (`probe`). It is therefore handled in a
**single atomic PR** (PR-C) so `master` never has two `probe/` directories or an ambiguous
`probe` package. Within PR-C the moves are ordered: `probe/`→`observer/` first, then
`mutqa/`→`probe/`.

## Migration units (one PR each, each leaves `master` green)

Each PR performs, for its component group: directory move → namespace-package restructure →
update **every** import → rename interface identifiers (env/CLI/MCP/bins) → update
**cross-references in other components** → update shared config → update the **doc code
identifiers that PR #73–#76 intentionally kept** (env vars, package names, module paths,
repo URLs, and the diagram asset filename + its `img src`) → rename the diagram asset file.

### PR-A — Arbiter (`specledger` → `khala.arbiter`)

- Move `specledger/` → `arbiter/`, restructure to `arbiter/src/khala/arbiter/`.
- Update all internal imports to `khala.arbiter`; `pyproject.toml` dist `khala-arbiter`.
- `SPECLEDGER_*` → `ARBITER_*`; MCP key `specledger` → `arbiter`; hook path.
- Cross-references (from audit): `nexus/nexus/a2a/external_ingest_skill.py`,
  `a2a/mapping.py`, `auth/principal.py`, `ingest/pipeline.py`, `web/js/doctype-signal.js`,
  `init.sql`, `nexus/tests/*`; `probe/src/nexus/types.ts`; `mutqa/tests/fixtures/*`;
  `ken.manifest.yaml`; root `Taskfile.yml`, `.github/workflows/ci.yml`, `ruff.toml`,
  `.gitignore`.
- Docs: `docs/src/content/docs/tools/arbiter.md` (+ko) code identifiers (`SPECLEDGER_DOCS`,
  `specledger.server`, MCP key, hook path) and `/diagrams/specledger.svg`
  → `/diagrams/arbiter.svg` (rename `docs/public/diagrams/specledger.svg` +
  `docs/src/diagrams/specledger.excalidraw`).
- Verify: Arbiter pytest + Nexus pytest (cross-ref) + full CI green.

### PR-B — Adept (`ken` + `ken-web` → `khala.adept` + `khala.adept_web`)

- Move `ken/`→`adept/` (`adept/src/khala/adept/`) and `ken-web/`→`adept-web/`
  (`adept-web/api/src/khala/adept_web/`, `adept-web/web/` npm `@khala/adept-web`).
- Update imports to `khala.adept` / `khala.adept_web`; dist `khala-adept` / `khala-adept-web`.
- CLI `ken`→`adept`, `ken-web-admin`→`adept-web-admin`; `KEN_*`→`ADEPT_*`.
- **DB identifiers**: `postgresql://ken:ken@…/ken`, `ken_session` cookie, DB user/name in
  `adept-web/api` config + `ken/docker-compose.yml` + `ken/db/init.sql`. See "Database
  migration" below.
- Cross-references: `ken.manifest.yaml`→`adept.manifest.yaml`; `nexus`/`ken` hashing-parity
  references; `Taskfile.yml`, `ci.yml` (ken job, 31 refs).
- Docs: `ken/README.md`, `ken-web/README.md`, `ken/docs/review-protocol.md` CLI/path
  identifiers; the Scots-etymology `ken` note stays (it explains the English word, not the
  identifier). Adept has no diagram asset to rename.
- Verify: Adept pytest + Adept-web api/web tests + CI green.

### PR-C — Observer + Probe atomic swap

- `probe/` (TS review tool) → `observer/`, npm `@khala/observer`, bins
  `observer`/`observer-mcp`, MCP key `observer`, rule ids `observer/*`, env `OBSERVER_*`,
  CI `probe.yml`→`observer.yml`, `.claude/` adapter references.
- `mutqa/` (Python mutation tool) → `probe/`, namespace `khala.probe`, dist `khala-probe`,
  imports `khala.probe`, `MUTQA_*`→`PROBE_*` (renamed **after** Observer's
  `PROBE_*`→`OBSERVER_*` above, mirroring the dir/asset ordering so the `PROBE_*` prefix is
  unambiguous mid-PR), the skill `name: mutqa`→`name: probe` (a user-facing
  invocation handle, renamed per Decision #1's interface cutover — this supersedes the
  doc-phase retention of `name: mutqa` in PR #74); its
  directory and package move; `mutqa-ledger.yaml`→`probe-ledger.yaml`. The mutation
  tool exposes **no MCP server** (it is a skill), so the `probe` MCP key freed by Observer is
  **retired, not reused**.
- Cross-references: `nexus` mentions of `probe`; `ken`'s own `probe.py` module is unrelated
  (Adept's internal "probe" — **not** renamed, it is Adept-internal vocabulary, confirmed by
  audit) and must be left intact.
- Docs: `observer.md`/`probe.md` (the mutation page) code identifiers; `/diagrams/probe.svg`
  →`observer.svg` and `/diagrams/mutqa.svg`→`probe.svg` — each `.svg` + `.excalidraw`
  source + `img src` move together, ordered to avoid the `probe.svg` filename collision:
  `probe.svg`→`observer.svg` **first**, then `mutqa.svg`→`probe.svg`.
- Verify: Observer vitest + Probe(mutation) pytest + both CI workflows green.

### PR-D — Archived GitHub repos (last, lowest-risk; in scope per Decision #1)

- Rename archived repos `specledger`→`arbiter`, `probe`→`observer` (and `mutqa`/`ken` if
  they exist) via `gh repo rename`. GitHub auto-redirects old URLs, so the doc source-repo
  links keep working. PR-D also updates **all** tool-doc source-repo URLs
  (`github.com/.../specledger`, `/ken`, `/probe`, `/mutqa` — deferred from PR-A/B/C) to the
  new repo names, in the **same** PR as the rename, so there is no broken-link window.
- No code impact; the live code is in the `khala` monorepo. Verify: links resolve.

## Database migration (PR-B detail)

Adept-web's Postgres uses `ken` as DB user and database name and `ken_session` as the
auth-cookie name. Two cases:

- **Fresh/dogfood DB (expected):** no data migration — the rename is purely config
  (`docker-compose.yml`, `init.sql`, connection strings, env). A fresh `adept`/`adept` DB is
  created on next `task up`.
- **Existing populated DB:** out of scope for this spec — if a live Adept-web DB holds real
  vouch data, a separate `ALTER … RENAME` / dump-restore step is required and must be
  designed before PR-B runs. The spec assumes the dogfood DB is reprovisionable; if not,
  PR-B is gated on a data-migration sub-spec.

## Verification strategy

- **Per PR:** run the renamed component's full test suite **and** every cross-referencing
  component's suite (enumerated per PR above) locally; push and confirm the full CI matrix
  is green before merge. Hard cutover means a red intermediate is a blocker, not a step.
- **Residual grep gate (component-specific):** after each PR, a repo-wide grep (excluding
  historical records) for that component's old identifiers must return **zero**
  non-historical hits. PR-A (`specledger`) and the mutation half of PR-C (`mutqa`) are plain
  greps. **PR-B (`\bken\b`) is a carve-out:** the Scots-etymology `ken` note is deliberately
  retained (it explains the English word, not the identifier), so PR-B's gate is zero
  `\bken\b` *except* that etymology note in `adept/README.md` / `adept.md`(+ko); every
  surviving `ken` must resolve to the etymology prose.
  - **Repo-URL survivors (all of PR-A/B/C):** old GitHub source-repo URLs
    (`github.com/LivingLikeKrillin/<oldname>`) are **expected** survivors until PR-D renames
    the repos and updates the URLs; they are excluded from each tool's gate until then.
  - **Observer (review-tool half of PR-C) is a special case:** the bare string `probe` is
    **legitimately reintroduced** in the same PR (the mutation tool becomes `probe/`, dist
    `khala-probe`, `khala.probe`, `probe-ledger.yaml`) and Adept retains its internal
    `probe.py`. So the Observer gate is **not** "grep `probe` → zero". It is zero hits for the
    *review-tool-specific* artifacts only: the npm bins `probe`/`probe-mcp`, the `probe/<rule>`
    lint-rule ids, the MCP key `probe`, the `probe/src/...` (TypeScript review-tool) paths,
    and the `probe.yml` CI workflow. Every surviving bare `probe` after PR-C must resolve to
    the new mutation tool (`khala.probe` / `probe/` Python) or Adept-internal `probe.py`.
- **No-shim assertion:** grep confirms the old env var / CLI / MCP key names are gone (not
  aliased), per the hard-cutover decision.

## Out of scope

- Historical records (accepted ADRs, `**/superpowers/**` except this spec, `specs/**`,
  CHANGELOGs, dogfood logs, `MIGRATION.md`) — retain old names by design.
- Compatibility shims / deprecation aliases — explicitly rejected (hard cutover).
- Populated-DB data migration (only triggered if the dogfood DB is non-reprovisionable; then
  a separate sub-spec).
- Adept's internal `probe.py` module (Adept-internal vocabulary, unrelated to the Probe tool).
- Publishing to PyPI/npm — the `khala-*` / `@khala/*` names are reserved by this layout but
  publishing is a later, separate effort.

## Risks

- **Cross-cutting blast radius.** Each PR edits files in multiple components + shared config;
  a missed reference breaks an unrelated component's CI. Mitigated by the per-PR cross-ref
  enumeration (from the audit) + the residual-grep gate.
- **PR-C is highest risk:** a name swap through `probe` plus two namespace restructures in
  one atomic PR. Mitigated by ordered moves and running both suites before merge.
- **Namespace restructure changes every import's shape**, not just its text — higher chance
  of stragglers than a flat rename. Mitigated by the residual-grep gate and CI.
- **Hard cutover breaks the PFPlay dogfood** the moment a PR merges. Mitigated by a migration
  note (new env/CLI/MCP names) handed to the team, and by sequencing so they update one tool
  at a time.
