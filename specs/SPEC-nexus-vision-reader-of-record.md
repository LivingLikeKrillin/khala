---
id: SPEC-nexus-vision-reader-of-record
type: spec
title: Replace the reader that cannot repeat itself — qualify candidates on both axes,
  after fixing the one defect adjudication found
status: approved
linked_adrs:
- ADR-0006
- ADR-0010
tags:
- nexus
- ingest
- vision
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-11T11:01:07Z'
content_hash: sha256:91a540cdc6acb4646a2c14e8b60b4659e1b88ce8855dfde2835bae69a5358667
---

## 1. What prompted it

Two measurements now exist that did not when `claude-sonnet-4-6` was chosen (on one screenshot,
scored by the implementing agent — [[SPEC-nexus-screenshot-text-extraction]] §2 says so itself).

**Reproducibility** — each reader called twice on the same images, same prompt, same transport
([[SPEC-nexus-vision-reproducibility]]):

| reader | images | both runs identical | token variation | threshold ≤ 10% |
|---|---:|---:|---:|:--|
| `claude-sonnet-4-6` (shipped) | 20 | 4/20 | **84.7%** | **fails** |
| `gemini-3.6-flash` (`thinkingLevel: minimal`) | 44 | 35/44 | 3.6% | passes |
| `opus` | 44 | 38/44 | **1.4%** | passes |

**Invention** — 44 images cross-checked between Gemini and Opus, each filtered to tokens that
reader read in **both** of its runs, adjudicated blind by the director with 10 interleaved controls
drawn from tokens all four runs agreed on:

| | count | what they were |
|---|---:|---|
| controls present | **10/10** | the premise holds — stable agreement means the token is in the image |
| **policy-value inventions** | **0** | — |
| Gemini inventions | 3 | `br`, `rightarrow`, `vdots` — icons (→, ⋮) and line breaks written as **markup names** |
| Opus inventions | 1 | a dummy placeholder string from a design mock-up |
| one-sided omissions | 5 | dummy placeholder strings, and one label |

Sonnet was not adjudicated: its 84.7% self-variation means a candidate list built against it is
noise, which is what four withdrawn SPEC drafts were built on.

### 1.1 Two corrections the adjudication itself produced

* **Two of twenty first-pass verdicts flipped on a second look, both the same way** — small text
  the director had not seen (`02` inside a red badge; `3-1` in white on red). The last candidate
  policy-value invention disappeared that way. Under-detection is easy and over-detection is hard,
  so §4 requires every `absent` verdict to be looked at twice.
* **One question was malformed by the instrument.** `툴팁_사용가이드_02` was tokenised to `02`,
  because the identifier pattern anchors on an ASCII character and splits mixed-script identifiers.
  The director was asked whether `02` was in the image, which is nearly unanswerable. §6 carries it.

## 2. Design

### 2.1 Fix the defect adjudication found, then qualify

The three Gemini inventions are one defect: the reader writes `rightarrow` where the image shows →.
That is a transcription error with a precise remedy, and it must be fixed **before** the candidates
are ranked — otherwise the ranking is of readers we are about to change.

`SYSTEM` gains one rule:

```
- 아이콘·기호·화살표는 **그 자리에 보이는 문자 그대로** 옮기거나, 옮길 문자가 없으면 비워라.
  `rightarrow`·`vdots`·`br` 처럼 **기호의 이름이나 마크업 명령을 쓰지 마라** — 그 글자는
  이미지에 없다.
```

Nothing else in the prompt changes. The dummy-placeholder disagreement (`txtxtx…`) is **not**
addressed: instructing a transcriber to decide which text is worth transcribing turns transcription
into judgement, which is a different contract for `machine_read`. It is recorded in §6 instead.

### 2.2 Qualification, pre-registered

Fixed here, before the new prompt runs, so that a threshold cannot be drawn around whichever
candidate wins:

1. Both candidates run the **new** prompt twice over all 44 images. **These runs are out of band**:
   they are not written to `vision_extractions` and produce no chunks, because a second reading of
   the same bytes under any identity is exactly what ADR-0010 §5 governs. Only the adopted
   candidate's re-extraction (§2.3) becomes the record.
2. **Reproducibility gate**: token variation ≤ 10% ([[SPEC-nexus-vision-reproducibility]] §2.1).
   A candidate that fails is out regardless of anything else.
