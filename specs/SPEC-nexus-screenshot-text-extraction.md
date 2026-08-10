---
id: SPEC-nexus-screenshot-text-extraction
type: spec
title: Read the policy that lives inside screenshots — khala absorbs the friction,
  the organisation does not retype its documents
status: approved
linked_adrs:
- ADR-0002
- ADR-0004
- ADR-0006
- ADR-0010
tags:
- nexus
- ingest
- vision
- grounding
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-10T05:52:47Z'
content_hash: sha256:173429db2a4510118e952a280f2bbda737d1fe9702fe93b7fddfa8f606b1c76d
---

## 1. What prompted it

The partner corpus was ingested, measured, and answered against for a full day before anyone
looked at what fraction of the policy is actually text. On 2026-08-08, asked for the point
thresholds that unlock each avatar, the system answered *"각 아바타별 구체적인 해금 포인트 수치는
제공된 문서에서 확인되지 않습니다"* — which was correct, and correct for a reason nobody had
counted.

Measured over the live tenant (116 documents, 289 chunks):

| document | body text | images | text per image |
|---|---:|---:|---:|
| policy A | 1,478 | 11 | 134 |
| policy B | 1,128 | 11 | 103 |
| policy C | 999 | 10 | 100 |
| policy D | 1,025 | 6 | 171 |
| policy E | 695 | 6 | 116 |

**Five documents carry 44 screenshots.** Captions were read from the Notion API for **one
document's 11 images: 0 of 11**; the other 33 are not measured and zero is assumed for them. The
text beside each image was a heading or a bullet **in the one document a human opened**; that the
specification is in the pixels is established for that document and is an inference for the other
four. [[ADR-0010]] bounds both claims the same way, and §7.1's step 0 is what closes the gap before
anything ships. Everything §8 of
`KOREAN_SEARCH_QUALITY.md` measured — answer quality 40/40 — was measured against the text that
exists, and the labels were authored by an agent that could only read that text. **The ruler never
pointed at the images.**

`KOREAN_SEARCH_QUALITY.md` §3.2 predicted exactly this shape and deferred it: *"표를 스크린샷으로
붙이면 검색 텍스트가 사실상 0인데 경고가 없다."*

**The disposition is a khala-philosophy question, and it was settled by the director on
2026-08-08.** Asking the organisation to retype its tables would move the friction onto the
organisation, which is the opposite of what this product is for. khala absorbs it.

## 2. What was measured before choosing

One screenshot was read by a human first and its contents recorded, so that a machine reading
could be scored rather than admired. Pre-registered criteria, fixed before any model ran:

    pass     screen id, version, the rule sentence, and both table attribute names
    partial  rule sentence and table attributes, small print missed
    fail     table structure collapses, Korean garbles, or content is invented

`partial` was declared usable in advance, on the ground that policy questions ask about rules and
attributes, not document version numbers. **Inventing content is failure at any score** — extracted
text becomes document body, and a fabrication would later be cited.

| path | criteria | per image | 44 images | cost |
|---|---:|---:|---:|---|
| `qwen2.5vl:7b` (CPU) | 3/5 partial | 522 s | 6 h 23 m | free |
| `qwen2.5vl:3b` (CPU) | 3/5 partial | 230 s | 2 h 49 m | free |
| `granite3.2-vision:2b` | — | — | — | **cannot run**: 16k context, the image is 59k tokens |
| **`claude` CLI (subscription)** | **5/5 pass** | **19 s** | **~14 m** | no API credit |

Neither local model invented anything, which is the result that matters most. Both lost the small
grey header strip carrying the screen id and version. The CLI read it.

The machine this was measured on has no discrete GPU (Intel Arc integrated, no CUDA, and the
Ollama container has no GPU device passed to it at all), so the local numbers are CPU numbers. On
an RTX 4060 Ti 8GB the 3b model fits entirely in VRAM and would be far faster — **estimated, not
measured**, and an earlier estimate in this work was wrong by 9x.

## 3. Decision

**Extract at ingest, through the Anthropic API with the image inlined as base64 — no tools, no
filesystem, no CLI.**

