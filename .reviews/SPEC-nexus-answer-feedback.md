---
target: SPEC-nexus-answer-feedback
critiqued_hash: sha256:f0e0698e94533b0cd2aadfdf41fb5a0e79e5b476472d3829110b5ab25bea2d1e
critiqued_at: '2026-08-14T11:28:32Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: '§0 declares a new gate solely on the director''s word, but ADR-0002
    does not permit a bare declaration: it restates demand-pull as "gate each debt-servicing
    feature on ''is this debt actually accumulating? show the signal''", enumerates
    exactly three cognitive-debt directions (ⓐ/ⓑ/ⓒ), and for ⓐ (a human-sourced per-artifact
    judgment signal — the closest match to a 👍/👎 verdict on an answer) requires "an
    observed, logged rate … crosses a set threshold in a rolling window" plus "construction
    still waits for gate ⓐ to fire against the observed threshold". The SPEC never
    maps its direction onto ⓐ/ⓑ/ⓒ, names no threshold, and asserts without support
    that applying the discipline to an unlisted direction "게이트 체계를 넓히는 일은 아니다". §1.1''s
    evidence (evaluation-set ceilings) is not the observation ADR-0002 specifies.'
  status: rejected
  disposition_reason: 이전 라운드에서 이미 본문에 반영됨 — 재지적.
- issue_id: I-002
  category: untestable-requirement
  severity: high
  description: 'I11 ("운영자 DM 에 본문이 없다", test: assert the DM payload contains only
    permalink + reason code) asserts a property of a path that §3.7 deleted — there
    is no DM, so the check is vacuous and can never fail. The same removed feature
    survives in two more places: §2''s non-goal text ("§3.7 의 운영자 DM 은 건당 라우팅이지…")
    and §3.5''s 안 B definition itself ("👎 가 오면 운영자에게만 DM 으로 퍼머링크를 보낸다"), which is
    the adopted option''s normative description. A reader implementing 안 B as written
    builds the DM path §3.7 forbids.'
  status: rejected
  disposition_reason: 이전 라운드에서 이미 본문에 반영됨 — 재지적.
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: 'I12 requires pointer columns to be NULLed at 90 days, but §6 ("유닛")
    states the opposite and ships no unit for it: "행 만료 유닛도 없다 — 저장하는 것이 수와 사유 코드뿐이라
    만료시킬 텍스트가 없다(I7)". That sentence is verbatim the 안 A-era rationale I12 itself
    calls "지금은 거짓". No unit owns the deletion job, no scheduling mechanism is named,
    and I12''s test (91일 된 행) cannot pass with nothing implementing it — so the only
    mitigation for the 질문자 추정 경로 admitted in §3.4/§7 has no home.'
  status: rejected
  disposition_reason: 이전 라운드에서 이미 본문에 반영됨 — 재지적.
