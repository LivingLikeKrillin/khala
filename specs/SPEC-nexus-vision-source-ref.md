---
id: SPEC-nexus-vision-source-ref
type: spec
title: Give the citation a way back to the image — the recourse ADR-0010 admits the
  tier for has never been stored
status: approved
linked_adrs:
- ADR-0004
- ADR-0006
- ADR-0010
tags:
- nexus
- ingest
- vision
- provenance
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-11T14:04:02Z'
content_hash: sha256:3ddb49783afcc4809136eabd1b7c16c1387a6ee2ab28b88ba51e2f6a64b9a695
---

## 1. What prompted it

[[ADR-0010]] §2 admits machine-read text into the corpus **because** a reader can go back and
re-read the image at its source, and §3.1 states that without a re-resolvable reference the tier is
*"a label with nothing behind it"*.

`vision.source_ref(source_uri, block_id, sha)` exists, carries that sentence in its docstring, and
**has no callers**. Verified across the tree.

What is actually stored today:

| where | what it carries |
|---|---|
| chunk marker in the body | `![](){: derived=vision extractor=<model>/<prompt_sha> }` |
| `vision_extractions` row | `(tenant, image_sha256, extractor_identity, text, error, truncated)` |
| `Extraction` dataclass | `text, identity, sha, truncated, error` |

**No block id anywhere, and no key joining a chunk to its extraction row.** A reader holding a
citation cannot reach the image, and neither can the system: `vision_health.fetch_reader_health()`
had to report chunks and extractions as two unjoined populations for exactly this reason.

[[SPEC-nexus-screenshot-text-extraction]] §7.1b reports step 0b as passed — 11 images re-fetched
*"from its stored block id alone"*, bytes identical 11 of 11. That run held the block ids in memory;
they were never persisted. **What was demonstrated is not what shipped.**

## 2. Design

### 2.1 The join key goes in the marker; the long parts go in the row

The chunk marker gains one field:

```
![](){: derived=vision extractor=<model>/<prompt_sha> img=<first 16 hex of image_sha256> }
```

and `vision_extractions` gains the two columns that make the reference resolvable:

```sql
ALTER TABLE vision_extractions
    ADD COLUMN IF NOT EXISTS block_id   TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS source_uri TEXT NOT NULL DEFAULT '';
```

`source_ref()` is finally called, at save time, from the values that are already in hand at
`vision_store._one()` where the image dict is held.

**Why the sha in the body and the block id in the row.** The marker is inside the hashed document
body, so anything put there costs a `content_hash` change once and must never change again — that
is exactly what ADR-0010 §5 refused a timestamp for. A **16-hex prefix of the image content hash is
stable for the same bytes forever**, so it is a one-time cost and never churns. A block id is longer,
is a Notion-shaped identifier that would sit in every citation a user reads, and is not needed to
*find* the row — only to *resolve* it, which happens after the row is found.

**Uniqueness is enforced, not measured.** A point-in-time check over today's 44 shas says nothing
about the next image ingested, and a handle that matches two rows would resolve a citation to the
**wrong image** — worse than the unresolvable state this SPEC exists to end. So the database
enforces it:

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_vision_handle
    ON vision_extractions (tenant, left(image_sha256, 16), extractor_identity);
