---
id: ADR-0009
type: adr
title: The embedding-model block of ADR-0008 is lifted - what the director declared,
  and what stays open
status: accepted
linked_adrs:
- ADR-0008
- ADR-0007
date: '2026-08-05T04:26:52Z'
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-05T05:11:02Z'
content_hash: sha256:3a4d5cb8cc39e3369517a6b7a43003eadd075de800dd214208ee22ae29e26888
---

# ADR-0009: The embedding-model block of ADR-0008 is lifted — what the director declared, and what stays open

## Status

**Proposed** — a successor record. It amends [[ADR-0008]] on **the embedding-model third of §6's
block**, which is lifted, and marks §2.6's "no instrument exists that could compare them" as
historical for embeddings. It also **records two readings** the director made on 2026-08-05 (§3, §4).
It amends more than one sentence, and saying "one point" would understate it.

Unchanged and still authoritative: the substrate decision, resume conditions (a)/(b)/(c), the
mecab-ko third of §6's block, and every other finding. It does not supersede ADR-0008.

**If this record is not accepted**, the shipped swap does not unship: it rests on the director's
declaration and on two approved SPECs. What would be missing is the ADR-side record — the gap this
exists to close.

## Date

2026-08-05

## Context — why a new record instead of an edit

[[ADR-0008]] §6 records that the Korean measurement gap "blocks three separate decisions: mecab-ko
retention, an embedding-model change, and resume condition (b)". **An embedding-model change has
since shipped** (KURE-v1 → the dogfood deployment, 2026-08-05). A reader of ADR-0008 alone would see
a block that was never lifted; the review of two downstream SPECs raised exactly that, twice.

Editing ADR-0008 in place was drafted and then abandoned. Where the rule lives took two corrections
to get right, so it is stated exactly: the invariant is **"accepted = content-hash stamped and
immutable"**, defined in `adr/README.md`'s status list, stated again in [[ADR-0007]] §3, and
originating with ADR-0005's own practice for ADRs 0001–0003. ADR-0007's *out-of-scope* entry
("Editing any accepted ADR") declines to decide the general question — it is not itself the
prohibition, which an earlier draft of this record claimed, and a later draft then over-corrected by
denying ADR-0007 carries the invariant at all. It does; it just is not the sole source.

The rule is also enforced mechanically: Arbiter recomputes the hash and flags a modified accepted
artifact as `tampered`. On 2026-08-05 the in-place edit was made, the ledger reported
`tampered: True`, the critic named the discipline, and the edit was reverted before any approval.
ADR-0007 is the **precedent for the shape** of this record — a successor amendment rather than a
patch.

## Decision

### 1. §6's embedding-model block is lifted — by declaration, on stand-in-corpus evidence

On **2026-08-05**, asked directly and with the limits named, the director (LivingLikeKrillin)
declared ADR-0008 §6's block on an embedding-model change **lifted** for the KURE-v1 swap. Three
grounds were recorded at the time: §6's block existed because *no* instrument existed; one now does;
its margin is large; and "(b) is the higher bar belonging to reopening Onyx adoption rather than to
this swap."

**The third ground was a misreading, and the declaration was re-confirmed without it.** §5 says
"(b) and (c) cannot reopen adoption alone — that is (a) — and (b) is a prerequisite for any
subsequent decision being evidence-based." Corrected, (b) is *more* pertinent to this swap, not
less. Shown that correction on **2026-08-05**, the director **re-affirmed the lift** on the
remaining two grounds, with the narrower reading available to a future reader and stated here: §5's
sentence sits inside the Sufficiency paragraph about reopening adoption, so "any subsequent
decision" can be read as decisions about *that* question — a defensible reading, not a compelled
one. **What is not claimed is that (b) was satisfied.** It was not, and the decision was taken on
stand-in-corpus evidence with that prerequisite open.

**The instrument, stated precisely enough to check** (`SPEC-nexus-korean-retrieval-eval`, approved
2026-08-02): Pack A = `kubernetes/website` Korean docs, 265 files pinned at commit `b035ea80`, 45
labels (40 answerable / 5 unanswerable), verdict rule fixed before any number was seen.

`Recall@10` on the 40 answerable queries — **two different quantities, not one metric on two
paths**:

