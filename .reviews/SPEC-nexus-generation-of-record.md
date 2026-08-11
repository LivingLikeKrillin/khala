---
target: SPEC-nexus-generation-of-record
critiqued_hash: sha256:5749712ef46358b5d4bdc3985a613d22df1615c555889aa338df7ab6a9e0dcf9
critiqued_at: '2026-08-11T00:29:32Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: §3.3 changes `_save_chunks` to null *every* vector column on a text
    change, which includes the old `embedding` column. ADR-0009's Consequences record
    the cutover invariant that "the old `embedding` column and its index [are] retained
    untouched, and rollback = three `.env` lines plus a restart", and ADR-0009 already
    flags that post-flip ingests leave that column NULL with "no gate consum[ing]"
    the count. §3.3 makes the rollback column decay faster (every edited chunk now
    loses its 768 vector too) while the SPEC never mentions rollback, never updates
    `nexus reembed status --column embedding` expectations, and adds no acceptance
    criterion for the retained column. The SPEC silently degrades a documented rollback
    guarantee of another accepted-path record.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: adr-contradiction
  severity: high
  description: ADR-0009's open-items table assigns "A rollback guard for the post-flip
    NULL gap" the trigger "Before any rollback, or **the next SPEC touching the embedding
    columns**", and assigns "a mechanism that detects backstop events, or a declaration
    made after the fact" and "a usable predicate for 'materially expand'" the trigger
    "**the next SPEC that links ADR-0008**". This SPEC is both — it links ADR-0008
    and rewrites the write path for the embedding columns — yet §4 (Non-goals) and
    §7 (Open items) neither discharge, decline, nor even acknowledge any of the three
    obligations. Obligations with named owners and detectable triggers pass through
    undischarged and silently.
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: risky-assumption
  severity: high
  description: '§3.2''s "No declaration → proceed, and warn once" leaves the incident
    fully reachable on every deployment that exists today, including the one that
    suffered it: there is no migration that backfills a declaration from the running
    deployment''s env, and no step in §3 or §5 that requires one. §6''s acceptance
    explicitly presupposes "the declaration for `default` set to embedding_1024/KURE-v1",
    so the SPEC demonstrates the guard only in the state nobody is in after upgrading.
    The fix''s effectiveness depends entirely on an undocumented, unprompted, untested
    human action.'
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: §3.2 exempts `nexus reembed run` from the declaration check and leaves
    it with only its dimension guard — but §2 states that guard "catches writing a
    1024 vector into a 768 column, not writing a *correct* 768 vector that nobody
    will search", which is exactly the accident. `nexus reembed run --column embedding
    --model nomic-embed-text` on the host therefore reproduces the incident through
    the one command the SPEC deliberately leaves unguarded. Nothing requires or verifies
    that the declaration is updated when a cutover completes; §3.2 only asserts "the
    declaration is how the change is recorded", with no mechanism, no test (test 5
    checks only that reembed is *not* blocked), and no way to notice a cutover that
    finished without re-declaring.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: missing-invariant
  severity: high
  description: §3.1 claims the declaration is "read by every write path", but §3.2
    specifies the check only in `run_ingest`, and §5's tests exercise only `nexus
    ingest`. Other paths that write chunks and vectors — `ingest-notion`, the HTTP
    ingest endpoint, the MCP ingest tool, and `ingest_external_spec` (the Arbiter
    promotion path ADR-0008 §7 records as writing into Nexus) — are neither named
    nor tested. The stated invariant and the specified implementation do not match,
    and any unlisted path is an unguarded replay of the incident.
  status: rejected
  disposition_reason: '사실이 다르다. 열거된 경로가 전부 run_ingest 로 모이는 것을 확인했다: cli.py:84(ingest)
    · a2a/server.py:370(governed-doc·external-spec) · api.py:487·545(HTTP) · ingest-notion
    은 _default_external_ingest_fn 을 ingest_fn 으로 넘겨 같은 a2a/server.py:370 을 탄다. 검사를
    run_ingest 한 곳에 두면 전부 덮인다. 다만 SPEC 이 그 수렴을 보이지 않고 주장만 한 것은 맞아서, §3.2 에 호출지점 표를
    넣었다.'
- issue_id: I-006
  category: missing-invariant
  severity: medium
  description: The `index_generation` table (§3.1) has no constraint tying `column_name`
    to a registered vector column or `model` to that column's dimension, and §3.2/§5
    specify no validation in `declare`. `nexus generation declare --column embedding_1024
    --model nomic-embed-text` (a 768 model in a 1024 column) is accepted, and a typo'd
    column name is accepted and then makes *every* ingest refuse forever with a message
    naming a column that does not exist. §3.3 enumerates columns "from the column
    registry" — the same registry is available here and is not used.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: risky-assumption
  severity: medium
  description: '`tenant` is the table''s PRIMARY KEY and "no declaration → proceed
    and warn" is per-tenant, so any ingest run against a tenant that has no row bypasses
    the guard entirely. A mistyped or defaulted `--tenant` silently restores the pre-fix
    behaviour, and it is precisely the operator running the wrong-shell command who
    is most likely to also be running with the wrong tenant resolution. No test covers
    a declared tenant coexisting with an undeclared one.'
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: adr-contradiction
  severity: medium
  description: ADR-0006's Decision item 1 ships "correct 're-embed only changed'"
    and its Consequences claim it is "fixing the stale-vector bug" / "killing stale-vector
    retrieval drift". §1.1 measures 8 chunks whose stored vector does not match their
    current text — that claim is falsified, and the mechanism (nulling only one column
    while the other survives a text change) was present in ADR-0006's own design.
    §7 records an obligation to amend the wrong sentence in SPEC-nexus-index-completeness
    §1 but records nothing about ADR-0006's now-false Consequences claim, leaving
    a stamped ADR asserting a bug is dead that this SPEC measured alive.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: unverifiable-claim
  severity: medium
  description: §1.1's control group is 45 chunks re-embedded that day — KURE-v1 chunks
    in `embedding_1024` — but the 8 findings are all on `nomic-embed-text`-labelled
    chunks in the other column, produced by a different model and a different (host)
    runtime. The control establishes recompute determinism for the arm where nothing
    was found, not for the arm where everything was found. A negative control on the
    nomic path (a nomic chunk known to be current, recomputed to 1.000000) is what
    would rule out the mismatches being an artifact of the host/container model-loading
    difference rather than genuine staleness.
  status: rejected
  disposition_reason: 두 행은 같은 팔이다. 재계산은 전부 컨테이너의 KURE 서비스로 `embedding_1024` 를 상대로
    했다(check_stale_vectors.py 는 configured_column() 하나만 읽는다). `nomic-embed-text` 는
    chunks.embed_model 이고 그것은 **다른 컬럼**의 마지막 writer 이름이라, 그 라벨을 단 청크의 1024 벡터도 KURE
    가 쓴 것이다. 즉 대조군과 발견은 같은 모델·같은 컬럼이고, 호스트/컨테이너 모델 로딩 차이는 이 측정에 들어오지 않는다. 라벨이 두 모집단처럼
    읽히게 표를 쓴 것은 맞아서 §1.1 에 그 문장을 넣었다.
- issue_id: I-010
  category: undefined
  severity: medium
  description: The §1.1 table column "vector does not match current text" has no stated
    decision threshold. 1.000000, 0.9954 and 0.593 are quoted, and §6 later uses "cosine
    ≥ 0.9999", but §1.1 never says which cutoff produced 8-out-of-119 — so the headline
    count cannot be reproduced or falsified from the document, and it is unclear whether
    0.9954 is the worst *passing* value or the best *failing* one.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: missing-invariant
  severity: medium
  description: Test 1 specifies that "re-declaring the same tenant replaces it", and
    the schema has no history table and no append-only ledger. §2 identifies the core
    problem as being unable to answer "which generation is this chunk indexed under";
    a table that overwrites its only row destroys the sole record of when the previous
    generation stopped being of record, so after a cutover nothing can date chunks
    against it. Every other declaration artifact in this system (`doc_reingest_events`
    in ADR-0006, the lifecycle ledger) is append-only; this one is not, without a
    stated reason.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: adr-contradiction
  severity: medium
  description: ADR-0009's Consequences record the shipped cutover invariant as "one
    generation per column (`embed_health` reports a single `embed_model` for the target
    column)". §1 establishes that 119 chunks now carry a `nomic-embed-text` label
    beside a KURE vector, i.e. that invariant is currently violated in production.
    §3 specifies no repair of those labels, §4 declines to touch `embed_model` at
    all, and §6 has no acceptance criterion for `embed_health` returning to a single
    model. Known-corrupt data is left in place, the seam invariant stays broken after
    this SPEC lands, and nothing detects it.
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: risky-assumption
  severity: medium
  description: §7 defers a durable staleness detector on the grounds that the durable
    form "is a migration and a write-path change on every indexing path" — but §3.1
    already introduces a migration and §3.3 already changes the vector-write path
    on every indexing path. The stated cost of the deferred option is largely being
    paid by this SPEC anyway, so the deferral's justification does not hold as written.
    The supporting scaling claim (334 chunks / ~35 minutes) is a single unbaselined
    measurement on one machine, with no target corpus size or budget defining what
    "does not scale" means.
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: unverifiable-claim
  severity: medium
  description: '"**Every number from the incident fits this and only this.**" is a
    uniqueness claim, but §1 eliminates exactly one alternative ("a run that stopped
    would have left neither"). Combinations — a partially-failed container run *plus*
    a later host ingest, or an interrupted reembed — would produce the same 51/119
    signature and are not addressed. Since §7 commits to amending an approved, stamped
    SPEC on the strength of this claim, the standard of proof matters and "and only
    this" is not established.'
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: untestable-requirement
  severity: low
  description: §3.2's "proceed, and warn once" and test 4's "proceeds and warns once"
    never define the scope of "once" — once per ingest run, per process lifetime,
    per tenant, per day, or per chunk. The test asserts a count against an undefined
    denominator, and the requirement cannot fail in any well-defined way. Given §1's
    finding that a real warning was "buried in 739 lines" of routine output, warn-frequency
    semantics are load-bearing here, not cosmetic.
  status: accepted
  disposition_reason: null
- issue_id: I-016
  category: missing-invariant
  severity: low
  description: '`declared_by` is `TEXT NOT NULL` populated from a self-asserted `--by
    <who>` flag, with no authentication, authorization, or attribution check specified.
    The SPEC leans on "declaration, not inference" as its legitimacy story and cites
    the exemption-list precedent, but the surrounding practice for declarations that
    carry authority (Arbiter''s "approve is a human signature — no self-approval")
    is not applied, so the audit field records whatever string the caller typed.'
  status: accepted
  disposition_reason: null
- issue_id: I-017
  category: risky-assumption
  severity: low
  description: §3.4 rewrites `README.md` and `CLAUDE.md` so that "every command that
    writes" is prefixed `docker exec nexus-app nexus …`. These are repository-level
    docs for a public repo, but the prefix is correct only for the single-host containerized
    dogfood topology; a reader running Nexus without that container name, or natively,
    is now given commands that cannot work. The SPEC treats one deployment's topology
    as the documented default without stating that assumption or offering a non-container
    form.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-11T03:02:28Z'
---

