---
id: SPEC-nexus-ranking-precision
type: spec
title: Ranking precision — cover-density lexical scoring and per-document diversity
status: approved
linked_adrs:
- ADR-0004
tags:
- nexus
- search
- ranking
- precision
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-11T18:45:36Z'
content_hash: sha256:f02147f400683dde470a90399c40f70e7fc50b08e63bd86dd7993d0d949443d5
---

## 1. Goal

Raise result **precision** with two changes, both bounded to the already-retrieved candidate set:

1. **Cover-density lexical scoring** — the BM25 leg ranks with `ts_rank`, which ignores term
   proximity and is biased toward long chunks. With OR-tsquery semantics (the recall fix), proximity
   is exactly what separates a real multi-term match from an incidental one. Switch to `ts_rank_cd`.
2. **Per-document diversity** — RRF dedups by chunk but not by document, so several chunks of one
   document can flood the top-k. Add a per-document cap so a single document cannot monopolize the
   results, with graceful fill when few documents match.

**Recall safety is empirical, not structural (I-001).** The diversity step (2) is a pure reorder of
the fused set and cannot drop a retrieved chunk. But (1) is *not* purely order-safe: `_bm25_search`
applies `ORDER BY score DESC LIMIT 20`, so when a query matches **more than 20** chunks,
`ts_rank_cd` and `ts_rank` can select a *different* top-20 into fusion — a gold chunk could shift out.
So the claim is not "cannot regress recall"; it is that the **recall harness (`misses = 0`, MRR ≥
0.80) is the gate**: this change ships only if the harness stays green, and if `ts_rank_cd` shifts a
gold chunk out of the fixture's top-20 the harness fails and we reconsider (e.g. raise the BM25
`LIMIT`). The safety is verified, not assumed.

## 2. Non-goals

- **A cross-encoder reranker.** Phase-2 work, gated on signals; not this SPEC.
- **The BM25 min-token-length filter.** Dropping single-syllable OR fragments (`엔` from `엔티티`)
  would improve precision but **drops query terms**, which can lower recall — and the recall harness
  enforces `misses = 0`. That filter needs its own recall re-tuning and is a **separate follow-up**,
  deliberately excluded here so this SPEC stays recall-safe.
- **Changing RRF weighting or `k`.** The equal-weight fusion and `k=60` are untouched; this SPEC adds
  a diversity step *after* fusion, it does not reweight the legs.
- **Vector-leg or graph changes.** Only the lexical score function and the post-fusion ordering.

## 3. What exists

- `_bm25_search` (`search/hybrid.py:66-70`): `ts_rank(c.tsvector_ko, to_tsquery('simple', $1))`,
  `ORDER BY rank_score DESC LIMIT $4`. The `WHERE … @@ …` set is unchanged by the score function —
  swapping `ts_rank → ts_rank_cd` re-orders the same matched rows.
- `_rrf_fusion` (`hybrid.py:140-165`): sums `1/(k+rank+1)` per chunk rid, `sorted(... reverse=True)`,
  returns `ranked[:final_top_k]`. Chunk-level dedup only; no document notion at this stage.
- `_enrich_hits` (`hybrid.py:206`) turns fused rids into `SearchHit`s carrying document metadata
  (incl. the owning document), so document identity is available **after** enrichment.
- The recall harness (`tests/test_search_recall.py`) measures keyword-leg MRR (`>= 0.80`) and
  `misses = 0` on a pinned fixture, in CI.

## 4. Design

### 4.1 `ts_rank_cd` (lexical proximity)

`_bm25_search` scores with `ts_rank_cd(c.tsvector_ko, to_tsquery('simple', $1))` instead of
`ts_rank`. Same `WHERE` (same rows *match*); the `ORDER BY` score changes — cover-density rewards
matched terms that are close together in the **tsvector position stream** (which is the mecab
POS-filtered token stream, josa/어미 removed — so "proximity" is over tokens, not raw characters,
I-006). Whether this raises MRR is an **empirical** question the recall harness answers; the SPEC
does not assert an improvement, only that the harness must not regress (§1). Under the `LIMIT`, the
top-20 reaching fusion can shift for high-match queries (§1) — again, harness-gated.

