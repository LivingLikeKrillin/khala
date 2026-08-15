---
target: SPEC-nexus-doc-code-anchors
critiqued_hash: sha256:a2f577844ce5245c836655d5ba512be26ebf3d01e22538835aa2057ea35e4093
critiqued_at: '2026-08-15T15:24:04Z'
issues:
- issue_id: I-001
  category: adr-contradiction
  severity: high
  description: '§1''s ADR-0008 re-read clears the backstop by asserting ''there is
    no new index backend'', but §3.1/§3.3 introduce exactly that: a new persistent
    symbol index plus a stored edge table with commit_sha/span_hash/bound_at. §1 itself
    says the existing code_source.py/gate_source.py ''store nothing: the resolution
    is recomputed per call and then discarded'' — so this unit adds a durable index
    Nexus does not have today. The exemption is asserted by re-definition rather than
    argued against ADR-0008 §5''s wording, and the ADR''s backstop exists precisely
    to stop that move.'
  status: open
  disposition_reason: null
- issue_id: I-002
  category: adr-contradiction
  severity: high
  description: 'ADR-0008 §3 item 3 fixes the procedure: ''a gate is declared fired
    by the director and recorded in that direction''s first SPEC — it is not argued
    into existence by the SPEC'', with ADR-0002 demand-pull discipline applying. This
    SPEC has no gate section, names no director declaration and no puller; §1 ''What
    prompted it'' argues the work into existence from two external papers. Under the
    ADR''s own procedure this SPEC is unauthorised as written, regardless of the merits
    of §3.'
  status: open
  disposition_reason: null
