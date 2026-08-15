---
title: Probe
description: Test quality via mutation. Finds behavioral-test gaps that advisory review misses, using surviving mutants.
---

Probe is a mutation-driven test-quality harness. It finds the **behavioral-test gaps** that advisory review (a TDD skill or an LLM test reviewer) tends to miss, and it does so *deterministically*: it mutates your code and checks which mutations the suite fails to catch. A mutation that survives a green suite is measured proof that some behavior isn't actually verified.

A passing test suite isn't the same as one that verifies behavior. AI-generated tests especially can be green but hollow, asserting structure rather than behavior. Advisory reviewers give opinions; Probe gives evidence. Its core discipline is to keep the **deterministic runner separate from judgment**: the runner produces the only hard output, a list of surviving mutants, and a Test Quality Critic triages each one reasoning *only from the measured fact* that the suite stayed green under that mutation. That grounding is what separates it from a pure LLM review.

In short: it turns "tests pass" into "tests actually verify behavior," using surviving mutants as the signal.

<svg class="kh-fig" viewBox="0 0 560 230" role="img" aria-label="Probe mutation-tests a green suite: of 12 mutants, 10 are killed and 2 survive. The survivors expose a real gap in ledger.py:reconcile where a boundary is not covered — add a test.">
<defs><marker id="pb-a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="kh-fig-ah" d="M0 0 L10 5 L0 10 z"/></marker></defs>
<rect class="kh-fig-panel" x="24" y="28" width="250" height="180" rx="8"/>
<text class="kh-fig-h" x="42" y="52">MUTANTS · 12</text>
<line class="kh-fig-rule" x1="42" y1="64" x2="256" y2="64"/>
<rect class="kh-fig-track" x="44" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="82" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="120" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="158" y="80" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="44" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="82" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-box-acc" x="120" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="158" y="110" width="30" height="22" rx="3"/>
<rect class="kh-fig-box-acc" x="44" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="82" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="120" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="158" y="140" width="30" height="22" rx="3"/>
<rect class="kh-fig-track" x="42" y="180" width="12" height="12" rx="2"/>
<text class="kh-fig-s" x="60" y="187">killed ×10</text>
<rect class="kh-fig-box-acc" x="150" y="180" width="12" height="12" rx="2"/>
<text class="kh-fig-s" x="168" y="187">survived ×2</text>
<path class="kh-fig-line-acc" d="M274 118 L300 118" marker-end="url(#pb-a)"/>
<rect class="kh-fig-panel" x="300" y="28" width="236" height="180" rx="8"/>
<text class="kh-fig-h" x="318" y="52">GAP FOUND</text>
<line class="kh-fig-rule" x1="318" y1="64" x2="518" y2="64"/>
<text class="kh-fig-ans" x="318" y="94">2 survived</text>
<text class="kh-fig-d" x="318" y="122">ledger.py:reconcile</text>
<text class="kh-fig-s" x="318" y="144">boundary not covered</text>
<text class="kh-fig-d" x="318" y="176">→ add test</text>
</svg>

## Core concepts

- **Mutation (cosmic-ray).** Probe drives `cosmic-ray` to mutate changed source modules and run the suite against each mutant.
- **Survivor.** A mutant the suite did *not* kill — i.e. behavior the tests don't pin down. The runner's survivor list is the only contract handed to judgment.
- **Test Quality Critic.** A subagent that triages each survivor into `real-gap`, `equivalent`, or `low-value`, reasoning only from deterministic evidence, and returns `{verdict, rationale, suggested_test_intent}`.
- **Ledger (`probe-ledger.yaml`).** A committed, versioned record of verdicts. Re-runs only re-triage *new* survivors — already-judged equivalents are not re-litigated, removing the recurring noise cost. The ledger is committed alongside source.
- **Biting real-gaps = the headline.** The report's headline is the count of un-waived `real-gap`s, not a mutation score. Equivalent/low-value and waived real-gaps are demoted but never dropped.
- **Advisory, not (yet) a gate.** Probe currently reports; it does not block. Enforcement (failing a commit on biting real-gaps) is a later milestone.
- **Two CLI commands.** The deterministic spine is available by hand: `probe survey` (run mutation, produce the survivor list) and `probe absorb` (fold verdicts into the ledger).

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
- Package modules: `khala.probe.scope`, `khala.probe.run`, `khala.probe.ledger`, `khala.probe.report`; Critic prompt + eval under `references/`.

:::note[Last verified]
Transcribed from the skill's `SKILL.md` (and dogfood notes). Site re-run verification pending.
:::
