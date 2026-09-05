---
target: SPEC-arbiter-status-is-read-only
critiqued_hash: sha256:e10860594507c6221d113211d26e92d102668b6c73ae52be5bcdaad4b0fc3cd2
critiqued_at: '2026-09-05T10:02:14Z'
issues:
- issue_id: I-001
  category: unverifiable-claim
  severity: high
  description: §2.1 states the central harm as "the moment one artifact drifts, every
    subsequent edit anywhere in the repo rewrites that file." By the doc's own §2.1
    description the write fires only on an *approved/accepted* artifact with a bad
    stamp; once demoted to `in_review` the artifact no longer matches that branch,
    so the rewrite happens at most once per drift event, not on every subsequent edit.
    The motivating cost is overstated by an unbounded factor and no measurement is
    offered.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: missing-invariant
  severity: high
  description: '§3.2 makes `index()` group on report status to stop a stale-stamped
    SPEC showing under 🟢 승인, but §3.1 leaves the ADR branch unchanged (report `status`
    stays `approved`, only `tampered: True`). After the change a tampered *ADR* is
    grouped under 승인 in the index — precisely the "silent regression in exactly the
    surface a reviewer looks at" that §3.2 exists to prevent. No invariant is stated
    for how `tampered` affects grouping, and §5 test 2 pins only the SPEC case.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: missing-invariant
  severity: medium
  description: No migration rule for artifacts already demoted on disk by the current
    behaviour. Once the write is removed, any SPEC previously reset to `in_review`
    by `status()` stays `in_review` in its frontmatter permanently, with no path back
    to `approved` and no way to distinguish it from a genuinely critiqued SPEC. The
    doc claims the tree has 0 mismatches today but never asserts 0 past demotions,
    and §5 adds no test or check for pre-existing demoted files.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: undefined
  severity: medium
  description: '§2.3 argues `needs_review: True` in the report is "the honest name
    for the same fact," and §3.1 makes it the sole carrier of the drift signal, but
    the doc never names a consumer. All four callers enumerated in §2.1 are described
    as reading `status` (§3.3 explicitly: `check_gate` reads `entry.get("status")`),
    and §3.2 makes `index()` group on report `status`. `needs_review` is therefore
    unread data; what any caller must do with it is undefined.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: unverifiable-claim
  severity: medium
  description: §2.3 claims writing `in_review` "says something that is not true" because
    there is no open critique — yet §3.1 keeps emitting exactly that value as the
    computed status in the report, and §3.3 makes the gate depend on it. The semantic
    objection, if sound, applies equally to the retained report value; the doc gives
    no argument for why the same claim is dishonest on disk but honest in the report.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: risky-assumption
  severity: medium
  description: §2.2 concludes "the asymmetry appears to be incidental" from the fact
    that neither `adr/README.md` nor ADR-0003 explains the SPEC/ADR difference. Absence
    of documentation is treated as evidence of accident, and this inference is the
    load-bearing premise for choosing the ADR branch as the target behaviour. SPECs
    are mutable working documents and ADRs are immutable records — a difference that
    could well justify the asymmetry — and no author, commit, or review record is
    consulted.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: risky-assumption
  severity: medium
  description: '§3.4 accepts a permanent regression (a stale artifact keeps displaying
    `status: approved` to any reader who does not run Arbiter) on the grounds that
    "`governance (ledger integrity)` checks it on every push." No workflow file, job
    name, or trigger configuration is cited, and §2.4 establishes that `ledger_integrity.py`''s
    coverage is itself selection-dependent. The mitigation for the sole accepted loss
    rests on an uncited CI property.'
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: adr-contradiction
  severity: medium
  description: §4 asserts that adding a status value for "approved but the stamp went
    stale" "is a lifecycle change under ADR-0003 and would need its own record." ADR-0003
    defines a two-tier stream/canonical lifecycle and explicitly lists what it does
    not decide; it never defines or governs the arbiter status vocabulary (`in_review`/`approved`/`accepted`)
    — that vocabulary is cited in §2.3 to `adr/README.md:68` and `specs/README.md`.
    The non-goal invokes authority ADR-0003 does not hold.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: adr-contradiction
  severity: medium
  description: ADR-0003 is status **Proposed**, self-describes as reversible, and
    ships zero code, yet §4 treats it as a binding constraint that blocks a vocabulary
    change. Deriving a hard non-goal from a proposed, unaccepted record is a governance
    inversion the doc does not acknowledge.
  status: rejected
  disposition_reason: '사실이 틀렸다. ADR-0003 의 frontmatter 는 status: accepted 다. 비평은 얼어붙은
    본문 텍스트를 읽었는데, adr/README.md 가 ''정본은 ledger 의 frontmatter 이고 accepted 본문은 얼어 있어
    대부분 여전히 Proposed 라고 적혀 있다''고 명시한다. proposed 라는 전제가 성립하지 않으므로 ''제안 단계 기록에서 강한 비목표를
    끌어냈다''는 파생 지적도 성립하지 않는다. ADR-0003 의 권위를 과잉 원용했다는 별개 지적은 I-008 에서 accepted 로 처리했다.'
