---
id: SPEC-nexus-generation-of-record
type: spec
title: Which generation is this corpus on — declare it in the database, because two
  processes reading the same config disagreed and nothing noticed
status: approved
linked_adrs:
- ADR-0006
- ADR-0008
- ADR-0009
tags:
- nexus
- index
- embedding
- ingest
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-11T03:02:28Z'
content_hash: sha256:2a10e043cf3ace75a99327ea8f77e1c77fbfa40c8dab01d7dba221e7d79258ce
---

## 1. What prompted it

[[SPEC-nexus-index-completeness]] surfaced a coverage gap and attributed it to an ingest run whose
*"vector indexing stopped partway"*. **That sentence is wrong**, and §8 records what must happen
to it.

Running the same repository code in two places resolves two different embedding generations:

```
host       column=embedding       model=nomic-embed-text  (768)   source=config
container  column=embedding_1024  model=KURE-v1           (1024)  source=env
```

`config.yaml` still declares the 768 generation as the repository default — deliberately, per the
per-deployment runbook of [[SPEC-nexus-kure-embedding-swap]] — and the deployment overrides it with
environment variables that exist **only inside the container**. The `nexus` CLI is also on the
host's PATH, and the documented commands invite exactly that:

| where | what the docs say |
|---|---|
| `nexus/README.md:294` | a preamble — *"컨테이너 안에서 돈다: `docker compose exec nexus-app nexus <command>`"* — above bare commands |
| `nexus/CLAUDE.md:297-303` | `docker exec nexus-app nexus ingest …` and bare `nexus ingest-notion --roots "…"`, **in the same block, with no preamble** |

README states the requirement once and then writes bare commands under it; `CLAUDE.md` mixes both
forms in one block with nothing distinguishing them, which reads as "the prefix is optional". The
corpus is Notion-sourced, so the command a person actually copies is `ingest-notion` — the bare one.
It ingests into the generation the deployment does not search.

**This account explains every number of the incident; the alternative it replaces does not.** The
51 chunks reported as missing held a 768 vector and no 1024 vector, and a run that stopped would
have left neither. `_save_chunks` nulls `embedding` when a chunk's text changes, the host run
refilled those and stamped its own model name — which is why 119 chunks carry a `nomic-embed-text`
label beside a KURE vector, and why whole small documents carry it while large ones carry it only
on their changed chunks. **It is not proved unique**: a container run that failed partway *followed
by* a host run would leave a similar signature. What is established is that a host-resolved
generation exists, is reachable by a documented command, and accounts for the observations without
any second event.

### 1.1 A third state, measured

`_save_chunks` nulls `embedding` and `tsvector_ko` on a text change and **leaves the other vector
column untouched**. Every re-embed queue is `WHERE <column> IS NULL`. So a chunk whose text changed
keeps a vector for text it no longer has, is never queued to fix it, and `nexus reembed run` cannot
repair it either — for the same reason.

**ADR-0006 declared this bug dead.** Its Consequences read *"'Re-embed only changed' becomes
correct, killing stale-vector retrieval drift"*, and its fix was to null on `IS DISTINCT FROM`.
That fix was written when there was one vector column. Adding a second silently reopened the bug
the record says was closed, and nothing connected the two.

Measured by recomputing every stored vector in the searched column and comparing
(`scripts/check_stale_vectors.py`). **A stored vector counts as stale below cosine 0.9999** — the
threshold is fixed in the script, not chosen after seeing results:

| label carried by the chunk | active chunks | stored vector ≠ current text |
|---|---:|---:|
| `KURE-v1` | 215 | 0 |
| `nomic-embed-text` | 119 | **8** |

Both rows are the **same arm**: every recomputation used the container's KURE service against
`embedding_1024`. The label describes the last writer of *either* column, so a `nomic-embed-text`
label does not mean a nomic vector — that ambiguity is §2's third bullet, not a second population.

The instrument was validated before the result was read: 45 chunks re-embedded earlier that day
scored cosine **1.000000**, which is also what makes 0.9954 a real difference rather than float
noise. The worst was **0.593**. Four of the eight were the opening chunk of four of the five policy
documents — the documents whose text had just been changed by screenshot extraction. All eight were
repaired (nulled, re-embedded, re-verified at 1.000000).

**Coverage cannot see this state.** A stale vector is not NULL, so it counts as covered. The
previous SPEC separated present from absent; this is *present and wrong*.

## 2. Why nothing caught it

- **Nothing in the database says which generation serves this corpus.** Both processes were
  correctly configured as far as either could tell. The host read config, the container read env,
  and neither is in a position to know the other exists.
- The dimension guard in `reembed run` compares `--model` against `--column`. It catches writing a
  1024 vector into a 768 column; it does not catch writing a *correct* 768 vector that nobody will
  search.
- `embed_model` records the last writer of *either* column, so it cannot answer "which generation
  is this chunk indexed under" while two columns are live. [[SPEC-nexus-index-completeness]] §8
  owns that label's design; this SPEC removes the cause without redesigning it.

## 3. Design

