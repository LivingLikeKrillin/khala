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
| `questions` (new) | Persist generated questions per artifact, bound to `content_hash`; mark stale when the artifact's hash changes (→ regenerate) | IO | `save_questions(artifact_id, content_hash, [Question])`, `load_questions(artifact_id) -> (hash, [Question])` |
| `schedule` (new) | **Pure** spaced repetition: `next_state(state, passed, now) -> state` over a fixed interval ladder `[now, 1d, 3d, 7d, 30d]` — pass advances one rung, fail resets to a short relearn; `due(states, now) -> [ids]` | pure | No SM-2 ease factor (YAGNI) |
| `attempt` (new) | Append one attempt `(person, question_id, content_hash, passed, score, ts)` to a JSONL ledger, **fail-loud** (raises on IO failure) | IO | mirrors v0 vouch ledger discipline |
| `vouch` (changed) | **Derived**: `is_vouched(artifact, person, states, now) -> bool` = every current question passing & fresh | pure | replaces v0's one-shot `record_vouch`/`vouch_log` |
| `coverage` (changed) | `vouched/total` + **weakness map** (questions/artifacts with repeated recent failures) | pure | reads derived state |
| `cli` (extended) | Agent primitives: `ken due` / `ken save-questions` / `ken record-attempt` / `ken coverage`; plus headless `ken review` (AnthropicLLM self-drive) | edge | |

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
Because v0 is unmerged (PR #29), v1 may freely refactor the vouch layer.

## 7. Spaced repetition (v1 policy)

Fixed interval ladder `[0, 1d, 3d, 7d, 30d]`. A question's state holds
`(interval_idx, consecutive_passes, last_result, next_due, content_hash)`. Pass →
`interval_idx += 1` (capped), `next_due = now + ladder[idx]`. Fail → `interval_idx = 0`,
`next_due = now` (relearn this session), failure counter increments (feeds weakness map).
Hash change → the question is stale; its state resets (the artifact changed, prior mastery
no longer applies).

## 8. Non-goals (v1)

- SM-2 / adaptive ease factors. Persisted explanation text. Web/TUI dashboard. Postgres.
  Multi-user concurrency. Auto-generation of questions without the agent (headless uses the
  v0 probe, which is fine, but no new auto-gen surface).

## 9. Error handling & integrity

- Attempt persistence is **fail-loud** (raises) — never silently drop an attempt.
- `save-questions` rejects questions whose declared `--hash` ≠ the artifact's current hash
  (prevents binding questions to stale content).
- Pure functions (`schedule`, `is_vouched`, `coverage`) never touch IO/LLM.
- No git-history dependency anywhere (carried over from v0).

## 10. Testing

- `schedule.next_state` (pass-advances, fail-resets, cap), `due`, `is_vouched`
  (all-pass-and-fresh truth table incl. a stale question blocking the vouch), `coverage`
  weakness-map aggregation → deterministic unit tests.
- `attempt` fail-loud (raises on unwritable path); `save-questions` hash-mismatch rejection.
- `ken review` headless path tested with `FakeLLM` (reuses v0 seam). Agent-driven loop is
  validated by the protocol doc + the underlying primitives' tests (the loop itself is the
  agent, not code).

## 11. Success criteria

- `ken due --as kr` returns due questions and flags needs-questions artifacts.
- Failing a question reschedules it to relearn (next_due = now) and increments its weakness
  count; passing it advances the interval.
- An artifact's vouch is *withheld* until **all** its current questions pass fresh, and is
  *revoked* (derived) the moment the artifact's hash changes.
- `ken coverage` shows vouched/total **and** a weakness map (repeatedly-failed items).
- The whole loop runs with **no `ANTHROPIC_API_KEY`** in agent-driven mode.

## 12. Open questions (carry to plan, non-blocking)

- Interval ladder values (start with `[0,1d,3d,7d,30d]`).
- Whether review state is cached or always recomputed from the attempt ledger (lean:
  recompute — single source of truth, pure).
- `question_id` derivation (e.g. `sha(artifact_id + content_hash + index)[:12]`).

---

## Implementation outline (for writing-plans)

1. `questions` store (save/load, hash-bound, stale detection).
2. `schedule` pure spaced-repetition (next_state, due) + tests.
3. `attempt` fail-loud JSONL ledger + tests.
4. Refactor `vouch` to derived `is_vouched`; retire v0 one-shot `vouch_log`/`record_vouch`.
5. `coverage` + weakness map (pure) + tests.
6. `cli`: `due` / `save-questions` (hash-checked) / `record-attempt` (updates schedule) / `coverage`; keep headless `review` (AnthropicLLM).
7. `ken/docs/review-protocol.md` — the agent-driven loop.
8. Dogfood: run an agent-driven review session on a khala artifact; record results.
