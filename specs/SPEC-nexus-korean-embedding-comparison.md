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
reviewed_at: '2026-08-04T00:36:18Z'
content_hash: sha256:e5392d6672b7b478567fc8724d3f9a20a4c60c2d144d2edd19d35ced36f1d1f6
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

### 1.1 Gate and backstop record

**This is not the direction's first SPEC** — `SPEC-nexus-korean-retrieval-eval` is, and it carries
the gate record ADR-0002's procedure requires (I-006). What this SPEC records is the director's
instruction that the embedding measurement follow it:

> **Instructed by LivingLikeKrillin (director) on 2026-08-03**, after the evaluation set landed.

If a reader judges an embedding comparison to be a *separate* direction rather than a
continuation — ADR-0008 §6 does list mecab-ko retention and an embedding-model change as two
blocked decisions — then that instruction is the declaration for it, made by the same director
the procedure names. **No ADR-0006 override is claimed here in either reading**; ADR-0008 §3
says stretching it to a retrieval-quality instrument is the director's call, and this SPEC does
not make that call for them.

**ADR-0008 §5's backstop names "a tokenizer or embedding-model change" as an event at which the ADR
is re-read.** Re-read 2026-08-04. Outcome: the deferral stands — this SPEC proposes no model change
and no substrate change, and its result is what a future swap SPEC would have to justify itself
against. §4.6 states what it does *not* do for condition (b).

## 2. Non-goals

- **Swapping the production model.** This measures. A swap means a dimension change (768 → 1024), a
  full re-embed and a migration; it gets its own SPEC and inherits these numbers. If the measurement
  does not favour KURE-v1, that SPEC is never written.
- **Editing the rule or the config to resolve their contradiction.** §1 records it; evidence decides
  which side moves.
- **Changing the production embedding path.** Per-model instruction formats live in the *harness*.
  `config.yaml` carries `embedding.document_prefix` / `query_prefix` keys the service does not read;
  that dead pair is recorded here and left alone.
- **Fixing the coverage defect §4.3 surfaces.** It is recorded with an owner and a checkable
  trigger, not repaired here.
- **Reranking, query rewriting, chunk-size tuning.** One variable at a time — with the exception
  §4.5 names and orders explicitly.
- **Making production's ANN exact.** §4.2.
- **Any multilingual claim beyond Korean, or any claim beyond Pack A.**

## 3. What exists, and what blocks a naive run

| fact | consequence |
|---|---|
| `chunks.embedding` is `vector(768)` | a 1024-dimension model cannot be stored there. §4.1 |
| `idx_chunk_vector` is `ivfflat` | approximate, not reload-stable. §4.2 |
| `EmbeddingService` hardcodes nomic's prefixes and speaks only to Ollama | per-model formats and a second backend live in the harness. §4.3, §4.4 |
| the eval harness had no vector leg and no fusion | built as Units 1–2 (landed 2026-08-03) |
| labels are at revision 2, pooled over mecab-ko and nori | any arm absent from the pool is penalised by construction. §4.5 |
| the committed mecab-vs-nori report was computed on revision 2 | re-pooling invalidates it. §4.5 |
| production embeds `get_search_text(chunk)`, not `chunk_text` | both arms embed that string. §4.3 |
| **Ollama's nomic-embed-text refuses inputs past its 2,048-token window** | 10 of this pack's 1,906 chunks cannot be embedded by that arm. §4.3 |

## 4. Design

### 4.1 The eval embedding store

```sql
CREATE TABLE IF NOT EXISTS ko_eval_embeddings (
    model          TEXT NOT NULL,
    tenant         TEXT NOT NULL,
    pack           TEXT NOT NULL,
    chunk_rid      TEXT NOT NULL,
    status         TEXT NOT NULL,        -- 'embedded' | 'refused'
    refusal_reason TEXT,                 -- the backend's own message, verbatim
    input_sha256   TEXT NOT NULL,        -- hash of get_search_text(chunk): the SHARED input
    payload_sha256 TEXT NOT NULL,        -- hash of what this arm actually sent (prefix applied)
    embedding      vector,               -- NULL exactly when status='refused'
    PRIMARY KEY (model, tenant, pack, chunk_rid)
);
```

