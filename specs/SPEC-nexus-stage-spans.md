---
id: SPEC-nexus-stage-spans
type: spec
title: Stage spans (Unit 1) — capture what each retrieval stage received and produced
status: approved
linked_adrs:
- ADR-0006
tags:
- nexus
- observability
- evaluation
date: '2026-09-04'
approved_by: LivingLikeKrillin
reviewed_at: '2026-09-04T12:03:06Z'
content_hash: sha256:69c6397b15a15d11d371a6f5bca3ca33047a833e7713c393a89a5af440ebd7ac
---

## 1. Goal

A production query that answers badly cannot be attributed to a stage. The live path records
`search_log` — one flat aggregate row per request — so telling *missed the candidate pool* from
*lost the ranking* from *cut by the diversity cap* from *never reached the prompt* requires
reproducing the query against a labelled set.

**This unit records the data. It does not judge.** A second unit reads it (§4.1).

### 1.1 Scope was cut, and why

The first draft carried capture, a verdict reader, a diagnostic re-query, format-compliance wiring
and a golden verdict test in one unit. Critique found the pattern was scope, not defect: two of the
added concerns were **not implementable as drafted** —

- the supersession filter lives inside the retrieval SQL, so rows it excludes are never returned;
  observing them needs a second query or a rewrite of that SQL, and both contradict *"no retrieval
  changes"*;
- the `answer` span carries aggregates only, so *"in the packet but absent from the answer"* had no
  data behind it — which also made the registered control outcome undecidable.

A third, the diagnostic re-query, is **harder than drafted rather than impossible**: `documents`
upserts in place and retains no past content, but `doc_reingest_events` is append-only and records
overwrites, so drift between capture and re-query is **partially** detectable even though the old
text is gone. The first draft claimed it was "not possible at all", which overstated the constraint;
this draft does not overstate the remedy either (round 4, I-008, I-009). Two blind paths remain:
an overwrite keyed on a colliding `doc_rid` cannot separate *this document changed* from *a
different document clobbered it*, and while ADR-0006 ties vector invalidation to a `chunk_text` change — which is itself an overwrite
that the reingest log records — that coupling does not cover **backfill of never-embedded chunks or
an offline model or dimension change**, neither of which leaves either signal (round 5, I-008). **Unit 2 must treat drift
detection as best-effort and refuse rather than assert completeness.**

Each is a real question. None can be answered before the data exists. So this unit is capture, and
those questions move to Unit 2 to be settled **against captured rows rather than against a guess**.

### 1.2 The failure taxonomy this serves

Barnett et al., *Seven Failure Points When Engineering a RAG System* (CAIN 2024, arXiv 2401.05856);
see [`research/2026-09-04-rag-current-practice.md`](../research/2026-09-04-rag-current-practice.md)
§2. FP1 has live detectors — `index/embed_health.py` (coverage, waivers, refusals, unreachable
documents) surfaced through `nexus status`, and `search/confidence.py`'s absence verdict in the
answer path. ⚠ *Detected* is not *delivered*: this repository's own history is a detector whose
result reached no consumer, and a vector index that broke silently (round 5, I-015). FP1 is out of
scope here because it has a path, not because the path is proven. FP6 has no
instrument anywhere and is deferred (`D2` in the audit). This unit captures what FP2, FP3, FP4 and
FP7 attribution will need; **it attributes none of them.**

### 1.3 Verdict criterion, registered before implementation

**One registered claim, and it runs in CI.**

**Constructed case.** On a fixture corpus with a **stub embedder** — vectors are fixture data, not a
model call — a query's answering chunk is **absent from the BM25 pool by construction — the query terms occur
nowhere in it** — and present in the vector pool at a known rank. The captured spans must show exactly that: absent from the BM25
leg's candidate rows, present in the vector leg's at that rank, and carried or cut at each later
stage as constructed. The failure stage is known because it was built.

