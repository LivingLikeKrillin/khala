# Design Spec — `ken`: the cognitive-debt meter (v0, active vouch core)

- **Date:** 2026-06-23
- **Status:** Design (brainstorming output) — pending spec review + user approval
- **Author:** LivingLikeKrillin (with Claude)
- **Working name:** `ken` (Scots/English "to know, to understand") — placeholder, fits the Nexus/Probe/mutqa tone; final name open.
- **Context:** khala's first **debt-management product** and the empty leg named in ADR-0002. Targets **cognitive debt** — "nobody understands the system the org ships." First consumer = khala itself (dogfood).
- **Research anchor:** Margaret-Anne Storey, "From Technical Debt to Cognitive and Intent Debt" (ACM Queue 2026 / arXiv:2603.22106); the existing-tool gap (CodeScene's git-attribution model breaks under AI authorship; ADR/AKM tools record but don't measure comprehension) was confirmed by a verified deep-research pass.

---

## 1. Problem & goal

When AI is the producer, code/docs arrive faster than humans build the mental model that
writing-by-hand used to force. The result is **cognitive debt**: artifacts ship that no
named human can actually explain or vouch for. Existing tools measure a *proxy* (git
contribution → assumed knowledge), which **breaks precisely when AI is the author**.

**Goal:** measure *actual* comprehension — whether a named human can vouch for an artifact —
and roll it up to an organization-level signal: **what fraction of critical artifacts has at
least one person who can currently vouch for it**, plus the **orphan list** (artifacts with
no fresh voucher) = the cognitive-debt hotlist.

**Non-negotiable design constraints (from research):**
- **No git-attribution dependency** — must work when AI wrote the artifact.
- **Measure comprehension, not a proxy** — a graded, grounded probe, not a click.
- **Low friction** — or it dies like ADR/AKM tooling (15-year adoption failure from
  author-pays/maintainer-benefits incentive mismatch).
- **Anti-rubber-stamp** — a bare "I understand" click is the exact failure khala exists to
  kill; the vouch must be *earned* against grounded questions.

## 2. Mechanism (decided)

- **North star: hybrid.** Passive signals (Storey's: change-failure, slow onboarding,
  nexus query concentration, bus factor) flag *which* artifacts are risky; active probes
  fire *selectively* on those. **v0 builds only the active vouch core**; passive targeting
  is deferred.
- **Probe = vouch + staleness.** A person attests "I understand and vouch for this"; an LLM
  generates grounded questions from the artifact's actual content and an LLM-as-judge grades
  the answers. A passing vouch is **bound to the artifact's `content_hash`** and has a TTL.
  When the artifact changes (hash mismatch) or the TTL lapses, the vouch goes **stale** and
  must be renewed. This mirrors specledger's `approved_hash` staleness exactly.

## 3. Unit of measurement (decided)

- The atomic record is a **vouch**: `(artifact × person)` — "this person can currently vouch
  for this artifact."
- **Freshness:** a vouch is *fresh* iff `vouch.content_hash == artifact.current_hash` AND
  `now - vouch.ts < TTL`. Otherwise *stale*.
- **Org metric (cognitive-debt coverage):** of the registered critical artifacts, the
  fraction with ≥1 *fresh* vouch. The complement — artifacts with zero fresh vouchers — is
  the **orphan list** (the cognitive-debt hotlist). This is a comprehension-based bus factor
  that is AI-authorship-safe (it never consults git).

## 4. Architecture (build shape A — new module, depends on nexus, borrows specledger hashing)

New module `ken/` following khala's per-tool layout (mirrors `mutqa/`, `specledger/`).
Each unit is one file with a single responsibility and a clear interface:

| Unit | Responsibility | Interface (pure where possible) | Depends on |
|---|---|---|---|
| `registry` | Register/track critical artifacts: `(artifact_id, path, current content_hash)` | `register(path) -> ArtifactRef`; `current_hash(path) -> str` | specledger `content_hash()` |
| `probe` | Generate N grounded questions from an artifact's content | `make_questions(text, n) -> list[Question]` | `LLMService` wrapper |
| `judge` | Grade answers against the artifact (LLM-as-judge) → pass/fail + rationale | `grade(text, qa_pairs) -> Verdict` | `LLMService` wrapper |
| `vouch` | Record a vouch; compute freshness | `record_vouch(...)`; `is_fresh(vouch, artifact, ttl) -> bool` (**pure**) | DB (signals.py pattern) |
| `coverage` | Org metric + orphan list | `coverage() -> CoverageReport` | DB view `v_cognitive_debt` |
| `cli` | `ken register` / `ken probe <artifact> --as <person>` / `ken coverage` | Typer | all above |

