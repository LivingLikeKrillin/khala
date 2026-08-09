---
id: ADR-0010
type: adr
title: Machine-read text from images is evidence, of a lower tier — and the tier must
  travel with it
status: in_review
date: 2026-08-09
tags:
- nexus
- grounding
- integrity
- ingest
linked_adrs:
- ADR-0002
- ADR-0004
- ADR-0006
---

# ADR-0010: Machine-read text from images is evidence, of a lower tier

## Status

**Draft** — settles one boundary question, ships no code. The design that depends on it is
`SPEC-nexus-screenshot-text-extraction`, which was critiqued before this ADR existed and was told,
correctly, that a SPEC cannot amend an ADR.

## Context

ADR-0002 subordinated the existing principles to the mission and named the first as the integrity
layer:

> **Grounded answers only / "system decides, LLM narrates"** → the *integrity layer* that makes
> recaptured understanding trustworthy.

That phrase carried an unexamined assumption. Every chunk Nexus has indexed was **text a person
wrote**, so "grounded" meant *traceable to an authored sentence* and a citation promised that.

### What was measured, and how

On 2026-08-08, over the live tenant (116 documents, 289 chunks):

* **Image count** — `![]()` placeholders counted in `chunks.chunk_text` by SQL over the live
  tenant. Five documents carry **44**; the other 111 carry none.
* **Text per image** — body characters divided by image count: **100–171 characters**. That text
  is a heading or a bullet.
* **Captions** — read from the Notion API's `image.caption` for one document's 11 images:
  **0 of 11**. The other 33 are **not** measured; "zero captions" is established for 11 and
  assumed for the rest, and the assumption is recorded as such.
* **What the pixels hold** — one screenshot was fetched and read by a human. It contained a screen
  id, a version, a rule sentence, and a two-row specification table, **none of which appears in
  the document's text**.

A user question — the point thresholds that unlock each avatar — returned "not found", correctly.
The answer-quality run that scored 40/40 the same day was scored against text only, using labels
an agent authored from that same text. **The ruler never pointed at the images.**

**Generalisation limit.** One document's images were opened. "The policy is the screenshots" is
supported for that document and is an inference for the other four. It is strong enough to act on
and not strong enough to state as fact, which is why §Open items requires a sample before any
extraction is committed.

### The demand-pull gate

ADR-0002 gates each debt-servicing feature on *"is this debt actually accumulating? show the
signal."* The signal here is not a forecast: a real question was asked, the answer was
unavailable, and the cause was counted (44 images, 100–171 characters of text beside each). The
director declared the gate **fired** on 2026-08-08 and ruled that **khala absorbs the friction**
rather than asking the organisation to retype its tables. This ADR records that declaration, which
ADR-0002 requires be recorded in the direction's first record.

## Decision

**Machine-read text from an image is admissible as evidence, at a lower provenance tier, and the
tier must travel with it.**

### 0. This is a different axis from the governance tier, and Nexus holds it

ADR-0006 records, following ADR-0004, that *"tier derivation stays in Arbiter — Nexus holds no tier
registry."* That sentence is about the **governance** tier — memo versus canonical, `doc_type`,
what a document *counts as* in the organisation. Deriving that stays in Arbiter and this ADR does
not touch it.

What this ADR introduces is a second, orthogonal axis: **how the text came to exist**. It is a
property of a chunk, produced at ingest, not a judgement about the document's standing. A canonical
document can contain machine-read text; a memo can be entirely authored.

**Director's ruling, 2026-08-09: Nexus holds the provenance tier.** It is stored beside the chunk,
because it must be known wherever the chunk is used and Nexus is what uses chunks. **ADR-0006's
sentence is hereby narrowed to governance tiers**; it does not extend to provenance, and a reader
who took it to cover both should read this paragraph as the correction.

### 1. Admissible

A machine reading of a screenshot is evidence about the document, in the same sense a chunk is. It
is derived — but so is every chunk, since chunking, normalisation and search-text construction are
transforms already trusted.

**The difference is rate and magnitude, not kind.** Existing transforms can also surface text no
author wrote: on 2026-08-08 a snippet-boundary limit sent a truncated table to the prompt, and a
citation parser mangled a title into something that appeared nowhere. Extraction is not
categorically novel; it is *far more likely* to produce a plausible sentence the author never
wrote, and that difference in likelihood is what the tier prices.

### 2. Of a lower tier

Never presented as equal to authored text. The distinction changes what a reader should do:

| | authored text | machine-read text |
|---|---|---|
| failure mode | the author was wrong | the author was right and **the reader invented** |
| recourse | supersede the document | re-read the image |
| what a citation promises | a person wrote this | a machine read this from an image a person made |

### 3. Representation, and what it applies to

* **Field**: a provenance tier stored per **chunk**, non-nullable.
* **Values**: `authored` | `machine_read`. Two values now. Audio, spreadsheets and scanned PDFs
  would extend the set, and the field is defined as an enum so that extension is a migration
  rather than a reinterpretation.
* **Granularity is the chunk, so extracted text is chunked separately.** Images sit beside
  headings and bullets, so the natural chunk mixes both. A mixed chunk cannot carry an honest
  single value — labelling it `authored` launders extracted text upward, labelling it
  `machine_read` defames the author's prose. **Extracted text therefore forms its own chunks**,
  and no chunk may contain both kinds.
