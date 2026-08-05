---
id: SPEC-nexus-ko-eval-pool-sensitivity
type: spec
title: A record of measurements already taken — how far the deferred pool adjudication
  could move the KURE verdict
status: approved
linked_adrs:
- ADR-0009
- ADR-0008
tags:
- nexus
- search
- korean
- embedding
- measurement
- evaluation
date: '2026-08-05'
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-05T09:28:49Z'
content_hash: sha256:771d69ef70a435c39b04d4a1cac9dae3bf525fd463482947c1b8dfd0ed0b212f
---

## 0. What this document is, and the order it was produced in

**This is a record of work already performed, submitted for gate approval after the fact.** The
instrument was repaired and re-verified, the bound computed, the concentration hypothesis tested and
falsified, and a 30-pair sample drawn and judged — **all on 2026-08-05, before this SPEC entered the
gate.**

[[ADR-0009]] §3(ii) records the same inversion — a declaration arriving after the artifact it
authorises — and calls it *"an exception, and calling it anything else would be worse"*, *"not a
licence"*, with *"nothing currently prevents recurrence"* left open. **This is that recurrence, and
it is named rather than smoothed.** No mechanism prevented it and none is claimed to now.

Why the record is submitted anyway rather than the work redone in order: redoing it would produce the
same numbers from the same store, and pretending the sequence was clean would be the worse of the two
available dishonesties. What is *not* claimed is that the process was followed.

**Consequence for the gate**: everything below is checkable — §3's inputs are published in full, §A
gives the sampling procedure exactly enough to re-run, and §7 is the test suite that would fail if
the numbers were wrong. Reviewers should treat the numbers as claims to verify, not as design to
approve.

## Backstop record

In the body, not the frontmatter: `Artifact.recompute_hash()` is `content_hash(self.body)`
(`arbiter/src/khala/arbiter/artifacts.py:51`, `hashing.py:10`), so a ruling in frontmatter can be
rewritten after approval with nothing to detect it.

```yaml
backstop:
- row: adr-0008-retrieval-stack
  reread: performed 2026-08-05 — ADR-0008 §5 and its resume-condition table were read before the
    work described here; conditions (a) and (c) were NOT re-checked (see §8)
  clause: none
  ruling: does-not-fire
  declared_by: LivingLikeKrillin
  declared_at: '2026-08-05'
  reason: >-
    Judged case by case, not by rule: this work reads an evaluation store and writes a report.
```

The ruling was made in conversation on 2026-08-05; the fields report it, and **nothing here proves
that** — the stamped `content_hash` also lives in frontmatter, so a body edit with a recomputed stamp
is one commit with no detector. An earlier draft claimed approval adds "tamper-evidence"; withdrawn.

**Why a re-read and a `does-not-fire` in the same record.** ADR-0008 §5's re-read is what one performs
*in order to judge* whether the work is a backstop event; it is not evidence that the event occurred.
So "read §5, judged it does not fire" is coherent, and it is what happened. Conditions (a) and (c)
prescribe their own re-reads **for a firing event** and were not performed — §8 states that as a fact
about scope, not as an admitted omission.

It does **not** reuse [[ADR-0009]] §4's ruling as a predicate — §4 says in terms that it is *"a ruling
on one case, not a predicate"* — and §6's path-shaped observation is a description of this change, not
a test for "materially expand".

## 1. What prompted it

`SPEC-nexus-korean-embedding-comparison` §4.5 deferred adjudication of **821 pooled candidates** and
defended the deferral with one sentence, inherited by [[ADR-0009]]:

> Unjudged documents count as non-relevant, and the arm that surfaces more new documents absorbs
> more of that penalty — here that is KURE, the winner. The reported gap is therefore *conservative
> against the conclusion*.

**Incomplete, not false.** It names the term that helps and omits the term that hurts: judging a
candidate relevant raises the gold denominator for both arms and a numerator only for an arm that
retrieved it, so some judgements widen the margin, some shrink it, and some **reverse** it. Nothing
had counted the third kind.

### 1.1 What was removed, and what was then done anyway

An earlier version specified a full adjudication protocol. It was removed on the ground that it is
design for work nobody had decided to buy. **Then 30 judgements of that same protocol were bought and
executed** (§4.5) — with a relevance criterion, a blind presentation rule and a proposer/reviewer
split, i.e. the removed protocol at n=30. The director approved that purchase before the sample was
drawn; what is inconsistent is the SPEC's rhetoric, not the sequence, and the inconsistency is
recorded rather than argued away.

