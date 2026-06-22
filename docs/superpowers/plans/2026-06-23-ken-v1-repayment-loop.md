# `ken` v1 — Cognitive-Debt Repayment Loop — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn ken from a meter into a repayment loop — vouch becomes *derived* from per-question mastery, with spaced repetition, remediation, and a weakness map; the Claude Code agent supplies cognition (keyless) over ken's deterministic substrate.

**Architecture:** Incremental on ken v0 (branch `feat/ken-v1-repayment`, based on `feat/ken-cognitive-debt-meter`; stacked PR base = v0 branch). New pure unit `schedule` (the ledger→states reducer + spaced repetition), new IO units `questions` and `attempt` (both fail-loud), `vouch`/`coverage` refactored to *derive* state from the attempt ledger, `cli` extended with agent primitives. Reuse v0 `registry`/`hashing`/`llm`/`probe`/`judge`.

**Tech Stack:** Python 3.11+, Typer, pytest, PyYAML/JSON files (no DB).

**Spec:** `docs/superpowers/specs/2026-06-23-ken-v1-repayment-loop-design.md`

**Key invariants:** attempt + questions store **fail-loud** (raise); `record-attempt` **append-only** (state recomputed on read); `save-questions` **replace-on-save + hash-checked**; derivations **pure** with explicit `now`; **no git** dependency.

---

## File structure (delta on v0)

```
ken/src/ken/
  models.py     # MODIFY: Question gains `id`; add Attempt, ReviewState, WeaknessItem; extend CoverageReport
  questions.py  # NEW: save_questions/load_questions (hash-bound, replace, fail-loud)
  attempt.py    # NEW: append_attempt (fail-loud) / load_attempts
  schedule.py   # NEW (pure): LADDER, next_state, rebuild(attempts)->states, due
  vouch.py      # MODIFY: add derived is_vouched(...); retire one-shot record_vouch/vouch_log
  coverage.py   # MODIFY: derive from questions+attempts; add weakness map
  cli.py        # MODIFY: add due/save-questions/record-attempt; rework coverage; keep headless review
  probe.py, judge.py, llm.py, registry.py, hashing.py   # REUSE unchanged
ken/docs/review-protocol.md   # NEW: the agent-driven loop (prose)
ken/tests/  test_questions.py, test_attempt.py, test_schedule.py,
            test_vouch_derived.py, test_coverage_v1.py, test_cli_v1.py   # + update test_vouch.py/test_coverage.py
```

---

## Chunk 1: substrate (models, questions, attempt, schedule)

### Task 1: models — Question.id, Attempt, ReviewState, weakness, CoverageReport

**Files:** Modify `ken/src/ken/models.py`; Test `ken/tests/test_models_v1.py`

- [ ] **Step 1: failing test**
```python
from ken.models import Question, Attempt, ReviewState
def test_question_has_id():
    q = Question(id="abc123", text="why?")
    assert q.id == "abc123"
def test_attempt_roundtrip():
    a = Attempt(person="kr", artifact_id="a1", question_id="q1",
                content_hash="sha256:x", passed=True, score=0.9, ts="2026-06-23T00:00:00Z")
    assert Attempt.from_dict(a.to_dict()) == a
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** in models.py:
  - Add `id: str` to `Question` (before `text`). All `Question(...)` construction must use keyword args (probe.py already does); verify no positional `Question("...")` remains.
  - `Attempt` (frozen) `(person, artifact_id, question_id, content_hash, passed, score, ts)` + `to_dict`/`from_dict`.
  - `ReviewState` (frozen) `(question_id, content_hash, interval_idx, last_ts, last_passed, fail_count)` — a *computed* view (not persisted).
  - Extend `CoverageReport` with `weakness: list[WeaknessItem]` where `WeaknessItem(question_id, artifact_id, fail_count)`. (Keep `orphans` for back-compat.)
- [ ] **Step 4:** run → PASS. **Step 5:** commit `feat(ken): v1 models (Question.id, Attempt, ReviewState, weakness)`.

### Task 2: questions store (hash-bound, replace, fail-loud)

**Files:** Create `ken/src/ken/questions.py`; Test `ken/tests/test_questions.py`

- [ ] **Step 1: failing tests**
```python
from ken.questions import save_questions, load_questions, make_question_id
from ken.models import Question
def test_save_load_roundtrip_replaces(tmp_path):
    store = tmp_path / "q.json"
    save_questions("a1", "sha256:h1", [Question(id="x", text="q1")], store_path=store)
    save_questions("a1", "sha256:h2", [Question(id="y", text="q2")], store_path=store)  # replace
    h, qs = load_questions("a1", store_path=store)
    assert h == "sha256:h2" and [q.text for q in qs] == ["q2"]
