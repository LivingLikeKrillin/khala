---
id: SPEC-nexus-embedding-cutover-seam
type: spec
title: The embedding cutover seam is half-built - the query path, the write path,
  and the wiring still hardcode the old generation
status: approved
linked_adrs:
- ADR-0008
tags:
- nexus
- search
- embedding
- migration
- cutover
date: '2026-08-04T13:28:28Z'
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-04T18:20:03Z'
content_hash: sha256:9e4df9de383c660abd457a7594a695f677af8b875c26928d76369cacecb75f8b
---

# The cutover seam is half-built — make the flip actually be a flip

## 1. Goal

`SPEC-nexus-kure-embedding-swap` §4.5 says the cutover is "a config flip once all of these hold",
and §4.2 says "`search.embedding_column` (config) decides which one queries read. Rollback is that
one setting, not a restore." **On the deployment as it stands today that is false**, and it fails in
the worst available shape: quietly during the migration, loudly at the moment the migration
finishes.

Measured on the dogfood deployment, 2026-08-04 — tenant `default`, **169 chunk rows, 167 active, 0
quarantined** (the two inactive rows are soft-deleted; every count below names its denominator):

1. **The query path never reads the model setting.** Every production construction site is
   `EmbeddingService()` with defaults — `nexus/api.py:285` (`/search`), `:378` (`/search/answer`),
   `:770` (streaming), `nexus/a2a/server.py:303`, `nexus/cli.py:221`, `nexus/ingest/pipeline.py:243`
   — and the defaults are `model="nomic-embed-text"`, `dimensions=768`, `backend=ollama`. Two greps
   over `nexus/` (attribute and `get("embedding.…")` forms; subscript forms) found no reader of the
   `embedding:` block of `config.yaml`; their only hits are an Ollama **response** key
   (`providers/embedding.py:138`) and `search.embedding_column` (`search/hybrid.py:379`). **Two
   greps are evidence, not proof of an absolute negative** — so §4.1 does not rest on it: a
   surviving `embedding.dimensions` that disagrees with the model is refused rather than ignored.
   The positive fact is certain: the six sites pass no config, so
   `search.embedding_column: embedding_1024` moves the column and leaves the query vector at 768
   dimensions.
2. **pgvector refuses the pair.** Verified in psql against the deployment DB:
   `SELECT (array_fill(0.1::real, array[768]))::vector <=> (array_fill(0.1::real, array[1024]))::vector`
   → `ERROR: different vector dimensions 768 and 1024`.
3. **The failure arrives late.** `_vector_search`'s SQL filters `WHERE c.<col> IS NOT NULL`. While
   `embedding_1024` is empty the predicate matches zero rows, the operator is never evaluated, and a
   flipped-but-not-re-embedded deployment looks healthy while returning **keyword-only results with
   no signal that it is doing so**. The error starts the moment the re-embed fills rows — at the end
   of the migration, on live traffic.
4. **And it takes search down rather than degrading it.** `hybrid.py:107-111` wraps only
   `embed_query` in `try`; the `db.fetch_all` below it is unguarded, the exception propagates through
   `asyncio.gather`, and `/search` returns 500. Swap SPEC §5 promises "the vector leg returns nothing
   and the keyword leg still answers. Search degrades; it does not error." That promise is not
   implemented.
5. **The write path is hardcoded to the retired generation.** `nexus/index/embed.py:47` and `:94`
   both write `SET embedding = $1::vector`. After a cutover every newly ingested chunk fills the old
   column and leaves `embedding_1024` NULL — invisible to the vector leg, with nothing raising.
6. **Nothing routes the app to the sidecar.** No `EMBED_URL`, no `EMBEDDING_BACKEND` in
   `docker-compose.yml`, its override, or `.env.example`.