Both sides are built, not ranked. **Stub vectors** matter because with a live model the expected
rank would be a property of the model, so a model or dimension change would silently break the gate.
The **BM25 side is made empty by construction** rather than by out-ranking, because a pool position
is a property of `ts_rank_cd`, the Korean tsvector configuration and `bm25_top_k` — real code that a
tokenizer or dictionary change moves (round 5, I-007). Retrieval only, **no LLM call**.

⛔ **The A51 reconstruction is not a gate.** An earlier draft registered *"read off the gold's
position at every stage"* for `m01`/`m02`. That claim is unfalsifiable as worded — a gold that
missed a pool has **no row and therefore no position**, only `absent`, and recovering its true rank
is precisely the diagnostic re-query deferred to Unit 2. It also requires resolving which `doc_rid`
is the gold, which this unit declares out of scope. So the A51 run is kept as a **recorded
observation** (§5), pinned to tenant, pool sizes and `index_generation`, and it is evidence rather
than a pass condition.

### 1.4 The unit's own first output

**No retrieval changes** — asserted and tested (§5). ⚠ Stated as *retrieval*, not *answer*: the
equivalence test asserts identical hits and ordering, and deliberately does **not** assert a
byte-identical LLM answer, which generation cannot provide.

And because *"live capture is cheap"* was asserted in an earlier draft with no measurement, and the
instrument for measuring it is the thing being built, this unit **reports its own cost as a
deliverable**:

- **quantity** — candidate rows and span rows written per request (
  counted from the rows written)
- **baseline** — the same queries with `spans.enabled=false`
- **completion** — counted **from the span rows themselves** over the fixture query set. No replay
  harness, no second arm, no new latency column: a benchmark rig attached to a capture unit was scope
  creep (round 5, I-016), and the row count is already in the data.
  ⚠ Live volume on this deployment is near zero, so a live completion condition may never be
  reachable; live numbers are an addition when volume exists, not a gate.
- **no assertion, no threshold.** The first pass is observation, and this repository has already
  built a gate on a number it had never measured.

**Bounded, not unbounded.** Worst case with a rewrite channel: legs `2 channels × 2 legs × 20` = 80,
fusion's merged union ≤ 80 but capped at 100, diversify's inputs ≤ 80 (**uncapped by exemption**),
fill additions ≤ `per_doc_cap`, packet ≈ `top_k`. With today's values that is **80 + 80 + 80 + 5 + 10
= 255 rows**, and the cap binds only if pool sizes grow (round 5, I-014). `spans.max_candidates_per_span`
(default 100) caps any single span, and a truncated span records `candidates_expected` above its row
count so truncation is visible rather than silent.

## 2. What exists

- **`search_log`** (`nexus/init.sql:440`) — one row per request; `read_scope`, `evidence_tenants`,
  `n_snippets`, `top_score`, `n_citations`, `unverified_citations`, `fusion_channels`, tokens, cost.
  `_insert` returns the row id, so a parent key exists. ⚠ **`search_log` has no purge today** (§3.4).
- **`hybrid_search`** (`search/hybrid.py`) — `tasks[(channel_index, "bm25"|"vector")]` holds each
  leg's pool, sized by `search.bm25_top_k` / `search.vector_top_k` (both 20). `_rrf_fusion` returns
  the **whole merged list, uncut**; `fuse_channels(ch_results, k=rrf_k)` is called **once across all
  channels** (`hybrid.py:660`), so fusion is singular by construction even with a rewrite channel.
  `_diversify(hits, top_k, per_doc_cap)` applies both the `top_k` cut and the per-document cap.
  `_bm25_search` and `_vector_search` return raw scores alongside ranks — `search/confidence.py`
  records why that matters: RRF consumes rank only, so "how well did it match" is erased at fusion.
- **`search/section_fill.py`** — fills a document's remaining sections when that document saturated
  `diversity_per_doc_cap`. `trigger_saturated` is that condition: the diversity rule cut the document,
  which means retrieval concentrated on it.
- **`search/evidence_packet.py`** — `assemble_packet` builds what reaches the prompt, including graph
  findings; `n_graph_edges` is the count of graph edges attached to the packet, the same quantity
  `search_log` already records.
