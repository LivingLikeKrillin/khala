---
target: SPEC-nexus-code-semantic-cards
critiqued_hash: sha256:d75a49e24bb6f4295bc39a940a8c2e57f439b69ace0209971faac7f3a35a57c8
critiqued_at: '2026-08-16T09:43:17Z'
issues:
- issue_id: I-001
  category: scope-creep
  severity: high
  description: '§2 non-goal states "edges are typed by comparison in a later unit"
    and "No LLM adjudication of doc-vs-code disagreement in this SPEC", but §3.5 and
    Unit 3 (§7) specify exactly that inside this SPEC: batch verification returning
    "a relation type and a confidence, plus the reason". The non-goal and the design
    section describe different scopes; a reviewer cannot tell which one the acceptance
    gates in §6 apply to.'
  status: open
  disposition_reason: null
- issue_id: I-002
  category: adr-contradiction
  severity: high
  description: §0 leaves the ADR-0008 §5 backstop explicitly unresolved ("Whether
    'not user-facing' is enough … is the director's call") while §7 still lists Units
    2–4 and §6 still gates on yield and cost-per-edge, which only exist if Unit 2
    ships. ADR-0008 §5 names "a second index backend" as precisely the moment the
    incumbent's cost is being repaid; a SPEC that both records the backstop as firing
    and proceeds to specify the gated work has not paid it. Either the decision is
    recorded, or Units 2–4 belong in a separate SPEC.
  status: open
  disposition_reason: null
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: §3.4 binds card embeddings to "the deployment's configured generation",
    but the generation of record covers the embedding model only — it does not cover
    the card generator model, prompt version, or traversal settings that produced
    the text being embedded. Two cards written by different generator prompts are
    indistinguishable inside one declared generation, which is the same class of silent
    heterogeneity SPEC-nexus-generation-of-record was written to prevent. The generator
    identity must be part of the declared record and enforced at write time.
  status: open
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: §2 asserts "No source text is stored" and that the lexical unit's invariant
    "extend[s] unchanged", but §3.2 stores `code_terms` (verbatim source identifiers)
    and imposes no rule preventing the generator from quoting source lines inside
    `behavior` or `subject`. No re-check in §3.2 tests for verbatim source in generated
    prose, and no acceptance gate in §6 covers it. The boundary between "generated
    prose" and "source text" is undefined and untested.
  status: open
  disposition_reason: null
- issue_id: I-005
  category: undefined
  severity: high
  description: §3.5 makes the confidence threshold the sole precision control for
    edge creation, but names no value, no scale, no calibration procedure, and no
    way to set it before edges exist. §6 gates the generator (6.1, 6.2) and reports
    yield (6.3) but never gates or fits this threshold, so the single knob that determines
    whether refusal actually holds is unspecified.
  status: open
  disposition_reason: null
- issue_id: I-006
  category: undefined
  severity: high
  description: The SPEC never states who consumes the edges it produces or what they
    mean downstream. §2 forbids cards from appearing in search, answers, or citations,
    but says nothing about edges; the relation type vocabulary is never enumerated
    (only `supported_by` appears, in passing in §4). Without a defined consumer and
    type set, §6.3's "the number is the deliverable" is a count of objects with no
    specified semantics.
  status: open
  disposition_reason: null
- issue_id: I-007
  category: risky-assumption
  severity: high
  description: §6.2 accepts up to 6 of 30 cards (20%) with a false `behavior`, while
    §4 identifies a false `behavior` as "the most expensive failure here" because
    a document agreeing with the wrong description binds as `supported_by`. No relation
    is established between card-level falsity rate and edge-level error rate — a 20%
    wrong-card population could produce a far higher or lower share of wrong edges
    depending on which cards attract matches. The gate is set on the wrong quantity.
  status: open
  disposition_reason: null
- issue_id: I-008
  category: untestable-requirement
  severity: medium
  description: §6.1 gates `behavior` on "semantic equivalence, judged by a human on
    a 20-card subsample" with no rubric, no equivalence criterion, no inter-rater
    check, and — unlike `domain_terms` — no threshold at all. A gate with no pass
    condition cannot block anything, yet §6.1 is declared to block the entire rest
    of §6.
  status: open
  disposition_reason: null
- issue_id: I-009
  category: risky-assumption
  severity: medium
  description: '§6.1''s 0.7 `domain_terms` set-overlap threshold is asserted, not
    derived: "below that the matching layer is measuring the generator''s noise" states
    a conclusion without connecting overlap to retrieval outcome. Two runs also give
    n=2 per symbol, which yields a point estimate with no interval — directly at odds
    with §5''s own claim that "[e]very number here is a sample with an interval".
    The vision-reproducibility precedent cited in §3.3 established a noise floor from
    repeated trials, not a pair.'
  status: open
  disposition_reason: null
- issue_id: I-010
  category: risky-assumption
  severity: medium
  description: 'All three cited evidence points are English-corpus and same-language:
    Greptile''s 0.8152/0.7280 is English query↔English docstring, CodeRAG-Bench (DS-1000)
    is English. The problem this SPEC exists for is Korean policy prose ↔ Java/Python
    identifiers, where the repository''s own record shows embedding-model choice dominates
    outcome (the KURE cutover). Transferring a ~12% English uplift to a Korean cross-register
    task is an assumption, and §6 contains no gate that would detect it failing before
    Units 2–3 are built.'
  status: open
  disposition_reason: null
- issue_id: I-011
  category: missing-invariant
  severity: medium
  description: §3.4 embeds cards under the deployment's configured generation, and
    a generation cutover is a live pending decision. Unit 4 (§7) covers regeneration
    only on span change, so an embedding-generation change silently leaves the entire
    card population unmatched against newly ingested documents. No invalidation rule
    for cards on generation change is stated, and no test covers it.
  status: open
  disposition_reason: null
- issue_id: I-012
  category: missing-invariant
  severity: medium
  description: Unit 4 and §4 trigger card staleness on "the span hash changes", but
    the card schema in §3.2 carries only `repo, file, start_line, end_line, symbol`
    and `commit_sha` — there is no span hash field. As specified, staleness can only
    be detected by line range, which shifts on any unrelated edit above the symbol,
    producing false staleness; and no rule states what happens to edges pointing at
    a stale card (retained, suppressed, deleted).
  status: open
  disposition_reason: null
- issue_id: I-013
  category: undefined
  severity: medium
  description: §3.5 records rejections "so the same proposal does not return", but
    never defines proposal identity. Cards are regenerated non-deterministically (§3.3
    measures exactly this), so card text and `domain_terms` change between runs; any
    rejection key derived from card content will fail to suppress the recurrence it
    exists to prevent. A stable key (symbol + span + alias pair) must be specified.
  status: open
  disposition_reason: null
- issue_id: I-014
  category: undefined
  severity: medium
  description: §3.1's card-candidate rule is written in Java vocabulary — "a class/interface/record"
    — while §2 fixes the scope at "Java and Python, the two grammars that exist".
    Python has neither interfaces nor records, and the rule says nothing about module-level
    functions, dataclasses, or nested definitions. Candidate selection is therefore
    undefined for half the supported languages, and cost and coverage both depend
    on it.
  status: open
  disposition_reason: null
- issue_id: I-015
  category: undefined
  severity: medium
  description: §3.1 defers the method body line threshold to "a parameter with a default"
    without naming the default, and §3.4's top-k is "k small and recorded" without
    a value. Both are described as the primary cost and coverage controls, and §6.4
    gates on cost per run — but the run cannot be costed or reproduced from the SPEC,
    and two implementations could differ by an order of magnitude while both conforming.
  status: open
  disposition_reason: null
- issue_id: I-016
  category: risky-assumption
  severity: medium
  description: §6.4 directs development runs to "use the keyless path unless a paid
    run is authorised in advance", but §6.1–6.2 measure reproducibility and faithfulness
    of a specific generator. If the reproducibility and faithfulness gates are measured
    on the keyless bridge backend and production cards are generated by a different
    model, the gates certify an instrument that will not be the one shipping. The
    SPEC must state that all §6 gates and the production run use the same declared
    generator, or report them separately per backend.
  status: open
  disposition_reason: null
- issue_id: I-017
  category: untestable-requirement
  severity: medium
  description: '§6.3 explicitly sets "No threshold: the number is the deliverable"
    for yield on the target corpus — the acceptance gate the whole SPEC is justified
    by cannot fail. Combined with §5''s pre-registered excuse ("matching will find
    little and that is a finding about the corpus, not a failure of the method"),
    there is no outcome of §6.3 that would falsify the direction. At minimum a pre-registered
    number below which the direction is abandoned should be recorded before the run.'
  status: open
  disposition_reason: null
- issue_id: I-018
  category: unverifiable-claim
  severity: medium
  description: §1 reports "9 candidates, of which realistically zero were genuine
    code references" — "realistically zero" is not a count and the adjudication rule
    is not given — and then asserts "no amount of loosening the extractor creates
    one — loosening only trades the measured 79% precision for noise". No loosened
    configuration was run; the 79% figure comes from the unloosened extractor on a
    different (engineering) corpus. This is the load-bearing claim that the cheap
    path cannot be extended, and it rests on an unrun experiment.
  status: open
  disposition_reason: null
- issue_id: I-019
  category: undefined
  severity: medium
  description: §3.2 has the agent "following calls, not just the declaration" with
    no depth bound, no cycle handling, no cross-file or third-party boundary, and
    no cap on tokens read per card. §4 identifies unbounded cost as a principal risk
    and §6.4 gates on it, but the traversal that generates that cost is left entirely
    to the implementation.
  status: open
  disposition_reason: null
- issue_id: I-020
  category: untestable-requirement
  severity: low
  description: §6.5 requires that the lexical path's "24-anchor census re-runs unchanged",
    but the census is a measurement over this repository's moving contents (§1 dates
    it 2026-08-16). Ordinary code and document changes will alter the count without
    any harm from this SPEC, so the check either fails spuriously or is quietly ignored.
    It must be pinned to a fixed commit and a stored expected set.
  status: open
  disposition_reason: null
- issue_id: I-021
  category: adr-contradiction
  severity: low
  description: §0 records the gate as fired in this SPEC, citing ADR-0002's rule that
    a gate is "recorded in that direction's first SPEC". This is not the first SPEC
    in the doc↔code binding direction — SPEC-nexus-doc-code-anchors shipped first
    and §1 presents this work as its continuation. Either this is a new direction
    (in which case the continuity framing in §1 is doing gate-shaped work) or the
    gate record belongs to the earlier SPEC; the SPEC should say which.
  status: open
  disposition_reason: null
- issue_id: I-022
  category: untestable-requirement
  severity: low
  description: §6.4 requires "spend per produced edge", but under §0's stated fallback
    (Unit 1 alone, "No embedding, no matching") no edges are produced and the metric
    is undefined. The fallback path is offered as a shippable outcome yet has no acceptance
    criteria of its own — §6.3 and §6.4 both presuppose Unit 2.
  status: open
  disposition_reason: null
approved_by: null
approved_at: null
---

