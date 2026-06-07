---
title: Probe
description: Platform-aware PR analyzer + API contract validator — grounds code review in platform cohesion, backward compatibility, and org guidelines.
---

Probe grounds the review of a change in context the reviewer would otherwise have to hold in their head. It is a **platform-aware PR analyzer + API contract validator** that turns three recurring review questions into deterministic checks:

1. **Is this PR's scope appropriate?** The same seven files can be one cohesive change in Spring Boot and three separate concerns in Next.js. Judging by file count misfires; Probe judges by *logical cohesion* against a platform profile.
2. **Is this API change backward-compatible?** Missing nullable flags, inconsistent error responses, and breaking changes slip past review. Probe lints the spec and diffs it against the base.
3. **Does this change conform to org guidelines?** Even with written guidelines, a reviewer can't recall and cross-check them every time. Probe infers the PR type and generates the matching checklist — and, when Nexus is connected, attaches the relevant rules and impact.

A design principle runs through all of it: **when everything is fine, Probe says nothing.** Noise kills trust. When it does warn, it proposes how to split.

One-line identity: the tool that keeps PR review honest by grounding scope, contracts, and conformance — optionally enriched by Nexus, but fully functional without it.

## Core concepts

- **Platform profile.** A mapping from file patterns to roles, per framework (Spring Boot, Next.js, React SPA). Roles compose into **cohesion groups** — e.g. Spring Boot `domain-crud` = entity + repository + service + controller + dto + mapper + exception + test.
- **Scope analysis.** Changed files are assigned roles, matched to cohesion groups, scored for severity, and — if concerns are mixed — a split is proposed with a suggested merge order.
- **Concern drift.** As you edit, Probe watches for files belonging to a *different* concern than the current change and warns immediately.
- **API lint + diff.** Ten built-in rules (`probe/nullable`, `probe/error-response`, `probe/path-naming`, `probe/field-naming`, `probe/pagination`, and more) check the spec; the differ detects breaking changes against a base.
- **PR type → checklist.** Ten PR types (`domain-crud`, `api-change`, `ui-feature`, `config-change`, `db-migration`, `test-only`, `docs-only`, …) each map to a review checklist; passing checks are auto-verified.
- **Khala (Nexus) is optional.** Without it, every feature still works; with it, results gain related guidelines, service impact, and design-observation gaps.

## Quickstart

Probe is a TypeScript / Node ≥ 20 package; pnpm is the package manager. CLI invoked via `npx probe`. Commands transcribed from the source repo README and `package.json`.

### Install

```bash
pnpm add -D probe
```

### Core commands

```bash
# PR scope analysis + review checklist
npx probe check

# API spec lint (10 built-in rules)
npx probe api:lint api/openapi.json

# API spec diff (breaking-change detection)
npx probe api:diff --base origin/main

# Generate a review checklist
npx probe review
```

### Output formats

```bash
npx probe check                  # markdown (default)
npx probe check --format json    # JSON (for agents / pipelines)
npx probe check --format brief   # one-line summary (CI)
npx probe check --silent         # no output when clean
```

If everything is in scope, `probe check` says nothing.

## How-to

### Check PR scope before opening it

```bash
npx probe check
```

Analyzes changed files against the platform profile; if concerns are mixed, it proposes a split. Stays silent when the change is cohesive.

### Validate an API change

```bash
npx probe api:lint api/openapi.json     # spec self-check (nullable, naming, …)
npx probe api:diff --base origin/main   # detect breaking changes vs. main
```

### Run inside Claude Code via MCP

Register Probe's MCP server so Claude Code calls scope analysis, API lint, and checklist generation automatically from conversation context. The bin `probe-mcp` maps to `dist/mcp/server.js`:

```json
// .mcp.json
{
  "mcpServers": {
    "probe": {
      "command": "node",
      "args": ["dist/mcp/server.js"],
      "cwd": "."
    }
  }
}
```

The MCP server exposes eight tools, including `probe.analyzeScope`, `probe.lintApiSpec`, `probe.diffApiSpecs`, `probe.reviewChecklist`, `probe.detectPlatform`, `probe.queryKhala`, `probe.groundTroubleshooting`, and `probe.groundReview`.

### Gate scope in CI (GitHub Actions)

```yaml
- run: npx probe check --base origin/main --format brief --silent
```

## Reference

- Source repo README: [github.com/LivingLikeKrillin/probe](https://github.com/LivingLikeKrillin/probe) (`README.md`).
- Per-version scope docs live under the repo's `docs/` (`probe-v{N}-scope.md`); guideline docs under `docs/guidelines/`.
- Build/test scripts (`pnpm build`, `pnpm test:run`, `pnpm typecheck`) are in `package.json`.

:::note[Last verified]
Source repo README (site re-run verification pending).
:::
