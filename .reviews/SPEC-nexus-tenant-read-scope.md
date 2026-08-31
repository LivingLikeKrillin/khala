---
target: SPEC-nexus-tenant-read-scope
critiqued_hash: sha256:2406abdeaea20751afcad0368d23034d288621f34310860129330f8fe92c8d57
critiqued_at: '2026-08-31T00:34:33Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: '§3.3 changes `effective_scope` from `(tenant, clearance)` to `(tenants:
    list[str], clearance)`, but nothing defines where the *write* tenant comes from
    afterwards. I-5 only says the write path ''does not receive the list''; it does
    not pin write tenant == principal.tenant. Boot check 1 (§3.1) requires only `tenant
    ∈ read_tenants`, not `tenant == read_tenants[0]`, so an implementation that writes
    to `tenants[0]` — the natural refactor when every caller now gets a list — would
    silently ingest into the wrong tenant for any principal whose list is ordered
    `["design_docs", "default"]`. Add an invariant + check: writes resolve to the
    declared `tenant` field, never to a list element.'
  status: open
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: §3.4 correctly identifies that the global `classification_level` enum
    is only safe because one principal reads one tenant, then defers per-chunk clearance
    to the cutover SPEC and enforces this with prose ('컷오버 SPEC 의 진입 조건으로 박는다') —
    after stating in the same paragraph that '산문 전제로는 부족하다'. Meanwhile C-4 requires
    the code to actually serve two tenants to a 2-element list. The mechanism therefore
    ships able to cross a clearance-vocabulary boundary, guarded only by the fact
    that nobody has written the config line yet. §4 has no invariant such as 'len(read_tenants)
    > 1 is rejected at boot until per-chunk clearance exists' — and C-4 forbids exactly
    that guard. A `design_docs` chunk labeled `internal` under one tenant's vocabulary
    becomes readable by a `default` principal whose `internal` means something weaker,
    the moment one config line is added, with no check firing.
  status: open
  disposition_reason: null
- issue_id: I-003
  category: risky-assumption
  severity: high
  description: '§3.1 boot check 3 makes process startup depend on DB *content* (''documents
    에 그 tenant 행이 하나라도 있는지''). Failure scenarios: (a) a legitimately empty or newly-provisioned
    tenant is listed → server refuses to boot; (b) the last document of a listed tenant
    is deleted or the tenant is re-ingested from scratch → next restart bricks the
    service; (c) the DB is unreachable or mid-migration at boot → undefined whether
    the check fails open, fails closed, or crashes. Neither the failure mode nor the
    DB-unavailable case is specified, and C-2 only tests the positive rejection. A
    typo-detection check should not be able to take down a running deployment on restart;
    make it a warning, or scope it to a tenant registry rather than row existence.'
  status: open
  disposition_reason: null
- issue_id: I-004
  category: undefined
  severity: medium
  description: §3.3 claims U1 touches exactly two places, but §1.1's own measurement
    reports 130 non-test `AND tenant` predicates, and the second row is only described
    as '`hybrid_search` 와 그것이 부르는 질의'. Which of the 130 are (i) read queries reached
    from `hybrid_search`, (ii) other read paths (evidence assembly, claims/value_query,
    feedback, ops-map) that keep `tenant = $1`, or (iii) writes, is never enumerated.
    Any read path left on the singular predicate while `effective_scope` now returns
    a list will either fail to type-check or silently coerce (e.g. `tenants[0]`),
    producing results scoped to a different tenant than the search leg that fed it.
    The SPEC needs the enumerated call-site list as an artifact, not a grep count.
  status: open
  disposition_reason: null
- issue_id: I-005
  category: untestable-requirement
  severity: medium
  description: 'I-4 / C-1 require the ''top-k order'' to be *identical* before and
    after, but no tie-break determinism is established for hybrid search: RRF ties,
    `ivfflat` probe behavior, and Postgres plan choice under `tenant = ANY($1)` can
    reorder equal-scoring rows without any semantic change. The SPEC simultaneously
    concedes (§5) that noise-width estimation is deferred to the cutover SPEC. So
    C-1 is either flaky or it is passing for reasons nobody characterized. Specify
    the corpus, the query set, the k, the tie-break (e.g. `ORDER BY score DESC, chunk_rid`),
    and how the ''before'' baseline is captured in CI.'
  status: open
  disposition_reason: null
- issue_id: I-006
  category: undefined
  severity: medium
  description: 'I-7 and C-3 require every out-of-scope tenant request to be recorded
    server-side as `tenant_out_of_scope`, but §3.3 explicitly places ''로그 스키마 변경''
    in the cutover SPEC. The sink is therefore undefined: application log line, `search_log`
    row, `a2a_audit` row, or metric counter — each has different retention, tenancy,
    and query-text-consent implications (a rejected tenant name is caller-supplied
    input). C-3 cannot be written as a test until the sink is named.'
  status: open
  disposition_reason: null
