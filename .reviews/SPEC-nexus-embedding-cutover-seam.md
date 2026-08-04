---
target: SPEC-nexus-embedding-cutover-seam
critiqued_hash: sha256:29fdade3b65ed5aed22ae70ac577b8ef24c17c6a8ca5225d90c151d09cafb9e3
critiqued_at: '2026-08-04T16:29:45Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: §4.6's flip restarts only `nexus-app` (`docker compose up -d nexus-app`),
    but §1 names six construction sites across three process families — `nexus/api.py`,
    `nexus/a2a/server.py:303`, `nexus/cli.py:221`, `nexus/ingest/pipeline.py:243`.
    The SPEC never states that all of them share one env/restart boundary. If the
    a2a server, a scheduled ingest job, or an operator's CLI shell still carries the
    old triple after the flip, §4.3's 'write path follows the setting' means those
    processes keep writing `embedding` and leave `embedding_1024` NULL — the exact
    silent, unraised failure of §1.5 that this SPEC exists to remove, now reintroduced
    by the procedure itself. No invariant ('every process that constructs an EmbeddingService
    reads the same deployment env'), no check, and no test covers the multi-process
    case.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: '§4.5''s revision pin is detect-only with no remedy. `reembed status`
    compares the *running* sidecar''s `/health.revision` against the pinned value,
    but §4.3 invariant 1 makes the re-embed queue NULL-rows-only, and §2 explicitly
    defers ''a re-embed verb that can rewrite non-NULL rows'' to the provenance SPEC.
    So if the check fires after a mid-migration checkpoint change — rows already populated
    from weights A, sidecar now on B — the operator is told the cutover is refused
    and has no in-SPEC action that can fix it: the only paths are manual SQL to NULL
    the column or an undefined recovery. A detection with no defined remediation is
    a permanently blocked cutover, and §5/§7 do not name what the operator does next.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: adr-contradiction
  severity: high
  description: 'The gate procedure ADR-0008 §3(3) fixes — ''a gate is declared fired
    by the director and recorded in that direction''s first SPEC'' — was not followed,
    and §1.1 concedes it: the swap SPEC (the direction''s first SPEC) was approved
    2026-08-04, one day *before* the 2026-08-05 declaration, and the §5 backstop re-read
    happened at the start of this SPEC''s work rather than the swap SPEC''s, which
    §5 requires (''re-read at the start of any work that would materially expand Nexus''s
    retrieval stack ... an embedding-model change''). Disclosing the violation is
    not the same as repairing it: the swap SPEC''s approval — the authority this SPEC''s
    Unit 4 implements — was taken while ADR-0008 §6''s block was still in force. The
    SPEC calls recording it ''the repair available now'' without proposing that the
    swap SPEC be re-recorded, so the defect is documented and then carried forward
    as if cured.'
  status: rejected
  disposition_reason: The ordering defect is real and is now recorded in §1.1 with
    its retrospectivity explicit; what the issue asks for — re-recording the already-approved
    swap SPEC — would invalidate its stamped content_hash and rewrite the chronology
    rather than record it. Arbiter has no amend verb, and a governance record whose
    repair is to overwrite the record is worse than a disclosed defect. The director
    holds the gate and declared it fired knowing the order in which it happened.
- issue_id: I-004
  category: adr-contradiction
  severity: high
  description: '§1.1''s directorial declaration lifts ADR-0008 §6''s embedding-change
    block on evidence the ADR''s own text says cannot lift it. ADR-0008 §2.6 states
    the gap is that ''no instrument exists that could compare them'' where the instrument
    must work on Khala''s corpus (§5(b): ''compares tokenizers on Khala''s real corpus''),
    and §6 lists the embedding-model change as blocked by that same gap. The instrument
    that exists (Pack A, `kubernetes/website` Korean docs) is a public stand-in, and
    §1.1 admits both that this ''narrows a condition the ADR stated more broadly''
    and that (b) is open. The SPEC labels the narrowing ''the director''s'', but ADR-0008
    §5 gives the director judgment over conditions (b) and (c), not authority to substitute
    a different corpus for the one §2.6 names — and the recall margin (0.402 vs 0.975)
    is measured on the substitute, so its size cannot itself justify the substitution.'
  status: rejected
  disposition_reason: ADR-0008 §5 names LivingLikeKrillin as the owner of these conditions.
    The substitution of a public stand-in corpus for khala's real one was put to them
    explicitly, with the difference and the open (b) named, and they decided it lifts
    §6's embedding-change block for this swap. The SPEC records that decision and
    does not perform the narrowing itself; it also leaves (b) open and says so. A
    SPEC arguing an ADR condition away would be the defect — this one asked the owner
    and wrote down the answer.
- issue_id: I-005
  category: risky-assumption
  severity: high
  description: '§4.6 closes the ingestion race with an operator promise plus one extra
    pass, and both legs are weaker than claimed. ''No ingestion runs during the window''
    has no enforcement mechanism — no lock, no flag, no ingest-side refusal — and
    the justification ''on this deployment ingestion is manual or scheduled, not continuous''
    concedes a scheduler exists that can fire unattended mid-window. The second pass
    is then said to be ''the evidence that nothing arrived meanwhile'', but it only
    proves nothing arrived *before that pass*: anything ingested between the second
    `reembed run` and `docker compose up -d nexus-app` gets `embedding` filled, `embedding_1024`
    NULL, and becomes vector-invisible at the flip with nothing raising. The window
    the design actually leaves open is never named or bounded.'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: untestable-requirement
  severity: medium
  description: '§7 lists "The deployment''s `.env` reaches the process: the effective
    triple inside a started container is the one the `.env` names" under **Automatically
    verifiable (§6)**, but §6 places exactly that check under ''Against compose (documented,
    run at wiring time rather than in CI)''. The one acceptance criterion guarding
    §4.5''s self-described load-bearing precedence trap (a literal `environment:`
    value silently beating `.env`, producing ''a flip that reports success and changes
    nothing'') is therefore a one-off manual step, not an automated gate — and nothing
    re-runs it if someone later edits compose.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: undefined
  severity: medium
  description: §2's checkable bound ('`/status` gains exactly one additional aggregate
    query — a single `GROUP BY tenant` over `chunks` counting both columns', asserted
    by a query-counting test in §6) cannot produce the fields §4.2 requires. §4.2's
    coverage record is `embedded / active / waived / pending`, and `waived` comes
    from `embed_waivers` (§4.6 condition 1, §5), a different table — unobtainable
    from a GROUP BY over `chunks` alone. Either `/status` omits the waived count (and
    §4.6 condition 1 is not answerable from `/status`), or the query bound and its
    test are wrong. The SPEC does not say which, so what `/status` actually reports
    is undefined at the point where the cutover decision is made.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: missing-invariant
  severity: medium
  description: '§4.5 adds `embedding_backend_connected` and `embedding_revision` to
    `/status`, both requiring outbound HTTP to the sidecar''s `/health` or Ollama''s
    `/api/tags`, with no timeout, no cache, and no failure budget specified. §2''s
    guard bounds only DB queries, so these calls escape it entirely. The failure mode
    is precisely the one §1.8 complains about: the health endpoint an operator reads
    during a cutover — exactly when the sidecar is most likely unreachable or slow
    to start — can now block on a hung connection instead of returning `null` promptly.
    §5 says the field is `null` ''when the backend is unreachable'' but never defines
    how unreachability is bounded in time.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: undefined
  severity: medium
  description: '`SearchResult.degraded: list[str]` is defined as an internal field
    with legal values asserted against the leg registry, but the SPEC never says it
    reaches an API consumer. `/search`, `/search/answer`, the streaming path, and
    the a2a surface have no stated response-schema change, and §2 defers only *persistence*
    to `search_log`. §1.3''s stated defect is that a degraded deployment ''looks healthy
    while returning keyword-only results with no signal that it is doing so'' — a
    field that exists only inside the process and in an error log does not close that
    for the caller, and §6''s Postgres test asserts `degraded == ["vector"]` on the
    internal object rather than on any response body.'
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: unverifiable-claim
  severity: medium
  description: '§4.5 asserts that pinning `EMBED_REVISION` means ''the vectors in
    the column and every later query vector come from one checkpoint'', but nothing
    in §6 or §7 verifies that the sidecar image actually consumes `EMBED_REVISION`
    — the only evidence offered is that the *unpinned* sidecar reports `"revision":
    "(unpinned)"`. The pin is also derived by reading the resolved snapshot out of
    the already-running sidecar, so it records what happens to be loaded rather than
    independently fixing it. There is no test of the form ''set `EMBED_REVISION` to
    a known commit, restart, assert `/health.revision` equals it'', which is the single
    check that would turn the pin from a declaration into a mechanism.'
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: untestable-requirement
  severity: medium
  description: '§4.7''s pre-registered rule (''`/search` p95 after ≤ 1.5 × p95 before
    and ≤ 1500 ms absolute'') fixes the threshold but not the measurement point of
    ''before''. The §4.6 procedure contains no latency step at all, and the window
    it describes changes several things that move `/search` p95 independently of the
    flip: the re-embed populates `embedding_1024`, `create-index` builds a second
    ivfflat index, and §4.7 itself requires recording corpus counts ''before and after''
    because drift is expected. A ''before'' taken pre-re-embed and a ''before'' taken
    post-index-build are different numbers against the same 1.5× multiplier, so the
    rule cannot be applied unambiguously or reproduced by a reviewer — which defeats
    the stated purpose of naming it in advance.'
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: risky-assumption
  severity: low
  description: '`MODEL_BACKENDS: {"nomic-embed-text": "ollama", "KURE-v1": "sidecar"}`
    hardcodes a 1:1 model→backend relation and §4.2 refuses any other pairing at construction
    (''KURE-v1 is not served by Ollama''). That is a fact about today''s two deployments,
    not about the models: a second sidecar host, a GGUF KURE served through Ollama,
    or a staging backend would be refused by a code table rather than by config, and
    §2 rules out the provider registry that would otherwise absorb this. The doc also
    never defines whether `backend` names a *kind* (ollama/sidecar protocol) or an
    *endpoint*, which is what decides whether `EMBED_URL` and `EMBEDDING_BACKEND`
    can disagree.'
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: undefined
  severity: low
  description: '§4.6 condition 3 — ''`embed_health` reports a single generation **for
    the target column**'' — is carried over as a cutover gate, but `embed_health`
    is never defined in this SPEC: not a table, view, CLI verb, or `/status` field
    anywhere in §3–§5, and §6 contains no test for it. ''A single generation'' is
    likewise undefined given §2''s explicit refusal of per-row provenance: with no
    `chunks.embed_revision` column, it is unclear what fact about the rows this condition
    even reads.'
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: undefined
  severity: low
  description: '§4.2''s override table mixes naming conventions without explanation:
    `NEXUS_EMBEDDING_MODEL` and `NEXUS_EMBEDDING_COLUMN` are prefixed, `EMBEDDING_BACKEND`
    is not (and `EMBED_URL`/`EMBED_REVISION` use a third form). Since §4.5 requires
    each to appear in compose as `${VAR:-default}` interpolation and §4.6''s rollback
    is ''those three env lines back'', an unprefixed `EMBEDDING_BACKEND` is both easy
    to mistype as `NEXUS_EMBEDDING_BACKEND` and liable to collide with an unrelated
    variable in a shared `.env`. A missed variable produces exactly the §4.2 contradiction
    refusal at boot — noisy rather than silent, but the naming rule is left unstated.'
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: scope-creep
  severity: low
  description: §4.5 defines `embedding_revision` for the *Ollama* backend via the
    model digest from `/api/tags`, and §4.3 builds the reverse migration (`nexus reembed
    run --column embedding --model nomic-embed-text --all-tenants`) as a remedy path.
    Neither is needed for the flip this SPEC exists to enable — both serve the retired
    generation and a rollback that §2 already scopes as 'the blue-green window and
    the rollback path stay' (i.e. unchanged). The Ollama digest in particular is checkpoint
    provenance for a backend the cutover retires, sitting against the 'not per-row
    embedding provenance' and 'not observability infrastructure' non-goals; the justification
    given ('so the field an operator reads after a rollback has a defined meaning')
    would be satisfied by documenting the field as sidecar-only.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-04T18:20:03Z'
---

