---
target: SPEC-nexus-search-recall
critiqued_hash: sha256:0bcc875fab1b456cb40ef5a87baa41d60f668982cf13d992c8463cab19b74f3e
critiqued_at: '2026-07-10T09:14:10Z'
issues:
- issue_id: I-001
  category: unverifiable-claim
  severity: medium
  description: The core measurement table (§3.1) cites '14 queries' but reports misses
    as '10/13', '1/13', '4/13' (denominator 13), while §4.1 reports the same experiments
    over 14 queries with denominator 14. The inconsistent query count (13 vs 14) makes
    the headline recall numbers unverifiable and internally contradictory.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: untestable-requirement
  severity: high
  description: 'The §4.3 assertion ''The keyword leg alone finds the gold document
    for every query that contains a content word present in it'' is not operationally
    defined: ''content word'' is undefined, and given mecab-ko fragments tokens (엔티티
    -> 엔+티티), ''present in it'' cannot be reliably determined. The assertion cannot
    be evaluated deterministically as written.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: undefined
  severity: medium
  description: '''content word'' in §4.3 and §7 is never defined. Whether a term counts
    as a content word (vs mecab fragment, stopword, or one-character token like 있)
    determines pass/fail of the central regression assertion, yet no definition or
    list is provided.'
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: risky-assumption
  severity: high
  description: The design assumes OR-joining relies on ts_rank to order chunks by
    match density, but RRF (used in fusion) credits by rank not score, so a chunk
    matching 1 of 5 lexemes contributes the same-shaped evidence as one matching all
    5. The doc itself flags this as 'the honest risk' on a 20-doc corpus but ships
    anyway with no guard, betting the regression test will catch degradation later
    — a risky assumption that noise won't materialize before the test fires.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: missing-invariant
  severity: medium
  description: No invariant bounds the number of chunks the OR query may return or
    match. With OR, a common single lexeme can match a large fraction of 163 chunks;
    there is no cap, minimum-match threshold, or score floor specified, leaving the
    keyword leg's output size unconstrained.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: unverifiable-claim
  severity: medium
  description: The rejected-alternative 'Dropping one-character tokens' cites 'MRR
    0.575 vs 0.595' but no 0.595 baseline appears in any other table (the OR baseline
    is 0.681 end-to-end and 0.795 per-leg). These orphan numbers cannot be reconciled
    with the presented measurements.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: untestable-requirement
  severity: medium
  description: 'The §7 acceptance criterion ''Ask Nexus a question in Korean using
    more than three words, and the keyword leg answers'' is not testable as stated:
    ''answers'' is unquantified (any hit? a relevant hit? top-1?) and ''more than
    three words'' does not guarantee any content word is indexed, so the criterion
    has no deterministic pass condition.'
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: risky-assumption
  severity: low
  description: §5 claims OR 'does not widen the injection surface; the same escaping
    applies' but provides no evidence that the tsquery boolean-operator change is
    neutral to injection; asserting equivalence without demonstrating that the quoting/escaping
    path is unchanged for the new joiner is an unproven safety assumption.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: adr-contradiction
  severity: low
  description: ADR-0004 §1 classifies Nexus as grounding in a 'derived document index
    (a snapshot that can drift)' and explicitly reserves 'decision-grade fact-check'
    and freshness/authority signaling to the distinct Archon engine (nexus/nexus/claims/).
    The design doc's framing that fixing recall makes 'route mean what the API says
    it means' and the acceptance goal of trustworthy answers risks conflating Nexus
    retrieval quality with grounding correctness; the doc never acknowledges the Archon
    grounding boundary despite touching search/hybrid.py which the ADR names as Nexus's
    symbol.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: scope-creep
  severity: low
  description: The §4.2 requirement that 'vector_only with no embedding_svc returns
    no hits and says so in route_used; it does not quietly fall back to BM25' introduces
    new fallback-suppression behavior beyond the stated goal of 'fix recall' and 'make
    route honoured' — reasonable, but it is a behavioral change to the no-embedding
    path not motivated by any measured failure in §3.
  status: rejected
  disposition_reason: vector_only + embedding_svc=None 을 zero-hit 로 못 박는 것은 폴백 '메커니즘'
    이 아니라 단언 한 줄이다. 조용히 BM25 검색으로 바뀌면서 route_used 는 vector_only 라 보고하는 것이 지금의 결함이므로,
    이 단언은 §4.2 의 본체다. 범위 확장이 아니다.
- issue_id: I-011
  category: missing-invariant
  severity: medium
  description: The recall floors in §4.3 are 'recorded as constants with the date
    and corpus' but no invariant ties the seeded test corpus to the live corpus the
    measurements were taken on. If the seeded corpus differs from the 20-doc/163-chunk
    live corpus, the recorded MRR/top-3 floors are not meaningful and the regression
    test could pass while live recall degrades.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-10T09:18:13Z'
---

