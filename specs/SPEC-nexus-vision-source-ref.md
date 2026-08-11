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
reviewed_at: '2026-08-11T15:04:38Z'
content_hash: sha256:14acd7ed8083cf64ca6ed3401af9f1232351ed620deaf1fe03caa728b8de0dd2
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

**It resolves stored chunk text, not a rendered snippet.** A reader holding a citation holds a
snippet, and ADR-0010 §1 records that snippet boundaries already truncate — a marker on the block's
first line is exactly what a truncating renderer drops. So the entry point a surface uses is by
**chunk rid**:

```
resolve_chunk(tenant, chunk_rid) -> same result as resolve_source on that chunk's stored text
```

The surface never has to carry the marker through the six hops of ADR-0010 §4; it carries the chunk
rid it already has, and the server reads the stored text. Building the affordance that calls this is
still out of scope (§3) — what is in scope is that the call is possible without the marker having
survived rendering.

**Every outcome it will actually meet is named, and each is distinguishable.** A caller must be able
to tell "this is not machine-read text" from "there is no reference" from "the lookup failed" —
conflating the last two is the same mistake as reading `ObjectNotFound` as deletion (§4). `None` is
one of those named outcomes, not an unexplained absence:

| case | result |
|---|---|
| authored chunk, no marker | `None` — this chunk is not machine-read, and that is not an error |
| marker without `img=` (ingested before this change) | `Unresolvable("pre-migration marker")` |
| handle matches no row | `Unresolvable("no extraction row")` — the row was pruned or the identity migrated |
| handle matches more than one row | **raises** `AmbiguousHandle` — never picks one |
| row found, `block_id = ''` | `Unresolvable("reference not recorded")` — distinct from "no row" |
| row found with a reference | the reference |

`Unresolvable` is a frozen dataclass carrying a `reason`. The **reason strings are diagnostic, not a
contract** — callers branch on the type, tests may match the strings, and no surface should parse
them.

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

**There are three participants, not two.** §4's fix makes the chunker recognise the marker and
re-emit it on every fragment of a split block, so a grammar change can break fragment re-emission
without touching either the writer or the parser. §5.7 is the pinning test for that third edge: it
runs writer → chunker → parser, so all three move together or the test goes red.

### 2.3 What this costs, stated before it is paid

* `content_hash` changes once for the five image-bearing documents; `doc_reingest_events` gains five
  rows, which perturbs ADR-0006's entropy signal ① with no marker to distinguish a deliberate
  migration — the same open item [[SPEC-nexus-vision-reader-of-record]] §6 carries, and the same
  mitigation: the migration records its timestamp and the five document rids.

  **The `img=` field costs that once; the marker as a whole costs it again on every extractor
  migration.** The marker already carried `extractor=<model>/<prompt_sha>`, which ADR-0010 §5
  *requires* to change whenever the reader changes — it changed twice on 2026-08-11. So every future
  reader swap rewrites the body of every image-bearing document and adds a reingest row per
  document. That is a recurring perturbation of signal ①, it predates this SPEC, and adding `img=`
  neither causes nor worsens it. §7 carries it as the open item it is; what is corrected here is the
  claim that the cost is paid once.
* The 40 `machine_read` chunks change text, so their vectors and tsvectors are nulled and requeued
  ([[SPEC-nexus-generation-of-record]] §3.4). `nexus status` must show no coverage gap when the
  queue drains.
* Existing rows keep `block_id = ''`. Empty is not "unknown-but-fine": §2.4 says what it means.

**The counts, reconciled — an earlier draft asserted them and could not explain them.** Measured on
the operating tenant: 44 images → 44 extraction rows → **41** active `machine_read` chunks, each
carrying exactly one marker. Two gaps, in opposite directions:

* **−4**: an image whose reader returns no text produces no block and therefore no chunk. Four
  extractions are empty, all in one document.
* **+1**: one extraction is long enough that the chunker splits it, and both fragments carry the
  handle (§4).

44 − 4 + 1 = 41. An earlier revision of this section said 40 and called the arithmetic closed; it was
counting before the split fix existed, and it did not distinguish active chunks from superseded ones.

**The four empty rows are still reachable.** An earlier draft called them "unresolvable-by-design"
and had §6 exclude them from acceptance. That was wrong about what the reference is for: the row is
written on the fetch/read path, which holds the block id whether or not the reader returned text, so
those four carry references like any other. Nothing needs excluding, and §6 no longer does.

**44 images → 44 rows is not a bijection in general.** Storage is keyed by bytes (ADR-0010 §5), so
the same image pasted into two blocks collapses to one row — see §4.

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

### 2.7 A handle collision must be loud

