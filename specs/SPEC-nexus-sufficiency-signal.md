---
id: SPEC-nexus-sufficiency-signal
type: spec
title: Record whether the evidence answered the question — a per-search verdict, off
  by default
status: in_review
linked_adrs:
- ADR-0002
- ADR-0006
tags:
- nexus
- llm
- grounding
- abstention
---

## 0. What shipped

**Implemented on branch `feat/nexus-sufficiency-signal`, 2026-08-10**, at the scope disposition
I-014 cut it to. What ships is **four columns**, not seven:

    sufficiency · sufficiency_at · sufficiency_judge · evidence_fingerprint

Removed before implementation, per that disposition: `judge_prompt_tokens`,
`judge_completion_tokens`, `judge_cost_usd`, `NEXUS_SUFFICIENCY_MAX_PER_DAY`, and the startup
config validator. All three columns are NULL on the `claude-code` bridge — the one backend the
named switch-on deployment uses — so they bought nothing there while generating more critique
findings than any other part of the design. The timeout/stranded coupling survives as a **runtime**
guard in `_judge_with_timeout` rather than a startup check: it raises when
`NEXUS_SUFFICIENCY_TIMEOUT` exceeds half `STRANDED_SECONDS`, which is the configuration that would
let a normal completion be discarded by the UPDATE's guard.

Sections below describing the cut mechanisms are kept as the record of what was considered and why
it was dropped; where they conflict with the four-column list above, **this section is what
shipped**.

Tests: `nexus/tests/test_sufficiency_signal.py` (17, no DB) and
`test_sufficiency_signal_db.py` (9, real Postgres). Suite: 1206 passed, 0 failed — baseline before
this change was 1180.

## 0.1 The shape, and why it is this shape

Ship the **observation mechanism**: one verdict per answered search, on the `search_log` row,
labelled with what produced it. **Default off.** No rate, no view, no threshold, no gate.

Six critique rounds got here, and the two that matter pulled in opposite directions:

* **Round 5** — a per-search outbound LLM call is a capability, not a count: new spend, new failure
  modes, and raw query + document text leaving for a provider. No fired gate covers it.
* **Round 6** — the resulting deferral was **self-sealing**. It made "a rate needs a denominator" a
  precondition while shipping nothing that could accumulate one, so the gate could never fire by
  construction.

**Default off is what reconciles them.** The mechanism exists so a denominator can start
accumulating (round 6); no deployment calls a provider per search, and no text leaves, until an
operator turns it on (round 5). The egress decision moves to the deployment that has the facts,
and `disabled` is a recorded value, so an off deployment is visible rather than silent.

What does **not** ship, and why: the aggregate. Round 4 established that a rate grouped by
day × tenant × judge × retrieval-config never reaches a usable denominator at this volume, and that
shedding under load biases it where it does. Rows are honest; aggregation belongs to whoever has
the traffic.

## 1. What was measured

### 1.0 Four phrases that are not synonyms

| term | who decides | population |
|---|---|---|
| `answerable` / `unanswerable` | the **label author**, before any run | 40 / 5 of the 45 labels |
| `answered` / `declined` | the **answerer**, at run time | 31 / 14 of the same 45 |
| `abstained` | **code**: retrieval returned zero hits | a field on `AnswerResult`, **not a column** |
| `sufficient` / `insufficient` | the **judge**, from query + evidence | what §1.2 measures |

14 declined ≠ 5 unanswerable: nine declines are on answerable queries.

**Correction (round 6).** Earlier drafts called `abstained` a `search_log` column. It is
`AnswerResult.abstained` (`nexus/nexus/llm/answer.py:71`, set at `:152` with reason `no_evidence`),
returned in the API response (`api.py:462`); no `.sql` file contains the string, and the nearest
persisted column is `search_log.no_answer`. So **no stored population exists behind any claim about
how often the flag fires** — every number below is an offline evaluation, never a production
observation. That absence is itself an argument for §3: the repo cannot currently answer "how often
is the evidence inadequate" from anything it has stored.

### 1.1 The flag cannot be repaired by a score threshold

`abstention-never-fires` records a flag whose condition is "no evidence at all". BM25 always
returns something, so it reads `false` even when the answer says the information is not there.
Offline, 2026-08-08: **0 of 5** on queries whose answers are absent from the corpus.

The obvious repair is a score cut:

    declined (14)   top .0288–.0323   mean .0183–.0290   gap .0047–.0176
    answered (31)   top .0161–.0323   mean .0156–.0291   gap .0010–.0186

The answered range contains the declined one on all three features. **What that rules out**: a
clean single-feature cut on this data. **What it does not**: anything about the distributions
between the extremes, about a threshold with useful precision/recall, or about combinations.

The load-bearing reason to stop looking is that an RRF score measures **lexical and semantic
proximity**, not whether the answer is present. Google Research's "sufficient context"
(arXiv 2411.06037) reports the same separation and concludes the fix is structural. The nesting
corroborates; it does not prove — and §3 therefore ships a *recording*, not a suppression rule.

**Scope**: Pack B corpus, KURE-v1 in `embedding_1024`, mecab-ko BM25, production RRF fusion, one
45-label set, one snapshot.

### 1.2 A separate judge does separate them

`nexus/nexus/llm/sufficiency.py` (merged) judges query + evidence, **never the answer** — a model
asked to grade its own output is the failure mode, not the fix.

**The reference standard**, unstated in earlier drafts even while §1.0 warned two splits exist:
scoring is against the **label author's** `answerable`/`unanswerable` split (40/5), never against
what the answerer did. Correct = a labelled-answerable query whose gold document reached the
evidence judged `sufficient`, or a labelled-unanswerable one judged `insufficient`. Queries whose
gold never reached the evidence are excluded, and the exclusion count is reported — in the
surviving run it was **0**, so the denominator is the full 45.

Three runs were made: **43/45, 42/45, 43/45**, with `insufficient` reported 5/5 each time.

