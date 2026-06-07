---
title: Archon
description: Domain truth governance — the authority window over your invariants and values, answered from code with calibrated honesty.
---

:::caution[Status]
Archon currently lives as a branch (`spec/domain-invariant-governance`) and the `claims` package inside the Khala/Nexus repo. Paths below reference that.
:::

## Overview

Archon is the authority window over domain truth. It is the single place a person or an agent goes to ask "what is true here, and on whose authority?" — and get an answer grounded in a governed source, with its freshness and confidence stated plainly.

The problem it calibrates: planners (non-engineers) constantly touch the system's preconditions in meetings — limits, policies, invariants — but have no fast way to confirm the *current* value. They corner an engineer, or trust a possibly-stale Notion page, and decisions pile up on wrong premises. Archon's answer is not "always correct" (impossible) but **calibrated**: it never dresses a soft or stale answer up as a hard one. It reads the value from the authoritative source (a code constant) at query time, so it cannot go stale; what it knows it asserts, what it does not it declines to assert.

One-line identity: **domain value / invariant / authority governance, built as a Khala/Nexus extension** — the defense against the failure mode where the machine confidently invents the meaning of your own business rules.

## Core concepts

- **Concepts are the spine; facts hang off them.** A registry of terms / actors / objects (ubiquitous language) is the foundation. Values, invariants, and requirements are *claims* that reference those concepts.
- **Claim.** A new resource kind. Its `kind` distinguishes `goal | invariant | requirement`; value-bearing claims carry a `value` that points at a `value_source` (e.g. a `code_constant`).
- **Reliability = calibration (honesty).** The achievable, sufficient definition of trust: the system never lies — it does not present a soft or stale answer as a hard one. (This is precisely what Notion cannot do.)
- **Point, don't copy (anti-shelfware).** Values are never copied into storage where they rot. A claim *points* at the authoritative source and reads the current value on demand, tagging freshness.
- **Claim ↔ code drift.** Each code symbol is hashed by (file path + symbol name); when the hash changes after a claim's last-verified commit, the claim is flagged (e.g. `claim_code_drift`).
- **System decides, LLM narrates.** (Inherited from Nexus.) Classification, verification, and routing are deterministic code; the LLM only proposes and summarizes — never final authority.

## Quickstart

Archon ships inside the Khala repo on the `spec/domain-invariant-governance` branch; the implementation is the `khala/claims/` package. It reuses the Nexus stack (PostgreSQL). The code-value resolver reads constants from a target repo set via `config.yaml` → `code_source.repo_path`. Commands transcribed from the branch's `khala/cli.py`.

### 1. Check out the branch

```bash
git clone https://github.com/LivingLikeKrillin/khala.git
cd khala
git checkout spec/domain-invariant-governance
```

Bring up the stack as for Nexus (`docker compose up -d`), and set `code_source.repo_path` in `config.yaml` to the codebase whose constants you want Archon to read.

### 2. Seed your domain claims

`claims.yaml` defines invariants/values, each pointing at a `value_source` (a code constant). Seeding snapshots the current code hash of each source.

```bash
khala claim-seed claims.yaml
```

(Note: the top-level `claims.yaml` shipped in the repo is a seed example, not the package.)

### 3. Ask for a current value

```bash
khala claim-value 준회원
```

Archon reads the value from the code constant at query time and answers with confidence + freshness — asserting the certain, declining on the unknown.

## How-to

### Look up a domain value

```bash
khala claim-value 준회원        # e.g. "associate member max playlists?"
khala claim-value 재생곡        # play-track limit, etc.
```

Returns the current value with a calibrated label: high-confidence when read cleanly from the code constant, an honest "couldn't verify" otherwise, and a drift warning if the source changed since last verified.

### Derive grade / role authority (emergent questions)

```bash
khala grade-authority --enum GradeType
khala grade-authority --enum GradeType --subpath some/scope
```

Extracts permission gates from code (via free tree-sitter AST, no CodeQL) and derives, by complement, which actions each grade is blocked from. Fixed-gate complements are reported as certain (high); "action-guard vs filter" semantics are flagged as needing confirmation (medium) — honestly distinguished.

### Query from an AI agent (MCP)

Archon exposes MCP tools so agents answer domain questions from the governed source instead of guessing:

- `archon_claim_value(concept, tenant, classification_max)` — current value of a concept's invariant/value.
- `archon_grade_authority(grade, enum_name, subpath)` — emergent/complement authority questions ("what can CLUBBER do?").

## Reference

- Branch: `spec/domain-invariant-governance` of [github.com/LivingLikeKrillin/khala](https://github.com/LivingLikeKrillin/khala).
- Package: `khala/claims/` (`seed.py`, `value_query.py`, `grade_authority.py`, `answer.py`, `repository.py`). CLI in `khala/cli.py`; MCP tools in `khala/mcp/server.py`.
- Design & plan docs: `docs/superpowers/specs/2026-06-06-domain-invariant-governance-design.md`, `docs/superpowers/specs/2026-06-06-value-validation-protocol.md`, and `docs/superpowers/plans/2026-06-06-domain-invariant-mvp-value-query.md`.

:::note[Last verified]
Transcribed from the `spec/domain-invariant-governance` branch (`khala/cli.py`, `khala/mcp/server.py`, design specs). Site re-run verification pending.
:::