**The extractor is named, because half of §4.3's identity and half of §4.4's cache key are made of
it.** Model: `NEXUS_VISION_MODEL`, pinned to its own literal default (`claude-sonnet-4-6`) and
**deliberately not** an alias of `LLMService.DEFAULT_MODEL`. An earlier draft shared that constant
so "one EOL migration moves both" — but half of `extractor_identity` is the model id, so bumping
the *answer* model would silently change the *extractor's* identity, invalidate every stored
extraction, and trigger a mass re-read of 44 images as a side effect of an unrelated change. The
two lifecycles are separate and the constants must be too. Prompt: a module constant in
`ingest/vision.py`, and `prompt_sha` is the first 8 hex of its SHA-256, derived from the string
actually sent rather than hand-maintained — the same rule `sufficiency_judge` follows, for the same
reason. Changing either changes the identity, which by [[ADR-0010]] §5 makes it a migration.

An earlier draft chose the `claude` CLI with `--allowed-tools Read`, on the ground that the
subscription costs no API credit. **That choice is withdrawn**, for two reasons that arrived
independently:

* **[[ADR-0010]] §6, now accepted, forbids it.** The reader must have "no tools and no filesystem…
  It may not read paths, fetch URLs, or execute anything", because extraction runs *ahead* of the
  quarantine gate on attacker-controllable bytes. `--allowed-tools Read` grants exactly the
  capability that ordering makes dangerous: a reader that can open any path the ingest host user
  can. "One file, named explicitly, per invocation" was a **prompt convention, not a control** —
  and a Read-based control cannot even be tested for the attack it targets, since the attack *is*
  a Read call.
* **The director ruled for the external API** (2026-08-09), so the constraint that motivated the
  CLI does not bind.

With the image inlined in the request there is no tool surface at all. The blast radius is not
argued; it is absent.

### 3.1 What this costs, and what it does not decide

**Bounded, because an unbounded reader is an unbounded bill.** Three limits, all enforced rather
than advised: `max_tokens` per image (**2048** — a dense spec table transcribes well inside it),
a cap on stored extracted characters per image (**8000**, beyond which the extraction is truncated
and the chunk marked as truncated rather than silently shortened), and a per-ingest ceiling on
images extracted (`NEXUS_VISION_MAX_PER_INGEST`, default **100**) so one malformed document cannot
walk a corpus of images. The sufficiency signal shipped without a spend instrument and drew the
same criticism; it is cheaper to state the numbers than to discover them.

Paid API credit, per image, once. The 44 images are a **first-run** cost — §4.4's cache means a
re-ingest of unchanged documents extracts nothing.

This does not decide the local path. §2's measurement (3/5 partial, header strip lost, nothing
invented) stands as the recorded alternative for the moment an organisation runs khala itself and
cannot send screenshots to a provider. That moment has its own decision.

## 4. Design

### 4.1 Where it runs

At ingest, in the Notion converter, where an `image` block is currently rendered as `![caption]()`.
The URL is dropped there for good reason — presigned, one-hour expiry, and 99% of the largest chunk
by character count — so the bytes must be fetched **during** the walk, while the URL is still valid.

### 4.2 The reader is bounded by construction

Three properties, each a consequence of the transport rather than a rule someone must follow:

* **No tools.** The request carries a system prompt, an image block, and nothing else. There is no
  tool definition in it, so there is no tool call to make.
* **No filesystem.** Bytes are passed in memory. The reader is never told a path and has no
  mechanism to open one.
* **One image per invocation.** The request contains a single image block and no other document,
  tenant, or corpus state.

This is [[ADR-0010]] §6's three constraints, satisfied structurally. An injected instruction inside
an image can still make the *extracted text* say anything — that is §4.6 — but it cannot make the
reader **do** anything.

### 4.3 What is stored — and extracted text never shares a chunk with authored text

[[ADR-0010]] §3 is explicit: *"Extracted text therefore forms its own chunks, and no chunk may
contain both kinds."* An earlier draft of this SPEC said extracted text "replaces the empty
placeholder" inline in the converted markdown — which puts it in the same body as the surrounding
heading and bullet, and the chunker would then produce exactly the mixed chunk the ADR forbids.
Labelling that chunk `authored` launders the extraction upward; labelling it `machine_read` defames
the author's prose. Neither is available.

So the converter emits the extraction as a **delimited block that the chunker treats as a hard
boundary**:

    ![](){: derived=vision extractor=<model>/<prompt_sha> }
    <!-- khala:vision:begin -->
    > (그림에서 읽은 내용)
    > …extracted markdown…
    <!-- khala:vision:end -->

**No timestamp in the body.** An earlier draft put `at=<iso8601>` in the marker. Since the block
enters `content_hash`, that alone would change the hash on every extraction and make every
image-bearing document look modified on every ingest — the exact churn [[ADR-0010]] §5 exists to
prevent, introduced by the field meant to document it. `at` lives in §4.4's durable table, where it
is a fact about the extraction rather than part of the document.

