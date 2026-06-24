# ken-web S5 Dashboard (per-question drill-down) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only per-question tracking dashboard — open an artifact and see each question's mastery rung, last attempt, next-due (overdue flagged), and fail count.

**Architecture:** Additive only. Expose the already-derived `schedule` state through a new pure service composition (`artifact_detail`) and a sibling read endpoint `GET /api/artifacts/{id}/detail` (no LLM, no generation), then a new `/artifact/:id` SPA page. No change to `schedule.rebuild` / `due` / coverage logic, no schema change, no PostgresStore change. Staleness stays artifact-level, matching the substrate.

**Tech Stack:** Python 3.13 (ken engine, FastAPI), React + Vite + TypeScript (SPA), pytest + vitest.

**Spec:** `docs/superpowers/specs/2026-06-24-ken-web-s5-dashboard-design.md`

---

## File Structure

- `ken/src/ken/schedule.py` — **modify**: add `next_due_at(state)`; `due` calls it (behavior-preserving).
- `ken/src/ken/service.py` — **modify**: add `_bound_questions` helper; refactor `due_items`/`ensure_questions` to use it; add `QuestionDetail` + `artifact_detail`.
- `ken/tests/test_schedule.py` — **modify**: `next_due_at` unit + `due`⇔`next_due_at` agreement.
- `ken/tests/test_service.py` — **modify**: `artifact_detail` cases.
- `ken-web/api/src/ken_web_api/schemas.py` — **modify**: add `QuestionDetailOut`, `ArtifactDetailOut`.
- `ken-web/api/src/ken_web_api/app.py` — **modify**: add `GET /api/artifacts/{id}/detail`.
- `ken-web/api/tests/test_api.py` — **modify**: detail endpoint tests.
- `ken-web/web/src/types.ts` — **modify**: add `QuestionDetail`, `ArtifactDetail`.
- `ken-web/web/src/api/client.ts` — **modify**: add `getArtifactDetail`.
- `ken-web/web/src/components/MasteryLadder.tsx` — **create**.
- `ken-web/web/src/pages/ArtifactDetail.tsx` — **create**.
- `ken-web/web/src/App.tsx` — **modify**: add `/artifact/:id` route.
- `ken-web/web/src/pages/Home.tsx` — **modify**: row click → `/artifact/:id`.
- `ken-web/web/tests/artifact-detail.test.tsx` — **create**.
- `ken-web/web/tests/home.test.tsx` — **modify**: row click routes to detail.

---

## Chunk 1: ken schedule — `next_due_at`

### Task 1: Extract `next_due_at` (behavior-preserving)

**Files:**
- Modify: `ken/src/ken/schedule.py`
- Test: `ken/tests/test_schedule.py`

- [ ] **Step 1: Write the failing test**

Add to `ken/tests/test_schedule.py` (it already imports from `ken.schedule`):

```python
def test_next_due_at_is_last_ts_plus_ladder_rung():
    from datetime import datetime, timezone
    from ken.schedule import next_due_at
    st = rebuild([att("q", True, "2026-06-01T00:00:00Z")], current_hashes={"q": "sha256:cur"})["q"]
    # one pass -> interval_idx 1 -> +1 day
    assert next_due_at(st) == datetime(2026, 6, 2, 0, 0, tzinfo=timezone.utc)


def test_due_agrees_with_next_due_at_across_rungs():
    # due-ness must be exactly: now >= next_due_at(state). Pin the agreement.
    from ken.schedule import next_due_at
    st = rebuild([att("q", True, "2026-06-01T00:00:00Z")], current_hashes={"q": "sha256:cur"})["q"]
    nd = next_due_at(st)
    just_before = "2026-06-01T23:59:00Z"
    at_or_after = "2026-06-02T00:00:00Z"
    assert "q" not in due({"q": st}, ["q"], now=just_before)
    assert "q" in due({"q": st}, ["q"], now=at_or_after)
    assert nd.isoformat() == "2026-06-02T00:00:00+00:00"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest ken/tests/test_schedule.py::test_next_due_at_is_last_ts_plus_ladder_rung -v`
Expected: FAIL with `ImportError: cannot import name 'next_due_at'`.

