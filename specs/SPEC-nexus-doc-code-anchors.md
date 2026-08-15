---
id: SPEC-nexus-doc-code-anchors
type: spec
title: A document that describes code should hold a typed reference into it, so "is
  this doc stale" is a join and not a judgement
status: in_review
linked_adrs:
- ADR-0008
tags:
- nexus
- ingest
- code
- drift
---

## 0. Gate declaration

[[ADR-0008]] §3.3 fixes the procedure, quoting [[ADR-0002]]: *"a gate is **declared fired by the
director and recorded in that direction's first SPEC** — it is not argued into existence by the
SPEC."*

**Declared fired by:** LivingLikeKrillin, 2026-08-15, in session — after a review of doc/code/live-data
convergence, directing that this be the first unit of work.
**Puller:** the team deployment already answering from a corpus that describes a codebase the corpus
cannot see.

The evidence in §1 is **supporting material for how to build it, not the authorisation to build it.**
An earlier draft of this SPEC argued the work into existence from two external papers; that is the
move ADR-0008 §3.3 forbids, and it was removed.

### ADR-0008 §5 backstop, re-read

§5 requires this ADR be re-read "at the start of any work that would materially expand Nexus's
retrieval stack — a new retrieval channel, a second index backend, a tokenizer or embedding-model
change, or connector work beyond the existing two sources."

Re-read. Argued rather than asserted, because an earlier draft cleared the backstop by redefining
its terms:

- **"A second index backend"** in ADR-0008 means a substrate alternative to Postgres — the whole ADR
  is about whether to move off it. This unit adds **tables inside the existing substrate**. That is
  not a second backend under any reading of the ADR, though it *is* durable state Nexus does not have
  today, which the earlier draft obscured by saying "there is no new index backend" full stop.
- **"A new retrieval channel"** — nothing here is reachable from `/search`. §2 holds that as a
  non-goal, and if a later unit moves it, the backstop fires then.
- **"Connector work beyond the existing two sources"** — the checkout produces no documents and
  enters no source adapter. It is read the way `code_source.py` reads it today.
- **Tokenizer / embedding model** — untouched.

The director's call, not this SPEC's, is whether adding durable state to the substrate counts as
paying the incumbent's cost again. It is surfaced here so the call can be made.

## 1. What prompted it

The corpus answers "what is the policy" from prose. The system it describes lives in code. When the
prose stops matching the code, nothing in Nexus notices, and the reader gets a confident answer from
a stale document.

Two constraints shape the design — neither is a claim about Nexus's measured behaviour, which has
not been instrumented for this.

**Asking a model which one is stale has bad precision at corpus scale.** DocPrism (PACMSE 2026)
reports a naive LLM judge flagging **98% of functions** as inconsistent at **14% accuracy**;
category filtering brings the flag rate to 14% at 94% accuracy, with inconsistency-level precision
**0.63**. Independently, corpus-wide contradiction detection has been human-validated near **70%
precision** (PaperQA2, biology papers). These are different tasks on different corpora and do not
compose into a prediction for this corpus; they are enough to say a bare LLM verdict is not a
foundation to build on.

**A structural anchor does not need a model at all.** If the document holds a typed reference into
the code, "is this still true of the thing it names" becomes a lookup: does the symbol resolve, and
has its text changed. Swimm anchors doc snippets to source and re-anchors on commit; Dosu checks
backticked symbols against a declared `sources:` list; Toss binds evidence to code spans with a
commit SHA and re-verifies by span hash. Precision figures are not published for any of the three,
so this is a convergence of design, not of measurement.

Nexus already has half of it. `index/code_source.py` re-reads constants from the checkout at answer
time and reports `fresh`/`drifted`; `index/gate_source.py` parses Java with tree-sitter. Both are
limited to what a human registered by hand in `claims.yaml`, and neither stores anything — the
resolution is recomputed per call and discarded.

> **Note on a citation that was removed.** An earlier draft cited TRACE's finding that models detect
> documentation faults far more often than implementation faults, to argue the answer path is biased
> toward prose. That mechanism requires the model to see prose *and* code. §2 forbids code from
> entering the corpus, so the model never makes that comparison in Nexus and the finding does not
> transfer. It was the SPEC's headline justification and it was wrong.