- issue_id: I-003
  category: risky-assumption
  severity: high
  description: The motivating TRACE finding is about a reader shown both prose and
    code ('A corpus holding both a spec and the code it describes will drift toward
    the spec'), but §2's first non-goal forbids code from ever entering the corpus
    or /search results. If code is never retrieved, the answer LLM is never in the
    doc-vs-code comparison TRACE measures, so the cited mechanism does not operate
    in Nexus and the premise does not support the design it is used to justify.
  status: open
  disposition_reason: null
- issue_id: I-004
  category: unverifiable-claim
  severity: high
  description: §1 states 'the answer path has a measured bias toward the wrong one'.
    Nothing measured Nexus's answer path — the numbers are TRACE's 456 Java method
    bundles across 7 LLMs on a different task. No instrument on Khala's corpus is
    cited or proposed (§6 measures anchor yield and binding precision, never the claimed
    answer-path bias), so the SPEC's headline justification is an unmeasured transfer
    stated as a measurement.
  status: open
  disposition_reason: null
- issue_id: I-005
  category: untestable-requirement
  severity: high
  description: §6 defines no pass/fail threshold for any item. Anchor yield, precision
    sample, and unparsed share are all 'reported' or 'recorded, not asserted' — there
    is no value at which the unit is rejected, so acceptance cannot fail. Worse, §1
    rejects prior art at ~70% precision, but a 30-item hand-check has roughly ±17pp
    at 95% confidence and cannot distinguish 70% from 90%; the sample size is too
    small to decide the one question the design's precision argument rests on.
  status: open
  disposition_reason: null
- issue_id: I-006
  category: scope-creep
  severity: high
  description: '§3.5''s guard ''compares it against the remote tip'', which requires
    network access to a git remote or its API at re-check time. §2 explicitly bounds
    input: ''No GitHub App, webhook, or API connector. The checkout on disk is the
    only input.'' The guard therefore contradicts the non-goal that the §1 re-read
    leans on to argue ADR-0008 §5 (''connector work beyond the existing two sources'')
    is not tripped, and no behaviour is defined for an unreachable or unauthenticated
    remote.'
  status: open
  disposition_reason: null
- issue_id: I-007
  category: missing-invariant
  severity: high
  description: '§3.5 covers only ''snapshot behind remote'', but the same confident-direction
    lie arises from states it does not name: a dirty working tree (span_hash is computed
    from uncommitted text while commit_sha claims otherwise), detached HEAD, a checkout
    ahead of or diverged from the remote, or a different branch than the one the docs
    describe. ''How far'' behind is also undefined — any commit at all, or only commits
    touching parsed files — so the guard''s firing condition is not implementable
    as specified.'
  status: open
  disposition_reason: null
- issue_id: I-008
  category: undefined
  severity: high
  description: §3.2 extracts four candidate classes, but §3.1 indexes only Java symbols
    and §3.3 binds only to 'exactly one symbol in the index'. File paths match every
    symbol in that file (always ambiguous → no edge); HTTP endpoint paths and configuration
    keys are not symbols and match nothing (always zero → no edge). Three of four
    extraction rules are structurally unbindable, yet §6.1 reports refusals split
    by 'zero vs ambiguous' — the denominator will be dominated by candidates that
    could never bind, making the reported bind rate uninterpretable.
  status: open
  disposition_reason: null
- issue_id: I-009
  category: missing-invariant
  severity: high
  description: Binding happens 'at ingest' (§3.2/§3.3) against whatever the symbol
    index held at that moment, but the index is built by a separate scan command (Unit
    1) and no unit re-binds. A document ingested before the first scan, before a symbol
    exists, or while a scan is mid-flight resolves to zero matches and stays permanently
    unanchored, since §3.3 records nothing for a refusal. Bind rate then depends on
    ingest-vs-scan ordering, and §6.1's yield number measures scheduling as much as
    corpus behaviour.
  status: open
  disposition_reason: null
- issue_id: I-010
  category: undefined
  severity: medium
  description: §3.4's re-check assumes the stored anchor re-resolves to zero or one
    symbol, but never states the resolution key (name only? file_path+name? +kind?
    +signature?). The ambiguous case at re-check — a second overload or a same-named
    class added in another package after binding — has no row in the table, and neither
    does a symbol that moved to a different file with identical text. Without the
    key and those states, `orphaned`/`fresh`/`changed` is not computable from the
    spec.
  status: open
  disposition_reason: null
- issue_id: I-011
  category: undefined
  severity: medium
  description: Storage, tenancy, and multiplicity are unspecified. The §3.1 row carries
    a `repo` column implying many repositories while the scan reads a single `code_source.repo_path`;
    no table, migration, or uniqueness key is given; nothing says whether symbols
    and edges are tenant-scoped though Nexus's documents and chunks are; and re-scan/re-ingest
    idempotency (does a second scan duplicate rows or supersede them?) is not addressed.
  status: open
  disposition_reason: null
- issue_id: I-012
  category: undefined
  severity: medium
  description: '`span_hash` is ''a hash of the symbol''s source text as extracted''
    with no normalisation rule — whether comments, annotations, leading trivia, line
    endings, or trailing whitespace are included, and which hash. §4 accepts that
    reformatting yields `changed`, but without the algorithm the fresh/changed split
    is not reproducible across platforms (CRLF alone would flip every anchor on a
    Windows checkout) and §6.3''s one-line-change test cannot be written to a defined
    expectation.'
  status: open
  disposition_reason: null
- issue_id: I-013
  category: risky-assumption
  severity: medium
  description: §4 argues that unique-resolution removes most incidental mentions 'because
    common names collide'. Collision only helps for names defined more than once in
    the single Java repo; a domain name with exactly one definition (`User`, `Session`,
    `Order`) mentioned in passing prose binds uniquely and falsely, and generic names
    like `Map` typically live outside the repo and resolve to zero regardless. The
    load-bearing precision claim is thus deferred entirely to a 30-item sample with
    no threshold (§6.2).
  status: open
  disposition_reason: null
- issue_id: I-014
  category: unverifiable-claim
  severity: medium
  description: '''This is the mechanism under every drift tool with a defensible precision
    story'' is a universal claim with no survey behind it, and neither Swimm, Dosu,
    nor the Toss convergence is given a precision figure or citation — the very evidence
    the sentence asserts exists. The SPEC''s core design choice inherits its credibility
    from this unsourced generalisation.'
  status: open
  disposition_reason: null
- issue_id: I-015
  category: unverifiable-claim
  severity: medium
  description: '§1 composes a prediction from three unrelated measurements: DocPrism''s
    function-level rates, PaperQA2''s ~70% corpus-wide contradiction precision, and
    a ~3.3% base rate from CLAIRE/WIKICOLLIDE. Different tasks, corpora, and units
    are combined to conclude what ''a detector at those numbers'' would do on Khala''s
    corpus, where neither the base rate nor the detector has been measured.'
  status: open
  disposition_reason: null
- issue_id: I-016
  category: risky-assumption
  severity: medium
  description: The SPEC treats ADR-0008 §5 as a binding obligation it must discharge,
    but the linked ADR's status line reads 'In review. Binding on acceptance.' If
    it is still in review, the §1 re-read discharges an obligation that has not attached,
    and if it has since been accepted the SPEC is citing a stale copy — either way
    the acceptance state the argument depends on is not established in the document.
  status: open
  disposition_reason: null
- issue_id: I-017
  category: untestable-requirement
  severity: low
  description: §6.3 requires confirming that the orphaned/changed detection 'required
    no LLM call', but no observable is defined — no call counter, no provider-level
    assertion, no offline/no-key run mode. As written the check is an inspection claim
    rather than a test, in a repo where LLM backends are configured by environment
    variable and can be reached from several paths.
  status: open
  disposition_reason: null
approved_by: null
approved_at: null
---

