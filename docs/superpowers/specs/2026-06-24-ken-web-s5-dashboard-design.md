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

### 4.2 `ken.service.artifact_detail(artifact_id, *, store, now) -> list[QuestionDetail]` (new, pure composition)

Storage-agnostic derivation, no LLM, no generation:

1. `ref = find_ref(artifact_id, store=store)`; raise `KeyError(artifact_id)` if absent.
2. `questions = store.load_questions(artifact_id)`; `attempts = store.load_attempts()`.
3. `current_hashes = {q.id: q.content_hash-of-current}` — same map `coverage`/`due`
   build (each question's current content hash). `states = schedule.rebuild(attempts,
   current_hashes=current_hashes)`.
4. `due_set = set(schedule.due(states, [q.id for q in questions], now=now))`.
5. Build one `QuestionDetail` per question (preserving question order):
   - `attempted = qid in states`
   - if attempted: `rung = state.interval_idx`, `last_passed = state.last_passed`,
     `last_ts = state.last_ts`, `fail_count = state.fail_count`,
     `next_due = schedule.next_due_at(state).isoformat()`
   - if never-attempted (absent from `states`, incl. stale-hash): `rung = 0`,
     `attempted = False`, `last_passed = None`, `last_ts = None`, `fail_count = 0`,
     `next_due = None` (≡ due now)
   - `due = qid in due_set`

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

> **Note on the hash map.** `coverage_report` already builds the per-question current
> hash basis; `artifact_detail` must use the **identical** construction so `rebuild`
> survivorship matches coverage exactly (a stale-hash attempt is dropped → the question
> reads as never-attempted in both). Factor the shared map construction if it isn't
> already a helper, to avoid divergence.

### 4.3 API — `GET /api/artifacts/{id}/detail`

```
GET /api/artifacts/{artifact_id}/detail  ->  200 {questions: [QuestionDetailOut...]}
                                             404 unknown artifact_id (KeyError)
```

- Calls `service.artifact_detail(artifact_id, store=make_store(), now=now_iso())`.
- **Does not generate** questions (unlike `/due`): an artifact with no questions yet
  returns `{"questions": []}`. A read-only tracking view must never spend LLM tokens.
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
- Detail derivation must agree with coverage: same hash basis, same `rebuild`/`due`
  outputs (no re-derivation of due-ness in the page or the service).

## 8. Testing

- **ken (`artifact_detail`):** never-attempted question (rung 0, `next_due=None`, `due`);
  one pass advances rung + `next_due` shifts; one fail resets rung 0 + `fail_count=1`;
  due vs not-due decided by `now` straddling `next_due`; stale-hash attempt → question
  reads never-attempted; unknown artifact → `KeyError`. Plus `next_due_at` unit
  (rung→interval) and the `due`/`next_due_at` agreement.
- **api:** `/detail` 200 shape; 404 unknown id; **no generation** triggered (store with
  questions + attempts, assert no LLM call / question count unchanged); empty-questions
  artifact → `{"questions": []}`.
- **web (vitest):** ArtifactDetail renders ladder rungs, overdue badge vs due-now,
  fail-count pill, empty state, and the review CTA; Home row click routes to
  `/artifact/:id`. Client module mocked (no network), per existing convention.

## 9. Success criteria

- Opening an artifact shows every question with its mastery rung, last attempt, next-due
  (overdue flagged), and fail count — all derived, no new stored state.
- The detail endpoint never calls the LLM and never generates questions.
- Coverage and detail agree on which questions are due / never-attempted.
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
