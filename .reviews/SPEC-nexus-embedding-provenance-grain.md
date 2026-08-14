---
target: SPEC-nexus-embedding-provenance-grain
critiqued_hash: sha256:535064c07d0fcb23fae9557856e6e6a28cdebd5a80b1a2d7888c69fd94c35281
critiqued_at: '2026-08-14T13:13:00Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: ADR-0009 §Consequences records that the shipped KURE cutover holds
    the invariant "one generation per column (`embed_health` reports a single `embed_model`
    for the target column)". §1.1–§1.3 of this SPEC prove that exact instrument is
    row-grain and last-writer-wins, i.e. it cannot distinguish per-column generations
    at all. So the SPEC establishes that ADR-0009's central post-flip invariant was
    never checkable and the 167/167 flip was certified by a broken gauge — yet the
    SPEC never states this, does not propose re-verifying the deployment under the
    new grain, and its non-goals ('모델을 바꾸지 않는다') quietly bypass the question.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: No atomicity is required between the vector write (`UPDATE chunks SET
    {col} = ...`) and the new provenance write. If the vector commits and the provenance
    insert fails (or a code path is missed), the result is a vector with no provenance
    row — which I3 defines as '미상' and explicitly excludes from violation counting.
    The designed failure mode of the write path is therefore silence, and I2's test
    ('각 경로를 실행하고 출처 행이 생기는지 본다') only exercises the happy path. Needs a same-transaction
    requirement plus a check that a vector without provenance is itself an error,
    not an unknown.
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: undefined
  severity: high
  description: '§3.3''s backfill is unimplementable as written: `chunk_vector_provenance`
    is keyed on `column_name`, but the migration''s whole premise is that it is unknown
    which column the legacy `embed_model` value describes. The SPEC never says what
    `column_name` the ''미상'' rows carry, nor whether a chunk with both a 768 and a
    1024 vector gets one unknown row or two. Consequently I4 (''마이그레이션 후 미상 행 수 ==
    마이그레이션 전 행 수'') has no determinate meaning — for the measured data (403 chunk
    rows, 346 non-null 1024 vectors, 352 non-null 768 vectors) the two counts cannot
    be equal under any per-(chunk,column) backfill.'
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: '§3.1 option B lists columns `(chunk_rid, column_name, model, written_at)`
    but declares no primary key, no uniqueness, and no `tenant` column. This repeats
    §1.4''s diagnosed bug verbatim — ''`model` 칸은 있지만 키가 아니라서 아무것도 막지 못한다'' — one
    level up: nothing prevents two contradictory provenance rows for the same (chunk,
    column), and I1''s test presumes exactly one row per column. Also, §3.2''s mismatch
    count must join `index_generation_events`, whose grain is (tenant, column_name);
    with no tenant on the provenance table the aggregation grain of ''혼합'' and ''불일치''
    is undefined (the measured data spans `default` and `ko_eval_packa`).'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: missing-invariant
  severity: high
  description: §3.4 changes only the `embed_waivers` PK, but the symptom named in
    §1.4 ('nomic 으로 포기한 청크가 KURE 에서도 포기된 것처럼 보인다') lives in the read path — the coverage/exemption
    check that consumes waivers. Nothing in §3.4 or §4 requires that reader to filter
    by the active model, so after the PK change a nomic-era waiver can still exempt
    a chunk under KURE. I5 only asserts that two rows can coexist, which is a schema
    property, not the behaviour that was wrong.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: risky-assumption
  severity: medium
  description: U3 is rated '낮음 — 소급 추정 없음', but waiver grain determines which chunks
    count as exempt in index-coverage accounting, and that accounting feeds `nexus
    status` output and exit codes. Splitting one waiver row per model can change the
    exempt population in both directions. The SPEC pins search invariance (I6) but
    pins nothing about coverage population or exit-code invariance, which is the surface
    U3 actually moves.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: unverifiable-claim
  severity: medium
  description: 'The decisive justification for option B — ''그리고 B 만이 `written_at`
    을 준다 — 그것이 §3.2 를 가능하게 한다'' — is false on both halves. Option A can carry per-column
    timestamps (`embed_model_768_at`), and §3.2''s replacement definition of ''혼합''
    never uses `written_at`: it counts distinct models per column and compares against
    the latest declaration. The recommendation may still be right for the column-churn
    reason, but the stated deciding evidence does not support it.'
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: untestable-requirement
  severity: medium
  description: '§3.2 introduces a second measure — ''선언과의 불일치'' against the latest
    `index_generation_events` row — and calls it ''실제로 위험한 신호'', but defines no threshold,
    no consumer, no exit-code or alert semantics, and no arm in §5''s control table.
    It is a number with nothing gated on it: precisely the defect ADR-0009 records
    for the post-flip NULL gap (''`nexus reembed status --column embedding` reports
    the count and no gate consumes it'').'
  status: rejected
  disposition_reason: 선언 불일치 수치에 문턱을 달지 않은 것은 의도다. 재본 적 없는 수로 게이트를 만드는 것이 이 리포가 반복한
    실수이고, §3.3 과 같은 이유로 **보이게만** 둔다. 게이트가 필요하면 그때 재본 수로 정한다.
