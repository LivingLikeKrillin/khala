---
id: SPEC-nexus-korean-embedding-comparison
type: spec
title: Korean embedding comparison — nomic-embed-text vs KURE-v1 on the pinned pack
status: approved
date: '2026-08-03T12:27:40Z'
linked_adrs:
- ADR-0008
tags:
- nexus
- search
- korean
- embedding
- measurement
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-03T12:44:25Z'
content_hash: sha256:995b3d8b1d3e2a00e49b7c65b78139a6747a20abe0614e90664d7adc4694026d
---

## 1. Goal

Nexus ships a **Korean-first** retrieval system whose vector leg runs on `nomic-embed-text` — an
English-centric v1 model — while `nexus/CLAUDE.md` rule 9 states *"영어 전용 embedding model 사용
금지 → multilingual 필수"*. The rule and the config (`config.yaml embedding.model`) have disagreed
for as long as both existed, and nothing could settle it because there was no way to measure Korean
retrieval.

There is now (`SPEC-nexus-korean-retrieval-eval`). This SPEC uses it to **measure the vector leg**,
which the tokenizer comparison could not touch: the tokenizer never reaches the embedding, and that
result (mecab-ko retained, p=0.180) says nothing about the model that produces the vectors.

Measure `nomic-embed-text` against **KURE-v1** (`nlpai-lab/KURE-v1`, MIT, sentence-transformers,
XLM-RoBERTa/BGE-M3 lineage, hidden size 1024, `max_seq_length` 8192 — all read from the checkpoint,
2026-08-03) on the same 265-document pack and the same labelled queries, under the verdict rule
already fixed in that SPEC's §4.3.

### 1.1 Gate record (I-005)

ADR-0002's demand-pull discipline, as ADR-0008 §3 item 3 restates it, requires the gate to be
*declared fired by the director* and recorded in the direction's SPEC rather than argued into
existence by it:

> **Gate: fired. Declared by LivingLikeKrillin (director) on 2026-08-03**, instructing that the
> embedding measurement be the next unit of work after the Korean evaluation set landed.

§1's rule-versus-config contradiction is *what* to measure. It is not the authority to measure it,
and no ADR-0006 override is claimed.

## 2. Non-goals

- **Swapping the production model.** This measures. A swap means a dimension change (768 → 1024), a
  full re-embed and a migration; it gets its own SPEC and inherits these numbers as evidence. If the
  measurement does not favour KURE-v1, that SPEC is never written — the point of measuring first.
- **Editing the rule or the config to resolve their contradiction.** §1 records it; evidence decides
  which side moves.
- **Changing the production embedding path at all** (I-013). Per-model instruction formats live in
  the *harness*, not in `nexus/providers/embedding.py`. `config.yaml` already carries
  `embedding.document_prefix` / `query_prefix` keys that the service does not read; that dead pair is
  **recorded here and left alone**, because reconciling it is a production change with its own
  review.
- **Reranking, query rewriting, chunk-size tuning.** One variable at a time.
- **Making production's ANN exact.** §4.2 says why the *evaluation* is exact and what that costs.
- **Any multilingual claim beyond Korean.** One corpus, one language, one verdict.

## 3. What exists, and what blocks a naive run

| fact | consequence |
|---|---|
| `chunks.embedding` is `vector(768)` | a 1024-dimension model **cannot be stored** there. §4.1 |
| `idx_chunk_vector` is `ivfflat` | approximate, not reload-stable (`SPEC-nexus-deterministic-retrieval-order` §4.3). §4.2 |
| `EmbeddingService` hardcodes `search_document: ` / `search_query: ` | nomic's instruction format. Applying it to KURE would measure our misuse of KURE. §4.3 |
| `EmbeddingService` speaks only to Ollama | KURE-v1 is a sentence-transformers checkpoint. §4.4 |
| **the eval harness has no vector leg and no fusion** — `ko_eval_harness.py` implements `run_keyword_leg` only, and `load_pack` indexes BM25 alone | the work §7 demands does not exist yet; §8 builds it (I-003) |
| labels are at revision 2, pooled over mecab-ko and nori | a model absent from the pool is penalised by construction. §4.5 |
| **the committed mecab-vs-nori report was computed on revision 2** | re-pooling invalidates it. §4.6 (I-001) |
| production embeds `get_search_text(chunk)` — section-path prefix + chunk text — not `chunk_text` | both arms must embed **that** string, byte-identical. §4.3 (I-011) |

The tokenizer comparison had two confounds and removed both. This one has more, and each is removed
or measured rather than noted in passing.

## 4. Design

### 4.1 Where the vectors live, and what stops a stale arm

```sql
CREATE TABLE IF NOT EXISTS ko_eval_embeddings (
    model          TEXT NOT NULL,
    tenant         TEXT NOT NULL,
    pack           TEXT NOT NULL,
    chunk_rid      TEXT NOT NULL,
    input_sha256   TEXT NOT NULL,      -- hash of the exact string embedded
    embedding      vector NOT NULL,    -- unconstrained dimension: 768 and 1024 coexist
    PRIMARY KEY (model, tenant, chunk_rid)
);
```

