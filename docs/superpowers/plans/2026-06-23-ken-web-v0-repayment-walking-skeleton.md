# ken-web v0.1 — Repayment Web Walking Skeleton — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A browser-driven vertical slice of ken's repayment loop — register an artifact → server generates grounded questions → user answers in a React SPA → server grades + returns remediation → coverage updates — across React → FastAPI → ken-core → LLM.

**Architecture:** New monorepo module `ken-web/` = `api/` (FastAPI over ken-core, server-side `AnthropicLLM`) + `web/` (React+Vite+TS SPA). ken-core gains a `service.py` orchestration layer shared by the CLI (extraction, behavior unchanged) and the API (plus new single-question grade + remediation). Reuse ken file storage (no Postgres). Single team, no auth.

**Tech Stack:** Python 3.13 / FastAPI / uvicorn / pydantic v2 / pytest (+TestClient); React 18 / Vite / TypeScript / vitest + React Testing Library. LLM via ken's `AnthropicLLM`/`FakeLLM` seam.

**Spec:** `docs/superpowers/specs/2026-06-23-ken-web-v0-repayment-walking-skeleton-design.md`

**Invariants:** grade LLM failure → **fail-closed** (`passed=False`); storage write → **fail-loud** (raise/5xx); remediation LLM failure → `remediation=None`, **never block recording**; `person` informational (not used in derivation); **API key never reaches the client**; FakeLLM in all automated tests (no live key).

---

## File structure

```
ken/src/ken/service.py        # NEW: orchestration (extraction + new grade_answer/remediate)
ken/src/ken/cli.py            # MODIFY: call service.* (behavior unchanged; 8 tests green)
ken/tests/test_service.py     # NEW
ken-web/api/
  pyproject.toml              # ken (path dep) + fastapi, uvicorn, httpx(test)
  src/ken_web_api/app.py      # FastAPI app + 5 routes
  src/ken_web_api/schemas.py  # pydantic DTOs
  src/ken_web_api/deps.py     # storage paths + LLM factory (_make_llm seam)
  tests/test_api.py           # TestClient + FakeLLM
ken-web/web/
  package.json, vite.config.ts, tsconfig.json, index.html
  src/api/client.ts           # typed fetch wrapper
  src/types.ts                # shared DTO types
  src/pages/Home.tsx          # coverage + start-review + attention list
  src/pages/Review.tsx        # the repayment session (core UX)
  src/components/{QuestionCard,RemediationPanel,ProgressBar,CoverageBadge}.tsx
  src/App.tsx, src/main.tsx, src/styles.css
  tests/review.test.tsx       # vitest + RTL flow
README.md (ken-web)           # run guide (dev proxy / prod serve)
```

---

## Chunk 1: ken-core `service.py` (extraction + new cognition)

### Task 1: extract shared orchestration into `service.py`

**Files:** Create `ken/src/ken/service.py`; Test `ken/tests/test_service.py`