- issue_id: I-009
  category: untestable-requirement
  severity: medium
  description: §5's '판정' arm is vacuous by construction. After the §3.3 backfill,
    every provenance row for `default.embedding_1024` is '미상', so `mixed=False` follows
    from I3 alone and would hold even if per-column provenance were computed completely
    wrongly. No arm tests the claim that actually matters on real data — that the
    230 KURE rows and the 116 mislabelled rows acquire the correct per-column model
    — so the negative control cannot distinguish 'fixed' from 'everything is unknown'.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: adr-contradiction
  severity: medium
  description: §8 acknowledges this SPEC is the trigger ADR-0009 named for the post-flip
    NULL-gap rollback guard ('the next SPEC touching the embedding columns') and then
    leaves it open without a disposition, a new owner, or a replacement trigger. ADR-0009
    chose that trigger precisely because backstop events are undetectable; discharging
    the trigger without closing or re-anchoring the item returns it to the undetectable
    state, which is the failure ADR-0009's own open-items table was built to prevent.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: risky-assumption
  severity: medium
  description: §3.3's '저절로 낫는다' assumes future re-embeds will overwrite every legacy
    row. Nothing in the SPEC triggers or schedules a full re-embed, and a chunk never
    re-embedded stays '미상' indefinitely — so the blind window §7 admits ('코퍼스가 전부
    미상이면 이 감지기는 아무것도 못 잡는다') is unbounded rather than transient. Either a backfill-by-re-embed
    unit or an explicit bound on tolerated '미상' share is missing.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: unverifiable-claim
  severity: medium
  description: 'The entire diagnosis rests on §1.2''s ad-hoc counts against a mutable
    dev DB with no committed query, fixture, or snapshot, so the observation cannot
    be re-run or regression-guarded. Separately, ''768 재임베딩이 나중에 돌면서 라벨을 덮었다'' is
    stated as fact but is inference: no per-column write timestamp exists yet (that
    is what §3.1 is being introduced to add), and §2/§3.3 elsewhere insist the provenance
    of those rows is unknowable.'
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: missing-invariant
  severity: medium
  description: '§1.2''s own numbers contain an unremarked live defect: 403 rows for
    tenant `default` but only 346 with a non-null `embedding_1024`, i.e. 57 chunks
    carry no vector in the currently declared generation and are invisible to the
    vector leg. The SPEC reads its measurement only for the labelling bug and states
    no invariant or check tying provenance/mixed detection to per-column coverage,
    so the new table will report those rows as simply absent rather than as a gap.'
  status: rejected
  disposition_reason: 정책 필터 없는 내 카운트가 오도했다. 필터를 걸고 다시 재니 309/309 로 구멍 0 이다 — 그 57행은
    inactive·격리라 검색이 안 읽는다. 추론은 옳았고 근거 숫자가 틀렸으며, §1.2 에 그 경위를 적었다.
- issue_id: I-014
  category: missing-invariant
  severity: low
  description: 'The interim state has two sources of truth: `embed.py`/`reembed.py`
    keep writing the known-false `chunks.embed_model` while ''혼합'' switches to the
    provenance table. §8 defers deletion until ''읽는 곳을 전부 옮긴 뒤에'' without enumerating
    those readers, and no invariant forbids new reads of `embed_model` or requires
    remaining readers (status output, web surfaces, `embed_health`) to be listed.
    The lie stays queryable with nothing marking it as such.'
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: untestable-requirement
  severity: low
  description: I6 ('검색 무변경') is asserted as '`hybrid_search` 가 받는 인자 값이 같다' — argument
    equality, not behaviour. U1 adds a write per chunk to both embed paths; nothing
    states the required behaviour for ingest latency, or for a provenance-write failure
    mid-ingest. An invariant phrased over call arguments cannot fail for either of
    the ways this change could actually affect the query path.
  status: accepted
  disposition_reason: null
- issue_id: I-016
  category: undefined
  severity: low
  description: The backstop record ships with `ruling`, `declared_by`, `declared_at`
    all '(서명 대기)', and the SPEC itself notes the detector checks field presence rather
    than authenticity. No ordering constraint is stated — nothing says U1 must not
    be implemented or merged before the signature exists. ADR-0009 §3(ii) records
    gate-after-SPEC as a one-time exception with 'Nothing currently prevents recurrence';
    this SPEC is the first opportunity for recurrence and adds no guard.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-14T13:30:28Z'
---

