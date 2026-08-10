---
target: SPEC-nexus-index-completeness
critiqued_hash: sha256:1e2d3c207c08ab8c3a5916638e9972a8e3e3f7da46439cfe8b748a452a4e23ec
critiqued_at: '2026-08-10T18:17:43Z'
issues:
- issue_id: I-001
  category: risky-assumption
  severity: high
  description: §2.1's premise — that the existing net 'counts what is present, never
    what is absent' — is false as stated. `nexus/nexus/index/embed_health.py::fetch_coverage_by_tenant()`
    already computes, in one aggregate, per-tenant active-chunk counts against BOTH
    `embedding` and `embedding_1024` populated counts, and `log_embedding_coverage()`
    already emits `embedding_coverage_partial` (and `embedding_column_empty`) for
    exactly this condition. The design attributes to a missing measurement what is
    actually a surfacing/timing defect (that function runs at startup and only logs;
    it is not run after ingest and drives no exit code or ⚠). §3.1's `vector_gap`
    therefore re-implements an existing query under a new name, and the SPEC's whole
    framing ('the existing net could not ring') would need rewriting around the real
    defect.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: adr-contradiction
  severity: high
  description: '§3.2.2 (`nexus ingest` exits non-zero when either gap > 0) reverses
    a design decision already taken and recorded, without citing or arguing against
    it. `log_embedding_coverage()`''s docstring records that refusing on NULL coverage
    was reviewed and rejected: NULL vectors are an ordinary transient state (just
    after ingest, a dead ingest, a 413 awaiting a waiver), a new tenant''s first ingest
    is legitimately coverage 0, and ''making that a refusal turns an ordinary ingest
    accident into a whole-deployment outage — enforcement belongs where a cutover
    condition is; only a check with a decision attached is entitled to refuse.'' The
    SPEC must either overturn that reasoning explicitly or scope its refusal to a
    decision point.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: adr-contradiction
  severity: high
  description: '§3.1 claims both gaps are measured ''over the same population the
    search legs actually read'', but the stated population is only `status=''active''
    AND NOT is_quarantined`. ADR-0006''s containment spine adds a document-level filter,
    implemented in `nexus/nexus/search/hybrid.py:100-102` and `:141-143`: `AND EXISTS
    (SELECT 1 FROM documents d WHERE d.rid=c.doc_rid AND d.status=''active'')`. Active
    chunks under a superseded document are read by no search leg, yet count as a gap
    forever — producing a permanent non-zero exit on every ingest and a permanent
    ⚠, the exact always-on-alarm failure §2.4 says is fatal. §5 test 1 tests a superseded
    *chunk* and never the superseded-parent case.'
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: The waiver exclusion `rid NOT IN (waived)` is not generation-scoped,
    but `embed_waivers` (migration 008) is `chunk_rid TEXT PRIMARY KEY` with a separate
    `model` column — one waiver per chunk, ever, across both vector columns. A chunk
    waived under nomic-embed-text/768 silently suppresses a genuine `embedding_1024`
    gap, and no second waiver can be recorded for the new generation. With two coexisting
    columns (ADR-0009), the gap query must join on the waiver's `model`/column, and
    the schema must permit a waiver per generation. Neither is specified.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: adr-contradiction
  severity: high
  description: '§3.3 removes the mixed-generation ⚠ while ADR-0009 Consequences records
    ''one generation per column (`embed_health` reports a single `embed_model` for
    the target column)'' as a live invariant of `SPEC-nexus-embedding-cutover-seam`.
    The proposed replacement — dimension of the searched column plus a populated count
    — cannot detect the invariant''s violation at all: any two models emitting 1024
    dimensions (a KURE upgrade, a second Korean model) are indistinguishable by `vector_dims`.
    The SPEC deletes the only alarm on a recorded invariant and substitutes a signal
    that is structurally incapable of firing for it, without amending the cutover
    SPEC.'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: risky-assumption
  severity: high
  description: '§2.4 declines to establish how 119 chunks came to carry a stale `nomic-embed-text`
    label after a cutover that ADR-0009 records as re-embedding 167/167 with zero
    failures — then retires the alarm anyway (''the structural defect does not depend
    on knowing''). It does depend on knowing: if a write path updates `chunks.embed_model`
    without re-embedding (or vice versa), that is a live data-integrity bug in the
    ingest/reembed path, and the ⚠ is currently its only symptom. §3.3 also keeps
    `embed_generation_report` in service (''tested and used elsewhere'') on data the
    SPEC has just argued is untrustworthy.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: risky-assumption
  severity: high
  description: The failure mode of the 2026-08-10 run is never established, and the
    entire remedy assumes the process survived. §2.3 says `run_ingest` catches, appends
    to `IngestResult.errors`, and logs `vector_indexing_failed` — so a signal did
    exist; §1 asserts 'Nothing said so' without checking whether that log line or
    `errors` was populated. If the run was killed (OOM/SIGKILL/timeout), no in-process
    code in §3.2.1 or §3.2.2 executes — no gap is computed, no exit code is set —
    and the defect recurs exactly as before, detectable only at the next `nexus status`.
    The SPEC needs either evidence the run raised, or a remedy that does not live
    inside the dying process.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: missing-invariant
  severity: high
  description: §6's acceptance ('`nexus status` on the current database prints no
    warning') contradicts §3.1's own facts. §3.1 states the eval-pack tenants `ko_eval_arm`
    and `ko_eval_packb` hold 289 chunks each with no vector in either column, in the
    same database, by design — and §3.2.3 marks ⚠ for any tenant with a gap. Per-tenant
    scoping does not remove the always-on alarm, it relocates it from one global line
    to two per-tenant lines (and §5 test 5 asserts precisely that ⚠). No exemption
    mechanism (a tenant flag, a pinned-corpus marker, an exclusion list) is defined
    for deliberately unindexed comparison corpora.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: undefined
  severity: high
  description: 'The gap''s scope is tenant-wide but the failure it gates is run-scoped:
    §3.2.1 fills `vector_gap` ''for the tenant just ingested'', so any pre-existing
    gap unrelated to this run (a chunk under a superseded document, a stale-model
    waiver, a partially rolled-back column, an in-flight 413) makes every subsequent,
    perfectly successful ingest exit non-zero. §6''s acceptance (''a printed count
    that equals the number of chunks with no vector'') inherits the same ambiguity.
    The SPEC must define whether the gate is on the delta this run left behind or
    on the tenant''s standing state.'
  status: rejected
  disposition_reason: 전제가 사라졌다. I-002 를 받아 게이트(비영 종료코드) 자체를 없앴으므로 '이번 실행이 남긴 델타냐 테넌트의
    누적 상태냐'가 거부 여부를 가르지 않는다. §3.2 는 테넌트의 현재 상태를 보고할 뿐이고 그것이 읽는 사람이 알아야 할 값이다 — 이번
    실행 탓이 아닌 구멍도 여전히 벡터 다리가 못 보는 청크다. §3.4 의 적재 후 출력도 같은 값을 찍는다.
