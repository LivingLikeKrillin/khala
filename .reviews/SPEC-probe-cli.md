---
target: SPEC-probe-cli
critiqued_hash: sha256:7b89d56ad6134539a46fa64ad35284ec96f805ea88a9466a7e697c1a5f35972c
critiqued_at: '2026-07-10T16:04:07Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: 'The SPEC claims the code rename ''has since completed (verified on
    the tree 2026-07-11): the probe/ directory now holds khala.probe — the cosmic-ray
    runner ... and the review analyzer lives in observer/; there is no top-level mutqa/''.
    This directly contradicts ADR-0005 §3, which states the code migration has NOT
    landed: ''The probe/ directory is Observer (new name), despite the path. There
    is no probe/ directory for the new Probe yet — it remains mutqa/.'' ADR-0005 §5
    and both out-of-scope sections explicitly defer directory renames. Either the
    SPEC''s factual premise is wrong or the ADRs are stale, but as written the SPEC
    contradicts the canonical mapping layer it claims to comply with.'
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: unverifiable-claim
  severity: medium
  description: '''The code rename has since completed (verified on the tree 2026-07-11)''
    is a point-in-time verification assertion with no reproducible evidence in the
    SPEC. It is precisely the kind of ''verified'' claim the SPEC elsewhere (§4) says
    it wants to avoid (''not as an unfalsifiable verified claim''), yet the entire
    naming/no-contradiction argument rests on this unfalsifiable statement.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: risky-assumption
  severity: medium
  description: §5.1 step 5 assumes pytest's collect-only trailing summary line is
    parseable enough to derive a coarse count, with a plain fallback string on failure.
    The claim 'nothing downstream depends on an exact count' is asserted but the suite_summary
    is fed into the Critic prompt as {suite_summary}; degraded/garbage summary could
    silently mislead Critic judgment, and there is no test asserting the fallback
    path produces the failure string.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: untestable-requirement
  severity: medium
  description: Acceptance §8.2/§8.3 and error handling require behavior 'from a consumer
    repo with cosmic-ray installed' — but §7 explicitly states the CLI is tested only
    with an injected runner and no cosmic-ray. The acceptance criteria that depend
    on real cosmic-ray execution (a live survey producing real survivors, the missing-binary
    FileNotFound message path) have no corresponding automated test and are only manually
    observable, making them effectively untestable within the stated test suite.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: missing-invariant
  severity: medium
  description: §5.3 step 3 says absorb 'records the new judgments immutably; a human-set
    waived_until is preserved, not overwritten', but no test in §7 asserts the waived_until
    preservation invariant. The immutability/no-overwrite guarantee is stated as a
    property of absorb yet is never exercised, so a regression that clobbers waivers
    would not be caught.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: low
  description: The verdict-domain enforcement is stated to live 'in the CLI' (§4 Verdict
    domain) because Verdict is a bare dataclass and absorb validates the domain (§5.3.1),
    but §4 also says 'absorb validates this domain'. It is ambiguous whether domain
    validation lives in the absorb() harness function or in cli.py; the SPEC claims
    the harness is not touched (§3 'does not touch their logic'), creating an unspecified
    boundary for where the invariant is actually enforced.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: undefined
  severity: low
  description: The 'biting' concept and biting_count that headlines the report is
    central to acceptance (§8.3) but never defined in the SPEC beyond referencing
    biting(survivors, ledger, today). What makes a survivor 'biting' (e.g. real-gap
    not waived, past some threshold) is left entirely to the un-described harness
    function, so the acceptance headline is asserted against an undefined predicate.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: risky-assumption
  severity: low
  description: §5.3 step 5 rebuilds Survivor.key from module:lineno:operator after
    round-trip, assuming those three fields are always present and uniquely reconstruct
    the key. If a round-tripped survey JSON is missing a field or has colon-containing
    operator/module values, key reconstruction could silently mismatch the verdict
    keys, but no test covers malformed/partial survey files (only malformed verdicts
    files are tested).
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: scope-creep
  severity: low
  description: The SPEC adds an unjudged-fresh-survivor warning path (I-005, §5.3.2)
    with its own comparison of survey fresh set vs verdict keys and a dedicated test.
    While useful, this is judgment-adjacent reconciliation logic beyond the stated
    minimal goal of 'making the advisory loop runnable' by wrapping existing harness
    functions; it introduces new CLI-only comparison behavior not present in the SKILL.md
    step-4 flow the SPEC claims to preserve unchanged.
  status: rejected
  disposition_reason: 이 경고는 내가 round-1 I-005(부분 verdicts 파일이 절반 판정을 조용히 영속)를 고치려 추가한
    것이다. CLI 표면의 읽기 전용 집합 비교(survey.fresh vs verdict keys)일 뿐 하네스 로직을 건드리지 않는다. 두
    라운드의 지적이 상충하는데, 조용한 데이터 손실이 몇 줄의 set-diff보다 나쁜 실패다 — 유지한다. SKILL step-4 흐름도 바꾸지
    않는다(판정 자체는 여전히 CLI 밖).
approved_by: LivingLikeKrillin
approved_at: '2026-07-10T16:07:30Z'
---

