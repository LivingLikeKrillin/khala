---
title: Probe
description: Test quality via mutation — surfaces behavioral-test gaps that advisory review misses, deterministically, through surviving mutants.
---

Probe (formerly mutqa) is a mutation-driven test-quality harness. It surfaces the **behavioral-test gaps** that advisory review — a TDD skill, an LLM test reviewer — systematically misses, and it does so *deterministically*: by mutating your code and seeing which mutations the suite fails to catch. A mutation that survives a green suite is measured proof that some behavior is not actually verified.

The problem it calibrates: a passing test suite is not the same as a suite that verifies behavior. AI-generated tests in particular can be green and hollow — they assert structure, not behavior. Advisory reviewers give opinions; Probe gives evidence. Its core discipline is to keep the **deterministic runner separate from judgment**: the runner produces the only contract — a list of surviving mutants — and a Test Quality Critic triages each one reasoning *only from the measured fact* that the suite stayed green under that mutation. That grounding is what distinguishes it from a pure LLM review.

One-line identity: the harness that turns "tests pass" into "tests actually verify behavior," with surviving mutants as the deterministic signal.

<img
  src="/diagrams/probe.svg"
  alt="Mutation flow: green suite → cosmic-ray mutate → run the suite per mutant → any survivors? None reports no gaps; otherwise Critic triage → ledger → report of biting real-gaps."
  style="max-width: 100%; height: auto; display: block; margin: 1.5rem auto;"
/>

## Core concepts

- **Mutation (cosmic-ray).** Probe drives `cosmic-ray` to mutate changed source modules and run the suite against each mutant.
- **Survivor.** A mutant the suite did *not* kill — i.e. behavior the tests don't pin down. The runner's survivor list is the only contract handed to judgment.
- **Test Quality Critic.** A subagent that triages each survivor into `real-gap`, `equivalent`, or `low-value`, reasoning only from deterministic evidence, and returns `{verdict, rationale, suggested_test_intent}`.
- **Ledger (`probe-ledger.yaml`).** A committed, versioned record of verdicts. Re-runs only re-triage *new* survivors — already-judged equivalents are not re-litigated, removing the recurring noise cost. The ledger is committed alongside source.
- **Biting real-gaps = the headline.** The report's headline is the count of un-waived `real-gap`s, not a mutation score. Equivalent/low-value and waived real-gaps are demoted but never dropped.
- **Advisory, not (yet) a gate.** Probe currently reports; it does not block. Enforcement (failing a commit on biting real-gaps) is a later milestone.

## Quickstart

Probe is a Python skill/harness; it requires `cosmic-ray` installed (Windows-native OK; mutmut is not). The target must be a git repo with a green test suite. Steps transcribed from the source `SKILL.md`.

### Prerequisites

```bash
pip install cosmic-ray
```

- Target is a git repo and the suite is green (the pre-mutation baseline must pass for results to mean anything).
- Run from the consumer repo; the `khala.probe` package must be importable (add its `src` to `pythonpath` or install it).

### 1. Identify changed modules + run mutation → survivors (deterministic, no LLM)

```python
from pathlib import Path
import json, dataclasses
from khala.probe.scope import changed_source_modules
from khala.probe.run import run_mutation

modules = changed_source_modules(base="HEAD~1")   # or name modules explicitly for a full analysis
survivors = []
for m in modules:
    survivors.extend(run_mutation(module_path=m, workdir=Path(".")))

Path("survivors.json").write_text(
    json.dumps([dataclasses.asdict(s) for s in survivors], ensure_ascii=False, indent=2)
)
```

`run_mutation` runs cosmic-ray `init`/`exec`/`dump` and returns only the survivors. Failures propagate as exceptions (no fail-open) — stop and report, don't fake an empty result. Zero survivors means the changed behavior is sufficiently pinned by the current suite → report "no gaps" and stop.

### 2. Triage and report

Load the ledger, take only *new* survivors, dispatch the Critic per survivor, absorb verdicts back into the ledger, then assemble the advisory report:

```python
from khala.probe.ledger import load_ledger, new_survivors, absorb, dump_ledger
from khala.probe.report import build_report

ledger = load_ledger(ledger_path.read_text(encoding="utf-8") if ledger_path.exists() else "")
fresh = new_survivors(survivors, ledger)   # only un-judged survivors go to the Critic
# ... dispatch Critic per `fresh` survivor, collect Verdict(...) list as fresh_verdicts ...
ledger = absorb(ledger, fresh_verdicts, today)
print(build_report(survivors, ledger, today))
```

## How-to

### Re-run after adding tests (only new survivors re-triaged)

Because verdicts persist in `probe-ledger.yaml`, a re-run calls `new_survivors(...)` and the Critic only sees survivors not already judged. Existing verdicts are reused, so equivalent-mutant noise isn't re-litigated each run.

### Read the report and act on real-gaps

The headline is `biting(survivors, ledger, today)` — the count of un-waived real-gaps. For each biting real-gap, Probe surfaces the Critic's `suggested_test_intent` and recommends adding a behavioral-verification test. It is advisory: the decision is yours. A human can hand-set `waived_until` on an entry to silence it until expiry; `absorb` won't overwrite a hand-set waiver.

### Guard the Critic against regressions

When you change the Critic prompt, re-run the golden cases in `references/critic-eval.md` (EVAL-1 = real-gap, EVAL-3 = low-value) — correctly triaging from deterministic evidence is the harness's entire value.

## Reference

- Source: `SKILL.md` for the Probe skill (mutation-driven test-quality harness, M2 = ledger).
- Plan/spec: `docs/superpowers/plans/2026-06-06-mutqa-m1-runner-advisory.md` (M1; M2/M3 in the spec §5–6); dogfood notes under the skill's `docs/`.
- Package modules: `khala.probe.scope`, `khala.probe.run`, `khala.probe.ledger`, `khala.probe.report`; Critic prompt + eval under `references/`.

:::note[Last verified]
Transcribed from the skill's `SKILL.md` (and dogfood notes). Site re-run verification pending.
:::
