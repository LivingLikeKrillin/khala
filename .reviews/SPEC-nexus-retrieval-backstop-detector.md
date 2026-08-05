---
target: SPEC-nexus-retrieval-backstop-detector
critiqued_hash: sha256:e4a4a19d34e6f4126a5819f6eb50a5e85b171c01c227850a9e39d143facde1e6
critiqued_at: '2026-08-05T08:58:05Z'
issues:
- issue_id: I-001
  category: unverifiable-claim
  severity: high
  description: 'The `backstop` block asserts `declared_by: LivingLikeKrillin` / `ruling:
    does-not-fire`, and the prose insists "The ruling was made, in conversation on
    2026-08-05". Nothing in the artifact, the ledger, or §4''s job can distinguish
    this from the failure §2 admits occurred the same day, in the same session: "an
    agent wrote `declared_by: LivingLikeKrillin` for a ruling the director had never
    made". §2 further concedes §4 "detects alteration *after* stamping" and would
    not have caught it. So the SPEC''s single load-bearing governance fact rests on
    exactly the mechanism it documents as absent — the reviewer is asked to take the
    author''s word, which is the same posture §1 uses to kill design 2 ("every anchor
    it would hang from is author-controlled").'
  status: accepted
  disposition_reason: 'Correct, and the record now says it in its own voice: the ruling
    was made in conversation and nothing in the artifact proves that; the same session
    produced a forged declared_by that only review caught, and this job would not
    have caught it. The reviewer is told plainly they are taking the author''s word.'
- issue_id: I-002
  category: undefined
  severity: high
  description: '§4 selects artifacts "whose `status` is `approved` or `accepted`"
    but never says where that status is read from — frontmatter, the ledger, or `adr/README.md`.
    §2 declares "This SPEC follows the ledger, which `adr/README.md` defines as authoritative",
    yet §4''s disclosed defect (2) — "flipping `approved` → `draft` is undetectable
    by the hash and silently exempts the file" — is only possible if selection reads
    author-editable frontmatter. The two sections describe different jobs. Concretely:
    ADR-0008''s body reads "In review" while the ledger says `accepted`; a frontmatter-driven
    job may not check ADR-0008 at all, and a ledger-driven job would eliminate defect
    (2) entirely, invalidating a whole paragraph of §4 and the §6 test that a `draft`
    artifact with a mismatched hash must pass.'
  status: accepted
  disposition_reason: 'Section 3 now states that selection reads frontmatter, not
    the ledger, and why: a ledger-driven selector removes bypasses (2) and (3) but
    skips artifacts whose bodies disagree with the ledger, which ADR-0009 records
    for seven of eight ADRs. Two sections previously described two different jobs.'
- issue_id: I-003
  category: missing-invariant
  severity: high
  description: '§4 states that disclosed bypasses (2) status-flip and (3) `id` deletion
    "are why §6 asserts a floor on the number of artifacts actually checked and requires
    every skipped file to be named in the job output" — but neither mitigation actually
    fires. The floor is 30 against a measured population of 39, so nine artifacts
    (23%) can be exempted by status-flip or `id` corruption with the job still green;
    and "named in the output" is not a failure condition, so a skipped file produces
    a passing build plus a log line nobody is required to read. Failure scenario:
    an author edits an approved SPEC''s body, flips its frontmatter `status` to `draft`
    (or deletes its `id`) in the same commit — count drops 39→38, above the floor,
    job passes green, and the alteration the job exists to catch is invisible.'
  status: accepted
  disposition_reason: The floor of 30 against 39 left nine artifacts exemptible with
    the build green, and 'named in the output' was never a failure condition. Replaced
    by a committed manifest of artifact ids; a listed id that is absent, unparseable
    or no longer selected fails the job.
- issue_id: I-004
  category: unverifiable-claim
  severity: high
  description: 'The Backstop record claims "What approval adds is ... **tamper-evidence**:
    the stamp fixes this body, so the record cannot be altered afterwards without
    §4''s job seeing it." §4 refutes this: the stamped `content_hash` lives in frontmatter,
    which "the hash does not cover", and §4''s own limit (1) concedes "Someone editing
    frontmatter and body together produces a consistent-looking approved artifact
    with an unbroken hash." Recomputing and re-writing the stamp alongside the body
    edit is a single-commit operation with no detector. The job therefore detects
    careless edits (the ADR-0009 §Context case) but not tampering, so the tamper-evidence
    the whole record''s credibility is staked on does not exist as stated.'
  status: accepted
  disposition_reason: The stamped content_hash is itself frontmatter, so a body edit
    with a recomputed stamp is one commit with no detector. The tamper-evidence claim
    is withdrawn; the job's claim is narrowed to what it does detect - an edit that
    did not update the stamp.
- issue_id: I-005
  category: adr-contradiction
  severity: high
  description: §5 declares ADR-0009's first open item "closed as *answered*", but
    ADR-0009 — accepted, content-hash stamped and immutable — names the acceptable
    outcomes as "a mechanism that detects backstop events, or a declaration made after
    the fact", and §7 concedes "neither of which is what §5 supplies". A SPEC closing
    an open item of an accepted ADR also contradicts the amendment discipline ADR-0009
    itself establishes ("a successor record" per the ADR-0007 precedent, after an
    in-place edit was reverted). §7 defers the propagation question to the director
    while §5 has already asserted the closure — the SPEC both claims the item closed
    and asks whether it may be. Additionally, §5's blanket "no signal ... without
    the author's cooperation" answers only the first of ADR-0009's two acceptable
    outcomes; a declaration made after the fact is by construction cooperative and
    was never a detection problem, so the impossibility argument does not reach it.
  status: accepted
  disposition_reason: 'Both halves are right. The document no longer closes anything:
    section 1 states the detector item is NOT discharged and stays open. And the impossibility
    argument never reached ADR-0009''s second acceptable outcome, since a declaration
    made after the fact is cooperative by construction and was never a detection problem.'
- issue_id: I-006
  category: unverifiable-claim
  severity: medium
  description: '§6 claims the §4 measurement "is reproducible by running the job itself:
    it *is* the script, committed at `scripts/ledger_integrity.py`", and §4 reports
    "Measured before writing this, 2026-08-05: 39 approved/accepted artifacts, 0 failures."
    But §1 kills design 1 precisely on the repo''s order — "SPECs are approved and
    merged *before* implementation" — so at review time either the script is not committed
    (and the measurement and the reproduction instruction are both unfounded, the
    reviewer having nothing to run) or implementation preceded approval, contradicting
    the ordering premise this SPEC''s central argument depends on. The doc cannot
    have it both ways; neither branch is disclosed.'
  status: accepted
  disposition_reason: Section 3 now states that the measurement used a throwaway script
    rather than the shipped one, because this SPEC precedes its implementation, and
    that it is reproducible only in the sense that the algorithm is three lines and
    is written out.
- issue_id: I-007
  category: missing-invariant
  severity: medium
  description: '§1 makes read-only behaviour a hard requirement — "§4''s job must
    therefore be read-only — recomputing the hash itself, never calling `status()`"
    — because `ledger.status()` rewrites a mismatched SPEC to `in_review` and saves
    the file (`ledger.py:73-77`), i.e. detection destroys the evidence. §6''s test
    list has no test for this: nothing asserts that a run over a tampered SPEC leaves
    the file byte-identical, and nothing prevents a later refactor from routing the
    check back through `status()`. One of the two gaps this SPEC exists to close is
    therefore shipped unpinned, and its regression would be silent — the job would
    still go red on the mismatch while quietly downgrading the artifact.'
  status: accepted
  disposition_reason: Read-only was a hard requirement with no test. Section 5 now
    pins that a run over a repository containing a mismatched SPEC leaves every file
    byte-identical, guarding against a refactor routing the check back through ledger.status(),
    which rewrites the artifact.
- issue_id: I-008
  category: adr-contradiction
  severity: medium
  description: ADR-0008 §3 item 3, citing ADR-0002, requires that a gate be "declared
    fired by the director and recorded in that direction's first SPEC", and ADR-0002
    subordinates every new capability to demand-pull. This SPEC opens a new direction
    — CI-enforced governance integrity, shipping code — and records no gate declaration;
    the only director field present is a `does-not-fire` backstop ruling, which is
    the opposite construct (it records that a re-read requirement was not triggered,
    not that a build gate fired). ADR-0009 §3(ii) flagged precisely this class of
    defect as "an exception ... a single non-compliant instance, not a licence", so
    repeating it in the very SPEC answering ADR-0009's open items is a direct contradiction
    of the record being discharged.
  status: accepted
  disposition_reason: 'Correct: this opens a direction (CI-enforced governance) and
    carries a does-not-fire backstop ruling, which is not a gate declaration. Recorded
    in section 4''s table as a gap rather than papered over. Whether to declare the
    gate is the approver''s act.'
- issue_id: I-009
  category: unverifiable-claim
  severity: medium
  description: §5's disposition is a universal negative — "No signal available in
    this repository detects an ADR-0008 §5 backstop event without the author's cooperation"
    — supported only by enumerating four candidate anchors. §7 withdraws a different
    universal negative in the same document for exactly this defect ("a universal
    negative over the workflow files offered without a reference; withdrawn"), yet
    the load-bearing one is retained. Unexamined candidates that would falsify it
    include CODEOWNERS/branch-protection review requirements, merge-diff globs over
    `nexus/nexus/search/`, `requirements`/model-name diffs, and the `embed_health`
    / `reembed status` outputs ADR-0009 already records as machine-readable signals
    of an embedding change.
  status: accepted
  disposition_reason: 'The universal negative is withdrawn along with the disposition
    it supported, and section 2 now lists what was never examined: CODEOWNERS and
    branch protection, a merge-diff glob resolving the governing SPEC from the ledger,
    model-name and requirements diffs, and the embed_health / reembed status outputs
    ADR-0009 already records as machine-readable.'
- issue_id: I-010
  category: undefined
  severity: medium
  description: '§5''s table header states the four changes are "each independently
    sufficient to make a detector worth designing", but §1 says of row 4 that it "is
    the design that becomes worth building **once any of the other three rows lands**,
    and §5''s table says so rather than listing it as independently sufficient". §5''s
    table does not in fact say so — row 4''s cell claims it "does not need the local
    gate". The reader is left without a defined condition for when the deferred detector
    work begins: any-one-of-four, or one-of-three-then-four.'
  status: accepted
  disposition_reason: The contradictory table is gone with the impossibility disposition;
    there is no longer a claim about which change is independently sufficient, only
    a list of what was not examined.
- issue_id: I-011
  category: untestable-requirement
  severity: medium
  description: '§5 sets "Owner: LivingLikeKrillin. Trigger: the first of those that
    lands — each is a commit, so the trigger is in the log rather than in anyone''s
    memory." Nothing scans the log for those commits, and three of the four rows (frontmatter
    hashing, a server-side hook, signed commits) have no distinguishing marker a search
    could match. This is weaker than the trigger ADR-0009 chose for the same item,
    which was deliberately "a detectable event (`linked_adrs`)"; as written the obligation
    is discharged only if the owner happens to remember, which is the condition the
    sentence claims to have eliminated.'
  status: accepted
  disposition_reason: The 'trigger is in the log' claim is removed. Section 4 records
    the items as open with an owner and does not pretend an undetectable trigger is
    detectable - which is the defect ADR-0009 deliberately avoided when it chose linked_adrs.
- issue_id: I-012
  category: missing-invariant
  severity: low
  description: §6 pins "a whitespace-only edit must *not* fail" as a permanent assertion,
    freezing the blind spot rather than bounding it. In Markdown, trailing whitespace
    is semantic — two trailing spaces are a hard line break — so an edit that changes
    the rendering of an approved artifact's body passes by design and is now protected
    by a test. §4 calls the third negative-control row "a real blind spot", but no
    invariant states its bound (whitespace changes must not alter rendered meaning),
    so the test locks in the gap without limiting it.
  status: deferred
  disposition_reason: 'Correct and not repaired: pinning ''whitespace-only must not
    fail'' freezes the blind spot rather than bounding it, and trailing whitespace
    is semantic in Markdown. Bounding it requires an invariant at the rendered level,
    which this job does not have. Recorded in section 6 risks; owed if the normalisation
    is ever revisited.'
approved_by: LivingLikeKrillin
approved_at: '2026-08-05T09:28:49Z'
---

