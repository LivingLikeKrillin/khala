# `ken` Cognitive-Debt Meter (v0) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `ken` v0 — a CLI that measures whether a named human can *vouch* for an artifact via graded, grounded questions (bound to a content hash, with staleness), and reports org-level cognitive-debt coverage + an orphan hotlist.

**Architecture:** New Python module `ken/` in the khala monorepo, mirroring `mutqa/` (src layout, pure-function core + thin IO/LLM edges, file-based ledger). Pure units (`hashing`, `models`, `vouch.is_fresh`, `coverage`) are deterministic-tested; LLM units (`probe`, `judge`) sit behind a small `LLMClient` protocol and are tested with a fake. Vouches persist to an append-only JSONL ledger (fail-loud). First consumer = khala dogfood.

**Tech Stack:** Python 3.11+, Typer (CLI), pytest, anthropic SDK (behind a wrapper), PyYAML (manifest). No DB in v0.

**Spec:** `docs/superpowers/specs/2026-06-23-ken-cognitive-debt-meter-design.md`

**Two deliberate refinements of the spec (consistent with its "manifest-first / defer schema" principle):**
1. **Persistence = file-based JSONL ledger** (like `mutqa`'s ledger), not a Postgres `vouch_log` table. Fail-loud is preserved (a write that fails raises). The DB table + `v_cognitive_debt` view graduate together in v1.
2. **`content_hash` is vendored** into `ken/hashing.py` (8 lines) rather than imported across sibling modules, with a **parity test** asserting byte-identical output to `specledger.hashing.content_hash` to catch drift. Avoids cross-module path coupling in the monorepo.

---

## File structure (locked)

```
ken/
├── pyproject.toml                  # mirrors mutqa: src layout, pytest pythonpath
├── README.md                       # one-paragraph what/why + CLI usage
├── src/ken/
│   ├── __init__.py
│   ├── hashing.py                  # vendored content_hash (parity-tested vs specledger)
│   ├── models.py                   # dataclasses: ArtifactRef, Question, Verdict, Vouch, CoverageReport
│   ├── registry.py                 # manifest read/write; register(path); current_hash(path)
│   ├── vouch.py                    # record_vouch (append JSONL, fail-loud); load_vouches; is_fresh (pure)
│   ├── coverage.py                 # pure aggregation: manifest + vouches -> CoverageReport
│   ├── llm.py                      # LLMClient Protocol + AnthropicLLM impl (mirrors nexus LLMService)
│   ├── probe.py                    # make_questions(text, n, llm) -> list[Question]
│   ├── judge.py                    # grade(text, qa_pairs, llm) -> Verdict  (fail-closed)
│   └── cli.py                      # Typer: register / probe --as / coverage
├── ken.manifest.yaml               # checked-in registry (artifact_id -> path)
└── tests/
    ├── conftest.py                 # FakeLLM fixture, tmp ledger/manifest fixtures
    ├── fixtures/sample_artifact.md
    ├── test_hashing_parity.py
    ├── test_models.py
    ├── test_registry.py
    ├── test_vouch.py
    ├── test_coverage.py
    ├── test_probe.py
    ├── test_judge.py
    └── test_cli_e2e.py
```

Each file has one responsibility; pure logic (`hashing`, `models`, `is_fresh`, `coverage`) is import-free of IO/LLM and independently testable.

---

## Chunk 1: ken v0 walking skeleton

### Task 1: Scaffold the `ken` module

**Files:**
- Create: `ken/pyproject.toml`, `ken/src/ken/__init__.py`, `ken/README.md`, `ken/tests/conftest.py`

- [ ] **Step 1: Create `ken/pyproject.toml`** (mirror mutqa)

```toml
[project]
name = "ken"
version = "0.1.0"
description = "Cognitive-debt meter — measures whether a named human can vouch for an artifact"
requires-python = ">=3.11"
dependencies = ["typer>=0.12", "pyyaml>=6", "anthropic>=0.40"]

[project.optional-dependencies]
dev = ["pytest>=8", "ruff>=0.5"]

[project.scripts]
ken = "ken.cli:app"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
```

- [ ] **Step 2:** Create empty `ken/src/ken/__init__.py` and a short `ken/README.md` (what/why + the three CLI commands).
- [ ] **Step 3:** Create `ken/tests/conftest.py` with a `FakeLLM` and tmp-path fixtures (filled in as tasks need them; start minimal).
- [ ] **Step 4: Verify** `cd ken && python -m pytest -q` runs (0 tests collected is fine).
- [ ] **Step 5: Commit** `feat(ken): scaffold module (pyproject, package, test harness)`

### Task 2: `hashing` — vendored content_hash + parity test

**Files:** Create `ken/src/ken/hashing.py`, `ken/tests/test_hashing_parity.py`

- [ ] **Step 1: Write the failing parity test**

```python
# test_hashing_parity.py
import sys, pathlib
import pytest
from ken.hashing import content_hash

SPEC_SRC = pathlib.Path(__file__).parents[2] / "specledger" / "src"  # tests->ken->khala root

@pytest.mark.parametrize("body", ["", "a\n", "x \r\ny\n\n", "한국어\n  trailing  \n"])
def test_parity_with_specledger(body):
    sys.path.insert(0, str(SPEC_SRC))
    from specledger.hashing import content_hash as spec_hash  # noqa
    assert content_hash(body) == spec_hash(body)
```

- [ ] **Step 2: Run** `pytest tests/test_hashing_parity.py -v` → FAIL (no `ken.hashing`).
- [ ] **Step 3: Implement `ken/hashing.py`** (copy specledger's exact algorithm)

```python
import hashlib

def _normalize(body: str) -> str:
    text = body.replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n")]
    return "\n".join(lines).strip("\n")

def content_hash(body: str) -> str:
    digest = hashlib.sha256(_normalize(body).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
```

- [ ] **Step 4: Run** the parity test → PASS.
- [ ] **Step 5: Commit** `feat(ken): vendored content_hash with specledger parity test`

### Task 3: `models` — domain dataclasses

**Files:** Create `ken/src/ken/models.py`, `ken/tests/test_models.py`

- [ ] **Step 1: Write failing test** asserting construction + JSON round-trip of `Vouch`.

```python
from ken.models import Vouch
def test_vouch_roundtrip():
    v = Vouch(artifact_id="a1", person="kr", content_hash="sha256:x", score=0.9,
              passed=True, n_questions=5, ts="2026-06-23T00:00:00Z")
    assert Vouch.from_dict(v.to_dict()) == v
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement `models.py`** with frozen dataclasses + `to_dict`/`from_dict`:
  - `ArtifactRef(artifact_id, path, content_hash)`
  - `Question(text)`
  - `Verdict(passed: bool, score: float, rationale: str)`
  - `Vouch(artifact_id, person, content_hash, score, passed, n_questions, ts)` + `to_dict`/`from_dict`
  - `CoverageReport(total, covered, ratio, orphans: list[str])`
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(ken): domain models`

### Task 4: `vouch.is_fresh` — pure freshness

**Files:** Create `ken/src/ken/vouch.py` (is_fresh only for now), `ken/tests/test_vouch.py`

- [ ] **Step 1: Write failing tests** covering the freshness truth table:

```python
from ken.vouch import is_fresh
from ken.models import Vouch
def mk(h="sha256:cur", ts="2026-06-23T00:00:00Z", passed=True):
    return Vouch("a1","kr",h,0.9,passed,5,ts)

def test_fresh_when_hash_matches_and_within_ttl():
    assert is_fresh(mk(), current_hash="sha256:cur", now="2026-06-23T00:10:00Z", ttl_days=90)
def test_stale_when_hash_differs():
    assert not is_fresh(mk(), current_hash="sha256:NEW", now="2026-06-23T00:10:00Z", ttl_days=90)
def test_stale_when_ttl_lapsed():
    assert not is_fresh(mk(ts="2026-01-01T00:00:00Z"), current_hash="sha256:cur", now="2026-06-23T00:00:00Z", ttl_days=90)
def test_stale_when_not_passed():
    assert not is_fresh(mk(passed=False), current_hash="sha256:cur", now="2026-06-23T00:00:00Z", ttl_days=90)
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement `is_fresh`** (pure): parse ISO timestamps with `datetime.fromisoformat` (3.11+ accepts trailing `Z`). **Normalize BOTH `vouch.ts` and `now` through the same parser** so both are tz-aware before subtracting (else naive/aware `TypeError`). Return `vouch.passed and vouch.content_hash == current_hash and (now - vouch.ts) < timedelta(days=ttl_days)`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(ken): pure vouch freshness`

### Task 5: `vouch` persistence — fail-loud JSONL ledger

**Files:** Modify `ken/src/ken/vouch.py` (add `record_vouch`, `load_vouches`), `ken/tests/test_vouch.py`

- [ ] **Step 1: Write failing tests**

```python
from ken.vouch import record_vouch, load_vouches
def test_record_then_load_roundtrip(tmp_path):
    p = tmp_path / "ledger.jsonl"
    v = mk()
    record_vouch(v, ledger_path=p)
    assert load_vouches(p) == [v]
def test_record_fails_loud_on_unwritable_path(tmp_path):
    bad = tmp_path / "nope" / "ledger.jsonl"   # parent dir missing
    import pytest
    with pytest.raises(OSError):
        record_vouch(mk(), ledger_path=bad, make_parents=False)
def test_load_missing_ledger_returns_empty(tmp_path):
    assert load_vouches(tmp_path / "absent.jsonl") == []
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `record_vouch(vouch, *, ledger_path, make_parents=True)` — append `json.dumps(vouch.to_dict())+"\n"`; **do not swallow IO errors** (let `OSError` propagate — this is the §9 fail-loud deviation from `signals.py`). `load_vouches(path)` returns `[]` if file absent, else parses each line.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(ken): fail-loud JSONL vouch ledger`

### Task 6: `registry` — manifest + current hash

**Files:** Create `ken/src/ken/registry.py`, `ken/tests/test_registry.py`, `ken/ken.manifest.yaml` (empty list to start)

- [ ] **Step 1: Write failing tests**

```python
from ken.registry import register, load_manifest, current_hash
def test_register_adds_entry_and_is_idempotent(tmp_path):
    man = tmp_path / "m.yaml"; art = tmp_path / "a.md"; art.write_text("hello\n", encoding="utf-8")
    register(str(art), manifest_path=man)
    register(str(art), manifest_path=man)   # idempotent on path
    entries = load_manifest(man)
    assert len(entries) == 1 and entries[0].path == str(art)
def test_current_hash_matches_content(tmp_path):
    art = tmp_path / "a.md"; art.write_text("hello\n", encoding="utf-8")
    from ken.hashing import content_hash
    assert current_hash(str(art)) == content_hash("hello\n")
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `registry.py`:
  - `register(path, *, manifest_path)` → derive a stable `artifact_id` (e.g. `sha256(path)[:12]`), append to manifest if path not present (idempotent), return `ArtifactRef`.
  - `load_manifest(path)` → `list[ArtifactRef]` (the manifest stores `artifact_id` + `path`; hash is computed live, never stored stale).
  - `current_hash(path)` → read file, `content_hash(text)`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(ken): registry manifest + live current_hash`

### Task 7: `coverage` — pure aggregation + orphan list

**Files:** Create `ken/src/ken/coverage.py`, `ken/tests/test_coverage.py`

- [ ] **Step 1: Write failing tests**

```python
from ken.coverage import compute_coverage
from ken.models import ArtifactRef, Vouch
def test_coverage_counts_only_fresh(monkeypatch):
    arts = [ArtifactRef("a1","/a","sha256:cur"), ArtifactRef("a2","/b","sha256:cur2")]
    vouches = [Vouch("a1","kr","sha256:cur",0.9,True,5,"2026-06-23T00:00:00Z"),
               Vouch("a2","kr","sha256:OLD",0.9,True,5,"2026-06-23T00:00:00Z")]  # stale: hash differs
    rep = compute_coverage(arts, vouches, now="2026-06-23T01:00:00Z", ttl_days=90)
    assert rep.total == 2 and rep.covered == 1
    assert rep.orphans == ["a2"] and abs(rep.ratio - 0.5) < 1e-9
def test_empty_registry_is_full_coverage_or_zero():
    rep = compute_coverage([], [], now="2026-06-23T00:00:00Z", ttl_days=90)
    assert rep.total == 0 and rep.orphans == []
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `compute_coverage(artifacts, vouches, *, now, ttl_days) -> CoverageReport` — for each artifact, fresh iff any vouch with that `artifact_id` passes `is_fresh(v, current_hash=artifact.content_hash, now, ttl_days)`; `covered`/`ratio`/`orphans` accordingly. **Pure** (artifacts already carry current hash; caller computes them via `registry.current_hash`).
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(ken): pure coverage aggregation + orphan list`

### Task 8: `llm` — LLMClient protocol + fake

**Files:** Create `ken/src/ken/llm.py`, update `ken/tests/conftest.py` (FakeLLM)

- [ ] **Step 1: Write failing test** that `AnthropicLLM` satisfies the protocol and `FakeLLM` returns scripted output.

```python
from ken.llm import LLMClient, FakeLLM
def test_fake_llm_returns_scripted():
    llm = FakeLLM(responses=["Q1\nQ2"])
    assert llm.generate("sys","user") == "Q1\nQ2"
    assert isinstance(llm, LLMClient)  # runtime_checkable Protocol
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** `llm.py`:
  - `LLMClient` = `@runtime_checkable Protocol` with `generate(system: str, user: str) -> str` (sync for v0 CLI simplicity).
  - `AnthropicLLM` — mirrors nexus `LLMService` but sync (`anthropic.Anthropic`), `generate` returns `resp.content[0].text`, model default `claude-sonnet-4-6` (intentionally newer than nexus's pinned `claude-sonnet-4-20250514` — do not "fix" it back to match nexus).
  - `FakeLLM(responses: list[str])` — pops scripted responses; raises if exhausted.
  - Put `FakeLLM` import into `conftest.py` as a fixture.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(ken): LLMClient protocol + Anthropic impl + FakeLLM`

### Task 9: `probe` + `judge` — grounded questions & grading (fail-closed)

**Files:** Create `ken/src/ken/probe.py`, `ken/src/ken/judge.py`, `ken/tests/test_probe.py`, `ken/tests/test_judge.py`

- [ ] **Step 1: Write failing tests** (LLM faked)

```python
# test_probe.py
from ken.probe import make_questions
from ken.llm import FakeLLM
def test_make_questions_parses_lines():
    llm = FakeLLM(responses=["What is X?\nWhy Y?\nHow Z?"])
    qs = make_questions("artifact text", n=3, llm=llm)
    assert [q.text for q in qs] == ["What is X?", "Why Y?", "How Z?"]

# test_judge.py
from ken.judge import grade
from ken.llm import FakeLLM
import pytest
def test_grade_parses_verdict_json():
    llm = FakeLLM(responses=['{"passed": true, "score": 0.8, "rationale": "ok"}'])
    v = grade("artifact text", [("Q","A")], llm=llm)
    assert v.passed and v.score == 0.8
def test_grade_fails_closed_on_llm_error():
    class Boom:
        def generate(self, s, u): raise RuntimeError("llm down")
    v = grade("t", [("Q","A")], llm=Boom())
    assert v.passed is False and v.score == 0.0  # fail-closed, never auto-pass
def test_grade_fails_closed_on_garbage_output():
    v = grade("t", [("Q","A")], llm=FakeLLM(responses=["not json at all"]))
    assert v.passed is False and v.score == 0.0  # unparseable -> fail-closed
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**
  - `probe.make_questions(text, n, llm)` — system prompt: "generate exactly N grounded comprehension questions answerable only by understanding this artifact"; parse non-empty lines → `Question`.
  - `judge.grade(text, qa_pairs, llm)` — system prompt: judge whether answers demonstrate understanding; return strict JSON; parse to `Verdict`. **Wrap the LLM call in try/except → on any error return `Verdict(passed=False, score=0.0, rationale="llm_error: ...")`** (fail-closed). Also fail-closed on unparseable output.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(ken): grounded probe + fail-closed judge`

### Task 10: `cli` — wire the walking skeleton

**Files:** Create `ken/src/ken/cli.py`, `ken/tests/test_cli_e2e.py`, `ken/tests/fixtures/sample_artifact.md`

- [ ] **Step 1: Write failing e2e test** (Typer `CliRunner`; FakeLLM injected by monkeypatching the `_make_llm` factory; answers fed via stdin)

```python
from typer.testing import CliRunner
from ken.cli import app
from ken.llm import FakeLLM

def test_register_probe_vouch_coverage(tmp_path, monkeypatch):
    man = tmp_path / "m.yaml"; led = tmp_path / "ledger.jsonl"
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes the orders topic.\n", encoding="utf-8")
    runner = CliRunner()

    r = runner.invoke(app, ["register", str(art), "--manifest", str(man)])
    assert r.exit_code == 0
    aid = r.stdout.strip().split()[-1]   # cli prints the artifact_id

    # ONE _make_llm() result is shared across both LLM calls in a single `probe`,
    # so FakeLLM.responses must be [questions, verdict_json] IN CALL ORDER.
    monkeypatch.setattr(
        "ken.cli._make_llm",
        lambda: FakeLLM(responses=["Q1?\nQ2?", '{"passed": true, "score": 0.9, "rationale": "ok"}']),
    )
    r = runner.invoke(
        app, ["probe", aid, "--as", "kr", "--manifest", str(man), "--ledger", str(led)],
        input="answer1\nanswer2\n",            # one line per question, via stdin
    )
    assert r.exit_code == 0

    r = runner.invoke(app, ["coverage", "--manifest", str(man), "--ledger", str(led)])
    assert "1/1" in r.stdout
```

- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement `cli.py`** with Typer commands:
  - **LLM seam (concrete):** a module-level factory `def _make_llm() -> LLMClient: return AnthropicLLM()`. Every command obtains its client via `_make_llm()` — never `AnthropicLLM()` inline — so tests do `monkeypatch.setattr("ken.cli._make_llm", lambda: FakeLLM(...))`.
  - `register PATH [--manifest]` — register and **print the `artifact_id`** as the last whitespace-delimited token (the e2e test parses `stdout.strip().split()[-1]`).
  - `probe ARTIFACT_ID --as PERSON [--manifest] [--ledger]` — load artifact text; `llm = _make_llm()`; `qs = make_questions(text, n, llm)`; read **one stdin line per question** (e.g. `typer.prompt` or `input()` in a loop); `grade(text, list(zip(q_texts, answers)), llm)` (**same `llm` instance** — note the FakeLLM call order: questions then verdict); **only on `passed`** `record_vouch(...)` bound to `current_hash`. Print the verdict.
  - `coverage [--manifest] [--ledger] [--ttl-days]` — load manifest, compute current hashes via `registry.current_hash`, `load_vouches`, `compute_coverage`, print `covered/total`, ratio, and the orphan list.
- [ ] **Step 4: Run** the e2e test → PASS. Then full suite `cd ken && pytest -q`.
- [ ] **Step 5: Commit** `feat(ken): CLI walking skeleton (register/probe/coverage)`

### Task 11: Dogfood on khala

**Files:** Modify `ken/ken.manifest.yaml`; create `ken/docs/dogfood-2026-06-23.md`

- [ ] **Step 1:** Register khala's critical artifacts into `ken.manifest.yaml`: the ADRs (`adr/ADR-0001*`, `adr/ADR-0002*`), approved SPECs (`specs/*.md`), and ~5 hand-picked core files (e.g. `nexus/nexus/search/hybrid.py`, `specledger/src/specledger/review.py`, `mutqa/src/mutqa/ledger.py`).
- [ ] **Step 2:** Run `ken coverage` against the manifest with **no vouches yet** → expect **0% coverage, every artifact an orphan** (this is the honest cognitive-debt baseline: AI built it, nobody has vouched).
- [ ] **Step 3:** Run `ken probe` on 1–2 artifacts as the director, answering honestly, to demonstrate a real vouch flips coverage. (Requires `ANTHROPIC_API_KEY`; if unavailable, record this step as pending.)
- [ ] **Step 4:** Write `ken/docs/dogfood-2026-06-23.md` capturing the baseline coverage number, the orphan list, and what the first vouch felt like (friction notes → feeds the hybrid v1 decision).
- [ ] **Step 5: Commit** `chore(ken): dogfood baseline on khala artifacts`

---

## Notes / discipline
- Pure units (`hashing`, `models`, `is_fresh`, `coverage`) never import IO/LLM → fast deterministic tests.
- LLM is always behind `LLMClient`; tests use `FakeLLM`. No live API calls in the test suite.
- **Fail-loud** on vouch persistence (raise), **fail-closed** on LLM error in judge (never auto-pass). These are the two integrity invariants — each has a dedicated test.
- No git history is consulted anywhere (the AI-authorship-safe guarantee).
- v1 graduation (out of scope here): Postgres `vouch_log` + `v_cognitive_debt` view, passive risk-targeting signals, web dashboard.