**The delimiters are stripped from extracted text before the block is assembled.** They are literal
strings in the same channel the reader writes, so an image containing
`<!-- khala:vision:end -->` would otherwise close the block early and put the rest of its own
output into an *authored* chunk — a boundary injection that laundries machine text upward, which is
precisely what §4.3 exists to stop. Any occurrence of either marker in extracted text is removed
(not escaped — the extracted text has no legitimate use for them), and §7.2.13 asserts it with an
image whose content is the end marker.

**Both directions, not one.** An earlier draft sanitised only the extracted side. Authored source
text can carry the markers too — a Notion page, an external spec, or a filesystem doc containing
`<!-- khala:vision:begin -->` would open a block the converter never opened and tier its own
authored prose as `machine_read`, which defames the author exactly as the mixed chunk laundered the
machine. **The markers are stripped from authored body text at convert time as well.**

The order is fixed and load-bearing, because the chunker splits at markers *unconditionally*:
**(1)** strip markers from authored source text, **(2)** strip them from extracted text,
**(3)** assemble the vision block, **(4)** chunk. By the time the chunker runs, the only markers in
the body are the ones the converter wrote in step 3. §7.2.15 asserts the authored direction.

The chunker splits at both markers, unconditionally, before any size-based splitting. A vision
block larger than the chunk bound splits into several chunks — all `machine_read`, never merged
with a neighbour. Test §7.2.11 asserts no chunk ever carries both kinds.

**Consequence for `content_hash`, which [[ADR-0010]] §5 leaves to this SPEC:** the block sits in the
document body, and `content_hash` is computed over the frontmatter-stripped body
(`ingest/collector.py`), so extracted text **does** enter it. That is the choice made here, and it
is the safe direction: an image whose bytes change produces a changed body and a re-ingest that
notices. It is only safe because §4.4's invariant holds — unchanged bytes under an unchanged
extractor never produce different text, so a re-ingest of an untouched document is still a no-op.

[[ADR-0010]] §3.1 requires three durable fields per chunk, not one. An earlier draft stored the
tier alone:

| field | why one is not enough |
|---|---|
| `provenance_tier` = `machine_read` | says *how* the text came to exist |
| `extractor_identity` = `{model}/{prompt_sha}` | ADR §5 calls changing the extractor "a migration" — and a migration must be able to **enumerate what it invalidates**. Without this, a recall cannot be scoped and a disputed sentence cannot be attributed |
| `source_ref` = source URI + block id + image byte sha256 | ADR §2's recourse is *re-read the image at its source*. Nexus is the index, not the store (ADR-0004), and Notion URLs expire within the hour. The byte hash proves **which** image was read; it cannot fetch it |

### 4.4 Cache — keyed by bytes **and** extractor identity

`(tenant, image_sha256, extractor_identity)`. An earlier draft keyed on bytes alone and a test
cemented it.
That key serves text produced by the old model under the new model's name — §4.3's marker would
record an `extractor` that did not produce the stored content.

The invariant is on the stored text, not on the cache ([[ADR-0010]] §5): **an extraction result,
once stored, is never replaced by a re-read of the same bytes under the same extractor identity.**
Losing the cache must be a performance event, never a content event.

That requires the store to be **durable, not a cache** in the evictable sense: a table,
`vision_extractions(tenant, image_sha256, extractor_identity, text, at)`, with the **triple** as
its primary key and no eviction policy.

**`tenant` is in the key, and that is not an optimisation.** An earlier draft keyed on
(bytes, identity) alone, making the store global while every other part of the index is
tenant-scoped (ADR-0006 identifies documents as `{tenant}:{filename}`). Byte-identical images are
not rare — the same UI screenshot, the same template — so a global store would serve one tenant's
extracted text to another, **including text that the first tenant's quarantine gate rejected**, and
would leak the existence of an image across the boundary. The duplicate extraction cost is the
price of the boundary, and it is small.

**The scanner runs before the durable write.** Extracted text is scanned and gated *first*; only
text that passes is stored. Ordering matters more than the backstop below: text that never enters
the table cannot be missed by a later sweep.