- [ ] **Step 3: Write minimal implementation**

In `ken/src/ken/schedule.py`, add after `next_state` (before `due`):

```python
def next_due_at(state: ReviewState) -> datetime:
    """When this question is next due: last attempt ts + the rung's interval.

    Single public source for the expression `due` uses internally, so the two can
    never disagree. Returns a tz-aware datetime (naive last_ts coerced to UTC).
    """
    return _parse_ts(state.last_ts) + LADDER[state.interval_idx]
```

Then change `due` to call it. Replace the inline computation:

```python
        next_due = _parse_ts(st.last_ts) + LADDER[st.interval_idx]
        if now_dt >= next_due:
```

with:

```python
        if now_dt >= next_due_at(st):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest ken/tests/test_schedule.py -v`
Expected: PASS (new tests + all existing schedule tests still green — behavior preserved).

- [ ] **Step 5: Commit**

```bash
git add ken/src/ken/schedule.py ken/tests/test_schedule.py
git commit -m "feat(ken): add schedule.next_due_at (due delegates; single source)"
```

---

## Chunk 2: ken service — `_bound_questions` + `artifact_detail`

### Task 2: Extract `_bound_questions` helper (DRY, behavior-preserving)

**Files:**
- Modify: `ken/src/ken/service.py` (`due_items`, `ensure_questions`)
- Test: existing `ken/tests/test_service.py` + `ken-web/api/tests/test_api.py` cover behavior.

- [ ] **Step 1: Add the helper**

In `ken/src/ken/service.py`, add near the top of the module's helpers (after `find_ref`):

```python
def _bound_questions(ref: ArtifactRef, *, store: KenStore) -> list[Question] | None:
    """The artifact's questions IFF currently bound to its live content, else None.

    Mirrors the artifact-level stale gate used by coverage/due: questions missing,
    or whose stored store-hash != the artifact's current hash, mean nothing is bound
    (the artifact is an orphan / needs (re)generation).
    """
    store_hash, qs = store.load_questions(ref.artifact_id)
    if not qs or store_hash != ref.content_hash:
        return None
    return qs
```

Ensure `Question` is imported in `service.py` (it is used by `ensure_questions`; confirm the import line includes `Question`).

- [ ] **Step 2: Refactor `due_items` to use it**

Replace the body loop in `due_items`:

```python
    for ref in refs:
        store_hash, qs = store.load_questions(ref.artifact_id)
        if not qs or store_hash != ref.content_hash:
            out.append(DueLine(ref.artifact_id, True, []))
            continue
        states = rebuild(attempts, current_hashes={q.id: ref.content_hash for q in qs})
```

with:

```python
    for ref in refs:
        qs = _bound_questions(ref, store=store)
        if qs is None:
            out.append(DueLine(ref.artifact_id, True, []))
            continue
        states = rebuild(attempts, current_hashes={q.id: ref.content_hash for q in qs})
```

- [ ] **Step 3: Refactor `ensure_questions` to use it**

Replace:

```python
    store_hash, qs = store.load_questions(artifact_id)
    if not qs or store_hash != ref.content_hash:
        made = make_questions(Path(ref.path).read_text(encoding="utf-8"), n=n, llm=llm)
        store.save_questions(artifact_id, ref.content_hash, made)  # fail-loud
        _, qs = store.load_questions(artifact_id)  # reload with ids
    return qs
```

with:

```python
    qs = _bound_questions(ref, store=store)
    if qs is None:
        made = make_questions(Path(ref.path).read_text(encoding="utf-8"), n=n, llm=llm)
        store.save_questions(artifact_id, ref.content_hash, made)  # fail-loud
        _, qs = store.load_questions(artifact_id)  # reload with ids
    return qs
```

- [ ] **Step 4: Run tests to verify nothing broke**

Run: `python -m pytest ken/tests/test_service.py ken-web/api/tests/test_api.py -v`
Expected: PASS (pure refactor — existing coverage proves behavior preserved).

- [ ] **Step 5: Commit**

```bash
git add ken/src/ken/service.py
git commit -m "refactor(ken): _bound_questions helper (due_items/ensure_questions share gate)"
```