**Correction (round 6) — only one run is evidenced.** `suff_measure.py` writes to a fixed filename,
so each run overwrote its predecessor. What survives:

    scored 45 · excluded 0 · accuracy 43/45
    false positives 2  (pb-loan-08, pb-space-01) · false negatives 0

The critique's arithmetic on the rest is correct and I could not refute it: with all 5 unanswerable
caught, a 42/45 run must contain **three** answerable queries judged `insufficient`. So "2 of 40,
reproduced every run" is **not supported** — two are reproducible and named, a third occurred once
and was not recorded. **The 5/5 claim is withdrawn on the same grounds**: it comes from the same
destroyed runs, and it is what the arithmetic above assumes. Only the surviving run evidences
5/5, so the honest statement is *5/5 in the one run that survives*, and the inference about the
42/45 run is conditional on an unevidenced premise — it is reported because it is the reading
least favourable to this SPEC, not because it is established. An instrument defect, not a judge finding, and the second time in this repo a
fixed output filename has destroyed the comparison it was written to make. §5 requires per-run
artifacts before any successor quotes a spread.

The controls, criteria written into the script before it ran:

| arm | manipulation | expected | criterion | result |
|---|---|---|---|---|
| A negative | drop the **gold document**, keep query and other snippets | flips to `insufficient` | ≥70% | **31/38** |
| B positive | give the 5 unanswerable queries **synthetic evidence containing the answer** | flips to `sufficient` | ≥4/5 | **5/5** |

**Correction (round 7) — arm A was not baseline-corrected.** It was first reported as 33/40. Two of
those 40 (`pb-loan-08`, `pb-space-01`) were **already** judged `insufficient` before the
manipulation, so they had no verdict to flip and were counted as trivial flips. Recomputed on the
38 queries judged `sufficient` at baseline: **31/38 = 81.6%**. That clears ≥70%, but the honest
label is **criterion met under a post-hoc population**: the criterion was fixed in advance, the
*eligible population* was not, and it was narrowed after the baseline verdicts were seen. Both
denominators are reported so a reader can take either.
All 7 non-flips (`pb-comp-01/04/06`, `pb-part-02/05/08`, `pb-mix-07`) were genuinely eligible, so
§6's worry that some may never have been flippable is closed — they were.

The artifacts are in `nexus/tests/eval/local/`, which is **gitignored** because Pack B is a partner
corpus and this repository is public. A gitignored file carries no history establishing write
order, so the pre-registration claim is **not independently verifiable** even from the working
tree — it rests on the author's account. Stated as a limit, not defended. The thresholds were chosen by judgement, not derived,
and arm B is weak on its own terms: at n=5, a coin-flipping judge clears ≥4/5 about 19% of the
time. Arm B is the **only** evidence that `insufficient` fires on genuinely absent facts, so the
most load-bearing control is the least powerful one (§6).

**What the arms support**: the verdict moves with the evidence. **What they do not**: arm A's 81.6%
is a response rate, not an accuracy — its 7 non-flips are unseparated between "another document
also carried the answer" (`pb-comp-04` has two golds) and "the judge missed it".

### 1.3 The false-positive rate is observed, not established

In the surviving run, **2 of 40** answerable queries were judged `insufficient` — 5.0% as a point
estimate, 95% Wilson interval roughly **1.4%–16.5%**, and per §1.2 the true across-run count is
2–3, so even the point estimate is a range. An earlier draft made 5% a floor a future gate had to
clear; it cannot carry that. What it establishes is directional: the `insufficient` rate has a
non-zero component owing nothing to evidence gaps.

## 2. Decision

**Record one verdict per answered search on its `search_log` row. Default off. Nothing reads it,
nothing is suppressed, no rate is computed here.**

### 2.1 No gate declaration, because ADR-0002 gates features on signals — not signals

Eight critique rounds went into placing this under ADR-0002, trying four positions: that ADR-0002
was merely *Proposed*; that gate ⓐ's observation-mechanism clause covered it; that ADR-0006's
demand-pull override covered it; and that ADR-0002's gate-declaration slot could be filled for it.
All four were refuted. The reasons, recorded rather than asserted, because three revisions argued
these positions in both directions:

* **"ADR-0002 is merely Proposed."** Its frontmatter is `status: accepted` with
  `approved_by: LivingLikeKrillin` and a stamped `content_hash`, while its body says *Proposed* —
  a contradiction in the ADR that this SPEC has no standing to resolve. It is moot here either way:
  the argument below does not need ADR-0002 to be binding, only to be read correctly. **The
  contradiction is left open and flagged in §6** — resolving it is an ADR's job, not a SPEC's.
* **Gate ⓐ's observation-mechanism clause.** ⓐ's signal is defined as sourced from the human; this
  one is derived from documents by an LLM.
* **ADR-0006's demand-pull override.** It is granted on an *entropy / ingestion-trust* ground that
  §2.3 disclaims for this SPEC, so the precedent is not claimed and **this SPEC does not rely on
  ADR-0006.**

  A tenth-round critique asserted the reverse — that ADR-0006 "ships nothing but measurement and
  still needed the override", which would make signal collection itself gated and refute this
  section. **Checked against the record, and it is wrong.** ADR-0006's Decision has four parts and
  measurement is one: (1) a document-level supersession filter injected into `_bm25_search` /
  `_vector_search`, so retrieval results change; (2) a `supersede(old_rid, new_rid, tenant)`
  primitive exposed through `nexus supersede`, `POST /supersede`, **and** an MCP tool — three
  product surfaces; (3) retrieval-time containment; (4) `doc_reingest_events` + `v_entropy_signals`.
  Its override was needed because it ships **features**. That its measurement rode along on a
  feature grant says nothing about whether measurement alone needs one, so it is not evidence
  against this section — and taking the assertion at face value is what produced a since-withdrawn
  override ADR.
* **Filling ADR-0002's gate-declaration slot.** ⓐ ⓑ ⓒ are candidate directions for the
  *cognitive-debt window* — a named human's comprehension, an org understanding map, run-time agent
  verification — and a verdict about whether retrieved evidence answers a query is none of them.