### 1.2 ADR-0009's open items — routed, not ruled

Both SPECs in this round carry `linked_adrs: ADR-0008`, which is the event ADR-0009's table names for
two items (a detector; a predicate for "materially expand"). **This SPEC does not rule on that
table.** Reading a trigger's scope is the owner's call — the same principle applied to the rollback
guard below — and an earlier draft applied opposite rules to the same table in adjacent paragraphs.

What is put to the owner, **as questions requiring an answer, not as dispositions**:

1. The detector item is answered by `SPEC-nexus-retrieval-backstop-detector` with *"no signal in this
   repository detects a backstop event without the author's cooperation"*. **Does a disposition of
   impossibility discharge an item whose stated outcomes are "a mechanism … or a declaration made
   after the fact"?** If not, it stays open with its trigger spent, and nothing guarantees another
   ADR-0008-linked SPEC.
2. The **predicate** item is not addressed by either SPEC in this round.
3. The **rollback-guard** item triggers on "the next SPEC touching the embedding columns". This work
   touches `ko_eval_embeddings`, an evaluation store in a disposable test database, not the
   production `embedding`/`embedding_1024` columns. **Does the trigger fire?**
4. Whatever the answers, a reader of ADR-0009 alone still sees these items open. **Propagation needs
   a successor record or an `adr/README.md` pointer** — the same gap ADR-0009 was written to close
   for ADR-0008 §6.

**These four are a precondition on implementation, not a footnote.** No code from §6 is written until
they are answered — otherwise the answers arrive after the work again, which is §0's defect repeated
inside the document that names it. Approval of this SPEC is approval of the *record* (§2–§5, §A) and
of the plan in §6–§7; it is not authority to start §6 while §1.2 is unanswered.

## 2. What can reverse a query

### 2.1 The class-based shortcut — retracted

An earlier draft proved a theorem over `Recall@10` alone and concluded only **nomic-only** candidates
(285 of 821) could matter. The arithmetic is right and the theorem is wrong: the rule is `Recall@10`
**with `MRR@10` breaking recall ties** (`ko_eval_harness.outcomes`). A *shared* candidate sits at a
different rank in each arm's list, so judging it relevant moves the two arms' `rr` unequally and can
reverse a tie-broken outcome. Withdrawn.

### 2.2 The removal move

The comparison SPEC's §4.7 defines the **comparable subset** as answerable queries whose gold
documents hold no chunk either arm refused. So adjudication can *remove a query from the test*: a
newly-relevant document that is one of the **9 refused-chunk documents** takes its query out of the
subset. Available from any class, because the trigger is a property of the document.

**Its effect is not uniform, and an earlier draft overstated it.** Removing a *win* deletes a
discordant pair and helps the adversary twice; removing one of the 8 *ties* deletes nothing, since
ties are not discordant pairs. Removal is available on 20 queries; the DP applies it wherever it
helps and nowhere else.

## 3. The bound

Three moves, costed per query by subset search over that query's candidates:

| move | smallest `S ⊆ C` such that … | applies to |
|---|---|---|
| **flip** | `(Recall@10, MRR@10)` strictly better for nomic (`S` excludes refused-chunk docs) | any query |
| **tie** | the pair is exactly equal | **wins only** — a win→tie deletes a discordant pair |
| **removal** | `S` = one refused-chunk document | the 20 queries whose candidates include one |

