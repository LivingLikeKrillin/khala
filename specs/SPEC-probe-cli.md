---
id: SPEC-probe-cli
type: spec
title: Probe gets a CLI — the deterministic spine as one command, the judgment left
  where it belongs
status: approved
linked_adrs:
- ADR-0004
- ADR-0005
tags:
- probe
- surface
- cli
- test-quality
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-10T16:07:30Z'
content_hash: sha256:0949c4c9585d70ae796ff2087508e98f3034de8757543711c793f4ddb978b548
---

## 0. Which "Probe" this is (naming, per ADR-0005)

**The falsifiable anchor, not a naming argument:** this CLI wraps the **`khala.probe` package** — the
cosmic-ray runner, `ledger.py`, survivor extraction. §4 lists its signatures and §7's tests `import`
it and exercise `run_mutation`. Whatever the ecosystem calls that package, its own module contents
are the mutation tool; if it weren't, those tests would fail to import or run. The naming below is
context, but the binding is by import path.

For the record: ADR-0004 is a point-in-time record written **before** the rename; in its vocabulary
the cosmic-ray tool is *mutqa* and *Probe* names the PR/review analyzer. ADR-0005 records the forward
mapping — **`mutqa` → Probe** (mutation-driven test quality), **old `Probe` → Observer** (review
analyzer) — and its §3 flags the reuse of "Probe" as the single most error-prone item.

**ADR-0005 is partially overtaken by implementation, and this SPEC does not depend on resolving
that.** ADR-0005 §3 (authored when the ADR shipped "zero product code") says the directory migration
had not landed — "it remains `mutqa/`". The subsequent rename PRs did move the directories, which is
why the package now imports as `khala.probe`. So ADR-0005 §3's transitional note is stale relative to
the tree, and whether ADR-0005 deserves a successor recording that the migration landed is a
governance question raised here but **out of scope for this CLI**. Either way, §0's first paragraph
stands on the import path, not on ADR-0005 §3's frozen snapshot.

## 1. Goal

Make Probe runnable as a tool. Today, using it means opening `probe/SKILL.md` and pasting six
Python blocks by hand, then dispatching a Critic subagent yourself. The audit's verdict was blunt:
"Not a tool … Give Probe a CLI or stop calling it a tool." This SPEC gives it a CLI.

## 2. The one constraint that shapes everything

Probe's first principle is that the **deterministic runner** (mutation execution, survivor
extraction, the ledger) and the **judgment** (a Test Quality Critic deciding real-gap vs equivalent
vs low-value) are never mixed. The runner's survivor list is the only contract; the Critic judges
from measured evidence. `SKILL.md`: "결정론 영역(러너, LLM 없음)과 판단 영역(Critic)을 섞지 않는다."

A CLI cannot dispatch a Claude subagent, and it must not try to. So a single `probe run` that "does
everything" is not an option — it would either fake the judgment or embed an LLM in the runner,
which is the exact fusion Probe exists to prevent. The CLI owns the deterministic spine and **hands
the judgment out across a file boundary**. This is not a limitation worked around; it is the
principle expressed as a command surface.

## 3. Non-goals

- **Dispatching the Critic from the CLI.** The judgment stays an agent action (subagent dispatch),
  exactly as `SKILL.md` step 4 describes. The CLI emits the filled prompts; the agent (or a human
  reading them) produces verdicts. The CLI never calls an LLM.
- **The M3 enforcing gate.** Probe is advisory (M2). `biting()` exists and the report headlines the
  biting count, but nothing fails a commit yet. This SPEC does not add enforcement; it makes the
  advisory loop runnable. (M3 is a separate decision, out of scope.)
- **Rewriting the harness.** `scope.py`, `run.py`, `ledger.py`, `report.py`, and the models are
  written and stay. This SPEC wraps them; it does not touch their logic. The CLI is the thin surface
  Arbiter's CLI already models (`arbiter/src/khala/arbiter/cli.py`).
- **Per-survivor coverage mapping / behavioral clustering.** Future work per `SKILL.md`; not here.

## 4. What exists (the harness this CLI wraps)

