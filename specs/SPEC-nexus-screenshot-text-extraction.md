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
reviewed_at: '2026-08-11T16:19:46Z'
content_hash: sha256:cb457b7ac1a06972c17ec1c15cbb2bd393730441b0f60109bc83f67686a39181
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

**This table selected a vendor; it is not a fidelity measurement.** It was scored by the
implementing agent against its own reading of one screenshot, which §7.1c disqualifies as an
independent reference. Neither local model invented anything *in that one image*, which is the
result that matters most and is n=1. Both lost the small
grey header strip carrying the screen id and version. The CLI read it.

The machine this was measured on has no discrete GPU (Intel Arc integrated, no CUDA, and the
Ollama container has no GPU device passed to it at all), so the local numbers are CPU numbers. On
an RTX 4060 Ti 8GB the 3b model fits entirely in VRAM and would be far faster — **estimated, not
measured**, and an earlier estimate in this work was wrong by 9x.

## 3. Decision

**Extract at ingest with the image inlined as base64, through a reader that has no tools and no
filesystem.** Two transports satisfy that, and the **`claude-code` bridge is the default** because
it costs no API credit.

**Correction (2026-08-10): an earlier revision of this section said "no CLI", and that was wrong.**
It withdrew the CLI because the way to hand it an image was a path plus the `Read` tool, which
[[ADR-0010]] §6 forbids. The objection was right about `Read` and wrong about the CLI: with
`--input-format stream-json` the image goes in as a base64 content block on stdin, with
`--allowed-tools ""` still set. No tool definitions, no path, one image. The constraint was on
**tools**, not on the transport, and the CLI has a path that opens neither door — I had not read
far enough into the CLI's own options.

Verified end to end on 2026-08-10 against a real policy screenshot: the reader transcribed the
full unlock-threshold table (12 tiers, three separate criteria) accurately through the bridge, with
every door closed and no API key.

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

### 3.0 Which transport, and what each costs

| transport | key | tools | when |
|---|---|---|---|
| **`claude-code` bridge** (default) | none — host `claude` auth | none (`--allowed-tools ""`) | dev and the dogfood deployment |
| Anthropic API | `ANTHROPIC_API_KEY` | none (no tool definitions in the request) | a deployment without a host `claude` |

Both inline the image as base64 and neither is given a path. The bridge is **dev-only** by the same
rule its docstring already carries — it needs an authenticated `claude` on the host, so it is not a
server backend and does not go in team or production compose.

One thing the bridge does not give: **`stop_reason`**. So a bridge-read extraction cannot tell
whether the model ran out of output budget mid-table. `read_image` records that as unknown rather
than assuming completion, and the API transport is what a deployment uses if that matters.

### 3.1 What this costs, and what it does not decide

**Bounded, because an unbounded reader is an unbounded bill.** All limits enforced rather than
advised:

* **`max_tokens` = 4096** per image, and **the response's `stop_reason` is recorded**. An earlier
  draft paired 2048 tokens with an 8000-character cap, which cannot both bind: 2048 tokens of
  Korean does not reach 8000 characters, so the truncation that was marked could never happen and
  the truncation that actually happens — the model running out of output budget mid-table — was
  invisible. A half-transcribed spec table would have travelled all six hops looking complete.
* **20,000 stored characters** per image, sized deliberately *above* what the token cap can emit,
  so it is a safety net for pathological output rather than the normal path. Either truncation
  marks the chunk; neither shortens it silently.
* **A fetch failure gets a key it can be recorded under.** The store is keyed by image bytes, and
  a failed fetch has none — which is the *most likely* failure, since §4.1 must download from a
  presigned URL that expires within the hour. Without a row, a failed ingest leaves a bare
  `![]()` and a later successful one adds the block, `content_hash` flips, and a document nobody
  edited reads as edited. So the key is derived deterministically from the **block id**, prefixed
  `unfetched:` so no reader mistakes it for a content hash.
* **`NEXUS_VISION_MAX_PER_INGEST` = 100 per run of the ingest command** — not per document. Past
  the ceiling, remaining images are left unextracted and recorded as failure rows, so the run is
  repeatable and the skipped images are visible rather than silently absent.
