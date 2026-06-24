# Design Spec — ken-web S5: per-question tracking dashboard (artifact drill-down)

**Date:** 2026-06-24
**Status:** approved design → spec
**Milestone:** B (self-host · single team)
**Depends on:** ken-web v0 (#35), v2 calendar-TTL / vouch-decay (#40)

## 1. Goal & the core shift

ken-web Home already surfaces a **coverage snapshot** (the headline badge) plus a
"needs your attention" list of artifacts (orphans first, then `weak_count`). What it
does **not** show is *why* an artifact is where it is: which specific questions are
weak, where each sits on the spaced-repetition ladder, and when each comes due again.

That derived state already exists in the substrate — `schedule.rebuild` produces a
`ReviewState` per question (`interval_idx`, `last_ts`, `last_passed`, `fail_count`) and
`schedule.due` decides due-ness — but **no API exposes it**. S5 closes that gap with a
read-only **per-question drill-down**: open an artifact → see each question's mastery
rung, last attempt, next-due (with an overdue badge), and fail count.

This makes the just-shipped v2 decay model legible: an artifact is `orphan` because
*these* questions went overdue, and *these* are the weak ones.

## 2. Scope decisions (settled in brainstorming)

- **Core job:** per-question drill-down + schedule, not a global due-calendar and not
  time-series trends. (Those remain deferred next-slice options.)
- **No `person` dimension.** Artifact/question-centric only. `person` tracking belongs
  to S6 (auth · multi-tenancy); the `person` field stays informational.
- **Pure tracking view.** The detail page is read-only. "Start review" reuses the
  **existing whole-artifact** review flow — no single-question targeting (no engine/API
  change for targeting).
- **Mastery labels are interval-factual** ("due now / 1d / 3d / 7d / 30d"), not invented
  stage names — no new semantics.

## 3. Approach (chosen): per-artifact detail endpoint

Mirror the existing `GET /api/artifacts/{id}/due` pattern with a sibling
`GET /api/artifacts/{id}/detail`. Rejected alternatives:

- **B — embed detail in `/coverage` or `/artifacts`.** Breaks the thin-row contract and
  over-fetches on Home. ✗
- **C — global `GET /api/schedule` (all artifacts).** Sets up the deferred due-calendar
  but mixes concerns and over-fetches for this scope (YAGNI). ✗

Everything below is **additive**. No change to `schedule.rebuild` / `schedule.due` /
`compute_coverage_v1` logic, no change to the store contract, no change to PostgresStore.

## 4. Units (each one responsibility)

### 4.1 `ken.schedule.next_due_at(state: ReviewState) -> datetime` (new, pure)

Single public source for "when is this question next due", currently computed inline
inside `due` as `_parse_ts(state.last_ts) + LADDER[state.interval_idx]`. Extract that
one expression into a public helper; `due` calls it so the two can never disagree.
Returns a tz-aware `datetime`. (Keeps `_parse_ts` private; this is the public surface.)

### 4.2 `ken.service.artifact_detail(artifact_id, *, store, now: str) -> list[QuestionDetail]` (new, pure composition)

Storage-agnostic derivation, **no LLM, no generation**. `now` is an ISO-8601 **string**
(same as `due_items` / `coverage_report`). Mirrors the exact gate-and-map used by
`due_items` (service.py:77-83) and `compute_coverage_v1` (coverage.py:34-43):

1. `ref = find_ref(artifact_id, store=store)`; raise `KeyError(artifact_id)` if absent.
2. `store_hash, questions = store.load_questions(artifact_id)`;
   `attempts = store.load_attempts()`. (`load_questions` returns a
   `tuple[str | None, list[Question]]` — the stored store-hash and the questions.)
3. **Artifact-level stale gate (same as coverage/due, short-circuits before rebuild):**
   if `not questions or store_hash != ref.content_hash` → return `[]`. The artifact's
   questions are missing or bound to *stale* content, so nothing is currently bound to
   review — exactly the condition under which `coverage` marks the artifact `orphan` and
   `due_items` returns `needs_questions`. The detail page renders its empty state ("no
   current questions — start a review to (re)generate"). There is **no per-question**
   stale handling; staleness is whole-artifact, matching the substrate.
4. Bound case — build the current-hash map exactly as the substrate does: every question
   maps to the **artifact's** current hash (the hash is uniform across an artifact's
   questions, not per-question). `Question` has only `text` and `id`; there is no
   `Question.content_hash`.
   ```python
   current_hashes = {q.id: ref.content_hash for q in questions}   # == due_items / coverage
   states = schedule.rebuild(attempts, current_hashes=current_hashes)
   due_set = set(schedule.due(states, [q.id for q in questions], now=now))
   ```
5. Build one `QuestionDetail` per question (preserving question order):
   - `state = states.get(q.id)`; `attempted = state is not None`
   - if attempted: `rung = state.interval_idx`, `last_passed = state.last_passed`,
     `last_ts = state.last_ts`, `fail_count = state.fail_count`,
     `next_due = schedule.next_due_at(state).isoformat()`
   - if absent from `states` (never-attempted; a stale-*attempt*-hash row is already
     dropped by `rebuild`): `rung = 0`, `last_passed = None`, `last_ts = None`,
     `fail_count = 0`, `next_due = None` (≡ due now)
   - `due = q.id in due_set`

```python
@dataclass(frozen=True)
class QuestionDetail:
    question_id: str
    text: str
    rung: int                 # interval_idx 0..4 (0 when never-attempted)
    attempted: bool
    last_passed: bool | None
    last_ts: str | None
    fail_count: int
    next_due: str | None      # ISO-8601; None ⇒ never-attempted ⇒ due now
    due: bool
```

> **Shared construction (advisory refactor).** The expression
> `{q.id: ref.content_hash for q in qs}` plus the `not qs or store_hash != ref.content_hash`
> gate is now repeated in `due_items`, `compute_coverage_v1`, and `artifact_detail`. A tiny
> helper (e.g. `_bound_questions(ref, store) -> list[Question] | None`, returning `None`
> when stale/empty) would remove the divergence risk. This is **advisory**, not required —
> if done, keep the diff bounded to these three call sites with no behavior change.

### 4.3 API — `GET /api/artifacts/{id}/detail`

```
GET /api/artifacts/{artifact_id}/detail  ->  200 {questions: [QuestionDetailOut...]}
                                             404 unknown artifact_id (KeyError)
```

- Calls `service.artifact_detail(artifact_id, store=make_store(), now=now_iso())`.
- **Does not generate** questions (unlike `/due`, which calls `service.ensure_questions`
  → `make_questions` → LLM): an artifact with no current questions returns
  `{"questions": []}`. The handler **must not call `deps.make_llm()` at all** — a
  read-only tracking view constructs no LLM client and spends no tokens.
- `QuestionDetailOut` Pydantic DTO mirrors `QuestionDetail` field-for-field.

### 4.4 Frontend — `/artifact/:id` detail page

- New route in `App.tsx`: `/artifact/:id` → `pages/ArtifactDetail.tsx`.
- `ArtifactDetail` (read-only): loads `getArtifactDetail(id)`; renders per question a row
  with **`MasteryLadder`** (5 pips, `rung` filled), last-attempt chip
  (pass/fail + relative time, or "never attempted"), **next-due** (date; `overdue` badge
  when `due && attempted`, "due now" when never-attempted), and `fail_count` when > 0.
- Header shows the artifact basename/path and a **"Start review →"** button that
  navigates to the existing `/review?artifact=<id>` whole-artifact flow.
- States: loading skeleton, error, and empty ("no questions yet — start a review").
- **Home change (approved):** artifact **row click → `/artifact/:id`** (detail), making
  Home an index → detail → review funnel. The cover **"Start review →"** button keeps its
  current direct-to-review behavior.
- `MasteryLadder` is a small presentational component (0–4 filled pips + interval label
  `due now / 1d / 3d / 7d / 30d`).
- `api/client.ts`: add `getArtifactDetail(id): Promise<ArtifactDetail>`.
- `types.ts`: add `QuestionDetail` + `ArtifactDetail` interfaces, in lockstep with the
  Pydantic DTOs.

## 5. Data flow

```
Home (index)  --row click-->  /artifact/:id
   GET /api/artifacts/:id/detail
     service.artifact_detail
       store.load_questions + store.load_attempts
       schedule.rebuild -> states ; schedule.due -> due_set ; next_due_at -> next_due
   -> [QuestionDetail...]  -> rows (MasteryLadder + last attempt + next due + fails)
   "Start review ->"  -->  /review?artifact=:id   (existing flow, unchanged)
```

## 6. Non-goals (S5)

- No global due-calendar across all artifacts (deferred option).
- No time-series / trend charts (deferred option).
- No `person` breakdown or filtering (S6).
- No single-question targeted review (engine/API unchanged).
- No new persistence, no schema change, no PostgresStore change.

## 7. Error handling & integrity

- Unknown `artifact_id` → `KeyError` in service → **404** (same mapping as `/due`).
- Read-only: no writes, so no fail-loud `OSError` path on this endpoint.
- `next_due_at` reuses `_parse_ts` (naive-ts → UTC coercion) — inherits the existing
  guard against tz-poisoning org-wide derivations.
- **Agreement with coverage (precise, given coverage's gate is artifact-level):**
  - *Stale or no questions* (`not questions or store_hash != ref.content_hash`): coverage
    marks the artifact `orphan`; detail returns `[]`. Both say "nothing bound."
  - *Bound artifact*: detail consumes the **same** `current_hashes` map and the same
    `rebuild` output, and its `due` flags are exactly `schedule.due(...)` — no due-ness is
    re-derived in the service or the page. A question never-attempted in coverage's rebuild
    is `attempted=False` in detail.
  This makes the invariant testable: detail's per-question `due` set ≡ `schedule.due` for
  the bound case, and detail ≡ empty for the stale/empty case coverage calls `orphan`.

## 8. Testing

- **ken (`artifact_detail`):** never-attempted question (rung 0, `attempted=False`,
  `next_due=None`, `due=True`); one pass advances rung + `next_due` shifts; one fail
  resets rung 0 + `fail_count=1`; due vs not-due decided by `now` straddling `next_due`;
  **stale store-hash artifact → `[]`** and **no questions → `[]`** (gate); stale-*attempt*-
  hash row → that question reads never-attempted (dropped by `rebuild`); unknown artifact
  → `KeyError`. Plus `next_due_at` unit (rung→interval) and a pinned `due` ⇔ `next_due_at`
  agreement test across the full rung range.
- **api:** `/detail` 200 shape; 404 unknown id; **handler never constructs the LLM** —
  monkeypatch `deps.make_llm` to raise and assert `/detail` still 200 (proves no LLM
  path); stale/empty artifact → `{"questions": []}` with question count unchanged (no
  generation side-effect).
- **web (vitest):** ArtifactDetail renders ladder rungs, overdue badge vs due-now,
  fail-count pill, empty state, and the review CTA; Home row click routes to
  `/artifact/:id`. Client module mocked (no network), per existing convention.

## 9. Success criteria

- Opening a **bound** artifact shows every question with its mastery rung, last attempt,
  next-due (overdue flagged), and fail count — all derived, no new stored state. A stale
  or question-less artifact shows the empty state (matching coverage's `orphan`).
- The detail endpoint never constructs the LLM and never generates questions.
- For a bound artifact, detail's per-question `due` set ≡ `schedule.due`; the stale/empty
  case ≡ coverage's `orphan` ("nothing bound") — granularity matches the substrate.
- No change to engine derivation logic, store contract, or PostgresStore; CI 9 jobs green.

## Implementation outline (for writing-plans)

1. `ken`: add `schedule.next_due_at`; refactor `due` to call it (no behavior change) —
   with a test pinning agreement.
2. `ken`: add `QuestionDetail` + `service.artifact_detail` (+ shared hash-map helper if
   needed) — TDD the 6 cases.
3. `api`: `QuestionDetailOut` DTO + `GET /api/artifacts/{id}/detail` — TDD 200/404/no-gen.
4. `web`: `types.ts` + `getArtifactDetail`; `MasteryLadder`; `ArtifactDetail` page;
   `App.tsx` route; Home row → detail — vitest each.
5. Verify CI 9 jobs green; (optional) extend the manual E2E note with a detail-page pass.