- issue_id: I-007
  category: adr-contradiction
  severity: medium
  description: '§0.1 records the ADR-0008 backstop with `ruling: pending-director`,
    and ADR-0002 (Follow-on backlog; restated in ADR-0008 §3 item 3) fixes the procedure
    as ''a gate is declared fired by the director and recorded in that direction''s
    first SPEC — it is not argued into existence by the SPEC''. ''pending'' means
    the gate has not been declared fired, yet §5''s completion conditions contain
    nothing that blocks implementation or merge on that ruling being filled in. As
    written, U1 can ship with the gate permanently unresolved. Add the ruling as an
    explicit precondition row in §5.'
  status: open
  disposition_reason: null
- issue_id: I-008
  category: adr-contradiction
  severity: medium
  description: '''교차 테넌트 중복 억제'' is deferred to the cutover SPEC (§0), but ADR-0006''s
    supersession primitive is structurally tenant-scoped — `supersede(old_rid, new_rid,
    tenant)` resolves both documents with `WHERE rid = $1 AND tenant = $2`, and the
    retrieval-time containment filter is a per-document `status=''active''` test.
    There is no expressible declaration for ''the `design_docs` original supersedes
    the `default` copy''. So the deferred work is not merely unscheduled here; it
    cannot be done with the mechanism ADR-0006 accepted, and the cutover SPEC will
    require either an ADR-0006 amendment or a new cross-tenant identity key. This
    SPEC should say so rather than forward-referencing a solution that does not exist.'
  status: open
  disposition_reason: null
- issue_id: I-009
  category: risky-assumption
  severity: medium
  description: '§2 states the current design property — `effective_scope` *ignores*
    the request tenant — and asserts ''이 SPEC 은 그 성질을 없애지 않는다''. §3.2 then makes the
    request tenant load-bearing: an in-list value narrows the scope. The property
    is in fact removed; what survives is only the weaker ''the request cannot widen''
    (I-1). This matters because the safety argument for the current design (isolation
    + no existence leak) is being cited to cover a contract it no longer describes,
    and callers that today send an arbitrary/stale `tenant` value harmlessly will,
    once any list exists, have their results silently narrowed. Restate §2 as the
    narrowing-only guarantee and re-derive the isolation argument from that.'
  status: open
  disposition_reason: null
- issue_id: I-010
  category: risky-assumption
  severity: medium
  description: '§3.2 row 3: an out-of-scope tenant request is answered from the principal''s
    default tenant with no error. The caller asked about corpus X and receives an
    answer grounded in corpus Y, with §3.3 explicitly excluding evidence assembly,
    citation verification, and badges from this SPEC — so nothing in the response
    signals the substitution. For an agent consumer this is worse than an error: it
    produces confidently-cited wrong-corpus answers. The server-side log (I-7) helps
    the operator, not the caller. At minimum the response should carry the resolved
    scope, which is a response-shape decision this SPEC is currently deferring.'
  status: open
  disposition_reason: null
- issue_id: I-011
  category: unverifiable-claim
  severity: medium
  description: §1.1 defines '사본' as 'a `default` document whose title also exists
    in `design_docs`' and reports 1,582 chunks as the corrected figure. Title equality
    is not copy identity — distinct documents sharing a title (a known hazard, since
    ADR-0006 records `canonical_uri = tenant:filename` basename collisions) inflate
    it, and a copy that was retitled deflates it. The query also counts all `chunks`
    rows with no `status='active'` predicate, so superseded chunks are included. The
    initial 1,849 was correctly demoted to an upper bound; 1,582 is an upper bound
    by the same argument and should not be stated as '사본은 1,582 다'.
  status: open
  disposition_reason: null
- issue_id: I-012
  category: missing-invariant
  severity: medium
  description: 'The claim that unattached principals behave exactly as today (§3.3,
    §5) is asserted for result *sets and order* only. `tenant = $1` → `tenant = ANY($1)`
    is a plan-visible change: composite `(tenant, …)` index usage and row-count estimates
    can differ even for a single-element array, and the live corpus is thousands of
    chunks per tenant. No latency or plan invariant is stated and C-1 would pass while
    p95 regresses. Add an `EXPLAIN`-level or latency-bound condition, or pin the single-element
    case to the scalar predicate.'
  status: open
  disposition_reason: null
- issue_id: I-013
  category: scope-creep
  severity: low
  description: 'C-4 constructs a live 2-element-list principal to prove the mechanism
    works, annotated ''배포에는 안 붙인다''. Nothing enforces that annotation: the synthetic
    principal is a config shape, and §4 has no invariant restricting multi-element
    lists to test fixtures or to non-production tenants. Combined with the shipped
    §3.1 example block, which itself shows `read_tenants: ["default", "design_docs"]`,
    the SPEC ships a copy-pasteable path to the exact state §0 and §3.4 promise this
    SPEC does not create.'
  status: open
  disposition_reason: null
approved_by: null
approved_at: null
---

