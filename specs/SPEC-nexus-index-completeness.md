---
id: SPEC-nexus-index-completeness
type: spec
title: Surface the coverage signal where someone reads it — the gap was measured,
  logged, and buried under an alarm that is always on
status: approved
linked_adrs:
- ADR-0006
- ADR-0008
- ADR-0009
tags:
- nexus
- index
- embedding
- observability
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-10T18:44:40Z'
content_hash: sha256:73ea975849674c394ae45b51fa730b5d865325bc4cc5e742d8cb30206988585f
---

## 1. What prompted it

On 2026-08-11 the queued next task was a ranking defect. Before implementing it the corpus was
inspected, and **51 of 334 active chunks in the operating tenant held no vector in the column this
deployment searches** (`embedding_1024`).

```sql
SELECT provenance_tier, count(*), count(*) FILTER (WHERE embedding_1024 IS NULL) AS missing
FROM chunks WHERE tenant = 'default' AND status = 'active' GROUP BY 1;
```

| provenance tier | active chunks | missing `embedding_1024` |
|---|---:|---:|
| `machine_read` (text read out of screenshots) | 45 | **45 — all of them** |
| `authored` | 289 | 6 |

All 51 carried `updated_at` inside the ingest window 2026-08-10 13:08–13:10 UTC, and chunks written
in that same window **did** receive vectors — so that run's vector indexing stopped partway. The
content that went missing is the whole payoff of [[SPEC-nexus-screenshot-text-extraction]]: the
policy text extracted from 44 screenshots was reachable only through the keyword leg, for a day.

`nexus reembed run --tenant default` filled 51/51 with zero failures in about four minutes. Both
rulers were then re-run on the repaired corpus.

**Retrieval** (`scripts/ko_eval_rank_crowding.py`, 40 answerable queries):

| | before repair | after repair |
|---|---:|---:|
| gold document **outside** the top 10 | 3 | **0** |
| top-10 slots held by tiny (<150 char) documents | 48/400 (12%) | 34/400 (8%) |
| queries whose top 10 is majority tiny documents | 3 | 2 (none missing gold) |

**Answers** (`scripts/ko_eval_answer_run.py --sufficiency`, same 40 queries, keyless bridge):

| sufficiency × outcome | before repair | after repair |
|---|---:|---:|
| insufficient / **abstained** — honest abstention, *fix retrieval* | 3 | **0** |
| insufficient / correct — parametric | 3 | 3 |
| sufficient / correct | 30 | **35** |
| sufficient / incorrect — generation defect | 3 | 2 |

The three honest abstentions were the missing chunks, and they are gone. The two remaining failures
are generation defects and are not this SPEC's business.

**The queued ranking work is withdrawn — and the withdrawal is bounded.** `3 → 0` is Recall@10 on
one run. It is *not* the pre-registered verdict rule of `SPEC-nexus-korean-embedding-comparison`
§4.7 (Recall@10 with MRR@10 breaking ties, two-sided sign test at α=0.05, no verdict below six
discordant pairs). Tiny documents still hold 8% of top-10 slots. The honest statement is **"no
remaining effect is visible to this ruler"**, not "the effect is zero". Reopening requires a
measurement, not an intuition; what was researched before withdrawing is recorded in §8.

## 2. What was already there, and why it did not help

The framing "nothing measured this" was **wrong**, and the first draft of this SPEC was built on it.
The critique caught it before any code was written.

**2.1 The measurement exists, and it was right.**
`embed_health.fetch_coverage_by_tenant()` counts, in one aggregate, per-tenant active chunks against
**both** vector columns; `log_embedding_coverage()` raises `embedding_coverage_partial` when a
tenant's populated count is below its active count. It fired, with the exact number:

```
2026-08-10 17:17:20 [warning] embedding_coverage_partial
    tenant=default column=embedding_1024 active=334 embedded=283 pending=51
```

**2.2 It is emitted only into a log, only at API startup.**
`api.py` calls it once on lifespan start. The HTTP `/status` payload carries
`embedding_coverage`; the CLI `nexus status` — the surface a human actually runs — carries **no
coverage at all**. It reports document counts, edges, generation labels, and waivers, and stays
silent about the one number that says how much of the corpus the vector leg can see.

**2.3 The true signal is buried under an alarm that is always on.**
The two pinned comparison corpora (`ko_eval_arm`, `ko_eval_packb`, 289 chunks each) hold no vector
in either column **by design**. Every startup therefore logs `embedding_column_empty` at **error**
level for both of them — 739 such lines in the current container's log. The one
`embedding_coverage_partial` that mattered sat in that stream. A check that cries wolf on a
deliberate state is why a true one goes unread.