def test_make_question_id_stable():
    assert make_question_id("a1", "sha256:h", 0) == make_question_id("a1", "sha256:h", 0)
    assert make_question_id("a1", "sha256:h", 0) != make_question_id("a1", "sha256:h", 1)
def test_save_fails_loud(tmp_path):
    import pytest
    with pytest.raises(OSError):
        save_questions("a1","h",[Question(id="x",text="q")], store_path=tmp_path/"no"/"q.json", make_parents=False)
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** `questions.py`:
  - `make_question_id(artifact_id, content_hash, index) -> sha256(f"{artifact_id}:{content_hash}:{index}")[:12]`.
  - Store = a JSON object `{artifact_id: {"content_hash": h, "questions": [{"id","text"}, ...]}}`. `save_questions` **replaces** the artifact's entry (keyed by artifact_id), assigns ids via `make_question_id` if missing, **fail-loud** write. `load_questions(artifact_id)` → `(hash, [Question])` or `(None, [])` if absent.
- [ ] **Step 4:** run → PASS. **Step 5:** commit `feat(ken): hash-bound questions store (replace, fail-loud)`.

### Task 3: attempt ledger (append-only, fail-loud)

**Files:** Create `ken/src/ken/attempt.py`; Test `ken/tests/test_attempt.py`

- [ ] **Step 1: failing tests** (mirror v0 vouch ledger tests)
```python
from ken.attempt import append_attempt, load_attempts
from ken.models import Attempt
def mk(passed=True, ts="2026-06-23T00:00:00Z", qid="q1"):
    return Attempt("kr","a1",qid,"sha256:h",passed,0.9,ts)
def test_append_then_load(tmp_path):
    p = tmp_path/"att.jsonl"; append_attempt(mk(), ledger_path=p); append_attempt(mk(passed=False), ledger_path=p)
    got = load_attempts(p); assert len(got) == 2 and got[1].passed is False
def test_append_fails_loud(tmp_path):
    import pytest
    with pytest.raises(OSError):
        append_attempt(mk(), ledger_path=tmp_path/"no"/"a.jsonl", make_parents=False)
def test_load_absent_is_empty(tmp_path):
    assert load_attempts(tmp_path/"absent.jsonl") == []
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** `attempt.py` — same shape as v0 `vouch.record_vouch`/`load_vouches` but for `Attempt`; **append-only, fail-loud**.
- [ ] **Step 4:** run → PASS. **Step 5:** commit `feat(ken): append-only fail-loud attempt ledger`.

### Task 4: schedule (pure reducer + spaced repetition) — LOAD-BEARING

**Files:** Create `ken/src/ken/schedule.py`; Test `ken/tests/test_schedule.py`

- [ ] **Step 1: failing tests**
```python
from ken.schedule import LADDER, rebuild, due
from ken.models import Attempt
def att(qid, passed, ts, h="sha256:cur"):
    return Attempt("kr","a1",qid,h,passed,1.0,ts)
def test_pass_advances_fail_resets():
    atts = [att("q",True,"2026-06-01T00:00:00Z"), att("q",True,"2026-06-02T00:00:00Z"),
            att("q",False,"2026-06-03T00:00:00Z")]
    st = rebuild(atts, current_hashes={"q":"sha256:cur"})["q"]
    assert st.interval_idx == 0 and st.last_passed is False and st.fail_count == 1