pgvector accepts a dimensionless `vector` column; it cannot be indexed, which §4.2 turns into the
design. Production's `chunks.embedding` is **never written** by this work.

**Staleness guards** (I-008). `chunk_rid` is derived from a tenant-qualified uri and the harness
deletes and reloads chunks between runs, so rows can outlive the chunks they describe. Before
scoring, an arm must satisfy all of:

- every `chunk_rid` in the arm exists in `chunks` for that tenant (join, not count);
- the arm's row count equals the **pack's current chunk count, derived at run time** — no literal
  (I-014);
- every row's `input_sha256` matches the string the harness would embed now.

Any mismatch aborts. Rows for a `(model, tenant)` are replaced wholesale, never merged.

### 4.2 The evaluation's vector leg is exact, deliberately

```sql
SELECT chunk_rid FROM ko_eval_embeddings
WHERE model = $1 AND tenant = $2
ORDER BY embedding <=> $3::vector, chunk_rid
LIMIT $4
```

Scanning ~1.9k chunks exactly is trivial, and it buys two things: the ANN candidate-set instability
left open by the determinism SPEC cannot contaminate the comparison, and `chunk_rid` as the final
key makes ties total, as in the keyword leg.

**The fidelity cost, stated rather than buried.** Production's vector leg is ivfflat and will recall
*less* than this for both models. This isolates **the model**, holding the search exact; it does not
predict production's absolute numbers, and a model that wins here could in principle lose under ANN
if its vectors distribute worse across lists. That residual is named in the report.

### 4.3 Identical input text, per-model instruction format, and no silent truncation

**Same string on both arms** (I-011). Each arm embeds `get_search_text(chunk)` — the composition
production uses — and the harness stores `input_sha256` per row. A test asserts the two arms'
`input_sha256` sets are **identical**. A model comparison whose arms saw different text is not a
model comparison.

**Per-model instruction format** (I-009). `nomic-embed-text` documents `search_document: ` /
`search_query: ` prefixes. KURE-v1's card documents **no** instruction prefix (2026-08-03: its
README shows plain `SentenceTransformer.encode`; the "instruct" strings in its tables are other
models being benchmarked), so its arm embeds raw text. This is a *choice made from documentation,
not from measurement*: the report prints each arm's exact prefix pair, and if KURE's card later
specifies an instruction, this run is superseded rather than reinterpreted.

**Truncation is measured, not assumed** (I-002). KURE-v1's `max_seq_length` is 8192, but the
**nomic arm is the exposed one**: Ollama applies its own context default, which is smaller than the
model's, and chunks target 1100 Korean tokens. So the harness:

- records, per arm, the token count of every input as the arm's own tokenizer sees it;
- sets the nomic arm's context explicitly to the model's full window rather than inheriting a
  default;
- **aborts if any input would be truncated in either arm**, and prints the maximum observed input
  length per arm in the report.

Comparing a truncated arm to a whole one measures window size, which is the embedding-shaped repeat
of the POS-filter confound.

### 4.4 Serving KURE-v1

A harness-only provider with the same surface as `EmbeddingService` (`embed_documents`,
`embed_query`), backed by `sentence-transformers` in an evaluation container. It is not wired into
`nexus/providers/`, does not ship in the app image, and is not importable from production code — the
rule `NoriTokenizer` already follows.

Recorded in the report: HF revision (commit sha), `sentence-transformers` and `torch` versions,
device, `normalize_embeddings`, `max_seq_length`, and the observed output dimension. Expected
dimensions live in the harness's **model registry**, not as literals in prose (I-014); a mismatch
between registry and observed dimension aborts.

### 4.5 Re-pooling over every leg, judged blind

Revision-2 gold was pooled over the two tokenizer arms. So:

1. Pool the **top-10 of every leg of every configuration** — keyword (mecab), vector (nomic),
   vector (KURE), **and both fused legs** (I-007). Fused is a leg: RRF can lift a document ranked
   11–20 in each leg into the fused top-10, where an unjudged document is silently counted
   non-relevant.
2. **Judge blind** (I-012). The adjudication dump lists candidates with arm membership **stripped
   and order shuffled**, because the documents being judged are exactly the ones that distinguish
   the arms, and the judge holds a hypothesis about which model should win. Arm membership is
   re-attached only after judgements are written.
3. Stamp **label revision 3**; the existing test forces the keyword floors to be re-recorded in the
   same commit.

### 4.6 Revision 3 invalidates the tokenizer verdict, so it is re-run (I-001)

The committed mecab-vs-nori report (7-2-31, p=0.180) was computed on revision 2. Adding gold
documents changes per-query recall and can flip discordant pairs, so after this lands that report
would describe a gold set that no longer exists — while being the sole evidence for mecab-ko
retention and for anything ADR-0008 §5(b) is asked about.