* **Token counts recorded per extraction** on the durable row. §3.1 criticised the sufficiency
  signal for shipping without a spend instrument and an earlier draft of this SPEC then did the
  same; this is the cheap version, and enough to answer *what did the first run cost*.

A limit nothing enforces is worse than no limit, because it reads as a control — the per-ingest
ceiling was defined and never wired.

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

**"Structurally" holds for one transport and not the other, and this section overstated it.** On the
API path the three properties really are consequences of the request: there is no tool field to
populate. On the `claude-code` bridge there is a full agent runtime on the other end and the
properties are **flags**, which is a weaker thing sitting ahead of the quarantine gate on
attacker-controllable bytes. The bridge therefore carries an invariant of its own, and it is pinned
by test rather than by intention (`tests/test_claude_llm_bridge.py` fixes the argv):

```
--allowed-tools ""        빈 allowlist = deny-all (print 모드에는 승인 절차가 없다)
--strict-mcp-config       사용자 전역 MCP 서버 무시
--setting-sources ""      프로젝트/유저 세팅·훅·스킬·CLAUDE.md 미로드
--no-session-persistence  문서 내용을 트랜스크립트에 안 남김
```

Any change that lets the bridge load host configuration reinstates the file-exfiltration primitive
§3 withdrew the `--allowed-tools Read` design for. The reader of record no longer uses this
transport (below), so the bridge's exposure today is dev-only — but the flags are load-bearing
wherever it runs.

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

**Trust is declared by the caller, not assumed from the path.** The chunker distrusts markers by
default and strips them; only a caller that wrote the block itself passes `trust_vision_markers=True`.
An earlier design stripped authored markers in the Notion converter alone — but filesystem documents
and `ingest_external_spec` payloads never pass through it, so a document of theirs containing the
begin marker would have had its author's own prose tiered `machine_read`. Defaulting to distrust
puts every current and future intake path on the safe side without anyone remembering to.

Within a trusted caller the order is fixed and load-bearing, because the chunker splits at markers
*unconditionally*:
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

**Deletion is a narrowing this SPEC makes**, not something [[ADR-0010]] §5 already allowed — the ADR
fixes the invariant on stored text and names no exception. It is permitted here because deletion
**removes rather than rewrites**: a later ingest re-extracts and passes the same gate, so nothing
drifted is served under an unchanged identity. The alternative was quarantined PII sitting in a
store the gate cannot reach.