### Task 3: `QuestionDetail` + `artifact_detail`

**Files:**
- Modify: `ken/src/ken/service.py`
- Test: `ken/tests/test_service.py`

- [ ] **Step 1: Write the failing tests**

Add to `ken/tests/test_service.py`. Reuse its `_seed` + `ensure_questions` pattern; add an `att`-style helper for attempts. Import additions: `from ken.service import artifact_detail, QuestionDetail` and `from ken.models import Attempt`.

```python
def _answer(store, ref, qid, passed, ts):
    # append one attempt at the artifact's CURRENT content hash
    from ken.models import Attempt
    h = ref.content_hash
    store.append_attempt(Attempt("kr", ref.artifact_id, qid, h, passed, 1.0, ts))


def test_artifact_detail_unknown_raises(tmp_path):
    store, ref = _seed(tmp_path)
    import pytest
    with pytest.raises(KeyError):
        artifact_detail("nope", store=store, now="2026-06-01T00:00:00Z")


def test_artifact_detail_never_attempted_is_due_rung0(tmp_path):
    store, ref = _seed(tmp_path)
    ensure_questions(ref.artifact_id, store=store, llm=FakeLLM(responses=["Q1?"]), n=1)
    rows = artifact_detail(ref.artifact_id, store=store, now="2026-06-01T00:00:00Z")
    assert len(rows) == 1
    r = rows[0]
    assert r.attempted is False and r.rung == 0 and r.next_due is None
    assert r.last_passed is None and r.last_ts is None and r.fail_count == 0 and r.due is True


def test_artifact_detail_pass_advances_and_sets_next_due(tmp_path):
    store, ref = _seed(tmp_path)
    qs = ensure_questions(ref.artifact_id, store=store, llm=FakeLLM(responses=["Q1?"]), n=1)
    _answer(store, ref, qs[0].id, True, "2026-06-01T00:00:00Z")
    rows = artifact_detail(ref.artifact_id, store=store, now="2026-06-01T06:00:00Z")
    r = rows[0]
    assert r.attempted is True and r.rung == 1 and r.last_passed is True
    assert r.next_due == "2026-06-02T00:00:00+00:00"  # +1d ladder rung
    assert r.due is False  # 6h < 1d


def test_artifact_detail_fail_resets_and_counts(tmp_path):
    store, ref = _seed(tmp_path)
    qs = ensure_questions(ref.artifact_id, store=store, llm=FakeLLM(responses=["Q1?"]), n=1)
    _answer(store, ref, qs[0].id, False, "2026-06-01T00:00:00Z")
    rows = artifact_detail(ref.artifact_id, store=store, now="2026-06-05T00:00:00Z")
    r = rows[0]
    assert r.rung == 0 and r.fail_count == 1 and r.last_passed is False and r.due is True


def test_artifact_detail_stale_content_returns_empty(tmp_path):
    store, ref = _seed(tmp_path)
    ensure_questions(ref.artifact_id, store=store, llm=FakeLLM(responses=["Q1?"]), n=1)
    (tmp_path / "a.md").write_text("DIFFERENT content.\n", encoding="utf-8")  # bumps live hash
    rows = artifact_detail(ref.artifact_id, store=store, now="2026-06-01T00:00:00Z")
    assert rows == []  # stale gate == coverage orphan


def test_artifact_detail_no_questions_returns_empty(tmp_path):
    store, ref = _seed(tmp_path)  # registered, never generated
    rows = artifact_detail(ref.artifact_id, store=store, now="2026-06-01T00:00:00Z")
    assert rows == []
```

