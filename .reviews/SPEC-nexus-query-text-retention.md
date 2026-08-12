---
target: SPEC-nexus-query-text-retention
critiqued_hash: sha256:a7ac71862fe4b898b8d5a5c3269c4d1a5371efa17b2219825961118df8f1263a
critiqued_at: '2026-08-12T05:35:35Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: '§3.1: `query_sha256` is the sole PRIMARY KEY while `tenant` is an
    ordinary NOT NULL column. If the hash is computed over query text alone (as it
    must be, to match the existing `search_log` hash), the same question asked in
    two tenants collides: only the first insert survives, the row is permanently attributed
    to whichever tenant asked first, and `seen_count`/`last_seen` silently aggregate
    across tenant boundaries. Worse, a tenant with NO `query_retention` row will bump
    `last_seen`/`seen_count` on a row retained for a different tenant — i.e. a deployment
    that opted out still contributes to a retained record, contradicting §3.2 ("A
    tenant with no row retains nothing") and §2 ("Not on by default, ever"). The key
    must be (tenant, query_sha256), or the hash must be tenant-salted, and the writer
    must be defined to no-op entirely for non-retaining tenants.'
  status: accepted
  disposition_reason: '§3.1 을 다시 설계했다: 키가 (tenant, retention_key) 이고 retention_key
    = sha256(tenant‖text) 라 테넌트 간 충돌이 불가능하다. 옵트인하지 않은 테넌트에서 writer 가 no-op 임을 행동으로
    명시했다(삽입뿐 아니라 기존 행 갱신도 안 한다).'
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: '§3.1 claims "No principal column ... Storing who asked turns a question
    log into a person log" — but the design''s whole point is that `search_query_text`
    joins to `search_log` on `query_sha256`. If `search_log` (or any adjacent table:
    rate-limit records, a2a_audit, request logs) carries a principal or any per-user
    identifier alongside the same hash, then hash+text on one side and hash+principal
    on the other reconstruct exactly the person log the SPEC says it prevents — via
    the same join §3.1 endorses. The SPEC states no invariant that no other table
    associates `query_sha256` with a principal, and §5''s test only asserts over this
    table''s own columns, which cannot catch the join. Either state and test the cross-table
    invariant, or drop the claim that omitting the column prevents a person log.'
  status: accepted
  disposition_reason: '실측으로 사실 확인: a2a_audit 이 principal 과 query_sha256 을 같은 행에 갖는다.
    문구가 아니라 키를 바꿨다 — 소금 친 retention_key 는 어디에도 저장되지 않은 값이라 조인할 대상이 없다. §5 에 information_schema
    를 훑는 교차테이블 불변식 검사를 추가했다(이 테이블만 보는 검사로는 못 잡는 결함이었다).'
- issue_id: I-003
  category: undefined
  severity: high
  description: '§3.3: `retain_days` is enforced against an unspecified column, and
    both candidates break the promise. Against `last_seen`, a recurring question is
    retained indefinitely — expiry never fires for exactly the questions most likely
    to be sensitive and most likely to be exported. Against `first_seen`, a still-active
    question is deleted and immediately re-created on the next search with a fresh
    `first_seen`, so the retention window resets and again never expires. §3.1''s
    dedup design makes this unavoidable, and no test in §5 pins which column governs
    ("Purge deletes past `retain_days`" is ambiguous), nor does §3.3 say which timestamp
    `/status`''s "oldest retained row" reads.'
  status: accepted
  disposition_reason: §3.3 을 first_seen 기준으로 못 박았다. 다시 물으면 새 창이 열린다는 점은 약속하지 않는다고
    명시했다 — 툼스톤 대안은 '물었던 질문의 영구 기록' 이라 보호하려는 것보다 나쁘다. /status 가 읽는 것도 first_seen 으로
    지정했다.
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: Nothing in §3 defines what happens to already-stored text when retention
    is revoked or narrowed. Purge is described as operating per tenant against `retain_days`,
    which lives in `query_retention` — so deleting a tenant's `query_retention` row
    (the natural way to turn retention off, per §3.2's "A tenant with no row retains
    nothing") orphans its existing `search_query_text` rows with no `retain_days`
    to evaluate against, and they are retained forever. Likewise, lowering `retain_days`
    mid-flight and disabling retention entirely have no specified effect on existing
    rows, and §6's acceptance only covers a tenant that was never switched on. Revocation
    is the operation a consent-based control most needs to define.
  status: accepted
  disposition_reason: '§3.4 신설: disable 이 텍스트와 retention 행을 한 트랜잭션에서 함께 지운다. purge
    는 고아 행(테넌트에 retention 행이 없는 텍스트)을 나이와 무관하게 삭제한다. retain_days 축소는 다음 purge 에 반영되고
    그 지연은 /status 로 보인다.'
- issue_id: I-005
  category: adr-contradiction
  severity: high
  description: 'ADR-0009''s Consequences create a live revisit obligation: "If a real-corpus
    set (Pack B, or any labelled set over khala''s own corpus) is built and its vector-leg
    Recall@10 comparison under the same pre-registered rule ... does not favour KURE-v1
    over the incumbent, this record is re-opened," owner LivingLikeKrillin, no expiry.
    Acceptance 3 of this SPEC builds precisely such a set (labels over khala''s own
    corpus, from real user queries) and says nothing about the obligation — neither
    that this set is Pack B, nor that it is not, nor who runs the KURE-vs-incumbent
    comparison it triggers. The SPEC creates the trigger condition for an open ADR
    obligation while remaining silent on it.'
  status: accepted
  disposition_reason: §3.6 신설 + Acceptance 4. 이 SPEC 이 의무를 해소하지 않는다는 것과, 방아쇠를 조용히
    당기지 않는다는 것을 명시했다. 사전등록 규칙·소유자·미달 시 '열린 상태 유지' 를 그대로 옮겨 적었다.
- issue_id: I-006
  category: missing-invariant
  severity: medium
  description: 'Acceptance 3 and U3 add a new `provenance: from_user_query` label
    class to the label gate, but state none of the discipline ADR-0009 records as
    load-bearing for that instrument: labels carrying `pooled_over` so a configuration
    absent from the pool cannot be scored, blind adjudication with a recorded seed,
    an anonymised pool dump committed before adjudication, and a verdict rule fixed
    before any number is seen. A label set assembled from exported user questions
    inherits none of these by default, so labels that pass the gate can silently be
    unpoolable — which is the failure ADR-0009 spent a section guarding against.'
  status: accepted
  disposition_reason: 부분 수용. Acceptance 3 에 '다른 라벨과 같은 corpus 결속 규칙으로 서명한다'(answer-quality-ruler
    §3.3)를 명시했다. 다만 ADR-0009 의 풀링 기구 자체를 여기서 다시 규정하지는 않는다 — 그 계측은 비교를 실제로 돌릴 때 §3.6
    가 지목한 소유자의 몫이고, 여기서 베끼면 두 곳에 규칙이 생긴다.
- issue_id: I-007
  category: adr-contradiction
  severity: medium
  description: '§3.4 places all derived eval labels in `tests/eval/local/` — gitignored,
    because the repo is public. ADR-0009''s pooling discipline depends on artifacts
    being *committed* before adjudication (`pool-blind.json`, `pool-rev2-adjudication.json`)
    precisely so a verdict cannot be tuned after the fact, and Acceptance 3 claims
    the new provenance is "distinguishable forever ... so the ceiling can be measured,
    not argued about." Labels that exist only on one operator''s disk, outside version
    control, cannot support either claim: they are neither reviewable nor reproducible,
    and "forever" is unverifiable for an untracked file. The SPEC needs a story for
    how a public repo carries auditable-but-non-disclosing label artifacts (hashes,
    redacted stubs, a private tracked location), not just an exclusion.'
  status: rejected
  disposition_reason: 되돌릴 수 없는 선행 제약이다. 리포가 public 이고 질의는 다른 조직의 내용이라, 라벨을 커밋하지 않는
    것은 SPEC-nexus-korean-retrieval-eval §4.1 이 이미 내린 처분이다. 보존 SPEC 이 그 결정을 뒤집을 자리가
    아니다. §3.5 에서 그 한계를 상속한다고 명시했다 — 숨기지 않되 여기서 고치지도 않는다.
- issue_id: I-008
  category: risky-assumption
  severity: medium
  description: §4 names expiry as one of three mitigations for the acknowledged case
    where a user pastes a secret into the search box — but §3.3 provides only a manual
    `nexus query-text purge` command plus a `/status` number. Nothing schedules or
    enforces it, and §6 does not require a single purge to have run. The index-coverage
    lesson cited in §3.3 supports surfacing as a fix for *measurement* invisibility;
    it does not make an unscheduled human-run command an adequate enforcement mechanism
    for a retention limit that was promised to the people asking the questions via
    `notice_shown`. As written, a deployment can satisfy every acceptance criterion
    while retaining every question indefinitely.
  status: accepted
  disposition_reason: '한계로 수용해 §4 에 적었다: 만료는 수동 purge 이고, 안 돌리는 운영자는 무기한 보존한다. /status
    가 그것을 보이게 할 뿐 불가능하게 만들지 않는다. 스케줄러는 nexus 에 없어서 신설은 범위 밖 — 없는 기계를 SPEC 에 적으면 지켜지지
    않는 약속이 된다.'
- issue_id: I-009
  category: untestable-requirement
  severity: medium
  description: §5's last test — "No API response body contains `query_text` — asserted
    over the OpenAPI schema, not per endpoint, so a new endpoint cannot leak it by
    being new" — is only as strong as response-model coverage. Any endpoint returning
    an untyped dict, `Any`, a passthrough of a DB row, a streaming/SSE body, or an
    error payload is invisible to a schema scan, so the stated guarantee ("a new endpoint
    cannot leak it by being new") does not follow from the test. The SPEC needs the
    supporting invariant — every route declares a concrete response model, itself
    enforced — or the claim must be weakened to what the assertion actually covers.
  status: accepted
  disposition_reason: 부분 수용. 생성된 OpenAPI 스키마를 문자열로 훑는 것으로 구체화했다. 응답 모델이 없는 엔드포인트가
    남는 구멍은 실재하며, 그 한계까지가 이 검사가 주는 것이다 — 더 강하게 적으면 검사보다 문장이 세진다.
- issue_id: I-010
  category: risky-assumption
  severity: medium
  description: §1 treats real user questions as straightforwardly lowering the ceiling
    on the 40/40 number, but the two sets are not comparable quantities. The current
    45 labels are 40 answerable / 5 unanswerable by construction; a pilot-traffic
    set will have an unknown and probably much larger unanswerable fraction, so Recall@10
    over its "answerable" subset is a different denominator and cannot be read against
    `revision 6`'s 40/40. ADR-0009 explicitly records that abstention and false-positive
    behaviour "went to production unmeasured" — the very axis real questions will
    load most heavily. The SPEC should state how answerability is adjudicated for
    user-authored queries and what, if anything, the new number may be compared against.
  status: accepted
  disposition_reason: '§4 에 항목을 추가했다: 실사용 질문 집합과 저술 집합은 다른 모집단이라 한 칸에 나란히 적으면 안 되고,
    provenance 로 갈라 따로 보고한다.'
- issue_id: I-011
  category: missing-invariant
  severity: medium
  description: The write path's failure and latency semantics are undefined. §3.1
    requires a read-modify-write upsert (increment `seen_count`, advance `last_seen`)
    on the hot search path, yet the SPEC never states that a retention write failure
    must not fail or degrade the search, nor whether the write is in-transaction with
    `search_log`. Since §3.1's central argument is that "deleting the text must not
    delete the measurement," the converse invariant — retention must never break the
    query or the hash-only log — deserves to be stated and tested, not inferred.
  status: accepted
  disposition_reason: '§3.5 에 명시: 보존 쓰기는 best-effort 이고 답변 경로 밖이며, 실패해도 검색을 실패시키거나
    지연시키지 않는다. §5 에 삽입을 강제로 실패시켜도 검색이 200 인지 거는 검사를 넣었다.'
- issue_id: I-012
  category: undefined
  severity: medium
  description: 'The absence of a principal column (§3.1) makes per-person erasure
    structurally impossible: once a question is stored, there is no way to honour
    "delete the questions I asked" short of purging the whole tenant. §2 and §4 discuss
    consent, scope, expiry and access but never acknowledge this trade-off, and §3.2''s
    consent story (`notice_shown` pointing at a Slack post) is exactly the setting
    where an individual is likely to ask. Either state that only tenant-wide deletion
    is offered — and that the notice must say so — or define the deletion path.'
  status: accepted
  disposition_reason: §3.4 에 '개인 단위 삭제는 구조적으로 불가능하다' 를 비용으로 적었다. 유일한 구제는 테넌트 단위 purge
    이고, 그 사실은 notice_shown 이 가리키는 고지에 들어가야 한다 — 나중에 물어본 사람이 발견하게 두지 않는다.
- issue_id: I-013
  category: undefined
  severity: medium
  description: ADR-0009's open-items table assigns "A mechanism that detects backstop
    events, or a declaration made after the fact" to "**The next SPEC that links ADR-0008**
    — a detectable event (`linked_adrs`), deliberately not 'the next backstop event',
    since that is the thing nothing can detect." This SPEC links ADR-0009, the successor
    that amends ADR-0008, and takes up neither that item nor the adjacent "usable
    predicate for 'materially expand'" item. Whether linking the amendment discharges,
    defers, or evades a trigger keyed on linking the amended record is undefined —
    and since the trigger was chosen for mechanical detectability, an undefined answer
    defeats the mechanism.
  status: rejected
  disposition_reason: 발화하지 않는다. ADR-0009 open-items 의 방아쇠는 'ADR-0008 을 링크하는 다음 SPEC'
    이고(그 ADR 이 일부러 탐지 가능한 사건으로 정의했다), 이 SPEC 은 ADR-0002·ADR-0009 만 링크한다. 항목을 트리거하려고
    무관한 ADR-0008 을 링크하면 그 탐지기 자체를 망가뜨린다.
- issue_id: I-014
  category: undefined
  severity: low
  description: '§5''s second test requires that a row with empty `notice_shown` "retains
    nothing, and the refusal is visible, not silent," but "visible" has no referent:
    log line, exception, `/status` field, CLI warning, or a failed search? §3.2 says
    only that "the writer refuses." Without naming the observable, the test cannot
    be written to fail for the right reason, and the same ambiguity applies to whether
    a refused retention write affects the user''s search at all.'
  status: accepted
  disposition_reason: §3.2 에서 '보인다' 를 /status 의 query_retention_refused 카운터로 지정했다.
    로그 한 줄은 아무도 안 본다 — index-completeness 에서 배운 것과 같은 실패다.
- issue_id: I-015
  category: unverifiable-claim
  severity: low
  description: §1 anchors the entire motivation on "`revision 6` scored **40/40**
    on one run with the five controls refusing 5 of 5" — a single run, with no repeat
    measurement and no stated run-to-run variance for the ruler itself. The doc then
    treats that number as a firm ceiling to be lowered. A one-run figure from a non-deterministic
    grader cannot carry that weight without an instrument-noise floor, and the SPEC
    does not claim one was measured.
  status: accepted
  disposition_reason: '§1 을 3런 실측으로 교체했다: 39/40 · 39/40 · 40/40, 실패 질의가 서로 달라 3런 전부
    실패한 질의는 없다. 단일 런 인용은 이 SPEC 이 경계하는 종류의 근거였다.'
- issue_id: I-016
  category: unverifiable-claim
  severity: low
  description: Acceptance 2 ("switched on with `notice_shown` pointing at a message
    the team actually received, and that message is quoted in the PR") and Acceptance
    1 ("verified against a live run, not only in tests") have no defined verification
    procedure or artifact format. §4 already concedes the first is unenforceable ("a
    string can be filled in with anything"); as acceptance criteria they are reviewer
    judgement calls, and §3.2 gives `notice_shown` no format, so nothing distinguishes
    a real reference from a plausible one.
  status: accepted
  disposition_reason: 부분 수용. Acceptance 1 은 '라이브 실행으로 확인' 이 무엇을 보는지 적었고, Acceptance
    2 의 검증은 고지 원문을 PR 본문에 인용하는 것이다. 거버넌스 주장의 검증이 결국 사람의 읽기라는 점은 §4 첫 항목에서 이미 한계로 선언했다
    — 자동 검증이 있는 척하지 않는다.
- issue_id: I-017
  category: undefined
  severity: low
  description: §2 states "Nothing reads this table at request time," yet §3.1's deduplication
    requires an upsert — a read-modify-write against `search_query_text` on every
    search — so the literal statement is false as written. The intended invariant
    is presumably that nothing in the *response path* derives from the table; that
    stronger, checkable form is never stated, and §5 contains no test for it.
  status: accepted
  disposition_reason: '§2 문구를 고쳤다: ''답변 경로의 어떤 읽기도 답을 바꾸지 않는다''. upsert 가 읽는다는 사실을
    괄호로 명시했다.'
approved_by: LivingLikeKrillin
approved_at: '2026-08-12T06:41:49Z'
---

