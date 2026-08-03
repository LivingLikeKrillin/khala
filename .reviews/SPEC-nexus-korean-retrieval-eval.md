---
target: SPEC-nexus-korean-retrieval-eval
critiqued_hash: sha256:db4638a931b8bd2b4a78678edc6f994d470d3b908f24515fefcf9a97e68dca8f
critiqued_at: '2026-08-02T10:32:25Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: §4.2 pools only the top-5 of every leg of every configuration, but
    §4.3 computes Recall@10/MRR@10/miss over the first 10 collapsed documents. Ranks
    6–10 are never adjudicated, so unjudged-but-relevant documents inside the scored
    window are counted non-relevant by construction — the same systematic penalty
    the SPEC identifies for out-of-pool configurations, silently applied to every
    configuration in the pool. Pool depth must be ≥ metric depth (or the metric cut
    must be ≤ pool depth); nothing in the doc states that invariant.
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: untestable-requirement
  severity: high
  description: §4.3's verdict is a two-sided exact sign test at α=0.05 over 40 queries
    with ties excluded. A two-sided binomial cannot reach p<0.05 with fewer than 6
    discordant pairs (6-0 gives p≈0.031). Recall@10 on a 265-document corpus will
    tie on most queries, so the instrument may be structurally incapable of ever firing
    ADR-0008 §5(b) regardless of how large the true tokenizer difference is. The SPEC
    acknowledges inconclusiveness is likely (I-012) but never states the minimum discordant
    count needed for the test to be able to conclude anything, and never checks it
    against an expected tie rate.
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: undefined
  severity: high
  description: §4.1's normalisation rules cover front-matter, shortcodes, HTML comments,
    CRLF→LF, trailing whitespace and final newline — but never specify a Unicode normalisation
    form. Hangul may arrive or be written as NFC or NFD depending on platform and
    tooling. This breaks the explicit 'two people running the builder get byte-identical
    packs' guarantee and the SHA-256 manifest, and worse, NFC vs NFD changes what
    mecab and nori produce — i.e. it silently perturbs the exact quantity the SPEC
    exists to measure.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: missing-invariant
  severity: high
  description: §4.4 defines the seam as `Tokenizer.tokenize(text) -> list[str]`, which
    carries no POS information, yet the same section claims 'nori' means 'nori's segmentation
    under our filter policy' (the mecab tag allow-list). With a bare list[str] there
    is no way to apply the allow-list to nori's output, so the mecab arm is allow-list-filtered
    and the nori arm is not. That reintroduces a filter-policy confound at precisely
    the comparison point the SPEC was written to de-confound, and no test in §6 detects
    it.
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: adr-contradiction
  severity: medium
  description: §4.3 maps `p ≥ 0.05` to 'mecab-ko is retained', but ADR-0008 §5(b)
    states the condition as 'its result does not favour mecab-ko'. An inconclusive
    result does not favour mecab-ko, so by the ADR's own wording it would satisfy
    (b), while the SPEC treats it as retention. The SPEC narrows a deliberately unquantified
    ADR condition into a default-for-the-incumbent rule without amending the ADR —
    and ADR-0008 §3 explicitly warns that the incumbent is not being claimed good.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: adr-contradiction
  severity: medium
  description: 'ADR-0008''s Status is ''In review. Binding on acceptance.'' The SPEC
    nonetheless treats it as binding authority throughout: §1.1 says ''ADR-0008 §3
    requires…'', §4.3 says ''ADR-0008 §5 assigned this SPEC the job of naming the
    criterion'', and §4.5 makes the committed report the answer to §5(b). If the ADR
    is amended or rejected in review, the SPEC''s gate record, verdict placement and
    unblocking claims all move. Also, the procedure §1.1 attributes to ADR-0008 §3
    is attributed by that ADR to ADR-0002 (''the procedure ADR-0002 fixes'').'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: adr-contradiction
  severity: medium
  description: ADR-0008 §5's backstop fires on 'work that would materially expand
    Nexus's retrieval stack — a new retrieval channel, a second index backend, a tokenizer
    or embedding-model change'. Unit 4 adds a Tokenizer abstraction into two production
    files, a second tokenizer implementation, and an OpenSearch container dependency.
    §2 asserts the seam 'is not such a change' and moves on; no re-read of ADR-0008
    is recorded, and the SPEC decides for itself that a trigger it names did not trigger.
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: adr-contradiction
  severity: medium
  description: §2 puts 'LLM-as-judge, in any role, including relevance labelling'
    permanently out of scope on ADR-0002's identity invariant, then in the same bullet
    permits labels to be written 'by an agent under human review'. Agent-authored
    relevance labels are LLM relevance labelling; 'under human review' is asserted
    with no mechanism, no provenance value distinguishing agent-authored from human-authored
    records (§4.2 allows only `authored_from_doc` | `adjudicated`), and no test in
    §6. The ban is therefore unenforced against its most likely violation.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: undefined
  severity: medium
  description: Pack B is given a definition, a location, a manifest requirement, an
    export format, a run protocol and a verify-or-it-is-not-a-result rule (§4.1),
    and §4.6 says the harness parameterisation exists to make it possible — but §8's
    four units contain no Pack B work and §7's acceptance criteria never mention it.
    Either it is unbuilt scope stated as design, or it is unassigned work that will
    be discovered mid-implementation. Since ADR-0008 §5(b) is 'fully satisfied only
    when a Pack B export is labelled and run', the SPEC's headline unblocking claim
    rests on the one artifact no unit produces.
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: undefined
  severity: medium
  description: §4.5 says the new Pack A metrics run in 'the existing `nexus (search
    recall, mecab)` job', but never says what happens to `tests/test_search_recall.py`
    itself — retained, extended, or retired. §3 argues it is a valid regression guard
    for the keyword leg and an invalid comparator, so its disposition is a real decision.
    If it is retired, the negative control that ADR-0008 §2.6 credits goes with it;
    if retained, its floors and the new floors are two independently pinned standards
    over two corpora in one job with no stated precedence.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: untestable-requirement
  severity: medium
  description: §4.2/§6's machine check — 'no gold document's title or any of its headings
    may appear as a substring of the query, after whitespace normalisation' — has
    no minimum length. Kubernetes Korean docs routinely carry one- or two-word headings
    such as `파드`, `노드`, `볼륨`. Under this rule a `loanword` or `compound` query that
    uses the very term the stratum exists to stress will fail the gate, forcing labellers
    toward unnatural queries that avoid the vocabulary being measured. The rule as
    written is in direct tension with two of the five strata.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: missing-invariant
  severity: medium
  description: §4.2 mandates 40 answerable queries at exactly 8 per stratum, but the
    §6 test only asserts 'Each stratum has ≥ 5 queries'. Nothing enforces the balance
    the design depends on, and §4.3's 'eight queries move 12.5 recall points per query'
    caveat assumes it. Additionally, the schema requires `stratum` on every record
    while the 5 unanswerable queries have no stated stratum assignment, so it is undefined
    whether they count toward the per-stratum minimum — a labeller can satisfy the
    test with a 5/5/5/5/20 split, or with unanswerable records padding a stratum.
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: risky-assumption
  severity: medium
  description: The manifest guard ('fails if the count or any hash disagrees with
    the committed manifest') detects drift after the first commit but cannot detect
    a wrong initial extraction — the committed manifest is whatever the first builder
    run produced. This is exactly the self-certification critique the SPEC applies
    to floors in I-011 (§4.5), with no equivalent independent bound applied to the
    pack. The stated 265 documents / ~2.75 MiB is disclaimed as 'not trusted from
    this text', yet §7 makes '265-document' an acceptance criterion, so a selection-rule
    bug that yields a different count silently becomes the standard or fails acceptance
    for the wrong reason.
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: undefined
  severity: medium
  description: '§4.1''s shortcode rules enumerate only the `{{< … >}}` angle-bracket
    form. Hugo''s percent form `{{% … %}}` (used in kubernetes/website Korean content,
    e.g. capture/tab-style shortcodes) is not covered by any of the three rules, so
    its handling is unspecified. Nested cases are also unaddressed: a `text=`-bearing
    tag inside a paired `note` block, and self-closing tags carrying `text=` that
    are also in the ''every other tag'' removal list. The 2,872-tag survey is cited
    as the basis for the ruleset but its per-form breakdown is not given, so the claim
    that three rules cover the corpus is unverifiable from the document.'
  status: accepted
  disposition_reason: null
- issue_id: I-015
  category: missing-invariant
  severity: low
  description: '§5 lists ''a third `tokenize_korean` call site appears'' as a mechanically
    guarded failure, with the guard being §6''s import-boundary test (''no module
    outside the tokenizer seam imports tokenize_korean directly''). An import check
    does not catch an additional call site added inside `index/bm25.py` or `search/hybrid.py`
    themselves, nor dynamic access. The guard is weaker than the failure it is tabled
    against, and the table marks it ''mechanical: yes''.'
  status: accepted
  disposition_reason: null
- issue_id: I-016
  category: undefined
  severity: low
  description: §4.5's sanity bound 'keyword-leg Recall@10 ≥ 0.50 and misses ≤ 25%'
    does not say whether Recall@10 is the macro-mean over the 40 answerable queries
    or a per-query minimum, and 'floors' (plural) is never enumerated — it is unstated
    whether floors exist per leg, per stratum, for MRR@10, or only for the aggregate
    keyword Recall@10. §6 asserts 'metrics meet the recorded floors' without resolving
    this, so two implementers can build different CI gates from the same text.
  status: accepted
  disposition_reason: null
- issue_id: I-017
  category: scope-creep
  severity: low
  description: The 5 unanswerable labels are excluded from every aggregate and carry
    only one assertion ('resolve to no gold document'), and the reserved `context`
    field is explicitly absent today — both exist solely for `SPEC-nexus-multi-turn-retrieval`
    and the unbuilt abstention work (§4.2, §4.6). They add labelling cost and schema
    surface to this SPEC while measuring nothing in it, and they inflate the headline
    '45 labels' in §7's acceptance criteria over the 40 that the instrument actually
    uses.
  status: rejected
  disposition_reason: 의도된 소량 스코프. 멀티턴 SPEC Unit 1 이 같은 코퍼스에 같은 종류의 라벨(답변불가)을 요구하므로
    40건과 함께 쓰면 몇 분, 나중이면 별도 패스가 된다. 대신 §7 이 40/5 를 분리 표기해 '45' 가 작업 표본을 대신하지 않게 했다.
approved_by: LivingLikeKrillin
approved_at: '2026-08-02T11:04:10Z'
---