Read off `probe/src/khala/probe/` at authoring; treat these signatures as the contract the CLI binds
to, not as an unfalsifiable "verified" claim — the tests in §7 exercise them for real.

- `khala.probe.scope.changed_source_modules(base="HEAD", run=_git) -> list[str]` — git-diff'd Python
  source modules, tests/`__init__` excluded, paths normalized with `/`.
- `khala.probe.run.run_mutation(module_path, workdir, test_command=DEFAULT, *, runner=_cosmic_ray)
  -> list[Survivor]` — one full cosmic-ray cycle per module in an isolated temp session; failures
  propagate as exceptions (no fail-open).
- `khala.probe.ledger`: `load_ledger(text) -> Ledger`, `new_survivors(survivors, ledger)`,
  `absorb(ledger, verdicts, today) -> Ledger`, `dump_ledger(ledger) -> str`,
  `biting(survivors, ledger, today) -> list[Survivor]`.
- `khala.probe.report.build_report(survivors, ledger, today) -> str`.
- `models.Survivor(module, lineno, operator, mutation_diff)` with a `.key` property
  (`module:lineno:operator`); `models.Verdict(survivor_key, verdict, rationale,
  suggested_test_intent=None)`.
- `references/critic-prompt.md` with slots `{module}`, `{lineno}`, `{operator}`, `{mutation_diff}`,
  `{suite_summary}`. §7 asserts a filled prompt leaves no slot literal, so a slot rename breaks a
  test rather than shipping silently.
- `pyproject.toml` has **no** `[project.scripts]`. That is the whole defect for reachability.

**`today`.** Each command computes `today = datetime.date.today()` once at invocation and threads it
into `biting`/`absorb`/`build_report`. Survey's `today` and a later absorb's `today` may differ, and
that is correct: survey's report is a preliminary snapshot; absorb's is the one recorded against the
ledger, and waiver expiry is meant to be evaluated at the moment of judgment. No cross-command
"same today" invariant is claimed or needed.

**Verdict domain.** A verdict's `verdict` field is one of exactly `real-gap` | `equivalent` |
`low-value` (the values `references/critic-prompt.md` emits). `Verdict` is a bare dataclass that does
not validate, and `absorb` (harness, untouched here) does not either — so **`cli.py` validates the
domain before constructing `Verdict` objects**, rejecting an unknown value loudly (§5.3, §6). The
enforcement lives at the CLI surface, not in the harness.

**"biting".** The report's headline count is `biting(survivors, ledger, today)` — the survivors that
are **real-gap and not currently waived** (unwaived real-gaps). It is not the mutation score. The
predicate is the harness's; this SPEC does not redefine it, only surfaces it as the headline.

**`absorb` and waivers.** That `absorb` records judgments immutably and preserves a human-set
`waived_until` is the **harness's** guarantee, covered by Probe's existing `test_ledger` suite. Per
§3 this SPEC does not touch or re-test that logic; the CLI merely calls `absorb`.

## 5. Design

Two commands, a file boundary between them where the judgment lives.

### 5.1 `probe survey` — the deterministic spine

```
probe survey [--base HEAD~1] [--module PATH ...] [--workdir .] [--out probe-survey.json]
             [--ledger probe-ledger.yaml]
```

1. Modules: `--module` explicitly, else `changed_source_modules(base)`. Zero modules → report
   "변경된 소스 모듈 없음" and exit 0.
2. `run_mutation` per module, accumulate survivors. Runner failures propagate (non-zero exit, the
   error surfaced) — never a silent empty result.
3. Zero survivors → "갭 없음: 변경 모듈의 행위가 현재 스위트로 고정됨", exit 0.
4. Load the ledger (`--ledger`, empty if absent). `new_survivors` → `fresh`.
5. `suite_summary`: run `python -m pytest --collect-only -q` in `--workdir` and derive a **coarse**
   summary string — best-effort, not a precise parse of a version-specific format. Prefer pytest's
   own trailing summary line (e.g. "69 tests collected"); if that is not recognizable, fall back to
   the captured tail as-is. On any collection failure, a plain "스위트 요약 수집 실패" string. The
   summary is advisory Critic context only — nothing downstream depends on an exact count, so a
   format drift degrades the Critic input, it never breaks the run.