* **Absence is impossible, not defaulted.** The column is `NOT NULL`. Existing chunks are
  backfilled `authored`, which is true of every chunk indexed before this decision. A consumer
  that cannot read the field **must not** present the text as authored.

### 4. The tier travels — to these surfaces, named

A tier that exists only in the ingest pipeline is not a tier. It must survive, and an
implementation is conformant only if it survives at every one of:

1. chunking and storage
2. the search result (`SearchHit`)
3. the evidence packet, and therefore the LLM prompt
4. the citation attached to an answer
5. the API response (`/search`, `/search/answer`) and thereby the web client
6. the agent surfaces — MCP tool results and the A2A evidence payload

**Acceptance**: a test per hop asserting the value is present and correct for a machine-read chunk.
If any hop strips it, the guarantee is gone and the reader cannot tell the two apart — worse than
not extracting, because it converts a known gap into an unmarked claim.

### 5. Extraction is stable, or it is not used

ADR-0006's spine depends on determinism in three places: `content_hash` idempotency on re-ingest,
re-embedding **only when `chunk_text` actually changed** (`IS DISTINCT FROM`), and entropy signal ②
(cross-URI `content_hash` collisions as exact-dup candidates). A machine reader is not
deterministic; re-running it on the same image can drift by a character.

Left alone, that drift would make every image-bearing document look changed on every ingest, force
needless re-embedding, and poison signal ②. So:

* **The same image bytes must yield the same stored text.** The mechanism is a cache keyed by the
  image bytes **and** by the extractor identity and prompt version — a key that omits the extractor
  would serve old output under a new model's name.
* **Unchanged bytes are never re-extracted.** Re-ingest reads the cache. Extraction runs on new or
  changed bytes only.
* **Changing extractor or prompt is a migration**, not a silent re-read: it changes the key, and
  the resulting churn is a deliberate act with a recorded reason.

### 6. Extraction precedes scanning

The quarantine scanner must see the **extracted text**, not the opaque image bytes. Extraction runs
first; its output enters `ingest/scanner.py` and the quarantine gate on the same terms as any other
document content. The screenshot examined during this work contains a work email address visible
only in pixels — precisely the case that slips through if the order is left unstated.

### 7. No extraction is committed before the tier exists

Extraction must not land in any corpus until §3's field and §4's six hops are in place. This is an
invariant, not a trigger: a corpus containing unmarked machine-read text is the outcome §4 calls
worse than not extracting at all.

## What this does not decide

- **Which extractor.** Model, cost, speed, local versus hosted — the SPEC's. This ADR constrains
  extractors only by §5 (stability) and §6 (ordering).
- **That invention is acceptable.** It is not. A tier is not a licence to hallucinate; it is what
  remains true after the SPEC's controls have worked.
- **That images are the last case.** Named only because only images have been measured.

## Consequences

**ADR-0002's integrity layer is widened, not weakened.** "Grounded" admits a second tier, and the
guarantee changes from *every citation points at authored text* to *every citation states which
kind of text it points at*. That is a stronger obligation, over six hops rather than one refusal at
the door.

**Quarantine is unaffected**, and §6 fixes the ordering that makes that true.

**A new failure mode enters the trust model.** Text extracted from an image is text an attacker can
place in an image. ADR-0006 already treats ingested content as untrusted; this ADR does not relax
it, and the SPEC must bound a reader that has file access. The SPEC's critique found two real
defects there and they remain the SPEC's to fix.

**The evidence for the benefit arrives after the change.** No measurement exists of answer quality
on image-carried policy, because the labels were authored from text only and new labels must be
authored *after* extraction so their author reads what a user reads. This is a genuine weakness in
the decision's falsifiability and is not argued away: it is bounded instead by §Open items, which
requires an invention-rate sample before any commit, and by the fact that extraction is reversible
— the cache and the tier make machine-read text identifiable and removable.

## Alternatives considered

**Refuse: index only authored text.** Honest, cheap, and what the system does today. Rejected
because the policy this corpus exists to serve is in the screenshots, and because the refusal is
invisible: "not found" reads identically whether the fact is absent or merely unreadable.

**Admit at equal tier.** Simplest; no marker, no plumbing. Rejected because it converts a known
unreliability into an unmarked claim, and the failure mode is invention — the one wrongness a
reader cannot detect from the answer.

**Ask the organisation to retype.** Correct in principle and the fastest path to authored text.
Rejected by the director: it moves friction onto the organisation. Recorded because it stays
available, and because a retyped document is strictly better evidence than one khala reads.

## Open items

| item | owner | trigger |
|---|---|---|
| Invention rate is unmeasured — the extractor comparison rests on one screenshot (n=1). A sample large enough to state a rate, read by a human, is owed **before any extraction is committed to a corpus** | LivingLikeKrillin | Before the first extraction is committed |
| "Zero captions" is measured for 11 of 44 images and assumed for the rest | LivingLikeKrillin | The extraction run, which reads all 44 |
| No measurement of answer quality on image-carried policy; labels must be authored after extraction | LivingLikeKrillin | Labels authored against extracted content |
| How much of the corpus is machine-read should be countable and visible, but unit, surface and threshold are undefined | LivingLikeKrillin | The first surface that reports corpus composition |