**Search bound**: subsets up to `|S| = 4`. **The cap never bound** — every one of the 36 queries has a
flip at cost ≤ 4 and every win has a tie at cost ≤ 3, so no query was scored "unreachable", which is
the error direction §3 would otherwise inherit (an unreachable query raises the DP's minimum and turns
an upper bound on the adversary's price into a claimed lower bound).

Measured 2026-08-05 over the 36 comparable queries — **746 (query, document) pairs**; the other 75 of
the 821 belong to the 4 queries outside the subset. **The unit is the pair**, which is how
`pool-blind.json` counts: 40 queries × 12–26 candidates = 821 entries, verified by summing the file.

| flip cost | queries (of 36) | tie cost | queries (of the 27 wins) |
|---:|---|---:|---|
| 1 | 12 | 1 | 12 |
| 2 | 17 | 2 | 11 |
| 3 | 3 | 3 | 4 |
| 4 | 3 | — | — |

12 + 17 + 3 + 3 = 35, plus **q014**, already a nomic win needing no move: 36. The tie column covers
**only the 27 wins**, because a tie move on an already-tied query buys nothing; an earlier draft
printed it over all 36 and could not be reconciled with the DP's input. Tie is **cheaper than flip on
17 of the 27 wins**.

A dynamic program over `(W, L)` minimises total cost subject to `p > 0.05` **or** `W + L < 6`:

> **The confirmatory verdict survives unless at least 10 of the 746 pairs are judged relevant, in a
> specific pattern.** Reachable defeats at cost 10: `W22 L10, p = 0.0501` and `W23 L11, p = 0.0576`.

Both count. The pre-registered condition is `p > 0.05`, and `0.0501` satisfies it; an earlier draft
set that case aside as "too close to α", which is a post-hoc closeness judgement against a
pre-registered threshold — the same defect §4.5 records against itself. Here it changes nothing (both
cost 10), and it is corrected rather than left as a habit.

Current state: `W27 L1 T8`, 28 discordant pairs, `p ≈ 2 × 10⁻⁷`.

**Pool-conditional.** Only candidates the six pooling configurations surfaced can ever become
relevant; a relevant document none surfaced stays non-relevant by construction. This bounds
sensitivity to *this pool*, not to the corpus.

## 4. Concentration — real, and it buys nothing on the branch that was tested

`concepts/cluster-administration/node-autoscaling.md` alone holds a cost-1 position in **7** queries;
two documents together cover 11. The obvious inference is that judging the concentrated documents
first closes the cheap attacks. **Tested 2026-08-05 and false:**

| documents declared non-relevant | pairs | minimum cost |
|---:|---:|---:|
| 0 | 0 | 10 |
| 5 | 23 | **10** |
| 8 | 32 | **10** |
| 12 | 43 | 11 |

**82 distinct documents** each supply a cost-1 move, so removing the concentrated ones moves the
adversary to the bench.

**The complementary branch was not costed.** The curve above assumes those documents are judged
*non-relevant*.

**And the unit must be said carefully, because an earlier draft got it wrong.** Relevance is judged
per **(query, document) pair**, which is what the DP costs. So `node-autoscaling.md` occupying a
cost-1 position in 7 queries does **not** mean one document buys 7 moves — it means **7 judgements**,
one per query, exactly as expensive per move as any other. What concentration changes is not the
price in judgements but the **correlation between them**: the same document judged by the same
criterion across related queries is likely to go the same way. That is a statement about how the
judgements co-vary, not about the adversary's cost, and an earlier draft reported it as though two
documents could defeat the verdict. They cannot; eleven judgements could.

So the honest statement is: **concentration cannot purchase safety** (measured, above), and it does
not cheapen a defeat either.

## 4.5 The base rate — rule fixed before the sample, and where the rule failed

§3's bound is a worst-case quantity. The decision-relevant question is how many relevant pairs the
pool actually holds, which nothing had estimated.

- **Sample**: 30 pairs drawn uniformly without replacement from the 746, seed `20260805`, procedure
  in §A.1, list fixed before judging.
- **Criterion** (binary): relevant iff the document contains the information the query asks for — a
  document that could stand alone as the answer source. **Topical adjacency is not relevance.**
- **Read depth**: judgements made from headings and query-matching passages, not full readings. An
  unquantified error term on top of sampling error, in either direction.
- **Proposal and review**: `proposed_by` and `reviewed_by` recorded and required to differ.

**Two defects in this pre-registration, both recorded because they affected the result:**

1. **Two branches fire at once and no precedence was stated.** The rule said `k = 2–4` ⇒ "refuted,
   not replaced", *and* that a CI spanning the 10-pair threshold ⇒ "unresolved at n = 30". At `k = 2`
   both apply. **The softer branch was chosen after the data were seen**, which is precisely what
   pre-registration exists to prevent. §8 therefore reports **both** readings rather than picking one.
2. **Blinding was asserted without a mechanism.** The original pooling earned that word with a
   committed anonymised dump (`pool-blind.json`); this sample has no separate process, no held-out
   artifact, and the same actor computed the costs and proposed the judgements. §A is what a future
   reader gets instead: the full drawn list and every judgement, so the claim can be checked rather
   than believed.

### 4.5.1 Result — `k = 2` proposed, **review pending**

`proposed_by: agent`. `reviewed_by:` **empty**. Under §4.5's own rule a judgement without a reviewer
is not a complete record, so this is reported as an incomplete measurement, not as a finding — and
§8 ships nothing from it into documentation until the review lands.

| pair | query | candidate | basis |
|---|---|---|---|
| #4 | livenessProbe 와 readinessProbe 를 어떻게 나눠 설정하나 | `concepts/configuration/liveness-readiness-startup-probes.md` | the document's sections are the answer. Unambiguous. |
| #15 | 파드 안에서 API 서버로 요청을 보내려면 | `concepts/architecture/control-plane-node-communication.md` | lines 32–34: a pod connecting to the API server uses its service account; root certificate and bearer token injected automatically. **A judgement call.** |

Two borderline candidates were checked against the text and confirmed negative:
`dynamic-provisioning.md` holds no reclaim-policy material, `debug-pods.md` no force-deletion
material. Full list and reasons: §A.2.

Intervals are **Clopper–Pearson**, a binomial interval, applied to a draw made *without replacement*
from a finite population of 746. The exact sampling distribution is hypergeometric; at `n/N ≈ 4 %` the
binomial form is the conservative (wider) one and the "spans 10" conclusion is unaffected, but the
label "95 %" is an approximation and is stated as one. It also does not include §4.5's unquantified
read-depth error.

| reading | point estimate over 746 | 95 % CI (Clopper–Pearson) | spans 10 |
|---|---:|---|---|
| `k = 2` as proposed | 49.7 | [6.1, 164.7] | yes |
| `k = 1` if #15 is rejected | 24.9 | [0.6, 128.4] | yes |

**Both readings leave the interval across the threshold**, so the review does not change the
statistical answer — only the point estimate and the price of resolving it (≈ 30 further pairs at
`k = 2`, ≈ 170 at `k = 1`, computed afterwards).

**The sample size was chosen without a power calculation. That was an error**, recorded so the next
sample is sized before it is drawn.

**Resolution was not bought**, on the director's decision of 2026-08-05, on the ground that a 95 %
label changes no sentence in §8.

**The scope of an unreviewed record, applied consistently.** §4.5 requires `proposed_by` and
`reviewed_by` to differ, and this record has no reviewer — so it is incomplete by its own rule, and
an earlier draft nonetheless leaned on it in §8, §9 and in the decision above. Corrected: until the
review lands, the sample supports exactly one sentence — **the pool has not been shown to be free of
relevant pairs** — and it is cited nowhere else. It is still committed as an artifact (§6) because an
unreviewed judgement that is *published with its reasons* is auditable, while one held back is not;
the file carries `reviewed_by: null` and §7 pins that consumers reject a record in that state.

## 5. The instrument guard

The computation could not run until the instrument reproduced its committed output, and that caught a
defect first:

- `ko_eval_embeddings` (1906 × 2 arms, 10 refused) survived, but the `chunks` rows it references did
  not — `tests/conftest.py:clean_db` truncates `chunks`/`documents` and does not include the eval
  store. Folding returned empty lists and **both arms scored `Recall@10 = 0.000`**, a mechanically
  impossible number. (`suspect-the-instrument-first`, third occurrence in this work.)
- **Repair**: `cmd_load` deletes the embedding store before reloading, so the pack was reloaded
  through `load_pack` alone.
- **Provenance** rests on `set(ko_eval_embeddings.chunk_rid) == set(reloaded rids)` (1906/1906, zero
  either side) and `verify_arm`'s per-chunk `input_sha256` / `payload_sha256` comparison — the second
  is what proves the stored vectors belong to the text now in the table, and it was run.
- **Reproduction**: nomic vector 0.402 / fused 0.777 / keyword 0.771; KURE 0.975 / 0.988 / 0.771;
  comparable 36/40 with 9 narrowed documents; confirmatory 27 W / 1 L / 8 T — matching
  `tests/eval/reports/2026-08-04-nomic-vs-kure.md` exactly.

**Three things ship**, as their own commit ahead of anything else, so the incident fix is revertible
independently:

1. `ko_eval_embed_compare restore-chunks` — reloads the pack while preserving the embedding store.
   **It must verify content, not only rids**: rid sets are stable across pack revisions with unchanged
   file identities, so a drifted pack (different commit, same 1906 rids, changed bodies) would restore
   silently. It therefore re-runs `verify_arm`'s `input_sha256` comparison and refuses on any
   mismatch — an earlier draft checked rid sets alone.
2. **A precondition in `ko_eval_harness`**: abort if the chunk→document map is empty or any store
   `chunk_rid` is absent from `chunks`. Scoped to runs that read the eval store, so a keyword-only run
   or a fresh CI job with no store loaded is unaffected.
3. **`clean_db` gains `ko_eval_embeddings`** — the root cause. An earlier draft diagnosed it and
   changed nothing, leaving a manual recovery command as the remedy, which is the trigger shape this
   repo has twice rejected. Truncating the store together with the chunks keeps the two consistent.

   **The guard is opt-in, and the default is to truncate.** An earlier draft had the fixture refuse
   whenever the store was populated — which is the normal state on any machine doing this work, so the
   default would have blocked the entire suite for everyone, and the repo's disposable-test-DB
   discipline says the suite truncates. Inverted: `clean_db` truncates the store as it truncates
   everything else, and a developer who wants to protect an expensive store sets
   `NEXUS_PRESERVE_KO_EVAL_STORE=1`, at which point the fixture skips the store and the eval suites
   that depend on it are skipped rather than run against a stale one. Environment variable rather
   than a pytest option because `clean_db` is autouse and must read it without per-test wiring.

## 6. What ships, by path

| file | change |
|---|---|
| `nexus/scripts/ko_eval_pool_sensitivity.py` | **new** — move costing, DP, concentration curve, sampler; writes the report |
| `nexus/scripts/ko_eval_embed_compare.py` | `restore-chunks` |
| `nexus/scripts/ko_eval_harness.py` | orphaned-store precondition |
| `nexus/tests/conftest.py` | `clean_db` covers the eval store + the opt-in guard |
| `nexus/tests/test_ko_eval_pool_sensitivity.py` | **new** — §7 |
| `nexus/tests/eval/ko/pool-sensitivity-sample.json` | the 30 drawn pairs and their judgements, `reviewed_by: null` until reviewed |
| `nexus/tests/eval/ko/refused-chunk-docs.json` | the 9 documents holding a chunk either arm refused — derived from the store, committed so §A.1's population is reconstructible from files alone |
| `nexus/docs/KOREAN_SEARCH_QUALITY.md` | §8 |

All under `nexus/scripts/**` and `nexus/tests/**`; nothing in `nexus/nexus/**`. That is a description
of this change, not a predicate for §5's "materially expand".

## 7. Tests

- **Move costing**: recall-decided win, **MRR-decided win on equal recall**, exact tie, refused-chunk
  candidate (removal, not flip), a case where tie is strictly cheaper than flip, and a tie move
  attempted on an already-tied query (must be rejected as a no-op).
- **The DP** against synthetic ledgers with hand-computed minima, including one defeated only through
  `W + L < MIN_DISCORDANT` and one whose cheapest path mixes all three moves.
- **The search cap**: a synthetic query whose only move costs 5 is reported as *unreachable*, and the
  DP must treat unreachable as "no move available" rather than as a cheap one.
- **Reproducibility of the sample**: seed `20260805` over the committed `pool-blind.json` reproduces
  the same 30 pairs. This is the test that makes §A checkable without the database.
- **Regression, in two halves, because one fixture cannot cover both.**
  - *In CI, from a committed fixture* — the per-query `(outcome, flip cost, tie cost, removal
    availability)` table: this pins **the DP's arithmetic** and nothing more. The fixture is an output
    of the 2026-08-05 run, so it cannot verify that run: if the costing was wrong, no CI test fails.
    An earlier draft offered this as "the test suite that would fail if the numbers were wrong",
    which it is not.
  - *Store-dependent, gated on the eval store being present* — recompute the costs from
    `ko_eval_embeddings` and assert they equal the committed fixture. This is the half that verifies
    the costing, and it runs only where the store exists. Skipped-not-failed elsewhere, and the skip
    is reported, so "it passed" and "it did not run" are distinguishable.
- **The per-document concentration figures** (82 documents supplying a cost-1 move; the four-row
  curve) are covered by the store-dependent half only. §9 keeps them as recomputable on one machine.
- `restore-chunks` refuses on a rid mismatch **and** on an `input_sha256` mismatch with matching rids.
- The scorer precondition aborts on an orphaned store; `clean_db` refuses to truncate a populated eval
  store without the explicit flag.

## 8. Disposition

**Pending the review of §4.5.1, nothing from the sample is written to documentation.** Once reviewed,
`KOREAN_SEARCH_QUALITY.md` §3.4's sentence *"그 페널티는 새 문서를 더 많이 건져 올린 팔이 더 많이
받는다: 결론 방향에 보수적이다"* is **deleted**, and replaced by three numbers claiming neither safety
nor refutation: the worst case (**10 of 746**), the base rate (**k of 30, point estimate, 95 % CI**),
and the pre-registration's own unresolved branch conflict (§4.5). The general caveat stays: every
figure remains a lower bound.

**A new open-item row.** Adjudicating the pool (≈ 821 pairs, reviewed) is the only work that lets this
direction be cited as measured. Owner: LivingLikeKrillin. **Trigger**: `linked_adrs` — any future
SPEC or ADR that links `SPEC-nexus-korean-embedding-comparison` or ADR-0009 must state whether it
relies on the direction. An earlier draft wrote "the first time the direction is used to decide
something", which is the undetectable shape ADR-0009 deliberately rejected.

**An inference this SPEC made and now retracts.** An earlier draft put it to the director that the
sample's point estimate (25–50 relevant pairs against the 10 an adversary needs) is *evidence that
the confirmatory margin may be an artefact of incomplete adjudication*. **It does not follow.** The
10 are pairs in a **specific adversarial pattern** — particular queries, particular cost-1
candidates; the base rate describes relevant pairs **as the pool actually holds them**, scattered.
And §1's own three-way argument cuts both ways: a relevant KURE-only pair *widens* the margin.
A count of relevant pairs anywhere in the pool therefore places no bound on the probability that the
adversarial pattern is realised, and the two numbers are not commensurable. Reporting them side by
side (above) is legitimate; drawing that conclusion from the pair was not.

What would license a statement about the *likely* outcome is a distributional calculation — sample
relevant pairs at the estimated rate and compute the resulting verdict distribution. **It is not done
here**, and nothing in this SPEC should be read as standing in for it.

So what goes to the owner is narrower: **the deferral is not demonstrably harmless**, which is the
whole of what §3 and §4.5 support.

**Not re-checked**: ADR-0008 §5's conditions (a) and (c) prescribe their own re-reads (Onyx's hook
executor and `ee/` tree; the merged-PR record). Neither was performed. Asserting a null where a
performed check is required is the error ADR-0009 §2 warns about, so it is stated as not done.

