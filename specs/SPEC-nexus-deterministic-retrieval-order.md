---
id: SPEC-nexus-deterministic-retrieval-order
type: spec
title: Deterministic ordering in the retrieval legs — the same query must not depend
  on physical row order
status: approved
date: '2026-08-03T10:08:58Z'
linked_adrs:
- ADR-0006
tags:
- nexus
- search
- correctness
- determinism
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-03T10:31:11Z'
content_hash: sha256:935de5c2ab8f64015bc91284fd6966449c2e9929cfb3a6058e05ae67f17ea910
---

## 1. Goal

The same query, against the same corpus, returns different results depending on the order rows
happen to sit in the heap.

Measured 2026-08-03 while trying to record the Korean evaluation set's floors: the same
265-document pack, loaded twice, scored `Recall@10` between 0.700 and 0.775 with 9 to 12 misses.

**The evidence that this is ordering and not content** (I-010):

- The index was identical. `md5(string_agg(tsvector_ko::text, '|' ORDER BY source_uri,
  chunk_index))` over each load's chunks returned the same digest, so the tokenised text and its
  ordering-independent aggregate matched exactly.
- Scores were identical. Running one query's SQL against both loads returned the same score
  sequence (`3.5, 3.4, 2.4, 2.2, 2.0, 2.0 …`) and the gold document at the same *chunk* rank.
- **Control**: querying one load twice returned identical results every time. Only a *reload*
  changed the answer — which is exactly the axis physical row order moves on.
- What differed was the order of rows *within equal scores*, and therefore which chunks fell inside
  `LIMIT 20` and which documents survived the collapse to ten.

The cause is that ties are left unordered:

```sql
ORDER BY rank_score DESC          -- nexus/search/hybrid.py, keyword leg
ORDER BY distance ASC             -- vector leg
```

`ts_rank_cd` ties densely — 13 to 16 distinct scores across the top 25 rows of a real query. Make
the order total, so the result is a function of the data rather than of the heap.

**Scope of the claim, stated up front** (I-004): this SPEC makes the **keyword leg** deterministic
and makes the **fusion and diversify layers** deterministic. The vector leg gets the same
tie-break, which removes tie nondeterminism — but *not* candidate-set nondeterminism, because
`idx_chunk_vector` is an **ivfflat ANN index** (`init.sql`). §4.3 says what that leaves open and
what would close it.

## 2. Non-goals

- **Changing relevance.** No score, weight, or ranking formula changes. This decides only what
  happens *between rows the scorer already called equal*.
- **Making the ranking better.** A stable order is not a better order. A tie-break that tried to
  improve relevance (recency, authority, chunk position) would be a ranking change with its own
  evidence requirement.
- **Making ANN retrieval exact.** §4.3.
- **Fixing document identity.** ADR-0006 records that `tenant:filename` is both too coarse and too
  fine; §4.2 bounds what that costs this design rather than repairing it.
- **Recording the Korean evaluation set's floors** (I-011). That is a follow-on unit under
  `SPEC-nexus-korean-retrieval-eval`, with its own numbers and its own CI obligation. Binding it to
  this fix would mean an unrelated floor regression could block or falsely validate an ordering
  change. This SPEC is testable on its own.

## 3. What exists

Query text is the post-ADR-0006 baseline — both legs already carry the containment predicate
`AND EXISTS (SELECT 1 FROM documents d WHERE d.rid = c.doc_rid AND d.status = 'active')` plus the
tenant/clearance/quarantine filters (I-012). This SPEC edits only the `ORDER BY`.

| place | ordering | tie behaviour |
|---|---|---|
| `_bm25_search` | `ORDER BY rank_score DESC LIMIT $4` | arbitrary — measured to vary between loads of identical content |
| `_vector_search` | `ORDER BY distance ASC LIMIT $4` | arbitrary; float distances tie less often, but duplicate and near-duplicate chunks do tie |
| `_rrf_fusion` | `sorted(..., key=score, reverse=True)` | inherits leg order via Python's stable sort — no tie-break of its own |
| `_diversify` | walks the fused order | same |

Retrieval output is also a function of `documents.status` (supersession, ADR-0006), which an
operator changes out of band. That is *intended* mutability, not nondeterminism: same data, same
answer.

**Why this was not noticed before.** Nothing measured retrieval twice on the same corpus.
`test_search_recall.py` uses five documents against a window of twenty, where the gold document
comes back whatever the order. The Korean set is the first instrument with a corpus large enough
(265 documents, window 10) for tie order to change an outcome, and this is the first thing it found
— before its own floors could be recorded (`SPEC-nexus-korean-retrieval-eval` §4.5).

## 4. Design

### 4.1 A total order in both legs, and at fusion

```sql
ORDER BY rank_score DESC, c.rid ASC     -- keyword
ORDER BY distance ASC, c.rid ASC        -- vector
```

and, explicitly rather than by inheritance (I-007):

```python
sorted(scores.values(), key=lambda x: (-x["score"], x["rid"]))     # _rrf_fusion
```

RRF scores are rank-derived and therefore tie *densely* — two chunks at the same rank in their
respective legs get the same score. Relying on Python's sort stability makes the fused order a
function of `_rrf_fusion`'s input construction; a later refactor to `heapq.nlargest`, a set, or a
parallel merge would silently restore nondeterminism with no failing test. The key is written out.

`_diversify` walks that order and appends, so it is deterministic once its input is — §6 asserts it
at the boundary rather than trusting the argument (I-008).

### 4.2 What `rid` gives, and what it does not (I-003, I-005)