> **Note:** confirm the store's attempt-append method name (`append_attempt`) against `ken/src/ken/store.py` `KenStore` Protocol and `FileStore`; if it differs (e.g. `record_attempt`), use that name in `_answer`. Likewise confirm `_seed`'s `register_artifact` recomputes `content_hash` live so the stale test bumps it (it does — `test_ensure_questions_regenerates_when_stale` relies on the same).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest ken/tests/test_service.py -k artifact_detail -v`
Expected: FAIL with `ImportError: cannot import name 'artifact_detail'`.

- [ ] **Step 3: Write the implementation**

In `ken/src/ken/service.py`, add (after `list_artifacts`):

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
    next_due: str | None      # ISO-8601; None => never-attempted => due now
    due: bool


def artifact_detail(artifact_id: str, *, store: KenStore, now: str) -> list[QuestionDetail]:
    """Per-question schedule/mastery rows for one artifact. Read-only; no LLM.

    Returns [] when the artifact has no current questions or its questions are stale
    (artifact-level gate, matching coverage's `orphan` verdict). For a bound artifact,
    due-ness is exactly `schedule.due` (never re-derived here).
    """
    ref = find_ref(artifact_id, store=store)
    if ref is None:
        raise KeyError(artifact_id)
    qs = _bound_questions(ref, store=store)
    if qs is None:
        return []
    attempts = store.load_attempts()
    states = rebuild(attempts, current_hashes={q.id: ref.content_hash for q in qs})
    due_set = set(schedule_due(states, [q.id for q in qs], now=now))
    rows: list[QuestionDetail] = []
    for q in qs:
        st = states.get(q.id)
        if st is None:
            rows.append(QuestionDetail(
                question_id=q.id, text=q.text, rung=0, attempted=False,
                last_passed=None, last_ts=None, fail_count=0,
                next_due=None, due=q.id in due_set,
            ))
        else:
            rows.append(QuestionDetail(
                question_id=q.id, text=q.text, rung=st.interval_idx, attempted=True,
                last_passed=st.last_passed, last_ts=st.last_ts, fail_count=st.fail_count,
                next_due=next_due_at(st).isoformat(), due=q.id in due_set,
            ))
    return rows
```

> Confirm imports at the top of `service.py`: `rebuild`, `schedule_due` (the file already imports `due as schedule_due` — verify the alias name used in `due_items` and reuse it), and add `next_due_at`. Confirm `dataclass` is imported.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest ken/tests/test_service.py -k artifact_detail -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Run the full ken suite**

Run: `python -m pytest ken/tests/ -q`
Expected: PASS (no regressions).

- [ ] **Step 6: Commit**

```bash
git add ken/src/ken/service.py ken/tests/test_service.py
git commit -m "feat(ken): service.artifact_detail — per-question schedule rows (read-only)"
```

---

## Chunk 3: api — `GET /api/artifacts/{id}/detail`

### Task 4: DTO + endpoint

**Files:**
- Modify: `ken-web/api/src/ken_web_api/schemas.py`, `ken-web/api/src/ken_web_api/app.py`
- Test: `ken-web/api/tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `ken-web/api/tests/test_api.py` (reuse its `_client` helper):

```python
def test_detail_unknown_artifact_404(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, responses=[])
    assert c.get("/api/artifacts/nope/detail").status_code == 404


def test_detail_no_questions_empty(tmp_path, monkeypatch):
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    c = _client(tmp_path, monkeypatch, responses=[])  # FakeLLM raises if generation attempted
    aid = c.post("/api/artifacts", json={"path": str(art)}).json()["artifact_id"]
    res = c.get(f"/api/artifacts/{aid}/detail")
    assert res.status_code == 200 and res.json() == {"questions": []}