Therefore: **the tokenizer comparison is re-run on revision 3 in the same change**, and its report
is re-issued citing the new revision. Every committed report states the label revision it was
computed on, and a test asserts that the newest report for each comparison cites the current
revision — reports and labels cannot drift apart silently.

### 4.7 The verdict

Inherited unchanged from `SPEC-nexus-korean-retrieval-eval` §4.3: Recall@10 per query, MRR@10
breaking recall ties, two-sided exact sign test at α = 0.05, and the ≥ 6 discordant-pair power
precondition that reports **"underpowered"** rather than "no difference".

- **Decisive leg: vector.** That is the leg the model changes.
- **Fused is reported, and disagreement has a pre-declared reading** (I-010). If the vector leg
  reaches p < 0.05 for KURE while fused does not, the recorded conclusion is **"favours KURE-v1 on
  the leg it changes; not yet demonstrated at the surface the user sees"** — and the swap SPEC
  inheriting it must carry both sentences, not the first alone. The reverse (fused significant,
  vector not) is recorded as **not a model result** and triggers a look at fusion, not a swap.
- **The power precondition is re-derived, not assumed portable.** Six discordant pairs is the
  arithmetic minimum for a two-sided exact binomial at α = 0.05 regardless of leg, but the *tie
  rate* differs between legs, so the report prints the discordant count for the vector leg before
  any p-value, as the keyword report does.
- **Incumbency**: inconclusive or underpowered leaves `nomic-embed-text`. A dimension change and a
  full re-embed are not paid for by a difference that was not measured.
- **Pack A is not khala's corpus** (I-006). Every statement of which model the evidence favours
  carries that sentence, exactly as the tokenizer report does. A verdict on public Korean
  documentation is not a verdict on internal Notion content.

## 5. Error handling

- KURE-v1 checkpoint unavailable, or its observed dimension disagreeing with the registry → abort.
- Any chunk failing to embed, any input that would truncate, any `input_sha256` mismatch, any
  `chunk_rid` without a live chunk, or a row count differing from the run-time pack chunk count →
  abort. A partially embedded arm is never scored.
- Rows for a `(model, tenant)` are replaced wholesale — the mixed-generation accident
  `index/embed_health.py` exists to detect is avoided by construction here.

## 6. Testing

Unit, no DB:

- Per-model instruction format: the nomic entry yields today's two strings; a model with none
  yields raw text; the report renderer prints both arms' prefixes.
- The exact-scan SQL orders by distance then `chunk_rid` (structural, as in the determinism suite).
- Registry/dimension mismatch raises rather than truncating or padding.
- The truncation guard fires on an input longer than an arm's window.
- Report-revision test: the newest report for a comparison cites the current label revision.

Against Postgres:

- **The vector leg has teeth** (I-004). The trivial "same model twice agrees" check proves only
  determinism, so the real control is degradation: an arm whose vectors are **shuffled between
  chunks** must collapse — Recall@10 below half the intact arm's. If a shuffled arm still scores,
  the vector harness is measuring nothing, and the suite says so in those words.
- Reload stability: three reloads, identical vector-leg orders.
- Both arms' `input_sha256` sets are identical.
- Writing eval embeddings never touches `chunks.embedding`.

Exploratory (documented, not in CI):

- The comparison, with a committed dated report carrying both arms' checkpoint provenance, prefix
  pairs, max input lengths, pool membership, unjudged count, discordant counts and p-values for the
  vector and fused legs — plus the re-issued tokenizer report on revision 3.

## 7. Acceptance

- `ko_eval_embeddings` holds a complete, non-stale arm per model — every guard in §4.1 passing —
  with `chunks.embedding` untouched.
- The evaluation's vector leg is exact and reload-stable, and its negative control (shuffled
  vectors) breaks it.
- Both arms embedded byte-identical inputs, each under its own documented instruction format, with
  **zero truncated inputs** in either arm.
- Labels reach revision 3 through blind re-pooling over every leg, the keyword floors are
  re-recorded, and **the tokenizer comparison is re-run and its report re-issued on revision 3**.
- A committed report applies the inherited verdict rule to the vector leg, reports fused alongside
  with the §4.7 reading for disagreement, and states which model the evidence favours — or that it
  favours neither — always with the sentence that Pack A is not khala's own corpus.
- Production is unchanged: no model change, no `chunks` schema change, no edit to
  `nexus/providers/embedding.py`, no new production dependency.

## 8. Units

1. **Eval vector leg** — `ko_eval_embeddings` + staleness guards, exact-scan retrieval, the shuffled
   negative control, reload-stability tests.
2. **Fused leg in the harness** — reuse production `_rrf_fusion` over the eval legs (not a
   reimplementation), so fused numbers mean what they mean in production.
3. **Embedding arms** — nomic via Ollama with an explicit full context window; KURE-v1 via a
   harness-only sentence-transformers provider; per-model instruction registry; truncation and
   input-hash guards.
4. **Re-pool, run, verdict** — blind pooling over all legs to revision 3, keyword floors
   re-recorded, tokenizer report re-issued, embedding comparison report committed.