### 3.1 The generation of record is declared, in the database, append-only

```sql
CREATE TABLE index_generation_events (
    id           BIGSERIAL PRIMARY KEY,
    tenant       TEXT NOT NULL,
    column_name  TEXT NOT NULL,
    model        TEXT NOT NULL,
    declared_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    declared_by  TEXT NOT NULL,
    reason       TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_index_generation_tenant ON index_generation_events (tenant, id DESC);
```

The generation of record for a tenant is its **latest row**. The table is append-only for the same
reason `doc_reingest_events` is: after a cutover, the date a generation stopped being of record is
the only thing that can place a chunk on one side of it or the other. Overwriting a single row
destroys exactly the evidence this incident needed.

```
nexus generation declare --tenant default --column embedding_1024 --model KURE-v1 \
                         --by <who> [--reason "…"]
nexus generation show [--tenant t] [--history]
```

`declare` **validates before writing**: the column must be in the vector-column registry, and the
model's dimension (`MODEL_DIMENSIONS`) must equal the column's. A typo'd column is refused at
declaration time rather than becoming a permanent ingest refusal naming a column that does not
exist.

`declared_by` is an **audit field, not authorization** — it records who says so, and this SPEC
claims nothing more for it. The gate that carries authority in this repository is Arbiter's
signature, and nothing here borrows it.

**Declaration, not inference** — the rule [[SPEC-nexus-index-completeness]] §3.3 already follows.
Nothing derives the generation from whichever column holds more rows, because during a cutover the
majority is the generation being *left*.

### 3.2 Every write path obeys the declaration

All chunk-writing paths converge on `run_ingest` — verified, not assumed:

| caller | site |
|---|---|
| CLI `nexus ingest` | `cli.py:84` |
| CLI `nexus ingest-notion` | `_default_external_ingest_fn` → `a2a/server.py:370` |
| HTTP ingest endpoints | `api.py:487`, `api.py:545` |
| A2A governed-doc / external-spec ingest | `a2a/server.py:370` |

so the check is placed once, in `run_ingest`, and covers all of them.

- **Declaration matches the resolved generation** → proceed.
- **Declaration differs** → **refuse before writing anything**, naming both sides and the command
  that resolves it. This is a check with a decision attached, which
  [[SPEC-nexus-index-completeness]] §2.4 identifies as the only kind entitled to refuse: which
  generation a corpus is on is a fact someone declared, not a transient state like a NULL vector.
- **No declaration for this tenant** → proceed, and warn **once per run per tenant** (the scope is
  stated because §1's real warning was lost in 739 routine lines). Upgrading must not break a
  running deployment, and a tenant that never declared has not decided anything to violate.

### 3.3 `reembed` is not exempt — it is how the declaration changes

The earlier draft exempted `nexus reembed run`, which left the incident reachable through the one
command it excused: `reembed run --column embedding --model nomic-embed-text` on the host is
dimension-consistent and would repopulate the unsearched generation.

- `reembed run` **without** `--change-generation` must match the declaration, or it refuses.
- `reembed run --change-generation` is the cutover: it may target the other column, and **on
  successful completion it appends the new declaration**, with `--by` required. A cutover that
  finishes therefore cannot leave the declaration behind, which is the failure mode of asking a
  human to remember a second command.
- A cutover that does *not* complete appends nothing; the declaration still names the old
  generation, which is true.

### 3.4 A changed chunk invalidates every derived artifact

`_save_chunks`'s `ON CONFLICT` will null **every** vector column plus the tsvector when
`chunk_text` changes, enumerated from the vector-column registry rather than written out by name,
so that adding a third generation cannot reintroduce this by omission.

**This does degrade the rollback column faster, and that is intended.** [[ADR-0009]] retains the
768 column and its index so that rollback is three env lines and a restart. A *stale* 768 vector is
not a rollback asset — rolling back onto it restores search over text that no longer exists, which
is the failure this SPEC exists to end. What rollback is owed is a **visible** gap, and it now has
one: [[SPEC-nexus-index-completeness]] §3.2 prints both columns' coverage in `nexus status`, so
whoever considers a rollback sees what they would be rolling into before they flip. §5 records this
as the discharge of ADR-0009's open rollback-guard item.

The chunk is invisible to the vector leg until re-embedded, which is correct and is already what
the keyword leg does. Better absent, where coverage can see it, than present and wrong, where
nothing can.

### 3.5 Bootstrap — the fix does nothing until a declaration exists

§3.2's "no declaration → proceed" means an upgraded deployment is exactly as exposed as before
until someone declares. So:

1. The migration **backfills nothing.** Inferring the generation from row counts is the thing §3.1
   forbids, and a wrong inference would refuse every ingest.
2. `nexus status` marks any tenant that **has active chunks and no declaration**, naming the
   `declare` command — beside the coverage lines that SPEC already prints.
3. Shipping this includes declaring `default` (`embedding_1024` / `KURE-v1`), recorded in the
   deployment runbook as the step that closes the incident.

### 3.6 The documented commands say where they must run

The command tables in `README.md` and `CLAUDE.md` currently mix `docker exec` and bare forms with
no stated reason, and the bare form is the accident. They will show **one form with the requirement
stated** — that write commands must run where the deployment's generation is configured — with the
containerised invocation as the example and a note that a non-container deployment must export the
same variables. This is not the guard (§3.2 is); it is a runbook that no longer leads into the
accident. The repository is public and must not present one host's topology as the only one.

## 4. Non-goals

- **The `embed_model` label is not redesigned.** [[SPEC-nexus-index-completeness]] §8 owns it.
  §3.1's table records the deployment's decision, not each chunk's history, and is not a substitute.
- **The 119 mislabelled chunks are not re-stamped.** See §5 — the invariant is currently broken and
  this SPEC records that rather than papering it with a mass update whose correctness depends on
  the label design that is still open.
- **No standing staleness detector.** §8 states the real cost and the trigger.
- **No multi-tenant generation policy.** The grain is per-tenant because coverage already is.

## 5. What this SPEC's links trip, and what it discharges

[[ADR-0009]] leaves three open items whose triggers this document fires — it links ADR-0008 and
rewrites the write path over the embedding columns.

| ADR-0009 open item | disposition here |
|---|---|
| A rollback guard for the post-flip NULL gap | **Discharged.** §3.4 states why a stale old-column vector is not worth retaining, and the guard rollback is actually owed — visibility of the old column's gap — ships in [[SPEC-nexus-index-completeness]] §3.2 and is asserted in §6. |
| A mechanism that detects backstop events, or a declaration made after the fact | **Not taken up**, and recorded as fired for the second time. This document decides how a generation is declared and obeyed; it makes no judgement about backstop events. |
| A usable predicate for "materially expand" | **Not taken up**, recorded as fired. |

ADR-0009 also records the shipped invariant *"one generation per column (`embed_health` reports a
single `embed_model` for the target column)"*. §1 establishes that this invariant is **currently
violated**: 119 chunks in the searched column carry the other generation's label. This SPEC removes
the mechanism that caused it and does not repair the existing rows (§4). The violation is therefore
a known, recorded state with an owner in [[SPEC-nexus-index-completeness]] §8, not an undetected one.