- **`signals.record_search`** (`search/signals.py`) — structlog always, best-effort DB insert,
  **never raises**. This unit writes there.
- **`search/purge_schedule.py`** — start-up plus periodic, advisory lock, because *"a purge that
  does not run has no symptom"*.
- **`llm/citations.py`**, **`llm/numbers.py`** — produce `unverified_citations` and
  `unverified_numbers` on `AnswerResult`.
- **`index_generation_events`** — the corpus's declared generation of record.
  **`doc_reingest_events`** — append-only per-document overwrite log (§1.1, §3.1).
- **Not available**: no OpenTelemetry instrumentation. `nexus/nexus/otel/` ingests *other systems'*
  telemetry into the graph — a name collision, not reusable plumbing.

## 3. Design

### 3.1 Two tables, plus two columns on the parent

```sql
ALTER TABLE search_log
    ADD COLUMN spans_expected INTEGER;          -- NULL = capture disabled. Known BEFORE the insert

CREATE TABLE search_span (                      -- summary tier
    id             BIGSERIAL PRIMARY KEY,
    search_log_id  BIGINT      NOT NULL REFERENCES search_log(id) ON DELETE CASCADE,
    ts             TIMESTAMPTZ NOT NULL DEFAULT now(),   -- purge cuts on this
    seq            INTEGER     NOT NULL,                 -- dense; ordering is by seq, not name
    stage          TEXT        NOT NULL,
    channel        TEXT,                                 -- leg rows only; NULL elsewhere
    leg            TEXT,                                 -- leg rows only; NULL elsewhere
    n_in           INTEGER,
    n_out          INTEGER,
    fired          BOOLEAN     NOT NULL DEFAULT true,    -- a stage that did not run still writes a row
    score_kind     TEXT,
    index_generation TEXT,
    candidates_expected INTEGER,                         -- rows the stage produced, before any cap
    candidates_cap      INTEGER,                         -- the cap in force at capture (round 4, I-005)
    candidates_purged_at TIMESTAMPTZ,                    -- stamped by purge only, and only if rows existed
    detail         JSONB       NOT NULL DEFAULT '{}',    -- scalars only; enforced in the writer
    UNIQUE (search_log_id, seq),
    CONSTRAINT span_stage_known CHECK (stage IN
        ('leg','fusion','diversify','section_fill','packet','answer')),
    CONSTRAINT span_score_kind_known CHECK (score_kind IS NULL OR score_kind IN
        ('ts_rank_cd','cosine_distance','rrf')),
    CONSTRAINT span_leg_fields CHECK (
        (stage = 'leg' AND leg IN ('bm25','vector') AND channel IS NOT NULL AND channel <> '')
     OR (stage <> 'leg' AND leg IS NULL AND channel IS NULL))
);
CREATE INDEX idx_search_span_ts  ON search_span (ts);
CREATE INDEX idx_search_span_log ON search_span (search_log_id, seq);
-- AT MOST one row per non-leg stage per request. "at least one" is a writer invariant (§3.3),
-- not something a partial unique index can express.
CREATE UNIQUE INDEX idx_search_span_singleton
    ON search_span (search_log_id, stage) WHERE stage <> 'leg';

CREATE TABLE search_span_candidate (            -- detail tier, kept briefly
    span_id    BIGINT  NOT NULL REFERENCES search_span(id) ON DELETE CASCADE,
    rank       INTEGER NOT NULL,                -- see below
    chunk_rid  TEXT,                            -- NULL under retention option 3 (§3.4)
    doc_rid    TEXT    NOT NULL,
    raw_score  DOUBLE PRECISION,                -- interpret via the span's score_kind
    dropped    BOOLEAN NOT NULL DEFAULT false,  -- diversify only: this row was cut
    PRIMARY KEY (span_id, rank)
);
```

**`rank` is the stage's INPUT ordering, 1-based**, and it is what the primary key rests on, so the
definition has to be exact:

| stage | `rank` derives from |
|---|---|
| `leg` | that leg's own result order (BM25 by `ts_rank_cd` desc, vector by distance asc) |
| `fusion` | the merged RRF order returned by `fuse_channels`, uncut |
| `diversify` | **its input order** — i.e. the fusion order. A cut row keeps its pre-cut rank and carries `dropped=true` |
| `section_fill` | the order in which chunks were appended |
| `packet` | snippet order as assembled into the prompt |

**Count semantics, and the one invariant that matters.** `n_in` and `n_out` are the stage's input
and output cardinality; for a `leg` span `n_in` is **NULL** (a query has no meaningful input count)
and `n_out` is the pool size. `candidates_expected` is **the number of candidate rows the stage
produced before `spans.max_candidates_per_span` was applied**. The invariant a reader may rely on:

> `COUNT(child rows) = LEAST(candidates_expected, candidates_cap)` — and any disagreement means rows
> were lost, never that the stage produced fewer.
>
> **Four exceptions, and a reader that omits them will report data loss on every purged request**
> (round 4, I-004; round 5, I-002): the invariant does not hold when `candidates_purged_at` is set,
> for the `answer` stage (no children by design: `candidates_expected = 0`, `candidates_cap` NULL,
> `n_in` = the packet's snippet count, `n_out` NULL — round 5, I-013), for a `fired=false`
> stage, or for **`diversify`, which is exempt from the cap** — there `COUNT(child rows) =
> candidates_expected` regardless of `candidates_cap`.
>
> `candidates_cap` is stamped **per span**, not read from config at read time — otherwise changing
> the cap would retroactively make every historical span look truncated or lost.

**Truncation keeps ranks 1..`candidates_cap` and discards the tail**, and `diversify` is **exempt from the cap**: its `dropped=true`
rows are the diagnostic payload, truncating by input rank would discard exactly them, and its size is
already bounded by the fusion list (round 4, I-006).

**`score_kind` names the metric, not the leg**: `ts_rank_cd` is a similarity (higher is better),
`cosine_distance` is a distance (lower is better). **Raw scores are comparable only within one
span.** Across spans, only ranks are. The domain is a CHECK, not a comment.

**`detail` is scalars-only, enforced by the database.** PostgreSQL rejects *subqueries* in CHECK
constraints, which is why the first draft's constraint was invalid — but that does not rule out a
constraint (round 4, I-014). The migration defines an `IMMUTABLE` helper and constrains on it, so a
second writer, a migration or a manual insert cannot store nested JSON that Unit 2 is being told it
may rely on:

```sql
CREATE FUNCTION jsonb_values_all_scalar(j jsonb) RETURNS boolean
    LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT bool_and(jsonb_typeof(value) NOT IN ('object','array')) IS NOT FALSE
    FROM jsonb_each(j) $$;
-- ... CONSTRAINT span_detail_scalar CHECK (
--         jsonb_typeof(detail) = 'object' AND jsonb_values_all_scalar(detail))
-- The top-level type check is not optional: jsonb_each raises on a non-object, so without it a
-- detail of '[]' produces a runtime error instead of a clean constraint violation (round 5, I-009).
```

The writer validates too, so a bad value fails fast with a readable error rather than a constraint
violation that discards the whole batch. ⚠ The guarantee is not absolute: `CREATE OR REPLACE` of the
helper does not revalidate existing rows, so the database enforces this only while nobody redefines
the function (round 5, I-009).

**`spans_expected` on the parent.** The child constraints abort the whole multi-row insert on any
violation, and `record_search` never raises — so a constraint bug would make **every** span for a
request vanish with no signal. This column carries **how many span rows the writer was about to
insert**, and it is written in the same statement as `search_log` itself, *before* the span insert.
A second statement set afterwards would leave a window in which a crash yields NULL —
indistinguishable from capture-disabled, collapsing the very distinction the column exists for
(round 4, I-007). A reader compares `spans_expected` against the actual span count:
`0 rows against a non-NULL expectation` means the batch was lost. Failures are also logged through
structlog. `candidates_expected` catches lost children; this catches a lost parent batch.

**`index_generation`** is the **corpus-wide** declared generation at capture time, read from the
latest `index_generation_events` row for the tenant and stored as that table's generation key
verbatim; **NULL when no generation has been declared** (round 5, I-012). ⚠ It cannot detect
a single document re-ingested under an unchanged corpus generation. `doc_reingest_events` records
those per document, so Unit 2 can detect drift for a specific `doc_rid` by joining on that log —
which matters because ADR-0006 documents `doc_rid` (`tenant:filename`) as *too coarse*, colliding
across documents that share a basename. **This unit records the facts; it resolves no gold, so the
ambiguity is not live here.** Unit 2 must refuse rather than guess when the join is ambiguous.

Counts, not ratios (`search/evidence_share.py`). **No thresholds anywhere in this unit.**

### 3.2 What one span is

| seq | stage | candidate rows | `detail` keys (all scalars) |
|---|---|---|---|
| 1..n | `leg` — one per (channel × leg); 2 today, 4 with a rewrite channel | that leg's pool | `pool_size` |
| +1 | `fusion` — **singular**, `fuse_channels` is called once across channels | the whole merged list, uncut | `rrf_k`, `n_channels` |
| +1 | `diversify` | its inputs, `dropped=true` on those cut | `top_k`, `per_doc_cap` |
| +1 | `section_fill` | the chunks it added | `trigger_saturated` |
| +1 | `packet` | the chunk snippets that entered the prompt — **graph findings get no candidate rows** (they are not chunks and have no `doc_rid`); they are counted in `detail` only, and `candidates_expected` counts snippets, so the row count does not disagree (round 5, I-005) | `n_snippets`, `n_graph_edges` |
| +1 | `answer` | none | `n_citations`, `unverified_citations`, `unverified_numbers`, `abstained`, `llm_failed` |

**A stage that does not run still writes a row with `fired=false`**, so `seq` is dense and a reader
never has to infer whether a missing row means *did not run* or *was lost*.

⛔ **`contained` is not captured.** Rows excluded by the ADR-0006 active/supersession filter are
never returned by the retrieval SQL, so observing them needs a second query or a rewrite of that
SQL. Unit 2 must decide how to pay for it (§4.1).

### 3.3 Write path

**Switch.** `spans.enabled`, **default `false`**. Capture accumulates the ranked-candidate corpus
that §3.4 concedes is a re-identification fingerprint, so it must not start before the window that
bounds that risk is chosen (round 5, I-010). Sign-off (§7) turns it on together with the window. When false, no span data is accumulated and
`spans_expected` stays NULL. The equivalence and destructive tests of §5 run against this switch and
a fault-injection point in the persistence call.

`hybrid_search` and `generate_answer` accumulate span records as **pure data** on the result object
and touch no database. Persistence happens in `signals.record_search`.

**Writer invariants** (the ones no constraint can express):

1. `seq` is dense from 1, with no gaps.
2. Every non-leg stage writes exactly one row per request, `fired=false` if it did not run.
3. **Leg rows number exactly `2 x search_log.fusion_channels`**, where `fusion_channels` counts the
   channels that were **dispatched**. A leg that errored or short-circuited still writes its row with
   `fired=false`, exactly as non-leg stages do — otherwise a failed leg yields `2n-1` rows and a
   reader must read it as lost data (round 5, I-006). The singleton index cannot express this; the
   writer and a test do.
4. `detail` values are scalars.

Each has a unit test; a violation is a bug in the writer, not a runtime condition.

**Transaction boundary (round 5, I-001).** `record_search` **commits the `search_log` row first**;
the span batch runs in its own transaction. Sharing one transaction would roll the parent back on any
child constraint violation, and then `spans_expected` would never survive — making the registered
"capture failure is visible" test impossible to pass.

**Id mapping.** One multi-row `INSERT ... RETURNING id, seq`; children attach by **matching on the
returned `seq`**, never by assuming the row order of a multi-row `RETURNING`.

**Failure is silent to the user, not to the record.** An answer must never fail to reach a user
because a span could not be written — but the failure is recorded via `spans_expected` and in the
log. Spans for a request whose `search_log` insert failed are prevented by the foreign key.

### 3.4 Retention — and the decision that is not the implementer's

- `search_span_candidate` — cut on the parent span's `ts`, window `spans.candidate_retain_days`,
  **3 days** (owner decision, §7).
  The pass stamps `candidates_purged_at` **only on spans that actually had candidate rows**;
  stamping a span whose children were never written (or the `answer` stage, which has none by
  design) would collapse the very distinction the column exists to preserve.
- `search_span` — cascades from `search_log`.
- Purge is **not a new mechanism**: one statement added to `search/purge_schedule.py`.

⚠ **`search_log` has no purge today**, so the summary tier inherits an unbounded lifetime. That is a
pre-existing retention gap for data this unit does not produce; it is **recorded here as a finding
and raised as its own item**, not folded into this unit's approval.

**Key-level joinability is preserved.** The detail tier hangs off `search_log.id`; it does not join
to `search_query_text`, whose `retention_key` is salted precisely so that it cannot be joined to
anything else.

⚠ **Key-level is not the whole argument.** A ranked candidate list is itself a strong fingerprint of
the query that produced it. Full-pool capture, correlated with `search_log`'s `evidence_tenants`,
timing and principal, is exactly the corpus that makes re-identification by correlation feasible —
a weaker form of the thing the salting prevents. **This spec does not claim that risk away.**

**Decision taken (§7): option 2, a 3-day window.** The reversible opening — a window widens once
volume is known, but discarded data cannot be recovered. `chunk_rid` is retained, so Unit 2 keeps
chunk-level attribution; the correlation exposure is bounded by time instead of by resolution.

## 4. Deferred

### 4.1 Unit 2 — the reader

Everything that judges, plus what this unit could not answer without data: verdict rules with
mutually exclusive predicates for the three FP3 sub-cases · refusal rules for missing evidence,
ambiguous `doc_rid` resolution and generation drift · **`contained`** (how to observe what the
supersession filter removed, and what it costs) · **FP4/FP7** (what per-claim signal the `answer`
span would need) · **the diagnostic re-query** for out-of-pool ranks, using `doc_reingest_events` to
detect drift · whether the A51 hand diagnosis is itself correct.

### 4.2 Not in either unit yet

FP5 (needs `search/format_compliance.py` wired into the live answer path — audit item `B2`, a
separate defect fix; pulling it in here was scope creep) · FP6 · per-candidate content hash ·
sampling · thresholds and alerting · an MCP tool · OTLP export · a web surface · a purge for
`search_log`.

## 5. Test plan

- **Pure assembly** — span records built from stage inputs, no database. Table-driven over the
  channel × leg matrix including the four-leg rewrite shape, and over stages that do not fire.
- **Writer invariants** — dense `seq`; one row per non-leg stage; `detail` with an object or array
  rejected; a span truncated at `max_candidates_per_span` still reports the full
  `candidates_expected`.
- **Persistence** — postgres: parent/child insert, `seq`-matched id mapping, cascade delete,
  `UNIQUE (search_log_id, seq)`, the singleton index rejecting a second `fusion` row, and each CHECK
  rejecting its bad case (unknown stage, unknown `score_kind`, a leg row with NULL leg, a non-leg row
  with a channel set, an empty-string channel).
- **Capture failure is visible** — with a constraint deliberately violated, the answer still returns,
  `search_log` is written, and **`spans_expected` is non-NULL while zero span rows exist**.
- **Retention** — purge removes candidates past the window, leaves summaries, stamps
  `candidates_purged_at` **only on spans that had rows**.
- ⭐ **Constructed case (§1.3.1)** — fixture corpus, chunk outside the BM25 pool and inside the vector
  pool. **Retrieval only, no LLM call**, so the test is cheap, deterministic and needs no live corpus.
- ⭐ **Reconstruction (§1.3.2)** — a recorded manual run over `m01`/`m02`, pinning tenant, pool sizes
  and `index_generation` in the report. Not a CI test.
- **Equivalence** — the same query with `spans.enabled` true and false produces **identical retrieval
  output** (hit rids and order) and identical `search_log` values **including `prompt_tokens`** —
  which is a function of the assembled packet, so it is the cheap check that capture did not perturb
  what reached the prompt (round 4, I-013) — and **excluding** `latency_ms`,
  `spans_expected`, `completion_tokens`, `cost_usd`, and **every answer-derived column**
  (`n_citations`, `unverified_citations`, `unverified_numbers`) — those are functions of the generated
  text and would flake for reasons unrelated to capture (round 5, I-004). The LLM answer is **not**
  asserted byte-identical.
- **Cost observation (§1.4)** — rows per request, counted from the captured spans over the fixture
  query set. Reported, not asserted. No separate harness.
- **Destructive path, deliberately broken** — with span persistence forced to raise, the answer path
  still returns an answer and `search_log` is still written. A skipped test here is no test.

## 6. Critique dispositions

Rounds 1 and 2 produced 35 issues; six were resolved by cutting scope (§1.1), the rest by design
changes now in §3. Round 3, 16 issues, all accepted:

| | disposition |
|---|---|
| I-001 | `search_log.spans_expected` — a lost parent batch is now recorded, not silent |
| I-002 | the singleton index comment corrected to **at most one**; density and at-least-one become writer invariants with tests (§3.3) |
| I-003 | `doc_rid` instability recorded; `doc_reingest_events` named as the per-document detector for Unit 2; this unit resolves no gold, so the ambiguity is not live here |
| I-004 | `spans.enabled` switch and a fault-injection point specified (§3.3) |
| I-005 | purge stamps `candidates_purged_at` only on spans that had rows |
| I-006 | the deliverable is **"no retrieval changes"**, matching what the test asserts |
| I-007 | cost deliverable given a quantity (`span_write_ms`, rows/request), an instrument, a baseline and N=100 |
| I-008 | accepted — claim 2 is a recorded run, pinned, and explicitly **not** the CI gate; claim 1 is |
| I-009 | resolved by verification — `fuse_channels` is called once across channels (`hybrid.py:660`), so fusion is singular even with a rewrite channel |
| I-010 | `rank` defined per stage as the input ordering, with the diversify cut case stated |
| I-011 | `n_in`/`n_out`/`candidates_expected` defined per stage, with the row-count invariant a reader may rely on |
| I-012 | accepted — "not possible at all" overstated; `doc_reingest_events` makes drift detectable per document, corrected in §1.1 |
| I-013 | accepted — the worst case is bounded arithmetic (~250 rows), stated; `spans.max_candidates_per_span` caps a span and truncation is visible |
| I-014 | `section_fill` and `evidence_packet` named in §2 with `trigger_saturated` and `n_graph_edges` defined |
| I-015 | `score_kind` domain and `channel <> ''` are CHECK constraints, not comments |
| I-016 | accepted — the `search_log` purge is recorded as a finding and raised separately, not made a condition of this unit's approval |

Round 4, 14 issues, all accepted:

| | disposition |
|---|---|
| I-001 | constructed case now uses a **stub embedder with fixture vectors** — model-independent and deterministic; a live model would have made the expected rank a property of the model |
| I-002 | accepted — *"read off the position at every stage"* is unfalsifiable for a gold that missed a pool. Claim rewritten and demoted |
| I-003 | accepted — the A51 reconstruction required gold resolution this unit declares out of scope. It is now a recorded observation, **not a gate**; one registered claim remains |
| I-004 | invariant carves out purge, the `answer` stage and `fired=false` stages explicitly |
| I-005 | `candidates_cap` stamped per span, so a config change cannot retroactively rewrite history |
| I-006 | truncation keeps the lowest ranks; `diversify` is exempt because its cut rows are the payload |
| I-007 | `spans_captured` (set after) replaced by `spans_expected` (written with `search_log` itself), removing the crash window |
| I-008 | drift detection restated as **partial**; the colliding-`doc_rid` blind path named |
| I-009 | second blind path named — NULL-driven re-embedding leaves no generation change and no reingest row |
| I-010 | cost measured by **synthetic replay** on a fixed corpus, not by waiting for live volume that may never arrive |
| I-011 | leg cardinality is a writer invariant: exactly `2 x fusion_channels` rows |
| I-012 | `span_write_ms` labelled the narrow slice; the replay harness measures end-to-end latency across both arms |
| I-013 | `prompt_tokens` moved **into** the equivalence comparison — it is a function of the packet, so it checks retrieval was not perturbed |
| I-014 | `detail` scalars-only is now a real CHECK over an `IMMUTABLE` helper; a subquery is invalid, a function is not |

Round 5, 16 issues, all accepted. ⚠ Three of the four highs were **created by round 4's own fixes** —
local repairs kept producing new interactions, which is a property of the artifact, not of the critic.
The loop stops here by the house rule that the target is disposition, not zero issues (the same
posture as `SPEC-nexus-tenant-read-scope`: 36 accepted, 7 deferred).

| | disposition |
|---|---|
| I-001 | transaction boundary stated — `search_log` commits **first**, the span batch runs in its own transaction. Sharing one would roll the parent back and make the registered failure test unpassable |
| I-002 | `diversify` added as a fourth carve-out to the row-count invariant; it is cap-exempt, so `LEAST()` does not apply to it |
| I-003 | **`span_write_ms` dropped.** It had no write path that survived the I-007 fix. Cost is counted from the span rows themselves |
| I-004 | equivalence excludes **every** answer-derived column (`n_citations`, `unverified_citations`, `unverified_numbers`), not just the token counts |
| I-005 | graph findings get no candidate rows and are counted in `detail` only, so the packet row count cannot disagree |
| I-006 | a leg that errored writes `fired=false`, same as non-leg stages; `fusion_channels` counts channels **dispatched** |
| I-007 | the BM25 side of the constructed case is made **empty by construction** rather than out-ranked — a pool position is a property of `ts_rank_cd` and the tokenizer, which is the fragility the stub embedder exists to avoid |
| I-008 | the second blind path narrowed to the cases that actually have it — backfill of never-embedded chunks, and an offline model or dimension change |
| I-009 | the CHECK also constrains the top-level type (`jsonb_each` raises on a non-object); the `CREATE OR REPLACE` limit on the guarantee is stated |
| I-010 | **`spans.enabled` now defaults to `false`.** Capture must not begin accumulating the fingerprint corpus before §7 chooses the window that bounds it |
| I-011 | truncation stated as "keeps ranks 1..cap, discards the tail" |
| I-012 | `index_generation` sourced from the latest `index_generation_events` row for the tenant, stored verbatim, NULL when none declared |
| I-013 | the `answer` span's `n_in`/`n_out`/`candidates_cap` defined |
| I-014 | the worst-case arithmetic corrected to 255 with today's values, and the cap's binding condition stated |
| I-015 | the FP1 claim softened — it has a **path**, not a proven delivery; this repository's own history is a detector that reached no consumer |
| I-016 | **the replay harness is gone.** Cost is counted from rows already written; a benchmark rig beside a capture unit was scope creep |

⚠ **Superseded by the above**: round 3's `I-007` and round 4's `I-012` describe `span_write_ms` and
the replay harness, both removed here. Those rows record what was decided then, not what stands.

## 7. Decisions taken at sign-off

| | decision |
|---|---|
| **Retention window** | **Option 2 — 3 days.** `chunk_rid` is kept, so Unit 2 retains chunk-level attribution and the correlation exposure is bounded by time rather than by resolution. The window can widen once volume is known; discarded rows cannot come back |
| **Capture** | **Stays off.** `spans.enabled` ships `false` and is not turned on by this unit. Turning it on is a separate, explicit act |

⇒ **Merging this unit accumulates nothing.** The tables, the writer, the purge and the tests land
dark. That is deliberate: it lets the schema, the constraints and the destructive path be exercised
in CI before a single production row exists, and it separates *does the capture work* from *do we
want the capture running*. The second question is answered later, with the first one already
settled.

⚠ **Consequence for §1.4.** The cost figure is counted from the fixture query set only — no live
rows will exist. A live number is available when capture is turned on, and not before.