The unique index turns a 16-hex prefix collision into an insert failure, and the save path swallows
it: `ON CONFLICT DO NOTHING` has no conflict target, so it absorbs *any* unique violation. The row
is not written, the subsequent read-back by full sha finds nothing, and the walk proceeds with the
extraction it holds — so the body is correct while **no row exists**, and the chunk's handle then
resolves to the *other* image's row. That is the wrong-provenance outcome §2.1 invokes the index to
prevent, arriving through the mechanism meant to prevent it.

A 64-bit prefix collision is not expected — the birthday bound puts it far past any corpus this will
see. Unexpected is not the same as handled. The save path checks, after the insert, that a row for
its own sha exists; if instead a row exists under the same handle with a different sha, it raises
rather than returning. Loud and rare beats silent and rare.


### 2.6 The retired reader's rows

They are kept. ADR-0010 §5's identity migration is the record of which reader produced which text,
and deleting the losing side would erase the evidence that a migration happened. They stay
reference-less because no walk will ever hold their block ids again, and that is a stated end state,
not a backlog item.

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
  handle whose uniqueness is asserted per tenant, not assumed. A collision is not merely a read-time
  ambiguity — it is an **insert** that the index rejects, and §2.7 says what happens then, because
  the failure the unwritten version had was silent and produced the wrong provenance.
* **The reference names an occurrence, not the citing document's occurrence.** Storage is keyed by
  bytes, so the same image in two blocks is one row holding one `(block_id, source_uri)`, and the
  fill is first-walk-wins (§2.4). A citation from the second document therefore resolves to the
  first document's block. The recourse ADR-0010 §2 asks for still holds — re-fetching that block
  returns *the same bytes*, which is the image the reader read — but the `source_uri` beside it can
  name a different document, and a surface that renders it must not claim otherwise. Making the
  reference per-occurrence means keying extractions by `(bytes, block)` and re-reading the same
  image once per block, which is the cost ADR-0010 §5 exists to avoid; not taken.
* **`block_id` is Notion-shaped, and today only one intake path produces images.** §2.4's refusal is
  on *no reference at all*, not on a Notion id specifically. A future connector must supply whatever
  locator lets its source be re-read; if one arrives that cannot, the refusal would turn "no
  reference" into "no extraction", and that trade has to be decided then rather than inherited from
  a rule written against a single connector.
* **One image, one row, two chunks.** A long extraction can be split by the chunker, so two chunks
  may carry the same `img=` handle. That is correct — they resolve to the same image — and the test
  in §5 covers it rather than leaving it to be discovered.

  **This was false when written, and §5.7 is what caught it.** The marker occupies the block's first
  line only, so a split left every fragment after the first with no handle at all: the tier travelled
  and the way back did not. The chunker now re-emits the marker on each fragment of a vision block.
  One block in the operating corpus does split, so this is not hypothetical — it was 1 of 41 active
  `machine_read` chunks.

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
   tenant with no extraction rows. The count is **split by extractor identity** (§5.11).
10. Migration 016 is idempotent and leaves existing rows with empty strings.
11. A retired reader's reference-less rows are counted **apart** from the current reader's, and do
    not raise the warning (§2.6).
12. **§5.5 has a negative control.** The stub source holds *two* distinct images, and the round trip
    asserts the reference selects the citing chunk's image; a mangled handle must fail to produce
    bytes rather than falling back to the only fixture in the map. Without this, a stub that returns
    the same image regardless of the reference passes §5.5 with a corrupt reference stored — the
    test would prove nothing about resolution.
13. A handle collision raises on the save path rather than silently writing nothing (§2.7),
    asserted by inserting a colliding sha through the same path.
14. `resolve_chunk(tenant, chunk_rid)` returns the same reference as `resolve_source()` on that
    chunk's stored text, and does so for a chunk whose rendered snippet would have dropped the
    marker (§2.2).
15. The chunk leg of the counter reports an active `machine_read` chunk whose marker does not
    resolve — a pre-migration marker and an unknown identity both count — while the row leg reports
    zero for the same state (§5.11). One test, two legs, because the point is that they disagree.

### 5.11 What the counter counts, corrected after the first real walk

§5.9 above originally said *"counted over extraction rows"* full stop, and that is what shipped
first. On the operating tenant it then reported **44 unresolvable out of 88** immediately after a
walk in which every row the walk could reach had been filled.

The number was not wrong; the population was. ADR-0010 §5 keys storage by
`(bytes, extractor_identity)`, so a walk only ever meets rows of the **current** identity — the 44
belonging to the retired reader are unreachable by any walk, forever. Counting them together
produces a warning that can never be turned off, which is the exact failure this repo removed from
`nexus status` two changes ago.

