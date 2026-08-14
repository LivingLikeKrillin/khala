---
id: ADR-0010
type: adr
title: Machine-read text from images is evidence, of a lower tier — and the tier must
  travel with it
status: accepted
retractions:
- SPEC-nexus-vision-reproducibility
- SPEC-nexus-screenshot-text-extraction
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
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-10T05:04:11Z'
content_hash: sha256:4be44a19f3cdb65303a1682b7ce6b38ce24c4555ea7b6208bb103501209259fb
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
  tenant. Five documents carry **44**; the other 111 produced none. *Placeholders surviving ingest
  and chunking is what was counted* — not images in the source. A Notion block type the converter
  renders without a placeholder would be invisible to this census, so "111 carry no images" is the
  stronger claim and is not the one the measurement supports.
* **Text per image** — body characters divided by image count: **100–171 characters**, a
  **per-document average**. A mean cannot establish the per-image distribution: one well-described
  image beside several bare ones averages the same. In the one document read by a human, the text
  adjacent to each image was a heading or a bullet; whether that holds for all 44 is not measured.
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

### 0. This is a different axis from the governance tier — and there was never a conflict

Earlier drafts spent a section narrowing ADR-0006's sentence, and one of them had a **draft ADR
"hereby" amending an accepted one**. Neither was needed. ADR-0006's actual words are:

> supersession governs the index, **`doc_type`** tier derivation stays in Arbiter — Nexus holds no
> tier registry

The qualifier is already there. That sentence is scoped to the **governance** tier — memo versus
canonical, what a document *counts as* in the organisation — and deriving that stays in Arbiter.
This ADR does not touch it, does not amend ADR-0006, and requires no edit to it.

What this ADR introduces is a second, orthogonal axis: **how the text came to exist**. It is a
property of a chunk produced at ingest, not a judgement about the document's standing. A canonical
document can contain machine-read text; a memo can be entirely authored.

**Director's ruling, 2026-08-09: Nexus holds the provenance tier.** It is stored beside the chunk,
because it must be known wherever the chunk is used and Nexus is what uses chunks. No registry is
created and no derivation moves out of Arbiter.

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
| recourse | supersede the document | re-read the image **at its source** (§3.1) |
| what a citation promises | a person wrote this | a machine read this from an image a person made |

### 3. Representation, and what it applies to

* **Field**: a provenance tier stored per **chunk**, non-nullable.
* **Values**: `authored` | `machine_read`. Two values now. Audio, spreadsheets and scanned PDFs
  would extend the set, and the field is defined as an enum so that extension is a migration
  rather than a reinterpretation.

#### 3.1 The tier alone is not enough — three fields, not one

A tier says *how* the text came to exist. Two more facts have to travel with it, and an earlier
draft stored neither:

