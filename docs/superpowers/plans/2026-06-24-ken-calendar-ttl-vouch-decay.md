# ken calendar TTL (vouch decay) — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a vouch decay over time — `is_vouched` returns True iff none of the artifact's questions are `due` per the spaced-repetition ladder — by delegating to `schedule.due` and threading an explicit `now` through the coverage path.

**Architecture:** `is_vouched(questions, states, *, now) = not schedule.due(states, [q.id…], now=now)`. Break the `vouch ↔ schedule` import cycle by moving `_parse_ts` into `schedule.py`. Thread required `now` through `compute_coverage_v1` → `coverage_report`/`list_artifacts` → CLI/ken-web call sites.

**Tech Stack:** Python 3.11, pytest, ruff. Pure functions, no API key.

**Spec:** `docs/superpowers/specs/2026-06-24-ken-calendar-ttl-vouch-decay-design.md`

---

## File Structure

- `ken/src/ken/schedule.py` — defines `_parse_ts` locally (moved in).
- `ken/src/ken/vouch.py` — `is_vouched(…, *, now)` delegates to `schedule.due`; loses `_parse_ts`.
- `ken/src/ken/coverage.py` — `compute_coverage_v1(…, *, now)`.
- `ken/src/ken/service.py` — `coverage_report(*, store, now)`, `list_artifacts(*, store, now)`.
- `ken/src/ken/cli.py` — `coverage` passes `now=_now()`.
- `ken-web/api/src/ken_web_api/app.py` — 3 call sites pass `now=service.now_iso()`.

---

## Chunk 1: move `_parse_ts` (cycle break, isolated)

### Task 1: relocate `_parse_ts` from `vouch.py` to `schedule.py`

**Files:**
- Modify: `ken/src/ken/schedule.py` (define `_parse_ts`; drop the import)
- Modify: `ken/src/ken/vouch.py` (remove `_parse_ts` + now-unused datetime imports)

This is a pure refactor — the full suite must stay green with no test changes.

- [ ] **Step 1: Move the definition into `schedule.py`**

In `schedule.py`, delete `from ken.vouch import _parse_ts` (line 17) and add, after the `LADDER` definition:

```python
def _parse_ts(ts: str) -> datetime:
    """Parse an ISO-8601 timestamp into a tz-aware datetime.

    `datetime.fromisoformat` on 3.11+ accepts a trailing 'Z'. A naive timestamp
    (e.g. a hand-edited ledger line lacking an offset) is coerced to UTC so it is
    never subtracted against an aware datetime (which would raise TypeError and
    poison org-wide coverage).
    """
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
```

Update `schedule.py`'s imports: it currently does `from datetime import timedelta`; change to `from datetime import datetime, timedelta, timezone`.

- [ ] **Step 2: Trim `vouch.py`**

Remove the `_parse_ts` function from `vouch.py` and its now-unused imports (`from datetime import datetime, timezone`). Leave `is_vouched` and the `Question`/`ReviewState` imports for now (next task rewrites `is_vouched`).

- [ ] **Step 3: Run the full suite — expect PASS (pure refactor)**

Run: `cd ken && python -m pytest -q`
Expected: all pass (notably `test_schedule.py`, which exercises `_parse_ts` via `due`/`rebuild`). `ruff check src tests` clean.

- [ ] **Step 4: Commit**

```bash
git add ken/src/ken/schedule.py ken/src/ken/vouch.py
git commit -m "refactor(ken): move _parse_ts into schedule (one-way dep for slice C)"
```

---

## Chunk 2: vouch decay + `now` threading (atomic)

A required `now` cascades through the whole coverage chain, so this lands as one coordinated TDD task.

### Task 2: `is_vouched(…, now)` delegates to `due`; thread `now` everywhere

**Files:**
- Modify: `ken/src/ken/vouch.py`, `ken/src/ken/coverage.py`, `ken/src/ken/service.py`, `ken/src/ken/cli.py`, `ken-web/api/src/ken_web_api/app.py`
- Test: `ken/tests/test_vouch_derived.py`, `ken/tests/test_coverage_v1.py`, `ken/tests/test_service.py`

- [ ] **Step 1: Rewrite the vouch tests for `now` (RED)** — replace `ken/tests/test_vouch_derived.py` body's `is_vouched(...)` calls with `now`-bearing versions and add the decay + failed-boundary cases:

```python
from ken.models import Attempt, Question
from ken.schedule import rebuild
from ken.vouch import is_vouched


def att(qid, passed, ts, h="sha256:cur"):  # local helper
    return Attempt("kr", "a1", qid, h, passed, 1.0, ts)


def _states(atts, qids):
    return rebuild(atts, current_hashes={q: "sha256:cur" for q in qids})


def test_all_pass_vouched_when_fresh():
    qs = [Question(id="q1", text="a"), Question(id="q2", text="b")]
    atts = [att("q1", True, "2026-06-20T00:00:00Z"), att("q2", True, "2026-06-20T00:00:00Z")]
    states = _states(atts, ["q1", "q2"])
    assert is_vouched(qs, states, now="2026-06-20T01:00:00Z") is True  # before +1d


def test_all_pass_decays_when_overdue():
    qs = [Question(id="q1", text="a")]
    atts = [att("q1", True, "2026-06-20T00:00:00Z")]  # rung 1 -> next_due +1d
    states = _states(atts, ["q1"])
    assert is_vouched(qs, states, now="2026-06-22T00:00:00Z") is False  # past next_due


def test_zero_attempt_question_blocks():
    qs = [Question(id="q1", text="a"), Question(id="q2", text="b")]
    atts = [att("q1", True, "2026-06-20T00:00:00Z")]  # q2 never attempted
    states = _states(atts, ["q1", "q2"])
    assert is_vouched(qs, states, now="2026-06-20T01:00:00Z") is False


def test_failed_question_blocks_at_boundary():
    qs = [Question(id="q1", text="a")]
    atts = [att("q1", False, "2026-06-20T00:00:00Z")]  # rung 0 -> next_due == last_ts
    states = _states(atts, ["q1"])
    # boundary: now == last_ts -> now >= next_due -> due -> not vouched
    assert is_vouched(qs, states, now="2026-06-20T00:00:00Z") is False


def test_stale_hash_blocks():
    qs = [Question(id="q1", text="a")]
    atts = [att("q1", True, "2026-06-20T00:00:00Z", h="sha256:OLD")]
    states = rebuild(atts, current_hashes={"q1": "sha256:NEW"})  # stale -> no state
    assert is_vouched(qs, states, now="2026-06-20T01:00:00Z") is False


def test_empty_questions_vouched():
    assert is_vouched([], {}, now="2026-06-20T00:00:00Z") is True
```

- [ ] **Step 2: Run — expect FAIL** (`is_vouched() got an unexpected keyword argument 'now'`)

Run: `cd ken && python -m pytest tests/test_vouch_derived.py -v`

- [ ] **Step 3: Implement `is_vouched` delegation** — replace `vouch.py`'s `is_vouched` with:

```python
"""Derived vouch: an artifact is vouched iff none of its current questions are due.

`is_vouched` consumes the rebuilt per-question states and the spaced-repetition
schedule (`schedule.due`), so a vouch decays once any question is overdue for
re-test. Pure — `now` is an explicit argument. Caller invariant: `now` >= every
recorded attempt timestamp (production callers use wall-clock now).
"""

from __future__ import annotations

from ken.models import Question, ReviewState
from ken.schedule import due


def is_vouched(questions: list[Question], states: dict[str, ReviewState], *, now: str) -> bool:
    """True iff NONE of the artifact's current questions are due.

    `schedule.due` already treats never-attempted, failed (interval_idx resets to
    0 -> due immediately), and stale-hash (no state) questions as due. An artifact
    with no questions has no due questions -> vacuously vouched.
    """
    return not due(states, [q.id for q in questions], now=now)
```

- [ ] **Step 4: Run vouch tests — expect PASS**

Run: `cd ken && python -m pytest tests/test_vouch_derived.py -v`

- [ ] **Step 5: Thread `now` into `coverage.py`** — change the signature and the `is_vouched` call:

```python
def compute_coverage_v1(
    artifacts: list[ArtifactRef],
    questions_by_artifact: dict[str, tuple[str | None, list[Question]]],
    attempts: list[Attempt],
    *,
    now: str,
) -> CoverageReport:
```

and at the call site (was `if is_vouched(questions, states):`):

```python
        if is_vouched(questions, states, now=now):
```

(The weakness-map loop above it is unchanged — it does not use `now`.)

- [ ] **Step 6: Thread `now` into `service.py`** — `coverage_report` and `list_artifacts`:

```python
def coverage_report(*, store: KenStore, now: str) -> CoverageReport:
    refs = store.load_manifest()
    attempts = store.load_attempts()
    qmap = {r.artifact_id: store.load_questions(r.artifact_id) for r in refs}
    return compute_coverage_v1(refs, qmap, attempts, now=now)


def list_artifacts(*, store: KenStore, now: str) -> list[ArtifactStatus]:
    """One status row per manifest ref, derived from `coverage_report` (no new logic)."""
    refs = store.load_manifest()
    report = coverage_report(store=store, now=now)
    ...  # rest unchanged
```

- [ ] **Step 7: Thread `now` into the CLI** — in `cli.coverage`, change `report = service.coverage_report(store=store)` to:

```python
    report = service.coverage_report(store=store, now=_now())
```

- [ ] **Step 8: Thread `now` into ken-web** — in `ken-web/api/src/ken_web_api/app.py`, the 3 sites:
  - line ~47: `rows = service.list_artifacts(store=store, now=service.now_iso())`
  - line ~62: `rows = service.list_artifacts(store=store, now=service.now_iso())`
  - line ~117: `rep = service.coverage_report(store=store, now=service.now_iso())`

- [ ] **Step 9: Update `coverage`/`service` tests for `now`**

`test_coverage_v1.py` — add `now="2026-06-20T01:00:00Z"` to each `compute_coverage_v1(...)` call (all attempts are at `2026-06-20T00:00:00Z`; the vouched case `test_fully_vouched_artifact_covered` stays covered since `01:00 < next_due 06-21`; orphan cases are orphan regardless). Add a decay test:

```python
def test_vouch_decays_when_overdue():
    arts = [ArtifactRef("a1", "/a", "sha256:cur")]
    qmap = {"a1": ("sha256:cur", [Question(id="q1", text="x")])}
    atts = [att("q1", True, "2026-06-20T00:00:00Z")]
    fresh = compute_coverage_v1(arts, qmap, atts, now="2026-06-20T01:00:00Z")
    assert fresh.covered == 1 and fresh.orphans == []
    stale = compute_coverage_v1(arts, qmap, atts, now="2026-06-22T00:00:00Z")
    assert stale.covered == 0 and stale.orphans == ["a1"]
```

`test_service.py` — add `now=` to the three call sites:
  - `test_coverage_report_zero_when_unanswered`: `coverage_report(store=store, now="2026-06-23T02:00:00Z")` (orphan regardless).
  - `test_list_artifacts_orphan_when_unanswered`: `list_artifacts(store=store, now="2026-06-23T02:00:00Z")` (orphan regardless).
  - `test_list_artifacts_vouched_with_weak_count`: `list_artifacts(store=store, now="2026-06-23T02:00:00Z")` — attempts fail@`06-23T00:00`, pass@`06-23T01:00` → rung 1 → `next_due = 06-24T01:00`; `02:00 < that` ⇒ still vouched.

- [ ] **Step 10: Full green gate**

Run: `cd ken && python -m pytest -q && ruff check src tests`
Expected: all pass; ruff clean (no unused imports in `vouch.py`).

Note: `test_cli_v1.py` is **not** edited but is in scope of the full run. Its `test_record_attempt_then_coverage_moves` / review tests record a pass via wall-clock `_now()` then run `coverage` (now stamped `now=_now()` microseconds later) — a single pass is rung 1 (next_due = +1d ≫ the gap), so it stays `1/1` green with no changes. Same wall-clock-gap reasoning as the ken-web tests.

Run: `cd ken-web/api && python -m pytest -q`
Expected: all pass (api threads `now` internally; no api test asserts `covered`).

- [ ] **Step 11: Commit**

```bash
git add ken/src/ken/vouch.py ken/src/ken/coverage.py ken/src/ken/service.py ken/src/ken/cli.py \
        ken-web/api/src/ken_web_api/app.py ken/tests/test_vouch_derived.py \
        ken/tests/test_coverage_v1.py ken/tests/test_service.py
git commit -m "feat(ken): vouch decays via ladder (is_vouched delegates to schedule.due; thread now)"
```

---

## Done criteria

- `is_vouched(…, now)` delegates to `schedule.due`; a passed-but-overdue question makes the artifact decay to orphan.
- `now` threaded (required) through `compute_coverage_v1`/`coverage_report`/`list_artifacts`; CLI uses `_now()`, ken-web uses `service.now_iso()`.
- `_parse_ts` lives in `schedule.py`; `vouch → schedule` is one-way; no import cycle.
- `cd ken && python -m pytest -q` and `cd ken-web/api && python -m pytest -q` green; `ruff check` clean.