## 9. Risks

- **The bound is worst-case**, and §4.5 gives it no comfortable base rate. Closing the item on the
  bound alone is a judgement, and after §4.5.1 it is a judgement against the point estimate.
- **Pool-conditional** (§3).
- **Concentration's favourable branch only** (§4).
- **Two shortcuts failed here** — the class reduction (§2.1) and concentration-first safety (§4).
  The subset search is slower and assumes nothing about the metric's shape.
- **The eval store is local and losable**; §7's committed fixture is what keeps the regression test
  runnable without it.
- **Arbiter's content hash covers the body only**, so frontmatter on every approved SPEC and accepted
  ADR is post-approval editable with nothing to detect it. Both SPECs in this round work around it by
  putting rulings in the body. **That is a workaround for a defect this SPEC does not own** — ADR-0009
  declined to dispose of a cross-cutting gap "in passing, in a record about something else", and the
  same restraint applies. Named, unowned, for the director to route.

## A. Appendix — the sample, so §4.5 can be checked rather than believed

### A.1 Draw procedure

Population: for each of the 36 comparable queries, in the order they appear in
`nexus/tests/eval/ko/labels.yaml`, its candidate list from `nexus/tests/eval/ko/pool-blind.json` in
file order, flattened to `(query_id, document)` pairs — 746 in total. The comparable subset is the
answerable queries whose gold holds no chunk either arm refused (9 such documents; q004, q023, q039,
q040 excluded).