6. Emit `--out` (`probe-survey.json`): the full `survivors` list (each field, so keys can be
   rebuilt), the `fresh` subset, `suite_summary`, and for each fresh survivor the **filled critic
   prompt** (from `references/critic-prompt.md`). Print the preliminary report
   (`build_report(survivors, ledger, today)`) and a one-line "N fresh survivors need judgment —
   dispatch the Critic on the prompts in probe-survey.json".
7. `fresh` empty (all survivors already judged) → print the report from the ledger and say
   "새로 판정할 survivor 없음"; no Critic step needed.

The command reads the ledger but **does not write it** — surveying changes no persistent state.

### 5.2 The judgment (outside the CLI, by design)

The agent or human dispatches the Test Quality Critic on each filled prompt in `probe-survey.json`
and collects the JSON verdicts into a file — a list of `{survivor_key, verdict, rationale,
suggested_test_intent}`. This is `SKILL.md` step 4, unchanged. The CLI deliberately does not do it.

### 5.3 `probe absorb` — fold the verdicts back, persist, report

```
probe absorb --verdicts verdicts.json [--survey probe-survey.json] [--ledger probe-ledger.yaml]
```

1. Load the ledger. Read verdicts; build `Verdict` objects. Two loud rejections, both leaving the
   ledger untouched (non-zero exit, the offending value named): a verdict whose `survivor_key` is
   **not in the survey's survivor set** (the ledger is not fed keys that never surveyed), and a
   verdict whose `verdict` value is **outside** `{real-gap, equivalent, low-value}`.
2. **Unjudged fresh survivors are reported, not swallowed (I-005).** With `--survey`, absorb
   compares the survey's `fresh` set against the verdict keys and, if any fresh survivor has no
   verdict, prints a warning naming those keys — a partial verdicts file does not silently persist a
   half-judgment. (Not fatal: a re-survey re-surfaces the unjudged ones; but the operator is told.)
3. `absorb(ledger, verdicts, today)` — the harness records the new judgments (immutably, preserving
   human waivers; that is `absorb`'s own guarantee, §4).
4. Write the ledger back to `--ledger` (`dump_ledger`). This file **is committed** — the judgment
   record versions alongside the source.
5. Reload survivors from `--survey`, rebuilding each `.key` as `module:lineno:operator` **exactly as
   the harness's `Survivor.key` property does** (a round-tripped Survivor loses the property per
   `SKILL.md`), so reconstructed keys cannot diverge from the harness's own notion. A survey JSON
   missing those fields is a corrupt artifact → non-zero exit, not a silent mismatch. Then print
   `build_report(survivors, ledger, today)` — real-gaps on top, waived ones demoted but never
   dropped. Without `--survey`, print the ledger-only view and say the survivor context was omitted.

### 5.4 Packaging

`[project.scripts]` `probe = "khala.probe.cli:main"`, matching Arbiter. `cli.py` builds a Typer app,
reconfigures stdout/stderr to UTF-8 on win32 (the same cp949 guard `nexus/cli.py` and
`arbiter/cli.py` carry), and injects nothing an LLM would need — the deterministic functions only.
`SKILL.md`'s procedure prose is rewritten to "run `probe survey`, dispatch the Critic on the emitted
prompts, run `probe absorb`" instead of six paste-in blocks.

Installing `SKILL.md` under a `.claude/skills/` path is a **separate** deliverable (a distinct audit
item) and is out of scope here — this SPEC gives Probe a CLI; where the skill file is registered does
not depend on it and is not tested here.

## 6. Error handling

- Runner (`run_mutation`) failure → exception propagates, non-zero exit, cause reported. Never a
  fake empty survivor list (fail-open is the one thing a test-quality gate must not do).
- `--collect-only` failure → coarse `suite_summary` string, survey still emitted (the Critic is
  advisory; a rough summary degrades its input, it does not break the run).
- `verdicts.json` unreadable / malformed → non-zero exit, clear message, ledger untouched.
- A verdict key absent from the survey, or a `verdict` value outside the domain → non-zero exit, the
  offending value named, ledger untouched.