Three corrections the first draft needed (I-002, I-003, I-007):

- **Two hashes, not one.** `input_sha256` covers the pre-prefix string, so the arms' sets *can* be
  identical and the "same input" guard is meaningful. `payload_sha256` covers the prefixed string
  each arm sent, which is per-arm by design and is what the staleness guard compares against a
  re-derivation. The earlier single hash made the acceptance criterion unsatisfiable.
- **A refused chunk is a row.** Otherwise refusal accounting has nowhere to live, and
  `embedded + refused = pack chunk count` cannot be checked. `embedding` is nullable and NULL
  exactly when `status='refused'`.
- **`pack` is in the key and in every predicate.** Otherwise two packs under one tenant collide on
  shared chunk_rids or get scanned together, silently mixing corpora.

**Staleness guards.** Before scoring, an arm must satisfy: every `chunk_rid` joins to a live chunk
in that tenant; `embedded + refused` equals the pack's chunk count derived at run time (no literal);
every `input_sha256` and `payload_sha256` matches what the harness would produce now. Any mismatch
aborts. Rows for `(model, tenant, pack)` are replaced wholesale.

### 4.2 The evaluation's vector leg is exact, deliberately

```sql
SELECT chunk_rid FROM ko_eval_embeddings
WHERE model = $1 AND tenant = $2 AND pack = $3 AND status = 'embedded'
ORDER BY embedding <=> $4::vector, chunk_rid
LIMIT $5
```

Scanning ~1.9k chunks exactly is trivial, and it removes the ANN candidate-set instability the
determinism SPEC left open; `chunk_rid` makes ties total.

**Fidelity cost, stated:** production's leg is ivfflat and will recall *less* than this for both
models. This isolates the model, holding the search exact; it does not predict production's absolute
numbers, and a model could in principle win here and lose under ANN.

### 4.3 Input identity, instruction formats, refusal, and coverage

**Same input on both arms.** Each arm embeds `get_search_text(chunk)`, built in one place;
`input_sha256` is compared across arms and must be identical. **The same rule applies to queries**
(I-013): the pre-prefix query text is recorded per arm and must match, because a harness bug sending
the arms different queries is exactly what the document-side guard exists to prevent.

**Per-model instruction format.** nomic documents `search_document: ` / `search_query: `; KURE-v1's
card documents none (2026-08-03), so its arm sends raw text. A documentation-derived choice, printed
per arm in the report. **Supersession is observable because the card lives in the pinned
repository revision** (§4.4): a card that later specifies an instruction is a different sha, and
a run at a different sha is a different configuration by the same rule that governs the weights.

**Truncation detection is per backend, and named** (I-008):

- *sentence-transformers truncates silently at `max_seq_length`.* So the KURE arm tokenises every
  payload with the model's own tokenizer and compares against `max_seq_length` **before** encoding;
  over-length input aborts. This is the guard, not an inference.
- *Ollama refuses rather than truncating*, with HTTP 500 and
  `{"error":"the input length exceeds the context length"}`. Observed 2026-08-03/04 at the boundary
  and on 10 real chunks. The harness records each refusal verbatim; it does not infer per-row
  safety from a boundary probe.

**The boundary, and a correction kept visible** (I-016). A binary search with a `"가" * n` probe
refuses past **≈ 2,042 characters**, and `PARAMETER num_ctx 8192` on a derived model does not
raise the window. An earlier draft turned that bound into a population estimate — **232 chunks,
12.2 %** — by counting chunks longer than it. **Running the arm gave 10 chunks, 0.5 %**: pure
Hangul costs ~1 token per character, while real Korean technical prose (Latin identifiers,
spaces, markdown) costs far less, so the shortest chunk actually refused is 3,324 characters.
The estimate was wrong by a factor of twenty, and I-016 had already said the token reading was an
inference whose rate is an artifact of the probe. **Population figures come from running the arm;
a boundary measurement speaks only about the boundary.**