The simplest reading was never tried, and it is the correct one. ADR-0002's rule says:

> gate each debt-servicing **feature** on "is this debt actually accumulating? show the signal."

The thing gated is a **feature**. A signal is what you *show* to open the gate.

The claim needs one narrowing, because gate ⓐ does put an observation mechanism inside a gated
sequence — "the observation mechanism… is itself ⓐ's first sub-step". Read precisely, that governs
**ⓐ's own** mechanism: a direction that has claimed a specific instrument owns it, and ⓐ's is
claimed. So the accurate statement is **ADR-0002 gates signal collection only where a direction has
claimed that signal — and no direction claims this one** (the ⓐ ⓑ ⓒ table above). Where nothing has
claimed it, what remains is the general rule, which gates features. Its own text supports this by
crediting `search_log` /
`v_search_health` as the demand signals gating already runs on. The weight that carries is limited
and is stated as such: ADR-0002 credits those as **pre-existing** signals, not as sanctioned new
builds, and neither makes an outbound per-request provider call. They show the rule's *shape* —
signals are what gates consume — not that any signal may be built at any cost. That is what §2.2's
constraints are for, and clause (d)'s off-by-default is what answers the part the precedent does
not cover.

Gate ⓐ is the one place the two are entangled, and ⓐ resolves it internally: its comprehension log
"is itself ⓐ's first sub-step". That is a statement about **ⓐ's ordering**, not a general rule that
signals need gates — and reading it as one produces a loop where a gate fires on an observation,
the observation needs a mechanism, and the mechanism needs a fired gate. Round 6 found that loop
empirically: the deferral it produced was self-sealing, requiring a denominator while shipping
nothing that could accumulate one.

**So: no gate declaration is required, and none is claimed.** What is required is that this stay a
signal. §2.2 is that argument, and it is checkable rather than rhetorical.

**What this decision does and does not rest on.** It rests on two things a reader can check: the
repo stores **nothing** from which retrieval adequacy can be asked (§1.0 — `abstained` is not even a
column), and an RRF score measures proximity rather than answer-presence, so no threshold on it was
ever going to close `abstention-never-fires` (§1.1). It does **not** rest on §1.2's accuracy figure
being reproducible — it is not: two of three runs were destroyed, the 5/5 claim is withdrawn, arm A
was recomputed on a post-hoc population, arm B is n=5, and the artifacts are gitignored. That
evidence is enough to say the judge is worth pointing at production and **not** enough to conclude
anything about how often evidence is inadequate. Which is the point: this SPEC ships the instrument
that would produce checkable numbers, and §2.2's step 2 requires the offline measurement to be
re-run with per-run artifacts before any gate is declared on it.

### 2.2 What keeps it a signal rather than a feature

Each line is a constraint this SPEC accepts, with where it is enforced. If a future revision wants
any of them back, it has become a feature and ADR-0002 gates it normally.

| | constraint | enforced by |
|---|---|---|
| a | **It records; it does not act.** No code branches on the value; nothing is suppressed, ranked, retried or cached differently | test 14 — **over Python modules only**; SQL clients, dashboards and the web UI are out of its reach, so migration 012 also carries a `COMMENT ON COLUMN` |
| b | **No product surface.** No endpoint, UI, skill or CLI consumes it; reading it is a hand-written query | review; §4's ships-list is the check |
| c | **No threshold, no decision rule, no view.** Rows only | §4 — migration 012 creates no view. Round 4 established the rate is uncomputable at this volume anyway |
| d | **Off by default**, with a stated ceiling and a recorded shed value | tests 3, 13 |
| e | **Off the request path on the four server paths**, cannot fail what it observes. The CLI (`await_persist=True`) waits by contract (§3.1); pool contention is the one route by which it could still delay a server request | tests 1, 5b, 11b — 5b is the one that proves a failure cannot take the row down |
| f | **No query- or document-derived text is recorded.** Added columns are a CHECK-constrained enum, two bounded identifiers, integers, a float and a timestamp | test 16 |
| g | **Reversal cost stated**: migration 012 down, plus the `_persist` judge block, the eligibility helper, `config` threading at 5 call sites, 24 tests, and 5 environment variables | §4 |
| h | **Review date: 2026-11-10.** By then either a consumer gate is declared or migration 012 is reversed | test 20 — a test that **fails on and after that date** unless a successor record exists. A date with no failing check is a wish |

**No threshold is pre-registered, and an earlier revision of this section was wrong to try.** It
named `≥ 15%` over 200 judged rows and justified 15% as "above the upper bound of §1.3's
false-positive interval (1.4–16.5%)" — 15% is *below* 16.5%, so the number sat inside the interval
of the judge's own error and a gate firing there would have been fully explained by judge bias. The
200-row denominator was the same self-sealing structure round 6 caught: §0 records that a
per-group denominator is not reached at this volume, so the condition could not fire.

What is pre-registered instead is the **order of operations**, which is the part that actually
prevents ratifying whatever the data shows:

1. the successor establishes that a usable denominator exists **and** that the `shed` fraction is
   small enough for the rate to mean anything — §3.4 states shedding is bias, not thinning, so a
   rate computed over a shed-heavy window is not a measurement
2. it re-measures the false-positive floor on its own window, since §1.3's is one sample of an
   unrecorded spread with a 1.4–16.5% interval
3. **only then** does it fix a threshold, and it states the threshold before looking at the
   collected rates

Any successor that fixes a number before (1) and (2) is doing what this revision just did.

### 2.2b The deployment that turns it on is named

Round 6's self-sealing finding kept coming back in a new form: default-off means nothing
accumulates, so the successor's precondition ("a usable denominator exists") can never be met, and
2026-11-10 arrives with zero rows and a reversal. Three revisions answered that with a switch and no
one to flip it. The concrete answer:

**The dogfood deployment turns it on, on the local `claude-code` bridge, for its own tenant only.**

That is not a promise about a hypothetical operator — it is the deployment this repo already runs
against the corpus every measurement in §1 was taken from.

**Correction, and it matters: the `claude-code` bridge is not local.** An earlier revision said
choosing it means "no text leaves". It does not. `nexus/nexus/tools/claude_llm_bridge.py` runs the
host's authenticated `claude -p` headless — **keyless, not private**: the query and evidence go to
the same provider, billed against the operator's existing Claude Code auth instead of an API key.
What the bridge buys is no separate key and no marginal billing, plus `--no-session-persistence` so
prompts are kept out of the local transcript. It does **not** answer §2.3's egress question, and
citing it as if it did would have let this SPEC claim a control it never had.

So the dogfood switch-on is an acceptance of the egress, made by the person who owns the corpus,
which is the same act §2.3 describes and not an exemption from it. The bridge reports no tokens
(§3.3), so that deployment gets rows and no cost figures — the right trade for a first window whose
question is *does `insufficient` ever fire*, not *what does judging cost*.

An earlier revision also cited ADR-0002's *"Khala is where the signal would first appear… the
natural observation post"* as authority here. That sentence is about **cognitive debt** appearing
first in an AI-native repo, not about switching instruments on, and it is withdrawn as support.

**The first window's question is binary, not a rate**, and that is what makes a low-volume
deployment sufficient for it: *does `insufficient` ever fire in production, on real queries nobody
wrote labels for?* Today the answer is unknown and unknowable — §1's `0 of 5` is offline. A handful
of rows answers it; §2.2's step 1 denominator is the **successor's** precondition for a threshold,
not this SPEC's for shipping. Conflating the two is what made three revisions self-sealing: the
instrument was being held to the sample size of the gate it is not allowed to define.

If the switch is not flipped, the loop is unbroken and test 20's reversal is the honest outcome.
Naming the deployment is what makes the difference between a plan and a hope.

### 2.3 Egress is the operator's decision, and the default is the control