That requires the store to be **durable, not a cache** in the evictable sense: a table,
`vision_extractions(tenant, image_sha256, extractor_identity, text, error, truncated, at)` with the
first three as its primary key and no eviction policy. (`error` and `truncated` were missing from an
earlier sketch of this schema; migration 013 carries them, and a schema without the failure columns
cannot express §7.2's failure tests.)

**Insert semantics: `ON CONFLICT DO NOTHING`.** Two concurrent ingests touching the same
byte-identical image within a tenant otherwise race on the durable write. First result wins, which
is precisely the invariant — a second read must never replace the first under the same identity.
**The losing writer discards its own extraction and reads the stored row back**, so both ingests
put the same text in their bodies; keeping its own would make `content_hash` depend on which
process won a race.

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
* **Sample**: **8 of the 44 images**, drawn across all five documents **from those the implementing
  agent has never opened**, each read by the director and recorded **before** the machine reading is
  looked at. No requirement about what the images contain — the sample measures transcription
  fidelity, and an earlier draft's rule (draw images carrying the thresholds) became unexecutable
  when step 0 established that none do.
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

  **Step 0 was run on 2026-08-10, and it failed.** Eleven images from the avatar-policy document
  were fetched and five opened. They are UI screen specifications — a header strip carrying
  screen path / ID / version, a rule box, and a 속성·형식·설명 table. Locks are drawn on avatar
  slots as UI state, but **no unlock condition or point value appears in any of them**, and the
  body text has none either: every `포인트` match in the corpus is `엔드포인트`. The motivating
  question most likely returned "not found" because the organisation has not written that rule
  down anywhere — not because it is trapped in an image.

  **So this criterion is void, exactly as step 0 was written to detect, and it is replaced in
  §7.1a.** Recording the failure rather than quietly swapping the question is the point: a
  pre-registered criterion that is changed after the fact has to leave a trace, or pre-registration
  means nothing.

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

### 7.1a-0 What step 0 does to ADR-0010's fired gate

[[ADR-0010]] recorded the demand-pull gate as **fired**, on this: *"a real question was asked, the
answer was unavailable, and the cause was counted (44 images, 100–171 characters of text beside
each)."* Step 0 falsifies the middle link. The answer was unavailable, and the cause was **not** the
images — the thresholds are in none of them, and none of the corpus text either. The most likely
explanation is that the rule was never written down.

**What survives, and it is not nothing.** The count stands: 44 images, 0 captions, 100–171
characters beside each, and five images opened confirm they carry screen ids, versions, rule
sentences and 속성 tables that appear **nowhere in the corpus text** — one of them a work email
address visible only in pixels. Policy content *is* trapped in images. What is no longer supported
is the specific causal claim that this question failed *because of* that.

The gate stays fired on the surviving evidence, and this section is the correction rather than a
quiet re-telling. **The ADR is accepted and hash-stamped, so it cannot be edited here**; a successor
note against it is owed, and §8 records that debt.

### 7.1a The replacement criterion, and why this one is answerable

Chosen by the director on 2026-08-10 **from what the images were measured to contain**, not from
what would be convenient:

> **Q.** Ava_01 화면에서 NFT 크기/위치 조정 범위는 어디까지인가?
> **A.** Body 크기의 1/2 범위 (조정 범위 마스킹 처리) — **UNVERIFIED**

**The expected value is not yet binding**, and the reason is the rule this section had just
written. §7.1c disqualifies the implementing agent's reading as an independent reference, and this
value came from exactly that — the agent opened the image and read it. Proposing the criterion and
supplying its answer is the judge-and-judged shape, one paragraph after forbidding it.

So it is marked UNVERIFIED until **the director opens that image and confirms it**. One image, one
value, and it must not be settled by the party that proposed it.

The label matches on the **load-bearing tokens** — the fraction and the masking term — not the full
sentence: an exact-string `must_contain` against a machine transcription is brittle to spacing and
particle choice, which is how the Korean harness scores elsewhere.

This value sits in the 속성 table and in a callout annotation of one image. **It is absent from the
entire corpus text**: `크기/위치`, `마스킹`, `조정 범위`, and `1/2`/`½` each match **0 chunks**
across every active document (measured 2026-08-10). So the question is unanswerable today and
becomes answerable only if extraction works — which is what an acceptance criterion is for. The old
one could have been failed by a corpus that never contained the answer; this one cannot.

Scored as a label in the Korean eval set, with `must_contain` on the value, and the citation must
carry `machine_read`.

### 7.1b Step 0b passed — but it measured something that had not shipped

[[ADR-0010]] §2 admits machine-read text *because* a reader can re-read the image at its source, and
§3.1 says that without a re-resolvable reference the tier is a label with nothing behind it. Run on
2026-08-10 over the same 11 images: each was re-fetched **from its stored block id alone** — the
original presigned URL discarded — and the bytes were **identical in 11 of 11**.

**"Stored" was wrong, and this section said it for a day.** That run held the block ids *in memory*
and dropped them when it exited. Nothing persisted them: the marker carried no join key, the
extraction row carried no block id, and `vision.source_ref()` had no callers anywhere in the tree.
So the recourse this gate certified did not exist in the shipped system — a reader holding a
citation could not reach the image, and neither could Nexus.

[[SPEC-nexus-vision-source-ref]] is that gap, and it closed on 2026-08-11: the marker carries a
16-hex handle, the row carries `block_id` and `source_uri`, and **3 of 3 citations resolved by hand
against the live corpus** — chunk text → reference → block re-fetched → *fresh* signed URL → bytes
hashing back to the stored `image_sha256`, with the ingest-time URL long expired. 44 of 44 rows for
the reader of record carry a reference.

The lesson is not that the number was wrong; 11/11 was true of what it measured. It is that a gate
can pass against state the deployed system does not hold, and nothing in the run said so. What that
gate should have asserted — and now does, one SPEC later — is a round trip that starts from **stored
state only**.

What either version establishes is that the reference resolves *today*. Neither makes the recourse
durable: that depends on the source system keeping the block, which Nexus does not control (§8).

### 7.1c The author cannot be both readers

The sample compares a human reading against the machine's. **The agent doing the implementation has
already opened five of these images** (nos. 6, 8, 9, 10, 11), so its reading of those cannot serve
as the independent reference — that is the judge-and-judged failure this repo has been caught by
before, and it would quietly turn the control into a machine-versus-itself comparison.

Two consequences, both binding:

* the 8-image sample is drawn **only from images the implementing agent has never opened** — six
  remain in this document and 33 more across the other four
* the expected contents are recorded by **the director**, not by the agent, before the machine
  reading is run

§7.1a's acceptance question is exempt from this: it is scored against a fixed expected value that
the director can verify by opening one image, not against a transcription judgement.

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

## 7.3 What happened when it was actually run (2026-08-10)

**Extraction: 44/44, no failures, nothing quarantined.** One extractor identity across all rows,
through the `claude-code` bridge with no API key. 45 `machine_read` chunks — 45 rather than 44
because one oversized block split, and both halves stayed `machine_read`. Zero active mixed chunks.

**The reader that produced those rows has since been withdrawn** ([[SPEC-nexus-vision-reproducibility]],
[[SPEC-nexus-vision-reader-of-record]]). Asked to read the same image twice, it returned **84.7%
different tokens**; the replacement returns 3.6%. Every count in this section was measured with a
reader that could not repeat itself, which does not make the counts wrong — 44 images produced 44
rows either way — but does mean this section describes the run, not the system as it stands. The
corpus today holds 44 rows under the reader of record (4 of them empty) and **41** active
`machine_read` chunks.

**§7.1a-0's step 0 verdict is withdrawn.** An earlier revision recorded that the unlock thresholds
were in none of the images and that this falsified ADR-0010's fired gate. **That was wrong**: five
of eleven images had been opened, a universal negative was written from them, and the table was in
one of the six that were skipped. The director caught it. The original acceptance criterion stands
and **it passes** — the question now returns the full table (12 DJ-point tiers, 4 referral, 4
party-room, with the composition rule), cited as `machine_read`, and step 0b's re-fetch held at
11/11 byte-identical.

**Answer quality did not recover, and extraction is not why.** Runs before extraction: 33, 36, 39,
40, 38, 39 out of 40. After: 34, 36, 35; after the chunking fix: 36, 34, 32. Measured rather than
assumed, the cause is elsewhere:

* only **1 of the top 20** hits for the failing queries is `machine_read` — extracted text is not
  taking the slots
* **12 of the top 20** are one-line Notion database rows (`- **디제잉 포인트**: 60`), present since
  2026-08-07
* the sentence those queries need is active and ranks **18th**
* the chunk holding it was **11,969 characters** in the labelled snapshot and is **289** now — the
  difference is eleven expired S3 image URLs that used to pad it

So **39/40 was an artifact**: URL garbage inflated one chunk past the length-normalisation league
of the one-line rows. Dropping those URLs was the correct fix and is what dissolved the number.
There is nothing to restore, and reverting extraction would not restore it.

**Measured after the NULL-vector repair (2026-08-11), which this section previously asserted without
reporting**: retrieval `Recall@10` **40/40**, and three answer runs at **grounded 39/40** each —
level with the best run this SPEC ever recorded, and with extraction in the corpus. The residual
failure is a single query in **6 of 6** runs, where the document's prose and the screen specification
inside its own image name different screens; that is the label debt in §8, not a quality loss.

The ruler is disclaimed in the same breath, and that is not resolved here: §8 records that the eval
set snapshots a corpus that no longer exists, and the 2026-08-11 run additionally found the scoring
counts a correct answer wrong when it cites a document other than the single one a label names.

**"The ranking defect is the real one" — withdrawn.** §8 recorded, and the paragraph above implied,
that a one-line database row outranking a policy document was the standing defect behind the lost
points. It was not. Every one of the 45 extraction chunks had `embedding_1024 = NULL`: the vector
indexing had failed silently during ingest, so the extracted text was reachable by BM25 only.
After repair, gold answers outside the top ten went from 3 to 0. The real defect was that the
pipeline swallowed an indexing failure — which is what [[SPEC-nexus-index-completeness]] and
[[SPEC-nexus-generation-of-record]] address — and it was diagnosed as a ranking problem for a day
because nobody checked whether the vectors existed before reasoning about their order.

**Four defects surfaced only by running it against the live corpus**, with every unit test passing:
the trust flag never reached the chunker (extraction laundered as authored); re-ingest silently
zeroed `documents.n_images`; the image marker outside the block produced 6–11 empty chunks per
document; and authored prose was cut at every image boundary. A fifth — SSRF in the image fetcher —
was found by review before it ran.

## 7.4 What the 8-image sample became, and what that does and does not close

§7.1 pre-registered a transcription sample: 8 images the implementing agent had never opened, the
director records the expected contents first, then the machine reading is compared. **That is not
what was run**, and pre-registration means the swap has to leave a trace.

**Why it was replaced.** §7.1's design assumed the reader repeats itself, and it does not. Measured
under [[SPEC-nexus-vision-reproducibility]], the reader of that era returned **84.7% different
tokens** when handed the same image twice. Comparing a human transcription against one such reading
scores a coin flip, and a `pass`/`partial` verdict would not have been about the reader at all. The
reader was replaced (3.6%); the sample design still had the deeper problem that it asks a human to
retype 8 screens — the exact cost this SPEC exists to remove from the organisation.

**What was run instead — three rounds of targeted adjudication.** Two independent commercial readers
each read every image **twice**; only tokens **stable across both of a reader's runs** were
compared, so run-to-run noise could not enter the question set. Where the two readers disagreed, the
disagreement became a single yes/no question — *does this string appear in this image?* — put to the
director with the producing model **blinded** and with control items mixed in, drawn from tokens the
two readers agreed on. Questions were grouped by image so one opening answers several.

| round | items | controls | disagreement items answered "present" | "absent" |
|---|---|---|---|---|
| 1 | 20 | 9/10 | 5 of 10 | 5 |
| 2 | 16 | **10/10** | **6 of 6** | 0 |
| 3 | 18 | **10/10** | **8 of 8** | 0 |

**Round 1's five absences, each accounted for.** Two were human misses the director reversed on a
second look — one of them a control (`02`), and one a string in white on a small red circle. The
remaining three (`r`, `dots`, `
ightarrow`) were **markup names emitted for glyphs**, not
invented content: the reader was naming a vertical-ellipsis icon rather than fabricating text. The
system prompt gained a rule against that, which moved `prompt_sha` and therefore the extractor
identity, and rounds 2 and 3 measured the corrected reader. A fourth was a repeat-count question
(`txtxtxtxt` inside a longer run of the same characters), resolved by stating the containment rule
in the sheet: a string visible as part of a longer string is **present**, because what is being
measured is whether the reader put characters on the screen that are not there.

**What this closes.** The zero-tolerance invention gate, on more evidence than the original design
would have produced: 54 items across three rounds, every disagreement in the two post-fix rounds
confirmed present, controls clean in both. It is targeted precisely where invention could hide —
places where one reader produced something the other did not — rather than at 8 images chosen for
being unread.

**What it does not close, stated plainly:**

* **The `≥ 6 of 8` fidelity score was never computed.** This method does not produce it, and
  claiming the gate passed in full would be false. What is established is *no invention*, not
  *faithful transcription*; a reader that omits half a screen scores clean here.
* **§7.1c's ordering is not satisfied.** The questions are derived from the machine readings, so the
  director's answers cannot precede them. Blinding and controls are what stand in for that, and they
  are weaker: they stop the judgement from favouring a model, not from being shaped by what the
  models happened to output.
* **Omission is now measured and unresolved.** Rounds 2 and 3 turned up **14 items where each reader
  saw what the other missed** — real content, in the image, recovered by exactly one reader. A union
  of two readers would capture it and would double the standing extraction cost, which is a
  different design; it is carried as an open item there rather than decided here.

## 7.5 The reader of record, and which gates actually stand

A reader of this document could not tell which model and prompt produced the 44 live rows — §3 pins a
default, §7.3 says the reader was withdrawn, §7.4 says the prompt moved. Stated once, here, because
[[ADR-0010]] §3.1 makes identity the thing a recall is scoped by:

| | value |
|---|---|
| extractor identity of record | `gemini-3.6-flash/06e83390` |
| rows under it | 44 (4 empty), 41 active `machine_read` chunks |
| rows marked truncated | **0** |
| transport | Gemini REST — it returns `finishReason`, so §3.1's truncation control is live on this path |

§3's pinned `NEXUS_VISION_MODEL` default and this value must move together; they did on 2026-08-11
under [[SPEC-nexus-vision-reader-of-record]], and the earlier identity's 44 rows remain as the
migration record.

**The truncation control was inert on the transport that produced the first run.** The
`claude-code` bridge does not return a stop reason and `read_image` records it as unknown, so a
table cut off at the token ceiling would have travelled all six hops looking complete. It is live
now. What is still unstated is what an `unknown` stop reason should *do* — today the extraction is
stored unmarked — and that belongs with the transport that has the gap (§8).

### Which acceptance gates stand

The document has said three different things about its own acceptance criterion. Resolved:

| gate | state |
|---|---|
| **Motivating question** (§7.1) | **passes.** §7.1a's replacement is **dead** — it existed only because step 0 concluded the thresholds were in no image, and §7.3 withdrew that conclusion after finding the table in one of the six images step 0 never opened. The original question is the live one, scored as a label. |
| **Invention: zero tolerance** (§7.1) | **passes**, by the substitute method of §7.4 rather than by the registered one. |
| **Fidelity ≥ 6 of 8** (§7.1) | **not met, and not merely unmeasured.** §7.4's method cannot produce the score, and no replacement is registered. What the corpus has today is a guarantee against fabrication and none against omission — and §7.4 measured 14 real omissions. |
| **Step 0b — recourse** (§7.1) | **partially met.** The registration asked for one image *per document*; both the original run (11 images, one document) and its 2026-08-11 replacement (3 citations) drew from documents already opened. The four documents §1 flags as inference rather than measurement are the ones not covered. |
| **ADR-0010 successor note** (§8) | **still owed, but for a different reason.** §7.1a-0's falsification was itself withdrawn (§7.3); what an accepted record now needs is a note that a gate it declared fired was reported against state the system did not hold (§7.1b). |

**Registering the replacement fidelity gate is deferred, not silently dropped** — §8 carries it with
what would close it: a bound on omission, which is the axis §7.4 opened and cannot close alone.

### The mistiering was a violated invariant, not a testing anecdote

[[ADR-0010]] §7 makes it an invariant that no extraction is committed before the tier exists.
§7.3's first defect — the trust flag never reaching the chunker — means machine-read text entered the
live corpus tiered `authored`, which ADR-0010 §4 calls *worse than not extracting*. Calling that a
discovery about testing understated it.

Remediated by re-ingest, and now assertable rather than assumed: **0** active chunks are tiered
`authored` while carrying a vision marker, measured 2026-08-11. The stale rows from the mistiered
body are `superseded`, which is where the base filter leaves them.

## 8. Open items

* **Correcting a single invented chunk has no path.** ADR-0010 §5 freezes stored text for a given
  (bytes, identity) while §3.1 justifies identity by the need to scope a recall — and recall implies
  replacement. Deferred at ADR approval as this SPEC's to answer, and it is not answered here.
* **~~Re-resolving the source reference is unverified.~~ Closed 2026-08-11.** It was worse than
  unverified — §7.1b's demonstration ran on block ids held in memory, and nothing in the shipped
  system stored them. [[SPEC-nexus-vision-source-ref]] persists the reference and resolves it from
  stored state alone; 3 of 3 hand round trips against the live corpus returned bytes hashing to the
  stored `image_sha256` from a freshly issued URL.
* **Separate chunks lose their referent.** ADR-0010 §3 requires extracted text to form its own
  chunks, which strips the 100–171 characters of authored heading that say what the image depicts —
  the context retrieval needs. A context prefix carrying the authored heading is the obvious
  candidate and is unmeasured.
* **The labels do not point here — and this is now costing measurements, not just owed.** Labels
  authored against extracted content are owed, and must be authored **after** extraction so their
  author reads what a user reads. Extraction has now happened, so this is unblocked.

  Measured 2026-08-11: query `pb-part-01` fails in **6 of 6** answer-quality runs across two
  transports, and it is the only query that does. The document's authored prose says a
  not-logged-in visitor lands on one screen; the screen specification **in an image in the same
  document** names a different one. The system consistently answers from the image, and the label —
  authored before extraction existed — scores that as wrong. Before extraction the same query
  passed. So this open item is not hypothetical debt: it is subtracting from every quality number
  taken since, and it may also be a genuine contradiction in the source document, which is a
  question for its owners rather than for the harness.
* **~~The ranking defect is the real one.~~ Withdrawn 2026-08-11 — see §7.3.** It was not a ranking
  defect. All 45 extraction chunks had a NULL vector: indexing failed silently at ingest and the
  extracted text was reachable by BM25 only. After repair, gold answers outside the top ten went
  from 3 to 0. What needs its own record is a pipeline that swallows an indexing failure.
* **The eval set measures a corpus that no longer exists.** `ko_eval_packb` snapshots the corpus
  while it still carried expired image URLs, so 40/40 and `Recall@10 = 1.000` taken on it guarantee
  nothing about the corpus as it stands.
* **One reader misses what the other sees.** Rounds 2 and 3 of §7.4 found 14 items where each
  reader recovered content the other did not — present in the image, absent from one reading. A
  union of two readers would capture it at double the standing extraction cost. Deferred to its own
  SPEC rather than decided in a §7 note.
* **Step 0b proves the reference resolves *today*.** ADR-0010 §2's recourse promises it resolves
  for the life of the chunk, and that depends on the source system keeping the block — which Nexus
  does not control. A demonstrated re-fetch falsifies the design early; it does not make the
  recourse durable.
* **The vision model's EOL is now a separate thing to remember.** Pinning `NEXUS_VISION_MODEL` to
  its own literal is what stops an answer-model bump from invalidating every extraction — the cost
  is that nothing else moves it, and an unmaintained default is a quiet way to keep reading with a
  retired model.
* **ADR-0010 owes a successor note.** §7.1a-0 falsified one link in the evidence its fired gate was
  declared on. The gate stands on what survives, but an accepted record should not be left saying
  something a later measurement contradicted — and it cannot be edited, so the correction belongs
  in a record of its own.
* **A replacement fidelity gate is unregistered.** §7.5 records the `≥ 6 of 8` criterion as unmet
  and §7.4 explains why the substitute cannot produce it. What would close it is a bound on
  **omission** — the axis §7.4 opened by measuring 14 items one reader saw and the other did not.
  Until such a gate is registered, this SPEC guarantees against fabrication and not against
  incompleteness, and the tier says nothing about the difference.
* **§4.4's deletion exception amends an accepted ADR.** ADR-0010 §5 names no exception and its own
  Status paragraph says a SPEC may not add one. The exception is also not closed by the argument
  given: after a deletion, a later ingest re-reads with a reader that diverges run to run, so
  different text can end up under the same `(bytes, identity)` pair and flip `content_hash` with no
  edit — the churn ADR-0006's spine is built to keep meaningful. Either a successor ADR carries it,
  or the deleted row is tombstoned so re-extraction under the same identity is refused.
* **The ceiling and sticky failure rows do not converge.** `NEXUS_VISION_MAX_PER_INGEST` records
  overflow images as failure rows so the run is repeatable, and §7.2.9 makes failure rows suppress
  retry until a human deletes them. A tenant with more images than the ceiling therefore never
  finishes extracting by re-running ingest. The live corpus (44) is under the ceiling, so this is
  latent — the first larger tenant meets it with only a count in the run summary.
* **Neither remedy has an operator surface.** Retry means deleting a failure row and quarantine
  remediation means deleting an extraction row, and both are hand-written SQL against a live table.
  §6 ships no command, endpoint or tool for either, and §4.4's invariant depends on the deletion
  being done correctly.
* **Marker stripping now touches every intake path.** §4.3's default-distrust flag removes the two
  marker literals from authored bodies on paths this SPEC does not otherwise touch, and body text
  feeds `content_hash`. The behaviour is right for tiering and is not enumerated per path.
* **Small print.** Both local models lost the header strip; the API reader read it. If the local
  path is ever taken up, "small print is not reliably read" belongs in the tier, not in a comment.