def test_next_due_is_last_ts_plus_ladder():
    atts = [att("q",True,"2026-06-01T00:00:00Z")]  # idx becomes 1 -> +1d
    states = rebuild(atts, current_hashes={"q":"sha256:cur"})
    assert "q" not in due(states, ["q"], now="2026-06-01T12:00:00Z")  # 12h < 1d
    assert "q" in due(states, ["q"], now="2026-06-03T00:00:00Z")      # >1d
def test_never_attempted_is_due():
    # a question with no state (never attempted / stale) is ALWAYS due — due owns this
    assert due({}, ["qNew"], now="2026-06-01T00:00:00Z") == ["qNew"]
def test_hash_change_resets_state():
    atts = [att("q",True,"2026-06-01T00:00:00Z",h="sha256:OLD")]
    st = rebuild(atts, current_hashes={"q":"sha256:NEW"})
    assert "q" not in st  # OLD-hash attempts ignored -> no state -> treated as never-attempted
def test_orphan_question_ignored():
    atts = [att("gone",True,"2026-06-01T00:00:00Z")]
    assert rebuild(atts, current_hashes={"q":"sha256:cur"}) == {}  # 'gone' not in current set
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** `schedule.py`:
  - `LADDER = [timedelta(0), timedelta(days=1), timedelta(days=3), timedelta(days=7), timedelta(days=30)]`.
  - `rebuild(attempts, *, current_hashes: dict[qid,hash]) -> dict[qid, ReviewState]`: for each `question_id` present in `current_hashes`, take only its attempts whose `content_hash == current_hashes[qid]`, sort by `ts`, fold: pass → `idx = min(idx+1, len-1)`; fail → `idx = 0, fail_count += 1`. Track `last_ts`, `last_passed`. Questions with no surviving attempts get **no** state entry (caller treats absence as never-attempted = not vouched & due).
  - `due(states, all_qids, *, now) -> list[qid]`: takes the **full question-id universe**. A qid is due iff it is **absent from `states`** (never-attempted / stale-hash → due) OR `_parse_ts(now) >= _parse_ts(last_ts) + LADDER[interval_idx]`. Reuse `vouch._parse_ts` for tz-safe parsing. **`due` owns never-attempted surfacing** — callers never re-derive it.
  - `next_state(state, attempt) -> state` is the per-attempt fold used internally by `rebuild` (covered via `rebuild` tests).
- [ ] **Step 4:** run → PASS. **Step 5:** commit `feat(ken): pure spaced-repetition reducer (rebuild/next_state/due)`.

---

## Chunk 2: derivation, cli, docs, dogfood

### Task 5: derived vouch

**Files:** Modify `ken/src/ken/vouch.py`; Test `ken/tests/test_vouch_derived.py`

