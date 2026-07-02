---
title: Observer
description: Platform-aware PR analyzer and API contract validator; grounds review in cohesion, backward compatibility, and org guidelines.
---

Observer grounds the review of a change in context a reviewer would otherwise have to hold in their head. It's a **platform-aware PR analyzer and API contract validator** that turns three recurring review questions into deterministic checks:

1. **Is this PR's scope appropriate?** The same seven files can be one cohesive change in Spring Boot and three separate concerns in Next.js. Judging by file count misfires; Observer judges by *logical cohesion* against a platform profile.
2. **Is this API change backward-compatible?** Missing nullable flags, inconsistent error responses, and breaking changes slip past review. Observer lints the spec and diffs it against the base.
3. **Does this change conform to org guidelines?** Even with written guidelines, a reviewer can't recall and cross-check them every time. Observer infers the PR type and generates the matching checklist — and, when Nexus is connected, attaches the relevant rules and impact.

One principle runs through all of it: **when everything is fine, Observer says nothing.** Noise kills trust. When it does warn, it proposes how to split the change.

In short: it keeps PR review honest by grounding scope, contracts, and conformance. It's richer with Nexus connected, but works fully without it.

<svg class="kh-fig" viewBox="0 0 560 220" role="img" aria-label="Observer assigns roles to a 3-file change — api (routes/pay.py, schemas/pay.py) and data (models/ledger.py) — finds two roles mixed, and proposes splitting into PR-a (api) and PR-b (data) with merge order preserved.">
<defs><marker id="ob-a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="kh-fig-ah" d="M0 0 L10 5 L0 10 z"/></marker></defs>
<rect class="kh-fig-panel" x="24" y="28" width="284" height="168" rx="8"/>
<text class="kh-fig-h" x="42" y="52">SCOPE · 3 FILES</text>
<line class="kh-fig-rule" x1="42" y1="64" x2="290" y2="64"/>
<text class="kh-fig-h" x="42" y="88">API</text>
<text class="kh-fig-d" x="88" y="88">routes/pay.py</text>
<text class="kh-fig-d" x="88" y="108">schemas/pay.py</text>
<text class="kh-fig-h" x="42" y="140">DATA</text>
<text class="kh-fig-d" x="88" y="140">models/ledger.py</text>
<text class="kh-fig-s" x="42" y="176">cohesion scored · roles matched</text>
<path class="kh-fig-line-acc" d="M308 112 L334 112" marker-end="url(#ob-a)"/>
<rect class="kh-fig-panel" x="334" y="28" width="202" height="168" rx="8"/>
<text class="kh-fig-h" x="352" y="52">VERDICT</text>
<line class="kh-fig-rule" x1="352" y1="64" x2="518" y2="64"/>
<text class="kh-fig-ans" x="352" y="92">mixed · 2 roles</text>
<text class="kh-fig-d" x="352" y="122">propose split</text>
<text class="kh-fig-d" x="352" y="146">› PR-a  api</text>
<text class="kh-fig-d" x="352" y="166">› PR-b  data</text>
<text class="kh-fig-s" x="352" y="186">merge order preserved</text>
</svg>

## Core concepts

- **Platform profile.** A mapping from file patterns to roles, per framework (Spring Boot, Next.js, React SPA). Roles compose into **cohesion groups** — e.g. Spring Boot `domain-crud` = entity + repository + service + controller + dto + mapper + exception + test.
- **Scope analysis.** Changed files are assigned roles, matched to cohesion groups, scored for severity, and — if concerns are mixed — a split is proposed with a suggested merge order.
- **Concern drift.** As you edit, Observer watches for files belonging to a *different* concern than the current change and warns immediately.
- **API lint + diff.** Ten built-in rules (`observer/nullable`, `observer/error-response`, `observer/path-naming`, `observer/field-naming`, `observer/pagination`, and more) check the spec; the differ detects breaking changes against a base.
- **PR type → checklist.** Ten PR types (`domain-crud`, `api-change`, `ui-feature`, `config-change`, `db-migration`, `test-only`, `docs-only`, …) each map to a review checklist; passing checks are auto-verified.
- **Nexus is optional.** Without it, every feature still works; with it, results gain related guidelines, service impact, and design-observation gaps.

## Quickstart

Observer is a TypeScript / Node ≥ 20 package; pnpm is the package manager. CLI invoked via `observer`. Commands transcribed from the source repo README and `package.json`.

### Install

```bash
pnpm add -D @khala/observer
```

### Core commands

```bash
# PR scope analysis + review checklist
observer check

# API spec lint (10 built-in rules)
observer api:lint api/openapi.json

# API spec diff (breaking-change detection)
observer api:diff --base origin/main

# Generate a review checklist
observer review
```

### Output formats

```bash
observer check                  # markdown (default)
observer check --format json    # JSON (for agents / pipelines)
observer check --format brief   # one-line summary (CI)
observer check --silent         # no output when clean
```

If everything is in scope, `observer check` says nothing.

## How-to

### Check PR scope before opening it

```bash
observer check
```

Analyzes changed files against the platform profile; if concerns are mixed, it proposes a split. Stays silent when the change is cohesive.

### Validate an API change

```bash
observer api:lint api/openapi.json     # spec self-check (nullable, naming, …)
observer api:diff --base origin/main   # detect breaking changes vs. main
```

### Run inside Claude Code via MCP

Register Observer's MCP server so Claude Code calls scope analysis, API lint, and checklist generation automatically from conversation context. The bin `observer-mcp` maps to `dist/mcp/server.js`:

```json
// .mcp.json
{
  "mcpServers": {
    "observer": {
      "command": "node",
      "args": ["dist/mcp/server.js"],
      "cwd": "."
    }
  }
}
```

The MCP server exposes eight tools, including `observer.analyzeScope`, `observer.lintApiSpec`, `observer.diffApiSpecs`, `observer.reviewChecklist`, `observer.detectPlatform`, `observer.queryNexus`, `observer.groundTroubleshooting`, and `observer.groundReview`.

### Gate scope in CI (GitHub Actions)

```yaml
- run: observer check --base origin/main --format brief --silent
```

## Reference

- Source: [`observer/` in the Khala monorepo](https://github.com/LivingLikeKrillin/khala/tree/master/observer) (`README.md`).
- Per-version scope docs live under the repo's `docs/` (`probe-v{N}-scope.md`); guideline docs under `docs/guidelines/`.
- Build/test scripts (`pnpm build`, `pnpm test:run`, `pnpm typecheck`) are in `package.json`.

:::note[Last verified]
Source repo README (site re-run verification pending).
:::
