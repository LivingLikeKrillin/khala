---
target: SPEC-nexus-answer-number-verification
critiqued_hash: sha256:811a2114db58fb4dddc7850b0ef1b75c0a134d79ed98b5a837707519bc993e3e
critiqued_at: '2026-07-13T07:24:51Z'
issues:
- issue_id: I-001
  category: risky-assumption
  severity: high
  description: The grounding set is `evidence_text ∪ query`, so any fabricated figure
    that echoes a number in the user's question is auto-grounded (§3 'Grounding set',
    I-001). But the question is not evidence. A common failure — the LLM parroting
    a number from the prompt into an authoritative-sounding claim ('is it above 50%?'
    → 'yes, 50%') — is systematically suppressed. The spec conflates 'shown to the
    LLM' with 'supported by evidence' and never acknowledges this class of miss (only
    the coincidental-evidence-collision miss is documented).
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: undefined
  severity: medium
  description: 'Significance is defined on token properties (''non-zero decimal part'',
    ''integer magnitude ≥10'') but the spec never fixes whether significance is evaluated
    on the raw token or the canonicalized value (after strip-trailing-zeros). `9.0`,
    `10.0`, `3.0` classify differently depending on order: `10.0`→`10` is significant
    post-canonical but has a zero decimal pre-canonical; `9.0` is a decimal token
    but canonicalizes to a sub-10 integer. This ordering ambiguity makes the significance
    filter''s output undefined for these inputs.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: untestable-requirement
  severity: medium
  description: The core quality goal — 'tuned to minimize false accusations' (§3 Error
    direction) and acceptance 'tuned to avoid false accusations' — has no metric,
    threshold, or measurable criterion. The tests assert only a handful of specific
    example cases; there is no defined false-positive/false-negative rate or corpus
    to test 'minimized' against, so the stated acceptance property cannot be verified.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: unverifiable-claim
  severity: medium
  description: The justification for the ≥10 significance boundary rests on 'it excludes
    the dominant false-positive class (small derived counts like "3 services")' (§3).
    No data, measurement, or corpus is cited to establish that small integers actually
    dominate false positives; it is asserted as the rationale for the central scoping
    decision. The doc even concedes it is 'not a proven optimum,' but then relies
    on the unproven claim to justify the design.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: risky-assumption
  severity: medium
  description: 'The version pre-strip `\d+(?:\.\d+){2,}` is applied to the grounding
    text as well as the answer (§3 I-005). This can delete legitimately-cited decimals:
    evidence `3.2.1` loses the `2.1` datum, so an answer stating `2.1` becomes falsely
    unverified; and a greedy match over `47.5.2` swallows the real decimal `47.5`.
    The mechanism intended to prevent spurious numbers can itself manufacture false
    flags in the grounding set.'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: risky-assumption
  severity: medium
  description: The grounding model is unit-blind except for a special-cased `%` class,
    and this special-casing is inconsistent. `120ms`→`120` so a fabricated dimensionless
    `120` grounds against a latency figure; currency is stripped (`$47`≡`47`) collapsing
    classes; yet `%` is kept distinct. There is no stated principle for why percent
    is dimensioned but ms/currency/count are not, so the class model is arbitrary
    and lets meaning-mismatched values ground each other.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: undefined
  severity: low
  description: The extraction regex (§3 'Extract') specifies currency, thousands separators,
    one decimal, and trailing `%`, but says nothing about sign or ranges. Negative
    numbers (`-5%`, `-3`) and hyphenated ranges (`10-20`, which would split into `10`
    and `20`) have undefined extraction/canonicalization behavior, and a leading minus
    is silently dropped so `-5` and `5` would collide.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: undefined
  severity: low
  description: 'Percent detection requires an immediately-trailing `%` token. Space-separated
    (`47 %`) or spelled-out percent is unspecified: `47 %` extracts as bare `47` (integer
    class) and would fail to ground against evidence `47%` (percent class), producing
    an over-flag. The boundary between percent and bare-integer class for whitespace/spelled
    forms is undefined.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: missing-invariant
  severity: low
  description: '`unverified_count` and the `numbers` list are defined independently
    (§3: count = ''number of distinct unverified canonicals''; numbers = distinct
    significant answer numbers with a `grounded` flag). No invariant ties them together
    (`unverified_count == len([n for n in numbers if not n.grounded])`), and no test
    asserts it, so the surfaced count and the list can silently drift.'
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: scope-creep
  severity: low
  description: '`AnswerResult` gains a full `numbers: list[dict]` field (§3 Wiring)
    that nothing consumes — the wire carries only the count and the renderer is explicitly
    deferred (§4). Persisting an unused structured field now, ahead of any reader,
    is speculative generality that the ''scope-tight'' framing (I-008) contradicts.'
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-13T07:26:55Z'
---

