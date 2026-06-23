# Design Spec — ken engine v2 / Slice A: headless `review` grades per-question

- **Date:** 2026-06-24
- **Status:** Design (brainstorming output) — pending spec review + user approval
- **Builds on:** ken v0/v1 + ken-web v0.1 + S2 Postgres (all merged, #29–#37). First of three independent "engine v2 friction" slices (A here; B path/install, C calendar-TTL deferred to their own spec→plan→PR).
- **Decisions locked:** Reuse the existing `service.grade_answer` per question (no new service surface); **retire `service.grade_set`** (becomes dead code); **inline tutoring** loop shape (per question: prompt → read answer → grade → on fail, show remediation). Out of scope: B (path/install), C (calendar TTL), and the `input()` interactivity of `review`.

---

## 1. Goal

Make the headless `ken review` command record **true per-question verdicts** so the v1 weakness map reflects reality, instead of stamping one whole-set verdict onto every question.

## 2. The bug (why this slice exists)

`cli.review` (`ken/src/ken/cli.py`: whole-set grade at line 203, per-question write loop at 209–221) grades the entire answer set as **one** verdict via `service.grade_set`, then writes that same `passed`/`score` to **every** question's attempt:

```python
verdict = service.grade_set(text, qa_pairs, llm=llm)        # ONE verdict for all answers
...
for q in qs:
    store.append_attempt(Attempt(..., passed=verdict.passed, score=verdict.score, ...))
```

v1's headline feature is **per-question mastery** (the spaced-repetition ladder and the weakness map are keyed per question). The whole-set collapse means: a reviewer who answers 4/5 correctly is recorded as 5/5 pass (if the set scores as pass) or 5/5 fail — the weakness map, ladder progression, and coverage all consume fabricated per-question data. This is a correctness regression specific to the headless path.

The agent-driven keyless loop (`record-attempt`) and the ken-web API (`service.grade_answer`) already record per-question. **Only `review` regressed.**

## 3. Key insight (why this is small)

`service.grade_answer(artifact_id, question_id, answer, *, person, store, llm, now)` (`ken/src/ken/service.py:113`) **already does exactly the right thing for one question**:

- grades that single answer via `judge.grade` (**fail-closed** internally: LLM/parse error → `passed=False, score=0.0`),
- records the attempt **fail-loud** (IO errors propagate), with the attempt written **before** remediation so a remediation failure can't block recording,
- on fail, returns a grounded `remediation` (`None` on any remediation LLM failure).

So the fix is **reuse, not new code**: `review` loops over `grade_answer`, one call per question. All the invariants we need already live in `grade_answer` / `judge` / the store — nothing about them changes.

## 4. Design

### 4.1 `cli.review` — inline per-question loop

Replace the collect-then-whole-set-grade body with an inline tutoring loop:

```python
qs = service.ensure_questions(artifact_id, store=store, llm=llm, n=n)
ts = _now()                       # one snapshot for the whole session (attempts share ts, as today)

passed_n = 0
for q in qs:
    typer.echo(q.text)
    answer = input()
    res = service.grade_answer(
        artifact_id, q.id, answer,
        person=person, store=store, llm=llm, now=ts,
    )
    mark = "pass" if res.passed else "fail"
    typer.echo(f"  {mark} (score={res.score})")
    if not res.passed and res.remediation:
        typer.echo(f"  remediation: {res.remediation}")
    passed_n += int(res.passed)

typer.echo(f"recorded {len(qs)} attempts for {artifact_id} ({passed_n} passed, {len(qs) - passed_n} failed)")
```

Notes:
- The existence check (`_find_ref` → unknown-id error, exit 1) and `ensure_questions` are unchanged.
- `review` no longer reads the artifact text itself — `grade_answer` reads it per call (the artifact is small; a CLI review is ~5 questions). The previously-local `text = Path(ref.path).read_text(...)` line (`cli.py:192`) is removed; `from pathlib import Path` becomes unused in `cli.py` and must be removed too (ruff would flag it).
- `now=ts` is passed once so all attempts in a session share one timestamp, matching today's behavior. `ts` is captured **after** `ensure_questions` (as today, where `_now()` runs after the LLM round-trips), not before.
- **Two acknowledged behavior deltas vs today (both harmless):** (a) `grade_answer` re-derives the live `content_hash` per call (via `find_ref`) instead of one snapshot — identical in practice (the file is not edited mid-review). (b) The artifact text is read once per question instead of once per session. Both accepted for DRY; documented so they aren't a surprise.

### 4.2 `service.grade_set` — retire

`grade_set` (`ken/src/ken/service.py:88`) is used **only** by `cli.review` (confirmed by grep: the sole non-test reference). Once `review` switches to `grade_answer`, `grade_set` is dead code → **delete it**. `judge.grade` (the whole-set grader it wrapped) stays — `grade_answer` calls it with a single `(question, answer)` pair, which is the correct per-question use.

## 5. Data flow (after)

```
ken review <aid> --as <person>
  → ensure_questions          (generate/regenerate questions if missing or stale)
  → per question:
       input() answer
       grade_answer            → judge.grade (fail-closed)
                               → store.append_attempt (fail-loud, per-question verdict)
                               → remediate on fail (None on failure)
  → summary line
  → coverage/weakness/ladder now reflect TRUE per-question results
```

## 6. Error handling (unchanged invariants)

All preserved because they already live in the reused code:

- **Grade fail-closed:** any LLM or parse error → `Verdict(passed=False, score=0.0)` (in `judge.grade`; `grade_answer` does not re-wrap it).
- **Store fail-loud:** `append_attempt` IO error propagates (no swallow).
- **Remediation never blocks recording:** attempt is recorded before remediation; remediation failure → `None`.
- **Keyless / no API key for tests:** the only LLM-calling path is still `review` (via `_make_llm`); the agent-driven primitives and all tests use `FakeLLM`.

## 7. Testing (no API key — `FakeLLM`)

Rewrite `tests/test_cli_v1.py::test_review_headless_with_fake_llm` (it currently scripts `[questions, verdict_json]` for the whole-set path) and add a mixed pass/fail regression test.

**FakeLLM call order (verified against source).** `FakeLLM` pops scripted responses strictly in order (`llm.py:52–55`). The exact call sequence for a 2-question review where Q1 passes and Q2 fails is:
1. `ensure_questions` → `make_questions` → **1 call** (question generation).
2. per question, `grade_answer` → `judge.grade` → **1 call** to grade; then **only if that verdict failed**, `remediate` → **1 more call**. So a **passing** question = 1 call (grade only); a **failing** question = 2 calls (grade, then remediate).

The concrete script for the regression test (do **not** insert a remediation slot after the passing Q1 — that would mis-align every later pop):

```python
FakeLLM(responses=[
    "Q1?\nQ2?",                                              # (1) probe / question generation
    '{"passed": true,  "score": 0.9, "rationale": "ok"}',   # (2) grade Q1 -> pass, no remediation
    '{"passed": false, "score": 0.1, "rationale": "no"}',   # (3) grade Q2 -> fail
    "remediation text for Q2",                               # (4) remediate Q2
])
```

**Regression assertions (the core of this slice).** Derive the two question ids the same way the existing tests do: `q1_id = make_question_id(aid, h, 0)`, `q2_id = make_question_id(aid, h, 1)` (cf. `test_cli_v1.py:93,112`). After the `review` run, run `ken coverage` and assert on its output:
- **`q2_id in stdout` (weakness map) AND `q1_id not in stdout`.** The negative assertion is the one that actually catches the bug: the *old* whole-set code stamped one verdict on both questions, so it would list *both* (or *neither*) — only the per-question fix lists exactly Q2. Asserting merely that Q2 appears does not discriminate.
- **Coverage `covered/total` is `0/1`** — coverage is **per-artifact**, not per-question (`coverage.compute_coverage_v1`: `total = len(artifacts)`, an artifact is `covered` only if `is_vouched` over *all* its questions). One artifact whose Q2 last-failed is an orphan → `0/1`. (`1/2` is impossible with one artifact; the all-pass case is `1/1`, as the existing test already asserts at `test_cli_v1.py:192`.)

**Remediation surfaced:** assert the Q2 remediation text appears in `review` stdout.

Existing keyless-loop tests (`due`/`save-questions`/`record-attempt`/`coverage`) stay green untouched. The grading path for tests is `FakeLLM` only; no `ANTHROPIC_API_KEY` is required by CI.

## 8. YAGNI / scope discipline

- **No new service function.** Reuse `grade_answer`; delete `grade_set`.
- **No change to derivations** (`schedule`, `vouch`, `coverage`) — they already consume per-question attempts correctly; they were just being fed bad data.
- B (path/install), C (calendar TTL), and non-interactive answer input are explicitly **not** in this slice.

## 9. Files touched

- `ken/src/ken/cli.py` — rewrite `review` body (inline per-question loop; drop local `text` read at line 192; remove the now-unused `from pathlib import Path` import).
- `ken/src/ken/service.py` — delete `grade_set`.
- `ken/tests/test_cli_v1.py` — rewrite `test_review_headless_with_fake_llm` + add mixed pass/fail regression test.
- (No schema, no API, no web changes.)
