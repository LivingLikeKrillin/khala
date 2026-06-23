# Design Spec — ken engine v2 / Slice C: calendar TTL (vouch decay)

- **Date:** 2026-06-24
- **Status:** Design (brainstorming output) — pending spec review + user approval
- **Builds on:** ken v0/v1 + ken-web + S2 + Slices A (#38) & B (#39), all merged. Third and final "engine v2 friction" slice.
- **Decisions locked (from brainstorming):** **Reuse the ladder as the TTL** — an artifact is vouched iff **none of its questions are `due`**; `is_vouched` delegates to the existing `schedule.due`. No new policy/constant. Thread an explicit `now` through the coverage path (same pattern as `due_items`). Break the `vouch ↔ schedule` import cycle by **moving `_parse_ts` into `schedule.py`**. Out of scope: changing ladder rungs, a separate configurable TTL, and a `stale`-vs-`orphan` output split.

---

## 1. Goal

Make a vouch **decay over time**: once a question is overdue for re-test (past its spaced-repetition `next_due`), the artifact stops counting as covered until it is re-passed. This completes the calendar-TTL that v1 explicitly deferred (`ken-v1-repayment-loop.md:184`: "v1 has no calendar TTL … `is_vouched` takes no `now`"; the v1 spec table already specified the intended `is_vouched(…, now)` = "pass AND *fresh*").

## 2. The gap (verified)

`vouch.is_vouched(questions, states)` (`ken/src/ken/vouch.py:15-28`) returns True iff every current question has a state whose latest attempt passed — it checks **only `last_passed`** and takes **no `now`**. It ignores the ladder's `next_due`, which `schedule.due` already computes (`schedule.py:80-97`). Consequences:

- A question that is **overdue** for re-test still counts as vouched → understanding never decays (the core cognitive-debt mechanic is inert).
- `coverage` (which calls `is_vouched`) and `due` (which lists overdue questions) **can disagree**: an artifact can be reported "covered" while `ken due` simultaneously lists its questions as due.

## 3. Design: vouched ⇔ no due questions

The ladder already encodes "when must this be re-tested." So:

```python
# vouch.py
def is_vouched(questions, states, *, now) -> bool:
    """True iff NONE of the artifact's current questions are due.

    Delegates to schedule.due, which already treats never-attempted, failed
    (interval_idx resets to 0 -> due immediately), and stale-hash (no state)
    questions as due. An artifact with no questions has no due questions -> True
    (vacuously vouched).
    """
    return not due(states, [q.id for q in questions], now=now)
```

This is the smallest change that:
- **unifies `is_vouched` with `due`** (they can no longer disagree — coverage's "covered" is exactly "no questions due"),
- reuses all existing ladder logic (no duplicated `next_due` math, no new constant),
- preserves every existing truth-table case **under the `now ≥ last_ts` invariant** (see §3.2): never-attempted (`st is None` → always due) and stale-hash (no state → due) are skew-robust; failed and passed route through `due`'s `now ≥ next_due` compare,
- adds decay: a passed question at rung *k* stays "not due" for `LADDER[k]` after its last pass (capping at 30 days at rung 4), then becomes due ⇒ the artifact decays to orphan until re-passed.

### 3.2 The `now ≥ last_ts` invariant (and the failed-question corner)

`due` decides a *stateful* question due iff `now ≥ last_ts + LADDER[interval_idx]` (`schedule.py:95`). A **failed** question has `interval_idx = 0`, so `next_due = last_ts + 0 = last_ts`; it is due iff `now ≥ last_ts`. In all real use `now` is wall-clock and therefore ≥ every recorded attempt ts, so a failed question is always due ⇒ not vouched — matching the old `last_passed`-based result exactly. The *only* divergence from the old truth table is a degenerate `now < last_ts` (clock skew / a future-dated hand-edited ledger line / a test passing a `now` earlier than its attempts): there the failed/passed question would be judged "not yet due" ⇒ wrongly vouched. We treat **`now ≥ all attempt timestamps` as a caller invariant** (every production caller uses wall-clock `now`; tests must pick `now` ≥ their attempt ts). A boundary test (§8) pins `failed + now == last_ts ⇒ due ⇒ not vouched` (the `≥` makes the boundary itself safe).

### 3.1 Break the import cycle: move `_parse_ts` into `schedule.py`

`schedule.py` currently does `from ken.vouch import _parse_ts` (`schedule.py:17`). If `vouch` now imports `schedule.due`, that is a circular import. Resolution: **move the `_parse_ts` definition from `vouch.py` into `schedule.py`** (its only consumer — verified: no other module or test imports `vouch._parse_ts`; `test_schedule.py:55` only names it in a comment, and `postgres_store.py:115` references it as `schedule._parse_ts` in a comment). After the move:
- `schedule.py` defines `_parse_ts` locally (drop the `from ken.vouch import _parse_ts` line); its behavior is unchanged.
- `vouch.py` keeps only `is_vouched`, adds `from ken.schedule import due`, and drops its now-unused `datetime`/`timezone` imports. Dependency is one-way: `vouch → schedule`.

## 4. Thread `now` through the coverage path

`now` is an explicit argument (no wall-clock in pure code), mirroring the existing `due_items(*, store, now)`:

- `coverage.compute_coverage_v1(artifacts, questions_by_artifact, attempts, *, now)` — pass `now` into `is_vouched` (`coverage.py:54`). The weakness map (lifetime `fail_count`) is unchanged.
- `service.coverage_report(*, store, now)` and `service.list_artifacts(*, store, now)` — accept `now` and pass it down (`list_artifacts` calls `coverage_report`).
- **Call sites:**
  - `cli.coverage` → `service.coverage_report(store=store, now=_now())` (`cli.py:189`).
  - ken-web `app.py` → `service.list_artifacts(store=store, now=service.now_iso())` at the two list sites (lines 47, 62) and `service.coverage_report(store=store, now=service.now_iso())` at the coverage site (line 117).

`now` is a **required** keyword arg on these functions (consistent with `due_items`), so every caller is forced to supply it — no silent wall-clock default in the pure/service layer.

## 5. Behavioral consequence (intended)

Coverage is now **time-dependent**: artifacts decay to orphan as their questions age past `next_due`, exactly the cognitive-debt-decay feature. The README (rewritten in Slice B) already describes this: "questions resurface for re-testing until they are passed again" — this slice makes coverage actually honor it.

## 6. Files touched

- **Modify:** `ken/src/ken/schedule.py` — define `_parse_ts` locally; remove `from ken.vouch import _parse_ts`.
- **Modify:** `ken/src/ken/vouch.py` — `is_vouched(questions, states, *, now)` delegates to `schedule.due`; import `due`; drop `_parse_ts` and unused datetime imports; update module docstring.
- **Modify:** `ken/src/ken/coverage.py` — `compute_coverage_v1(..., *, now)`; pass `now` to `is_vouched`.
- **Modify:** `ken/src/ken/service.py` — `coverage_report(*, store, now)`, `list_artifacts(*, store, now)`.
- **Modify:** `ken/src/ken/cli.py` — `coverage` passes `now=_now()`.
- **Modify:** `ken-web/api/src/ken_web_api/app.py` — pass `now=service.now_iso()` at the 3 call sites.
- **Tests:** `ken/tests/test_vouch_derived.py` (add `now`; new overdue-decay case), `ken/tests/test_coverage_v1.py` (add `now`; new decay case), `ken/tests/test_service.py` (add `now` to coverage_report/list_artifacts calls), `ken/tests/test_schedule.py` (unaffected, but confirms `_parse_ts` move didn't break it). ken-web api tests stay green (now-threaded internally).

## 7. Error handling / invariants

- Pure functions stay pure: `now` is an explicit string arg; no wall-clock in `vouch`/`coverage`/`schedule`.
- `_parse_ts`'s tz-safety contract (naive ts coerced to UTC) is preserved verbatim by the move — `test_schedule.py` guards it.
- No change to fail-loud writes, fail-closed grade, the ladder rungs, or the weakness map.
- Hash-staleness behavior is unchanged (stale attempts dropped by `rebuild` → no state → due → not vouched).

## 8. Testing (no API key — pure functions)

Recall `due` uses `now ≥ next_due` (boundary = due), and a single pass advances to **rung 1** (`next_due = last_ts + 1d`). Pick `now` values accordingly — exact values below so no test sits on a boundary.

- **`is_vouched` truth table with `now`:**
  - all-pass, `now` before `next_due` ⇒ True (pass at `2026-06-20T00:00:00Z`, `now = "2026-06-20T01:00:00Z"`; rung-1 `next_due = 2026-06-21T00:00:00Z`).
  - all-pass but `now` past `next_due` (`now = "2026-06-22T00:00:00Z"`) ⇒ **False** (decay — the new case).
  - never-attempted / stale-hash ⇒ False (unchanged; skew-robust).
  - failed question ⇒ False, including the **boundary** `now == last_ts` (`pass`→ fail at `2026-06-20T00:00:00Z`, `now = "2026-06-20T00:00:00Z"`; `next_due == last_ts`, `now ≥ next_due` ⇒ due ⇒ not vouched) — locks §3.2.
  - empty questions ⇒ True (any `now`).
- **coverage decay:** one artifact, one question passed at `2026-06-20T00:00:00Z`; `now = "2026-06-20T01:00:00Z"` ⇒ `covered = 1`; `now = "2026-06-22T00:00:00Z"` ⇒ `covered = 0`, `orphans = ["a1"]`. Proves decay purely from the clock, no content change.
- **Exact `now` for the existing tests** (so none flips):
  - `test_vouch_derived.py` / `test_coverage_v1.py` — all attempts at `2026-06-20T00:00:00Z`; pass `now = "2026-06-20T01:00:00Z"` (well within +1d for the pass cases; the fail/never/stale cases are False regardless).
  - `test_service.py::test_list_artifacts_vouched_with_weak_count` — the question is **failed then passed** (`2026-06-23T00:00:00Z`, then `2026-06-23T01:00:00Z`): the fail resets to rung 0, the pass advances to **rung 1**, so `next_due = 2026-06-24T01:00:00Z`. Pass `now = "2026-06-23T02:00:00Z"` (1h after the last pass) to keep it vouched. `test_list_artifacts_orphan_when_unanswered` and `test_coverage_report_zero_when_unanswered` are orphan regardless; pass any `now ≥` their attempts (use `"2026-06-23T02:00:00Z"`).
- **ken-web api tests stay green** — note: `test_api.py` asserts only `cov["total"] == 1`, never `covered`, and the api computes its attempt `now_iso()` and coverage `now_iso()` microseconds apart (well within +1d), so threading `now=service.now_iso()` internally cannot flip them. (Do not "strengthen" those tests to assert `covered` — that would couple them to wall-clock timing.)
- `test_schedule.py` runs unchanged and green (verifies the `_parse_ts` relocation is behavior-preserving).
- `ruff check` clean (no unused imports after the `_parse_ts`/datetime removals in `vouch.py`).

## 9. YAGNI / scope discipline

- No new TTL constant or config — the ladder *is* the TTL.
- No `stale` vs `orphan` output distinction (decayed artifacts simply appear as orphans this slice).
- No change to ladder rungs or to `due`'s contract — `is_vouched` is now a thin consumer of it.