**Deletion is the backstop, and it is the one named exception to §4.4's invariant.** For content
quarantined after the fact — a scanner rule added later, a re-classification — the
`vision_extractions` row is **deleted**. The invariant forbids *replacing* stored text with drifted
text under an unchanged identity; deletion removes rather than rewrites, and a later ingest
re-extracts and is gated again by the same scanner, so nothing drifted is ever served as if it were
the original. Leaving quarantined PII in a durable store the gate cannot reach was the worse
option. §7.2.16 asserts the row is gone. An earlier draft called it a cache and stated the invariant anyway,
which leaves the spine resting on retention: one miss re-runs a non-deterministic reader and lands
drifted text under an **unchanged** identity, invisible precisely because the identity did not move.
The migration in §6 creates it; §7.2.8 asserts the second read never re-extracts.

### 4.5 The tier travels — six hops

[[ADR-0010]] §4 names six surfaces and conformance is a test per hop:

1. chunking and storage
2. the `SearchHit`
3. the evidence packet, and therefore the prompt
4. the citation
5. the API response (`/search`, `/search/answer`) and thereby the web client
6. **MCP tool results**

An earlier draft of this SPEC listed five and dropped MCP together with A2A. That was a mistake:
ADR-0010 removes only **A2A** from the list — ADR-0004 keeps that surface minimal until a consumer
pulls it — and MCP stays, because it is a live agent surface today. Dropping a hop is the failure
ADR-0010 §4 calls worse than not extracting: it converts a known gap into an unmarked claim.

### 4.6 Quarantine, and what extraction can and cannot do

Extracted text passes `ingest/scanner.py` and the quarantine gate on the same terms as any other
document content. The screenshot examined in §2 contains a work email address visible only in
pixels — the case that slips through if the ordering is left unstated.

What remains, stated rather than assumed away: an image containing *"ignore previous instructions…"*
produces extracted text containing that sentence, which becomes document body. Per §4.2 the reader
cannot act on it. Per [[ADR-0010]] §6 this is **not a new exposure class** — every ingested document
already reaches the answer prompt — but it is a new *channel*: text a human reviewing the document
would not see. The tier is what keeps that channel labelled.

## 5. What this does not do

* **It does not read images for the answer path.** Extraction happens once, at ingest. The answer
  path sees text like any other text.
* **It does not describe pictures.** The target is text rendered inside an image — tables, labelled
  UI, spec rows. A photograph or an unlabelled diagram yields little, and the honest outcome there
  is a short extraction, not an invented description.
* **It does not fix the labels.** Pack B labels were authored from text only. Whether answer
  quality on image-carried policy is good stays **unmeasured** until §7.1's labels exist.

## 6. Ships

    nexus/nexus/ingest/vision.py                   the reader (API, base64, no tools) + durable store
    nexus/nexus/ingest/sources/notion_convert.py   image block → fetch, extract, marker block
    nexus/nexus/ingest/chunker.py                  hard split at the markers; no mixed chunk (hop 1)
    nexus/nexus/ingest/pipeline.py                 scanner/gate before the durable write; tier persisted
    nexus/nexus/search/hybrid.py                   tier on SearchHit (hop 2)
    nexus/nexus/search/evidence_packet.py          tier into the packet and the prompt (hop 3)
    nexus/nexus/llm/citations.py                   tier on the citation (hop 4)
    nexus/nexus/api.py                             tier in the response (hop 5)
    nexus/nexus/mcp/server.py                      tier in MCP tool results (hop 6)
    nexus/migrations/0NN_provenance_tier.sql       tier + extractor identity + source ref; backfill authored
    nexus/migrations/0NN_vision_extractions.sql    durable store, PK (tenant, image_sha256, extractor_identity)

An earlier draft listed four files. Six hops touch nine, and a ships list that omits half the
change is how a hop gets dropped — which §4.5 calls worse than not extracting.

## 7. Acceptance — the question that prompted this must be answerable

**Nothing here counts as success until the §1 question is answered.** An earlier draft's tests could
all pass while *"각 아바타별 해금 포인트 수치"* still returned "not found", which means they measured
the machinery and not the work.

### 7.1 The pre-registered gate, fixed before any extraction is read

Written down now, because a threshold chosen after seeing output ratifies whatever the output was:

* **Step 0b — the recourse must work.** [[ADR-0010]] §2 admits machine-read text *because* a reader
  can re-read the image at its source; §3.1 says that without a re-resolvable reference the tier is
  "a label with nothing behind it". So a working re-fetch is demonstrated **from a stored
  `source_ref` alone** for at least one image per document, before extraction is committed. §8
  records why this is in doubt (`canonical_uri` is basename-only; Notion URLs expire in an hour).
  If it cannot be demonstrated, the tier's justification fails and extraction does not ship.
