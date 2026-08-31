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
  status: accepted
  disposition_reason: 불변식 I-5 신설 — 쓰기는 principal.tenant 로 해소되고 목록 원소로는 절대 아니다. 목록이
    생기면 tenants[0] 로 리팩터하는 것이 자연스럽고 그게 잘못된 테넌트에 적재한다는 지적이 정확하다.
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
  status: accepted
  disposition_reason: 설계를 바꿨다. 부팅 검사 B-3 로 len(read_tenants) > 1 을 U1 에서 거부하고, C-4
    는 살아 있는 principal 이 아니라 effective_scope 단위 검사로 바꿨다. '설정 한 줄만 쓰면 열리는 상태로 출하한다'는
    지적이 맞았다.
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
  status: accepted
  disposition_reason: 실재 테넌트 검사를 뺐다. 기동을 DB 내용에 의존시키면 비어 있는 신규 테넌트나 재적재 중 재시작이 서비스를
    죽인다. 오타는 §3.2 의 기록으로 잡는다.
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
  status: accepted
  disposition_reason: 세어서 적었다. '130곳'도 '두 곳'도 틀렸다 — 전체 32곳, 검색 읽기 경로 12곳이고 파일·건수를
    §1.2 에 열거했다. 목록을 반환하면 그 12곳이 전부 바뀌어야 한다.
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
  status: accepted
  disposition_reason: C-1 에 타이브레이크(ORDER BY score DESC, chunk_rid)와 기준선 포착(라벨 18개
    질의, CI)을 박았다.
- issue_id: I-006
  category: undefined
  severity: medium
  description: 'I-7 and C-3 require every out-of-scope tenant request to be recorded
    server-side as `tenant_out_of_scope`, but §3.3 explicitly places ''로그 스키마 변경''
    in the cutover SPEC. The sink is therefore undefined: application log line, `search_log`
    row, `a2a_audit` row, or metric counter — each has different retention, tenancy,
    and query-text-consent implications (a rejected tenant name is caller-supplied
    input). C-3 cannot be written as a test until the sink is named.'
  status: accepted
  disposition_reason: §3.2 에 자리를 명시했다 — 새 표 없이 애플리케이션 로그 한 줄 + 계수기, 요청 원문 미저장. search_log·a2a_audit
    스키마는 안 건드린다.
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
  status: accepted
  disposition_reason: §5 에 선행 조건 P-1 을 신설했다 — backstop ruling 이 director 서명으로 채워지기
    전에는 구현하지 않는다. 2판은 pending 으로 두고도 그것을 막는 조건이 없었다.
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
  status: accepted
  disposition_reason: §1.3 에 적었다 — 교차 테넌트 supersession 은 오늘의 프리미티브로 표현이 불가능하고, 컷오버
    SPEC 은 ADR-0006 개정이나 새 식별자를 필요로 한다. 있는 것으로 되는 일처럼 앞으로 미루지 않는다.
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
  status: accepted
  disposition_reason: §2 를 다시 썼다. '이 성질을 없애지 않는다'는 거짓이었다 — 요청 tenant 를 좁히는 데 쓰므로 성질은
    없어지고, 남는 보장은 '좁힐 수만 있다' 하나다. 낡은 tenant 를 보내던 호출부가 조용히 좁아지는 부작용도 적었다.
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
  status: accepted
  disposition_reason: 응답이 해소된 범위를 들고 나가게 했다. 코퍼스 X 를 묻고 Y 로 답을 받는데 아무 신호가 없으면 에이전트에겐
    오류보다 나쁘다는 지적이 맞다.
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
  status: accepted
  disposition_reason: 1,582 도 상한이라고 적었다 — 제목 일치는 사본 동일성이 아니고 status 필터도 없다. 사본 식별
    술어는 컷오버 SPEC 이 정한다.
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
  status: accepted
  disposition_reason: C-5 신설 — 원소 하나 배열의 질의 계획이 스칼라와 같거나 p95 가 기준선 안이어야 한다.
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
  status: accepted
  disposition_reason: C-4 를 단위 검사로 바꾸고 §3.1 예시의 read_tenants 를 원소 하나로 줄였다. 복사해 붙이면
    §0 이 안 만든다고 한 상태가 되는 경로를 없앴다.
approved_by: LivingLikeKrillin
approved_at: '2026-08-31T01:10:09Z'
---

