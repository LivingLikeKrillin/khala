---
target: SPEC-nexus-korean-embedding-comparison
critiqued_hash: sha256:7f442afc9fa5ceebcfbbbeac934e81e651e31ff1c10d12681d062257e5889712
critiqued_at: '2026-08-03T12:32:45Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: '§4.5 bumps the gold set to label revision 3 by adding documents adjudicated
    from the KURE/nomic arms, but only requires that the *keyword floors* be re-recorded.
    The already-committed mecab-vs-nori verdict (nexus/tests/eval/reports/2026-08-03-mecab-vs-nori.md:
    wins 7 / losses 2 / p=0.180, computed on revision 2) is not re-run against revision
    3. New gold documents change per-query Recall@10 and MRR@10 for both tokenizer
    arms and can flip discordant pairs, so after this SPEC lands, the sole evidence
    for mecab-ko retention — and for ADR-0008 §5(b) — will have been computed on a
    gold set that no longer exists, with no invariant requiring the two reports to
    cite the same revision.'
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: risky-assumption
  severity: high
  description: The SPEC claims to enumerate and remove all four confounds (§3), but
    never controls input truncation. config.yaml chunking.korean_tokens is 1100, while
    §4.4 merely *records* max sequence length as provenance. If KURE-v1's sentence-transformers
    max_seq_length (512 on the published checkpoint) is shorter than the chunk, KURE
    silently sees a truncated chunk while nomic (served via Ollama with its own num_ctx
    default) sees a different prefix of the same text. The comparison would then measure
    window size, not model quality — the embedding-shaped repeat of exactly the POS-filter
    confound §4.3 says it is avoiding. No acceptance item or test asserts that zero
    chunks are truncated in either arm.
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: undefined
  severity: high
  description: §4.6 and §7 require fused numbers to be reported alongside the vector
    leg ('a vector-leg win that RRF erases is a real result'), and §4.5 pools 'the
    keyword arm, since fused results are reported'. But the existing harness implements
    only run_keyword_leg (nexus/scripts/ko_eval_harness.py:221) — there is no vector
    leg and no RRF fusion in the eval path, and load_pack indexes BM25 only, never
    embeddings. The four Units in §8 build the exact-scan vector leg but no fusion
    stage, no RRF-over-eval-legs implementation, and no embedding of pack chunks into
    the eval store as part of pack loading. The work required to satisfy §7 is not
    in the plan.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: untestable-requirement
  severity: high
  description: 'The only ''null comparison'' in §6 — ''two arms of the same model
    produce identical rankings'' — is true by construction: same vectors, same deterministic
    exact scan with chunk_rid as total-order key. It cannot fail for any reason other
    than nondeterminism, so it proves nothing about whether the instrument is sensitive
    to a model difference. ADR-0008 §2.6 confound 5 names precisely this gap (the
    recall fixture''s deliberate-degradation negative control is ''the check that
    proves the instrument has teeth''), and this SPEC ships no equivalent: nothing
    establishes that the vector-leg harness could have detected a model that is genuinely
    worse.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: adr-contradiction
  severity: medium
  description: 'ADR-0008 §3 item 3 unblocks a Korean evaluation set only ''to be proposed,
    each through its own SPEC and gate'', and fixes the procedure from ADR-0002: a
    gate is ''declared fired by the director and recorded in that direction''s first
    SPEC — it is not argued into existence by the SPEC''. It further declines to extend
    ADR-0006''s entropy override to retrieval-quality instruments, calling that ''a
    call for the director to make, not a reading to assume''. This SPEC records no
    fired gate and no director declaration; §1 argues the work into existence from
    the rule-9/config contradiction, which is the move ADR-0002''s procedure forbids.'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: risky-assumption
  severity: medium
  description: The whole verdict rests on Pack A (265 public Korean k8s docs), yet
    §7 requires the report to state 'which of nomic-embed-text and KURE-v1 the evidence
    favours' with no generalisation caveat. The parent SPEC's §7 and its committed
    report both require the statement that Pack A is not Khala's own corpus, and ADR-0008
    §2.6 records the same limit. Dropping that requirement means a result on out-of-domain
    public documentation becomes the recorded evidence for changing the embedding
    model of a system whose real corpus is internal Notion/filesystem content.
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: missing-invariant
  severity: medium
  description: '§4.5 pools ''the top-10 of every arm'' but names only the two embedding
    arms and the keyword arm — the fused leg is excluded. The parent SPEC''s rule
    is the union of the top-10 of *every leg* of every configuration, and fused is
    a distinct leg: legs run at depth 20 (bm25_top_k/vector_top_k) while pooling is
    at depth 10, so RRF can promote a document ranked 11–20 in every leg into fused''s
    top-10, where it is unjudged and silently scored non-relevant. Since §4.6 requires
    fused to be reported as the user-facing consequence, fused metrics would be computed
    against a knowingly incomplete pool.'
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: missing-invariant
  severity: medium
  description: ko_eval_embeddings (§4.1) is keyed on (model, chunk_rid) with no tenant,
    pack, label-revision, or foreign key to chunks. chunk_rid is derived from doc_rid,
    which the harness builds from a tenant-qualified uri, and the DB fixture deletes
    and reloads chunks between runs. An arm embedded against a previous load or a
    different tenant therefore leaves rows that satisfy the only guard the SPEC defines
    (count(*) == 1906) while pointing at chunk_rids that no longer exist, and the
    exact scan returns rids that map to nothing. §5's 'replaced wholesale per model'
    prevents mixed checkpoints but not mixed loads.
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: unverifiable-claim
  severity: medium
  description: '§4.3 asserts that nomic''s model card says ''quality drops sharply''
    without prefixes and that ''BGE-M3-family models (KURE-v1) expect the raw text'',
    with no citation and no measurement. The second claim is the load-bearing one:
    the KURE arm''s configuration is chosen from an assumption about what its checkpoint
    expects. If KURE-v1''s own card specifies a query instruction (as several BGE-derived
    retrieval checkpoints do), the run measures misuse of KURE in the opposite direction,
    and the SPEC''s own argument against nomic-prefixed KURE applies verbatim. No
    test or acceptance item validates the chosen prefix policy against either model''s
    documentation.'
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: undefined
  severity: medium
  description: §4.6 substitutes the vector leg as the decisive leg but does not define
    the outcome mapping §7 demands. If the vector leg reaches p<0.05 for KURE while
    fused shows no difference or favours nomic, §7 still requires a single statement
    of 'which the evidence favours' — and §2 says the swap SPEC inherits these numbers
    as evidence. Nothing says whether that case counts as favouring KURE. The inherited
    ≥6-discordant-pair precondition is also carried over unchanged without re-deriving
    it for a leg whose tie structure differs from the keyword leg it was calibrated
    on.
  status: accepted
  disposition_reason: null
