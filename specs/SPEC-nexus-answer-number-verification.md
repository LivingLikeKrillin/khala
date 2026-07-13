---
id: SPEC-nexus-answer-number-verification
type: spec
title: Deterministic verification that answer numbers appear in the evidence
status: approved
linked_adrs: []
tags:
- nexus
- llm
- faithfulness
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-13T07:26:55Z'
content_hash: sha256:c003182e406b41c2e77fb3c4ea455a8fa987149aabfc45e20662ef71c839d937
---

## 1. Goal

#134 checks that each `[출처: …]` the LLM emits names a real evidence title. It does **not** check the
**numbers** in the answer. An LLM can state a precise, authoritative-looking figure — `47%`, `250ms` —
that never appeared in the evidence or the question it was given. That is a distinct, common
faithfulness failure (fabricated statistics). Add a **deterministic** check: extract the significant
numbers from the answer and verify each appears in what the LLM was shown. The idea is drawn from
LLMware's deterministic `evidence_check_numbers` (per 2026 OSS survey; the mainstream RAG-eval
libraries do faithfulness by LLM-judge, not a deterministic numeric check) — khala's implementation here
is independent and fits its "System decides, LLM narrates" stance.

## 2. What exists

- `llm/citations.py::validate_citations(answer, packet)` — the #134 title-existence check
  (`answer.py:116`).
- `answer.py::generate_answer` computes `evidence_text = format_for_llm(packet)` (`answer.py:107`) and
  has the user `query` in scope. Together these are what the LLM was shown. `format_for_llm`
  (`evidence_packet.py:93`) injects numbers **beyond snippet bodies**: `confidence` as `{:.2f}`
  (`0.85`), `error_rate` as `{:.2%}` (`5.00%`), `call_count`, `latency_p95` (`120ms`). So the grounding
  set MUST come from the full `evidence_text` **and** the `query`, not just `snippet.text` — else a
  legitimately-grounded graph figure or a number the user typed would be falsely flagged (I-001).
- The stream path (`api.py`) also has `query` and builds `evidence_text = format_for_llm(packet)`.

## 3. Design

New pure module `llm/numbers.py`, `validate_numbers(answer_text, evidence_text, query="") -> NumberReport`
(pure, never raises — same contract as `citations.py`):

- **Pre-strip version-like tokens (I-005):** before extraction, remove substrings matching
  `\d+(?:\.\d+){2,}` (two-or-more dotted segments — versions, IPs, `3.2.1`) from *both* answer and
  grounding text, so they never become numbers.
- **Extract** numeric tokens with one regex: optional currency (`$₩`), digits with optional thousands
  separators, optional single decimal, optional immediately-adjacent trailing `%`. A trailing sentence
  period is not part of the number (`점유율은 47.` → `47`). A **leading sign is not captured** (magnitude
  only: `-5`→`5`); a range `3-5` yields `3` and `5` separately (I-007); `%` counts only when adjacent —
  `47 %` (with space) extracts the bare `47` (I-008, documented).
- **Canonicalize** by numeric value, **keeping the percent class distinct (I-002):** strip commas /
  currency / spaces; strip trailing zeros in any decimal part and a bare trailing dot; **if the token
  carried `%`, append a `%` marker to the canonical form.** So `5.00%`→`5%`, `5%`→`5%` (but `5`→`5`,
  a *different* class); `0.50`→`0.5`, `1,000`→`1000`, `3.140`→`3.14`, `120ms`→`120`, `0.85`→`0.85`. A
  percentage thus grounds only against a percentage, never against the bare integer. **Only `%` is
  class-separated (I-006)** — it is pervasive and graph-injected; other trailing units (`ms`, `원`, `배`)
  fall outside the numeric token and are treated dimensionless, so a fabricated `120 요청` grounding
  against evidence `120ms` is a documented miss.
- **Grounding set** = canonicalized set of all numbers in `evidence_text` **∪** `query`. Including
  `query` is intentional (I-001): a figure the user typed is by definition available to the model, so
  echoing it is not fabrication.
- **Answer numbers to check** = the **significant** ones only, significance evaluated on the
  **canonical** form (I-002): significant iff the canonical ends in `%`, **or** contains a `.` (a
  genuine fraction survives trailing-zero strip — `5.0`→`5` is *not* significant, `0.85` is), **or** its
  integer value ≥ 10. Bare `0`–`9` (no `%`/decimal) are skipped.
  This is a deliberate **conservative scoping choice**, not a proven optimum: it excludes the dominant
  false-positive class (small derived counts like "3 services") at the known cost of **also not
  catching fabricated small integers**. The ≥10 boundary is a heuristic (§4 records the tradeoff).