def test_detail_never_calls_llm(tmp_path, monkeypatch):
    # The detail handler must construct NO LLM. Make make_llm explode; /detail must still 200.
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    c = _client(tmp_path, monkeypatch, responses=["Q1?\nQ2?"])  # for /due only
    aid = c.post("/api/artifacts", json={"path": str(art)}).json()["artifact_id"]
    c.get(f"/api/artifacts/{aid}/due")  # generate 2 questions (consumes the response)

    def _boom():
        raise AssertionError("detail must not construct the LLM")
    monkeypatch.setattr(deps, "make_llm", _boom)

    res = c.get(f"/api/artifacts/{aid}/detail")
    assert res.status_code == 200
    body = res.json()
    assert len(body["questions"]) == 2
    q = body["questions"][0]
    assert set(q) == {"question_id", "text", "rung", "attempted", "last_passed",
                      "last_ts", "fail_count", "next_due", "due"}
    assert q["attempted"] is False and q["due"] is True and q["next_due"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest ken-web/api/tests/test_api.py -k detail -v`
Expected: FAIL (404 route not found → 404 test may pass coincidentally; the shape tests fail). Confirm `test_detail_no_questions_empty` fails with 404.

- [ ] **Step 3: Add the DTOs**

In `ken-web/api/src/ken_web_api/schemas.py`, add:

```python
class QuestionDetailOut(BaseModel):
    question_id: str
    text: str
    rung: int
    attempted: bool
    last_passed: bool | None = None
    last_ts: str | None = None
    fail_count: int
    next_due: str | None = None
    due: bool


class ArtifactDetailOut(BaseModel):
    questions: list[QuestionDetailOut]
```

- [ ] **Step 4: Add the endpoint**

In `ken-web/api/src/ken_web_api/app.py`, import `artifact_detail` is via `service.artifact_detail`. Add the route (place it near `get_due`); update the schemas import to include `ArtifactDetailOut, QuestionDetailOut`:

```python
@app.get("/api/artifacts/{artifact_id}/detail", response_model=ArtifactDetailOut)
def get_detail(artifact_id: str) -> ArtifactDetailOut:
    """Read-only per-question schedule rows. No generation, no LLM."""
    store = deps.make_store()
    try:
        rows = service.artifact_detail(artifact_id, store=store, now=service.now_iso())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown artifact_id: {artifact_id}") from exc
    return ArtifactDetailOut(
        questions=[
            QuestionDetailOut(
                question_id=r.question_id, text=r.text, rung=r.rung, attempted=r.attempted,
                last_passed=r.last_passed, last_ts=r.last_ts, fail_count=r.fail_count,
                next_due=r.next_due, due=r.due,
            )
            for r in rows
        ]
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest ken-web/api/tests/test_api.py -v`
Expected: PASS (new detail tests + existing flow test green).

- [ ] **Step 6: Commit**

```bash
git add ken-web/api/src/ken_web_api/schemas.py ken-web/api/src/ken_web_api/app.py ken-web/api/tests/test_api.py
git commit -m "feat(ken-web): GET /api/artifacts/{id}/detail (read-only, no LLM)"
```

---

## Chunk 4: web — types, client, MasteryLadder, ArtifactDetail page, routing

### Task 5: types + client

**Files:**
- Modify: `ken-web/web/src/types.ts`, `ken-web/web/src/api/client.ts`

- [ ] **Step 1: Add types**

In `ken-web/web/src/types.ts`, append (lockstep with the Pydantic DTOs):

```typescript
/** QuestionDetailOut — one per-question schedule row. next_due null ⇒ never-attempted ⇒ due now. */
export interface QuestionDetail {
  question_id: string;
  text: string;
  rung: number;            // 0..4, index into the ladder [now,1d,3d,7d,30d]
  attempted: boolean;
  last_passed: boolean | null;
  last_ts: string | null;
  fail_count: number;
  next_due: string | null;
  due: boolean;
}

/** ArtifactDetailOut — all per-question rows for one artifact. */
export interface ArtifactDetail {
  questions: QuestionDetail[];
}
```

- [ ] **Step 2: Add the client fn**

In `ken-web/web/src/api/client.ts`, import `ArtifactDetail` and add:

```typescript
/** GET /api/artifacts/{id}/detail — read-only per-question schedule rows (no generation). */
export function getArtifactDetail(artifactId: string): Promise<ArtifactDetail> {
  return request<ArtifactDetail>(`/api/artifacts/${encodeURIComponent(artifactId)}/detail`);
}
```

- [ ] **Step 3: Commit**

```bash
git add ken-web/web/src/types.ts ken-web/web/src/api/client.ts
git commit -m "feat(ken-web): web types + getArtifactDetail client"
```

### Task 6: `MasteryLadder` component

**Files:**
- Create: `ken-web/web/src/components/MasteryLadder.tsx`

- [ ] **Step 1: Create the component**

```tsx
// 5-pip mastery ladder. Index-aligned with ken.schedule.LADDER [0,1d,3d,7d,30d];
// keep LABELS in lockstep with that ladder so a future ladder change is caught here.
const LABELS = ["due now", "1d", "3d", "7d", "30d"] as const;

export default function MasteryLadder({ rung }: { rung: number }) {
  const clamped = Math.max(0, Math.min(rung, LABELS.length - 1));
  return (
    <span className="ladder" aria-label={`mastery ${clamped} of ${LABELS.length - 1} — ${LABELS[clamped]}`}>
      {LABELS.map((_, i) => (
        <span key={i} className={`ladder__pip ${i <= clamped ? "ladder__pip--on" : ""}`} aria-hidden="true" />
      ))}
      <span className="ladder__label">{LABELS[clamped]}</span>
    </span>
  );
}
```

- [ ] **Step 2: Add minimal styles**

Append to `ken-web/web/src/styles.css` (uses existing tokens — `--line-strong`, `--gold`, `--paper-faint`, `--mono`):

```css
/* mastery ladder — 5 pips, index-aligned with ken.schedule.LADDER [now,1d,3d,7d,30d] */
.ladder {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.ladder__pip {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--line-strong);
}
.ladder__pip--on {
  background: var(--gold);
}
.ladder__label {
  margin-left: 8px;
  font-family: var(--mono);
  font-size: 0.72rem;
  color: var(--paper-faint);
}
```

- [ ] **Step 3: Commit**

```bash
git add ken-web/web/src/components/MasteryLadder.tsx ken-web/web/src/styles.css
git commit -m "feat(ken-web): MasteryLadder component"
```

### Task 7: `ArtifactDetail` page + tests

**Files:**
- Create: `ken-web/web/src/pages/ArtifactDetail.tsx`
- Create: `ken-web/web/tests/artifact-detail.test.tsx`

- [ ] **Step 1: Write the failing test**

Model on `ken-web/web/tests/home.test.tsx` (mock `../src/api/client`, render with `MemoryRouter` at `/artifact/:id`). Cover: renders a row per question with ladder + overdue badge for `due&&attempted`, "due now" for never-attempted, fail-count pill when `fail_count>0`, empty state when `questions:[]`, and a "Start review" link to `/review?artifact=<id>`.

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";

// Explicit factory (matches home.test.tsx convention — mock every export used).
vi.mock("../src/api/client", () => ({
  getArtifactDetail: vi.fn(),
}));

import * as client from "../src/api/client";
import ArtifactDetail from "../src/pages/ArtifactDetail";

const getArtifactDetail = client.getArtifactDetail as unknown as ReturnType<typeof vi.fn>;

function renderAt(id: string) {
  return render(
    <MemoryRouter initialEntries={[`/artifact/${id}`]}>
      <Routes>
        <Route path="/artifact/:id" element={<ArtifactDetail />} />
        <Route path="/review" element={<div>review route</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ArtifactDetail", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders a row per question with overdue + never-attempted states", async () => {
    getArtifactDetail.mockResolvedValue({
      questions: [
        { question_id: "q1", text: "Q one?", rung: 0, attempted: false, last_passed: null,
          last_ts: null, fail_count: 0, next_due: null, due: true },
        { question_id: "q2", text: "Q two?", rung: 2, attempted: true, last_passed: false,
          last_ts: "2026-06-01T00:00:00Z", fail_count: 3, next_due: "2026-06-02T00:00:00+00:00", due: true },
      ],
    });
    renderAt("a1");
    expect(await screen.findByText("Q one?")).toBeInTheDocument();
    expect(screen.getByText("Q two?")).toBeInTheDocument();
    expect(screen.getByText(/overdue/i)).toBeInTheDocument();   // q2 attempted && due
    expect(screen.getByText(/3/)).toBeInTheDocument();          // fail count
  });

  it("links Start review to the artifact's review flow", async () => {
    getArtifactDetail.mockResolvedValue({ questions: [] });
    renderAt("a1");
    const cta = await screen.findByRole("link", { name: /start review/i });
    expect(cta).toHaveAttribute("href", expect.stringContaining("/review?artifact=a1"));
  });

  it("shows empty state when no questions", async () => {
    getArtifactDetail.mockResolvedValue({ questions: [] });
    renderAt("a1");
    expect(await screen.findByText(/no .*questions/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ken-web/web && npx vitest run tests/artifact-detail.test.tsx`
Expected: FAIL (module `../pages/ArtifactDetail` not found).

- [ ] **Step 3: Write the page**

Create `ken-web/web/src/pages/ArtifactDetail.tsx`. Mirror `Home.tsx` structure (status state machine: loading skeleton / error / ready; `useParams` for `id`; load via `getArtifactDetail`). Render header with a `Link` "Start review →" to `/review?artifact=<id>`; per-question rows with `MasteryLadder rung`, last-attempt chip (pass/fail + `last_ts`, or "never attempted"), next-due (show `overdue` badge when `due && attempted`, "due now" when `!attempted`), and a fail-count pill when `fail_count > 0`. Empty state: "No current questions — start a review to generate them." Use existing CSS classes (`stack`, `row`, `pill`, `state`, `btn btn--primary`) for visual consistency.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ken-web/web && npx vitest run tests/artifact-detail.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ken-web/web/src/pages/ArtifactDetail.tsx ken-web/web/tests/artifact-detail.test.tsx
git commit -m "feat(ken-web): ArtifactDetail tracking page"
```

### Task 8: route + Home row → detail

**Files:**
- Modify: `ken-web/web/src/App.tsx`, `ken-web/web/src/pages/Home.tsx`, `ken-web/web/tests/home.test.tsx`

- [ ] **Step 1: Add a row-click test to the Home suite**

`home.test.tsx` currently has **no** row-click test (only the cover "Start review" button → `/review`). **Add** a new test (do not change the existing one). First add an artifact-detail stub route to `renderHome`'s `<Routes>` and a stub component (uses the already-imported `useLocation`):

```tsx
function ArtifactStub() {
  const loc = useLocation();
  return <div>artifact route: {loc.pathname}</div>;
}
// inside renderHome()'s <Routes>, add:
//   <Route path="/artifact/:id" element={<ArtifactStub />} />
```

Then add the test (the artifact row is a `<button className="row">` containing the basename `payment.md`; clicking that text fires the row's onClick):

```tsx
it("clicking an artifact row routes to its detail page", async () => {
  const user = userEvent.setup();
  renderHome();
  await user.click(await screen.findByText("payment.md"));
  expect(await screen.findByText("artifact route: /artifact/art-1")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd ken-web/web && npx vitest run tests/home.test.tsx`
Expected: FAIL (row still routes to `/review`).

- [ ] **Step 3: Add the route**

In `ken-web/web/src/App.tsx`, import `ArtifactDetail` and add inside `<Routes>`:

```tsx
        <Route path="/artifact/:id" element={<ArtifactDetail />} />
```

- [ ] **Step 4: Change Home row click**

In `ken-web/web/src/pages/Home.tsx`, change the row handler from `review(a.artifact_id)` to navigate to the detail page:

```tsx
                onClick={() => navigate(`/artifact/${encodeURIComponent(a.artifact_id)}`)}
```

Leave the cover "Start review →" button (`review(startTarget)`) unchanged.

- [ ] **Step 5: Run web tests**

Run: `cd ken-web/web && npx vitest run`
Expected: PASS (home + artifact-detail + review all green).

- [ ] **Step 6: Commit**

```bash
git add ken-web/web/src/App.tsx ken-web/web/src/pages/Home.tsx ken-web/web/tests/home.test.tsx
git commit -m "feat(ken-web): /artifact/:id route; Home row -> detail funnel"
```

---

## Final verification

- [ ] **Run all suites**

```bash
python -m pytest ken/tests/ ken-web/api/tests/ -q
cd ken-web/web && npx vitest run && npm run build
```
Expected: all green; SPA builds.

- [ ] **Lint/type (match CI)**

Run ruff + the web typecheck/lint the CI uses (mirror the workflow). Expected: clean.

- [ ] **Push branch + open PR** (`feat/ken-web-s5-dashboard`), wait for CI 9 jobs green, then merge (per the project workflow). Optionally extend `ken-web/docs/e2e-2026-06-23.md` with a detail-page pass once a key is available.