3. **Invention gate**: the cross-check runs between the surviving candidates, each filtered to its
   stable tokens, with 10 controls interleaved and blinded. **Any adjudicated invention disqualifies
   that candidate** — ADR-0010's rule is *"inventing content is failure at any score"*, and it is
   applied here without exception.

   An earlier draft of this section exempted "markup-name" and "dummy-placeholder" inventions. That
   exemption was drawn **after** seeing the four inventions the two candidates actually made and it
   exactly covered them, producing zero disqualifications — a threshold fitted to the result, which
   is the failure this SPEC's opening sentence claims to avoid. It is withdrawn. Both candidates
   currently **fail** this gate: Gemini on three markup names, Opus on one placeholder.
4. **This gives the §2.1 prompt change a measurable job**: it must take Gemini's markup-name
   inventions to zero. If it does not, the change did not work and the candidate is still out. Opus's
   single placeholder invention has not been re-examined under §4's second-look rule and is
   unconfirmed; it is re-adjudicated in this round.
5. **Tie-break among survivors, in order**: (a) fewer adjudicated inventions; (b) lower token
   variation; (c) **deployability** — a reader that cannot run in a deployed ingest cannot be the
   reader of record.
6. **If no candidate survives, nothing is adopted.** The corpus stays on the current reader with its
   84.7% recorded and surfaced, the prompt is iterated, and the round is re-run. Adopting a
   disqualified reader because the incumbent is worse is how a gate becomes decoration; the
   incumbent's failure is an argument for urgency, not for lowering the bar.

(c) is not a formality. `opus` reaches Nexus only through `claude_llm_bridge.py`, which states it is
*"dev 전용 … 서버 백엔드가 아니다. 팀/프로덕션 compose 에 넣지 않는다"* and needs an
authenticated `claude` on the host. Anthropic's API would remove that constraint and the key exists,
but it has no credit; that is a purchase, not a design decision, and this SPEC does not assume it.

**On today's numbers Opus wins (a) and (b) and loses (c).** The order is deliberate: a reader that
reads better but cannot be deployed is not a candidate, and stating the order now stops it being
re-argued after the re-measurement.

**The incumbent's elimination rests on old-prompt numbers, and that is not symmetric with §2.1.**
§2.1 argues the candidates must not be ranked on numbers taken before the prompt change; the same
argument applies to Sonnet's 84.7%, and it is not re-measured here. The asymmetry is deliberate and
bounded: the prompt change adds one line forbidding markup names, and no mechanism is offered by
which that would move a reader from 84.7% self-disagreement to under 10%. If a reviewer thinks it
might, the remedy is to include Sonnet as a third candidate in the same round — which costs one
more pair of runs and is not refused. Its 20-image arm is also smaller than the candidates' 44,
which the table states and this SPEC does not paper over.

### 2.3 The change is one migration

`extractor_identity()` is `{vision_model()}/{prompt_sha()}` and **both** parts move: the model and
the prompt. By ADR-0010 §5 that is *"a migration, not a silent re-read … a deliberate act with a
recorded reason"*; §1 is the reason. Consequences, all of them:

* **Where the bytes come from, which an earlier draft omitted while claiming to list everything.**
  Nexus is index-not-store (ADR-0004): it holds the image's content hash and no bytes, and Notion's
  signed URLs expire within the hour. Re-extraction therefore re-walks Notion by page id — which
  works today and is how every measurement in §1 was run — **using the per-root token from
  `notion_sources.token_env`**, because the roots use different integrations and asking with one
  token returns `ObjectNotFound` for the others, indistinguishable from deletion.
  `vision.source_ref()` exists and **has no callers**, so a chunk still cannot name its own image;
  this migration does not depend on it, and §6 keeps it open.
* 44 images are re-read under the new identity. Prior rows survive (`(tenant, image_sha256,
  extractor_identity)`), so the old reading stays auditable, and they produce no chunks —
  `build_block()` is called with the current run's extraction, so exactly one block enters the body.
* `content_hash` changes for the five image-bearing documents; `doc_reingest_events` gains five
  rows. This is the churn ADR-0010 §5 accepts for a deliberate migration, and it perturbs ADR-0006's
  entropy signal ① with no marker to distinguish it (§6).
* The 45 `machine_read` chunks change text, which nulls their vectors and tsvectors
  ([[SPEC-nexus-generation-of-record]] §3.4) and requeues them. `nexus status` must show no coverage
  gap when it finishes.
* `reader_variation` is written for the new identity on the images actually drawn twice — all 44.
  The old identity's rows keep the 84.7% measured on 20 and `NULL` on the other 24.