**Coverage, printed above the verdict.** Per arm, `embedded / total`: on this pack, nomic
**1,896 / 1,906 (99.5 %)** and KURE-v1 **1,906 / 1,906**. The gap is small here, which is itself a
reason to print it rather than assume it: coverage is a property of the corpus's length
distribution, and a corpus with longer documents would move it.

**Refused chunks are scored as absent, not aborted**, because that is what production does:
`providers/embedding.py` retries three times and raises, `index/embed.py` catches and returns
`False`, and the chunk keeps `embedding = NULL`, invisible to the vector leg until re-embedded.

**The production finding, scoped to its evidence** (I-010): *on a corpus of Pack A's shape*, 0.5 %
of chunks are not vector-searchable, and nothing surfaces it — `index/embed_health.py` reports
generation mixing but not the share of active chunks with a NULL embedding. Korean Notion content
has a different length distribution, so this figure does not transfer; what transfers is that the
failure is **silent**. Owner **LivingLikeKrillin**; trigger: **the first change to chunking, to the production
embedding model, or to `embed_health.py` after this SPEC lands** (I-009). Deliberately *not*
this SPEC's own Unit 5 — a trigger that fires inside the change that records it would either
contradict §2 or mean nothing. Each named event leaves a commit, so the trigger is checkable
from the log rather than from memory.

### 4.4 Serving KURE-v1

A harness-only provider with `EmbeddingService`'s surface, backed by `sentence-transformers` in an
evaluation image; not wired into `nexus/providers/`, not in the app image, not importable from
production.

**The checkpoint is pinned by revision before the run** (I-015) — resolving `nlpai-lab/KURE-v1` to
whatever `main` points at would let a re-trained checkpoint of the same 1024 dimensions change the
arm silently between runs. The report records revision sha, library and torch versions, device,
`normalize_embeddings`, `max_seq_length`, and observed dimension; the registry aborts on a dimension
mismatch.

### 4.5 Re-pooling comes first, as its own landing

**Order matters, and §2's one-variable rule is preserved by sequencing** (I-017). The re-pool and
the tokenizer re-issue land **before** the embedding arms are scored:

1. **Pool over every leg of every configuration**: keyword/mecab, **keyword/nori** (I-001 — omitting
   it would enrich the gold set with documents the other arms found and then re-run the tokenizer
   comparison against it, biasing exactly the verdict §4.6 exists to keep valid), vector/nomic,
   vector/KURE, and both fused legs. Depth 10, the metric depth.
2. **The judging procedure, stated** (I-008). The judge is the director or an agent under the
   recorded review the labels already require (`authored_by` / `reviewed_by`). The criterion is
   the one the labels were built on: *would reading this document answer the query*. **Only
   newly-pooled documents are judged**; revision-2 judgements stand. That does make revision 3 a
   mixture of two rounds, which is disclosed here rather than smoothed over — both rounds used
   the same criterion, and the second is the stricter of the two because it is blind.
3. **Judge blind, with an artifact** (I-014): the dump is stripped of arm membership and shuffled by
   a **recorded seed**; the anonymised dump is committed *before* judgements are attached, so a
   reviewer can check that the judgements were written against it.
4. Stamp **label revision 3**; keyword floors re-recorded in the same commit (the existing test
   enforces the citation).

**What revision 3 is valid for, recorded beside the labels** (I-007). A pooled gold set is only
unbiased for the configurations in its pool. Revision 3 covers exactly the six legs above; a
seventh configuration — a third model, a reranker, a chunking change — is penalised against it
until it re-pools. The label file carries that list in a `pooled_over` field so a later author
cannot inherit the numbers without inheriting the condition, and §2's phrase about a swap SPEC
inheriting these numbers means exactly this, no more.

