---
id: SPEC-nexus-query-text-retention
type: spec
title: Keep the question, so the eval set can stop being written by the documents
  it grades
status: approved
date: '2026-08-12T00:00:00Z'
linked_adrs:
- ADR-0002
- ADR-0009
tags:
- nexus
- eval
- governance
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-12T06:41:49Z'
content_hash: sha256:89cdc6ab3c16c9f7ccf3db91d78f09e2495d5cca0fa92e633dcb789a8f9ba046
---
# Keep the question, so the eval set can stop being written by the documents it grades

## 1. What prompted it

The answer ruler now reports a grade that means something: labels are bound to the text they were
signed against, refusals have a scope, an unjudged citation is not a wrong citation. On 2026-08-12,
`revision 6` measured three times gave **39/40, 39/40, 40/40** — the two failures landing on
*different* queries, none failing all three.

That number has a ceiling built into it. **All 45 labels were authored from the documents they
grade.** A query written by reading the answer is a query the corpus is guaranteed to contain, and a
retrieval system measured only on such queries is being asked whether documents can find
themselves. The label file says so in its own header — `provenance: authored_from_doc` on every
row — so this is a known limit, not a discovery.

The obvious fix is real questions. The infrastructure to collect them exists and has been running:
`search_log` holds **946 rows**. It cannot supply a single question:

```
query_sha256  text  not null
query_len     integer not null
```

The text was never kept. That was a deliberate privacy choice and it is the right default. The
consequence is that every search the team has ever run is unusable for building the eval set, and
the Slack pilot — the first real traffic this system will ever see — would be an event that answers
questions and then throws every one of them away.

## 2. Non-goals

- **Not analytics.** No dashboards, no popular-query reports, no per-person history. Those are
  different products with different consent stories, and building the storage "in case" is how a
  narrow retention becomes a behaviour log.
- **Not a personalisation substrate.** No read of this table influences an answer. (The writer does
  read it — an upsert must — but nothing on the answering path does.)
- **Not on by default, ever.** A deployment that does nothing keeps hashing.
- **Not a redaction engine.** This SPEC does not attempt to detect and strip secrets from questions.
  A question is user-authored text and may contain anything; the controls here are consent,
  scope, expiry and access — not scrubbing, which cannot be verified and would make the
  protection look stronger than it is.

## 3. Design

### 3.1 A key that cannot be joined to a person

Retention lands in its own table, and — this is the load-bearing part — **its key is deliberately
not `search_log`'s key**:

```sql
CREATE TABLE search_query_text (
  tenant        text NOT NULL,
  retention_key text NOT NULL,          -- sha256(tenant || '\x00' || query_text)
  query_text    text NOT NULL,
  first_seen    timestamptz NOT NULL DEFAULT now(),
  last_seen     timestamptz NOT NULL DEFAULT now(),
  seen_count    integer NOT NULL DEFAULT 1,
  PRIMARY KEY (tenant, retention_key)
);
```

The first draft keyed on `query_sha256`, the same hash `search_log` stores, and claimed that
omitting a principal column prevented a person log. **That claim was false, and checking cost one
query:** `a2a_audit` carries `principal` *and* `query_sha256` in the same row. Text on one side,
principal on the other, joined by the shared hash — the person log the design said it prevented,
reconstructable by anyone with read access to both tables.

Salting with the tenant fixes it structurally rather than by promise: the retention key equals no
hash stored anywhere else, so there is nothing to join on. The join to `search_log` is not lost,
because it was never needed — building an eval set needs the question and how often it was asked,
not which request served it.

The same salt closes a second hole the first draft had: with `query_sha256` as sole primary key,
the same question asked in two tenants collided on one row, and a tenant that had *not* opted in
would still bump `seen_count` on another tenant's retained row.

**The writer is a no-op for a tenant with no retention row** — it does not insert, does not update,
does not touch an existing row. "A tenant with no row retains nothing" is a statement about
behaviour, not only about inserts.

**Invariant, stated so it can be tested:** no table may carry `retention_key` alongside a principal
or any per-user identifier. §5 asserts this over the live schema, not over this table alone —
the failure being prevented was in a *different* table.

### 3.2 Opt-in per tenant, declared in the database

Retention is on only for tenants with a row in `query_retention` (`tenant`, `enabled_at`,
`enabled_by`, `notice_shown`, `retain_days`). Not an env var and not a config file: an env var is
invisible in review, gets copied between deployments, and cannot record **who turned it on**.
`notice_shown` is a free-text reference to where the people asking questions were told — a Slack
message link, an onboarding page.

The writer refuses when `notice_shown` is empty, and the refusal is **counted and surfaced in
`/status`** (`query_retention_refused`), not only logged. A consent control whose failure is a log
line nobody greps is the same failure as index coverage: the number existed, and no one was shown
it (SPEC-nexus-index-completeness).

### 3.3 Expiry runs against `first_seen`, and what that does not promise

`retain_days` (default 90) is measured from **`first_seen`**. Not `last_seen`: a recurring question
would then never expire, and recurring questions are exactly the ones most likely to be exported
and most likely to matter.

What this does **not** promise: a question asked again after its row is purged creates a new row
with a fresh window. The window bounds how long **a given sighting** is kept, not how long a
repeatedly-asked question can be reconstructed. The alternative — a tombstone so re-asking cannot
restart the clock — would keep a permanent record of every question ever asked, which is worse than
the thing it protects against. This is a choice with a cost, written down rather than smoothed over.

`nexus query-text purge` deletes rows past the window and prints what it deleted. **`/status`
reports the oldest `first_seen` per tenant**, so a purge that never runs is visible where everything
else that never ran is visible.