- **Dedup:** report each **distinct canonical** significant answer number once; `value` is the first
  surface form seen. Invariant (I-009): `unverified_count == len([n for n in numbers if not
  n.grounded])`.
- Grounded iff canonical ∈ grounding set; else unverified.
- `NumberReport(numbers: list[NumberCheck], unverified_count: int)`,
  `NumberCheck(value: str, grounded: bool)`.

**Framing — signal, not verdict.** Like #134's unverified citations, an unverified number is a
*calibration warning*, not a "fabricated" judgment.

**Error profile, asymmetric by construction (I-003, I-004):** value-equality matching + the significance
filter make the design favour **false negatives over false accusations** — this is a structural property
of the algorithm, not a tuned metric. A fabricated value that coincidentally equals *any* number anywhere
in the grounding text is called grounded (a miss). Residual **over**-flag
cases exist and are documented: a grounded figure written with a Korean scale word (`1.5천`, `3억`)
canonicalizes to `1.5`/`3` and won't match evidence `1500`/`300000000` → may be flagged. Both directions
are bounded by "value-presence, not semantics" and surfaced as a soft signal, never a block.

**Wiring (scope-tight, I-008):**
- `AnswerResult` gains `numbers: list[dict]` and `unverified_numbers: int` (default `0`).
- `generate_answer` calls `validate_numbers(result.answer, evidence_text, query)` right after
  `validate_citations`.
- `/search/answer` response and the stream `done` event carry only the **count** `unverified_numbers`
  (mirroring `unverified_citations`). The full `numbers` list stays on `AnswerResult` (in-process) until
  a renderer needs it — deferred with the web work below.

## 4. Non-goals

- **Search-log signal / fabrication-rate metric for numbers** — deferred to a #136-style follow-up
  (schema change); this SPEC adds the check + count surfacing only, as #134 preceded #136.
- **Web rendering** of the numeric warning, and putting the `numbers` list on the wire — follow-up.
- **Catching fabricated small integers** — excluded by the significance filter (documented tradeoff).
- **Korean numeral / scale words** (`삼십`, `3천`, `2배`) — only Arabic-numeral tokens; mixed
  Arabic+scale (`1.5천`) is a documented over-flag residual.
- **Unit/semantic/percent-fraction equivalence** — `5%` is not reconciled with the fraction `0.05`; we
  verify value-presence within its class, not meaning. Same entailment boundary as #134.

## 5. Testing

`test_numbers.py` (pure, no DB/LLM):

- Significant answer number present in `evidence_text` → grounded; absent → unverified, count incremented.
- **Query grounding:** a number present only in `query` (not evidence) → grounded (I-001).
- **Percent class (I-002):** answer `5%` grounded by evidence `5.00%`; answer `5%` **not** grounded by
  an evidence that only has bare `5`; `0.85` grounded by `confidence 0.85`; `1,000` by `1000`; `120ms`
  by `120`.
- **Significance filter:** bare `3` (no evidence `3`) → **not** flagged; `47` (≥10) absent → flagged;
  `3.14` absent → flagged; `50%` absent → flagged.
- **Version exclusion (I-005):** `버전 3.2.1` contributes no checked number.
- **Dedup (I-006):** `47%` thrice unverified → one entry, `unverified_count == 1`.
- **Coincidental collision (I-004, documented miss):** answer `47%` with evidence containing an
  unrelated `47%` elsewhere → grounded (asserts the known false-negative behavior).
- Trailing period `점유율은 47.` → `47`. Empty answer / no significant numbers → empty report, count 0.
- Never raises on `"버전 3.2.1"`, lone `%`, `"1,,2"`.

## 6. Acceptance

When an answer states a significant number (percentage, decimal, or integer ≥10) that appears neither in
the evidence the LLM was shown nor in the question, `validate_numbers` reports it unverified and counts
distinct such numbers; numbers that do appear (including graph-injected `confidence`/`error_rate`/
`latency` and query numbers) are grounded, with percentages matched only against percentages. Bare small
counts are not checked. The check is deterministic and pure, with an error profile that structurally
favours false negatives over false accusations (accepting the documented false-negative and
Korean-scale-word residuals), and surfaced as a count on `AnswerResult`
and the `/search/answer` + stream responses alongside the citation fields. No LLM judgment is involved.