## 2. Non-goals

- **Code does not enter the search corpus.** No code chunks, no embeddings over code, no code in
  `/search` results. Symbols are an anchor target, not a retrieval unit. Moving this is a decision
  that re-fires ADR-0008 §5, not a refactor.
- **No semantic edge typing in this unit.** `supported_by` / `contradicted_by` require judging
  whether prose and behaviour agree. This unit produces `mentions` only. A follow-up SPEC types the
  subset this unit shows has **changed** — a far smaller and better-conditioned candidate set.
- **Only backticked identifiers are extracted.** An earlier draft also extracted file paths, HTTP
  endpoints and configuration keys. Against a Java-symbol index those are structurally unbindable —
  a file path matches every symbol in the file (always ambiguous), and endpoints and config keys are
  not symbols (always zero). Including them would have inflated the refusal denominator with
  candidates that could never bind and made the yield number uninterpretable.
- **No new language support.** Java only, because that is the parser that exists.
- **No network at any point.** No GitHub App, webhook, API, or remote comparison. See §3.5.
- **No ranking change.** Drift state is a report, never a score input.

## 3. Design

### 3.1 Symbol index

Parse the repository at `code_source.repo_path` with tree-sitter. One row per symbol:

```
tenant, repo, file_path, symbol_kind, symbol_name, start_line, end_line, span_hash, scan_commit
```

- **Storage**: a new table in the existing Postgres, tenant-scoped like `documents` and `chunks`.
- **Uniqueness**: `(tenant, repo, file_path, symbol_kind, symbol_name, start_line)`.
- **Idempotency**: a scan replaces the prior scan for `(tenant, repo)` in one transaction. Re-scanning
  does not accumulate rows; symbols absent from the new scan are gone, which is what makes §3.4's
  `orphaned` computable.
- **`span_hash`**: `sha256` over the symbol's source text **normalised** — line endings to `\n`,
  trailing whitespace per line stripped, leading/trailing blank lines removed. Comments and
  annotations are **included**. Without the CRLF rule every anchor flips on a Windows checkout; the
  rule is stated so §6.3's one-line-change test has a defined expectation.
- No LLM. Every value here is a parse result, so a wrong one is a bug, not a probability.

### 3.2 Anchor extraction

At ingest, extract candidate references from chunk text: **backticked tokens matching a Java
identifier shape**. Nothing else (§2).

### 3.3 Binding, and refusing to bind

**Resolution key**: `symbol_name` exact match within `(tenant, repo)`. Not file-scoped — a document
naming a symbol rarely names its file, and requiring one would refuse nearly everything.

A candidate becomes an edge only if the key resolves to **exactly one** symbol.

| matches | outcome | recorded |
|---|---|---|
| 1 | edge, type `mentions` | `chunk_rid, symbol row, scan_commit, span_hash, bound_at` |
| 0 | no edge | refusal row, reason `unresolved` |
| >1 | no edge | refusal row, reason `ambiguous`, with the match count |

**Refusals are recorded, not dropped.** This is what makes re-binding possible (§3.6) and what makes
§6.1's split real rather than reconstructed.

An absent edge means *"no trustworthy link was established"* — never *"these are unrelated"*.

### 3.4 Freshness — a join, not a judgement

Re-check resolves the stored `symbol_name` against the current index:

| condition | state |
|---|---|
| 0 matches | `orphaned` |
| 1 match, `span_hash` equal | `fresh` |
| 1 match, `span_hash` differs | `changed` |
| >1 match (became ambiguous after binding) | `ambiguous_now` — the edge is retired, not re-pointed |

A symbol that moved to a different file with identical text stays `fresh`: the key is the name, and
the text is what the document was making a claim about.

**No LLM call is needed to learn that two hashes are equal.** Confining non-determinism to the rows
that actually changed is both the cost control and the quality control.

### 3.5 The snapshot guard — offline

A stale or dirty checkout makes every verdict above a lie in the confident direction. The guard must
therefore run **without network**, because §2 forbids it and because a guard that needs a remote
fails open exactly when the remote is unreachable.