- issue_id: I-011
  category: missing-invariant
  severity: medium
  description: The SPEC never fixes what text is embedded. Production embeds the composed
    string from nexus/nexus/utils.py (context_prefix or '[section_path]' prepended
    to chunk_text), not chunk_text alone. §4.3 discusses only the model instruction
    prefix and §4.4 only the provider, so an implementer may embed raw chunk_text
    in the eval arms — a different input than production and, worse, a different input
    than whatever the other arm's implementer chooses. Both arms seeing byte-identical
    input text is the core invariant of a model comparison and it is stated nowhere.
  status: accepted
  disposition_reason: null
- issue_id: I-012
  category: risky-assumption
  severity: medium
  description: §4.5 step 2 says 'judge every pooled document not already in gold'
    with no blinding and no adjudication criteria beyond what the parent SPEC records
    as process. The documents being judged are precisely those that one arm surfaced
    and the other did not, and the adjudicator is the same party that authored the
    hypothesis that KURE-v1 is the better model. Unblinded relevance judgements on
    arm-distinguishing documents bias the resulting gold set toward whichever arm
    the judge expects to win, and this bias enters the revision-3 labels that all
    future comparisons inherit.
  status: accepted
  disposition_reason: null
- issue_id: I-013
  category: scope-creep
  severity: low
  description: §4.3 moves the prefixes out of nexus/nexus/providers/embedding.py:30-32
    into per-model configuration — a change to the production embedding path — inside
    a SPEC whose §2 non-goals and §7 acceptance both promise production is untouched
    ('no new production dependency', 'behaves exactly as before'). It also ignores
    that config.yaml:40-41 already declares embedding.document_prefix / query_prefix,
    which the service currently does not read; the SPEC neither reconciles those dead
    keys nor says whether they become the per-model source, leaving two candidate
    configuration surfaces after the change.
  status: accepted
  disposition_reason: null
- issue_id: I-014
  category: untestable-requirement
  severity: low
  description: '§5 and §7 hardcode 1,906 as the chunk count for each arm, and §6 tests
    that the harness refuses to score an arm whose count differs ''from the pack''s
    chunk count''. The two statements are not the same guard: the literal 1906 is
    a function of chunking.korean_tokens (1100) and overlap_ratio (0.15) in config.yaml,
    so any chunker or config change makes the acceptance criterion assert a stale
    number while the test still passes. The SPEC gives no derivation or source of
    truth for 1906, and §5''s abort condition (''dimension not 1024'') hardcodes an
    expected dimension per model with no registry defining it.'
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-08-03T12:44:25Z'
---