* **Extractor identity** (`{model}/{prompt_sha}`) per chunk. §5 calls changing the extractor "a
  migration", but a migration must be able to **enumerate what it invalidates**. Without this you
  cannot list the chunks a rollback covers, cannot audit which model asserted a disputed sentence,
  and cannot scope a recall when an extractor is found to invent. The cache key already carries
  this; the durable record must too. (Nexus learned the same lesson recording `sufficiency_judge`
  beside a verdict: a value produced by a model is unreadable without the model's name.)
* **A re-resolvable source reference** — the source URI plus block id, plus the image byte hash
  used as the cache key. §2's recourse for machine-read text is *re-read the image*, and ADR-0004
  fixes Nexus as the **index, not the store**: it does not keep the bytes, and Notion's image URLs
  are time-limited signed links that expire within the hour. Without a reference that can be
  re-resolved at the source, the lower tier is a label with nothing behind it and §2's central
  promise is empty.

**The byte hash is not a substitute for the reference.** It proves *which* image was read; it
cannot fetch it. Both are stored.
* **Granularity is the chunk, so extracted text is chunked separately.** Images sit beside
  headings and bullets, so the natural chunk mixes both. A mixed chunk cannot carry an honest
  single value — labelling it `authored` launders extracted text upward, labelling it
  `machine_read` defames the author's prose. **Extracted text therefore forms its own chunks**,
  and no chunk may contain both kinds.
* **Absence is impossible, not defaulted.** The column is `NOT NULL`. Existing chunks are
  backfilled `authored` — see the caveat in §Open items, since the corpus has several intake paths
  and that claim is asserted rather than verified.
* **The obligation is on Nexus's surfaces, not on consumers.** An earlier draft said a consumer
  that cannot read the field "must not present the text as authored". Nexus cannot enforce that —
  ADR-0002 preserves ADR-0001's boundary: it *emits* evidence and cannot force a consumer to read
  it. What Nexus owes is that **every surface it controls carries the tier**, so no consumer is
  ever in the position of having to guess. A consumer that receives the tier and discards it has
  made its own choice, and that is the honest limit of what this decision can promise.

### 4. The tier travels — to these surfaces, named

A tier that exists only in the ingest pipeline is not a tier. It must survive, and an
implementation is conformant only if it survives at every one of:

1. chunking and storage
2. the search result (`SearchHit`)
3. the evidence packet, and therefore the LLM prompt
4. the citation attached to an answer
5. the API response (`/search`, `/search/answer`) and thereby the web client
6. the MCP tool results

**A2A is deliberately not on that list.** An earlier draft made extending the A2A evidence payload
a conformance condition, which would have forced the one extension ADR-0004 forbids: A2A "has no
active consumer today… stays minimal and is not extended until a real agent pulls it". No consumer
is named here, so requiring it would have made this ADR the puller — by fiat. The rule instead:
**if A2A ever carries evidence, it carries the tier**, and that obligation attaches when a consumer
pulls the surface, not now.

**Acceptance**: a test per hop asserting the value is present and correct for a machine-read chunk.
If any hop strips it, the guarantee is gone and the reader cannot tell the two apart — worse than
not extracting, because it converts a known gap into an unmarked claim.

### 5. Extraction is stable, or it is not used

ADR-0006's spine depends on determinism in three places: `content_hash` idempotency on re-ingest,
re-embedding **only when `chunk_text` actually changed** (`IS DISTINCT FROM`), and entropy signal ②
(cross-URI `content_hash` collisions as exact-dup candidates). A machine reader is not
deterministic; re-running it on the same image can drift by a character.

**How far that reaches depends on a design choice this ADR does not make.** `content_hash` is
computed over the document **body** with frontmatter excluded (`ingest/collector.py`), not over
derived chunk text. So drift touches `content_hash` and signal ② **only if extracted text enters
the hashed body** — which it does if extraction rewrites the `![]()` placeholder in the converted
markdown, and does not if extracted chunks are attached after hashing. The re-embedding trigger
(`chunk_text` changed) is affected either way. The SPEC chooses the placement; whichever it
chooses, §5's invariant below is what keeps the choice safe.

Left alone, that drift would make every image-bearing document look changed on every ingest, force
needless re-embedding, and poison signal ②. So:

* **The invariant is on the stored text, not on a cache.** *Stored text for unchanged bytes never
  changes.* An earlier draft named a cache as the mechanism and stopped there, which leaves the
  spine resting on cache durability: a rebuild, an eviction, a retention policy or a new
  environment produces a miss, the miss re-runs a non-deterministic reader, and drifted text lands
  under an **unchanged** extractor identity — the exact churn §5 exists to prevent, now invisible
  because the identity did not move. So the requirement is stated on the durable side: **an
  extraction result, once stored, is never replaced by a re-read of the same bytes under the same
  extractor identity.** Whether a cache exists is the SPEC's business; losing one must be a
  performance event, never a content event.
* **Unchanged bytes are never re-extracted.** Re-ingest resolves the stored result by
  (byte hash, extractor identity). Extraction runs on new or changed bytes only.
* **Changing extractor or prompt is a migration**, not a silent re-read: it changes the key, and
  the resulting churn is a deliberate act with a recorded reason.

### 6. Extraction precedes scanning

The quarantine scanner must see the **extracted text**, not the opaque image bytes. Extraction runs
first; its output enters `ingest/scanner.py` and the quarantine gate on the same terms as any other
document content. The screenshot examined during this work contains a work email address visible
only in pixels — precisely the case that slips through if the order is left unstated.

**This ordering creates its own exposure, and an earlier draft left it unstated.** Running the
reader first means **attacker-controllable, unscanned bytes reach a model before the default-deny
gate** that ADR-0002 names as protecting the substrate. The order is still correct — a scanner
cannot read pixels, so scanning first would gate on nothing — but it is not free, and the cost is
paid by constraining the reader rather than by reordering:

* **The reader has no tools and no filesystem.** It receives image bytes and returns text. It may
  not read paths, fetch URLs, or execute anything. A reader with file access, prompted by text an
  attacker wrote into an image, is a file-exfiltration primitive that this ordering would place
  *ahead* of the quarantine gate.
* **No *code* branches on its output.** Extracted text goes into the same scanner every other
  ingested string does. It does reach the LLM prompt at §4 hop 3 — that is the point of extracting
  it — so "never interpreted as instruction" would be false as written and is not claimed. What is
  true is narrower and worth stating plainly: **prompt injection through retrieved evidence is a
  property Nexus already has**, since every ingested document reaches the same prompt, and this ADR
  neither creates nor fixes it. What extraction changes is the *channel*: text that a human
  reviewing the document would not see. §4's tier is what keeps that channel labelled.
* **The blast radius is one image.** A reader invocation sees one image's bytes and no other
  document, tenant, or corpus state.

These three are what make the ordering safe rather than merely necessary. The SPEC must implement
and test them; the ADR fixes them as the price of §6's order.

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

**Quarantine's coverage widens; its exposure also does.** §6's ordering is what lets the scanner
see pixel-only content it could never have read before — the work email address in the examined
screenshot is now catchable. The same ordering puts a reader in front of the default-deny gate, and
§6's three constraints (no tools, no filesystem, one image per invocation) are the price. Saying
"quarantine is unaffected", as an earlier draft did, was false in both directions.

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

* **A human-read sample is owed before any extraction is committed.** Size and an
  invention-rate threshold must be **pre-registered — written down before the sample is read**,
  since a threshold chosen after seeing the output ratifies whatever the output happened to be.
  This ADR does not set the numbers; the SPEC does, and it may not skip them. (An earlier draft
  pointed at "the extractor comparison", an artifact that appears nowhere in this document —
  extractor choice is deferred entirely.)

* **The backfill claim is unverified.** §3 backfills existing chunks `authored` and asserts that is
  true of every chunk indexed before this decision. It is not checked, and the corpus has several
  intake paths (`ingest-notion`, `ingest_external_spec`, filesystem docs) while §1 concedes
  existing transforms already surface text no author wrote. `authored` remains the only honest
  default available for text nobody can now re-derive, but it is a default, not a finding.

* **Corpus composition has no reporting surface, and this ADR does not create one.** If one is
  ever built, it reports the machine-read share; the unit and threshold are its own to define. An
  earlier draft made "the first surface that reports corpus composition" the *trigger* for defining
  those terms, which is a trigger nothing can observe.

* **Whether images are the last case is unknown.** Only images have been measured. Audio,
  spreadsheets and scanned PDFs would extend §3's enum, which is why it is an enum.