**2.4 Refusing was already considered and rejected, and this SPEC does not reverse it.**
`log_embedding_coverage()`'s docstring records the decision: NULL vectors are an ordinary transient
state (just after ingest, a dead ingest, a 413 awaiting a waiver), a new tenant's first ingest is
legitimately coverage 0, and turning that into a refusal *"turns an ordinary ingest accident into a
whole-deployment outage — enforcement belongs where a cutover condition is; only a check with a
decision attached is entitled to refuse."* That reasoning stands. **No exit code changes here.**

**2.5 What is not established — and what follows from that.**
Whether the 2026-08-10 run *raised* or was *killed* is **unknown**. The ingest was run through
`docker exec`, whose output does not reach the container log, so the absence of a
`vector_indexing_failed` line there proves nothing. This is load-bearing: if the process died, no
in-process remedy — no line appended to `run_ingest`'s tail, no exit code — would have executed
either. **The remedy must therefore not depend on the ingesting process surviving.** Anything added
inside `run_ingest` is a convenience; the guarantee has to live where someone looks afterwards.

## 3. Design

### 3.1 Reuse the existing query. Do not write a second one.

`fetch_coverage_by_tenant()` already answers the vector question for both columns. This SPEC does
not add a parallel `vector_gap`. It makes three corrections to what is counted:

**(a) The population must be what the legs actually read.** The current predicate is
`status='active' AND is_quarantined=false`. The search legs additionally require the parent document
to be active (ADR-0006 containment; `search/hybrid.py`). Measured today that difference is **0
chunks**, and both supersession paths cascade to chunks — but a count that can drift into a
permanent phantom gap is exactly the failure of §2.3. The predicate gains the parent-document
condition so it cannot.

**(b) The keyword leg is not covered at all.** Add `bm25` to the same aggregate. Its dark state is
`tsvector_ko IS NULL` **or an empty tsvector** — `tokenize_korean()` keeps only whitelisted parts of
speech, so a chunk can yield no tokens and store `''::tsvector`, which is non-NULL and unreachable.
Measured today: 0 NULL, 0 empty. Both are counted because the present-versus-absent confusion is the
whole subject of this document.

**(c) Waivers are reported, not subtracted.** `embed_waivers` is `chunk_rid TEXT PRIMARY KEY` with a
separate `model` column — one waiver per chunk, ever, across both vector columns. It therefore
cannot express "waived for this generation", and subtracting it would let a waiver taken under the
768 generation silently mask a real 1024 gap. The count is displayed beside the coverage, never
folded into it. Making the waiver per-generation is an open item (§8), not this SPEC's work.

### 3.2 Put it where a human looks

`nexus status` prints one line per tenant that has chunks:

```
커버리지  default        active 334  vector(embedding_1024) 334  vector(embedding) 334  bm25 334
⚠ 커버리지  <tenant>     active N    vector(...) M  ← 벡터 다리가 못 보는 청크 K건 · nexus reembed run --tenant <t>
```

**Both vector columns are shown, deliberately.** ADR-0009 leaves *"a rollback guard for the post-flip
NULL gap"* as an open item due *"before any rollback, or the next SPEC touching the embedding
columns"*. This is that SPEC. Printing the old column's coverage next to the new one is the guard in
its cheapest honest form: whoever considers a rollback sees the gap they would be rolling into,
before they flip. (Measured today: the old column is 334/334 — a rollback would lose nothing.)

The ⚠ marks a tenant with a gap; the recovery command is named in the line, because a warning whose
remedy the reader has to go find is a warning that gets postponed.

### 3.3 Declared exemption for deliberately unindexed tenants

A tenant may be listed in `config.yaml` as holding no vectors on purpose:

```yaml
index:
  coverage_exempt_tenants: [ko_eval_arm, ko_eval_packb]
```

Exempt tenants are reported at `info` with the exemption named, never at `error`, and never with ⚠.
Exemption is **declaration, not inference** — nothing guesses from a name prefix or a zero count,
because a silent rule that hides zero coverage is the same failure as an alarm that never stops.

### 3.4 Ingest reports what it left behind, and this is the convenience, not the guarantee

`IngestResult` gains the post-indexing coverage for the tenant it just ingested, and `nexus ingest`
prints it. Per §2.4 the exit code does not change; per §2.5 this path is assumed to be *absent*
whenever the process dies, which is why §3.2 exists.

## 4. Non-goals

- **No refusal, no new exit code.** §2.4.
- **No retry or resume inside `run_ingest`.** `nexus reembed run` fills NULLs and is resumable. The
  defect was that nobody was told to run it.