### 4.6 What the re-issued tokenizer report does and does not mean

The committed mecab-vs-nori report was computed on revision 2; revision 3 changes per-query recall,
so it is re-run and re-issued citing the new revision, and a test asserts each comparison's newest
report cites the current revision.

Two limits, stated (I-005, I-011):

- **It does not move ADR-0008 §5(b).** (b) requires khala's real corpus; Pack A is public
  documentation. (b) is unmet before this work and unmet after it.
- **If it reverses, that is a finding, not a decision.** Should the revision-3 re-run favour nori,
  the recorded outcome is that the tokenizer question is *reopened on Pack A* — the retention
  decision, the keyword floors and any citation of it are then re-derived under
  `SPEC-nexus-korean-retrieval-eval`, which owns them. This SPEC does not silently overturn a
  merged decision, and it does not preserve one either.
- **It is not an independent confirmation.** It re-tests a hypothesis already tested (p = 0.180) on
  a label set enlarged partly by documents the embedding arms surfaced. Its p-value is reported as
  **descriptive**, and the report says so in the same sentence as the number.

### 4.7 The verdict, and how coverage is kept out of it

The rule is inherited: Recall@10 per query, MRR@10 breaking recall ties, two-sided exact sign test at
α = 0.05, and the ≥ 6 discordant-pair power precondition reporting "underpowered" rather than
"no difference".

**The confounder this run has, and the analysis that removes it** (I-004). nomic is structurally
absent from part of the corpus — 0.5 % of chunks as measured, but the share is a corpus property,
not a constant — so a KURE win over all queries could be measuring context-window size rather
than embedding quality — the very failure the truncation rule exists to prevent. So two
analyses are computed and reported side by side:

- **Confirmatory — the comparable subset.** Queries whose gold documents' chunks are *all* within
  nomic's window, so both arms could return every gold document. The sign test on this subset is the
  **model** claim, and it is the only test in this change whose α is spent on a confirmatory
  question. The report prints the subset size; if it falls below the six-discordant-pair
  precondition, the answer is "underpowered", not a borrowed verdict from the full set.
- **Descriptive — all answerable queries.** What a user gets today, coverage gap included. Reported
  with coverage beside it and never quoted alone as a model result.

**Multiplicity** (I-011): one confirmatory test (vector leg, comparable subset). The fused leg, the
all-query vector analysis and the re-issued tokenizer comparison are descriptive; no correction is
applied because no error rate is claimed for them, and the report labels each.

