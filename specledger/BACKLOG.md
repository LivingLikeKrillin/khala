# Specledger Backlog

Post-MVP items deferred from the initial build (see the design spec's Non-goals and
the final review). None block the MVP; all are tracked here.

## Performance
- **`check_gate` full-scan (review I-2):** `Gate.check_gate` calls `Ledger.status()`
  with no argument, which loads + hashes every artifact on every gated edit. Fine at
  solo scale; for a large governed repo, switch to `ledger.status(active_spec_id)`
  (scoped scan, still repairs the active spec) and only opportunistically full-scan on
  `index()`.

## Artifact format fidelity (spec §4)
- **`review_ref` field (review I-3):** add a `review_ref: .reviews/<id>.md` pointer to
  artifact frontmatter on `approve()` so a human/tool can navigate artifact → review
  evidence without knowing the naming convention.
- **`version` field (review I-3):** increment a `version` on living-spec evolution
  (re-review after edit). Requires bump logic in `approve()`/`status()`.

## Enforcement precision
- **`governs:` path-glob mapping:** the MVP gate is path-agnostic (any approved active
  spec allows any source edit). Add optional `governs: [src/**]` globs in spec
  frontmatter so the gate maps edits to the spec that actually governs them.
- **Bash tool gap:** the PreToolUse hook gates `Write|Edit|MultiEdit` only; the `Bash`
  tool can still write files (echo/tee/python -c). Consider a PreToolUse matcher for
  Bash that inspects the command, or a complementary check.

## Review depth
- **Comprehension questions (Q4-B):** optional, high-risk-spec-only "what's the riskiest
  assumption?" gate on top of issue-disposition. Designed but not built.
- **Re-critique after edit:** `approve()` proves a spec was *edited* after an `accepted`
  disposition (hash change) but not that the edit *correctly addresses* the issue.
  Optionally force a re-`critique()` before final approval.

## Drift
- **`stale` auto-detection:** detect spec↔code drift (e.g. spec-derived tests failing,
  or Khala design-vs-observation diff) and auto-flag artifacts `stale`.

## Team
- **Multi-user / real approver identity:** `approved_by` is recorded but unauthenticated
  (solo MVP). Add identity + a shared ledger backend for team use.

## Server test seam
- **MCP wiring integration test (review M-4):** add a test that drives
  `begin_implementation → check_gate → end_implementation → check_gate` through
  `build_app` to cover shared `Gate` state across tool calls (currently only the core
  objects are exercised end-to-end).