7. **`EMBED_REVISION` is empty** — the running sidecar's `/health` reports `"revision":
   "(unpinned)"` (alongside `dim: 1024`, `max_seq_length: 8192`), while compose's own comment says
   "컷오버 전에 반드시 채운다 (§4.4)". An unpinned checkpoint means the vectors in the column and the
   vectors a later query produces can come from different weights, with no dimension change to
   reveal it.
8. **`/status` names the wrong dependency.** `nexus/api.py:1046` reports `ollama_connected`
   unconditionally. After a cutover the health signal an operator reads describes a service the
   search path no longer uses.
9. **And the flip has nowhere safe to be written.** `docker-compose.yml:132` mounts `.:/app`, so the
   dev/dogfood deployment reads `config.yaml` **out of the git working tree**; the prod overlay
   `!override`s volumes and bakes it into the image. Flipping today means either an uncommitted edit
   to a tracked file that `git checkout` silently reverts, or an image rebuild. Neither is a cutover
   procedure (§4.2).

The goal is not to re-decide anything. It is that **the flip the swap SPEC described can be
performed at all**, and that its failure modes are visible where the decision is made instead of
silent until traffic finds them.

### 1.1 Gate record

**Authority.** `SPEC-nexus-kure-embedding-swap` is `approved` by **LivingLikeKrillin** (2026-08-04,
`linked_adrs: [ADR-0008]`) and defines the cutover as its Unit 4. This SPEC implements that unit and
repairs defects found in that SPEC's Units 1–3. It fires no gate of its own.

**ADR-0008 re-read (§5 backstop) — an embedding-model change is one of the named backstop events, so
this is that re-read.** ADR-0008 §6 records that the Korean measurement gap "blocks three separate
decisions: mecab-ko retention, an embedding-model change, and resume condition (b)"; §2.6 records
that no instrument existed. What is true now:

- An instrument exists, **for a public stand-in corpus only**: Pack A (`kubernetes/website` Korean
  docs, 265 files at commit `b035ea80`), 45 labels, pre-registered verdict rule
  (`SPEC-nexus-korean-retrieval-eval`, approved 2026-08-02). On it, `Recall@10` was **0.402
  (nomic-embed-text) vs 0.975 (KURE-v1)** exact-scan (40 answerable queries, label revision 2,
  tenant `ko_eval`; sign test on the comparable subset 27–1–8, p ≈ 2 × 10⁻⁷,
  `nexus/tests/eval/reports/2026-08-04-nomic-vs-kure.md`) and **0.777 vs 0.988** through the
  production ivfflat path, per-arm exact→ANN deltas +0.000 / −0.000
  (`2026-08-04-ann-vs-exact.md`, which carries its own retraction of a poisoned first run). Both are
  **lower bounds under an incomplete pool**, as those reports say.
- **Resume condition (b) is not closed and this SPEC does not claim it is.** (b) requires a set that
  compares on *khala's real corpus*; Pack B does not exist and the live corpus is unlabelled.

**Directorial declaration (ADR-0008 §3(3): a gate is declared fired by the director and recorded,
not argued into existence by the SPEC).** On **2026-08-05**, **LivingLikeKrillin**, asked directly
whether approving the swap SPEC lifts §6's embedding-change block given that the evidence is
stand-in-corpus evidence and (b) remains open, declared that **it does**: §6's block existed because
no instrument existed at all, one now exists, its margin is large, and (b) is the higher bar
belonging to reopening Onyx adoption rather than to this swap. The alternative — leaving the swap
undone — keeps a configuration that violates `nexus/CLAUDE.md` rule 9 (no English-only embedding
model in a Korean-first system). Conditions (a) and (c) are untouched; Onyx adoption stays deferred.

**Two things about that declaration, said plainly rather than smoothed over.** First, it **narrows
a condition the ADR stated more broadly**: §2.6 frames the gap as the absence of an instrument that
compares *on khala's corpus*, and the instrument that exists compares on a public stand-in. That
narrowing is the **director's**, made with the difference in front of them, not a reading this SPEC
performed on the ADR's behalf. Second, it is **retrospective for the swap SPEC and prospective for
this cutover**: the swap SPEC was approved 2026-08-04, one day before the declaration, so the
decision it records was taken before the gate was declared fired. The correct order would have been
to declare first; it was not followed, and recording that here is the repair available now. The
re-read itself happened at the start of *this* work rather than at the start of the swap SPEC's —
also later than §5 asks.

**One inconsistency found while re-reading, not fixed here.** ADR-0008's frontmatter is
`status: accepted`, `approved_by: LivingLikeKrillin`, `reviewed_at: 2026-08-01T14:09:35Z`, and
`INDEX.md` lists it as approved, but its body §Status still reads "**In review.** Binding on
acceptance." The ledger is the record of approval, so the body line is stale. It is not corrected
here for a reason that is itself governance: **editing an approved artifact's body invalidates its
stamped `content_hash`**, and Arbiter has no amend verb — the fix is a re-record and re-approval of
ADR-0008, a governed action of its own that must not ride along inside an implementation SPEC.
Until it lands, this SPEC's authority rests on the ledger's stamp and on the director's declaration
above, both of which are records rather than readings.

The same stand-in limit governs §4.6's latency budget: measured on this deployment, binding on this
deployment's flip, generalisable to nothing.

## 2. Non-goals

- **Not a model decision.** No new retrieval-quality measurement; the reports above stand.
- **Not a provider registry** — no plugin surface, no per-tenant model, no runtime switching.
- **Not the removal of `embedding`.** The blue-green window and the rollback path stay.
- **Not dual-write** (§4.3 — refused, cost bounded by a reported number).
- **Not per-row embedding provenance.** Binding each stored vector to the checkpoint revision that
  produced it (a `chunks.embed_revision` column, a backend `identity()`, a re-embed verb that can
  rewrite non-NULL rows, a cutover condition over revisions) is a **provenance subsystem, deferred
  to its own SPEC**. This SPEC pins the revision (§4.5) and makes `reembed status` compare the
  **running** sidecar's reported revision against the pinned one, which is what keeps a
  mid-migration checkpoint change from passing unnoticed; it does not build per-row history.
  Triggers for that SPEC: a re-pin after a column is populated, a second model, or a deployment
  that must answer "which weights produced this row" for an individual row.
- **Not a chunking change.** The sidecar rejects over-length input (413) rather than truncating.
  Whether that fires here was **measured, not argued from units**: the longest active chunk in the
  live corpus (3,795 characters) embedded successfully through the sidecar, returning a 1024-d
  vector (2026-08-04). `max_seq_length: 8192` is a token limit and the corpus's character-to-token
  ratio is not assumed anywhere; if a future chunk does trip the limit, it is a counted failure and
  the existing waiver path handles it.
- **Not observability infrastructure.** The line, stated as a principle and bounded by a number:
  **what the cutover decision and its failure modes require to be readable at the moment of decision
  ships** (`/status` fields, run output, a log line); **the time series does not** — persisting
  degraded legs to `search_log`, rates, windows, thresholds and alerting are deferred with their own
  gate. The bound that makes this checkable rather than rhetorical: **`/status` gains exactly two
  additional aggregate queries** — one `GROUP BY tenant` over `chunks` (active, embedded per column,
  pending) and one over `embed_waivers` (the waived count, which lives in that table and so cannot
  come from the first) — and a test asserts that count, so "one more field" cannot quietly become a
  per-tenant fan-out.
- **Not the correction of `KOREAN_SEARCH_QUALITY.md` §6**, whose first row still lists the retracted
  "ivfflat eats KURE's recall" finding as open. One-line fix, its own change.

## 3. What exists, and what must move

| Concern | Today | After |
|---|---|---|
| Which column is read | `search.embedding_column`, whitelisted (`vector_index.py`) | same, plus an env override, same whitelist |
| Which model embeds the query | hardcoded default at 6 sites | one factory, config + env |
| Which column is written on ingest | hardcoded `embedding` | the configured column |
| Which column the re-embed writes | `--column`, default `embedding_1024` | explicit, never from config (§4.3) |
| model / column / backend disagreeing | undetectable until a row exists | refused at construction |
| Configured column empty or partial | invisible | logged at startup, counted on `/status` |
| Vector-leg data error (dimension) | 500 | empty leg, keyword answers, flagged |
| Any other vector-leg failure | 500 | 503 (the existing rule, made explicit) |
| App → sidecar route | absent | `EMBED_URL` + backend setting |
| Checkpoint revision | unpinned | pinned in compose, reported by `/health` and in the record |
| Where a flip is written | a tracked file or an image rebuild | deployment env |
| Which generation is live | not exposed | `/status` |

## 4. Design

### 4.1 One factory, and the dimension is a fact about the model — checked, not trusted

`EmbeddingService` already owns the per-model prefix policy (`MODEL_PREFIXES`) and refuses unknown
models. It gains the other facts of the same kind:

```python
MODEL_DIMENSIONS: dict[str, int] = {"nomic-embed-text": 768, "KURE-v1": 1024}
MODEL_BACKENDS:   dict[str, str] = {"nomic-embed-text": "ollama", "KURE-v1": "sidecar"}
```

`MODEL_BACKENDS` records **how each model is served in this system today**, not a property of the
models: a GGUF conversion of KURE served through Ollama is possible and would be refused by this
table. That friction is intended — the conversion is precisely the unpinned step swap SPEC §4.1
refused — and the escape is a code change with a test, not a config key, because the alternative is
the provider registry §2 rules out.

and a single construction path used by every production site:

```python
def embedding_service_from_config(cfg: dict) -> EmbeddingService
```

reading the model, the backend and the prefix keys `resolve_prefixes` already honours, with the
dimension taken **from `MODEL_DIMENSIONS`, not from config**. `embedding.dimensions` is removed from
the shipped `config.yaml`, and a surviving key that **disagrees** with the model's dimension is
refused at construction with both values named — so the design does not depend on §1.1's
unprovable negative, only on the fact that a disagreement cannot pass silently.

**The table is an assumption until a vector is counted against it.** Every vector a backend returns
is length-checked against `MODEL_DIMENSIONS[model]` before it is stored or used in a query; a wrong
length raises, naming model, expected and received. A Matryoshka-truncated output, a mis-configured
sidecar, or a checkpoint whose head changed all land here instead of arriving as a swallowed
pgvector error.

Absent config keys keep today's behaviour (`nomic-embed-text`, `ollama`): a deployment that changes
nothing sees nothing change.

### 4.2 Three settings, one place to move them, and a partial move that cannot construct

**Three** values must agree: model, column, backend — KURE-v1 is not served by Ollama and
nomic-embed-text is not served by the sidecar. Each gets an environment override, because §1.9 shows
config-file editing is not available as a deployment mechanism here:

| setting | config key | env override |
|---|---|---|
| model | `embedding.model` | `NEXUS_EMBEDDING_MODEL` |
| column | `search.embedding_column` | `NEXUS_EMBEDDING_COLUMN` |
| backend | `embedding.backend` | `NEXUS_EMBEDDING_BACKEND` (legacy `EMBEDDING_BACKEND` still read, prefixed wins) |

The three cutover variables share the `NEXUS_` prefix deliberately — a `.env` is shared with other
software, an unprefixed `EMBEDDING_BACKEND` collides and mistypes into the odd one out, and
`EmbeddingService` already reads the unprefixed name, so it stays supported rather than silently
ignored. `EMBED_URL` / `OLLAMA_URL` keep their names: they are **endpoints**, while `backend` names
a **protocol kind** (`ollama` | `sidecar`) — the distinction that decides that the two settings can
legitimately vary independently (a second sidecar host is a URL change, not a backend change).

**The env boundary is one container.** On this deployment every construction site of §1.1 lives in
`nexus-app`: the API and the A2A routes are the same process (`api.py` mounts them; compose has no
separate a2a service), ingestion runs as `docker exec nexus-app nexus ingest`, and the CLI is run
the same way — so `docker compose up -d nexus-app` moves all of them at once. A process started
outside that container (a host-run CLI, a future worker service) is **not** covered and must carry
the same three variables; `/status` and the factory's startup log make the effective triple
readable, so a stale process is discoverable rather than theoretical. That is the invariant this
procedure depends on, stated so a deployment that breaks it knows it broke it.

**Env wins over config**, resolved once at construction, with the effective triple and the source of
each value logged — so "what is this process actually running" is a log line, not a reconstruction.
The column value goes through the existing `resolve_column()` whitelist whether it came from config
or env, so a typo is refused rather than interpolated. The flip is therefore three lines in a
deployment's `.env` plus a restart on both deployment shapes, and rollback is the same three lines
back; repository files never change and the repository default stays the old generation.

**The dimension the check uses is a name-to-number table, and that has a limit worth naming.**
`VECTOR_COLUMNS` maps `embedding_1024 → 1024`; nothing at construction reads the column's *declared*
type, so a column altered to a dimension its name does not describe would pass. Reading
`pg_attribute.atttypmod` needs a database and construction has none (below), so the check goes where
a database is already open and a decision is attached: **`nexus reembed status` and
`create-index` verify the declared dimension against the table and refuse on disagreement**, which
is before any flip. The runtime guard (§4.4) remains the floor under both.

The three stay separate settings — deriving the model from the column would let the config *say* one
model while the code used another — and a contradiction is refused with all three named:

```
embedding generation is inconsistent: model='nomic-embed-text' (768d, expects ollama) ·
column='embedding_1024' (1024d) · backend='sidecar'.
A cutover moves all three; this deployment moved one.
```

**The check lives in the factory**, not in `api.py`'s startup hook: `a2a/server.py` and the ingest
path construct their own services, and after §4.3 the ingest path *writes* vectors — a check that
only guarded the API would leave the one process that can write wrong-generation rows unguarded.
`api.py:78`'s startup path calls the factory eagerly so the API refuses to serve rather than failing
per-request.

**Coverage is reported, not enforced at boot.** An empty configured column raises nothing (§1.3), so
it needs its own visibility — but a boot refusal is the wrong instrument: a NULL vector is an
ordinary transient (a chunk inserted and not yet embedded, a crashed ingest, a 413 awaiting a
waiver), a brand-new tenant's first ingest legitimately sits at zero coverage, and any of those
would then take the whole deployment down at the next restart. The construction path also has no
database handle, and a check that needed one would make the API's boot depend on a query that
migrations may not yet allow. So:

- **At startup** (in the API's existing async startup, which already has a pool), one log line per
  tenant with `embedded / active / waived / pending` for the configured column, at **error level
  when a tenant has active chunks and zero vectors** — the "flipped before re-embedding" shape — and
  at warning level for partial coverage.
- **On `/status`**, the same numbers per tenant for **both** columns, so the state is answerable
  without reading logs, and so §4.3's rollback gap is a number.
- **Enforcement lives at the cutover**, where the operator is: the conditions of §4.6 must hold for
  every tenant with chunks before the flip. That is a check with a decision attached, which is what
  makes it the right place — a permanent runtime assertion has no decision attached, only an outage.

### 4.3 The write path follows the setting; the re-embed tool never does

`index_chunk_embedding` / `index_chunks_embedding` write the configured column via
`resolve_column()`, whitelisted the same way the read path is, never interpolated from raw config.

**The re-embed tool is the exception, deliberately.** `nexus reembed run --column` is explicit and
**never derived from the configured column**: during a cutover the configured column is still the
old one, so a config-following re-embed would aim the migration at the column it must preserve. Two
invariants make a mis-aimed run harmless, both asserted by tests:

1. **The queue is NULL rows only** — a run can never overwrite an existing vector, so the rollback
   target cannot be damaged by re-running anything.
2. **`--column` and `--model` must agree dimensionally**, refused before the first row is read.

`run` and `status` also take **`--all-tenants`**, which enumerates the tenants that have chunks and
loops, because §4.6's conditions are per tenant and an operator enumerating them by hand is how a
tenant gets missed.

**Dual-writing both columns during the blue-green window is refused.** It would double every
ingest's embedding cost, require both backends up for any ingestion to succeed, and make "which
generation is this chunk" unanswerable per row. The cost of refusing it: **rollback is a true
restore only for the corpus as it stood at the flip** — chunks ingested after the flip have a NULL
`embedding` and would be keyword-only under a rollback. That gap is **bounded by a number the
operator reads before deciding**: `/status` (§4.2) and `nexus reembed status --column embedding`
report the pending count for the *other* column per tenant, so "rolling back drops N of M chunks to
keyword-only" is a query, and the remedy is the same tool pointed the other way
(`nexus reembed run --column embedding --model nomic-embed-text --all-tenants`).

### 4.4 The vector leg degrades on a data error — everything else still 503s

`nexus/CLAUDE.md`'s rule is specific — "DB 연결 실패: 503. partial result 반환 금지" — so what is
forbidden is answering *around a dead database*, not degrading one leg: swap SPEC §5 requires
exactly that degradation for an absent embedding backend, and the two rules do not collide once the
difference is stated. **The database is the substrate both legs stand on; the embedding backend
serves one leg.** When the substrate is gone, no answer is trustworthy and the request must fail
loudly. When one leg's server is gone, the other leg's answer is still grounded — worse, and marked
as worse, but not wrong.

The split is therefore deliberately **narrow**, and the tie goes to 503 — a false 503 is a visible
outage, a false degradation is a silently worse answer, and this codebase has paid for the second
kind twice, both recorded: the retrieval order that varied between reloads of the same corpus
(`KOREAN_SEARCH_QUALITY.md` §3.1 → `SPEC-nexus-deterministic-retrieval-order`) and the ANN
measurement that read constant vectors a test had written (§3.5, retracted in PR #155).

- **Degrade** (empty leg, marked, logged at error): `asyncpg.exceptions.DataError`. **Verified on
  the client path, not assumed** — the dimension mismatch surfaces as
  `asyncpg.exceptions.DataError`, SQLSTATE `22000`, message `different vector dimensions 768 and
  1024` (run through asyncpg from inside `nexus-app`, 2026-08-04). This is the class that is a
  property of *this query's vector*, cannot be fixed by retrying, and must not take search down.
  The class is broader than that one fault — a query-construction bug in the vector leg would land
  here too — which is why the degradation logs at **error** level with the SQLSTATE and is asserted
  by §6's tests: a construction bug is caught by tests and a loud log, whereas a live 500 is caught
  by users.
- **Propagate** (503, unchanged): everything else, explicitly including connection loss, pool
  timeout, `QueryCanceledError` / statement timeout, and `InsufficientPrivilegeError`. A statement
  timeout under load and a missing GRANT are health signals about the deployment, not per-query
  faults, and hiding them behind keyword-only results is the failure shape §1 exists to remove.

The classifier is one function over exception types with a table-driven test, so the split is
reviewable in one place rather than scattered across `except` clauses.

`SearchResult.degraded: list[str]` carries the failed legs, values asserted against the leg registry
(`"bm25"`, `"vector"`, `"graph"`), and each degradation logs the column and exception type.
Persisting it is deferred (§2).

### 4.5 Wiring and pinning

- `docker-compose.yml`: `nexus-app` gets `EMBED_URL: http://nexus-embed:8080` and the three
  overrides of §4.2 **as interpolations with defaults, never as literals**:
  `NEXUS_EMBEDDING_MODEL: ${NEXUS_EMBEDDING_MODEL:-nomic-embed-text}` and the same shape for the
  column and the backend. This is load-bearing, not stylistic: `.env` only feeds compose
  *interpolation*, so a literal `environment:` value would win over the deployment's `.env` and the
  §4.6 procedure would leave the process on the old generation while every consistency check passed
  — a flip that reports success and changes nothing. §6 tests the compose-to-process precedence by
  reading the effective triple out of a container started with an `.env`, not by reading the file.
  **No `depends_on`** — verified, not assumed: a
  compose project whose enabled service depends on a profile-gated one fails with
  `service "a" depends on undefined service "b": invalid compose project` (Compose v2, this machine,
  2026-08-04). §4.4's degradation path covers an absent sidecar, and it is now real.