`rid` is the primary key: unique, non-null, present on every row. It is a hash of the chunk's
identity — `make_rid("chunk", doc_rid, section_path, chunk_index)` — so:

- **It is stable across a reload of the same corpus**, which is the property this SPEC needs.
- **It is not derived from content.** Rename a file and every rid under it changes, because
  identity flows from `tenant:filename` (ADR-0006's known weakness, deliberately not fixed here).
  Identical *text* under a different name orders differently. Determinism is per corpus identity,
  not per corpus content, and that limit is inherited rather than introduced.
- **It is arbitrary but fixed.** Because it is a hash, ordering by `rid` does not systematically
  favour early chunks or one region of the uri space in any way a reader could predict — but it
  *is* a fixed preference applied to every query. Two chunks the scorer cannot separate will always
  resolve the same way. That is the price of determinism, and it is accepted deliberately: the
  alternative on offer is not "no preference" but "a different arbitrary preference each time".
  §6 measures the size of the effect rather than asserting it is zero.

### 4.3 The vector leg is only half-fixed, and this says so

`idx_chunk_vector` is `ivfflat`. An ANN index returns an **approximate candidate set** whose
membership can depend on `ivfflat.probes`, on which lists the planner visits, and on whether the
planner chooses the index at all for a given statistics snapshot. A tie-break orders whatever came
back; it cannot make the candidate set stable.

So this SPEC claims: **tie order in the vector leg becomes deterministic; candidate-set stability
does not.** §6 measures the residual with the same reload harness and the report records it. If the
vector leg turns out to vary across reloads with the tie-break in place, that is a separate defect
with a named remedy (pin `ivfflat.probes`, or accept exact scan for evaluation runs) and its own
SPEC. Claiming "both legs are deterministic" in the acceptance criteria would have been unreachable
(I-004).

### 4.4 What changes for a user

Among rows the scorer scored equal, a different one may be returned than yesterday's arbitrary pick
— once. After that the answer stops moving.

Two honest consequences (I-002):

- **Within a leg**, no row that outranks another *by score* changes relative position. Only tied
  rows reorder.
- **Across the `LIMIT`**, the returned set itself can change: when a tie straddles the cut, a
  different member of that tie survives. That is the mechanism §1 describes, so the set is *not*
  invariant, and §6 tests the invariant that actually holds (the scored match set below the limit)
  rather than one that does not.
- **Downstream**, a changed leg candidate set changes RRF ranks, so non-tied rows can move in the
  fused output. This is a consequence of the legs' cut, not of the fusion key.

### 4.5 The determinism claim assumes a quiesced index (I-006)

`embedding` and `tsvector_ko` are populated after insert, and ADR-0006 records re-embedding as
NULL-column driven. A query issued while a backfill is in flight sees a different *candidate set*,
not merely a different order. The guarantee is therefore: **for a corpus whose active chunks all
have their derived columns populated, the same query returns the same result.** §6's harness indexes
fully before querying, and the assertion is stated with that precondition rather than left implicit.

## 5. Error handling

None. The clause adds a column to an existing sort: no new query path, no new failure mode, no
schema change. `idx_chunk_bm25` is unaffected — the sort already ran over the matched set. The
added key can cost a comparison per tied row; the sets are bounded by `bm25_top_k` / `vector_top_k`.

## 6. Testing

Against Postgres:

- **The reload test, N = 3** (I-001, I-009). The same corpus is loaded into **the same tenant**
  three times (delete, re-ingest, index to completion), and after each load the same query set runs
  through the keyword leg. Assertion: the returned `(rid, rank)` sequences are **exactly equal
  across all three loads**, and — because rid carries the tenant, so a two-tenant comparison would
  legitimately differ — no cross-tenant comparison is used anywhere in this test.
- **It must be able to fail.** The same test body against a copy of the leg's SQL *without* the
  tie-break is expected to disagree across loads; because that disagreement is probabilistic, the
  suite additionally asserts **structurally** that each leg's `ORDER BY` ends with the primary key.
  The empirical half is what caught the defect; the structural half is what cannot flake.
- **The scored match set is unchanged** (I-002): with `LIMIT` raised above the number of matching
  rows, the `(rid, score)` set returned before and after the change is identical. This is the
  invariant that holds — the truncated set is not, and is not asserted.
- **Fusion determinism at the boundary** (I-007, I-008): `_rrf_fusion` given equal-score inputs in
  two different input orders returns the same output order; and `hybrid_search` over a reloaded
  corpus returns the same `hits` sequence — the user-visible layer, past `_diversify` and
  `final_top_k`, not just the legs.
- **The vector leg's residual** (I-004): the same reload comparison for the vector leg, reported
  rather than asserted green — with the ANN caveat named in the assertion message, so a failure
  reads as "candidate set varied" instead of "your tie-break is broken".
- **Effect size of the fixed preference** (I-005): the Korean set's per-query Recall@10 before and
  after the change, printed in the run's report. No threshold — the number exists so a reader can
  see whether an arbitrary-but-fixed preference moved anything.

## 7. Acceptance

- Loading the same corpus into the same tenant three times and querying it yields identical keyword-
  leg orders and identical `hybrid_search` hit sequences, on a fully-indexed corpus.
- Each leg's `ORDER BY` ends with the primary key, asserted structurally.
- The scored match set (below the limit) is unchanged by this SPEC, asserted rather than assumed.
- The vector leg's reload behaviour is **measured and recorded**, with any residual attributed to
  the ANN candidate set rather than to tie order.
- No change to scores, weights, or formulas.

Recording the Korean set's floors and re-running the tokenizer comparison happen **after** this
lands, under their own SPEC (§2).