- **Decisive leg: vector** — the leg the model changes. **Fused** is reported as the user-facing
  consequence; if vector reaches significance and fused does not, the recorded conclusion carries
  both sentences ("favours KURE on the leg it changes; not demonstrated at the surface the user
  sees"). Fused significant while vector is not is recorded as *not a model result*.
- **Incumbency**: inconclusive or underpowered leaves `nomic-embed-text`.
- **Pack A is not khala's corpus**, on every statement of what the evidence favours.

## 5. Error handling

- KURE checkpoint unavailable, unpinned, or its observed dimension disagreeing with the registry →
  abort.
- **Silent truncation** (KURE arm, detected by tokenising before encoding), `input_sha256` or
  `payload_sha256` mismatch, a `chunk_rid` with no live chunk → abort. The arm is describing
  something other than the corpus.
- **Explicit refusal → recorded as a `status='refused'` row** with the backend's message, counted in
  coverage, scored as absent.
- Row-count guard: `embedded + refused == pack chunk count`. A chunk that is neither still aborts —
  an unexplained gap is not coverage.

## 6. Testing

Unit, no DB:

- Per-model instruction registry: nomic yields today's two strings, KURE yields raw text; the report
  prints both.
- `input_sha256` ignores the prefix; `payload_sha256` does not — asserted on the same chunk for both
  arms.
- The exact-scan SQL filters on `(model, tenant, pack, status='embedded')` and orders by distance
  then `chunk_rid`.
- Registry/dimension mismatch raises rather than padding.
- The KURE truncation guard fires on a payload longer than `max_seq_length`, using the model's own
  tokenizer count as its source.
- Comparable-subset selection: given a chunk-length map and gold sets, the subset contains exactly
  the queries whose gold chunks all fit the narrower arm's window.
- Report-revision test: each of the two existing comparisons' newest report cites the current
  label revision (I-011 — scoped to the comparisons that exist, not a standing invariant for all
  future ones).
- **Harness-only isolation** (I-010): no module under `nexus/nexus/` imports
  `sentence_transformers`, `torch`, or the harness arm modules, and neither appears in the app
  image's dependency set. Asserted, because §4.4 and §7 both promise it and nothing else checks.

Against Postgres (fixture vectors — **no model server required**, so this runs wherever the DB does):

- **The vector leg has teeth**: an arm whose vectors are shuffled between chunks (fixed seed,
  recorded) must collapse — intact Recall@10 = 1.0 on the fixture by construction, shuffled below
  0.5 (I-009). The fixture is deliberately larger than the metric window, because a corpus smaller
  than the window makes a miss impossible — the defect this whole line of work exists to remove.
- Reload stability across three loads.
- Refused rows: `status='refused'` with NULL embedding never appears in results, is counted in
  coverage, and satisfies the row-count guard.
- Writing eval embeddings never touches `chunks.embedding`.

Exploratory (documented, not in CI):

- The comparison, with a committed report carrying coverage first, then both analyses, checkpoint
  provenance, prefix pairs, measured character boundary, pool membership, seed, unjudged count,
  discordant counts and p-values — plus the re-issued tokenizer report on revision 3.

## 7. Acceptance

- Every chunk of the pack is accounted for per arm as `embedded` or `refused`, with the backend's
  own message on refusals, and `chunks.embedding` untouched.
- **Coverage per arm is printed above the verdict.**
- Both arms embedded byte-identical *inputs* (pre-prefix) for documents and queries, each under its
  own documented instruction format, with **zero silently truncated payloads** — detected by
  tokenising, not inferred.
- Labels reach revision 3 through blind re-pooling **over every leg including keyword/nori**, with
  the anonymised dump and its seed committed; keyword floors re-recorded; the tokenizer report
  re-issued and labelled descriptive.
- A committed report gives the **confirmatory comparable-subset verdict** and the **descriptive
  all-query view** separately, states which model the evidence favours — or that it favours neither
  — and carries the Pack A sentence.
- Production unchanged: no model change, no `chunks` schema change, no edit to
  `nexus/providers/embedding.py`, no new production dependency.

## 8. Units

1. **Eval vector leg** — store, guards, exact scan, shuffled negative control. *(landed 2026-08-03)*
2. **Fused leg** — production `_rrf_fusion` reused. *(landed 2026-08-03)*
3. **Arms + refusal accounting** — nomic via Ollama with refusal rows; KURE via the pinned
   harness-only provider with a tokeniser-based truncation guard; two hashes; coverage.
4. **Re-pool and tokenizer re-issue** — blind pooling over all six legs to revision 3, floors
   re-recorded, tokenizer report re-issued as descriptive. **Lands before Unit 5.**
   *Authority note* (I-011): the labels, the floors and the tokenizer report belong to
   `SPEC-nexus-korean-retrieval-eval`. This unit executes there under that SPEC's rules — its
   §4.2 already mandates re-pooling for a new configuration — and is sequenced here only because
   this change is what creates the new configurations. Nothing in it is decided by this SPEC.
5. **Comparison and verdict** — comparable-subset confirmatory analysis, all-query descriptive
   analysis, report committed.