### 3.4 Revocation is an operation, not an absence

Turning retention off is `nexus query-text disable --tenant`, which **deletes the tenant's stored
text and its `query_retention` row, in that order, in one transaction.** Deleting the
`query_retention` row by hand would otherwise orphan the text: no `retain_days` to evaluate, so
purge skips it and it lives forever. Purge therefore also treats **orphaned rows as expired** —
text whose tenant has no retention row is deleted on the next run, whatever its age.

Lowering `retain_days` takes effect at the next purge; it does not delete retroactively on its own,
and `/status`'s oldest-row number is what makes the lag visible.

**Per-person erasure is structurally impossible here, by construction.** With no principal column
there is no way to honour "delete my questions" for one person; the only available remedy is
purging the tenant. That is the cost of not building the person log, it is the right trade for this
purpose, and it must be in the notice `notice_shown` points at — not discovered by someone asking.

### 3.5 The text never leaves through an API, and never blocks a search

No endpoint returns `query_text`. The only reader is the CLI (`nexus query-text export --tenant`),
writing to a path the operator names. Eval labels derived from it live in `tests/eval/local/` —
gitignored, because the repo is public and questions are organisational content
(SPEC-nexus-korean-retrieval-eval §4.1). This inherits that SPEC's stated limit: an outside reviewer
can re-derive behaviour from committed fixtures and nothing else.

The retention write is **best-effort and off the answer path**: a failure is counted and logged, and
never fails or delays the search. A consent-scoped side-record must not be able to take down
answering.

### 3.6 This set triggers ADR-0009's revisit obligation

ADR-0009 records an obligation with no expiry: if a labelled set over khala's own corpus is built
and its vector-leg Recall@10 comparison under the pre-registered rule (two-sided sign test,
α = 0.05, ≥ 6 discordant pairs) does not favour KURE-v1 over the incumbent, the record re-opens; an
underpowered result leaves the obligation open rather than discharging it. Owner: LivingLikeKrillin.

The set §6.3 builds is such a set. **This SPEC does not discharge that obligation and does not
attempt to** — it names it so the trigger is not pulled silently. When the first labels with
`provenance: from_user_query` reach a size that can produce ≥ 6 discordant pairs, the comparison is
run under that rule and its result recorded against ADR-0009. Until then the obligation stays open,
which is what ADR-0009 says an absent result means.

## 4. How this can lie, and what it costs if it does

- **The flag can be flipped without anyone being told.** `notice_shown` is a string, and a string
  can be filled in with anything. This SPEC makes the claim recordable and reviewable; it cannot
  make it true. That is the honest limit of a governance control implemented as a column.
- **A question can contain a secret.** Someone will paste a token into the search box. There is no
  redaction (§2), and expiry is a *manual* purge — an operator who never runs it retains
  indefinitely. `/status` makes that visible; nothing makes it impossible.
- **"Real questions" is not comparable to 40/40.** A set of real questions and the current authored
  set measure different populations; a lower score on real questions is not a regression, and
  putting the two numbers in one column would be the same error this ruler was built to stop. They
  are reported separately, with `provenance` naming which is which.
- **Retention makes the eval set better and the corpus no better.** Nothing here improves an answer.
  It improves the honesty of the measurement, which is the thing that was inflating.

## 5. Testing

- **Default off:** no `query_retention` row → after searches, `search_query_text` is empty *and*
  no existing row's `seen_count`/`last_seen` moved (control: with a row, the same search writes one).
- Empty `notice_shown` → nothing retained, and `/status` reports the refusal count (not just a log).
- Repeat search of the same text: one row, `seen_count` 2, `last_seen` advanced, `first_seen` fixed.
- **Cross-table invariant:** no table in the live schema carries `retention_key` next to a principal
  column — asserted by scanning `information_schema`, so a *future* table cannot re-open the join
  that made the first draft's claim false.
- Purge: deletes rows whose **`first_seen`** is past `retain_days`, keeps the rest, and deletes
  orphans (text whose tenant has no `query_retention` row). `search_log`'s row count is unchanged.
- `disable` deletes text and the retention row together; a crash between them cannot leave text
  without a row (single transaction — asserted by aborting mid-transaction).
- The write path cannot fail a search: with the retention insert forced to raise, the search still
  returns 200 and the failure is counted.
- No API response exposes `query_text`: asserted by walking the generated OpenAPI schema for the
  string, so a new endpoint cannot leak it by being new.

## 6. Acceptance

1. A tenant with retention off stores nothing new after this ships — verified against a live run,
   not only in tests.
2. The pilot tenant is switched on **with `notice_shown` pointing at a message the team actually
   received**, and that message is quoted in the PR body.
3. One export produces a candidate question list, and the first labels authored from real questions
   carry `provenance: from_user_query` — distinguishable forever from `authored_from_doc`, so the
   ceiling can be measured rather than argued about. Those labels are signed under the same
   `corpus` binding rule as every other label (SPEC-nexus-answer-quality-ruler §3.3).
4. ADR-0009's obligation is either run (result recorded) or explicitly recorded as still open at the
   moment the real-question set first reaches ≥ 6 discordant pairs.

## 7. Units

| # | unit | lands in |
|---|---|---|
| U1 | `search_query_text` + `query_retention`, migration, salted key, no-op writer, best-effort write | `nexus/db`, `migrations/` |
| U2 | `purge` (first_seen + orphans) · `disable` (transactional) · `/status` surfacing | `nexus/cli.py`, status payload |
| U3 | `export` + `provenance: from_user_query` accepted by the label gate | `nexus/cli.py`, `ko_eval_labels.py` |
| U4 | Turn it on for the pilot tenant with the notice recorded | operational, PR body |