* **Sample**: **8 of the 44 images**, drawn across all five documents, each read by a human and its
  contents recorded **before** the machine reading is looked at.
* **Invention**: **zero tolerance.** One non-trivial line of extracted text that does not appear in
  the image fails the sample outright and extraction is not committed. **"Non-trivial line"** is
  fixed here rather than after the reading: a line carrying at least one of a number, a proper
  noun, a table cell value, or a rule clause. Punctuation, whitespace, markdown scaffolding
  (`|---|`), and repeated headers are trivial. A disagreement about whether a line is trivial is
  resolved as **non-trivial**. Fabrication becomes document
  body and is later cited as grounded; there is no acceptable rate.
* **Fidelity**: **≥ 6 of 8** at `pass` or `partial` on §2's pre-registered scale.
* **The motivating question**: after extraction, `nexus query "각 아바타별 해금 포인트 수치"` returns
  the thresholds, with a citation carrying `machine_read`.

  **The pass condition is a label, not a reading.** "Returns the thresholds" is scored by the
  existing Korean answer-quality harness: the values recorded in step 0's human survey become a
  label with `must_contain` entries, and the motivating question is judged by the same deterministic
  ruler as everything else rather than by someone reading the answer and nodding.

  **Step 0, before any of the above: confirm the thresholds are in an image at all.** ADR-0010's
  Context bounds this — one document's images were opened by a human, and "the policy is the
  screenshots" is an *inference* for the other four. If no image renders the per-avatar thresholds,
  this criterion fails for a reason that has nothing to do with extraction quality, and the honest
  response is to say so rather than to blame the reader. So the 8-image sample is drawn to
  **include** whichever images the human survey finds carrying the thresholds; if the survey finds
  none, extraction may still be worth building but **this SPEC's acceptance criterion is void and
  must be replaced before it ships.**

**What an 8-image sample does not buy.** A clean sample places **no bound on invention in the 36
unread images**, and §8 concedes there is no path to correct a single invented chunk once stored.
That combination is the sharpest edge in this SPEC, and it is not resolved by sampling harder. Two
things make it survivable, and both are required rather than recommended:

* **The tier is a label, and a label is the most Nexus can owe.** Every extracted chunk is marked
  `machine_read` at all six hops, so an invented sentence is never *presented by Nexus* as
  authored. Calling that "containment", as an earlier draft did, overstates it: [[ADR-0010]] keeps
  ADR-0001's boundary — Nexus emits and cannot force a consumer to read the tier. What is owed is
  that no consumer ever has to guess.
* **Recall is bulk, and it moves the identity.** Until §8's correction path exists, the remedy for
  a discovered invention is to re-extract **under a new `extractor_identity`** — bump the prompt,
  which moves `prompt_sha`, which by [[ADR-0010]] §5 makes it a migration with a recorded reason.
  Re-extracting under the *same* identity would store different text for the same
  (bytes, identity) pair and break §4.4's invariant, which an earlier draft's wording would have
  done. Coarse, and cheap enough at 44 images that coarse is acceptable.

n=1 chose the reader; n=8 decides whether it ships.

**And the n=1 does not even transfer.** §2's "5/5 pass, 19 s" was measured on the `claude` CLI,
which §3 withdraws: the shipped reader is a different transport, a different system prompt, and no
tools. That measurement selected a *vendor*, not the thing being shipped, and §7.1's sample must
therefore run **on the shipped path** — same model id, same prompt, same base64 request — or it
measures something else again. §2's "neither local model invented anything" is likewise a claim
from one image and is not evidence of a no-invention property.

### 7.2 Tests — all runnable in CI

The reader is stubbed at the `LLMService` boundary, so no test needs an authenticated CLI or a live
API. An earlier draft's three primary controls required both and would have been skipped forever,
which in this repo means they would not exist.

1. **The fixture is synthetic.** A generated PNG containing a known table, a known rule sentence,
   and a **synthetic** email address — committed to the repo. The §2 screenshot is **not**
   committed: it carries partner PII and an organisational fingerprint into a public repo whose CI
   scans every commit for exactly that.
2. **The pipeline transcribes what the reader returned** — every non-trivial extracted line appears
   in the fixture's recorded contents, and a stub that summarises fails. **This does not establish
   no-invention** and its name must not suggest it does: the reader is stubbed, so what is proven
   is that nothing between the reader and the chunk adds or drops text. No-invention is established
   only by §7.1's human-read sample against the shipped transport.