Draw: `random.Random(20260805).sample(pairs, 30)`, **CPython 3.11+** — `Random.sample`'s algorithm is
an implementation detail and a different runtime may return a different subset, so the version is part
of the procedure, not context. The refused-chunk documents that define the comparable subset are
committed (`refused-chunk-docs.json`, §6) rather than re-derived from the store, so the population is
reconstructible from files alone. §7 pins that this reproduces the list below.

**If a future CPython changes `sample`**, the test fails and the recorded list — not the algorithm —
is what the sample *was*; §A.2 is the artifact, the seed is provenance.

### A.2 The 30 pairs and their proposed judgements

`R` = proposed relevant, `·` = proposed non-relevant. `proposed_by: agent`; `reviewed_by:` empty.

| # | query | candidate | | basis |
|---:|---|---|---|---|
| 1 | q028 HPA CPU 스케일 예제 | `tasks/configure-pod-container/resize-container-resources.md` | · | in-place resize, not HPA |
| 2 | q008 워드프레스+MySQL PV 예제 | `concepts/workloads/management.md` | · | kubectl bulk ops |
| 3 | q009 PVC 생성·연결 절차 | `setup/best-practices/cluster-large.md` | · | large-cluster sizing |
| 4 | q030 liveness vs readiness | `concepts/configuration/liveness-readiness-startup-probes.md` | **R** | sections are the answer |
| 5 | q024 볼륨 스냅샷 | `concepts/overview/working-with-objects/object-management.md` | · | object management styles |
| 6 | q015 노드어피니티 | `concepts/architecture/nodes.md` | · | node lifecycle, not affinity |
| 7 | q038 사이드카 주입 | `tasks/inject-data-application/downward-api-volume-expose-pod-information.md` | · | downward API |
| 8 | q009 PVC 생성·연결 절차 | `tasks/debug/debug-application/debug-service.md` | · | service debugging |
| 9 | q037 레플리카셋 개수 유지 | `concepts/cluster-administration/logging.md` | · | logging architecture |
| 10 | q003 Konnectivity 설정 | `tasks/debug/debug-application/debug-service.md` | · | service debugging |
| 11 | q032 파드 단위 sysctl | `tutorials/security/cluster-level-pss.md` | · | pod security standards |
| 12 | q024 볼륨 스냅샷 | `setup/best-practices/cluster-large.md` | · | large-cluster sizing |
| 13 | q019 환경 변수 전달 | `tutorials/kubernetes-basics/create-cluster/cluster-intro.md` | · | minikube intro |
| 14 | q033 스테이트풀셋 강제 삭제 | `tasks/debug/debug-application/debug-pods.md` | · | **checked**: no force-deletion material |
| 15 | q021 파드에서 API 서버 호출 | `concepts/architecture/control-plane-node-communication.md` | **R** | lines 32–34, SA token + root cert |
| 16 | q003 Konnectivity 설정 | `tasks/access-application-cluster/service-access-application-cluster.md` | · | Service access, not Konnectivity |
| 17 | q002 AppArmor 제한 | `concepts/policy/resource-quotas.md` | · | quotas |
| 18 | q031 PV Retain 정책 | `concepts/storage/dynamic-provisioning.md` | · | **checked**: no reclaim-policy material |
| 19 | q036 접근 모드 단일 파드 | `concepts/storage/ephemeral-volumes.md` | · | ephemeral volumes |
| 20 | q018 네임스페이스 기본 요청량 | `tasks/configure-pod-container/resize-container-resources.md` | · | resize, not LimitRange |
| 21 | q037 레플리카셋 개수 유지 | `concepts/cluster-administration/node-shutdown.md` | · | node shutdown |
| 22 | q017 자원 부족 시 축출 순서 | `tasks/debug/debug-application/debug-pods.md` | · | pod debugging |
| 23 | q008 워드프레스+MySQL PV 예제 | `concepts/configuration/manage-resources-containers.md` | · | requests/limits |
| 24 | q037 레플리카셋 개수 유지 | `concepts/scheduling-eviction/pod-priority-preemption.md` | · | priority/preemption |
| 25 | q027 kubeadm 업그레이드 순서 | `concepts/workloads/pods/disruptions.md` | · | disruptions/PDB |
| 26 | q005 EndpointSlice 분할 | `tutorials/services/pods-and-endpoint-termination-flow.md` | · | termination flow — topical adjacency, refused |
| 27 | q036 접근 모드 단일 파드 | `concepts/architecture/control-plane-node-communication.md` | · | unrelated |
| 28 | q014 리소스쿼터 | `concepts/containers/images.md` | · | images |
| 29 | q031 PV Retain 정책 | `concepts/storage/volume-pvc-datasource.md` | · | CSI cloning |
| 30 | q025 taint 효과 | `concepts/scheduling-eviction/topology-spread-constraints.md` | · | spread constraints |