```

and `resolve_source()` **refuses on ambiguity** rather than returning a row — if the index is ever
absent, the function must still not guess (§2.2).

### 2.2 Resolution is a function, and it is exercised end to end

```
resolve_source(tenant, chunk_text) -> {source_uri, block_id, image_sha256, extractor_identity}
```

parses the marker, finds the row by (tenant, sha prefix, identity), and returns the reference. §5
requires a test that goes **chunk text → reference → image bytes → same sha**, because a reference
that has never been resolved is the state this SPEC exists to end.

**Every outcome it will actually meet is named, and none of them is a silent None.** A caller must
be able to tell "there is no reference" from "the lookup failed" — conflating those is the same
mistake as reading `ObjectNotFound` as deletion (§4):

| case | result |
|---|---|
| authored chunk, no marker | `None` — this chunk is not machine-read, and that is not an error |
| marker without `img=` (ingested before this change) | `Unresolvable("pre-migration marker")` |
| handle matches no row | `Unresolvable("no extraction row")` — the row was pruned or the identity migrated |
| handle matches more than one row | **raises** `AmbiguousHandle` — never picks one |
| row found, `block_id = ''` | `Unresolvable("reference not recorded")` — distinct from "no row" |
| row found with a reference | the reference |

### 2.5 The marker has a grammar, because a parser now depends on it

The marker is written by `build_block()` and read by `resolve_source()`, and those two will outlive
whoever wrote them. An earlier draft claimed the marker cost is *"paid once and never changes"* —
false: it already embeds `extractor=<model>/<prompt_sha>`, which ADR-0010 §5 **requires** to change
on every extractor migration, and it changed twice on 2026-08-11.

Fixed here:

```
![](){: derived=vision extractor=<model>/<prompt_sha> img=<16 lowercase hex> }
```

* fields are `key=value`, space-separated, in that order;
* values contain no spaces or `}`; `img` is exactly 16 lowercase hex characters;
* an unknown field is **ignored** by the parser, and a missing `img` is `Unresolvable`, not a crash —
  so a future field can be added without stranding old chunks;
* §5 pins the format with a test that reads a marker the writer produced, rather than a hand-typed
  string, so the two cannot drift apart silently.

### 2.3 What this costs, stated before it is paid

* `content_hash` changes once for the five image-bearing documents; `doc_reingest_events` gains five
  rows, which perturbs ADR-0006's entropy signal ① with no marker to distinguish a deliberate
  migration — the same open item [[SPEC-nexus-vision-reader-of-record]] §6 carries, and the same
  mitigation: the migration records its timestamp and the five document rids.
* The 40 `machine_read` chunks change text, so their vectors and tsvectors are nulled and requeued
  ([[SPEC-nexus-generation-of-record]] §3.4). `nexus status` must show no coverage gap when the
  queue drains.
* Existing rows keep `block_id = ''`. Empty is not "unknown-but-fine": §2.4 says what it means.

**The counts, reconciled — an earlier draft asserted them and could not explain them.** Measured on
the operating tenant: 44 images → 44 extraction rows → **40** `machine_read` chunks, each carrying
exactly one marker (verified by counting markers per chunk). The gap is **4 empty extractions**, all
in one document: an image whose reader returns no text produces no block and therefore no chunk.

That matters here rather than being trivia: those four rows **are not reachable from any citation**,
because no chunk exists to carry a handle. §2.4's counter must count them as unresolvable-by-design
rather than as a defect, and §6's acceptance cannot demand a round trip for them.

(A previous message in this lineage reported "0 empty extractions". That measurement joined the new
rows against the old identity's rows and answered a different question. The number above is the
direct one.)

### 2.4 Backfill, and what an empty reference means

Existing extraction rows cannot be backfilled from stored data — the block id was never kept.

**And re-ingest alone will not fill them**, which an earlier draft assumed. ADR-0010 §5 fixes that
unchanged bytes are never re-extracted: the walk hits the stored result and the save path is
skipped, so `source_ref()` would never fire for any of the 44. The acceptance criterion built on
that assumption was unreachable.

So the reference is recorded on the **cache-hit path as well**: when a walk resolves a stored
extraction and that row has no reference, the walk fills `block_id` and `source_uri` from the image
it is holding. **This does not re-extract and does not touch `text`** — the stored reading is
untouched, which is exactly what §5 protects. Writing down where a reading came from is not
replacing the reading.

**New rows must carry a reference.** The save path refuses an extraction whose `block_id` is empty
rather than storing an unresolvable row — the walk always has it, so an empty one means a defect
upstream, and admitting it silently is how the tier's precondition rots (§2.4's counter would then
grow with nobody having decided anything).

Until then, `block_id = ''` means **this extraction cannot be resolved to its source**, and that is
reportable: `nexus status` counts unresolvable extractions beside the reproducibility counts it
already prints. An unresolvable `machine_read` chunk is a tier whose justification is not met, and
the operator should be able to see how many there are without reading the schema.

## 3. Non-goals

- **No change to what the reader does.** Extraction, prompt and identity are untouched.
- **No image bytes stored.** ADR-0004 fixes Nexus as index-not-store; this makes the *reference*
  resolvable, not the corpus a blob store.
- **No new rendering.** The marker is **user-visible** — it lives in `chunk_text`, which is what a
  citation renders — so adding a field to it *is* a change to what a reader sees, and an earlier
  draft was wrong to file that under non-goals while simultaneously arguing the block id was too
  ugly to put there. What is out of scope is building a UI affordance on top of it; what is in scope
  is the string, and §2.5 fixes its grammar so writer and parser cannot drift.
- **No guarantee the source still exists.** §4.

## 4. Limits

* **Resolvable is not durable.** The reference resolves only while Notion keeps the block and the
  integration retains access. That access is per-root and token-scoped, which is why asking with the
  wrong token returns `ObjectNotFound` and reads as deletion — fixed for the CLI on 2026-08-11, and
  the reason this SPEC stores `source_uri` alongside the block id rather than the token.
* **A 16-hex prefix is not the key.** The full sha remains the primary key; the prefix is a lookup
  handle whose uniqueness is asserted per tenant, not assumed.
* **One image, one row, two chunks.** A long extraction can be split by the chunker, so two chunks
  may carry the same `img=` handle. That is correct — they resolve to the same image — and the test
  in §5 covers it rather than leaving it to be discovered.

## 5. Testing

**Everything below runs in CI against the disposable test database with a stub fetcher.** The live
corpus is not a fixture: an earlier draft made the load-bearing assertions depend on a live Notion
block, the right per-root token and an unexpired signed URL — all three of which §4 says can vanish,
so those tests would have been skipped or red for unrelated reasons.

1. `source_ref()` is called on the save path — asserted by reading `block_id` and `source_uri` back
   from the row, not by mocking the call.
2. The save path **refuses** an extraction with an empty `block_id` (§2.4).
3. The cache-hit path fills a reference on a row that lacks one **without changing `text`** — the
   stored reading is compared before and after (§2.4, ADR-0010 §5).
4. The marker carries `img=`, and the handle matches the row's `image_sha256` prefix.
5. **Round trip, with a stub fetcher**: chunk text → `resolve_source()` → fetch by the returned
   reference → the bytes hash to the same `image_sha256`.
6. Every row of §2.2's outcome table, including `AmbiguousHandle` **raising** rather than returning.
7. Two chunks split from one long extraction carry the same handle and resolve to the same image.
8. The unique index rejects a second row whose sha shares the first sixteen characters — asserted
   against the constraint, not against application code.
9. `nexus status` reports the count of extractions with an empty `block_id`, counted over
   **extraction rows** (not chunks — they are different populations, §1), and prints nothing for a
   tenant with no extraction rows.
10. Migration 016 is idempotent and leaves existing rows with empty strings.

## 6. Acceptance

- §5.5's round trip passes in CI, and is **also** run once by hand against a real image from the
  live corpus — recorded as a one-off observation, not as a test.
- After the reference-filling walk, every extraction row for the operating tenant that has a chunk
  carries a non-empty `block_id`. **The four empty extractions are excluded and counted separately**
  (§2.3): no chunk exists to cite them, so no citation can need a way back.
- Any row that stays empty because its block is gone from the source is reported by §5.9's counter
  rather than blocking acceptance — §4 says the source is not ours to control, and §7 carries the
  disposition.
- `vision.source_ref()` has at least one caller, which is the sentence this SPEC exists to make true.

## 7. Open items

| item | why not here | when |
|---|---|---|
| The migration perturbs ADR-0006 entropy signal ① | No column distinguishes a deliberate migration from re-upload; adding one touches ADR-0006's schema. The run records its timestamp and the five document rids so a reader of signal ① can subtract them. | Whoever next reads signal ① |
| Durability of the reference | Nexus does not control whether the source keeps the block. Only the resolution is owned here. | If a re-fetch fails in practice |
| One reader misses what the other sees (8 items measured 2026-08-11) | A union of two readers is a different design with a standing cost. | Its own SPEC |
