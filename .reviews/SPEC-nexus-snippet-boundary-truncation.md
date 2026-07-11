---
target: SPEC-nexus-snippet-boundary-truncation
critiqued_hash: sha256:fd8692ec9c82a796361c0a8b934859ad771891988f1f33c28ed848ca2a7e1f2a
critiqued_at: '2026-07-11T19:48:00Z'
issues:
- issue_id: I-001
  category: missing-invariant
  severity: high
  description: '§5''s length invariants are self-contradictory and one is violable.
    It first says output is ''never longer than max_chars plus a completed sentence
    it chose to keep'', then says the cut index is always < max_chars so output ≤
    max_chars + len('' …'') — these describe two different behaviors (keeping a sentence
    past max_chars vs never cutting past it). Worse, ''never returns text longer than
    the original'' is false in the hard-cut branch: input of length max_chars+1 yields
    max_chars + '' …'' = max_chars+2 characters, longer than the original. The invariants
    as written cannot all hold and cannot be tested as stated.'
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: risky-assumption
  severity: high
  description: 'The design assumes cutting back to a boundary is harmless, but the
    boundary/whitespace threshold of max_chars//2 means the LLM can receive as little
    as ~150 of today''s 300 characters — up to 50% less evidence text in the common
    case. Long Korean/technical sentences frequently exceed 150 chars, so the trailing
    partial sentence the model previously saw (and could still ground on) is now silently
    dropped. The doc claims ''strictly no worse than today'' only for the rare hard-cut
    branch and never analyzes this information-loss trade-off, nor plans to measure
    it despite the repo''s existing search_log/citation-fabrication signal infrastructure
    (PRs #27, #136) that could detect a faithfulness regression.'
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: risky-assumption
  severity: medium
  description: '§4''s numeric-period note is wrong for the case that matters: treating
    any ''.'' as a sentence boundary means ''3.14'', ''v2.3'', or ''1.5M'' near the
    cut point can be severed to ''3. …'' — corrupting a numeric fact mid-token, which
    directly contradicts the doc''s own ''never sever a word or mid-clause'' rationale
    and is *worse* than today''s dumb cut (a truncated number reads as a different,
    complete-looking value to the LLM). The doc dismisses this as ''still a clean,
    non-word-severing cut'' without considering decimals/versions, which are common
    in exactly the decision-grade evidentiary text this change is meant to protect.
    No test covers it.'
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: undefined
  severity: medium
  description: 'The fallback ladder has an undefined branch: §4 says fall back to
    ''last whitespace ≥ max_chars // 2'' and hard-cut only ''if neither exists (e.g.
    a long unbroken token)''. But text whose only whitespace sits before max_chars//2
    is neither case — whitespace exists, just not past the threshold. As written it''s
    ambiguous whether this hard-cuts (severing a word, violating the stated guarantee)
    or accepts the early whitespace (losing most of the snippet). The §6 tests only
    cover ''no boundary and no space in range'', not this gap.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: untestable-requirement
  severity: medium
  description: §7's acceptance criterion is stated as an unconditional guarantee —
    'An evidence snippet the LLM receives ends at a sentence (or at worst a word)
    boundary, not in the middle of a word' — but the design's own hard-cut fallback
    (§4, tested in §6) explicitly produces mid-word cuts for unbroken tokens. The
    acceptance criterion as written can never be certified against the design that
    accompanies it; it needs the same 'except graceful worst case' qualifier the design
    carries.
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: risky-assumption
  severity: medium
  description: 'The doc frames the change as affecting only ''what the LLM sees'',
    but SearchHit.snippet also flows to human surfaces (API responses, web chat.js,
    Slack formatter''s evidence_snippets) and to existing tests. Changing the suffix
    from ''...'' to '' …'' (different characters) and lengths from a fixed 300 to
    variable 150–300 alters every truncated snippet everywhere; the doc verified no
    further *truncation* downstream but never surveyed consumers that key on the old
    suffix/length (UI rendering, tests, logged-signal baselines). Verified in-repo:
    snippets reach slack/formatter.py and the web view, not just format_for_llm.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: adr-contradiction
  severity: medium
  description: ADR-0004 §3 establishes Nexus as dual-mode — the same answer surface
    serves humans via the web UI and agents via MCP/A2A — yet the design doc's §2
    ('the snippet text is display/LLM input only') and §7 acceptance reason exclusively
    about LLM narration quality. The snippet is also the human-visible evidence in
    the hosted UI (and per nexus/CLAUDE.md's error-handling rule, snippets are served
    to users verbatim when LLM answering fails). A design that changes evidence text
    for both modalities but evaluates impact on only one is in tension with the ADR's
    dual-mode consequence ('different audience, different deploy').
  status: accepted
  disposition_reason: null
- issue_id: I-008
  category: unverifiable-claim
  severity: medium
  description: '§1''s motivating claims — the 300-char cut ''routinely severs the
    evidentiary sentence'' and this is ''hurting faithfulness'' — are asserted with
    no measurement, sample, or signal evidence, even though the project already ships
    the instrumentation to quantify both (search_log / v_search_health, and the citation-fabrication
    measurement added in PR #136). ''Routinely'' and ''hurting'' are load-bearing
    for the design''s priority but are unverifiable as written.'
  status: accepted
  disposition_reason: null
- issue_id: I-009
  category: scope-creep
  severity: low
  description: '§3 declares window tuning a non-goal, yet §4 adds the tuning machinery
    anyway: a new config key (search.snippet_max_chars), threading through hybrid_search
    into _enrich_hits, and a §6 test for the config path. The stated goal (boundary-aware
    cut at the existing 300) requires none of this; making the max tunable is a separate
    small feature smuggled in against the doc''s own non-goals section.'
  status: accepted
  disposition_reason: null
- issue_id: I-010
  category: undefined
  severity: low
  description: '§4''s ''cut just after'' the boundary leaves punctuation-adjacency
    behavior unspecified: sentence terminators followed by closing quotes/brackets
    (''."'', ''다.")'') would be cut inside the quotation; whether a terminator must
    be followed by whitespace/EOL to count as a boundary (the key to the abbreviation/decimal
    problem) is not defined; and whether trailing whitespace is stripped before appending
    '' …'' is unstated. §6 has no test for any of these.'
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-11T19:50:25Z'
---