Report states only when **all** of these hold:

- working tree is clean for the parsed subtree (`git status --porcelain` empty)
- `HEAD` is not detached
- the recorded `scan_commit` **is an ancestor of, or equal to,** current `HEAD`

Otherwise output `unknown` with the reason (`dirty`, `detached`, `scan_ahead_of_head`,
`scan_diverged`) and the recorded vs current commit. Staleness relative to a remote is deliberately
**not** assessed — that is the user's `git pull`, and a report that silently assumes it happened is
the failure this guard exists to prevent.

"Unknown" is a correct answer here. "Fresh" computed from a dirty tree is not.

### 3.6 Re-binding

Binding at ingest depends on whether a scan had run and whether the symbol existed at that moment.
Without a re-bind step, a document ingested first is unanchored forever and the yield number
measures scheduling.

So the drift command **re-binds refusals** before reporting: every recorded `unresolved` refusal is
retried against the current index. Refusals are cheap rows; retrying them is a join.

## 4. How this can lie, and what it costs if it does

- **Prose that names a symbol without referring to it.** Unique-resolution helps only for names
  defined more than once. A domain type with exactly one definition — `User`, `Session`, `Order` —
  mentioned in passing binds uniquely and falsely, and this is the failure mode most likely to
  dominate. It is not argued away; §6.2 measures it, and §6 states what that measurement can and
  cannot settle.
- **Rename churn reads as drift.** A refactor orphans every anchor to the renamed symbol. Correct,
  but arrives in bulk. Reported as a count with the causing commit, not as per-anchor alerts.
- **Java-only coverage invites a wrong denominator.** Every count is "of anchors bindable in the one
  language parsed". §6.5 requires the unparsed share printed beside it.
- **Reformatting yields `changed`.** Comments and annotations are inside `span_hash` by choice — a
  changed contract note is a real signal — so a comment-only edit produces `changed`. Until semantic
  typing exists, `changed` is a reading list, not a defect list, and must be labelled that way.

## 5. Limits

- `mentions` cannot say a document is *wrong*. It can say the thing it names has moved or gone. That
  is the honest ceiling of the deterministic layer, and the reason the follow-up SPEC exists.
- If the corpus rarely names symbols in backticks, this produces few anchors. That is a finding
  about the corpus, not a failure of the unit.

## 6. Acceptance

1. **Anchor yield** — candidates extracted; bound; refused split by `unresolved` vs `ambiguous`.
   **No threshold.** This unit is exploratory on yield: nobody knows how often these documents name
   symbols, and inventing a bar would be inventing the answer. The number is the deliverable.
2. **Precision sample** — 30 bound anchors hand-checked for whether the document is actually
   referring to that symbol, recorded with date and checker. **This sample cannot settle the
   precision question**: at n=30 the 95% interval is roughly ±17pp, which cannot separate 70% from
   90%. It is a screen with one pass condition — **if more than 6 of 30 are false, the extraction
   rule is rejected and this unit does not ship**, because at that rate the corpus is being polluted
   faster than the report is worth. Anything better than that is "not obviously broken", not
   "precise", and a larger sample is a separate decision.
3. **The net catches a real break** — in a scratch checkout: delete a symbol → `orphaned`; change one
   line → `changed`; move the symbol to another file unchanged → `fresh`; add a colliding definition
   → `ambiguous_now`. All four required.
4. **The guard fires** — dirty tree, detached HEAD, and a scan commit not an ancestor of HEAD each
   produce `unknown` with the right reason, never `fresh`.
5. **No LLM call, observably** — the drift path runs to completion in a process with no LLM provider
   configured and no API key present. Failure to reach a provider must not be the reason it passes;
   the run must succeed.
6. **Unparsed share printed** beside every count.

## 7. Units

1. Symbol index + scan command (§3.1) with the offline guard (§3.5).
2. Anchor extraction + binding + refusal recording at ingest (§3.2, §3.3).
3. Re-bind + re-check + drift report (§3.4, §3.6) with §6's numbers.

Follow-up SPEC, not this one: semantic typing of the `changed` subset.