It is also inaccurate in the direction that matters. Every active `machine_read` chunk carries the
current identity in its marker, so **no citation points at a retired row**. A counter that exists to
answer *"can a reader holding a citation get back to the image?"* must not count rows no citation
can reach.

So: the warning counts the current reader's reference-less rows; retired ones are reported on a
plain line beside it, so they are visible without being an alarm.

**"Current" means the identity this deployment's reader would produce right now** —
`vision.extractor_identity()`, i.e. `<vision model>/<prompt sha>`. It is deployment state, not a
stored fact, so changing the configured reader moves rows between the two lines with no data change.
That is the intended reading: the question is whether *this* deployment's readings can be traced.

**Rows are not the whole population, and the row counter cannot see the failure it names.** §5.9
counts extraction rows, but an unresolvable *citation* lives in a chunk: a pre-migration marker with
no `img=`, a marker naming an identity whose rows were pruned, and (before §4's fix) a fragment that
lost its handle are all unresolvable citations that a row-based counter reports as **zero**. The
supporting claim in the paragraph above — every active `machine_read` chunk carries the current
identity — was a point-in-time observation with nothing enforcing it; an identity migration that
does not rewrite chunk text breaks it silently.

So the counter has both legs: reference-less rows *and* active `machine_read` chunks whose marker
does not resolve. The chunk leg is the one that answers the question the counter is for.

## 6. Acceptance

- §5.5's round trip passes in CI, and is **also** run once by hand against a real image from the
  live corpus — recorded as a one-off observation, not as a test.
- After the reference-filling walk, every extraction row of the **current** identity carries a
  non-empty `block_id` — including the four empty extractions, which are written on the fetch path
  and so carry references like any other (§2.3 corrects the earlier exclusion). Retired identities
  are out of scope by §2.6.
- Any row that stays empty because its block is gone from the source is reported by §5.9's counter
  rather than blocking acceptance — §4 says the source is not ours to control, and §7 carries the
  disposition.
- `vision.source_ref()` has at least one caller, which is the sentence this SPEC exists to make true.

### 6.1 What it measured when it was actually run (2026-08-11)

| criterion | result |
|---|---|
| extraction rows for the current reader carrying a reference | **44 / 44** — 0 unresolvable, including the four empty extractions §2.3 excused |
| active `machine_read` chunks carrying a handle | **41 / 41**; one block split, both fragments resolve (§4) |
| hand-run round trip on the live corpus | **3 / 3** — citation → block re-fetched → *fresh* signed URL → bytes hash to the stored `image_sha256` |
| retired reader's rows | 44, reference-less by construction (§2.6), reported apart |

The round trip is the load-bearing one: the URL held at ingest had long expired, and the reference
still produced the same bytes. It is re-runnable rather than anecdotal —
`scripts/vision_roundtrip_probe.py N` walks the first N active `machine_read` chunks and exits
non-zero if any fails — but it needs live Notion access and a valid per-root token, which is why §5
keeps it out of CI. Three is the count that fit inside one manual run; the script takes any N. That is the recourse ADR-0010 §2 admits the tier for, demonstrated
against stored state rather than against ids held in memory — which is how
[[SPEC-nexus-screenshot-text-extraction]] §7.1b came to report a passing round trip for something
that had never shipped.

**Two things this SPEC asserted were false, and running it is what showed that** — both are recorded
where they belong (§4, §5.11) rather than quietly fixed. A third defect was outside this SPEC and
blocked its walk: `nexus ingest-notion` ran two event loops, so the connection pool from the first
was dead in the second and all 112 pages failed while the command exited 0.

## 7. Open items

| item | why not here | when |
|---|---|---|
| The migration perturbs ADR-0006 entropy signal ① | No column distinguishes a deliberate migration from re-upload; adding one touches ADR-0006's schema. The run records its timestamp and the five document rids so a reader of signal ① can subtract them. | Whoever next reads signal ① |
| Durability of the reference | Nexus does not control whether the source keeps the block. Only the resolution is owned here. | If a re-fetch fails in practice |
| One reader misses what the other sees (8 items measured 2026-08-11) | A union of two readers is a different design with a standing cost. | Its own SPEC |
| The reference requirement is enforced in the save path, not in the schema | The invariant is *"rows of the current identity carry a reference"*, and "current" is deployment state (§5.11) — a CHECK or partial index would have to freeze today's identity string into DDL, and would then reject the retired rows §2.6 deliberately keeps. The compensating detector is §5.9's counter, which is why it gained the chunk leg. | If a second writer to `vision_extractions` is ever added |
| Per-occurrence references (same bytes in two blocks) | Requires keying extractions by `(bytes, block)` and re-reading the same image once per block — the cost ADR-0010 §5 exists to avoid. §4 states what a surface may and may not claim in the meantime. | If a corpus is found where it actually misleads |