- **`EMBED_REVISION` is pinned** to the resolved commit of `nlpai-lab/KURE-v1`, read from the
  running sidecar's resolved snapshot and written into compose as the default **before the re-embed
  starts**, so the vectors in the column and every later query vector come from one checkpoint. And
  the pin is **checked, not just declared**: `nexus reembed status` compares the running sidecar's
  `/health.revision` against the pinned value and refuses the cutover when they differ or when the
  sidecar reports `(unpinned)`. And the pin is a **mechanism, not a claim** — §6 sets
  `EMBED_REVISION` to a known commit, restarts the sidecar, and asserts `/health.revision` equals
  it, because "unpinned reports `(unpinned)`" only proves the negative case.
  **The remedy when the check fires** is named, because a detection without one is a permanently
  blocked cutover: **re-pin the sidecar to the revision the populated rows came from** and restart
  it — that revision is knowable because the pin is set before the run and only changes by human
  action, so the previous value is in compose's history. Moving the *column* to a new checkpoint
  instead means re-embedding rows that already have vectors, which invariant 1 of §4.3 forbids by
  design; that is exactly the deferred provenance SPEC's trigger (§2), not something this SPEC
  smuggles in through a flag. Reconstructing *which* rows came from which checkpoint likewise
  belongs there.
- **`/status`** adds `embedding_model`, `embedding_column`, `embedding_backend`,
  `embedding_backend_connected`, `embedding_revision`, and the per-tenant coverage of §4.2.
  `embedding_revision` is **sidecar-only by definition** — the sidecar's `/health.revision`, and
  `null` on the Ollama path, documented as such. (Ollama does expose a model digest, but reporting
  it would be provenance for the generation this cutover retires — the non-goal of §2 — so the
  field's contract is "the pinned checkpoint when one exists, null otherwise".) The two probes this
  requires (`/health`, and Ollama's existing check) carry a **2-second timeout and return `null` on
  timeout**: `/status` is what an operator reads *while the sidecar is starting*, so it must never
  block on it. `ollama_connected` keeps its present meaning — Ollama's reachability, reported
  whether or not it is the embedding backend — so no existing consumer breaks, and the new field is
  what says whether the backend actually in use is up.
- **The caller is told, not just the log.** `SearchResult.degraded` is surfaced in the `/search` and
  `/search/answer` responses (and the streaming path's final event) as a `degraded` list. §1.3's
  defect is that a degraded deployment "looks healthy" *to whoever is asking*; a field that exists
  only inside the process does not close that, and the web surface already renders trust signals
  that this can join.

### 4.6 The cutover procedure this makes possible

The four conditions (swap SPEC §4.5's), printed by `nexus reembed status`, **for every tenant that
has chunks**:

1. Every active, non-quarantined chunk is accounted for — a non-NULL vector in the target column or
   a signed `embed_waivers` row.
2. Zero unwaived failures in the run summary.
3. `embed_health` (`nexus/index/embed_health.py`, which reports the distribution of
   `chunks.embed_model` under the vector index's partial predicate) reports **one distinct
   `embed_model`** among non-NULL rows **of the target column** — i.e. `mixed = false`. With
   per-row revision provenance deferred (§2), "generation" means exactly that: the model name the
   rows were written with, which is the fact the column actually holds.
4. The ANN measurement of swap §4.6 is run and recorded (done: `2026-08-04-ann-vs-exact.md`).

**Ingestion during the window is the one race the design does not close by itself**, so the
procedure closes it. While the re-embed runs, config still names the old column, so §4.3's write
path fills `embedding` and leaves `embedding_1024` NULL for anything newly ingested; the completed
run will not pick those rows up, because its queue was NULL-at-the-time. They would become
vector-invisible the moment the flip lands. Hence: **no ingestion runs during the window** (an
operator step, and on this deployment ingestion is manual or scheduled, not continuous), and — since
"no ingestion" is a promise and promises are not invariants — **a second re-embed pass immediately
before the flip**, whose output is the evidence that nothing arrived meanwhile.

```bash
# EMBED_REVISION pinned in compose first (§4.5); ingestion paused for the window
docker compose --profile embed up -d nexus-embed
nexus reembed run --column embedding_1024 --model KURE-v1 --all-tenants   # --column is explicit
nexus reembed create-index --column embedding_1024                        # lists sized after the run
nexus reembed run --column embedding_1024 --model KURE-v1 --all-tenants   # second pass: must be 0
nexus reembed status --column embedding_1024 --all-tenants                # four conditions + the pin
# then, in the deployment's .env — not in a tracked file, not in the image:
#   NEXUS_EMBEDDING_MODEL=KURE-v1
#   NEXUS_EMBEDDING_COLUMN=embedding_1024
#   EMBEDDING_BACKEND=sidecar
docker compose up -d nexus-app
nexus reembed status --column embedding_1024 --all-tenants                # after the flip, for the record
```

A non-zero second pass means something was ingested during the window: it is embedded by that pass,
and `create-index` is re-run if the row count moved enough to change `lists`. The final `status`
after the restart is what the operator record cites, because the state that matters is the one the
flipped process sees.

**The residual window is named rather than claimed closed.** Between the second pass and the
restart, an ingest could still write `embedding` and leave `embedding_1024` NULL. That window is
(i) short and operator-controlled, (ii) **detected** — the post-restart `status` reports a non-zero
pending count for the new column, which is why that command is in the procedure rather than
optional, and (iii) **self-healing**: after the flip the write path writes the new column, so one
more `reembed run` fills exactly those rows and nothing else. What the design does not do is *lock*
ingestion; a lock is a mechanism this SPEC would have to build and defend, and the same guarantee is
reached here by a check plus a bounded repair.

**Rollback is those three env lines back plus a restart** — seconds on either deployment shape —
with §4.3's bounded gap. The repository default stays `nomic-embed-text` / `embedding` / `ollama`.

### 4.7 The latency debt, with a pass/fail rule fixed before the numbers

Swap §4.1 withdrew its own latency table — the KURE figure was in-process, the shipped path is a
sidecar — and wrote that it is "replaced with that number **before any cutover decision**"; §4.6
owes p50/p95 of the query embed and of end-to-end `/search`, before and after. Neither exists. This
SPEC pays it on the real path, with the rule fixed first:

- **Query embed**: p50/p95/max, nomic via Ollama and KURE-v1 via the sidecar, **both over HTTP from
  the app's process** — the same kind of measurement on both sides, which the withdrawn table was
  not.
- **End-to-end `/search`**: the **same fixed query set before and after**, and the set is
  **committed, not sampled from the corpus** — `nexus/tests/eval/latency_queries.yaml`, ~20 Korean
  and mixed-script technical queries written for this purpose. Sampling the live corpus would make
  the set undistributable (this repository is public and the corpus is real organisational
  material), unverifiable by a reviewer, and unstable across the re-embed window during which
  ordinary ingestion changes the corpus. A committed set is reproducible by anyone and identical by
  construction on both sides of the flip.
- **N = 200 requests** after 20 discarded warm-ups (a p95 from 30 samples is the second-worst
  observation, with an interval wider than any difference worth acting on), reported as
  min/p50/p95/max with the count.
- **"Before" has one defined moment**: immediately **after** the re-embed and `create-index` and
  **immediately before** the env flip, so the only difference between the two readings is the flip
  itself. (A reading taken before the re-embed would fold the new index's construction into the
  delta, and the rule's multiplier would be measuring a different thing each time it was applied.)
  A pre-re-embed reading may be recorded as background; it is not what the rule is evaluated on.
- **Pre-registered rule**: the flip stands only if **`/search` p95 after ≤ 1.5 × p95 before and
  ≤ 1500 ms absolute**. Failing either, the flip is reverted in the same session and the report says
  why. Naming the rule now is the point; naming it afterwards would be choosing the conclusion.
- The report records corpus size and chunk counts **before and after** (so corpus drift across the
  window is visible rather than assumed absent), the `lists` value of **both** indexes, machine,
  backend, and the pinned revision.
- **What this comparison is, and is not.** It is a **budget guard on the deployment**: everything
  that changes at the flip — model, backend, HTTP hop, a newly built index sized after the re-embed
  — changes together, by design, because that bundle *is* what production will run. It is **not a
  controlled experiment attributing latency to the model**, and a pass or a fail must not be
  reported as one. Attribution would need the index geometry and the corpus held fixed across arms,
  which the cutover cannot do without building a second measurement environment — the ANN report
  already did that for *recall*, and latency does not carry the same decision weight.

**Two limits.** (i) **The report carries no corpus content**: the query set is committed and written
by hand, and the report renders a fixed aggregate record — counts, percentiles, identifiers — so
there is no path from a document to the file. This is a property of *this* report's inputs, claimed
no more broadly. (ii) **169 rows is a small corpus.** At this size `lists=1` makes the index a scan
and fixed overheads dominate: the numbers are *this deployment's* budget for *this* rollback
decision and predict nothing about a production-scale corpus — the same limit ADR-0008 §2.6 records
for a tiny fixture. A larger corpus re-measures and registers its own rule.

## 5. Error handling

- **Sidecar unreachable / unready (503 from the sidecar)** → vector leg empty, keyword leg answers,
  `degraded` carries `vector`, `/status` shows `embedding_backend_connected: false`. No 500.
- **Dimension mismatch reaching SQL** → `DataError` → degraded leg. Unreachable after §4.1 and §4.2;
  the guard is the floor, not the plan.
- **Any other DB failure** → 503 (§4.4).
- **Wrong vector length from a backend** → raised at the boundary naming expected and received; on
  the re-embed path a counted failure, never a stored row.
- **Over-length chunk (413)** → counted failure, blocks the cutover until waived. Unchanged.
- **Unknown model, contradictory triple, disagreeing `embedding.dimensions`, or a column outside the
  whitelist** → refused at construction, values named.
- **Configured column with zero vectors while chunks exist** → error-level startup log and `/status`
  counts; the deployment serves keyword-only rather than not serving.

## 6. Testing

Unit, no DB:

- The factory returns today's defaults for a config with no `embedding` block, the configured values
  when present, and each env override beats its config key with the source recorded in the log line.
- `MODEL_DIMENSIONS` and `MODEL_BACKENDS` cover every model in `MODEL_PREFIXES` — asserted over the
  registry, so adding a model without its dimension fails a test rather than a deployment.
- Contradiction: `(nomic, embedding_1024, *)`, `(KURE-v1, embedding, *)`,
  `(KURE-v1, embedding_1024, ollama)` each raise with all three values in the message; the two
  coherent triples pass. A disagreeing `embedding.dimensions` raises. A column outside the whitelist
  raises whether it came from config or env.
- A backend returning a wrong-length vector raises, naming expected and received.
- `--column` / `--model` disagreement in the re-embed CLI is refused before any row is read.
- The classifier: a table of asyncpg exception types → `{503, degrade}` asserted exhaustively,
  including `QueryCanceledError`, pool timeout and `InsufficientPrivilegeError` on the 503 side, and
  `DataError` (SQLSTATE `22000`) on the degrade side.
- `SearchResult.degraded` legal values match the leg registry; default empty.
- The latency report renders exactly its aggregate record's fields.

Against Postgres:

- **The 500 regression, asserted directly**: with a query embedding of the wrong dimension, the
  vector leg returns empty, `hybrid_search` returns BM25 hits, and `degraded == ["vector"]`. The
  test that would have caught today's state.
- A connection-level failure and a statement timeout still 503 — §4.4's boundary from both sides.
- The write path writes the configured column: ingest under `embedding_1024` leaves `embedding`
  NULL and vice versa, asserted by reading the columns, not by reading config.
- Startup coverage logging: zero-vector tenants log at error and appear on `/status`; partial
  coverage logs at warning; a chunk-less install logs neither; **none of them refuses to boot**.
- `--all-tenants` covers every tenant that has chunks, including one created after the run started
  being written (it is simply not covered, and `status` says so).
- After a flip, a chunk ingested post-flip has NULL in the old column and `reembed status --column
  embedding` counts it — §4.3's gap, asserted so the rollback number is measured rather than hoped.
- `/status` reports the generation, the in-use backend's reachability, and per-tenant coverage for
  both columns — in **one** added aggregate query, asserted by counting queries (§2's bound).
- `reembed status` and `create-index` read the target column's declared dimension from the catalog
  and refuse when it disagrees with `VECTOR_COLUMNS`; `reembed status` refuses when the running
  sidecar's revision differs from the pinned one or reports `(unpinned)`.
- A chunk ingested between a completed re-embed and the flip is caught by the second pass, and the
  second pass reports zero when nothing was ingested — §4.6's race, asserted from both sides.

- The `/search` and `/search/answer` responses carry `degraded` when the vector leg failed — the
  caller-visible half of §1.3, asserted on the response body rather than on the internal object.

Against Docker (Unit 3's wiring checks; the repository already runs a docker-backed CI job, so these
run there rather than being a one-off ritual):

- The effective triple read out of a running container matches the deployment's `.env`, proving the
  interpolation form beats a literal — §4.5's precedence trap, checked against a process rather than
  against a file.
- `EMBED_REVISION` set to a known commit, sidecar restarted, `/health.revision` equals it — the pin
  as a mechanism rather than a declaration.

Exploratory (documented, not CI): §4.7's latency runs, with a committed dated report.

## 7. Acceptance

Automatically verifiable (§6):

- Moving all three settings switches **both** the read and the write path, verified against
  Postgres; moving fewer is refused at construction, naming them.
- With the sidecar stopped, and with a wrong-dimension query vector injected, `/search` answers from
  the keyword leg and reports the degradation; a dead database, a statement timeout and a permission
  error still 503.
- Coverage is logged and reported per tenant for both columns, and no coverage state refuses to boot.
- The re-embed refuses a `--column`/`--model` mismatch and covers every tenant under
  `--all-tenants`.

- The deployment's `.env` reaches the process and the pin reaches the sidecar — both asserted
  against running containers in the docker-backed job, not by reading files.
- A degraded vector leg is visible in the API response, not only in the log.

Operator-verified, recorded rather than automated (Unit 4 is an operator action):

- `EMBED_REVISION` is pinned before the re-embed, `reembed status` confirms the running sidecar
  reports it, and the pinned value is in the cutover record.
- The second re-embed pass immediately before the flip reports its count, and the post-restart
  `status` is what the record cites.
- The withdrawn latency table of swap §4.1 is replaced by a measurement over the shipped HTTP path;
  `/search` p50/p95 before and after are recorded with §4.7's rule applied and the decision it
  produced written down — for this deployment, which is the only thing it binds.
- The cutover is performed from deployment env, with a three-line rollback, the repository default
  unchanged, and the post-flip gap reported as a number.

## 8. Units

1. **Generation seam** — `MODEL_DIMENSIONS`, `MODEL_BACKENDS`, `embedding_service_from_config`, the
   env overrides through the existing whitelist, the six call sites, vector-length checks, the
   contradiction refusal in the factory, `embedding.dimensions` removed from the shipped config and
   refused when disagreeing. No behaviour change at default config.
2. **Write path + degradation + visibility** — configured column on ingest, `_vector_search` guarded
   by the classifier, `SearchResult.degraded`, startup coverage logging, `/status` fields.
3. **Wiring + pin** — compose `EMBED_URL` and the three overrides, `EMBED_REVISION` pinned,
   `--all-tenants`, `.env.example` and the deploy runbook.
4. **Cutover run** — the committed latency query set, the measurement script and its dated report
   under §4.7's rule, then the live re-embed, index, status, flip, and the operator record. Each unit
   is separately reviewable and revertible; Unit 4 merges nothing that Units 1–3 have not already
   established.