**Reuse, not reinvent:** `content_hash()` is imported from specledger (proven, identical
staleness semantics); LLM access goes through an `LLMService`-style wrapper (mirrors nexus);
DB persistence mirrors `nexus/search/signals.py` (pure `extract` + best-effort `record`).

## 5. Data flow

```
register(path)              → registry row (artifact_id, path, content_hash)
ken probe <artifact> --as P → probe.make_questions(content)         [grounded]
   person answers           → judge.grade(content, answers) → Verdict(passed, score, why)
   if passed                → vouch.record_vouch(artifact_id, P, content_hash, score)
artifact edited / TTL lapses→ vouch.is_fresh(...) == False           [stale]
ken coverage                → coverage(): % artifacts with ≥1 fresh vouch + orphan list
```

## 6. Data model

`vouch_log` (PII-safe, best-effort insert, mirrors `search_log`):

| column | type | note |
|---|---|---|
| `id` | BIGSERIAL PK | |
| `ts` | TIMESTAMPTZ default now() | |
| `artifact_id` | TEXT | stable id from registry |
| `person` | TEXT | named voucher (an identity, not PII payload) |
| `content_hash` | TEXT | the hash the vouch was earned against |
| `score` | DOUBLE PRECISION | judge score 0–1 |
| `passed` | BOOLEAN | |
| `n_questions` | INTEGER | |

`v_cognitive_debt` view: per registered artifact, whether a *fresh* vouch exists (join
`vouch_log` to the registry's current hash, within TTL), plus the org-level coverage ratio.
TTL is config (default e.g. 90 days). Registry stored in a small `artifact` table or a
checked-in manifest; v0 may start with a manifest file to avoid premature schema.

## 7. First slice (scope)

- **Interface:** CLI only (matches nexus/mutqa).
- **First consumer:** **khala itself** — register khala's own critical artifacts (the ADRs,
  the approved SPECs, and a hand-picked set of core module files) and measure the director's
  vouch coverage over them. Genuine: khala is AI-built, so its cognitive debt is real.
- **Walking skeleton (end-to-end thin):** register → probe(generate questions) →
  answer(CLI prompt) → judge → vouch → coverage. One artifact, one person, all the way
  through, before breadth.

## 8. Non-goals (v0)

- Passive signal auto-instrumentation (Storey signals) — the hybrid's second half.
- Web dashboard / visualization.
- Multi-tenant, auth, org directory integration.
- Run-time AI-agent evaluation.
- Intent-debt / technical-debt scope (owned by specledger / mutqa+probe respectively).

## 9. Error handling & integrity

- LLM failure in `probe`/`judge`: surface a clear error; **never** auto-pass a vouch on
  failure (fail-closed — a vouch must be earned).
- DB unavailable: `record_vouch` is best-effort like `signals.py`? **No** — a vouch is the
  product's core record, so it must persist transactionally; if the DB is down, the command
  fails loudly rather than silently dropping a vouch. (This is the one place we deviate from
  the fire-and-forget signal pattern.)
- `content_hash` uses specledger's exact normalization so freshness is reproducible.

## 10. Testing

- `judge` verdict shaping, `vouch.is_fresh`, and `coverage` aggregation are **pure
  functions** → deterministic unit tests (no LLM).
- LLM calls (`probe.make_questions`, `judge.grade`) are mocked in tests; a thin contract
  test asserts the wrapper boundary.
- An end-to-end test runs the walking skeleton against a fixture artifact with a stubbed LLM.

## 11. Success criteria

- `ken coverage` reports a real number (% of registered khala artifacts with a fresh vouch)
  and a correct orphan list.
- Editing a registered artifact flips its vouch to **stale** (hash mismatch) — verified.
- A vouch cannot be obtained without passing graded, grounded questions (anti-rubber-stamp).
- Zero dependency on git history anywhere in the measurement path.

## 12. Open questions (carry into the plan, not blocking)

- TTL default and whether it should vary by artifact criticality.
- Registry as table vs checked-in manifest for v0 (lean toward manifest first).
- Identity of `person` (free-string vs a small roster) — v0: free string.

---

## Implementation outline (for writing-plans)

1. Scaffold `ken/` module (pyproject, package, CLI entry) following `mutqa/` layout.
2. `registry` + `content_hash` reuse → register artifacts.
3. `probe.make_questions` + `judge.grade` behind an LLM wrapper (mocked in tests).
4. `vouch` record + `is_fresh` (pure) + `vouch_log` schema.
5. `coverage` + `v_cognitive_debt`.
6. `cli` wiring the walking skeleton.
7. Dogfood: register khala's ADRs/SPECs + core files; run `ken coverage`.
