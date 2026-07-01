---
title: Archon
description: Domain truth governance — the authority window over your invariants and values, answered from code with calibrated honesty.
---

:::caution[Status]
Archon currently lives as a branch (`spec/domain-invariant-governance`) and the `claims` package inside the Nexus repo. Paths below reference that.
:::

Archon is the authority window over domain truth — the single place a person or an agent goes to ask "what is true here, and on whose authority?" and get an answer grounded in a governed source, with its freshness and confidence stated plainly.

The problem it calibrates: planners (non-engineers) constantly touch the system's preconditions in meetings — limits, policies, invariants — but have no fast way to confirm the *current* value. They corner an engineer, or trust a possibly-stale Notion page, and decisions pile up on wrong premises. Archon's answer is not "always correct" (impossible) but **calibrated**: it never dresses a soft or stale answer up as a hard one. It reads the value from the authoritative source (a code constant) at query time, so it cannot go stale; what it knows it asserts, what it does not it declines to assert.

One-line identity: **domain value / invariant / authority governance, built as a Nexus extension** — the defense against the failure mode where the machine confidently invents the meaning of your own business rules.

<svg class="kh-fig" viewBox="0 0 560 210" role="img" aria-label="Archon reads the code constant config/limits.py:12 (MAX_RETRIES = 5) at query time and verifies its content-hash matches the approved hash, returning a calibrated, cited answer: MAX_RETRIES = 5.">
<defs><marker id="ar-a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="kh-fig-ah" d="M0 0 L10 5 L0 10 z"/></marker></defs>
<text class="kh-fig-q" x="24" y="22">› max retry limit?</text>
<rect class="kh-fig-panel" x="24" y="36" width="250" height="150" rx="8"/>
<text class="kh-fig-h" x="42" y="60">READ CONSTANT</text>
<line class="kh-fig-rule" x1="42" y1="72" x2="256" y2="72"/>
<text class="kh-fig-d" x="42" y="94">config/limits.py:12</text>
<text class="kh-fig-ans" x="42" y="120">MAX_RETRIES = 5</text>
<text class="kh-fig-s" x="42" y="146">content-hash 3f9a2c</text>
<text class="kh-fig-verified" x="42" y="168">✓ matches approved</text>
<path class="kh-fig-line-acc" d="M274 111 L300 111" marker-end="url(#ar-a)"/>
<rect class="kh-fig-panel" x="300" y="36" width="236" height="150" rx="8"/>
<text class="kh-fig-h" x="318" y="60">GROUNDED ANSWER</text>
<line class="kh-fig-rule" x1="318" y1="72" x2="518" y2="72"/>
<text class="kh-fig-ans" x="318" y="98">MAX_RETRIES = 5</text>
<text class="kh-fig-d" x="318" y="124">→ config/limits.py:12</text>
<text class="kh-fig-s" x="318" y="148">read at query time · calibrated</text>
<text class="kh-fig-verified" x="318" y="170">✓ VERIFIED · no drift</text>
</svg>

## Core concepts

- **Concepts are the spine; facts hang off them.** A registry of terms / actors / objects (ubiquitous language) is the foundation. Values, invariants, and requirements are *claims* that reference those concepts.
- **Claim.** A new resource kind. Its `kind` distinguishes `goal | invariant | requirement`; value-bearing claims carry a `value` that points at a `value_source` (e.g. a `code_constant`).
- **Reliability = calibration (honesty).** The achievable, sufficient definition of trust: the system never lies — it does not present a soft or stale answer as a hard one. (This is precisely what Notion cannot do.)
- **Point, don't copy (anti-shelfware).** Values are never copied into storage where they rot. A claim *points* at the authoritative source and reads the current value on demand, tagging freshness.
- **Claim ↔ code drift.** Each code symbol is hashed by (file path + symbol name); when the hash changes after a claim's last-verified commit, the claim is flagged (e.g. `claim_code_drift`).
- **System decides, LLM narrates.** (Inherited from Nexus.) Classification, verification, and routing are deterministic code; the LLM only proposes and summarizes — never final authority.

## Quickstart

Archon ships inside the Nexus repo on the `spec/domain-invariant-governance` branch; the implementation is the `nexus/claims/` package. It reuses the Nexus stack (PostgreSQL). The code-value resolver reads constants from a target repo set via `config.yaml` → `code_source.repo_path`. Commands transcribed from the branch's `nexus/cli.py`.

### 1. Check out the branch

```bash
git clone https://github.com/LivingLikeKrillin/khala.git nexus
cd nexus
git checkout spec/domain-invariant-governance
```

Bring up the stack as for Nexus (`docker compose up -d`), and set `code_source.repo_path` in `config.yaml` to the codebase whose constants you want Archon to read.

### 2. Seed your domain claims

`claims.yaml` defines invariants/values, each pointing at a `value_source` (a code constant). Seeding snapshots the current code hash of each source.

```bash
nexus claim-seed claims.yaml
```

(Note: the top-level `claims.yaml` shipped in the repo is a seed example, not the package.)

### 3. Ask for a current value

```bash
nexus claim-value Basic
```

Archon reads the value from the code constant at query time and answers with confidence + freshness — asserting the certain, declining on the unknown.

## How-to

### Look up a domain value

```bash
nexus claim-value Basic        # e.g. "basic tier max projects?"
nexus claim-value 작업          # task limit, etc.
```

Returns the current value with a calibrated label: high-confidence when read cleanly from the code constant, an honest "couldn't verify" otherwise, and a drift warning if the source changed since last verified.

### Derive grade / role authority (emergent questions)

```bash
nexus grade-authority --enum GradeType
nexus grade-authority --enum GradeType --subpath some/scope
```

Extracts permission gates from code (via free tree-sitter AST, no CodeQL) and derives, by complement, which actions each grade is blocked from. Fixed-gate complements are reported as certain (high); "action-guard vs filter" semantics are flagged as needing confirmation (medium) — honestly distinguished.

### Query from an AI agent (MCP)

Archon exposes MCP tools so agents answer domain questions from the governed source instead of guessing:

- `archon_claim_value(concept, tenant, classification_max)` — current value of a concept's invariant/value.
- `archon_grade_authority(grade, enum_name, subpath)` — emergent/complement authority questions ("what can MEMBER do?").

## Reference

- Branch: `spec/domain-invariant-governance` of [github.com/LivingLikeKrillin/khala](https://github.com/LivingLikeKrillin/khala).
- Package: `nexus/claims/` (`seed.py`, `value_query.py`, `grade_authority.py`, `answer.py`, `repository.py`). CLI in `nexus/cli.py`; MCP tools in `nexus/mcp/server.py`.

:::note[Last verified]
Transcribed from the `spec/domain-invariant-governance` branch (`nexus/cli.py`, `nexus/mcp/server.py`, design specs). Site re-run verification pending.
:::