- [ ] **Step 1: failing tests** (LLM via FakeLLM; tmp stores)
```python
from ken.llm import FakeLLM
from ken.service import ensure_questions, due_items, coverage_report, register_artifact

def _seed(tmp_path):
    art = tmp_path/"a.md"; art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    man = tmp_path/"m.yaml"; ref = register_artifact(str(art), manifest=str(man))
    return man, ref

def test_ensure_questions_generates_when_missing(tmp_path):
    man, ref = _seed(tmp_path); qs_store = tmp_path/"q.json"
    qs = ensure_questions(ref.artifact_id, manifest=str(man), questions_store=str(qs_store),
                          llm=FakeLLM(responses=["Q1?\nQ2?\nQ3?"]), n=3)
    assert [q.text for q in qs] == ["Q1?","Q2?","Q3?"] and all(q.id for q in qs)

def test_ensure_questions_regenerates_when_stale(tmp_path):
    man, ref = _seed(tmp_path); qs_store = tmp_path/"q.json"
    ensure_questions(ref.artifact_id, manifest=str(man), questions_store=str(qs_store),
                     llm=FakeLLM(responses=["OLD?"]), n=1)
    (tmp_path/"a.md").write_text("CHANGED content now.\n", encoding="utf-8")  # hash changes
    man2, _ = _seed.__wrapped__ if False else (man, None)  # re-register not needed; register updates? -> re-register
    from ken.registry import register as reg
    ref2 = reg(str(tmp_path/"a.md"), manifest_path=str(man))   # idempotent on path; hash recomputed live
    qs = ensure_questions(ref.artifact_id, manifest=str(man), questions_store=str(qs_store),
                          llm=FakeLLM(responses=["NEW?"]), n=1)
    assert [q.text for q in qs] == ["NEW?"]

def test_coverage_report_zero_when_unanswered(tmp_path):
    man, ref = _seed(tmp_path); qs_store = tmp_path/"q.json"; led = tmp_path/"l.jsonl"
    ensure_questions(ref.artifact_id, manifest=str(man), questions_store=str(qs_store),
                     llm=FakeLLM(responses=["Q1?"]), n=1)
    rep = coverage_report(manifest=str(man), questions_store=str(qs_store), ledger=str(led))
    assert rep.total == 1 and rep.covered == 0 and rep.orphans == [ref.artifact_id]
```
*(Note: `registry.current_hash` is computed live; re-registering the same path is idempotent and the manifest entry's hash is read live in coverage/ensure — confirm against registry.py while implementing; the stale test asserts regeneration after content change.)*

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement `service.py`** — move the orchestration out of `cli.py`:
```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ken.attempt import append_attempt, load_attempts
from ken.coverage import compute_coverage_v1
from ken.judge import grade as judge_grade
from ken.llm import LLMClient
from ken.models import Attempt, ArtifactRef, Question, Verdict, CoverageReport
from ken.probe import make_questions
from ken.questions import load_questions, save_questions
from ken.registry import current_hash, load_manifest, register as registry_register
from ken.schedule import due as schedule_due, rebuild

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def find_ref(manifest: str, artifact_id: str) -> ArtifactRef | None:
    return next((r for r in load_manifest(manifest) if r.artifact_id == artifact_id), None)

def register_artifact(path: str, *, manifest: str) -> ArtifactRef:
    return registry_register(path, manifest_path=manifest)

def ensure_questions(artifact_id, *, manifest, questions_store, llm: LLMClient, n) -> list[Question]:
    ref = find_ref(manifest, artifact_id)
    if ref is None:
        raise KeyError(artifact_id)
    store_hash, qs = load_questions(artifact_id, store_path=questions_store)
    if not qs or store_hash != ref.content_hash:
        made = make_questions(Path(ref.path).read_text(encoding="utf-8"), n=n, llm=llm)
        save_questions(artifact_id, ref.content_hash, made, store_path=questions_store)  # fail-loud
        _, qs = load_questions(artifact_id, store_path=questions_store)  # reload with ids
    return qs

@dataclass(frozen=True)
class DueLine:
    artifact_id: str
    needs_questions: bool
    questions: list  # list[tuple[qid, text]] when not needs_questions

def due_items(*, manifest, questions_store, ledger, now) -> list[DueLine]:
    refs = load_manifest(manifest); attempts = load_attempts(ledger); out = []
    for ref in refs:
        store_hash, qs = load_questions(ref.artifact_id, store_path=questions_store)
        if not qs or store_hash != ref.content_hash:
            out.append(DueLine(ref.artifact_id, True, [])); continue
        states = rebuild(attempts, current_hashes={q.id: ref.content_hash for q in qs})
        due_ids = schedule_due(states, [q.id for q in qs], now=now)
        tbid = {q.id: q.text for q in qs}
        out.append(DueLine(ref.artifact_id, False, [(qid, tbid[qid]) for qid in due_ids]))
    return out

def grade_set(artifact_text, qa_pairs, *, llm: LLMClient) -> Verdict:
    return judge_grade(artifact_text, qa_pairs, llm=llm)

def coverage_report(*, manifest, questions_store, ledger) -> CoverageReport:
    refs = load_manifest(manifest); attempts = load_attempts(ledger)
    qmap = {r.artifact_id: load_questions(r.artifact_id, store_path=questions_store) for r in refs}
    return compute_coverage_v1(refs, qmap, attempts)
```
- [ ] **Step 4:** run → PASS. **Step 5:** commit `feat(ken): service.py — shared orchestration (extraction)`.

### Task 2: refactor `cli.py` to use `service.py` (no behavior change)

**Files:** Modify `ken/src/ken/cli.py`

- [ ] **Step 1:** Run the existing CLI suite to capture green baseline: `cd ken && python -m pytest tests/test_cli_v1.py -q` → all pass.
- [ ] **Step 2:** Refactor `due` to call `service.due_items(...)` and print the same lines (`needs-questions {id}` / `due {id} {qid} {text}`). Refactor `coverage` to call `service.coverage_report(...)` (same output). Refactor `review` to use `service.ensure_questions(...)` + `service.grade_set(...)` (keep the set-grade-applied-to-each-question behavior verbatim). Leave `register`/`save-questions`/`record-attempt` as-is (thin) or route through `service.register_artifact`. Keep `_make_llm`.
- [ ] **Step 3:** Run `cd ken && python -m pytest -q` → **all 50 still green** (no output/behavior change).
- [ ] **Step 4:** commit `refactor(ken/cli): call service.py (behavior unchanged)`.

### Task 3: NEW — single-question `grade_answer` + `remediate`

**Files:** Modify `ken/src/ken/service.py`; Test `ken/tests/test_service.py`

- [ ] **Step 1: failing tests**
```python
from ken.service import grade_answer, remediate
class _Boom:
    def generate(self, s, u): raise RuntimeError("llm down")

def test_grade_answer_pass_records(tmp_path):
    man, ref = _seed(tmp_path); qs_store=tmp_path/"q.json"; led=tmp_path/"l.jsonl"
    qs = ensure_questions(ref.artifact_id, manifest=str(man), questions_store=str(qs_store),
                          llm=FakeLLM(responses=["Q1?"]), n=1)
    res = grade_answer(ref.artifact_id, qs[0].id, "a good answer", person="kr",
                       manifest=str(man), questions_store=str(qs_store), ledger=str(led),
                       llm=FakeLLM(responses=['{"passed": true, "score": 0.9, "rationale": "ok"}']),
                       now="2026-06-23T00:00:00Z")
    assert res.passed and res.remediation is None
    from ken.attempt import load_attempts
    assert len(load_attempts(str(led))) == 1

def test_grade_answer_fail_includes_remediation(tmp_path):
    man, ref = _seed(tmp_path); qs_store=tmp_path/"q.json"; led=tmp_path/"l.jsonl"
    qs = ensure_questions(ref.artifact_id, manifest=str(man), questions_store=str(qs_store),
                          llm=FakeLLM(responses=["Q1?"]), n=1)
    # FakeLLM returns verdict (fail) then remediation text, in call order
    res = grade_answer(ref.artifact_id, qs[0].id, "wrong", person="kr",
                       manifest=str(man), questions_store=str(qs_store), ledger=str(led),
                       llm=FakeLLM(responses=['{"passed": false, "score": 0.1, "rationale": "no"}',
                                              "Here is why: the service publishes orders..."]),
                       now="2026-06-23T00:00:00Z")
    assert res.passed is False and res.remediation and "publishes" in res.remediation

def test_grade_answer_fail_closed_on_grade_llm_error(tmp_path):
    man, ref = _seed(tmp_path); qs_store=tmp_path/"q.json"; led=tmp_path/"l.jsonl"
    qs = ensure_questions(ref.artifact_id, manifest=str(man), questions_store=str(qs_store),
                          llm=FakeLLM(responses=["Q1?"]), n=1)
    res = grade_answer(ref.artifact_id, qs[0].id, "x", person="kr", manifest=str(man),
                       questions_store=str(qs_store), ledger=str(led), llm=_Boom(),
                       now="2026-06-23T00:00:00Z")
    assert res.passed is False  # fail-closed; attempt still recorded

def test_remediation_llm_failure_yields_none_but_records(tmp_path):
    man, ref = _seed(tmp_path); qs_store=tmp_path/"q.json"; led=tmp_path/"l.jsonl"
    qs = ensure_questions(ref.artifact_id, manifest=str(man), questions_store=str(qs_store),
                          llm=FakeLLM(responses=["Q1?"]), n=1)
    # one-shot llm: verdict fail, then raises on the remediation call
    class _FailRemediate:
        def __init__(self): self.calls = 0
        def generate(self, s, u):
            self.calls += 1
            if self.calls == 1: return '{"passed": false, "score": 0.0, "rationale": "no"}'
            raise RuntimeError("remediation down")
    res = grade_answer(ref.artifact_id, qs[0].id, "x", person="kr", manifest=str(man),
                       questions_store=str(qs_store), ledger=str(led), llm=_FailRemediate(),
                       now="2026-06-23T00:00:00Z")
    assert res.passed is False and res.remediation is None
    from ken.attempt import load_attempts
    assert len(load_attempts(str(led))) == 1  # recorded despite remediation failure
```
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** in `service.py`:
```python
@dataclass(frozen=True)
class AttemptResult:
    passed: bool
    score: float
    remediation: str | None

def remediate(artifact_text, question_text, answer, *, llm: LLMClient) -> str | None:
    sys_p = ("You are tutoring a developer who answered a comprehension question wrong. "
             "Using ONLY the artifact, explain the correct understanding concisely and "
             "concretely. No preamble.")
    user = f"ARTIFACT:\n{artifact_text}\n\nQUESTION: {question_text}\nTHEIR ANSWER: {answer}"
    try:
        return llm.generate(sys_p, user).strip() or None
    except Exception:
        return None  # never block recording on remediation failure

def grade_answer(artifact_id, question_id, answer, *, person, manifest, questions_store,
                 ledger, llm: LLMClient, now) -> AttemptResult:
    ref = find_ref(manifest, artifact_id)
    if ref is None:
        raise KeyError(artifact_id)
    _, qs = load_questions(artifact_id, store_path=questions_store)
    q = next((x for x in qs if x.id == question_id), None)
    if q is None:
        raise KeyError(question_id)
    text = Path(ref.path).read_text(encoding="utf-8")
    try:
        verdict = judge_grade(text, [(q.text, answer)], llm=llm)
    except Exception:
        verdict = Verdict(passed=False, score=0.0, rationale="grade_error")  # fail-closed
    append_attempt(Attempt(person=person, artifact_id=artifact_id, question_id=question_id,
                           content_hash=ref.content_hash, passed=verdict.passed,
                           score=verdict.score, ts=now), ledger_path=ledger)  # fail-loud
    rem = None if verdict.passed else remediate(text, q.text, answer, llm=llm)
    return AttemptResult(passed=verdict.passed, score=verdict.score, remediation=rem)
```
*(Note: `judge.grade` already catches its own LLM/parse errors and returns a fail-closed Verdict; the extra try/except is belt-and-suspenders — confirm against judge.py and drop if redundant.)*
- [ ] **Step 4:** run → PASS; full `cd ken && pytest -q` green. **Step 5:** commit `feat(ken): single-question grade_answer + remediate (API cognition)`.

### Task 4 (review checkpoint): add a `list_artifacts` status helper

**Files:** Modify `ken/src/ken/service.py`; Test `ken/tests/test_service.py`
- [ ] **Step 1:** failing test: `list_artifacts(...)` returns one row per manifest ref with `status` ("orphan" if in `coverage_report().orphans` else "vouched") and `weak_count` (sum of `weakness[].fail_count` for that artifact).
- [ ] **Step 2-4:** implement using `coverage_report` (no new derivation), test green, commit `feat(ken): list_artifacts status helper`.

---

## Chunk 2: `ken-web/api` (FastAPI)

### Task 5: scaffold the API package

**Files:** Create `ken-web/api/pyproject.toml`, `src/ken_web_api/__init__.py`, `deps.py`
- [ ] **Step 1:** `pyproject.toml` — name `ken-web-api`, requires-python ">=3.13", deps `["ken", "fastapi>=0.115", "uvicorn>=0.30"]`, dev `["pytest>=8","httpx>=0.27","ruff>=0.5"]`, `[tool.setuptools.packages.find] where=["src"]`, pytest `pythonpath=["src"]`. ken is a **path dependency**: `[tool.uv.sources]` or install editable both (`pip install -e ../../ken -e .`). Document the install in README; tests assume `ken` importable.
- [ ] **Step 2:** `deps.py` — central config: storage paths (env-overridable: `KEN_MANIFEST`, `KEN_QUESTIONS`, `KEN_LEDGER`, default under a `KEN_DATA_DIR`), `N_QUESTIONS`, and `make_llm() -> LLMClient` (returns `AnthropicLLM()`; **the test seam** — tests monkeypatch `ken_web_api.deps.make_llm`).
- [ ] **Step 3:** commit `feat(ken-web/api): scaffold package + deps`.

### Task 6: schemas + the 5 endpoints (TDD with FakeLLM)

**Files:** Create `src/ken_web_api/schemas.py`, `src/ken_web_api/app.py`; Test `tests/test_api.py`
- [ ] **Step 1: failing tests** (TestClient; monkeypatch `deps.make_llm` to FakeLLM; tmp data dir via env/fixture)
```python
from fastapi.testclient import TestClient
from ken.llm import FakeLLM
from ken_web_api.app import app
from ken_web_api import deps

def _client(tmp_path, monkeypatch, responses):
    monkeypatch.setenv("KEN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(deps, "make_llm", lambda: FakeLLM(responses=responses))
    return TestClient(app)

def test_register_due_attempt_coverage_flow(tmp_path, monkeypatch):
    art = tmp_path/"a.md"; art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    c = _client(tmp_path, monkeypatch, responses=["Q1?\nQ2?",  # due -> generate
                                                  '{"passed": true, "score": 0.9, "rationale":"ok"}'])
    aid = c.post("/api/artifacts", json={"path": str(art)}).json()["artifact_id"]
    due = c.get(f"/api/artifacts/{aid}/due").json()
    assert len(due["questions"]) == 2
    qid = due["questions"][0]["question_id"]
    res = c.post("/api/attempts", json={"artifact_id": aid, "question_id": qid,
                                        "person": "kr", "answer": "good"}).json()
    assert res["passed"] is True and res["remediation"] is None
    cov = c.get("/api/coverage").json()
    assert cov["total"] == 1

def test_attempt_fail_returns_remediation(tmp_path, monkeypatch):
    art = tmp_path/"a.md"; art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    c = _client(tmp_path, monkeypatch, responses=["Q1?",
        '{"passed": false, "score": 0.1, "rationale":"no"}', "Because it publishes orders."])
    aid = c.post("/api/artifacts", json={"path": str(art)}).json()["artifact_id"]
    qid = c.get(f"/api/artifacts/{aid}/due").json()["questions"][0]["question_id"]
    res = c.post("/api/attempts", json={"artifact_id": aid, "question_id": qid,
                                        "person":"kr", "answer":"wrong"}).json()
    assert res["passed"] is False and "publishes" in res["remediation"]
```
Also tests: `GET /api/artifacts` shape; storage-write failure → 5xx (point KEN_DATA_DIR at an unwritable path); unknown artifact_id → 404.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** `schemas.py` (pydantic v2: `RegisterReq{path}`, `ArtifactOut{artifact_id,path,status,weak_count}`, `DueOut{questions:[{question_id,text}]}`, `AttemptReq{artifact_id,question_id,person,answer}`, `AttemptOut{passed,score,remediation}`, `CoverageOut{...}`) and `app.py` (the 5 routes, each calling `service.*` with paths from `deps`, `llm=deps.make_llm()`; map `KeyError`→404; storage `OSError`→500). `GET /due` calls `service.ensure_questions` (regenerate on missing/stale) then `due_items` for that artifact. No CORS needed if same-origin in prod; add permissive CORS for dev (localhost:5173) behind a flag.
- [ ] **Step 4:** run → PASS; ruff clean. **Step 5:** commit `feat(ken-web/api): 5 endpoints over ken.service (FakeLLM-tested)`.

---

## Chunk 3: `ken-web/web` (React + Vite SPA) — the repayment UX

> Use the **frontend-design** skill for this chunk: production-grade, distinctive, NOT generic AI aesthetics. UX (flow, immediacy, sense of progress) is the product's core value.

### Task 7: scaffold Vite + React + TS

**Files:** `ken-web/web/{package.json,vite.config.ts,tsconfig.json,index.html,src/main.tsx,src/App.tsx,src/styles.css}`
- [ ] **Step 1:** Scaffold Vite React-TS. `vite.config.ts` proxies `/api` → `http://localhost:8000` in dev. Add `vitest` + `@testing-library/react` + jsdom.
- [ ] **Step 2:** `src/types.ts` mirroring the API DTOs; `src/api/client.ts` typed `fetch` wrapper (`getArtifacts`, `registerArtifact`, `getDue`, `postAttempt`, `getCoverage`).
- [ ] **Step 3:** commit `feat(ken-web/web): scaffold Vite+React+TS + api client`.

### Task 8: Review flow (core UX) — TDD with mocked client

**Files:** `src/pages/Review.tsx`, `src/components/{QuestionCard,RemediationPanel,ProgressBar}.tsx`; Test `tests/review.test.tsx`
- [ ] **Step 1: failing flow test** (RTL; mock `src/api/client`): render `Review` for an artifact whose `getDue` returns 2 questions; answer Q1 → `postAttempt` resolves `{passed:true}` → advances to Q2 (progress "2 / 2"); answer Q2 → `postAttempt` resolves `{passed:false, remediation:"..."}` → **RemediationPanel shows the text**; click "I've reviewed this" → session summary appears.
- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3: implement** `Review.tsx` state machine (load due → per-question: input → submit → grading → pass(advance)/fail(remediation→acknowledge→requeue) → end:summary) + the components. Apply frontend-design (typography, spacing, motion on transitions, clear pass/fail affordances, calm remediation panel). One question at a time; visible progress.
- [ ] **Step 4:** run → PASS. **Step 5:** commit `feat(ken-web/web): repayment Review flow + components`.

### Task 9: Home (coverage + selection)

**Files:** `src/pages/Home.tsx`, `src/components/CoverageBadge.tsx`; extend `tests/`
- [ ] **Step 1:** failing test: `Home` renders coverage ("0 / 1 vouched") from mocked `getCoverage`+`getArtifacts`, lists attention items, and **Start review** routes to `/review?artifact={firstOrphan}`.
- [ ] **Step 2-4:** implement (frontend-design), test green, commit `feat(ken-web/web): Home — coverage + start-review selection`.

---

## Chunk 4: wiring, docs, manual e2e

### Task 10: prod serve + dev proxy + README
**Files:** `ken-web/api/src/ken_web_api/app.py` (mount built SPA), `ken-web/README.md`
- [ ] **Step 1:** In prod, FastAPI serves `ken-web/web/dist` as static (StaticFiles) at `/`, API under `/api` (single origin → no CORS). Dev uses Vite proxy. Guard the static mount so it's optional when `dist` absent (tests/dev).
- [ ] **Step 2:** `README.md` — run guide: `pip install -e ken -e ken-web/api`, `uvicorn ken_web_api.app:app`, `cd ken-web/web && npm i && npm run dev`; prod `npm run build` + serve. Note `ANTHROPIC_API_KEY` required for real LLM (tests use FakeLLM).
- [ ] **Step 3:** commit `feat(ken-web): prod static serve + dev proxy + README`.

### Task 11: manual e2e walkthrough (note)
**Files:** `ken-web/docs/e2e-2026-06-23.md`
- [ ] **Step 1:** With server `ANTHROPIC_API_KEY` set, run API+web, register one khala artifact, answer in browser, observe pass/fail+remediation + coverage move. If no key available in this env, record the steps as **pending** (do not fabricate). Capture screenshots/notes.
- [ ] **Step 2:** commit `docs(ken-web): manual e2e walkthrough`.

---

## Notes / discipline
- **CI:** add a `ken-web-api (pytest)` job (mirror ken) and a `ken-web (vitest)` job in a follow-up (or fold into this branch's CI edit) so the new module is CI-covered. *(Recommended; flag in PR.)*
- Fail-closed (grade) / fail-loud (storage) / remediation→None each have a dedicated test.
- API key never sent to client; `person` informational; FakeLLM in all automated tests.
- ken's 50 existing tests stay green after the cli refactor (Task 2 gate).