The judge sends the **raw query and raw evidence text** to the configured LLM backend.
`search_log` has deliberately never held either (`init.sql:430`, Nexus principle #3), and §3.5
keeps it that way — but the call routes that text to a provider.

That is a deployment fact — but **not the one an earlier revision claimed**: the `claude-code`
bridge is keyless, not local (§2.2b), so text reaches the provider on every backend this repo has.
What differs is billing and which credential carries it. So the SPEC does not decide it — but it does not let one flag decide it for everyone either. An
earlier revision made `NEXUS_SUFFICIENCY=on` a **deployment-wide** switch while the corpus it
routes is **tenant-scoped**, so one operator's flip would have sent every tenant's queries and
document bodies to the provider with no per-tenant opt-in. Two changes fix that:

* **`NEXUS_SUFFICIENCY_TENANTS`** — an explicit allowlist; empty means none. A tenant not named is
  `disabled`, so consent is recorded per corpus rather than per process. There is no `*`.
* **`sufficiency_judge` records the backend**, as `{backend}/{model}/{prompt_sha}` — otherwise a
  row cannot say whether the text went to a local bridge or an external API, which is the only
  fact that matters when someone asks later what left the building. Recorded plainly because it went unnoticed until the fifth round: **the offline evaluations in
§1 already sent Pack B text to the API backend**, and §6 asks a successor to expand the label set,
which would send more of the same partner text down the same path. Ruling the harness out of scope
would leave the only path that has actually fired uncontrolled, so it does not get ruled out.

An earlier revision's rule — "evaluation runs over a partner corpus use the local `claude-code`
bridge" — is **withdrawn as inert**: per §2.2b the bridge is keyless, not local, so choosing it
controls billing and not egress. What replaces it is the only control that bites: **an evaluation
run over a partner corpus records, in its run artifact, that the corpus owner consented to the text
reaching the provider, and names which backend received it.** This constrains the author, which is
the point — the production switch has an operator to accept the risk, and the harness has only me.

**On "system decides, LLM narrates":** what is recorded is an LLM's opinion, labelled as one, by
(a) above. A bad number here means the retrieval machinery is failing, not that a person has
stopped understanding — which is why it is substrate instrumentation and not gate ⓐ's subject
matter, and why it needs ⓐ's human-sourced signal to remain a different thing rather than a
weaker version of it.

## 3. Design

### 3.1 Where it runs

Inside `_persist`, the detached body of `record_search`. From `nexus/nexus/search/signals.py:155`:
`record_search()` is awaited by its callers and runs synchronously up to `create_task`; only
`_persist()` runs detached; `record_search(sig, await_persist=True)` — the CLI — waits on purpose so
the row lands before `close_pool()`.

* server paths (`api.py:367`, `:447`, `:922`, `a2a/server.py:331`): answer latency unchanged
* CLI (`cli.py:273`): the command does wait. Accepted — it has already blocked on the answer's own
  LLM call, and this is one more of the same order over the same evidence
* the verdict is not available to that request's caller, by design

**Two local `try/except` blocks inside `_persist`, not one.**

The judge call has its own, because the outer handler that already wraps `_persist` swallows the
exception *and skips the UPDATE*, so a raising judge would leave the row `pending` forever —
indistinguishable from stranded once `sufficiency_at` ages out. That handler is what makes `error`,
`timeout` and `unparseable` reachable at all (test 5).

**Everything this SPEC adds *before* the INSERT needs the same protection, and an earlier revision
left it uncovered.** The eligibility helper, `configured_column(cfg)`, `active_tokenizer()`, the
fingerprint hash, and slot acquisition all run ahead of the row. Under the outer handler alone, a
stale `NEXUS_EMBEDDING_COLUMN`, a tokenizer import failure, or `config` not threaded at one of the
five call sites would abort `_persist` and **lose the `search_log` row entirely** — corrupting
`v_search_health` and `v_image_gap_signal`, and violating §2.2e directly. So the prologue is
wrapped too, and its failure path is **the plain INSERT this SPEC found**, with everything else
unchanged. A broken instrument records nothing; it does not take the signal down with it.

That row is written **`uninstrumented`, not NULL.** An earlier revision wrote NULL and thereby gave
one value two incompatible meanings — "predates migration 012" and "the instrument broke on this
request" — in a column whose whole design (`pending`, §3.2) exists to keep failures from hiding in
the value readers are told to skip. A rising `uninstrumented` count is a deployment fault: a stale
`NEXUS_EMBEDDING_COLUMN`, a missing tokenizer, or `config` unthreaded at one of the five call sites.
NULL keeps its single meaning and stays a statement about *when the row was written*, never about
what happened during it.

On an `uninstrumented` row the other added columns are **`sufficiency_judge = 'off'` and everything
else NULL** — `evidence_fingerprint` included, because the prologue raising is precisely the case
where it could not be computed, and writing a partial or fabricated fingerprint would put a wrong
grouping key on the row. §3.3's "on every row" rule holds for `sufficiency_judge` and stops there.
Tests 5b and 8 cover both.

**Eligibility is decided once**: `not_applicable` → `disabled` → `shed`, in that order, in **one
helper in `signals.py`** — not at the five entry points, which would let the same deployment state
store different values by path and silently split the series. A search-only request on an off
deployment is `not_applicable`: what the row *is not* is more informative than what the deployment
has switched off.

Only searches where an **answer was attempted** are eligible. `search_log` also records search-only
requests; there is no answer there, `sufficient` has no established meaning, and the cost argument
(the evidence text was already paid for once) does not hold.

### 3.2 The write protocol

Two statements, **separately committed**:

    id = INSERT INTO search_log (..., sufficiency, sufficiency_at) VALUES (..., $n, now())
         RETURNING id                    -- $n = the terminal value if known, else 'pending'
    ... judge, inside its own try/except ...
    UPDATE search_log SET sufficiency = $1, ...          -- sufficiency_at is NOT overwritten
     WHERE id = $2 AND sufficiency = 'pending'
       AND sufficiency_at > now() - interval '300 seconds'   -- stranded is terminal

`sufficiency_at` means **when the observation started**, and only that. An earlier revision had the
UPDATE set it to `now()`, which would have made one column mean start-time on `pending` rows and
finish-time on judged ones — and would have made the row's own age, the input to the stranded rule,
unrecoverable after the fact.

* **Separate commits are load-bearing.** Each `db.execute` / `db.fetch_val` takes its own pooled
  connection and autocommits (`nexus/db.py:69`). `db.execute_in_transaction` **must not** be used:
  one transaction across both means a hung judge or process exit rolls back the INSERT and the row
  is lost. Losing a verdict is cheap; losing the row corrupts `v_search_health`,
  `v_image_gap_signal` and every other consumer.
* **Keyed by primary key** from `RETURNING id`. Nothing else on this table is unique.
* **`AND sufficiency = 'pending'`** so a late verdict cannot overwrite a terminal value. Zero rows
  matched means purged or already stamped; logged at warning, not retried.
* **Terminal values are written at INSERT when already known** — no UPDATE follows, so a `shed` row
  killed mid-flight reads `shed`, not `pending`.
* **One slot spans the whole observation** — taken **before the INSERT** and released **after the
  UPDATE**. Two earlier revisions got this wrong in opposite directions and the corrections are
  what fixed it: releasing the slot when the judge returned left UPDATE checkouts bounded by
  request rate rather than by the cap, and deciding `shed` without holding the slot was a
  check-then-act race across the INSERT — the same race §3.4 rejects `asyncio.Semaphore` for.
  Holding one slot end to end resolves both: `shed` is knowable at INSERT because the slot was
  already tested and taken, and **concurrent pooled checkouts from this mechanism never exceed
  `NEXUS_SUFFICIENCY_CONCURRENCY`**, which is what keeps it off the answer path's pool. The cost
  is that a slot is held across two single-row indexed writes; that is small next to the judge call
  it already spans, and it is the price of the bound.

  **Release is unconditional — `finally`, never a code path.** The slot now spans an INSERT, the
  judge, and an UPDATE, so it can leak from far more than a hung provider: a slow pooled UPDATE
  (§2.2e's live failure mode), a cancelled task, or any raise outside the judge's own handler. At
  the default cap of 2, two leaks make every subsequent search record `shed` **forever, silently**
  — a failure that looks exactly like healthy load-shedding. Test 11c asserts release on the
  INSERT-failure and UPDATE-failure paths, which is where an earlier revision's `finally`-less
  reading would have leaked.

**In flight vs stranded.** `sufficiency_at` is stamped at INSERT while the timeout bounds only the
judge call, so acquisition plus a call running to just under the limit plus the UPDATE round-trip
can exceed the timeout on a *successful* path. Reusing the timeout as the stranded threshold would
manufacture faults. A row is **stranded** when `now() - sufficiency_at > 300 seconds` and
`sufficiency = 'pending'`; below that it is in flight. **The UPDATE carries the same 300s bound**,
so a judge returning after a row has been declared stranded cannot resurrect it — otherwise "no
retry, no reclamation" is a sentence rather than an invariant, and a raised timeout would let late
verdicts overwrite rows already counted as faults. The threshold is a **fixed constant, not
`2 × NEXUS_SUFFICIENCY_TIMEOUT`** — deriving it from a mutable env var would retroactively
reclassify every historical row when an operator retunes the timeout, and §3.3 makes the stranded
count a fault signal. 300s is comfortably above the 30s default plus any UPDATE round-trip; a
deployment raising the timeout past 150s must raise it too — the two are coupled, and the coupling
is stated rather than left to be discovered when late verdicts start being dropped by the UPDATE's
same-300s guard. Both live as **one named constant** in `signals.py`, not two literals, so they
cannot drift apart, and **`signals.py` refuses to start when `NEXUS_SUFFICIENCY_TIMEOUT` exceeds
half the constant** (150s) — prose coupling is what let three revisions drift, and a fail-fast check
is what makes it impossible to configure a deployment whose judge outlives its own stranded bound.

### 3.3 What is recorded

| value | meaning | judged |
|---|---|---|
| `sufficient` | the evidence answers the question | **yes** |
| `insufficient` | it does not | **yes** |
| `unparseable` | the judge replied in a form that could not be read | no |
| `error` | the judge raised — stamped by the local handler (§3.1) | no |
| `timeout` | exceeded `NEXUS_SUFFICIENCY_TIMEOUT` | no |
| `disabled` | switched off in this deployment (**the default**) | no |
| `not_applicable` | search-only row — no answer was attempted | no |
| `shed` | the concurrency cap was saturated, or the daily ceiling reached (§3.4) | no |
| `pending` | in flight, or stranded — read with `sufficiency_at` (§3.2) | no |
| `uninstrumented` | the prologue raised; the row was written **without** the instrument (§3.1) | no |
| `NULL` | the row predates migration 012 | no |

`sufficiency TEXT`, nullable, `CHECK` listing exactly those ten non-NULL values. **No backfill** — pre-migration
rows stay NULL, mirroring migration 011. A stranded `pending` is terminal: no retry, no reclamation.
A growing stranded count is a fault (pool exhaustion, repeated kills); naming an automated response
would be building the aggregation §2.1 forbids.

On **every** row including non-judged ones:

* `sufficiency_judge` — `{backend}/{model}/{prompt_sha}`, where `backend` names which client
  carried the text out (`claude-code` bridge vs direct API — both reach the provider, §2.2b) and
  `prompt_sha` is the first 8 hex of SHA-256
  over **the system prompt, the user-prompt template, and the decoding parameters** — not the system
  prompt alone, or two materially different judges share an identity. On a `disabled` row, where no
  backend is contacted and none may even be configured, the value is the literal `off` rather than a
  fabricated identity. The same applies to **every row where no backend was contacted** —
  `not_applicable` and `shed` included — so the rule is one line rather than a per-value table:
  `off` unless a judge call was actually attempted. This matters because §2.2's successor groups on
  this column, and a fabricated identity on the search-only path would pollute the grouping key.
  Tests 17 covers `disabled`, `not_applicable` and `shed`.
  What it cannot capture is the model version behind a provider alias — stated, not papered over.
* `evidence_fingerprint` — first 8 hex of SHA-256 over
  `{embedding_column}|{embedding_model}|{tokenizer}|{bm25_top_k}|{vector_top_k}|{rrf_k}|{snippet_max_chars}`.
  `tokenizer` from `active_tokenizer()` — §1.1's scope names mecab-ko BM25 and a mecab-ko→nori swap
  is live here. `embedding_column` from `configured_column(cfg)`, honouring `NEXUS_EMBEDDING_COLUMN`,
  since config file text can be stale. **Limit**: this fingerprints the retrieval *configuration*,
  not the corpus generation — re-ingest, re-embedding, or an ADR-0006 supersession changes what
  reaches the judge while it holds still. Comparisons across such an event must segment on `ts`.
* `judge_prompt_tokens`, `judge_completion_tokens`, `judge_cost_usd` — **their own columns**, never
  summed into the answer's. Cost is `compute_cost(...)` against the config pricing table, exactly as
  the answer path does, and NULL when tokens are unknown — the `claude-code` bridge case, where NULL
  means *not priceable*, not free.

**No `sufficiency_reason`.** Earlier drafts stored the judge's stated reason behind an opt-in. It is
LLM free text over query + evidence, so it can quote either verbatim, on the one table whose DDL
says the raw query is never stored — and no draft ever specified redaction, a quotation
prohibition, or a test on the opted-in path. A diagnostic field is not worth converting a schema
invariant into a toggle. Debugging the judge is what the evaluation harness is for.

### 3.4 Off by default; cap, shed, timeout, ceiling

* **`NEXUS_SUFFICIENCY` defaults to `off`.** An upgraded deployment makes no new provider calls and
  sends no text until someone sets it. Read per request. This is §2.2's egress control and §2.1's
  restraint in one switch.
* **Cap.** `NEXUS_SUFFICIENCY_CONCURRENCY` (default 2), **per process, not per deployment** — under
  N workers up to 2N observations are in flight and spend scales with N. Taken **before the INSERT**
  and released **after the UPDATE** (§3.2), so one slot bounds the judge call *and* both pooled
  checkouts. It is not released between them: doing so unbounds the UPDATE checkouts, and testing
  the cap without taking it races.
* **Shed, not queue.** The cap is a plain non-negative counter tested and decremented in one
  synchronous block with **no `await` between the test and the decrement**, which is race-free on a
  single event loop. `asyncio.Semaphore` is not used: it has no non-blocking acquire, and a
  `locked()` check followed by `await acquire()` is a check-then-act race that lets two callers past
  a cap of one. The cap is the only bound on concurrent spend, so its mechanism is specified rather
  than left to the implementer.
* **Daily ceiling.** `NEXUS_SUFFICIENCY_MAX_PER_DAY` sheds once that many rows have been judged
  today, where all three ambiguities are pinned rather than left to the implementer: the count is
  **per process** (like the cap, so N workers permit N × the ceiling — stated because the name reads
  deployment-wide), the day boundary is **UTC**, and the counter is **in-process**, so it resets on
  restart and a crash-looping worker never sheds. A DB-side count would be the per-day aggregate
  §2.2c forbids, which is why the weaker in-process counter is chosen and its weakness recorded.
  **Default 500**, not unlimited: an unlimited default means the shipped ceiling bounds nothing the
  first time someone switches the judge on, which is exactly when the bound is wanted. Round 5's cost objection was otherwise answered only by handing the
  operator a switch and no instrument: the cap bounds concurrency, not volume, and §2.1 forbids the
  aggregate that would reveal runaway spend. A **count** is not a rate and not a gate, so this stays
  inside that constraint while giving a deployment a ceiling it can set before switching on.
  **It bounds rows, not dollars**, and the two come apart: cost per judged row scales with the
  evidence text volume (`snippet_max_chars` × k), which is not held fixed, and `judge_cost_usd` is
  NULL on the `claude-code` bridge because that backend reports no tokens. So on the default
  deployment the ceiling is a row counter with no view of spend. A deployment that needs a dollar
  bound must use a backend that reports tokens and watch `judge_cost_usd` itself — §2.2c forbids
  this SPEC from shipping the aggregate that would watch it for them.
* **Timeout.** `NEXUS_SUFFICIENCY_TIMEOUT` (default 30s) releases the slot; it does not protect
  answer latency (§3.1 already does). Without it one hung call holds a slot forever and, at a
  default of 2, two of them shed every request thereafter.

Consequence of shedding, stated: **judged rows are a load-dependent, non-random subset** — shedding
correlates with concurrency, which correlates with query mix and time of day. Anyone computing a
rate must treat `shed` as bias, not thinning. One of the reasons no rate ships here.

### 3.5 Raw text does not enter the record

`search_log`'s DDL says "PII-safe: the raw query is NEVER stored — only sha256 + length"
(`init.sql:430`). With `sufficiency_reason` cut (§3.3), **no column added by this SPEC can hold
query- or document-derived text.** The three character columns are bounded by shape, not by
convention: `sufficiency` is CHECK-constrained to nine values, `evidence_fingerprint` is `CHAR(8)`
of hex, and `sufficiency_judge` is `VARCHAR(128)` holding `{model}/{prompt_sha}` — where `{model}`
is a provider-supplied identifier, so it is neither an enum nor a hash and the earlier revision's
"enum, hash, integer, float or timestamp" was overbroad. What matters is that none of them is a
free-text sink and none is written from the query or the evidence. The invariant is preserved
rather than converted into a toggle.

`SearchSignals` gains no text field. Query and evidence are call-scoped arguments, not logged, and
not interpolated into the warning emitted by **either** exception handler — the prologue's and the
judge's — both of which log `str(exc)` and the `search_log` id, never the prompt they were building.
Test 14 asserts it for the judge handler and test 5b for the prologue's, since an exception message
assembled from the evidence would put document text in the log the rest of §3.5 works to keep clean.

## 4. Ships

    nexus/nexus/llm/sufficiency.py   generate_full (usage) + timeout + effective-prompt accessor;
                                     docstring amended per §2.1
    nexus/nexus/search/signals.py    eligibility helper; judge inside _persist with a local
                                     try/except; INSERT…RETURNING id → guarded UPDATE
    nexus/nexus/api.py               pass `config` to extract_signals (3 call sites)
    nexus/nexus/a2a/server.py        pass `config` to extract_signals (1 call site)
    nexus/nexus/cli.py               pass `config` to extract_signals (1 call site)
    nexus/migrations/012_sufficiency.sql   7 columns + CHECK + COMMENT ON COLUMN (§2.1); no view
        sufficiency · sufficiency_at · sufficiency_judge · evidence_fingerprint ·
        judge_prompt_tokens · judge_completion_tokens · judge_cost_usd

**`sufficiency.py` is not unchanged**, contrary to an earlier draft: `judge()` calls `generate()`,
which discards usage (`llm.py:201`). The accounting already exists — `generate_full()` returns
`Usage` with `cost_usd` from config pricing (`llm.py:190`), and `search_log` already carries the
answer's three columns (`init.sql:451`), persisted by `signals.py` and read by `llm/budget.py`. A
one-line gap, not missing infrastructure.

The four entry points are touched only to thread `config` through for `evidence_fingerprint`.
`answer.py` and migration 011's `v_image_gap_signal` are untouched.

## 5. Tests

Deterministic; the judge is stubbed. **`NEXUS_SUFFICIENCY_TIMEOUT` and
`NEXUS_SUFFICIENCY_CONCURRENCY` are injected per test, and `now()` is injectable** — otherwise the
timing tests either sleep 30 seconds or assert nothing, and the cap tests pass at the default
whether or not the mechanism works.

1. **The judge runs in the detached task, not the caller's** — the stub records
   `asyncio.current_task()`; asserted different from the task that awaited `record_search`.
   Structural, so no wall-clock threshold to flake or pass vacuously.
2. **`await_persist=True` does wait** — the CLI contract, so the two paths cannot converge silently.
3. **Off by default**: with no environment set, no judge call is made and the row reads `disabled`.
   If this regresses, deployments start calling a provider silently. This is §2.2's control.
4. **The INSERT is committed before the judge runs** — read the row back on another connection and
   find it `pending`. Fails if both statements are wrapped in `execute_in_transaction`.
5. **A raising judge stores `error`**, not merely a warning — §3.1's local handler; without it the
   row strands at `pending`.
5b. **A raise *before* the INSERT still writes the row, as `uninstrumented`** — inject a failure
   into the eligibility helper and into `evidence_fingerprint` computation; the row is present, the
   rest of the signal is intact, and the value is **not** NULL. §3.1's prologue handler. Without it
   a stale `NEXUS_EMBEDDING_COLUMN` silently deletes `search_log` rows and takes `v_search_health`
   with them; with NULL instead, the fault hides among pre-migration rows.
6. **Stranded is distinguishable from in-flight, on the fixed 300s constant** — with an injected
   clock, a `pending` row at 299s reads in-flight and at 301s reads stranded, **and the classification
   does not move when `NEXUS_SUFFICIENCY_TIMEOUT` is changed**. An earlier revision wrote this test
   against `2 × timeout`, the rule §3.2 explicitly rejects; under §5's injected short timeouts that
   test would have failed a correct implementation and passed the forbidden one.
7. **Terminal-at-INSERT values write no UPDATE** — asserted by statement count, so a killed `shed`
   row cannot read `pending`.
8. **Eligibility precedence** — a search-only request on an **off** deployment reads
   `not_applicable`, decided in one helper so all five entry points agree.
9. **A late verdict cannot overwrite a terminal value** — the guarded UPDATE matches zero rows.
10. **All ten values round-trip distinctly**, only `sufficient`/`insufficient` count as judged, and
    the CHECK rejects an eleventh. `uninstrumented` and NULL are asserted **distinguishable**: one
    says the instrument broke on this request, the other that the row predates it.
11. **Saturation records `shed` without queueing, at `NEXUS_SUFFICIENCY_CONCURRENCY=1`** — pinned to
    1, since at the default of 2 a second call succeeds whether or not the cap works. The slot is
    asserted **held from before the INSERT until after the UPDATE** (§3.2): the second call is shed
    while the first is still in its UPDATE, which fails if the slot is released when the judge
    returns.
11b. **The mechanism never holds more pooled connections than the cap** — with
    `NEXUS_SUFFICIENCY_CONCURRENCY=1` and a slow UPDATE, a concurrent answer-path checkout
    succeeds. §2.2e's only documented failure route is pool contention, and it was asserted as
    enforced while untested until this test existed.
12. **A judge hanging past an injected short timeout records `timeout` and releases the slot** —
    asserted by a subsequent call succeeding at cap 1.
11c. **The slot is released on every path** — INSERT failure, UPDATE failure, and task
    cancellation each leave the counter at zero. Two leaks at the default cap make every later
    search read `shed` forever, which is indistinguishable from healthy shedding.
11d. **A tenant not in `NEXUS_SUFFICIENCY_TENANTS` records `disabled`** and no judge call is made,
    asserted by call count — §2.3's per-tenant consent, which a deployment-wide flag would have
    bypassed.
13. **`NEXUS_SUFFICIENCY_MAX_PER_DAY` sheds past the ceiling**, does not shed below it, and
    **defaults to 500** — asserted explicitly, since the same parameter was specified as 500 in one
    section and unlimited in another and no test caught it.
14. **Nothing reads the column**: no module outside `signals.py` and `migrations/` references
    `sufficiency` from `search_log`. **The scope limit is asserted in the test itself** — Python
    modules only; SQL clients, dashboards and the web UI are out of reach, which is why migration
    012 also carries the column comment (§2.1).
15. **The judge never receives the answer**, asserted on call arguments.
16. **No column added by this SPEC can hold free text.** An `information_schema` type assertion
    cannot express this — `sufficiency`, `sufficiency_judge` and `evidence_fingerprint` are all
    character types — so the test asserts the specific shape instead: `sufficiency` carries the
    nine-value CHECK; `evidence_fingerprint` is `CHAR(8)`; `sufficiency_judge` is `VARCHAR(128)`;
    and **the migrated table gains no other character column**, asserted against an explicit
    allowlist. A successor adding one fails here and must amend the allowlist deliberately, which
    is the check §3.5 needs — an unbounded `TEXT` column is what would let document text in.
17. **`sufficiency_judge` is `off` on every row where no judge was contacted** — `disabled` (the
    default path), `not_applicable`, and `shed` — and `evidence_fingerprint` is present on all of
    them, since it describes the retrieval that happened regardless of whether a judge ran.
18. **Judge tokens land in their own columns**, the answer's totals are unchanged, and
    `judge_cost_usd` is NULL when the backend reports no tokens.
20. **The review date has teeth** — on or after 2026-11-10 the test fails unless a record in
    `specs/` or `adr/` carries the frontmatter key **`resolves: SPEC-nexus-sufficiency-signal`**.
    A string in a frontmatter field is mechanically decidable; "declares a consumer gate" is a
    property of prose and would have degraded into a grep heuristic. Adding the key is the
    successor's deliberate act, which is the point.
    §2.2h is otherwise a date nothing observes, which is how ungated observation becomes permanent
    maintenance surface. Note the interaction §6 records: if no operator ever accepts §2.3's egress,
    this test fires with zero rows collected and the correct response is to reverse the migration.
19. **`sufficiency_judge` changes when the system prompt, the user template, or the decoding
    parameters change**; **`evidence_fingerprint` changes when `NEXUS_EMBEDDING_COLUMN` changes and
    when the active tokenizer changes**.

## 6. Open items

* **Review date 2026-11-10** (§2.2h). By then a consumer gate is declared against §2.2's
  pre-registered threshold, or migration 012 is reversed. Ungated observation that nobody ever
  consumes is the maintenance surface ADR-0002's *taste = subtraction* exists to prevent.
* **`abstention-never-fires` does not close here.** The flag still reads `false` when the answer is
  absent; what ships is the instrument that could justify a fix.
* **May an LLM-sourced signal authorise a build?** Unsettled, and it decides whether these columns
  are ever more than a log. §2.1 no longer depends on the answer — the gate declaration does that
  work — but the successor still needs it.
* **Arm B is n=5 and clears its criterion 19% of the time by chance** — the least powerful control
  carries the most weight, being the only evidence that `insufficient` fires on genuinely absent
  facts. A successor must expand the unanswerable label set before relying on it.
* **Per-run artifacts.** §1.2's run spread was destroyed by a fixed output filename — the second
  such loss in this repo. No successor may quote a spread without per-run files.
* **The pre-registration claim is not independently verifiable** (§1.2): the artifacts are gitignored
  and a gitignored file carries no history establishing write order.
* **All of §1 rests on one 45-label set over one Pack B snapshot**, with the two persistent misses
  (`pb-loan-08`, `pb-space-01`) reproducible under the current prompt and model — the judge asks
  whether the question can be answered definitively, the label asks whether a word appears.
* **The shed fraction under real load is unknown** and the cap is per-process. A default of 2 is a
  guess. `NEXUS_SUFFICIENCY_MAX_PER_DAY` defaults to **500 per process per UTC day** (§3.4) — an
  operator running many workers, or wanting a tighter bound on the first day, should set it
  explicitly rather than trust a default chosen without load data.
