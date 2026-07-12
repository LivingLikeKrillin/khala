---
id: SPEC-nexus-web-citation-verification
type: spec
title: Web chat renders citation verification (verified / unverified)
status: approved
linked_adrs: []
tags:
- nexus
- web
- faithfulness
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-12T05:53:06Z'
content_hash: sha256:2b2480464798fd44d777593d3453d3bef3b99509a53e2d3c324c79de7dfb9c91
---

## 1. Goal

The streaming answer's `done` event already carries `citations` (`[{title, section, verified}]`) and
`unverified_citations` (count) — the faithfulness signal built in PR #134/#136. The web chat's
`onDone(data)` handler **ignores them**. So when the LLM cites a source whose title does not match any
evidence snippet the model was shown, the user sees nothing. Surface it: render, under each answer, each
cited source with a verified / unverified marker and a one-line summary.

Scope is the **presentation layer only** — no backend, no API, no ranking change. (The `doc_type` trust
badge already renders per evidence snippet via `doctype-signal.js`/#59; this SPEC adds the orthogonal
**citation-verification** strip on the answer itself.)

## 2. What exists

- `llm/citations.py::validate_citations`: `verified=True` **iff** the cited title, normalized
  (`_norm` = trim + collapse-spaces + lowercase), **exactly matches** a `packet.snippets[*].doc_title`.
  So `verified=False` means "the cited title does not match any evidence-snippet title shown to the
  LLM" — a hallucinated source, or (less often) a real source whose title the LLM reworded. The correct
  user-facing wording is therefore **"근거에서 확인 안 됨"** (not confirmed against evidence), **not**
  the stronger "근거에 없음". Entailment (right title, wrong claim) is explicitly out of #134's scope.
- `api.py` stream `done` event: `citations: [{title, section, verified: bool}]`,
  `unverified_citations: int` (`api.py:870`).
- `web/js/views/chat.js` `onDone(data)` (`chat.js:295`) finalizes the bubble and **drops**
  `data.citations`. `chat.js` also holds `fullAnswer` (accumulated stream text) and `escapeHtml`.
- Pattern: pure display module + vitest (`freshness.js`+`freshness.test.js`, `doctype-signal.js`); DOM
  wiring lives in `chat.js` and is browser-verified — `package.json` states this convention explicitly.

## 3. Design

New pure module `web/js/citations.js` exporting `citationReport(citations)`:

- Not an array, or empty ⇒ returns `null` (no strip). See §4 for what this deliberately does *not* try
  to detect.
- Otherwise, first **dedupe** by final `label` (an LLM repeating `[출처: X]` yields duplicate entries
  via `finditer`): keep one entry per label; if duplicates disagree on `verified`, the merged entry is
  **unverified** (conservative). Then return `{ total, verifiedCount, unverifiedCount, tone, summary,
  items }`:
  - `items[i] = { label, verified }`.
    - `verified = c.verified === true` — a missing/`undefined`/non-`true` flag counts as **unverified**;
      a trust marker is never shown for something not explicitly verified.
    - `label`: `title` when `section` is empty, else `` `${title} · ${section}` ``. `title` is
      `String(c.title ?? '').trim()`; if that is empty ⇒ `(제목 없음)` (matching the evidence panel's
      fallback). `section` is appended only when `typeof c.section === 'string'` and its trim is
      non-empty; the trimmed value is used.
  - `verifiedCount` / `unverifiedCount` are `items.filter(...).length` over the **deduped** items — the
    single source of truth, so the summary count and the per-item markers are computed from the same
    array (tested in §5).
  - `tone = unverifiedCount > 0 ? 'warn' : 'ok'`.
  - `summary` (Korean): ok ⇒ `출처 N개 — 모두 근거에서 확인됨`; warn ⇒
    `출처 N개 중 M개가 근거에서 확인 안 됨` (`N = total`, `M = unverifiedCount`).

`chat.js` `onDone` calls `citationReport(data.citations)`; when non-null it renders a `.citation-strip`
appended inside the assistant bubble: the toned (`--ok`/`--warn`) `summary` line plus one
`.citation-chip` per item with a `✓` (verified) / `⚠` (`.citation-chip--unverified`) marker and the
`label`. `label`s come from **document content (untrusted)** → escaped via the existing `escapeHtml`,
exactly as evidence titles already are. `style.css` gains `.citation-strip`,
`.citation-strip--ok/--warn`, `.citation-chip`, `.citation-chip--unverified`, reusing existing
trust-badge tone variables (no new palette).

## 4. Non-goals

- **Flagging a fully un-cited answer.** An LLM answer that streams real prose but emits **zero**
  `[출처:]` markers is also a faithfulness concern, but distinguishing it from the benign
  evidence-only / LLM-not-configured / llm-failed paths (all of which also yield zero citations)
  requires a backend "an answer was produced" signal the `done` event does not carry. Adding that is a
  **follow-up**; this SPEC stays presentation-only and shows nothing when there are no citations.
- **Backend / API / signal changes** — the `done` event already carries the citations; `search_log`
  fabrication-rate (#136) is untouched.
- **Entailment / claim-level checking** — verification stays title-match, exactly as #134 defined; this
  SPEC only *shows* that result.
- **The `doc_type` trust badge** (#59) and the **non-stream `/search/answer`** renderer — orthogonal /
  out of scope.

## 5. Testing

`citations.test.js` (vitest, pure — the full contract of `citationReport`):

- `null` / `undefined` / `[]` / non-array ⇒ `null`.
- All `verified:true` ⇒ `tone:'ok'`, `unverifiedCount:0`, `total` correct, every item `verified:true`,
  ok summary names `total`.
- Mixed ⇒ `tone:'warn'`, correct `unverifiedCount`, warn summary names `M = unverifiedCount`.
- **Count/summary agreement invariant:** for a mixed input, the `M` in `summary` equals
  `items.filter(i => !i.verified).length` equals `unverifiedCount` (guards the "cannot contradict"
  claim).
- `verified` missing / `undefined` / `false` ⇒ that item is unverified.
- Dedup: the same `[출처: X]` repeated ⇒ one item; a verified+unverified collision on one label ⇒
  merged item is unverified.
- `label`: `section` non-empty string ⇒ `` `${title} · ${section}` ``; empty/whitespace/non-string
  section ⇒ `label === title`; empty/missing `title` ⇒ `(제목 없음)`.

DOM wiring (`chat.js`, `style.css`) is verified **in the browser** (repo convention): ask a question,
confirm the strip appears beneath the answer with the right tone, a `✓`/`⚠` per citation, and that a
citation whose title is absent from the evidence shows `⚠` + the warn summary; ask something with no
answer and confirm no strip.

## 6. Acceptance

`citationReport` satisfies the §5 contract. In the browser, after an answer streams, the chat shows
beneath it each cited source with a verified/unverified marker and a one-line summary; if any citation
is not confirmed against the evidence the strip reads as a warning; when the answer cited nothing, no
strip appears; labels are HTML-escaped. No backend or ranking behaviour changes.