- **The mixed-generation warning is not touched here.** The first draft proposed retiring it; that
  is withdrawn. See §8 — the evidence is recorded, the diagnosis is not, and deleting the only alarm
  on an invariant ADR-0009 records is not a thing to do as a side effect of a coverage SPEC.
- **No change to the ranking path**, on §1's bounded withdrawal.
- **No search-time disclosure** that a corpus is partially indexed. That is governance, and it needs
  its own decision.

## 5. What this SPEC's links trip

ADR-0009's open-item table names *"a mechanism that detects backstop events, or a declaration made
after the fact"* and *"a usable predicate for 'materially expand'"*, both due on **the next SPEC
that links ADR-0008**. This SPEC links ADR-0008, so **the trigger has fired and is recorded as
fired**. It is not taken up here: this document decides how an existing coverage measurement is
surfaced, and carries no judgement about backstop events. The obligation moves forward unchanged,
and the next SPEC linking ADR-0008 inherits it — it must not be able to claim the trigger never
fired.

## 6. Testing

Against Postgres in the `nexus-postgres` CI job, not the unit fixtures alone — the thing being
measured is a database state ([[ci-must-cover-destructive-paths]]).

1. Coverage counts a NULL-vector active chunk, and does **not** count: a quarantined chunk, a
   superseded chunk, a chunk of another tenant, **or an active chunk whose parent document is not
   active** (§3.1a — the case the first draft's tests missed).
2. The BM25 count catches both a NULL `tsvector_ko` **and** a non-NULL empty one (§3.1b).
3. A waived chunk still counts as a gap, and the waiver count is reported separately (§3.1c).
4. **Partial failure, not only total.** The embedding service raises for one batch out of several:
   the chunks of the surviving batches are populated, the failing batch's are not, and the reported
   gap equals exactly the latter. (Total failure is the easy path and would pass while this stays
   broken.)
5. **The process dies.** Coverage is computed by `nexus status` alone, with no ingest process
   involved, from a database seeded to look like 2026-08-10 13:10 — proving §3.2 does not depend on
   §3.4.
6. An exempt tenant with zero coverage produces no ⚠ and no `error`; a non-exempt tenant with the
   same state produces both — with both present in one database, as they are in the real one.
7. `nexus status` emits no ⚠ for a fully indexed tenant.

## 7. Acceptance

- A database seeded with an active tenant at 283/334 coverage and the two exempt tenants at 0/289
  produces from `nexus status` exactly one ⚠, naming the tenant, the count 51, and the recovery
  command. This is the reconstructable form of "what would have been printed at 2026-08-10 13:10
  UTC" — the original state no longer exists, so the criterion is a fixture, not a counterfactual.
- On the current database `nexus status` prints no ⚠ (the corpus is whole) and shows both vector
  columns at 334/334.

## 8. Open items

| item | why it is not decided here | when it is looked at |
|---|---|---|
| The mixed-generation ⚠ is currently **false** | `chunks.embed_model` is one label for two coexisting vector columns. Measured: all 334 active chunks in the operating tenant hold both a 768- and a 1024-dim vector; 215 are labelled `KURE-v1`, 119 `nomic-embed-text` (all 119 `updated_at` on 2026-08-10, all `authored`). The searched column is single-generation by dimension. **How the 119 labels arose is not established.** The leading hypothesis is a `reembed --column embedding --model nomic-embed-text` run keeping the rollback column warm, which would make the ⚠ a rollback-readiness artifact rather than corruption — untested. Retiring the alarm would also delete the only check on ADR-0009's recorded "one generation per column" invariant, and `vector_dims` cannot replace it (two 1024-dim models are indistinguishable). | Before the next embedding cutover, or when the ⚠ is next read as if it meant something |
| `embed_waivers` cannot express a per-generation waiver | PK is `chunk_rid`; with two columns live, one waiver cannot describe both. No waivers exist today (0 rows), so nothing is masked yet. | When the first waiver is taken under a second live column |
| ADR-0009's backstop-detection and "materially expand" obligations | §5 — fired, recorded, not taken up. | The next SPEC linking ADR-0008 |
| The ranking work, withdrawn on a bounded measurement | §1. Research already done and preserved: brevity bias is a named, measured phenomenon (arXiv:2503.05037) with **no mitigation proposed in the literature**; the standard remedy is filling `context_prefix` (Anthropic Contextual Retrieval; dsRAG's CCH-alone ablation 4.72→6.04 on KITE); Onyx's Notion connector prepends the page title but not the parent database title; late chunking does not apply, because a one-line row is not a fragment of a longer document. | If a measurement under §4.7's verdict rule shows a remaining effect |
