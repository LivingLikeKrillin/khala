---
id: SPEC-nexus-vision-reproducibility
type: spec
title: The reader must be able to repeat itself — ADR-0010's central invariant is
  false in production, and nothing was checking
status: approved
retractions:
- SPEC-nexus-vision-reader-of-record
linked_adrs:
- ADR-0006
- ADR-0010
tags:
- nexus
- ingest
- vision
- measurement
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-11T09:46:02Z'
content_hash: sha256:637a9ce86a4141bedf784c0c2c0d2077034b810bedf25bbf8a74084bee0b1e39
---

## 1. What prompted it

[[ADR-0010]] §5 fixes the invariant the whole machine-read tier rests on:

> **Unchanged bytes are never re-extracted.** Re-ingest resolves the stored result by
> (byte hash, extractor identity). Extraction runs on new or changed bytes only.

That rule only makes sense if identity determines the reading — if calling the same reader twice on
the same bytes gives the same text. **It does not, for the reader in production**, and nothing in
the repository ever checked.

Measured 2026-08-11 by calling each reader **twice on the same images**, same prompt, same
transport, `temperature 0`, comparing normalised token sets:

| reader | images | both runs identical | token variation |
|---|---:|---:|---:|
| `gemini-3.6-flash` (`thinkingLevel: minimal`) | 44 | **35/44** | **3.6%** |
| `claude-sonnet-4-6` via the claude-code bridge | 20 | **4/20** | **84.7%** |

The shipped reader agrees with itself on about a sixth of its output. The 45 `machine_read` chunks
in the live corpus are **one draw**; a second draw of the same images produces substantially
different policy text, and `extractor_identity` — `claude-sonnet-4-6/18c36580` for all 44 rows —
cannot distinguish the two.

### 1.1 How this was found, and what it invalidates

It was found by accident, and late. A cross-model comparison (Sonnet against Gemini, adjudicated by
Opus) reported that Sonnet omitted 32 identifier tokens the other two readers saw. Four successive
drafts of a SPEC were built on that number. The critique asked what the stored Sonnet extractions
actually were, and re-running Sonnet against them showed a 63% difference — which was first read as
a harness problem, then measured properly as the reader disagreeing with itself.

**Every comparative claim from that work is withdrawn**: reader-to-reader difference was 7.4%,
inside a self-variation of 84.7%. Nothing about which reader reads better was established, and the
32 were noise. What is established is this document's subject.

The error has one name: **no instrument had its noise floor measured before its readings were
believed.** Two runs of the same reader is the cheapest control that exists and it was never run.

### 1.2 What is not claimed

* Gemini is **not** shown to read more accurately. It is shown to repeat itself. Accuracy needs the
  human sample [[SPEC-nexus-screenshot-text-extraction]] §7.1 still owes.
* 3.6% is not zero. 9 of 44 Gemini image pairs still differ.
* The Sonnet arm is 20 images, not 44, and the two arms were drawn as the first N of the same
  catalogue order (document title, image index) — deterministic, not random, and not selected on
  anything the readings showed.
* The difference is not an artefact of the smaller arm. On the per-image "both runs identical"
  outcome — 35/44 versus 4/20 — a two-sided Fisher exact test gives **p = 1.3 × 10⁻⁵**. An earlier
  draft asserted this without computing it, which is the habit this document exists to correct.

## 2. Design

### 2.1 Reproducibility is an adoption condition, not a hope

No extractor becomes or remains the reader of record without a measured self-agreement rate. The
procedure, fixed here:

* draw the **whole image corpus** for the tenant (44 today);
* call the candidate reader **twice**, same prompt, same transport, same generation settings;
* normalise both readings (§2.2) and compare token sets per image;
* report **image-identical rate** and **token variation rate**.

**The harness runs out of band and writes nothing.** A second call on bytes that already have a
stored result under the same `extractor_identity` is precisely what ADR-0010 §5 governs, so the
measurement must never reach `vision_extractions` or produce a chunk. Today the only thing
preventing that is an incidental `ON CONFLICT DO NOTHING` in `vision_store.save()`
(`nexus/nexus/ingest/vision_store.py:44`); this SPEC makes it a requirement with a test (§4.6)
rather than a coincidence a future author has no reason to preserve.

**Threshold, pre-registered:** a reader of record must reach **token variation ≤ 10%**.

The justification is not that 10% sits far from both measurements — it does not: 3.6% → 10% is
2.8×, and an earlier draft claimed "an order of magnitude" in both directions, which is wrong on the
side that matters. The bar is 10% because **that is the largest self-disagreement under which
ADR-0010 §5's resolution key still means something**: at 10%, re-reading the same bytes reproduces
nine of ten values, and a citation points at text a second draw would substantially agree with. At
84.7% it does not, and the key is decorative.

The measured 3.6% is an **upper bound**, not a point estimate: §5's dash-welding defect scores some
pure rendering differences as variation. That biases against the passing reader, so the pass is
conservative.

### 2.2 Normalisation

Rendering is folded, content is not: NFKC (folds full-width spaces, `①` → `1`); `−`/`–`/`—` → `-`;
leading `#`/`>` stripped; `|` **replaced by a space, never deleted** (deletion welds two cells into
an identifier present in neither reading); scaffold-only rows dropped; whitespace runs collapsed.
Tokens compared are `[A-Za-z0-9][A-Za-z0-9_.-]*` of length > 1. Hangul runs are counted separately
and are not part of the threshold — §5.

### 2.3 The identity must carry what changes the reading

`extractor_identity()` is `{model}/{prompt_sha}`. Two facts break it:

* **the same identity produced both readings above.** Identity does not determine text, so
  ADR-0010 §5's resolution key is not a key;
* `gemini-3.6-flash` and `sonnet` are **vendor-side aliases**. A snapshot change behind an alias
  changes the reader without moving the identity.

