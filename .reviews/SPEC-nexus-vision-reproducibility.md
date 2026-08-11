---
target: SPEC-nexus-vision-reproducibility
critiqued_hash: sha256:ce28865136fc5720d8aed03254e9730c0822454f9dd86527503e96db63c9cb25
critiqued_at: '2026-08-11T09:14:09Z'
issues:
- issue_id: I-001
  category: risky-assumption
  severity: high
  description: '§1''s table states both readers were called with "same prompt, same
    transport, `temperature 0`". Only the Gemini arm sets it: `nexus/scripts/vision_gemini_probe.py:60`
    sends `{"temperature": 0, ...}`, while the Anthropic path `AnthropicBackend.vision_extract`
    (`nexus/nexus/providers/llm.py:110`) passes only `model`, `max_tokens`, `system`,
    `messages` — no temperature, i.e. the vendor default (1.0). The repo already caught
    the sibling version of this: `vision_gemini_probe.py:48` records that "same prompt,
    temperature 0" was written down while only one reader got the control. So 84.7%
    may be sampling temperature rather than reader instability, and the two arms are
    not comparable. The headline measurement, the 10% threshold, the withdrawal of
    the cross-model work, and §2.4''s labelling all rest on this one line being true,
    and it is not.'
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: adr-contradiction
  severity: high
  description: '§1 asserts ADR-0010 §5 "only makes sense if identity determines the
    reading", and §2.3/§6 conclude "ADR-0010 §5''s resolution key is not a key". ADR-0010
    §5 states the opposite premise explicitly: "A machine reader is not deterministic;
    re-running it on the same image can drift by a character", and it therefore places
    the invariant on the durable side ("an extraction result, once stored, is never
    replaced by a re-read of the same bytes under the same extractor identity") precisely
    so drift can never land. (tenant, image_sha256, extractor_identity) is a storage
    key that resolves to exactly one row — it never claimed to predict text. The measurement
    does not invalidate §5; it changes how much confidence one arbitrary stored draw
    deserves. The whole framing, the open item, and the deferral to "the next ADR
    revision" are aimed at a claim the ADR does not make.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: adr-contradiction
  severity: high
  description: '§6 defers the identity redesign with the reason "Amending an accepted
    ADR is not a SPEC''s to do." ADR-0010''s Status line reads "**Draft** — settles
    one boundary question, ships no code." The named blocker does not exist: the ADR
    is amendable now, and ADR-0010 itself was written because a SPEC could not amend
    an ADR — the correct move here is to amend the draft, not to schedule it behind
    a revision that has no trigger.'
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: adr-contradiction
  severity: high
  description: §2.1 labels the 10% bar "Threshold, pre-registered" and in the same
    paragraph derives it from the two measurements already taken ("Gemini measures
    3.6% and passes; Sonnet measures 84.7% and does not"). ADR-0010's Open items require
    thresholds "pre-registered — written down before the sample is read, since a threshold
    chosen after seeing the output ratifies whatever the output happened to be." A
    bar chosen to sit between the only two readings ever taken is post-hoc; calling
    it pre-registered is the exact failure the ADR named, and the disclaimer ("not
    a line drawn around today's winner") is assertion, not procedure.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: unverifiable-claim
  severity: high
  description: '§2.4 justifies keeping the 45 live chunks with "the answer harness
    scored 39/40 with them in place". That number is withdrawn in the repo: `specs/SPEC-nexus-screenshot-text-extraction.md:625`
    — "So **39/40 was an artifact**: URL garbage inflated one chunk past the length-normalisation
    league" — and ADR-0010 §Context records the same-day answer run as "scored against
    text only… The ruler never pointed at the images." A document whose subject is
    believing instruments before their noise floor is measured uses a known-broken
    instrument''s reading as the sole evidence that the retained text "has been answering
    correctly".'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: undefined
  severity: high
  description: '"Token variation rate" — the quantity the entire pre-registered gate
    is expressed in — is never defined. §2.1 says only "report image-identical rate
    and token variation rate"; §2.2 says tokens are compared per image. Symmetric
    difference over union, per image then averaged, or pooled corpus-wide, produce
    materially different numbers on the same data, and 3.6% vs 10% is close enough
    that the choice decides pass/fail. §4.1 asserts the metric''s endpoints (1.0 for
    disjoint, 0.0 for identical) without the formula that would make those endpoints
    derivable, so the test pins two points on an unspecified function.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: risky-assumption
  severity: high
  description: §2.2 excludes Hangul runs from the threshold, and §5 concedes the resulting
    rate for prose is "unknown, on the class that carries most of the policy" over
    a corpus of 44 Korean UI/policy screenshots. The adoption gate in §2.1 is therefore
    decided entirely on identifier and numeric tokens. A reader that reproduces `Ava_01`
    and `0.1.6` perfectly while inventing different Korean rule sentences on each
    draw passes at ≤10% — and invention in prose is the precise failure mode ADR-0010
    §2 prices the tier for ("the author was right and the reader invented"). The limit
    is disclosed but the gate is not narrowed to match it.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: untestable-requirement
  severity: high
  description: '§2.1 states "No extractor becomes **or remains** the reader of record
    without a measured self-agreement rate" and fixes ≤10%, while §3 makes not changing
    the reader of record a non-goal and §2.4 keeps the 84.7% reader serving. The document
    therefore contains a normative rule its own state violates on publication, with
    no deadline, owner, failing condition, or gate that observes the violation. Nothing
    can be run that fails, so the requirement is decorative: the reader that does
    not meet the bar remains the reader of record indefinitely.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: undefined
  severity: medium
  description: '§2.4 says the current reader''s poor reproducibility is "recorded
    on the extraction rows", but §1 measured Sonnet on 20 of 44 images and §2.3 defines
    `NULL` as "nobody checked". Which rows receive 0.847 is unspecified: writing it
    to all 44 asserts a measurement on 24 images that were never drawn twice (breaking
    the column''s own NULL semantics), writing it to 20 leaves the rest indistinguishable
    from unexamined, and nothing says how the 20 were selected — so a reader cannot
    tell whether the sample was random, first-N, or the images that had already looked
    suspicious.'
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: missing-invariant
  severity: medium
  description: '`reader_variation` is added to `vision_extractions`, which no consumer
    reads. ADR-0010 §4 requires the provenance signal to survive six named hops, and
    the fields that actually travel live on `chunks` (`provenance_tier`, `extractor_identity`,
    `source_ref` — `nexus/migrations/013_provenance_tier.sql`). Nothing joins a `SearchHit`,
    an evidence packet, a citation, an API response or an MCP result back to the extraction
    row. §2.3''s stated purpose — "so that a reading can at least be interpreted"
    — is met for nobody outside psql, and the SPEC states no invariant that the value
    must reach a surface.'
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: missing-invariant
  severity: medium
  description: §4.4 requires `reader_variation` to "accept 0..1, and reject values
    outside it", but the DDL in §2.3 is a bare `NUMERIC` with no CHECK constraint.
    Postgres will accept -1 and 2 silently, so the test as specified fails against
    the migration as specified — and, worse, a harness bug that emits a ratio outside
    the range is storable and would later read as a legitimate rate.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: missing-invariant
  severity: medium
  description: §4.5 requires migration 015 to be idempotent, but the statement given
    is `ALTER TABLE vision_extractions ADD COLUMN reader_variation NUMERIC;` without
    `IF NOT EXISTS`, against a repo convention that uses it everywhere (`ADD COLUMN
    IF NOT EXISTS` throughout `013_provenance_tier.sql`). Re-running raises duplicate_column
    and aborts the transaction, so the migration as written fails its own test.
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: missing-invariant
  severity: medium
  description: The §2.1 procedure calls the reader a second time on bytes that already
    have a stored result under the same `extractor_identity` — the exact operation
    ADR-0010 §5 governs. The SPEC never states that the measurement harness runs out
    of band and must not write to `vision_extractions` or produce chunks. Today the
    only thing preventing a second draw from becoming the record is the incidental
    `ON CONFLICT DO NOTHING` in `vision_store.save()` (`nexus/nexus/ingest/vision_store.py:44`),
    which the SPEC does not cite and a future harness author has no reason to preserve.
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: unverifiable-claim
  severity: medium
  description: '§2.1: "The bar is set an order of magnitude above the passing measurement
    and an order of magnitude below the failing one." 3.6% → 10% is 2.8×; an order
    of magnitude above 3.6% is 36%. The arithmetic offered as the reason the threshold
    is not drawn around today''s winner is wrong in the direction that matters, and
    the bar in fact sits between the only two readers ever measured with the passing
    one nearer to it.'
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: unverifiable-claim
  severity: medium
  description: '§1.2: "The gap (4/20 versus 35/44) is far outside what more images
    would move." No interval, test, or power argument is given, and the two arms differ
    in sample size, image subset, sampling temperature (see the temperature finding)
    and reasoning budget — Gemini ran at `thinkingLevel: minimal`, which `vision_gemini_probe.py`
    records cannot be set to zero, while the Sonnet arm had no equivalent control
    and an earlier run showed 58,838 thinking tokens on one side only. This is the
    same shape of unbacked comparative assertion §1.1 withdraws four drafts of work
    for.'
  status: accepted
  disposition_reason: null
- issue_id: I-016
  category: risky-assumption
  severity: medium
  description: §2.2 claims "Rendering is folded, content is not", but §4.3 and §5
    concede that `10–20` and `10 - 20` yield different token sets. That is a rendering
    difference the normalisation fails to fold, so any two draws that differ only
    in spacing around a range register as variation. On a corpus of specification
    tables this biases the measured rate upward against a 10% gate that a reader cleared
    at 3.6% — the residual 9 differing Gemini pairs are exactly where this would show.
    Pinning the defect in a test freezes a known measurement bias into the instrument
    the threshold is read from.
  status: accepted
  disposition_reason: null
- issue_id: I-017
  category: scope-creep
  severity: low
  description: §3 defers the reader-of-record change to "its own record", but §2.1
    fixes that record's binding acceptance criterion ("a reader of record must reach
    token variation ≤ 10%") in advance. The deferred decision arrives with its pass/fail
    line already drawn from data gathered before the deferral, which is the same pre-emption
    the document objects to when a SPEC constrains an ADR.
  status: rejected
  disposition_reason: '문턱을 지금 못박는 것이 이 SPEC 의 요지다. 재현율 기준을 판독기 교체 SPEC 으로 미루면, 그때
    고를 후보의 측정값을 보고 선을 긋게 된다 — 오늘 네 번 되돌아온 실패가 정확히 그것(숫자를 본 뒤 기준을 맞춤)이다. ADR 을 SPEC
    이 제약하는 것과 다르다: 여기서 정하는 것은 **이 SPEC 이 도입하는 계측기의 합격선**이고, 그것을 계측기와 같은 문서에 두는 것이
    사전등록이다. 다만 지적의 절반은 옳아서 §2.1 의 근거를 ''두 측정에서 멀다''(틀린 산수)에서 ''ADR-0010 §5 의 해석 키가
    의미를 갖는 최대 불일치''로 바꿨다.'
- issue_id: I-018
  category: undefined
  severity: low
  description: '44 and 45 are used interchangeably without stating the mapping: "44
    images", "the 45 `machine_read` chunks", "`claude-sonnet-4-6/18c36580` for all
    44 rows", "what the 44 live rows are", "§2.4 What happens to the 45 live chunks".
    Images, `vision_extractions` rows and chunks are three different populations under
    the schema, and a labelling and migration plan that addresses "the rows" cannot
    be checked for completeness without knowing which population each count refers
    to.'
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-11T09:46:02Z'
---