## 6. Testing

Against Postgres in the `nexus-postgres` job.

1. `declare` appends a row; `show` returns the latest; `show --history` returns all in order.
2. `declare` refuses a column outside the registry, and refuses a model whose dimension does not
   match the column's.
3. Ingest with a **matching** declaration writes vectors as before.
4. Ingest with a **differing** declaration refuses **before any row is written** — asserted by
   comparing document and chunk counts before and after, not merely by catching an error.
5. Ingest with **no declaration** proceeds and warns exactly once for that tenant in that run, with
   a declared tenant present in the same database (the mixed case, which the previous SPEC's
   exemption tests showed is where scoping bugs live).
6. `reembed run` refuses against a differing declaration; `reembed run --change-generation`
   proceeds and **appends the new declaration on completion**; a run that fails partway appends
   nothing.
7. Changing a chunk's text nulls **every** registered vector column and the tsvector — asserted by
   enumerating the registry, so a column added later without updating the write path fails here.
8. A chunk whose text changed is picked up by the re-embed queue on the next run — the property
   §1.1 shows was missing.
9. `nexus status` marks a tenant that has chunks and no declaration, and does not mark a declared
   one.

## 7. Acceptance

- With `default` declared as `embedding_1024`/`KURE-v1`, running `nexus ingest` in a shell whose
  environment resolves the 768 generation **refuses and writes nothing**. This is the accident of
  2026-08-10, replayed against the fix.
- After changing one chunk's text and re-running ingest, recomputing that chunk's vector and
  comparing to the stored one yields cosine ≥ 0.9999 — §1.1's check, with nothing left to find.
- `nexus status` on a database with an undeclared tenant names it and the `declare` command; on the
  declared deployment it prints both columns' coverage (ADR-0009's rollback visibility, §5).

## 8. Open items

| item | why it is not decided here | when it is looked at |
|---|---|---|
| The wrong sentence in [[SPEC-nexus-index-completeness]] §1 | That document is approved and stamped; amending it needs its own signature, not a side effect of this one. §1 here is the corrected account, and the two must be read together until then. | Immediately after this SPEC is approved |
| A standing "present but wrong" detector | The honest cost is not "a migration and a write-path change" — this SPEC pays both. It is that the *durable* form stores a hash of the search text beside every vector, which every indexing path must then maintain, and a hash that is written by the same code that writes the vector cannot detect that code being wrong. §3.4 removes the known cause; `scripts/check_stale_vectors.py` (recompute-and-compare, ~35 min for 334 chunks on the dogfood host) stays the instrument for the unknown ones. | When a second cause of staleness is found, or when a corpus makes the script impractical and the risk is judged worth an independent check |
| `embed_model`'s ambiguity, and the 119 rows that carry the wrong label | [[SPEC-nexus-index-completeness]] §8 | Before the next embedding cutover |
