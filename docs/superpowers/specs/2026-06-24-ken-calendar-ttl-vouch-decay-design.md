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
- preserves every existing truth-table case (never-attempted/failed/stale-hash all remain `due` ⇒ not vouched; empty-questions stays vacuously vouched),
- adds decay: a passed question at rung *k* stays "not due" for `LADDER[k]` after its last pass (capping at 30 days at rung 4), then becomes due ⇒ the artifact decays to orphan until re-passed.

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

- **`is_vouched` truth table with `now`:**
  - all-pass and `now` before `next_due` ⇒ True (e.g. pass at `T`, `now = T+1h`, rung-1 `next_due = T+1d`).
  - all-pass but `now` past `next_due` (e.g. `now = T+2d`) ⇒ **False** (decay — the new case).
  - never-attempted / failed / stale-hash question ⇒ False (unchanged, now with `now` supplied).
  - empty questions ⇒ True.
- **coverage decay:** one artifact, one question passed at `T`; `now = T+1h` ⇒ `covered = 1`; `now = T+2d` ⇒ `covered = 0`, `orphans = ["a1"]`. Proves the artifact decays purely from the clock, no content change.
- Existing vouch/coverage/service tests updated to pass a `now` that keeps their intended outcome (recent pass ⇒ before `next_due`).
- `test_schedule.py` runs unchanged and green (verifies the `_parse_ts` relocation is behavior-preserving).
- `ruff check` clean (no unused imports after the `_parse_ts`/datetime removals in `vouch.py`).

## 9. YAGNI / scope discipline

- No new TTL constant or config — the ladder *is* the TTL.
- No `stale` vs `orphan` output distinction (decayed artifacts simply appear as orphans this slice).
- No change to ladder rungs or to `due`'s contract — `is_vouched` is now a thin consumer of it.