- issue_id: I-010
  category: adr-contradiction
  severity: medium
  description: 'ADR-0009''s open-items table names two triggers that this document
    fires and does not take up: ''A rollback guard for the post-flip NULL gap — Before
    any rollback, or **the next SPEC touching the embedding columns**'', and ''A mechanism
    that detects backstop events / a usable predicate for "materially expand" — **The
    next SPEC that links ADR-0008**''. This SPEC links ADR-0008 and defines new gates
    over the embedding columns. Worse, by scoping `vector_gap` to ''<configured column>''
    only, it builds exactly the gate machinery ADR-0009 says is missing (''`nexus
    reembed status --column embedding` reports the count and no gate consumes it'')
    while leaving the old column''s gap unconsumed — creating the appearance that
    completeness is now covered when the rollback hazard is untouched.'
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: risky-assumption
  severity: medium
  description: '§1 withdraws the queued ranking work on a single coarse metric. ''Gold
    document outside the top 10: 3 → 0'' is Recall@10 only; ADR-0009''s pre-registered
    rule (`SPEC-nexus-korean-embedding-comparison` §4.7) fixes Recall@10 *with MRR@10
    breaking recall ties*, a two-sided sign test at α=0.05, and no verdict below 6
    discordant pairs. Here n=40 with a 3-query difference, no rank-position measure,
    and no significance test — while the SPEC''s own table shows 34/400 top-10 slots
    (8%) still held by tiny documents and 2 queries whose top 10 is still majority-tiny.
    ''The expected benefit… is now 0 of 40'' asserts the absence of an effect the
    instrument cannot see.'
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: missing-invariant
  severity: medium
  description: '`bm25_gap` tests only `tsvector_ko IS NULL`, which does not cover
    the equally dark state of an *empty* tsvector. `tokenize_korean()` (`nexus/nexus/index/bm25.py`)
    returns only tokens whose POS is in `_INCLUDE_POS`, and falls back to whitespace
    splitting when mecab init fails; a chunk yielding no qualifying tokens produces
    `''''::tsvector`, which is non-NULL and unreachable by the keyword leg. The same
    class of miss motivates the whole SPEC (present-vs-absent), so the gap predicate
    should be NULL-or-empty, and §5 test 2 should include the empty case.'
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: untestable-requirement
  severity: medium
  description: §6's second acceptance criterion — `nexus status` 'would have printed
    one at 2026-08-10 13:10 UTC' — is a counterfactual over a database state that
    no longer exists (`reembed run` filled 51/51 before this document was written)
    and for which no snapshot, dump, or fixture is specified. As written it can be
    neither run nor failed. It needs restating as a reconstructable fixture (seed
    a tenant with N NULL-vector active chunks and assert the warning), which §5 test
    5 nearly is.
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: undefined
  severity: medium
  description: The exit code conflates two operator actions with opposite remedies.
    §4 rules out retry/resume inside `run_ingest` on the grounds that `nexus reembed
    run` is the fix, yet §3.2.2 signals that state through the one channel schedulers
    universally interpret as 'retry the command' — a retry that re-runs ingest and
    cannot close the gap. Nothing distinguishes 'ingest failed' from 'ingest succeeded,
    corpus incomplete, run reembed' (distinct exit codes, or a machine-readable field).
    This also silently breaks existing automation around `nexus ingest`/`ingest-notion`,
    and no compatibility note is given.
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: risky-assumption
  severity: medium
  description: §5 test 3 exercises only total failure ('the embedding service raises
    for every batch'), but the defect under repair is a *partial* run — vectors written
    for some chunks in the same window and not others. The all-or-nothing path can
    pass while the partial path (batch loop aborting mid-iteration, per-batch commit
    ordering, gap computed before the final commit) stays uncovered. §3.2.1's 'filled
    after the indexing steps regardless of whether they raised' also does not say
    whether the count is taken inside or outside the ingest transaction, which decides
    what a partial run reports.
  status: accepted
  disposition_reason: null
- issue_id: I-016
  category: unverifiable-claim
  severity: low
  description: 'The corpus figures are stated without measurement timestamps or shown
    tenant scoping, and at least one pair cannot both hold at the same instant: §1
    reports 51 of 334 active chunks with NULL `embedding_1024`, while §2.4 reports
    ''334 active chunks, every one of which holds both a 768-dim and a 1024-dim vector''.
    §2.4 evidently postdates the repair, but says so nowhere, and the corpus-mixed
    conclusion is drawn from it. Separately, 289 appears three times as three different
    populations (operating-tenant `authored` chunks, and each of the two eval-pack
    tenants), which is the shape an unscoped query produces; the queries should be
    shown.'
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-10T18:44:40Z'
---