- issue_id: I-004
  category: undefined
  severity: high
  description: I10 ("block_actions 페이로드의 (channel, message.ts) 가 answer_offered 의
    값과 다르면 거절") is stated unconditionally, but §3.1.1 (3)'s reason submission arrives
    from an *ephemeral* message whose `message.ts` is necessarily different from the
    answer message's `message_ts`. The SPEC never scopes I10 to the 👍/👎 click. Applied
    as written, every reason click is rejected and 사유 — declared "이 기능의 유일한 산출물" —
    is never recorded; scoped silently, the invariant's test passes while the reason
    path has no binding check at all.
  status: rejected
  disposition_reason: 이전 라운드에서 이미 본문에 반영됨 — 재지적.
- issue_id: I-005
  category: risky-assumption
  severity: medium
  description: 'I10''s stated purpose ("이것이 없으면 answer_key 는 30일짜리 무기명 자격증명이다") is
    defeated by §3.3''s orphan rule: a vote whose `answer_key` has no offer row is
    accepted, a `synthesized` row is fabricated, and the SPEC itself notes "orphan
    경로는 I10 도 함께 우회한다". Binding is therefore bypassed by *omitting* a valid key rather
    than stealing one, and any caller can insert unbounded rows with random keys.
    The trust-boundary argument ("슬랙이 인증한 인터랙션") justifies accepting genuine votes
    but does not restore the reuse protection I10 claims.'
  status: rejected
  disposition_reason: 이전 라운드에서 이미 본문에 반영됨 — 재지적.
- issue_id: I-006
  category: undefined
  severity: medium
  description: '§3.3 says "synthesized 행에 딸린 투표는 유효표로 세되" and defends it at length
    as a deliberate exception, but every aggregation the document defines excludes
    them: §5.2/§5.3''s 분모 is `WHERE NOT synthesized` and §5.3''s 분자 query joins `answer_offered`
    with `NOT o.synthesized` for the explicit reason that 분자와 분모가 같은 모집단이어야 한다. §5.3
    also states these two queries are "관측 수단 전부". No defined counter treats orphan
    votes as valid, so "유효표" has no operational meaning.'
  status: rejected
  disposition_reason: 이전 라운드에서 이미 본문에 반영됨 — 재지적.
- issue_id: I-007
  category: scope-creep
  severity: medium
  description: I8 instructs U1 to find the enforced `top_k` clamp and, "못 찾으면 상한을
    먼저 만들고 검사한다" — i.e. add a new cap to the retrieval configuration. That contradicts
    §2's non-goal ("검색·답변 생성을 바꾸지 않는다") and I9, whose golden-kwargs comparison would
    itself break if `top_k` handling changed; it also pushes the unit toward exactly
    the kind of retrieval-stack change ADR-0008 §5 names as a backstop re-read trigger,
    which §0.1 asserts this SPEC does not do.
  status: rejected
  disposition_reason: 이전 라운드에서 이미 본문에 반영됨 — 재지적.
- issue_id: I-008
  category: risky-assumption
  severity: medium
  description: §5.3 rejects the draft's threshold of 3 as "재본 적 없는 숫자" and §2 forbids
    "X 미만이면 …" rules, yet the document installs 제안 30건, 제안 100건, 표 30건, 평가일 90일, 키
    만료 30일, 사유 가드 1시간, 포인터 90일 — none of which is measured or derived. The self-binding
    argument in §5.2 applies with equal force to its own numbers; the same objection
    that killed 3 is unaddressed for 30/100/90.
  status: rejected
  disposition_reason: 이전 라운드에서 이미 본문에 반영됨 — 재지적.
- issue_id: I-009
  category: risky-assumption
  severity: medium
  description: §5.3's timeline ("§5.2 의 투표 문턱 30건은 약 3개월") divides §1.3's estimate
    of 월 10표 (vote *rows*) by a threshold §5.2 explicitly defines as `COUNT(DISTINCT
    answer_key)` —서로 다른 답변 수. The same section warns two paragraphs earlier that counting
    rows instead of distinct answers is wrong because 재클릭이 행을 쌓는다. With repeat votes
    the distinct-answer count is strictly lower, so the 3-month figure is an underestimate
    of unknown size, and 월 10표 itself has no measurement behind it.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: untestable-requirement
  severity: medium
  description: §5.3's first disposition row reasons "제안 30건 미만 ⇒ 파일럿이 안 돈 것이다. 이 기능이
    아니라 파일럿을 본다", then prescribes removing the buttons if the second evaluation date
    is also under 30. The prescribed action does not follow from the stated diagnosis
    — a feature is killed on evidence about a different subject — and the rule cannot
    distinguish "버튼이 안 먹혔다" from "아무도 봇에게 묻지 않았다", which is the very distinction the
    row claims to make.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: untestable-requirement
  severity: medium
  description: §5.1's central operating requirement — "주기적으로(월 1회 권장) nexus feedback
    을 조회한다" — names no owner, no scheduled mechanism, and no check that it happened;
    §3.7 concedes the failure mode ("아무도 조회를 안 하면 자료는 쌓이기만 한다") and cites the index-coverage
    precedent where detection existed and delivery did not, then mitigates with a
    single `nexus status` line whose content is not specified. There is no invariant
    or unit that can fail if the review never occurs, and §3.7 defers the delivery
    mechanism to §5.3's evaluation date — 90 days after the pointers whose expiry
    (I12) makes the review time-critical.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: missing-invariant
  severity: medium
  description: 'The anonymity argument rests on `answer_key` never co-locating with
    identity or query text, but the invariants only cover the schema (I3: the column
    appears in two tables) and the user id in logs (I4). Nothing forbids `answer_key`
    from appearing in application logs, traces, or error reports next to the query
    text or `principal` that the bot already handles in the same request — the exact
    re-linking mechanism I4 was written to close for `slack_user_id`. Given §7''s
    admission that a plaintext→hash→principal path already exists, an unconstrained
    log line reconstitutes the 투표↔질의 link outside the DB.'
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: risky-assumption
  severity: medium
  description: §0.1 reads ADR-0008 §5's list ("a new retrieval channel, a second index
    backend, a tokenizer or embedding-model change, or connector work beyond the existing
    two sources") as an exhaustive checklist and concludes "재독 트리거에 해당하지 않는다". The
    ADR's operative clause is "any work that would materially expand Nexus's retrieval
    stack", with the list following an em dash as illustration. §0 itself enumerates
    six new surfaces including a new inbound interaction path, two new tables, and
    a Slack app setting change; whether that is "material" is a judgment the SPEC
    forecloses by construing examples as a closed set.
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: unverifiable-claim
  severity: medium
  description: §1.2 — the load-bearing existence proof — states "실제 범위는 108건이었고 시스템은
    그 수를 알고 있었다" with no log id, query, thread pointer, or artifact anyone can re-check;
    §1.1's figures (Pack A 34~35 → 38~40, "3런 지속실패 4건 중 시스템 결함 0", "three_sentences
    양팔 0/30") are likewise cited without run references. §0 makes §1.1 rather than
    §1.2 the gate's basis, so the unreproducible numbers are precisely the ones the
    gate declaration rests on.
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: unverifiable-claim
  severity: low
  description: 'The SPEC''s procedural footing is two ADRs that are not yet binding:
    ADR-0002 is "**Proposed** — this ADR records a positioning decision, not an engineering
    commitment", and ADR-0008 is "**In review.** Binding on acceptance." §0 asserts
    "절차의 출처는 ADR-0002 다" and §0.1 draws a normative conclusion from ADR-0008 §5 as
    though both were in force; if either is amended before acceptance, the gate record
    and the backstop analysis both lose their basis.'
  status: accepted
  disposition_reason: null
- issue_id: I-016
  category: undefined
  severity: low
  description: U3 is specified only as "조회 nexus feedback + nexus status 한 줄". The
    command's filters, output fields, default window, tenant handling, and the exact
    content of the status line (which count? offers, votes, unreviewed 👎?) are undefined,
    and no invariant covers U3. Since §5.1 makes this command the sole investigation
    entry point and §3.7 makes the status line the sole delivery mechanism, there
    is no way to test whether U3 satisfies either requirement.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-14T11:30:55Z'
---