- `run_mutation` raising (missing `cosmic-ray`, a broken session, a non-zero cosmic-ray exit) →
  the CLI does **not** fake an empty survey; it exits non-zero and surfaces the underlying error with
  context (naming cosmic-ray as the likely cause when the failure is a missing-binary `FileNotFound`,
  without promising a specific string for every failure mode the injected runner might produce).

## 7. Testing

The CLI is unit-testable without cosmic-ray or a live Critic: the runner is injected
(`run_mutation(..., runner=)`), git is injected (`changed_source_modules(run=)`), and the Critic is
a file the test writes. Tests use Typer's `CliRunner`.

- `survey` with an injected runner yielding known survivors writes `probe-survey.json` containing
  those survivors, the fresh subset, and a filled prompt per fresh survivor (slots substituted, no
  `{module}` left literal).
- `survey` with zero changed modules exits 0 with "변경된 소스 모듈 없음" and writes no survey.
- `survey` with zero survivors exits 0 with the "갭 없음" line.
- `survey` where every survivor is already in the ledger prints the report and says "새로 판정할
  survivor 없음" — the fresh set is empty, no prompts emitted.
- `survey` does not write the ledger file (surveying is read-only on persistent state).
- `absorb` folds a verdicts file into the ledger, writes it, and the report headlines the biting
  real-gap count; an equivalent verdict is demoted, not dropped.
- `absorb` with a verdict key that never surveyed exits non-zero, names the key, and leaves the
  ledger file unchanged (asserted byte-for-byte).
- `absorb` with a `verdict` value outside `{real-gap, equivalent, low-value}` exits non-zero, names
  the bad value, and leaves the ledger unchanged.
- `absorb --survey` with a verdicts file missing one fresh survivor prints a warning naming the
  unjudged key and still absorbs the ones present (partial judgment is reported, not swallowed).
- `absorb` with a malformed verdicts file exits non-zero and leaves the ledger untouched.
- A `run_mutation` failure surfaces as a non-zero exit from `survey`, not an empty survey (fail-open
  is asserted against).
- The console script entry resolves: `probe --help` lists `survey` and `absorb`.

- `survey` whose `--collect-only` step fails writes a survey whose `suite_summary` is the fallback
  string ("스위트 요약 수집 실패"), and the survey still emits (the failure degrades Critic context,
  it does not break the run).

The Critic's own judgment quality is not retested here — that is `references/critic-eval.md`'s
golden cases, unchanged. This SPEC wires the runner and the ledger to a command; it does not touch
what the Critic decides. Nor does it re-test harness internals (`absorb`'s waiver preservation,
`biting`'s predicate) — those are Probe's existing `test_ledger`/`test_report` suites; §7 covers only
the CLI's own surface behavior.

## 8. Acceptance

Observable, from a consumer repo (e.g. Arbiter) with `khala.probe` importable and `cosmic-ray`
installed:

1. `probe --help` lists `survey` and `absorb` (the console script resolves).
2. `probe survey --base HEAD~1` exits 0 and writes `probe-survey.json` containing a `survivors`
   list, a `fresh` subset, a `suite_summary` string, and one filled Critic prompt per fresh survivor
   with no `{slot}` left literal; it does **not** modify `probe-ledger.yaml`.
3. After the operator dispatches the Critic and writes `verdicts.json`, `probe absorb --verdicts
   verdicts.json --survey probe-survey.json` exits 0, rewrites `probe-ledger.yaml` (a diff to commit),
   and prints a report whose headline is the biting real-gap count.
4. `probe absorb` with a verdict key that never surveyed, or a verdict value outside the domain,
   exits non-zero and leaves `probe-ledger.yaml` byte-for-byte unchanged.

Steps 2–4 exercise the **live** path (real cosmic-ray, real survivors) and are the go-live
acceptance gate — the same shape as the Access-tunnel and Slack-workspace gates: the automated suite
(§7) proves the CLI's logic with an injected runner and no cosmic-ray, and the one thing a real
cosmic-ray run is needed for is this end-to-end confirmation.

The six-block paste is replaced by two commands plus the one Critic dispatch a CLI cannot perform.

