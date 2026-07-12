---
target: SPEC-nexus-web-citation-verification
critiqued_hash: sha256:10b321cd958bda7f6fd6503a787064cff8831c534e7ae88ab8ab4a631522158c
critiqued_at: '2026-07-12T05:50:16Z'
issues:
- issue_id: I-001
  category: risky-assumption
  severity: high
  description: 'Empty/absent `citations` is treated as benign (''answer cited nothing
    / LLM-not-configured'') and renders NO strip. But an LLM answer that streams text
    yet emits zero `[출처: …]` tags produces `citations: []` too — a fully ungrounded
    answer, the single worst faithfulness case (violates nexus CLAUDE.md principle
    #1 ''Grounded answers only, 추측 금지''). The SPEC''s own goal is to surface faithfulness,
    yet the highest-risk case gets no signal at all. Distinguish ''no answer'' from
    ''answer with zero citations''.'
  status: accepted
  disposition_reason: null
- issue_id: I-002
  category: risky-assumption
  severity: medium
  description: The doc equates `verified:false` with a 'fabricated citation' (§1)
    and renders the summary '근거에 없음 — 주의' (not in evidence). But backend `_classify`
    sets verified only on an EXACT normalized (whitespace/lowercase) title match against
    packet snippet titles. Any surface variation the LLM introduces — abbreviated/partial
    title, translated title, trailing punctuation, wrong section split — yields verified:false
    for a source that WAS shown. The user-facing copy then mislabels a matching failure
    as fabrication, eroding the trust signal it exists to provide.
  status: accepted
  disposition_reason: null
- issue_id: I-003
  category: untestable-requirement
  severity: medium
  description: The core acceptance behavior — the `.citation-strip` renders inside
    the bubble with correct tone, per-citation ✓/⚠ markers, and a fabricated citation
    showing ⚠ (§5 last para, §6) — is only 'verified in the browser' manually. No
    automated test exercises the `chat.js` DOM wiring; vitest covers only the pure
    `citationReport` return value. The acceptance criteria are therefore not enforceable
    in CI and can silently regress.
  status: accepted
  disposition_reason: null
- issue_id: I-004
  category: undefined
  severity: low
  description: '`citationReport` is specified as a pure module over arbitrary `citations`,
    but behavior is undefined when an item''s `title` is missing/null/empty. `label
    = title (+ '' · ''+section)` would produce `undefined` or ` · section`. Not listed
    in the test matrix (§5). The pure-module contract should define the missing/empty-title
    case.'
  status: accepted
  disposition_reason: null
- issue_id: I-005
  category: undefined
  severity: low
  description: '`section` is ''non-empty'' vs ''absent/empty'' drives label formatting
    (§3, §5), but ''non-empty'' is not defined for a whitespace-only or non-string
    section — is it trimmed before the check? The test says ''absent/empty ⇒ label
    === title'' without pinning whitespace semantics.'
  status: accepted
  disposition_reason: null
- issue_id: I-006
  category: missing-invariant
  severity: low
  description: 'No dedup invariant. `validate_citations` uses `finditer`, so an LLM
    repeating the same `[출처: X]` yields duplicate Citation entries; `citationReport`
    maps 1:1, so `total`/counts double-count and the strip shows the same chip twice.
    The SPEC neither dedups nor states that duplicates are intentional.'
  status: accepted
  disposition_reason: null
- issue_id: I-007
  category: unverifiable-claim
  severity: low
  description: The claim that deriving counts from `items` means 'the summary can
    never contradict the per-item badges' (§3) is asserted but not backed by any listed
    test. The tests check `unverifiedCount`/`tone`, but none asserts that the numeric
    M/N interpolated into the Korean `summary` STRING equals `verifiedCount`/`unverifiedCount`
    — so the 'never contradict' guarantee is unverified.
  status: accepted
  disposition_reason: null
approved_by: LivingLikeKrillin
approved_at: '2026-07-12T05:53:06Z'
---