- issue_id: I-010
  category: adr-contradiction
  severity: medium
  description: ADR-0003's canonical tier is defined by "approval gate, `content_hash`,
    vouched via `ken`," with the vouch binding to `content_hash` and going stale when
    the artifact changes — the mechanism that keeps a canonical artifact's approval
    honest. §3.4 deliberately allows a canonical artifact to keep asserting `approved`
    in its own frontmatter after its body has diverged from its stamp. The doc does
    not reconcile this with the hash-bound approval the canonical tier assumes, nor
    state whether any `ken`-side staleness signal compensates.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: unverifiable-claim
  severity: medium
  description: '§6 asserts "Searched: the only frontmatter-status reader outside the
    package is `scripts/ledger_integrity.py`" with no search method, pattern, or scope
    given, and the risk is closed on that basis. The claim is also unenforced going
    forward — §5 adds no guard test preventing a new external reader from assuming
    self-correction, unlike the precedent set by `SPEC-nexus-retrieval-backstop-detector`
    §5, which the doc itself cites approvingly for pinning such a property.'
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: unverifiable-claim
  severity: low
  description: 'Artifact counts are given three different ways and none is sourced:
    "64 artifacts as this is written" (§2.1), "42 of 60 listed" (§2.4), "4 of 53 SPECs"
    (§6). They may be reconcilable (total / stamped / SPEC-only) but the doc never
    says which denominator is which, so the §2.1 scan-cost argument and the §2.4 coverage-gap
    argument cannot be checked against each other.'
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: untestable-requirement
  severity: low
  description: §6 disposes of the "demotion is load-bearing for an undocumented human
    workflow" risk by stating "this SPEC's review is where it should surface." That
    defers the only check on the risk to reviewer recall, with no search, no logged
    usage of `arbiter status`, and no acceptance criterion — nothing in §5 can fail
    if the assumption is wrong.
  status: deferred
  disposition_reason: 지금 확인할 자료가 없다. 'arbiter status 에 의존하는 사람 워크플로가 있는가' 를 답하려면 그
    명령의 실사용 기록이 있어야 하는데, 이 리포는 호출을 남기지 않는다. 리뷰어 기억으로 닫는 것이 부정확하다는 지적 자체는 맞으므로 반박하지
    않고, 근거가 생길 때까지 미룬다. §6 에 그 이유를 적어 두었다.
- issue_id: I-014
  category: scope-creep
  severity: low
  description: The Goal is scoped to "This SPEC removes the write. `status()` reports;
    nothing else," but §3.2 additionally changes `index()`'s grouping semantics from
    disk state to report state — altering a reviewer-facing governance surface for
    all artifact types, not only drifted SPECs. The change may be necessary, but it
    is a second behavioural change presented as a consequence rather than declared
    in the Goal.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-09-05T10:31:06Z'
---