- [ ] **Step 1: failing tests**
```python
from ken.vouch import is_vouched
from ken.models import Question, Attempt
from ken.schedule import rebuild
def att(qid, passed, ts, h="sha256:cur"):   # local helper (each test file defines its own)
    return Attempt("kr","a1",qid,h,passed,1.0,ts)
def test_all_pass_vouched():
    qs=[Question(id="q1",text="a"),Question(id="q2",text="b")]
    atts=[att("q1",True,"2026-06-20T00:00:00Z"),att("q2",True,"2026-06-20T00:00:00Z")]
    states=rebuild(atts,current_hashes={"q1":"sha256:cur","q2":"sha256:cur"})
    assert is_vouched(qs, states) is True
def test_zero_attempt_question_blocks():
    qs=[Question(id="q1",text="a"),Question(id="q2",text="b")]
    atts=[att("q1",True,"2026-06-20T00:00:00Z")]  # q2 never attempted
    states=rebuild(atts,current_hashes={"q1":"sha256:cur","q2":"sha256:cur"})
    assert is_vouched(qs, states) is False
def test_failed_question_blocks():
    qs=[Question(id="q1",text="a")]
    atts=[att("q1",False,"2026-06-20T00:00:00Z")]
    states=rebuild(atts,current_hashes={"q1":"sha256:cur"})
    assert is_vouched(qs, states) is False
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** `is_vouched(questions, states) -> bool`: True iff **every** question has a state with `last_passed is True` (missing state = never-attempted = block). Hash staleness is already handled by `rebuild` (stale-hash attempts ignored → no state → block). **v1 has no calendar TTL** (refines spec §1/§6 — TTL deferred; staleness = hash change + fail-on-retest), so `is_vouched` takes no `now`. Keep `vouch._parse_ts` (used by `schedule.due`).
- [ ] **Step 4:** run → PASS. **Step 5:** commit `feat(ken): derived is_vouched from per-question mastery`. (Deletion of the superseded v0 one-shot vouch happens in Task 7 per the Final v0 surface list.)

### Task 6: coverage + weakness map

**Files:** Modify `ken/src/ken/coverage.py`; Test `ken/tests/test_coverage_v1.py`

- [ ] **Step 1: failing test**
```python
from ken.coverage import compute_coverage_v1
from ken.models import ArtifactRef, Question, Attempt
def att(qid, passed, ts, h="sha256:cur"):   # local helper
    return Attempt("kr","a1",qid,h,passed,1.0,ts)