| arm | vector leg alone (exact scan) | fused BM25 + vector (RRF) |
|---|---:|---:|
| nomic-embed-text | 0.402 | 0.777 |
| KURE-v1 | 0.975 | 0.988 |

The fused figures are higher than the vector-leg ones because the keyword leg carries most of the
fused result. That observation is what made the swap interesting — but it comes from the report's
**descriptive** section, which the report itself forbids citing as a model-quality claim, so it is
recorded here as motivation, not as evidence. Source:
`nexus/tests/eval/reports/2026-08-04-nomic-vs-kure.md`.

`2026-08-04-ann-vs-exact.md` measured each arm against **itself** through the ivfflat path and found
the exact→ANN delta to be ±0.000. **That is weaker than it sounds**: the run used `lists = 1`, where
a single list is scanned exhaustively, so exact ≈ ANN is close to guaranteed by construction. It
rules out a gross approximation loss at that setting on Pack A's 1,906 chunks; it says little about
the production index (167 chunks, its own `lists`), and the cross-arm ANN comparison is descriptive
because the ANN candidate set was never re-pooled.

**Significance, pooling, and what has no test at all** — a margin from 40 queries needs all three:

- **Pre-registered rule** (`SPEC-nexus-korean-embedding-comparison` §4.7, fixed before any number):
  Recall@10 per query **on the decisive leg — here the vector leg**, MRR@10 breaking recall ties,
  **two-sided exact sign test at α = 0.05**, and no verdict below 6 discordant pairs (below that the
  answer is "underpowered", not a borrowed verdict). The **comparable subset** is part of that rule,
  not a post-hoc trim: queries where **both arms embedded every gold document**. An earlier draft of
  this record cited the *tokenizer* SPEC's keyword-leg rule instead; that was the wrong instrument's
  rule.