### 4.2 Per-document diversity (no single-doc flooding)

The candidate cut moves to **after** enrichment so diversity can key on the document:

- `_rrf_fusion` returns the **full deduped fused list** in RRF-score order (no `final_top_k` cut).
  Its length is naturally bounded by the deduped union of the two legs — at most `2 × bridge_top_k`
  (≈ 40) candidates (I-003 — one bound, not two).
- `_enrich_hits` enriches that list (small, ≤ ~40). Enrichment may itself drop a hit whose metadata
  is missing, so the counts below are relative to the **enriched** hits, not the raw fused list
  (I-005).
- A new pure `_diversify(hits, top_k, per_doc_cap)` produces the final top-k: walk the RRF-ordered
  enriched hits and take each whose owning document has not yet hit `per_doc_cap`; if fewer than
  `top_k` are selected because too few documents qualified, **fill** the remainder from the skipped
  hits in RRF-score order. It returns exactly `min(top_k, len(enriched_hits))` hits — never fewer, so
  it cannot empty a non-empty result. Default `per_doc_cap` from `config.yaml` (e.g. 3), tunable.

**The output order is the diversified ranking, not pure `SearchHit.score` order (I-004).** A
filled-in hit can have a higher RRF score than an earlier interleaved one; that is intentional
(diversity ≠ score sort). Each hit's `score` field stays correct; consumers must treat the **list
order** as the ranking and not re-sort by `score`. `evidence_packet` already consumes hits in list
order, so this holds end-to-end. When only one document qualifies, the fill path returns the same
hits in the same RRF order — old behaviour, gracefully.

## 5. Error handling / invariants

- Diversity is **order-only**: it never returns a chunk that was not in the enriched fused list, and
  returns exactly `min(top_k, len(enriched_hits))` results — so it cannot worsen recall or empty a
  non-empty result. Pinned by a test.
- `ts_rank_cd` on an empty tsquery is never reached (`_bm25_search` returns early on empty tsquery,
  unchanged).
- Single matched document → diversity returns the same hits in the same order (cap not binding via
  the fill path).

## 6. Testing

- **`_diversify` (pure):** given hits from 1 document, output == input order (no starvation). Given
  hits from many documents where one document dominates the RRF order, the output interleaves so no
  document exceeds `per_doc_cap` while any others remain, and the count is `min(top_k, pool)`. Given
  fewer distinct docs than needed to fill `top_k`, the fill path restores count (no under-fill).
- **Ordering within a document** is preserved (a document's kept chunks stay in RRF order).
- **Output count** equals `min(top_k, len(enriched_hits))` on every branch (cap-binding, fill,
  single-doc).
- **`ts_rank_cd` behaviour (primary, I-009):** a DB-backed test on a fixture where match count ≤ the
  BM25 `LIMIT` (so the set is stable) asserts a query in which proximity matters ranks the proximate
  chunk **above** a distant same-term chunk — the precision the change buys — and, because the fixture
  stays under the `LIMIT`, the matched **set** is identical to `ts_rank` there (a scoped recall check,
  not a general claim). The behavioural ordering is the assertion; any implementation-string check is
  a secondary guard only.
- **Recall harness is the recall gate:** `tests/test_search_recall.py` must still pass (`misses = 0`,
  MRR ≥ 0.80) with `ts_rank_cd` and the diversity step. This is where the LIMIT-shift risk (§1) is
  actually caught — a failing harness blocks the change.

## 7. Acceptance

The BM25 leg ranks by cover density (proximity-aware), and the final top-k caps how many chunks any
one document contributes, so a query no longer returns a page dominated by a single document when
other relevant documents exist. Both changes reorder within the already-retrieved candidate set;
the recall harness (`misses = 0`, MRR ≥ 0.80) is unchanged or improved. The min-token-length filter
and a learned reranker remain named follow-ups.