This SPEC does not redesign the identity — that is ADR-0010's to amend (§6). It records that the
identity is **incomplete** and stores the measured self-agreement rate beside the extractions:

```sql
ALTER TABLE vision_extractions
    ADD COLUMN IF NOT EXISTS reader_variation NUMERIC
    CONSTRAINT chk_reader_variation CHECK (reader_variation IS NULL
                                           OR (reader_variation >= 0 AND reader_variation <= 1));
```

`IF NOT EXISTS` and the `CHECK` are both load-bearing: the repository's migrations are idempotent by
convention (`013_provenance_tier.sql`), and a bare `NUMERIC` would store a harness bug's `-1` as a
legitimate rate.

**Which rows receive a value, precisely.** The rate is a property of a *reader over a corpus*, not
of one extraction, so it is written only to rows whose image was actually drawn twice: **20 of the
44** for `claude-sonnet-4-6/18c36580` (the first 20 in catalogue order), and the remaining 24 stay
`NULL`. `NULL` means "nobody checked" and must not be filled by extrapolation — writing 0.847 to the
other 24 would assert a measurement that was never made, which is the error this whole document is
about.

**The rate must reach a surface.** A column nothing joins is not a signal:
[[SPEC-nexus-index-completeness]] showed a correct measurement sitting unread in a log for a day.
`nexus status` gains one line per tenant — how many active `machine_read` chunks come from a reader
whose variation is unmeasured, and how many from one above the §2.1 threshold. That is the whole
surface this SPEC requires; carrying the rate through ADR-0010 §4's six hops to the citation is the
identity redesign's business (§6).

### 2.4 What happens to the live chunks

The populations, kept apart because §1's counts were previously used interchangeably: **44 images**
→ **44 rows** in `vision_extractions` → **45 `machine_read` chunks** (one extraction is long enough
that the chunker splits it — 11/11, 11/11, 10/10, **7**/6, 6/6 by document).

They stay, and they are labelled. They are already `machine_read` at all six hops, which is the
strongest claim ADR-0010 permits; this SPEC adds the reader's measured variation on the 20 rows
where it was measured.

**They are not silently re-extracted.** Re-reading under the same identity is forbidden by ADR-0010
§5, and re-reading under a new one is the reader-of-record change this SPEC does not take (§6).
Deleting them would remove policy text that has been answering correctly — the answer harness
scored 39/40 with them in place — on the strength of a reproducibility finding, which is a
different question from whether the text is right.

## 3. Non-goals

- **The reader of record is not changed here.** The measurement licenses a change; the change needs
  its own record, including what happens to the existing chunks and what the migration costs.
- **No accuracy claim.** §1.2.
- **No cross-model adjudication.** That instrument is withdrawn until it runs on readers that pass
  §2.1; comparing two draws from an 84.7%-variance reader measured nothing.
- **No change to `SYSTEM`.** Moving `prompt_sha` mid-measurement would confound it.

## 4. Testing

1. The self-agreement procedure returns 1.0 variation for two disjoint readings and 0.0 for two
   identical ones — the metric's endpoints, asserted on fixtures.
2. Normalisation: `60 | FENDI` yields `60` and `FENDI`, never `60FENDI`; `−`, `①`, full-width
   space and leading `#`/`>` fold; `0.1.6` survives.
3. A dash-range pair (`10–20` versus `10 - 20`) produces **different** token sets — the known
   welding limit is pinned so it cannot be silently "fixed" (§5).
4. `reader_variation` defaults to NULL, accepts 0 and 1, and the database **rejects** -0.1 and 1.1 —
   asserted against the constraint, not against application code.
5. Migration 015 is idempotent: applying it twice succeeds and leaves existing rows NULL.
6. The measurement harness writes nothing: run it against a seeded database and assert `chunks`,
   `documents` and `vision_extractions` are byte-identical before and after (content digest, not row
   count — an in-place UPDATE leaves counts equal).
7. `nexus status` reports the unmeasured and above-threshold chunk counts, and reports nothing for a
   tenant with no `machine_read` chunks (no new always-on line — the failure
   [[SPEC-nexus-index-completeness]] §2.3 records).

## 5. Limits

* **Token-level.** A reader that repeats itself while putting values in the wrong cells passes.
* **Identifiers only.** Hangul prose is excluded from the threshold: readers differ legitimately on
  line breaks and particles, so prose variation would be measured as reader instability. The rate
  for prose is therefore **unknown**, on the class that carries most of the policy.
* **Dash welding** — `10–20` and `10 - 20` normalise to different tokens; ranges are compared
  incorrectly and the test pins the behaviour rather than fixing it.
* **Two runs, not many.** Self-agreement from n=2 is a floor estimate; a reader could be bimodal.
* **One corpus**: 44 Korean UI/policy screenshots, five documents, one machine.
* **The Sonnet arm is 20 of 44 images.**

## 6. Open items

| item | why not here | when |
|---|---|---|
| ADR-0010 §5's resolution key is not a key | The ADR states an invariant this SPEC measures as false. Amending an accepted ADR is not a SPEC's to do. | Next ADR revision touching extraction |
| Vendor aliases hide snapshot changes | Pinning to a dated snapshot is available for some vendors and not others; it interacts with the identity redesign above. | With the identity amendment |
| The reader of record | §3. The measurement licenses it; the change is its own record. | Next |
| Prose reproducibility is unmeasured | §5. A sentence-level agreement measure is a different instrument. | If prose invention is found by §7.1's sample |
| Whether the 45 live chunks are *correct* | Reproducibility is not accuracy. [[SPEC-nexus-screenshot-text-extraction]] §7.1's human sample is still owed, and the 8 images for it are drawn and waiting. | Next human session |
