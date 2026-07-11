---
id: SPEC-nexus-citation-validation
type: spec
title: Verify the LLM's citations against the evidence — the code checks, it doesn't
  trust
status: approved
linked_adrs:
- ADR-0004
- ADR-0006
tags:
- nexus
- llm
- faithfulness
- grounding
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-11T18:28:07Z'
content_hash: sha256:9dd75a09314bd8884c8addb7db5e263556e16d810f4526238abdab488567c776
---

## 1. Goal

Make Nexus **verify** the `[출처: …]` citations the LLM emits against the evidence it was actually
given, instead of trusting them. Today the citation is free text the model writes; nothing reconciles
it against the packet, so a citation to a **source that was never in the packet** ships as if
grounded. This is the "System decides, LLM narrates" principle applied to citations: the *system*
decides whether a cited source exists in the evidence; the LLM only proposes it.

Precisely: this catches a citation whose **title is not among the snippets shown** (a fabricated /
non-existent source). It does **not** catch a *real* title cited for a claim it doesn't actually
support — that is claim-level entailment (§2, non-goal). The win is closing the "the source doesn't
even exist" hole, which is the one a title check can decide deterministically.

## 2. Non-goals

- **Claim-level entailment (NLI).** Checking that each *sentence* is entailed by the evidence is a
  much larger, model-dependent problem. This SPEC validates citation **existence/attribution** — that
  a cited title corresponds to a snippet actually in the packet — not semantic entailment.
- **Rewriting the LLM's prose.** The answer text is not mutated (silently editing a model's output is
  its own faithfulness risk). Validation is **surfaced** alongside the answer; consumers decide how to
  render an unverified citation.
- **Blocking the answer.** An unverified citation does not fail the request. It is reported (and
  counted as a signal); the grounded-evidence and empty-evidence gates are unchanged.
- **Changing retrieval or the prompt's citation instruction.** `prompts.py` already tells the model to
  cite the bracket title; this SPEC checks that it did so truthfully.
- **The `search_log` fabrication-rate signal.** Recording `unverified_citations` as a persisted
  metric needs a `search_log` column (schema migration) and touches `signals.py`'s fixed INSERT, and
  the stream path records no signals at all yet (a separate finding). To keep this SPEC to the
  validator + surfacing, the persisted metric is a **follow-up**, not delivered here. The fields are
  surfaced on the response first; measuring them over time comes next.
- **Extending the A2A answer payload.** Per ADR-0004, A2A stays minimal; this SPEC adds the fields to
  the HTTP `/search/answer` response and the stream event only — not to the A2A card/message shape.

## 3. What exists

- `llm/answer.py::generate_answer` calls `llm_svc.generate(SYSTEM_PROMPT, user_prompt)` and stores the
  raw text in `result.answer` — no post-processing.
- The LLM is instructed (`prompts.py:15`) to cite `[출처: 문서 제목, 섹션]` using the **bracket
  title** from each evidence header, which `format_for_llm` renders as
  `### 근거 {i} [{doc_title}] ({section_path})` (`evidence_packet.py:100`). So the set of *legitimate*
  citation titles is exactly `packet.snippets[*].doc_title` (+ their `section_path`).
- `AnswerResult` (`answer.py:19-27`) already carries `evidence_snippets` and `provenance`; the API
  returns it on `/search/answer` and the stream. `search/signals.py` records per-search signals; the
  stream path currently records none (a separate finding, not this SPEC).

## 4. Design

### 4.1 A pure validator

`validate_citations(answer_text: str, packet) -> CitationReport` in a new
`nexus/llm/citations.py`:

