# Design Spec — `ken` v1: the cognitive-debt repayment loop

- **Date:** 2026-06-23
- **Status:** Design (brainstorming output) — pending spec review + user approval
- **Builds on:** ken v0 (PR #29, branch `feat/ken-cognitive-debt-meter`). This v1 branches off v0; its PR base is the v0 branch (stacked). Merge order: v0 (#29) → v1.
- **Context:** v0 *measures* cognitive debt (a one-shot earned vouch → coverage + orphan list). v1 turns ken from a **meter** into a **repayment loop** — failed comprehension is remediated and re-tested with spaced repetition until mastered. This is the "pay down the debt" half of khala's mission, not just diagnosis.

---

## 1. Goal & the core shift

v0's vouch is a one-shot pass. v1 redefines it:

> **A vouch is *derived*, not recorded one-shot.** A person vouches for an artifact iff
> they currently pass **all** of that artifact's questions, each still *fresh* (answered
> against the current `content_hash`, within TTL). Failing a question triggers
> **remediation** (a grounded explanation) and **spaced re-testing** until it passes.

This makes ken *reduce* the debt it measures, and yields a **sharper signal** than binary
coverage: a *weakness map* of repeatedly-failed questions/areas.

## 2. Control model (decided): agent-driven + ken = deterministic substrate

ken is a subprocess and cannot call back into the Claude Code agent. So "session LLM, no
API key" is realized by **inverting control**:

- **ken owns the deterministic substrate:** the question store, the per-person review state
  + spaced-repetition schedule, the attempt ledger, and the *pure* derivations (is_vouched,
  coverage, weakness map). No cognition.
- **The Claude Code agent owns cognition:** generating grounded questions, grading answers,
  and writing remediation explanations — calling ken's primitives. No API key needed; this
  is "system decides, LLM narrates" applied to the whole loop.
- **Headless/CI still works:** a `ken review` command self-drives using the existing v0
  `AnthropicLLM` (keyed). Both modes share the same substrate.

## 3. Units (incremental on v0; each one responsibility)

| Unit | Responsibility | Kind | Notes |
|---|---|---|---|
| `questions` (new) | Persist questions per artifact, bound to `content_hash`; **replace-on-save** keyed by `artifact_id`; **fail-loud** write; stale when artifact hash changes | IO | `save_questions(artifact_id, content_hash, [Question])`, `load_questions(artifact_id) -> (hash, [Question])`. Each `Question` carries a stable `id = sha(artifact_id + content_hash + index)[:12]` |
| `schedule` (new) | **Pure** spaced repetition: `rebuild(attempts) -> states` (replay a question's attempts in `ts` order — the single ledger→state reducer all derivations use), `next_state(state, attempt) -> state`, `due(states, now) -> [ids]`. Fixed ladder `[0, 1d, 3d, 7d, 30d]` (rung 0 = due now); pass advances one rung (capped at last), fail resets to rung 0 | pure | No SM-2 (YAGNI). `next_due = last_attempt.ts + ladder[interval_idx]` (deterministic, no wall-clock in recompute) |
| `attempt` (new) | **Append** one attempt `(person, artifact_id, question_id, content_hash, passed, score, ts)` to a JSONL ledger, **fail-loud**. Append-only — never mutates prior state | IO | `artifact_id` denormalized so derivations need no live join |
| `vouch` (changed) | **Derived**: `is_vouched(artifact, person, states, now) -> bool` = **every** current question (from the fresh-hash store) has a latest attempt that is *pass* AND *fresh*; a question with **zero** attempts ⇒ not vouched | pure | replaces v0's one-shot `record_vouch`/`vouch_log` |
| `coverage` (changed) | `vouched/total` + **weakness map** (per question/artifact failure counts from the ledger) | pure | reads derived state via `schedule.rebuild` |
| `cli` (extended) | Agent primitives: `ken due` / `ken save-questions` / `ken record-attempt` / `ken coverage`; plus headless `ken review` (AnthropicLLM self-drive) | edge | `record-attempt` **only appends**; schedule state is a read-time view (`rebuild`), never a mutated file |

## 4. Agent-driven review loop (the "session LLM", made concrete)

Persisted as a short protocol doc the agent follows: `ken/docs/review-protocol.md` (prose,
not code). The loop:

```
ken due --as kr
  → list of (artifact_id, question_id, question_text) due now;
    artifacts with no (or stale) questions are returned as "needs-questions"
for each needs-questions artifact:
    agent reads the artifact's real content, generates N grounded questions,
    → ken save-questions <artifact_id> --hash <current_hash>   (questions via stdin/JSON)
present each due question to the person; person answers; agent grades:
    pass → ken record-attempt --as kr --question <id> --passed [--score]
    fail → agent shows a grounded explanation (remediation), then
           ken record-attempt --as kr --question <id> --failed
ken coverage --as kr
  → vouched/total + the weakness map
```

`record-attempt` updates the schedule (advance/reset) and appends to the attempt ledger.
Remediation explanations are produced by the agent on the fly and **not persisted** (YAGNI).

## 5. Persistence

File-based, mirroring mutqa/v0 (no DB). Under a `.ken/` directory (or alongside the
manifest): a questions store (per artifact, with the bound `content_hash`), an
append-only attempt ledger (JSONL), and the review state (rebuildable from the attempt
ledger + schedule; lean toward recomputing, not caching — single source of truth). Reuse v0 `registry`, `hashing`, and `content_hash`
staleness unchanged. **Fail-loud** on all writes.

## 6. Reconciliation with v0

v0's one-shot `record_vouch` + `vouch_log` are **superseded** by the attempt ledger +
derived `is_vouched`. v0 `registry`, `hashing`, `coverage` *shape*, `llm` (LLMClient +
AnthropicLLM + FakeLLM), `probe`, `judge` are reused. `probe`/`judge` remain for the
headless `ken review` path; in agent-driven mode the agent performs those roles directly.
Because v0 is unmerged (PR #29), v1 may freely refactor the vouch layer. **Model change:**
v0's frozen `Question` dataclass (currently just `text`) gains a stable `id` field (computed
as in §3) — a small, explicitly-called-out addition.

## 7. Spaced repetition (v1 policy)

Fixed interval ladder `LADDER = [0, 1d, 3d, 7d, 30d]` (rung 0 = due now). Per-question state
is **recomputed** (never stored) by `schedule.rebuild`, replaying that question's attempts in
`ts` order:

- **Initial** (freshly generated question, zero attempts): `interval_idx = 0` → due
  immediately; counts as *not vouched*.
- **Pass:** `interval_idx = min(interval_idx + 1, len(LADDER) - 1)`.
- **Fail:** `interval_idx = 0`; failure counter += 1 (feeds the weakness map).
- **next_due** (deterministic): `last_attempt.ts + LADDER[interval_idx]` — no wall-clock at
  recompute time, so derivations stay pure and unit-testable.
- **Hash change:** attempts whose `content_hash` ≠ the question's *current* hash are ignored
  by `rebuild` (artifact changed → state resets to initial, vouch revoked). Orphaned
  attempts (whose `question_id` is absent from the current fresh-hash store) are likewise
  ignored.
- **In-session relearn termination:** `due`/`review` presents each question **at most once
  per invocation** even if failed; a failed question re-surfaces on the *next* run. This
  bounds the loop (no infinite same-session relearn).

## 8. Non-goals (v1)

- SM-2 / adaptive ease factors. Persisted explanation text. Web/TUI dashboard. Postgres.
  Multi-user concurrency. Auto-generation of questions without the agent (headless uses the
  v0 probe, which is fine, but no new auto-gen surface).

## 9. Error handling & integrity

- Attempt persistence is **fail-loud** (raises), **append-only** — never silently drop,
  never mutate prior records.
- The questions store write is **fail-loud** too — it is the join target for all
  derivations, so a dropped `save-questions` corrupts coverage as badly as a dropped attempt.
- `save-questions` **rejects** questions whose declared `--hash` ≠ the artifact's current
  hash (no binding to stale content), and **replaces** the artifact's prior set (keyed by
  `artifact_id`).