### 2.4 What the existing chunks are, until then

They stay and they are labelled. `nexus status` already reports that their reader's variation is
above threshold. Deleting policy text that has been answering correctly (39/40 on the answer
harness) on the strength of a reproducibility finding would trade a known-imperfect corpus for an
empty one; re-extraction replaces them in the same act that fixes the problem.

## 3. Non-goals

- **No context injection, no captioning, no image classification.** Three proposals were withdrawn
  on their own critiques on 2026-08-11.
- **No change to what `machine_read` means.** The reader still transcribes.
- **No second sample of the 36 unread images.** §1's cross-check covered all 44; the human read
  20 targeted items, not 44 transcriptions, and that is the point of the instrument.
- **No purchase.** §2.2(c) records what Anthropic API credit would change and does not assume it.

## 4. The adjudication protocol, amended

As [[SPEC-nexus-vision-reproducibility]] §4 fixed it, plus the two corrections §1.1 produced:

* **Every `absent` verdict is looked at a second time**, at full zoom, before it is recorded.
  Errors are asymmetric: missing small text is easy, inventing text you did not see is not.
* **Questions whose token is a fragment of a longer identifier are not asked.** The instrument must
  present the identifier the reader actually produced (§6).
* Controls are scored first and must be 10/10; a failing control voids the run.
* **The protocol leaves an artifact or it did not happen.** Each item records a first verdict and,
  where the first was `absent`, a second — both stored. Without that, the requirement most
  load-bearing for the outcome is the one with no evidence, and §1.1 shows the second look changed
  two verdicts of twenty and removed the last candidate policy-value invention.
* **Category assignment is not a verdict.** §2.2 no longer exempts any category, so nothing turns
  on whether a token is called "markup" or "a value" — the adjudicator answers presence only.

## 5. Testing

1. The new `SYSTEM` produces a different `prompt_sha`, and therefore a different
   `extractor_identity`, from the stored one — asserted directly, since this is what makes the
   re-read legal under ADR-0010 §5.
2. Prior `vision_extractions` rows survive a re-extraction under the new identity (no overwrite).
3. Re-extraction nulls the affected chunks' vectors and tsvectors and requeues them.
4. The qualification harness refuses to adopt a candidate whose measured variation exceeds 10%,
   **and refuses to adopt any candidate when every candidate is disqualified** (§2.2.6) — asserted
   on a fixture where both fail, since that is the case an implementation is most likely to get
   wrong by falling back to "the least bad one".
5. The qualification runs write nothing: `chunks`, `documents` and `vision_extractions` are
   byte-identical before and after (content digest, not row count).
6. **ADR-0010 §6 holds for whichever reader is adopted** — the request carries one image, declares
   no tools, and names no filesystem path. Asserted against the request the adopted client actually
   builds, not against a comment. A reader swap is the change most able to reintroduce tool access
   ahead of the quarantine gate, and §6 is the constraint that forbids it.
7. `nexus status` reports no coverage gap once the re-embed queue drains; the migration is not
   "complete" until it does, and a stalled queue leaves the ⚠ standing rather than being reported
   as success.

## 6. Open items

| item | why not here | when |
|---|---|---|
| The tokeniser splits mixed-script identifiers (`툴팁_사용가이드_02` → `02`) | It produced one unanswerable question and, worse, it can score two readings as agreeing on `02` when they read different identifiers. Fixing it changes every count in [[SPEC-nexus-vision-reproducibility]], so it is its own change with its own re-measurement. | Before the next cross-check is used for a decision |
| Dummy placeholder text (`txtxtx…`) is transcribed by one reader and not the other | §2.1 — instructing a transcriber which text is worth transcribing is a different contract. It is noise in the index, not a fidelity defect. | If it is found to crowd retrieval |
| The migration perturbs ADR-0006 entropy signal ① | Five `doc_reingest_events` rows from a deliberate extractor change look like undisciplined re-upload, and no column distinguishes them. Adding one touches ADR-0006's signal schema and is its own change. **The trigger "when signal ① is next read" is one nobody is obliged to notice**, so instead: the migration records the timestamp and the five document rids in its run log, and that list is the thing a reader of signal ① compares against. It is a fact checkable now rather than an obligation owed to an unobservable event. | Whoever next reads signal ①, using the recorded list |
| Anthropic API credit would make `opus` deployable and it wins on both measured axes | A purchase, not a design decision. | If the director funds it |