- Extract every `[출처: … ]` bracket from `answer_text`. **Titles can contain commas** (Notion pages,
  filenames — I-002), so the inner text is **not** naively split on the first comma. Instead: build
  the legitimate-title set from `packet.snippets[*].doc_title` (the exact strings the LLM was shown),
  and for each citation's inner text, mark it **verified** iff, after normalization (trim, collapse
  internal whitespace, case-insensitive), some shown title is a **prefix** of it — the remainder
  (after a trailing comma) is then the section. This prefix-against-known-titles match is robust to
  titles with commas, where a first-comma split would guess wrong. No shown title is a prefix →
  **unverified** (a source not in the packet).
- Verification means **title-presence in the packet**, not doc-identity (I-007): if two snippets
  share a title, a citation to it is "present" — the check answers "was a source with this title
  shown?", which is the deterministic question a title match can settle.
- Return `CitationReport(citations: list[Citation], unverified_count: int)` where each `Citation` is
  `{title, section, verified}`. Pure function, no I/O — unit-testable without an LLM.

### 4.2 Wiring

- `generate_answer` runs the validator after a successful `generate()` and attaches
  `result.citations` (the list) and `result.unverified_citations` (the count) to `AnswerResult`. On
  the LLM-failure or empty-evidence paths there is no model answer, so the report is empty.
- The **`/search/answer`** response includes `citations` and `unverified_citations`.
- The **streaming path** (`api.py`, the `event_stream` generator): the streamed `answer_delta` chunks
  are **accumulated** into the full text as they are emitted; after the stream completes, the full
  text is validated against the same packet and the citations + count are emitted in the terminal
  **`done`** event (which already carries `timing_ms`). This is the wiring the web chat consumes —
  the accumulation is the only new logic (validation is the shared pure fn).
- A consumer (web badge) marks which citations are grounded and flags the count. Rendering is a
  follow-up; the two response/event fields are the contract this SPEC delivers.

### 4.3 What a consumer does with it

This SPEC surfaces the verification; it does not dictate UI. The natural use: render verified
citations normally and mark unverified ones (e.g. a "미확인 인용" badge). The persisted
fabrication-rate metric and its health view are the follow-up named in §2 (they need a `search_log`
column). The API contract (the two fields on the response and the `done` event) is what this SPEC
delivers.

## 5. Error handling

- No citations in the answer → empty `citations`, `unverified_count = 0` (not an error; some answers
  legitimately carry none, e.g. the empty-evidence canned string).
- Malformed/partial `[출처:` fragment → parsed leniently; an unparadeable fragment is ignored rather
  than raising (the validator must never crash the answer path).
- Empty packet → validator not run (no model answer to validate).

## 6. Testing

Pure-function tests (`tests/test_citation_validation.py`), no LLM:

- An answer citing a title that **is** in the packet → that citation `verified = True`.
- An answer citing a title that is **not** in the packet (fabricated) → `verified = False`,
  `unverified_count` incremented.
- Case/whitespace-different but real title → verified (normalization, no false positive).
- An answer with **no** citations → empty list, `unverified_count = 0`.
- Multiple citations, mixed real/fabricated → each classified correctly, count = number fabricated.
- A malformed `[출처:` fragment does not raise.
- A cited title that **contains a comma**, present in the packet, verifies (prefix match, not
  first-comma split).
- `generate_answer` attaches `citations`/`unverified_citations` to `AnswerResult` (with an injected
  fake `LLMService` returning a known answer + a stub packet) — the non-stream wiring.
- **Stream wiring:** the `event_stream` generator, driven with a fake LLM that streams a known
  answer, emits the citations + count in its `done` event (accumulation + validation), asserted on
  the captured SSE.

## 7. Acceptance

`/search/answer` (and the streaming `done` event) return, alongside the answer, a `citations` array
marking each `[출처: …]` as verified or not against the evidence packet, plus an
`unverified_citations` count. A model that cites a **source not in the packet** is caught by the
system — that citation is reported as unverified rather than shipped as grounded — without rewriting
the answer or failing the request. The faithfulness gap (citations were unenforced free text) is
closed at the **contract** level: consumers can now tell grounded citations from invented ones. The
persisted fabrication-rate metric over that signal is the named follow-up.
