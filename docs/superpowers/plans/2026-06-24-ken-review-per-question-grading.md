# ken review per-question grading — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `ken review` record a true per-question verdict for each question (fixing the v1 weakness-map regression where one whole-set verdict was stamped onto every question).

**Architecture:** Reuse the existing, tested `service.grade_answer` once per question inside an inline tutoring loop in `cli.review`; retire the now-dead `service.grade_set`. No new service surface, no derivation changes.

**Tech Stack:** Python 3.11, Typer CLI, pytest, ruff, `FakeLLM` test double (no API key).

**Spec:** `docs/superpowers/specs/2026-06-24-ken-review-per-question-grading-design.md`

---

## File Structure

- `ken/src/ken/cli.py` — `review` command rewritten; `from pathlib import Path` import removed (becomes unused).
- `ken/src/ken/service.py` — `grade_set` deleted.
- `ken/tests/test_cli_v1.py` — `test_review_headless_with_fake_llm` rewritten + new mixed pass/fail regression test.

No other files change (no schema, no API, no web).

---

## Chunk 1: review grades per-question

### Task 1: Rewrite the review test for per-question grading (RED)

**Files:**
- Test: `ken/tests/test_cli_v1.py` (replace `test_review_headless_with_fake_llm`, ~line 166-192)

Context the worker needs:
- `FakeLLM(responses=[...])` pops responses **strictly in order** (`ken/src/ken/llm.py`).
- Call order for a review: (1) one question-generation call (`ensure_questions` → `probe.make_questions`), then per question (2) one grade call, and (3) **only if that question failed**, one remediation call. So a passing question consumes 1 response, a failing question consumes 2.
- Question ids are derived `make_question_id(aid, h, index)` where `h = current_hash(art_path)` (see existing helpers `_register` and `_current_hash`, and `make_question_id` import at top of the test file).
- `review` reads answers from stdin, one line per question, via the runner's `input=` parameter.

- [ ] **Step 1: Replace the existing whole-set test with the per-question version**

Replace `test_review_headless_with_fake_llm` (currently lines ~166-192) with:

```python
def test_review_headless_records_per_question(tmp_path, monkeypatch):
    man = tmp_path / "m.yaml"
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes the orders topic.\n", encoding="utf-8")
    aid = _register(man, art)
    store = tmp_path / "q.json"
    ledger = tmp_path / "l.jsonl"
    h = _current_hash(art)

    # Call order: probe(1) -> grade Q1 pass(1) -> grade Q2 fail(1) -> remediate Q2(1)
    monkeypatch.setattr(
        "ken.cli._make_llm",
        lambda: FakeLLM(responses=[
            "Q1?\nQ2?",
            '{"passed": true,  "score": 0.9, "rationale": "ok"}',
            '{"passed": false, "score": 0.1, "rationale": "no"}',
            "study the orders topic section",
        ]),
    )
    r = runner.invoke(
        app,
        ["review", aid, "--as", "kr", "--manifest", str(man),
         "--questions", str(store), "--ledger", str(ledger)],
        input="answer1\nanswer2\n",
    )
    assert r.exit_code == 0, r.stdout
    assert "study the orders topic section" in r.stdout  # remediation surfaced for the failed Q

    q1_id = make_question_id(aid, h, 0)
    q2_id = make_question_id(aid, h, 1)

    r = runner.invoke(
        app,
        ["coverage", "--as", "kr", "--manifest", str(man),
         "--questions", str(store), "--ledger", str(ledger)],
    )
    # one artifact, Q2 last-failed -> orphan -> 0/1 (per-artifact coverage)
    assert "0/1" in r.stdout
    # the discriminator: per-question recording means ONLY Q2 is in the weakness map
    assert q2_id in r.stdout
    assert q1_id not in r.stdout
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd ken && python -m pytest tests/test_cli_v1.py::test_review_headless_records_per_question -v`
Expected: FAIL. With today's whole-set code, the FakeLLM script mis-aligns (whole-set makes only 1 grade call, not per-question), and/or the weakness map lists both/neither question, so `q1_id not in r.stdout` (or `0/1`) fails.

---

### Task 2: Rewrite `review` to grade per question (GREEN)