3. **The request carries no tool definitions**, asserted on the outgoing payload. This is §4.2, and
   it is the control an earlier draft could not write: its test asserted "no tool call other than
   `Read`", while the attack it targeted *was* a Read call.
4. **The request carries exactly one image block** and no path, URL, or filesystem reference.
5. **An injected instruction inside the image becomes content, not direction** — the extracted text
   contains the string, and the outgoing request for the *next* image is unchanged by it.
6. **PII in an image is quarantined** on the same terms as PII in prose. The bypass test.
7. **The tier survives all six hops** of §4.5 — one assertion per hop, MCP included.
8. **The cache is keyed by (bytes, extractor identity).** Same bytes under a new identity
   re-extract; same bytes under the same identity never do.
9. **Extraction failure degrades, it does not abort.** One unreadable image leaves the rest of the
   document indexed, as an embedding refusal does today — and **the failure is recorded** in
   `vision_extractions` as a failure row for that (tenant, bytes, identity) — **fetch failure and
   extraction failure alike**, since a presigned URL that expired mid-walk produces the same
   silently-different body as a reader that refused. Without it the body
   silently differs between a failed ingest (bare `![]()`) and a later successful one (with the
   block), `content_hash` flips, and the document reads as edited when nothing was edited. With it,
   a retry is an explicit act — deleting the failure row — rather than something that happens
   whenever the presigned URL cooperates. Failure rows are **sticky by design**, so one transient
   network error leaves an image unextracted until a human deletes the row — which must be visible
   rather than silent: the ingest summary reports the failure-row count beside the extraction
   count.
10. **A pre-ADR chunk reads `authored`** after the migration's backfill.
11. **No chunk carries both kinds.** A document whose image sits between a heading and a bullet
    produces authored chunks and `machine_read` chunks, never one containing both — [[ADR-0010]]
    §3's rule, and the one an earlier draft's inline placement would have broken silently.
12. **A vision block larger than the chunk bound splits into `machine_read` chunks only**, never
    merging with an authored neighbour at the boundary.
13. **An image whose text *is* the end marker cannot close the block early** — the markers are
    stripped from extracted text, and the following authored content stays `authored` while the
    extraction stays `machine_read`. The boundary-injection control.
15. **Authored text containing a vision marker is stripped**, so no authored prose can be tiered
    `machine_read` by writing a comment. The other direction of §4.3's sanitisation.
16. **Quarantining extracted text deletes its `vision_extractions` row**, so PII read from an image
    does not survive in a durable store the quarantine gate cannot reach.
14. **Re-extracting the same bytes produces no body change** — no timestamp rides in the block, so
    `content_hash` is stable across a second ingest of an untouched document.

## 8. Open items

* **Correcting a single invented chunk has no path.** ADR-0010 §5 freezes stored text for a given
  (bytes, identity) while §3.1 justifies identity by the need to scope a recall — and recall implies
  replacement. Deferred at ADR approval as this SPEC's to answer, and it is not answered here.
* **Re-resolving the source reference is unverified.** `canonical_uri` is basename-only and ADR-0006
  calls it too coarse; Notion URLs expire. A working re-fetch must be demonstrated before extraction
  is committed, or §4.3's recourse is a label with nothing behind it.
* **Separate chunks lose their referent.** ADR-0010 §3 requires extracted text to form its own
  chunks, which strips the 100–171 characters of authored heading that say what the image depicts —
  the context retrieval needs. A context prefix carrying the authored heading is the obvious
  candidate and is unmeasured.
* **The labels do not point here.** Labels authored against extracted content are owed, and must be
  authored **after** extraction so their author reads what a user reads.
* **Step 0b proves the reference resolves *today*.** ADR-0010 §2's recourse promises it resolves
  for the life of the chunk, and that depends on the source system keeping the block — which Nexus
  does not control. A demonstrated re-fetch falsifies the design early; it does not make the
  recourse durable.
* **The vision model's EOL is now a separate thing to remember.** Pinning `NEXUS_VISION_MODEL` to
  its own literal is what stops an answer-model bump from invalidating every extraction — the cost
  is that nothing else moves it, and an unmaintained default is a quiet way to keep reading with a
  retired model.
* **Small print.** Both local models lost the header strip; the API reader read it. If the local
  path is ever taken up, "small print is not reliably read" belongs in the tier, not in a comment.