- Derivations take `now` as an explicit argument — no wall-clock at recompute (deterministic).
- Pure functions (`schedule`, `is_vouched`, `coverage`) never touch IO/LLM.
- No git-history dependency — *structural*: ken imports no git/subprocess (carried from v0).

## 10. Testing

- **`schedule.rebuild` (load-bearing reducer):** replay ordering; pass-advance / fail-reset
  / cap; **hash-change mid-history resets state**; orphaned-attempt skip; `next_due` formula
  → deterministic tests.
- `schedule.next_state`, `due`.
- `is_vouched` truth table: all-pass-and-fresh ⇒ true; a stale question blocks; **a question
  with zero attempts blocks** (the "withheld until all pass" case — easiest to get wrong).
- `coverage` weakness-map aggregation.
- `attempt` fail-loud (raises on unwritable path); **questions store fail-loud**;
  `save-questions` hash-mismatch rejection; **replace-on-save** (re-save replaces prior set).
- `ken review` headless path with `FakeLLM` (reuses v0 seam). Agent-driven loop is validated
  by the protocol doc + the primitives' tests (the loop itself is the agent, not code).

## 11. Success criteria

- `ken due --as kr` returns due questions and flags needs-questions artifacts.
- Failing a question reschedules it to relearn (next_due = now) and increments its weakness
  count; passing it advances the interval.
- An artifact's vouch is *withheld* until **all** its current questions pass fresh, and is
  *revoked* (derived) the moment the artifact's hash changes.
- `ken coverage` shows vouched/total **and** a weakness map (repeatedly-failed items).
- The whole loop runs with **no `ANTHROPIC_API_KEY`** in agent-driven mode.

## 12. Resolved decisions (previously open)

- **Interval ladder:** `[0, 1d, 3d, 7d, 30d]` (fixed).
- **State storage:** **always recompute** from the attempt ledger via `schedule.rebuild` —
  single source of truth, no cached state file.
- **`question_id`:** `sha(artifact_id + content_hash + index)[:12]` — stable, and changes
  when the artifact's content changes (the intended staleness reset).

---

## Implementation outline (for writing-plans)

1. `questions` store (save/load, hash-bound, stale detection).
2. `schedule` pure spaced-repetition: `rebuild` (the ledger→states reducer all derivations use), `next_state`, `due` + tests.
3. `attempt` fail-loud JSONL ledger + tests.
4. Refactor `vouch` to derived `is_vouched`; retire v0 one-shot `vouch_log`/`record_vouch`.
5. `coverage` + weakness map (pure) + tests.
6. `cli`: `due` / `save-questions` (hash-checked) / `record-attempt` (updates schedule) / `coverage`; keep headless `review` (AnthropicLLM).
7. `ken/docs/review-protocol.md` — the agent-driven loop.
8. Dogfood: run an agent-driven review session on a khala artifact; record results.
