# khala three-debts Reframe — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land `adr/ADR-0002` that reframes khala around "stay in command of your own system in the AI era," map the three AI-era debts onto khala modules, name cognitive debt as the empty leg, and reflect the chosen identity line in README + docs — shipping zero new product code.

**Architecture:** A documentation/positioning deliverable. ADR-0002 is hand-authored following ADR-0001's exact precedent (frontmatter convention + a dry-run accountable-review log), because specledger's MCP server is disabled in-session (`.claude/settings.local.json`) and the PreToolUse gate is not wired (no blocking on `adr/`). The accountable review is dogfooded via an adversarial critic subagent run against specledger's real rubric. The `content_hash` is stamped using specledger's actual `content_hash()` algorithm so the stamp is genuine.

**Tech Stack:** Markdown + YAML frontmatter; Python (only to compute the content hash via `specledger.hashing`/`specledger.frontmatter`); git.

**Source spec:** `docs/superpowers/specs/2026-06-23-khala-debt-reframe-design.md`

---

## Chunk 1: ADR authoring, critique, stamp, reflection

### Task 1: Author ADR-0002 body + frontmatter (status: proposed)

**Files:**
- Create: `adr/ADR-0002-reframe-system-command-debt.md`

**Frontmatter convention** (match ADR-0001 key order exactly; `render()` preserves insertion order):
```yaml
---
id: ADR-0002
type: adr
title: <final title>
status: proposed          # becomes 'accepted' at stamp time (Task 4)
date: 2026-06-23
tags: [identity, debt, ai-era, ecosystem, reframe]
linked_adrs: [ADR-0001]
# approved_by / reviewed_at / content_hash added at Task 4
---
```

**Body sections** (from design spec §2–§9):
1. `## Status` — Proposed (mirror ADR-0001's prose style).
2. `## Context — 전환 (왜 지금)` — AI as producer; the three debts (Fowler) + 하용호 J-curve / Verification Tax; cite keynote as reference, do NOT embed the PDF.
3. `## Decision — Mission` — present 2–3 tagline candidates, pick ONE as the committed identity line (recommend "AI가 짓고, 당신이 이해한다 / AI builds it. You understand it."). State framing: positive mission, debts = enemy, khala = the debt-servicing window; explicitly note nexus retrieval is NOT demoted.
4. `## The enemy — three debts ↔ modules` — the grounded mapping table (technical→mutqa+probe; intent→specledger `content_hash`+critique→approve gate; cognitive→EMPTY). Every cell checkable against code.
5. `## The empty leg — cognitive debt` — definition, why no window exists, why it is the mission's center; name direction only ("이해도/장악도 계측"), no design.
6. `## Principles, re-placed` — grounded-answers / "system decides, LLM narrates" / default-deny / demand-pull, each subordinated to the mission.
7. `## Taste = subtraction (self-discipline)` — zero new code; features signal-gated.
8. `## Follow-on backlog (gated — not designed here)` — the 3 directions + gate signals table; first consumer = khala dogfooding.
9. `## Consequences` — what changes (README/docs identity), what does not (no code, no schema), reversibility.

- [ ] **Step 1:** Write the file with frontmatter (no hash yet) + all 9 sections.
- [ ] **Step 2:** Re-read for internal consistency with the design spec; confirm no TODO/placeholder.

### Task 2: Dogfood the accountable review (critique subagent)

- [ ] **Step 1:** Dispatch an adversarial critic subagent. Give it ONLY the ADR-0002 body + ADR-0001 body (for `adr-contradiction` checks) + specledger's exact rubric: `risky-assumption, missing-invariant, unverifiable-claim, scope-creep, adr-contradiction, undefined, untestable-requirement`. Ask for issues as `(category, severity, description)`.
- [ ] **Step 2:** Triage returned issues into dispositions (accepted / deferred / rejected) with one-line reasons. Apply body fixes for every `accepted` issue.
- [ ] **Step 3:** Append a `## Review log (dry-run, 2026-06-23)` section to the ADR (same shape as ADR-0001's): the issue table with dispositions + the note that the canonical specledger `critique`→`approve` run is pending MCP registration.

### Task 3: (folded into Task 2) — final tagline locked in the Decision section

- [ ] Confirm the Decision section commits to exactly one identity line; the others remain listed as considered-and-rejected alternatives.

### Task 4: Stamp the frontmatter with a genuine content_hash

**Files:**
- Modify: `adr/ADR-0002-reframe-system-command-debt.md` (frontmatter)

- [ ] **Step 1:** Set `status: accepted`, add `approved_by: LivingLikeKrillin`, `reviewed_at: '2026-06-23T...Z'` (ISO 8601 UTC).
- [ ] **Step 2:** Compute the hash using specledger's real code (guarantees a stamp specledger would reproduce):

```bash
cd "C:/Users/Eisen/Desktop/Labs/[projects] khala"
python -c "import sys; sys.path.insert(0,'specledger/src'); from specledger.frontmatter import split; from specledger.hashing import content_hash; t=open('adr/ADR-0002-reframe-system-command-debt.md',encoding='utf-8').read(); meta,body=split(t); print(content_hash(body))"
```
Expected: `sha256:<64-hex>`

- [ ] **Step 3:** Write the printed value into the `content_hash:` frontmatter field.
- [ ] **Step 4 (verify):** Re-run the command and confirm the printed hash equals the stamped value (body unchanged since stamping). If it differs, the body was edited after stamping — re-stamp.

### Task 5: Reflect the identity in README + docs (additive, reversible)

**Files:**
- Modify: `README.md` — add the mission tagline + a short three-debts/third-leg framing. KEEP the existing "two failure modes" spine (it maps: "the human stops judging" == cognitive debt). Do not delete existing copy.
- Modify: `docs/src/content/docs/index.mdx` (EN hero/description) — weave in the mission line additively.
- Modify: `docs/src/content/docs/ko/index.mdx` (KO hero/description) — same, in Korean.
- Modify: `adr/README.md` — add the ADR-0002 row to the Index table.

- [ ] **Step 1:** Edit README.md (additive).
- [ ] **Step 2:** Edit EN + KO docs landing (additive, parallel wording).
- [ ] **Step 3:** Add ADR-0002 to `adr/README.md` index table (status: accepted, date 2026-06-23).
- [ ] **Step 4 (verify):** `git diff --stat` shows only the 4 files + the ADR; no source/code files touched.

### Task 6: Commit + PR

- [ ] **Step 1:** `git add -A && git commit` (conventional message; co-author trailer).
- [ ] **Step 2:** `git push -u origin docs/adr-0002-debt-reframe`.
- [ ] **Step 3:** `gh pr create` targeting master with a body summarizing the reframe, the grounded mapping, and the zero-code / signal-gated discipline. Include the 🤖 Generated-with trailer.
- [ ] **Step 4 (verify):** PR created; report the URL.

---

## Notes / discipline
- No product code, schema, endpoint, or skill. Only ADR + README + docs landing + adr index.
- The comprehension meter / quiz is NOT designed here (separate signal-gated session).
- PDF original is not committed; cited as a keynote reference only.
- The PR is the human review gate (user reviews before merge).