def test_coverage_and_weakness():
    arts=[ArtifactRef("a1","/a","sha256:cur")]
    qmap={"a1":("sha256:cur",[Question(id="q1",text="x"),Question(id="q2",text="y")])}
    atts=[att("q1",True,"2026-06-20T00:00:00Z"),
          att("q2",False,"2026-06-20T00:00:00Z"),att("q2",False,"2026-06-20T01:00:00Z")]
    rep=compute_coverage_v1(arts, qmap, atts)
    assert rep.total==1 and rep.covered==0 and rep.orphans==["a1"]
    assert any(w.question_id=="q2" and w.fail_count==2 for w in rep.weakness)
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** `compute_coverage_v1(artifacts, questions_by_artifact, attempts) -> CoverageReport`: per artifact, build `current_hashes` from its questions (all = the artifact's current hash), `rebuild`, then `is_vouched`. covered/orphans accordingly. **weakness = lifetime `fail_count` from `ReviewState`** per current-hash question (matches `ReviewState.fail_count`). No `now` (no TTL). Delete the v0 `compute_coverage` (see Final v0 surface).
- [ ] **Step 4:** run → PASS. **Step 5:** commit `feat(ken): v1 coverage with weakness map`.

### Task 7: cli — agent primitives + headless review

**Files:** Modify `ken/src/ken/cli.py`; Test `ken/tests/test_cli_v1.py`

- [ ] **Step 1: failing e2e tests** (Typer `CliRunner`; FakeLLM via `_make_llm` monkeypatch as in v0)
```python
# due: a registered artifact with no questions shows as needs-questions
# save-questions: rejects wrong --hash; stores on correct hash
# record-attempt: appends; coverage reflects it
# coverage: shows covered/total + weakness
# review (headless): FakeLLM yields questions then verdict; vouch derived to covered
```
Write concrete tests for: `save-questions --hash WRONG` exits non-zero; `record-attempt --passed` then `coverage` shows movement; `due` lists `needs-questions` for an artifact with no saved questions; **`due` lists saved-but-unanswered question ids as due** (questions-exist-zero-attempts — distinct from needs-questions and from due-after-elapse).
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** cli commands (paths via options `--manifest/--questions/--ledger`):
  - `due --as PERSON` — load manifest; for each artifact load questions; artifacts with **no** saved questions (or stored store-hash ≠ current hash) → print `needs-questions <artifact_id>`; else `rebuild(attempts, current_hashes)` then `due(states, all_qids=[q.id for q in questions], now)` → print due `(artifact_id, question_id, text)`. (Never-attempted saved questions surface via `due`'s full-id-set contract.)
  - `save-questions ARTIFACT_ID --hash H` — **reject** if `H != registry.current_hash(path)`; read questions from stdin (one per line or JSON), `save_questions`.
  - `record-attempt --as P --question QID --artifact AID (--passed|--failed) [--score]` — build `Attempt(ts=utc now)`, `append_attempt`. Append-only.
  - `coverage [--as P]` — load manifest+questions+attempts, `compute_coverage_v1`, print covered/total + weakness.
  - `review --as P [ARTIFACT_ID]` — **headless**: `_make_llm()` (AnthropicLLM), for due/needs questions use `probe.make_questions`/`judge.grade`, record attempts. Reuses v0 seam; tested with FakeLLM.
  - Remove the v0 one-shot `probe`→`record_vouch` cli command (superseded). See **Final v0 surface after v1** below for the exact delete list.
- [ ] **Step 4:** run full suite `cd ken && python -m pytest -q` → PASS. **Step 5:** commit `feat(ken): cli agent primitives (due/save-questions/record-attempt) + headless review`.

### Task 8: agent review protocol doc

**Files:** Create `ken/docs/review-protocol.md`

- [ ] **Step 1:** Write the prose loop (from spec §4): `ken due` → generate+`save-questions` for needs-questions → present → grade → on fail show grounded explanation → `record-attempt` → `ken coverage`. State the "present each question at most once per run" rule and that cognition (questions/grading/explanations) is the agent's job (keyless).
- [ ] **Step 2:** commit `docs(ken): agent-driven review protocol`.

### Task 9: dogfood (agent-driven, keyless)

**Files:** Create `ken/docs/dogfood-v1-2026-06-23.md`

- [ ] **Step 1:** Using the existing `ken.manifest.yaml`, run the agent-driven loop on ONE artifact: the agent (this session) generates grounded questions from the artifact's real content → `ken save-questions` → answer (director) → agent grades → `ken record-attempt` (pass and a deliberate fail to show remediation+weakness) → `ken coverage`. Capture: questions, the weakness entry from a failed item, and coverage movement. No API key used.
- [ ] **Step 2:** Write the dogfood doc (what ran, outputs verbatim, friction notes). Commit `chore(ken): v1 dogfood — agent-driven keyless review`.

---

## Final v0 surface after v1 (exact delete/keep list — reach the Task 7 green gate without guessing)

**Delete** (superseded by the attempt ledger + derived vouch):
- `models.py`: `Vouch` dataclass.
- `vouch.py`: `record_vouch`, `load_vouches`, `is_fresh` (no TTL in v1). **Keep** `_parse_ts` (used by `schedule.due`); **add** `is_vouched`.
- `coverage.py`: v0 `compute_coverage` (replaced by `compute_coverage_v1`).
- `cli.py`: the v0 `probe` command and any `record_vouch` call.
- Tests: delete `test_vouch.py` (v0 freshness+persistence) → replaced by `test_vouch_derived.py`; delete `test_coverage.py` (v0) → replaced by `test_coverage_v1.py`; delete `test_cli_e2e.py` (v0 probe→vouch flow) → replaced by `test_cli_v1.py`.

**Keep & reuse unchanged:** `registry.py`, `hashing.py`, `llm.py`, `probe.py`, `judge.py`, `models.ArtifactRef`/`Question`(+id)/`Verdict`/`CoverageReport`(extended), `test_hashing_parity.py`, `test_registry.py`, `test_probe.py`, `test_judge.py`, `test_models.py` (+ new `test_models_v1.py`).

After Task 7, `cd ken && python -m pytest -q` must be fully green with no dangling imports.

## Notes / discipline
- Pure (`schedule`, `is_vouched`, `compute_coverage_v1`) never import IO/LLM; `now` is explicit where used (`due`).
- Fail-loud: `append_attempt`, `save_questions`. Append-only attempts; state recomputed via `rebuild`.
- No git anywhere. Headless `review` is the only LLM-calling path and is FakeLLM-tested.
- v1 retires v0's one-shot vouch; update/remove the superseded v0 tests rather than leaving dead asserts.