- **Confirmatory reading**: 36 of the 40 answerable queries qualify (nomic refused 10 chunks —
  coverage 1896/1906 against KURE's 1906/1906 — and coverage is printed *above* the verdict by that
  SPEC's design). Result: **27 wins / 1 loss / 8 ties over 28 discordant pairs**, two-sided exact
  p ≈ 2 × 10⁻⁷ (one-sided ≈ 1 × 10⁻⁷). An earlier draft doubled both figures.
- **Pooling**: the pool was built from **six configurations** — keyword/mecab, keyword/nori,
  vector×2, fused×2, all legs at top-10 — and judged **blind**: candidates stripped of arm identity
  and shuffled with a recorded seed, the anonymised dump committed before adjudication
  (`pool-blind.json`, `pool-rev2-adjudication.json`), and labels carrying `pooled_over` so a
  configuration absent from the pool cannot be scored against that gold set. Adjudication was left
  incomplete, which is why every figure is a **lower bound**; this record does not upgrade them.
- **The production quantity has no confirmatory test.** What ships is the fused path, and the fused
  comparison lives in the report's *descriptive* section — which the report explicitly forbids
  citing as a model-quality claim. The confirmatory statistic covers the vector leg alone. That is a
  real limit on this lift and it is recorded rather than smoothed: the swap was justified by a leg,
  not by the end-to-end quantity users experience.
- **The ANN path was not re-pooled either.** `2026-08-04-ann-vs-exact.md` reads each arm against
  *itself* (exact → ANN, ±0.000) precisely because a changed retrieval path surfaces documents the
  pool never judged; its arm-versus-arm ANN comparison is descriptive by the same rule. And it ran
  on Pack A's 1,906 chunks at `lists=1`, not on the production index's 167.

### 2. What the lift does **not** close

- **Resume condition (b) stays open — and (b) is about tokenizers, not embeddings.** Its text:
  "A Korean evaluation set exists that can compare **tokenizers** on Khala's real corpus, and its
  result does not favour mecab-ko." An earlier draft of this record paraphrased it as a general
  real-corpus condition and dropped both the tokenizer scope and the outcome clause; that was wrong,
  and the difference matters for what Pack B must satisfy.
- **§5's sufficiency text says something else than an earlier draft claimed.** It reads: "(b) and
  (c) cannot reopen adoption alone; they raise the priority of re-examining (a), and (b) is a
  prerequisite for any subsequent decision being evidence-based." So (b) does **not** gate reopening
  Onyx — (a) does — and (b) is named a prerequisite for *evidence-based decisions*. **The director
  acted on stand-in-corpus evidence with that prerequisite unmet**, judging the margin sufficient.
  That is the plain shape of the decision; dressing it as "(b) gates something else" was a
  misreading of the source and is retracted here.
- **Transferability between Pack A and khala's corpus is neither argued nor measured** — different
  domain, register and scale (265 public k8s docs vs 167 chunks of internal material). The lift, and
  the flip that followed it, rest on that unmeasured transfer.
- **§6's mecab-ko third is NOT lifted**, and the reason is power, not the absence of an instrument.
  The same Pack A pooled keyword/mecab and keyword/nori and *did* return a comparison (p = 0.180, 9
  discordant pairs) — so §2.6's "no instrument exists" is historical for tokenizers too. What is
  missing there is a decisive result: an underpowered null is not evidence of equivalence, mecab-ko
  was retained on it, and **ADR-0008's position that the retention is unevidenced stands unchanged**.
  The asymmetry between the two thirds is arithmetic: 28 discordant pairs at p ≈ 2 × 10⁻⁷ against 9
  at p = 0.180 on the same set.
- **The 5 unanswerable queries were not used.** Every figure above is Recall@10 over the 40
  answerable ones. Abstention and false-positive behaviour — where a stronger vector leg could
  plausibly get *worse* — went to production unmeasured. The instrument can carry it; nothing has.
- **Rule 9 motivates replacing nomic-embed-text; it does not select KURE-v1.** `nexus/CLAUDE.md`
  rule 9 forbids an English-only embedding model, and that is why the incumbent was questioned — but
  the choice of KURE-v1 rests on the comparison above, and **no broader survey of Korean-capable
  models was run.** ADR-0008 §4 recorded the reverse error (defending a tool as though it were the
  principle); this record avoids repeating it in the other direction.
- **(a) and (c) are not re-checked here.** ADR-0008 §5 prescribes how each is noticed — re-reading
  Onyx's hook executor and `ee/` tree for (a), the merged-PR record for (c) — and **neither re-read
  was performed for this record.** Onyx adoption therefore stays deferred on the existing finding,
  not on a fresh one. Saying "(a) and (c) are untouched", as an earlier draft did, asserted a null
  where a performed check is required.

### 3. Two procedural defects in how the swap was gated, and their disposition

**(i) §5's backstop re-read happened late.** An embedding-model change is a named backstop event,
and §5 asks for the re-read "at the start of any work that would materially expand Nexus's retrieval
stack". The re-read is recorded in `SPEC-nexus-embedding-cutover-seam` §1.1 — written *after* the
swap SPEC was approved and while the cutover was being built, not at the start of the work. It
happened; it happened late.

**(ii) The gate declaration came after the SPEC it authorises.**

ADR-0008 §3 item 3 asks that a gate be declared fired by the director **and recorded in that
direction's first SPEC**, attributing the procedure to [[ADR-0002]]. The declaration is dated
2026-08-05; `SPEC-nexus-kure-embedding-swap` was approved 2026-08-04. The order was inverted.

**Disposition: the swap stands.** It is not re-gated and not reverted — the director's declaration
covers it, and the evidence it rests on predates both dates. What is *not* claimed is that the
process was followed: it was not.

**This is an exception, and calling it anything else would be worse.** Neither ADR-0008 §3 item 3
nor the ADR-0002 procedure it cites provides for retroactive declarations, so recording one is a
departure, made once, for a change already deployed. **It does not amend ADR-0002** — this record
has no jurisdiction there, ADR-0002's discipline stands as written, and what is recorded here is a
single non-compliant instance, not a licence. **Nothing currently prevents recurrence**, which is an
open item with an owner rather than a hope.

### 4. §5's backstop, read once, for one repair

Asked whether §5's backstop ("a tokenizer or embedding-model change") fires for a defect repair that
deep-copies the tokenizer the stack had already loaded — so a length check stops sharing one Rust
object with the encoder (`SPEC-nexus-embed-tokenizer-race`) — the director declared on 2026-08-05
that **it does not**: nothing enters or leaves the retrieval path.

**This is a ruling on one case, not a predicate.** It does not define "materially expand", §5's
wording is unchanged, and the trigger remains a judgement the director makes case by case. That
limitation is real and is listed as an open item rather than papered over.

## Consequences

- **What shipped, and how far it reaches.** The dogfood deployment is a single-host Nexus (local +
  Cloudflare Tunnel, Access-gated), one tenant (`default`), 167 active chunks, re-embedded 167/167
  with zero failures before the flip. The invariants the cutover holds are recorded in
  `SPEC-nexus-embedding-cutover-seam`: one generation per column (`embed_health` reports a single
  `embed_model` for the target column), the old `embedding` column and its index **retained
  untouched**, and rollback = three `.env` lines plus a restart. Post-flip ingests leave the old
  column NULL; that gap is reported as a number by `nexus reembed status --column embedding`.
- **A revisit obligation, stated so it can actually be breached.** If a real-corpus set (Pack B, or
  any labelled set over khala's own corpus) is built and its **vector-leg Recall@10 comparison under
  the same pre-registered rule** (two-sided sign test, α = 0.05, ≥ 6 discordant pairs) does not
  favour KURE-v1 over the incumbent, this record is re-opened. **If the comparison is underpowered**
  (fewer than 6 discordant pairs) the rule returns "underpowered" rather than a verdict, and the
  obligation **stays open** — an inconclusive result does not discharge it. The obligation has no
  expiry: it is discharged only by a result, so it cannot lapse by an event failing to occur.
  Owner: LivingLikeKrillin.
- **Rollback is three `.env` lines *plus* a repair whose size grows.** The old column and index are
  retained untouched, so the mechanism is one restart — but post-flip ingests leave that column NULL,
  and a rollback would drop the vector leg for exactly those chunks. Stating "rollback = three lines"
  without that clause, as an earlier draft did, is false for any moment after the flip.
  `nexus reembed status --column embedding` reports the count and **no gate consumes it**: a rollback
  today succeeds while silently dropping them. Bounding it (a reverse re-embed first, or a refusal
  above a threshold) is not decided here and is an open item.
- **Model selection was a floor, not a field.** Two arms were compared. No survey of Korean-capable
  models was run, and this record creates no obligation to run one — it records that the choice
  rests on beating the incumbent, which rule 9 already disqualified.
- **A reader of ADR-0008 must read this record too.** `adr/README.md` carries the pointer, as it
  already does for ADR-0005 §3.
- **Nothing new is authorised.** No further embedding, tokenizer, or substrate work is unblocked;
  each direction still needs its own SPEC and gate.

## An observation, recorded because this record depends on it

Accepted ADR bodies are frozen, so a body's Status line and the ledger's can never be reconciled by
editing. On 2026-08-05, seven of eight ADR bodies disagreed with the ledger while all eight were
`accepted` in the ledger and in `adr/README.md`'s index — including ADR-0008, whose body reads
"In review", which is why this record had to establish that ADR-0008 was binding at all before
amending it.

**This makes no rule.** `adr/README.md` already defines `accepted` as stamped and immutable; the
observation is recorded only because the amendment above leans on it, and a reader checking that
lean deserves the fact rather than an assertion.

## Open items this record deliberately leaves

| item | owner | when it is looked at |
|---|---|---|
| A mechanism that detects backstop events, or a declaration made after the fact | LivingLikeKrillin | **The next SPEC that links ADR-0008** — a detectable event (`linked_adrs`), deliberately not "the next backstop event", since that is the thing nothing can detect |
| A usable predicate for "materially expand" — §5's trigger is a case-by-case judgement | LivingLikeKrillin | Same trigger as above |
| A rollback guard for the post-flip NULL gap | LivingLikeKrillin | Before any rollback, or the next SPEC touching the embedding columns |
| Pack B — a labelled set over khala's own corpus | LivingLikeKrillin | Unchanged from ADR-0008 §5(b); also the trigger for the revisit obligation in Consequences |
| Abstention / false-positive behaviour on the 5 unanswerable labels | LivingLikeKrillin | When the abstention mechanism is built (already an open item in `KOREAN_SEARCH_QUALITY.md` §6) |

**ADR-0008 §7's reconciliation gap** (#143's freshness TTL vs ADR-0006's deferral) is *not* taken up
here. ADR-0008 ruled it out of scope and said it needs its own disposition; attaching an owner and a
trigger to it would be that disposition, made in passing, in a record about something else. It stays
where ADR-0008 left it.
