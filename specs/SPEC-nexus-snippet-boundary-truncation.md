---
id: SPEC-nexus-snippet-boundary-truncation
type: spec
title: Evidence snippets truncate at a sentence boundary, not mid-sentence
status: approved
linked_adrs:
- ADR-0004
tags:
- nexus
- search
- evidence
- faithfulness
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-11T19:50:25Z'
content_hash: sha256:cce2e9c913f2ea90dc0bc2b015c478150849688ebfc299fd72a22ff8e5022016
---

## 1. Goal

Stop the evidence snippet from being cut **mid-word / mid-sentence**. Today `_enrich_hits` truncates
each chunk to a hard 300 characters (`chunk_text[:300] + "..."`): for **any** chunk longer than 300
chars whose sentence spans character 300, the snippet is severed mid-sentence — a certainty for such
chunks, not a measured rate. That severed snippet is what the answer is built on and what a reader
sees. Cut at a sentence (or at worst a word) boundary instead.

This snippet is **dual-mode** (ADR-0004): the same `SearchHit.snippet` feeds the LLM's grounding
prompt **and** the human surfaces — the `/search` and `/search/answer` responses, the web chat
evidence list, and the Slack Block-Kit reply. A clean boundary improves both the agent's faithfulness
and the human's readability; it is not an LLM-only concern.

## 2. What exists

- `search/hybrid.py:256`: `snippet = r["chunk_text"][:300] + "..." if len(...) > 300 else
  r["chunk_text"]`. The result is `SearchHit.snippet` → `EvidenceSnippet.text` → `format_for_llm`
  (`evidence_packet.py:106`, LLM prompt) **and** the `evidence_snippets`/`text` fields returned by the
  answer endpoints and rendered by the web chat and the Slack formatter. This is the only cut; every
  consumer sees its output.
- Retrieval (which chunks match/rank) is entirely upstream of this; the snippet text is display/LLM
  input only. So this change **cannot affect recall or ranking** — it only changes the *text* of an
  already-selected hit.

## 3. Non-goals

- **Changing which chunks are retrieved or how they rank.** Untouched; the recall harness is
  unaffected by definition (snippet text ≠ retrieval).
- **Re-tuning the window.** The max becomes config-tunable (`search.snippet_max_chars`) and the
  default **stays 300**, so behaviour changes only at the cut point; deciding a larger default is a
  separate call, not made here.
- **Semantic/sentence-segmentation models.** A lightweight boundary scan, not an NLP segmenter.

## 4. Design

A pure `_truncate_snippet(text: str, max_chars: int) -> str`, an **exhaustive** ladder that keeps as
much content as possible while never severing a word:

1. `len(text) <= max_chars` → return unchanged (no ellipsis).
2. Within `text[:max_chars]`, find the last **real** sentence terminator — `. ! ? 。` **immediately
   followed by whitespace or the window end** (the whitespace lookahead excludes intra-token dots like
   `3.14`, `v2.3`, `1.5M`, `1.1` — I-003). If one exists **at or past `0.7 × max_chars`** (near the
   end, so we cut back only a little — I-002 keeps most of the window), cut just after it; extend the
   cut past any immediately-following closing punctuation `" ' ) ] 」 』` (I-010); append ` …`.
3. Else fall back to the **last whitespace anywhere in `text[:max_chars]`** — a word boundary near the
   window end, preserving ≈`max_chars` of content and never cutting a word. Append ` …`.
4. Else (no sentence terminator near the end **and** no whitespace at all — a single long token) hard
   cut at `max_chars` + ` …`. Strictly no worse than today, and rare.

The ladder never returns *less* content than a word-boundary cut near `max_chars` unless a clean
sentence end sits in the last 30 % of the window — so it does not trade away context for tidiness
(I-002). `_enrich_hits` calls `_truncate_snippet(r["chunk_text"], max_snippet_chars)` with
`max_snippet_chars` from `config.yaml` (`search.snippet_max_chars`, default 300) threaded from
`hybrid_search`.

## 5. Error handling / invariants

- Output length ≤ `max_chars + C`, where `C` is a small constant: the boundary is always found within
  `text[:max_chars]`, and the only content kept *beyond* the cut index is the run of immediately-
  following closing punctuation (step 2), a handful of chars, plus ` …`. It never returns more than the
  original text (I-001 — no "plus a whole sentence" beyond the window; the earlier wording was wrong).
- Empty/short text (`≤ max_chars`) passes through unchanged, no ellipsis.
- Pure function, no I/O.

## 6. Testing

- Text ≤ max → unchanged, no ellipsis.
- Text with a sentence boundary before `max_chars` → cut just after that boundary (not at `max_chars`),
  ` …` appended, no mid-sentence sever.
- Text whose only boundary is very early (< half) → falls back to a word boundary, not the early
  sentence cut (we don't lose most of the snippet).
- Text with no boundary and no space in range (one long token) → hard-cut at `max_chars` + ` …`
  (graceful worst case).
- A Korean sentence ending in `다.` truncates after the period, not inside the preceding word.
- `_enrich_hits` uses the configured `snippet_max_chars` (a small DB-backed or unit check that a long
  chunk comes back cut at a boundary, ≤ the configured length + ellipsis).

## 7. Acceptance

An evidence snippet — as seen by the LLM **and** by a human on the web/Slack/API surfaces — ends at a
sentence boundary, or a word boundary when no clean sentence end sits near the window's end; only the
rare single-token-with-no-whitespace case falls back to a hard cut (no worse than today, I-005). It is
no longer severed mid-word/mid-clause, so the model narrates from — and a reader sees — complete
statements. Retrieval, ranking, and recall are unchanged (snippet text is not a retrieval input). The
window is config-tunable (`search.snippet_max_chars`), default 300.
