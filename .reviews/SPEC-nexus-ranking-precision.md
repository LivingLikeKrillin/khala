---
target: SPEC-nexus-ranking-precision
critiqued_hash: sha256:a7ce5dec51129aad2744782b38477afe73be794a4570f90d2649780dca644911
critiqued_at: '2026-07-11T18:43:13Z'
issues:
- issue_id: I-001
  category: risky-assumption
  severity: high
  description: 'The core recall-safety argument (§1, §3, §4.1: ''reorder candidates
    without dropping any'', ''no row added or removed'') is false whenever the WHERE
    clause matches more than bm25_top_k rows. _bm25_search (hybrid.py:66-83) applies
    `ORDER BY rank_score DESC LIMIT $4`, so swapping ts_rank → ts_rank_cd changes
    WHICH rows survive the LIMIT, not just their order. With OR-tsquery semantics
    (the recent recall fix) matching well over 20 chunks on a real corpus is the norm,
    so the change CAN drop the gold chunk from the leg''s returned set and regress
    recall. The strict harness stays green only because its pinned fixture has 5 documents
    — far below the LIMIT — which masks the unsoundness rather than proving safety.'
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: unverifiable-claim
  severity: medium
  description: §6 requires a test asserting 'the matched set is identical to ts_rank
    (recall unchanged)'. This assertion is only true (and only passes) when matched
    rows ≤ LIMIT; on the small fixture corpus it will trivially pass while proving
    nothing about production behavior where the LIMIT binds. The test as specified
    manufactures false confidence in the exact claim that is structurally unsound.
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: undefined
  severity: medium
  description: §4.2 gives two different, conflicting bounds for the candidate pool
    — 'up to final_top_k × POOL (e.g. ×4)' and 'bounded by 2 × bridge_top_k' — without
    stating which governs, and `bridge_top_k` does not exist anywhere in the codebase
    (the legs are configured by `search.bm25_top_k` and `search.vector_top_k`, hybrid.py:285-286).
    The POOL multiplier's config key, default value, and whether it is tunable are
    all unspecified ('e.g. ×4' is an example, not a decision), while per_doc_cap gets
    a config.yaml key but also only an example default ('e.g. 3').
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: medium
  description: 'After _diversify, SearchResult.hits is no longer sorted by the exposed
    SearchHit.score field (skipped-then-filled hits have higher RRF scores than earlier
    selected ones). The SPEC never states the post-diversification ordering contract
    for downstream consumers — evidence packet assembly, the web UI, MCP/A2A clients,
    and the citation-validation path (PR #134) — some of which may assume score-descending
    order or use score for display/thresholding. This silent contract change is exactly
    the kind of invariant §5 should pin.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: missing-invariant
  severity: medium
  description: '§5''s pinned invariant ''never fewer results than min(top_k, len(pool))''
    is not enforceable as stated: _diversify operates on hits AFTER _enrich_hits,
    which silently drops pool members whose chunk row is missing at enrichment time
    (hybrid.py:230-233, `if not r: continue`). The actual guarantee is min(top_k,
    len(enriched_hits)); a test written against the stated invariant either can''t
    be written or must quietly test the weaker property. The SPEC should state the
    invariant relative to the enriched set.'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: risky-assumption
  severity: medium
  description: §4.1's 'MRR should hold or improve' is asserted without argument. 'Proximity'
    in tsvector_ko is proximity in the mecab POS-filtered token stream (josa/eomi/symbols
    removed, bm25.py:35-43), not raw text, and ts_rank_cd is also known to produce
    coarser, tie-heavy scores than ts_rank for sparse OR matches. On the 6-query pinned
    fixture a single rank inversion moves keyword-leg MRR by ~0.03-0.17, so the ≥0.80
    gate can regress from reordering alone; the doc offers no reasoning or measurement
    that cover density helps on this corpus, only that the harness will catch failure
    after the fact.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: unverifiable-claim
  severity: low
  description: §1 grounds both changes in 'the query-quality review flagged' them,
    but no review artifact, search_log/v_search_health signal, or observed instance
    of single-document flooding is cited. Per the repo's own demand-pull discipline
    (ranking-intelligence work gated on collected search signals), the motivating
    evidence should be linkable; as written, the premise that document flooding actually
    occurs in practice cannot be verified from the SPEC.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: adr-contradiction
  severity: low
  description: No direct contradiction with linked ADR-0004 was found — but that is
    because ADR-0004 (component grounding division, Archon repositioning, deployment
    classes) contains no decision bearing on search ranking at all. The governing
    decisions this SPEC should be checked against — the demand-pull gate on reranking/ranking
    work tied to the search-signal infrastructure, and the search-recall SPEC that
    introduced OR semantics and the harness — are not linked, so the 'checked against
    linked ADRs' review step is vacuous as scoped.
  status: rejected
  disposition_reason: 크리틱 스스로 '직접 모순 없음'이라 확인했다. ADR-0004는 Nexus 검색 컴포넌트의 우산 ADR로
    링크한 것뿐이며 상충하지 않는다 — 조치 불요.
- issue_id: I-009
  category: untestable-requirement
  severity: low
  description: §6 requires a DB-backed test that 'asserts the BM25 SQL uses ts_rank_cd'
    — a string-match on the implementation rather than a behavioral property. It is
    brittle (breaks on any harmless SQL refactor), proves nothing the adjacent proximity-ordering
    assertion doesn't already prove, and should be dropped or restated as a behavioral
    requirement.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-11T18:45:36Z'
---

