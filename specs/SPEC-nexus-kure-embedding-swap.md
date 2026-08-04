---
id: SPEC-nexus-kure-embedding-swap
type: spec
title: Swap the embedding model to KURE-v1 — dimension change, re-embed, and the ANN
  measurement the comparison could not make
status: approved
linked_adrs:
- ADR-0008
tags:
- nexus
- search
- korean
- embedding
- migration
date: '2026-08-04T05:38:24Z'
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-04T05:49:54Z'
content_hash: sha256:adcfca46faca8fb1d4be329e3e17c873dba80a8c3b93424379e2fa56dc0743c3
---

## 1. Goal

The comparison licensed one thing: writing this SPEC. On Pack A (label revision 2, exact-scan vector leg), the measured
`Recall@10` was **0.402 for `nomic-embed-text` and 0.975 for KURE-v1**; on the confirmatory
comparable subset the paired sign test gave **27 wins / 1 loss / 8 ties — 28 discordant pairs,
p ≈ 2 × 10⁻⁷** (I-018: not "≈ 0", and well past the rule's ≥ 6 discordant-pair precondition).
Those are **point estimates under an incomplete pool**: 821 pooled documents are unjudged and count
as non-relevant, so both arms' numbers are depressed. Which arm loses more is **not derivable**
(I-012) — the earlier phrasing "conservative against the winner" was an argument, not a
measurement, and §4.6 relies on the opposite property (asymmetry) to demote the cross-arm ANN
comparison. Both cannot be assumed. What survives without an argument is the size of the gap:
0.402 against 0.975 under one identical gold set, on a leg where 27 of 28 discordant queries went
one way. Fused 0.777 was carried almost
entirely by the keyword leg's 0.771 — on Korean, today's hybrid is BM25 with a passenger. `nexus/CLAUDE.md` rule 9 forbids English-only embedding
models; `config.yaml` runs one. The rule was right.

This SPEC changes the production embedding model to KURE-v1: a **dimension change 768 → 1024**, a
**full re-embed**, a serving path that is not Ollama, and the **ANN-side measurement the comparison
explicitly could not make**.

### 1.1 Gate record

> **Gate: fired. Declared by LivingLikeKrillin (director) on 2026-08-04**, choosing the swap over
> Pack B labelling and multi-turn as the next unit.

ADR-0008 §3(3) unblocked two directions to be *proposed* — multi-turn retrieval and a Korean
evaluation set — and an embedding swap is not one of them; §5's backstop is a **re-read
obligation**, not an authorisation (I-013). So the authority here is the declaration above and
nothing else, recorded as ADR-0002's procedure requires. No ADR-0006 override is claimed.

**ADR-0008 §5's backstop fires here** — "an embedding-model change" is one of its named events —
and it is discharged in full rather than in part (I-013). Re-read 2026-08-04:

- **(a) extension point under MIT** — unchanged; nothing in Onyx's hook situation moved. The
  deferral stands on its own sufficiency clause.
- **(b) Korean evaluation set on khala's real corpus** — still unmet. Pack A is a public stand-in;
  this SPEC does not claim otherwise anywhere.
- **(c) does maintaining our retrieval stack crowd out governance work** — judged from the
  merged-PR record, as ADR-0008 §5 requires: the last two merges (#152, #153) were retrieval
  *measurement*, and the two production defects they surfaced were governance-relevant
  (determinism, silent NULL coverage). Retrieval work has not displaced governance work; it has
  been the thing producing the evidence governance needs. (c) does not fire.
- **ADR-0008 §6's connector-cost review**, tied to the same event: the connector gap is unchanged
  (two source paths). No connector work is authorised here; the cost stays visible and unpaid.

## 2. Non-goals

- **Re-deciding the model.** That comparison is done and committed. If someone wants a third model,
  it re-pools and re-runs; it does not reopen here.
- **Reranking, chunk-size tuning, query rewriting.** Those stay out.

  But **"one variable" is not an honest description of this change** (I-014). It lands a new
  production service, a column, an index, a per-model prefix registry with new startup failures, a
  re-embed CLI with a waiver table, and a config seam. §4.2 argues the extra variables cannot
  confound the *measurement*; that says nothing about **delivery risk**. The mitigation is
  sequencing and reversibility, not pretending the change is small: Units land in order, each is
  inert until the next arrives (the column is unread, the sidecar unused, the CLI unrun), and the
  cutover is one setting with the old path intact behind it.
- **Making the Notion corpus the evidence.** Pack A is what was measured. §4.6 says what this
  SPEC does and does not claim about the live corpus.
- **Removing Ollama.** It stays for any other model use; this SPEC adds a serving path, it does not
  delete one.
- **Judging the deferred pool.** The 821 unjudged candidates stay unjudged (that SPEC's §4.5); the
  tripwire test still guards them.

## 3. What exists, and what the swap must move

| fact | consequence |
|---|---|
| `chunks.embedding` is `vector(768)`; `idx_chunk_vector` is ivfflat over it | a 1024-dimension model needs a new column and a new index. §4.2 |
| `EmbeddingService` speaks only to Ollama and hardcodes `search_document: ` / `search_query: ` | KURE is a sentence-transformers checkpoint and takes no prefix. §4.1, §4.3 |
| `config.yaml` declares `embedding.document_prefix` / `query_prefix` that the service never reads | dead keys become live, per model. §4.3 |
| `chunks.embed_model` is recorded per vector; `index/embed_health.py` reports the distribution and warns on mixing | the mixed-generation window is already observable — this is what it was built for (#142) |
| ingest re-embeds on NULL, and a failed embed leaves NULL silently | the re-embed must be *driven*, not left emergent, and its progress must be countable. §4.4 |
| measured 2026-08-04, CPU: **query 101 ms median / 217 ms max**, document ≈ 2.2 s per 2,000 characters, model load 8.8 s | queries are interactive-safe; re-embedding is an offline cost. §4.1 |
| **Archon (`nexus/nexus/claims/`) and Arbiter contain no reference to `embedding` or the vector search path** — checked 2026-08-04 | ADR-0008 §7 requires both to be treated as in scope at a substrate-adjacent change (I-014). They are in scope and the check is recorded: neither reads nor writes the vector column, so the swap does not implicate them. If that changes, this row is where the claim was made |
| `ingest/pipeline.py` nulls `embedding` on text change and back-fills `WHERE embedding IS NULL` | the same emergent path must learn the new column, or ingest silently keeps filling the old one. §4.4 |

## 4. Design

### 4.1 Serving: a sidecar, not Ollama

Ollama does not ship KURE-v1, and importing a converted checkpoint would put an unpinned conversion
between the measurement and production. So KURE is served by a **small sentence-transformers HTTP
service** in `docker-compose.yml` (`nexus-embed`), pinned by checkpoint revision, exposing the two
calls `EmbeddingService` needs.

**The honest cost.** This is a new production service carrying torch (~2–3 GB image) and ~9 s of
model load at start. The evaluation SPEC promised torch would stay out of the **app image**; that
promise holds — the app talks HTTP and its dependency set is unchanged, and the existing isolation
tests keep it that way.

**Why CPU is acceptable, against the baseline it must be compared to** (I-011). Measured on the same
machine, 2026-08-04:

| | query embed (median / max) |
|---|---|
| `nomic-embed-text` via Ollama, over HTTP (today's production path) | **67 ms / 73 ms** |
| KURE-v1, sentence-transformers **in-process** (not the shipped path) | **101 ms / 217 ms** |

**These two are not the same kind of measurement** (I-011). The nomic figure includes an HTTP
round trip and a container boundary; the KURE figure is a library call in the process that loaded
the model. The shipped path is a sidecar, so the honest comparison does not exist yet: **Unit 1
re-measures KURE over its own HTTP boundary and this table is replaced with that number before
any cutover decision**. The in-process figure bounds the model's own cost (~101 ms) and says the
design is not obviously infeasible; it does not license the +34 ms claim, which is withdrawn until
measured on the real path.

**Cold start is part of that path.** The model takes ~8.8 s to load. The sidecar therefore exposes
a readiness endpoint that is false until the model is resident, compose gates dependants on it,
and the client uses a **timeout shorter than the search budget** so an unready or wedged service
degrades the vector leg (§5) instead of hanging the request — §5's clean-degradation claim is only
true if a timeout exists, so it is specified here rather than assumed. §4.6 records the
end-to-end `/search` p50/p95 before and after, because that — not the embedding step alone — is the
budget rollback is judged against, and this SPEC does not get to declare it acceptable in advance.

**Re-embed wall clock**: ~2.2 s per 2,000-character chunk, single-threaded CPU, ≈ **37 minutes per
1,000 chunks**. The live corpus size is read at migration time and printed before the run starts,
so the mixed-generation window is a number the operator sees rather than discovers. Batching and a
GPU both shorten it; neither is required.

### 4.2 Schema: a second column, not an ALTER

```sql
ALTER TABLE chunks ADD COLUMN embedding_1024 vector(1024);
CREATE INDEX CONCURRENTLY idx_chunk_vector_1024 ON chunks
    USING ivfflat (embedding_1024 vector_cosine_ops) WITH (lists = <sized below>)
    WHERE status = 'active' AND is_quarantined = false AND embedding_1024 IS NOT NULL;
```

Altering `embedding` in place would drop every vector at once and leave search dark until the
re-embed finished. Two columns give a **blue-green window**: the old vectors keep serving while the
new ones fill, and `search.embedding_column` (config) decides which one queries read. Rollback is
that one setting, not a restore.

**`lists` is sized from the row count**, not copied. The rule, fully specified so a test can assert
it (I-015): `lists = max(1, min(rows // 1000, 2000))` for `rows ≤ 1_000_000`, and
`lists = round(sqrt(rows))` above that — pgvector's two published regimes, with a floor of 1 so a
small corpus yields a valid index. **`rows` counts the chunks the index's partial predicate
matches** (`status='active' AND NOT is_quarantined AND embedding_1024 IS NOT NULL`), evaluated
**after** the re-embed completes — during the migration window that count is climbing, and sizing
against a half-filled column would size against a corpus that never exists. The migration records
the value and the count it came from.

**This is a second variable, and it is named** (I-019). Re-sizing `lists` changes ANN recall by
itself, so if the new column got a well-sized index and the old one kept a stale one, §4.6 would
credit the model for the index. **The measurement therefore rebuilds the old column's index at the same computed `lists` —
in the disposable measurement tenant's database only, never in production** (I-010). ivfflat
indexes are table-wide, so rebuilding production's would change live ranking and break both §7's
"`embedding` and its index are untouched" and the rollback test's "returns the old ranking
exactly". The model comparison runs between two indexes sized alike **in the measurement
environment**; production's old index keeps exactly the geometry it has, which is what makes
rollback a true restore. The per-model prefix registry of §4.3 is a third variable in the same
sense, but it cannot confound §4.6: each arm is measured under its own documented format, which is
the condition the comparison already established.

After the cutover holds (§4.5), a later change drops `embedding` and the old index. **Not in this
SPEC**: keeping the rollback path is the point.

### 4.3 Per-model instruction format, in production this time

`EmbeddingService` gains a per-model prefix lookup, read from the config keys that already exist and
are currently dead (`embedding.document_prefix` / `query_prefix`), defaulting per model:

- `nomic-embed-text` → today's two strings, so behaviour is unchanged for anyone still on it.
- `KURE-v1` → empty, because its card documents no instruction.

**Precedence, stated because empty is a legitimate value** (I-015): the per-model default is the
source of truth; an explicit config key **overrides** it; a *present but empty* key means "no
prefix" and is distinguishable from an absent key (absent → fall back to the default). And an
explicit prefix set against a model whose card documents none — nomic's strings configured for
KURE — **fails at startup**, not silently: that combination is the confound the comparison removed,
reintroduced by configuration. An unknown model likewise fails loudly rather than inheriting
nomic's format. Tests cover all four cases.

### 4.4 The re-embed is driven and countable

A CLI (`nexus reembed --model KURE-v1`) walks active chunks with a NULL `embedding_1024`, embeds in
batches, and writes `embed_model` alongside. It is resumable (the NULL column *is* the queue), and it
reports progress as `done / total` with a rate, because "it is running" is not a status.

**Failures are counted, not swallowed.** The Korean work found that a refused or failed embed leaves
a NULL that nothing reports. Here: each failure is recorded with its reason, the run ends with a
summary, and **a non-zero failure count blocks the cutover** (§4.5). `embed_health.py` already
reports the generation distribution; the re-embed run reads it before and after so the mixed window
is visible rather than inferred.

### 4.5 Cutover, and what would send it back

The cutover is a config flip once **all** of these hold, checked and printed by
`nexus reembed --status`:

1. Every active, non-quarantined chunk is **accounted for**: either a non-NULL `embedding_1024`, or
   an explicit **waiver row** (I-009):

   ```sql
   CREATE TABLE embed_waivers (
       chunk_rid  TEXT PRIMARY KEY,
       model      TEXT NOT NULL,
       reason     TEXT NOT NULL,       -- the backend's message, verbatim
       waived_by  TEXT NOT NULL,       -- the same signature convention approvals use
       waived_at  TIMESTAMPTZ NOT NULL DEFAULT now()
   );
   ```

   A waiver is a human decision to leave corpus content out of the vector index, so it is a row
   with a name on it, not a flag: the re-embed CLI never creates one (it only reports candidates),
   `--waive <rid> --reason ... --by ...` does, re-runs leave existing waivers alone and re-attempt
   nothing that is waived, and `embed_health` reports the count thereafter. §6 tests the path. A single permanently-failing chunk — oversized, malformed, an OOM — must not strand the
   migration with the corpus half-migrated, but it must not vanish either: waived chunks are listed
   in the cutover output and counted in a `waived` metric that `embed_health` reports thereafter.
2. Zero *unwaived* failures in the run summary.
3. `embed_health` shows a single generation **for the new column**, which means it must first be
   taught about it (I-008): today it reads `embedding` under the old index's partial predicate.
   Unit 3 extends it to report per-column generations and the `waived` count, and a test asserts
   it reports the new column — otherwise this condition would pass by describing the column being
   replaced.
4. **The ANN measurement of §4.6 has been run and recorded.**

**Rollback** is `search.embedding_column` back to `embedding`; the old column and index are intact
until a later SPEC removes them. **Rollback knowingly restores a rule-9-violating configuration**
(I-016) — an English-centric model in a Korean-first system — and that is accepted as the lesser
harm against a broken search, with an exit obligation: a rollback opens the question again rather
than closing it, and the rolled-back state is a recorded exception, not a resting place. Rollback triggers, named in advance so the decision is not made
under pressure: the ANN measurement showing worse fused recall than the recorded baseline, p95 search
latency regressing beyond the budget recorded at cutover, or the embed service failing in a way that
takes search down rather than degrading it.

### 4.6 The measurement this SPEC owes

The comparison ran an **exact** vector leg and said in writing that it does not predict production's
ivfflat. This SPEC pays that debt:

- **On the pinned Pack A corpus**, loaded into a disposable tenant with both columns populated,
  measure the fused leg through `hybrid_search` — the real path, ivfflat and all — for the old model
  and the new one, at the `lists` value §4.2 computes (both indexes rebuilt at it, §4.2).
- **The primary reading is each arm against itself** (I-012): `exact → ANN` delta per arm. That
  comparison is immune to the unjudged pool, because the same gold set scores both sides of it and
  a document nobody judged is missing from both.
- **The arm-versus-arm ANN comparison is reported but not confirmatory.** Changing the retrieval
  path surfaces documents the pool never saw, they count as non-relevant, and the penalty is not
  symmetric between arms. Making that comparison confirmatory would require re-pooling under ANN —
  which is the deferred adjudication, still deferred. The cutover condition (§4.5) is written
  against the self-delta, not against the cross-arm p-value.
- **Latency**: p50/p95 of the query embedding and of end-to-end `/search`, before and after, recorded
  at cutover as the budget rollback is judged against.
- The verdict rule is inherited unchanged (paired sign test, α = 0.05, ≥ 6 discordant pairs, "no
  measurable difference" leaves the incumbent). **If ANN erases the advantage, the swap does not
  happen** — the comparison's own words were that the exact result is necessary, not sufficient.

**What it still will not prove.** Pack A is not khala's corpus, so this measures the swap on a
representative public corpus and not on the live one. The live corpus gets the same treatment only
when Pack B exists. The report says so, as its siblings do.

## 5. Error handling

- Embed service unreachable at query time → the vector leg returns nothing and the keyword leg still
  answers, as today when Ollama is down. Search degrades; it does not error.
- Embed service unreachable during re-embed → the run stops with a resumable state; the NULL column
  is the queue.
- A vector of the wrong dimension → rejected at write, never stored. `vector(1024)` enforces it in
  the column, unlike the eval store's deliberate lack of a dimension.
- Cutover attempted with any condition of §4.5 unmet → refused, with the failing condition named.

## 6. Testing

Unit, no DB:

- Per-model prefixes: nomic yields today's strings, KURE yields empty, an unknown model raises.
- `lists` sizing from row count, including the small-corpus floor.
- Cutover precondition checker: each of §4.5's four conditions independently blocks, with its own
  message.
- The re-embed's failure summary is non-empty when an embed fails — the "silent NULL" regression,
  asserted directly.

Against Postgres:

- Migration adds the column and index without touching `embedding`; existing vectors are byte-identical
  afterwards.
- Writing a 768-vector into `embedding_1024` is rejected by the column type.
- `search.embedding_column` switches which column the vector leg reads, asserted at the seam by
  counting queries, not by reading config back.
- Re-embed is resumable: interrupt after N rows, re-run, and every active chunk ends non-NULL exactly
  once.
- Rollback: flipping the setting back returns the old ranking exactly, since the old column is untouched.

Exploratory (documented, not in CI):

- §4.6's ANN comparison on Pack A, with a committed dated report.

## 7. Acceptance

- KURE-v1 serves production embeddings through a pinned sidecar; the app image's dependency set is
  unchanged and the isolation tests still pass.
- `chunks.embedding_1024` exists with its own ivfflat index at a computed `lists`; `embedding` and its
  index are untouched and still queryable.
- Every active chunk is embedded under one generation, with zero failures, both counted and printed.
- **The ANN measurement of §4.6 is committed.** If it shows the advantage surviving ivfflat, the
  cutover proceeds and the criteria above apply.
- **If it does not** (I-017), this SPEC still completes, in a defined state: the sidecar, the column,
  the index and the re-embed **stay in place and unused** (`search.embedding_column` remains
  `embedding`), the report is committed as the record of why the swap did not happen, and the
  follow-up is named — an ANN-side investigation (probe tuning, HNSW, or a different index) rather
  than a model question, since the exact-scan result already answered the model question. Nothing is
  torn down: a negative ANN result is information about the index, and throwing away the vectors
  would discard the only evidence for it.
- `config.yaml` no longer contradicts `nexus/CLAUDE.md` rule 9, and the previously dead prefix keys
  are live and per-model.
- Rollback is one setting, exercised in a test rather than described.

## 8. Units

1. **Sidecar + provider** — `nexus-embed` service pinned by revision, `EmbeddingService` gains a
   backend and per-model prefixes, unknown model fails loudly.
2. **Schema + sizing** — migration for `embedding_1024` and its index, `lists` computed and recorded,
   `search.embedding_column` seam with its switch test.
3. **Driven re-embed** — resumable CLI, counted failures, `embed_health` before/after, status command
   implementing §4.5's four preconditions.
4. **ANN measurement and cutover** — §4.6's report on Pack A, latency budget recorded, flip, rollback
   test.
