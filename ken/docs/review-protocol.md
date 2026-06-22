# ken — agent-driven review protocol (the keyless loop)

This is the loop the Claude Code agent (or any session LLM) follows to repay
cognitive debt **without an API key**. ken owns the deterministic substrate (the
question store, the attempt ledger, and the pure derivations); the agent owns
cognition (generating grounded questions, grading answers, writing remediation).
ken is a subprocess and cannot call back into the agent — so control is inverted:
the agent drives, calling ken's primitives.

The keyed `ken review` command exists only for headless/CI; the loop below uses no
key.

## The loop

```
1. ken due --as <person>
     → for each registered artifact, prints either:
         needs-questions <artifact_id>          (no questions, or stored hash is stale)
         due <artifact_id> <question_id> <text> (a question that is due now)
       `due` surfaces never-attempted questions too — its contract takes the FULL
       question-id set and treats any id with no review state as due.

2. for each `needs-questions <artifact_id>`:
     - read the artifact's REAL content (from the manifest path)
     - generate N grounded questions answerable ONLY by someone who understands
       THIS artifact's specific content (not generic domain knowledge)
     - ken save-questions <artifact_id> --hash <current_content_hash>
         (questions piped on stdin, one per line)
       save-questions REJECTS a --hash that != the artifact's current hash, and
       REPLACES the artifact's prior question set. Re-run `ken due` to get the
       freshly-assigned question ids.

3. present each DUE question to the person (at most once per run — see below).
   The person answers; the agent grades:
     pass → ken record-attempt --as <person> --question <id> --artifact <aid> --passed [--score S]
     fail → the agent shows a GROUNDED remediation explanation (drawn from the
            artifact's content), then
            ken record-attempt --as <person> --question <id> --artifact <aid> --failed

4. ken coverage --as <person>
     → covered/total + ratio, the orphan hotlist, and the weakness map
       (questions with the highest lifetime fail counts).
```

## Rules

- **Present each question at most once per run.** A failed question is rescheduled
  to relearn (its `next_due` becomes its last-attempt time, i.e. due immediately)
  and re-surfaces on the *next* `ken due` invocation — never in an infinite
  same-session relearn loop. This bounds each run.
- **Cognition is the agent's job, keyless.** Question generation, grading, and
  remediation are produced by the session LLM on the fly. Remediation text is
  **not persisted** (YAGNI) — it is shown, then the pass/fail is recorded.
- **The substrate is deterministic and append-only.** `record-attempt` only
  appends to the ledger; review state is *recomputed* from the ledger on every
  read (`schedule.rebuild`), never cached or mutated in place.
- **Vouch is derived, not granted.** An artifact is "covered" iff *every* one of
  its current questions has a latest attempt that passed. Zero-attempt questions
  block the vouch. Changing the artifact's content changes its hash, which drops
  all prior attempts (they were bound to the old hash) — so the vouch is
  automatically revoked and the questions resurface as `needs-questions`.
- **No calendar TTL in v1.** Staleness = artifact hash change (resets state) plus
  fail-on-retest. Spaced repetition uses a fixed ladder `[0, 1d, 3d, 7d, 30d]`:
  a pass advances one rung (capped), a fail resets to rung 0.

## Why keyless works

"System decides, LLM narrates" applied to the whole loop: ken decides *what* is
due, *whether* the set passes, and *where* the weakness is; the agent narrates the
questions, the grading judgement, and the remediation. No `ANTHROPIC_API_KEY` is
needed in this mode — only the headless `ken review` path calls a keyed model.
