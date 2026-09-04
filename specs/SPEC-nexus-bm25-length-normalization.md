---
id: SPEC-nexus-bm25-length-normalization
type: spec
title: Length normalisation for the keyword leg — an amendment to the cover-density
  choice
status: approved
date: '2026-09-03T18:40:00Z'
linked_adrs:
- ADR-0004
- ADR-0006
tags:
- nexus
- search
- ranking
- amendment
approved_by: LivingLikeKrillin
reviewed_at: '2026-09-03T18:40:00Z'
content_hash: sha256:93e29069dde3c7fe87a64bdc56e03ad4c893ae800aca07b0aa7a486136eea8ae
---

## 0. Why this is a separate document

`SPEC-nexus-ranking-precision` is **approved and stamped**. Its §4.1 deliberately chose
`ts_rank_cd` *without* a normalisation flag, and its body hash is checked on every push
(`scripts/ledger_integrity.py`). Editing that body to record a later decision would break the
stamp and forge the record of what was approved in July.

So this is an amendment, filed as its own artifact. It changes one argument of one call and
nothing else in that SPEC.

## 1. Goal

The keyword leg must not drop a short, exactly-matching chunk out of `bm25_top_k` merely because
longer chunks accumulate more matches.

## 2. What was wrong

`_bm25_search` scored with `ts_rank_cd(vector, query)` — normalisation `0`. Cover density grows
with match count, and nothing divided it by length. Measured on live `default`, 2026-08-26, for
one query with 140 matches:

    1st    프로필/아바타 정책     score 4.700   (1228 chars)
    48th   디제잉 아바타 10       score 0.400   (  19 chars)   ← the row that answers the question

The row was **matched and outranked**, not missed. Being outside the leg's `LIMIT` meant it never
entered RRF from that side, so fusion — which rewards documents both legs agree on — dropped it,
and the answer path never saw it.

## 3. Decision

`_bm25_search` passes `BM25_LENGTH_NORMALIZATION = 1` (`score / (1 + log(document length))`).

Five candidates were compared on the **product path** (`hybrid_search` Recall@10), not on the leg
alone — measuring a leg while shipping a fusion is how an earlier gain failed to reach an answer.
Rules were fixed before the run: `tests/eval/bm25-normalization/README.md`.

| flag | all | fragment | control | rule 2 |
|---|---:|---:|---:|---|
| 0 (previous) | 0.758 | 0.111 | 1.000 | — |
| **1** | 0.848 | **0.444** | 1.000 | **met** |
| 2 | 0.879 | 0.778 | **0.917** | rejected — control recall drops |
| 16 | 0.848 | 0.444 | 1.000 | met |
| 32 | 0.758 | 0.111 | 1.000 | monotone; no reordering |

## 4. What this decision does not claim

- **No significance.** 5 wins, 0 losses, 28 ties. The direction never reverses, but five
  discordant pairs is one short of the pre-registered threshold of six, so the sign test says
  underpowered. The adoption bar was rule 2 (fragment up, control not down), and that is what was
  met.
- **One corpus.** Live `default`, 466 chunks, 33 questions. The flag affects every query in every
  tenant.
- **`1` over `16` was a tie-break, not a finding.** The two were identical on every metric here.
- **`2` is better for the targeted case and was still rejected**, because it costs control recall
  (1.000 → 0.917). Full length normalisation presses genuine long policy documents down.
- **It does not close the gap.** Fragment recall is 0.444 on the product path while the vector leg
  alone reaches 0.889. Fusion, diversity and the top-k cut still drop about half the gain; that
  remains open.

## 5. Invariants

- The `WHERE` clause is untouched: the same rows *match*, only `ORDER BY` changes. §4.1's own
  framing of the earlier `ts_rank → ts_rank_cd` swap applies unchanged.
- Ties still break on `c.rid` (`SPEC-nexus-deterministic-retrieval-order`), so the total order
  stays reproducible.
- Reverting is setting the constant to `0`. No stored data derives from it.

## 6. Testing

- The constant is declared **and reaches the query** — a constant nothing passes is worth zero,
  which this repo has shipped before.
- Behavioural: the short/long score **ratio** must increase when normalisation is on. The test
  deliberately does *not* assert "the short row wins", because `1` is a gentle damping and a
  fixture repeating a term forty times still beats it — an assertion tuned until it passes would
  be guarding the fixture, not the code.

## 7. Acceptance

`tests/test_bm25_length_normalization.py` green, full suite green, and the measurement in
`tests/eval/bm25-normalization/README.md` reproducible from the committed probe.