**Files:**
- Modify: `ken/src/ken/cli.py` — `review` command (body at ~line 186-222) and the `from pathlib import Path` import (~line 15).

- [ ] **Step 1: Replace the body of `review`**

Replace from `text = Path(ref.path).read_text(encoding="utf-8")` down through the final `typer.echo(f"recorded {len(qs)} attempts ...")` with:

```python
    llm = _make_llm()
    qs = service.ensure_questions(artifact_id, store=store, llm=llm, n=n)
    ts = _now()  # one snapshot for the session; all attempts share ts

    passed_n = 0
    for q in qs:
        typer.echo(q.text)
        answer = input()
        res = service.grade_answer(
            artifact_id, q.id, answer,
            person=person, store=store, llm=llm, now=ts,
        )
        typer.echo(f"  {'pass' if res.passed else 'fail'} (score={res.score})")
        if not res.passed and res.remediation:
            typer.echo(f"  remediation: {res.remediation}")
        passed_n += int(res.passed)

    failed_n = len(qs) - passed_n
    typer.echo(
        f"recorded {len(qs)} attempts for {artifact_id} "
        f"({passed_n} passed, {failed_n} failed)"
    )
```

Keep the lines above unchanged: the `_find_ref` existence check (prints `unknown artifact_id`, exit 1) stays. Delete the old `text = Path(ref.path).read_text(...)`, the old `service.grade_set(...)` call, and the old `for q in qs: store.append_attempt(Attempt(...))` loop.

- [ ] **Step 2: Remove the now-unused `Path` import**

In `ken/src/ken/cli.py`, delete `from pathlib import Path` (line ~15). Verify `Path` is used nowhere else in the file (it is not — `review` was the only user). `Attempt` is still imported and used by `record_attempt_cmd`, so leave the models import alone.

- [ ] **Step 3: Run the new test to verify it passes**

Run: `cd ken && python -m pytest tests/test_cli_v1.py::test_review_headless_records_per_question -v`
Expected: PASS.

---

### Task 3: Delete the dead `grade_set` (GREEN/refactor)

**Files:**
- Modify: `ken/src/ken/service.py` — delete `grade_set` (~line 88-89).

Context: grep confirmed `grade_set` is referenced only by `cli.review` (now removed) and tests/plan-docs. `judge.grade` (which it wrapped) stays — `grade_answer` calls it per question.

- [ ] **Step 1: Delete `grade_set`**

Remove:
```python
def grade_set(artifact_text: str, qa_pairs, *, llm: LLMClient) -> Verdict:
    return judge_grade(artifact_text, qa_pairs, llm=llm)
```

- [ ] **Step 2: Verify nothing references it**

Run: `cd ken && grep -rn "grade_set" src tests`
Expected: no matches in `src/` or `tests/` (matches in `docs/` plan/spec history are fine and out of scope).

If `Verdict` import in `service.py` becomes unused after the deletion, remove it too. Check: `grep -n "Verdict" src/ken/service.py` — if the only hit was the deleted signature, drop `Verdict` from the `from ken.models import ...` line. (`grade_answer` uses the local `verdict` variable but the return type is `AttemptResult`, so `Verdict` may indeed become unused — verify and clean up.)

---

### Task 4: Full suite green + lint + commit

- [ ] **Step 1: Run the whole ken test suite**

Run: `cd ken && python -m pytest -q`
Expected: all pass (the keyless-loop tests `due`/`save-questions`/`record-attempt`/`coverage` are untouched and stay green).

- [ ] **Step 2: Lint**

Run: `cd ken && ruff check src tests`
Expected: clean (in particular, no unused-import warning for `Path`/`Verdict`).

- [ ] **Step 3: Commit**

```bash
git add ken/src/ken/cli.py ken/src/ken/service.py ken/tests/test_cli_v1.py
git commit -m "feat(ken): headless review grades per-question (retire grade_set)"
```

---

## Done criteria

- `ken review` records a distinct per-question verdict; weakness map reflects exactly the failed questions.
- `grade_set` removed; no `src/`/`tests/` references remain.
- `cd ken && python -m pytest -q` green; `ruff check` clean.
- No changes outside `cli.py` / `service.py` / `test_cli_v1.py`.
