---
id: SPEC-nexus-answer-staleness-warning
type: spec
title: Deterministic staleness warning on answer evidence (Unit 1, backend)
status: approved
linked_adrs: []
tags:
- nexus
- governance
- faithfulness
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-14T07:36:51Z'
content_hash: sha256:9a1e2fa0f133940266062a45cf5df2bc47d8c70bdbd03e2be98e9336ba1f3c3c
---

## 1. Goal

Semantic retrieval ignores time: an answer can rest on a document that is *current* (not superseded) but
**stale** — older than it should be for its kind — with no signal to the user. This session's deep
research found no OSS RAG shipping an answer-time staleness warning (directional); it is khala's
differentiation bet. Unit 1 is the **deterministic backend**: carry each evidence document's timestamp
through to the answer, judge it against a per-`doc_type` freshness TTL from config, and surface
**per-snippet staleness + an answer-level count** on `AnswerResult` and the `/search/answer` responses.
Web badges/strip = **Unit 2**.

**Honest strength of the signal (I-001):** because the timestamp is `updated_at` (ingest time), this is
a **conservative lower bound** — it reliably flags documents that have *not even been re-ingested* within
their TTL (unambiguously old), but **under-warns** a document that was re-synced without a content change
(its `updated_at` looks fresh though the text is stale). That error direction is the safe one
(**miss, not false-accuse**); catching the re-synced-but-stale case needs a content/review timestamp,
the documented upgrade path (§4).

This is **orthogonal to supersession**: supersession *excludes* the old *version* from search; staleness
*warns* that a still-current document has aged past its type's expectation. Both are needed. No LLM
judgment — the system decides deterministically from timestamps.

## 2. What exists

- `documents.updated_at` (TIMESTAMPTZ) — the chosen freshness signal. **Documented limitation:** it is
  *ingest* time, not content-authored or human-reviewed time (a Notion re-sync refreshes it even if the
  text is old). Better signals (`origin_last_edited` lives only in frontmatter, not a column; a
  `last_verified` review date does not exist) are deferred (§4).
- `SearchHit` / `EvidenceSnippet` carry `doc_type` (#59) but **no timestamp** — the retrieval→packet→
  answer chain drops `updated_at`; Unit 1 must thread it.
- `answer.py::generate_answer` builds `result.evidence_snippets` (dicts with `doc_type`, no timestamp).
- Real `doc_type` values are mostly generic (`wiki`, `markdown`) with governance types (`ADR`,
  `RUNBOOK`, …) where classified — so the config's `default` TTL is load-bearing, not an edge case.
- `web/js/freshness.js` renders corpus ingest-recency (a display primitive Unit 2 will reuse).

## 3. Design

- **Config** — `config.yaml` `staleness.ttl_days: {ADR: 365, DESIGN: 365, RFC: 365, PRD: 180,
  RUNBOOK: 90, POSTMORTEM: 180, NOTE: 730, default: 365}` (days). A doc_type mapped to `null` (or a
  `null` default) means **no TTL → never stale** for it.
- **Pure** `staleness(updated_at, doc_type, now, ttl) -> {age_days: int|None, ttl_days: int|None,
  stale: bool}` (in `nexus/documents/staleness.py`, never raises). Both `updated_at` and `now` are
  **tz-aware UTC** datetimes (`documents.updated_at` is `TIMESTAMPTZ` → asyncpg returns aware; `now =
  datetime.now(timezone.utc)`). A naive `updated_at` is coerced to UTC before subtracting so mixing
  never raises (I-004).
  - `ttl_days = ttl.get((doc_type or "").upper(), ttl.get("default"))` — a `None`/empty `doc_type`
    (EvidenceSnippet default is `""`) falls to `default`; never `.upper()` on `None` (I-002). If the
    resolved value is absent, `None`, non-int, or **`<= 0`** ⇒ treated as **no TTL → `stale=False`**
    (a zero/negative TTL is invalid config, not "everything stale") (I-006).
  - `updated_at is None` ⇒ `age_days=None`, `stale=False` — **unknown age is not stale** (don't accuse
    without a timestamp).
  - else `age_days = max(0, (now - updated_at).days)` (future/clock-skew ⇒ 0, never negative).
  - `stale = ttl_days is not None and age_days is not None and age_days > ttl_days`.
- **Pure** `annotate_staleness(snippets, now, ttl) -> (annotated, n_stale)`: each snippet dict carrying
  `updated_at` + `doc_type` gets a `"staleness"` sub-dict from the function above; returns the list plus
  the count of `stale` ones. Deterministic; empty ⇒ `([], 0)`.
- **Thread the timestamp:** `_enrich_hits` SELECT adds `d.updated_at`; `SearchHit.updated_at:
  datetime|None`; `EvidenceSnippet.updated_at`; the `evidence_snippets` dict in `generate_answer` gains
  `updated_at` (ISO string) + the `staleness` sub-dict.
- **Wire:** `generate_answer` loads the TTL (`_load_staleness_ttl()` from config; on a missing/malformed
  section it returns `{}` **and logs a warning** so the feature turning off — everything never-stale —
  is visible, not silent (I-003)), calls `annotate_staleness` with `datetime.now(timezone.utc)`, sets
  `AnswerResult.n_stale`. `/search/answer` response + stream `done`
  event carry `n_stale`; the evidence snippets (sync response + stream evidence event) carry the
  per-snippet `staleness`.

## 4. Non-goals

- **Unit 2** — web staleness badges on evidence + an "N stale sources" answer strip (reuses
  `freshness.js`). Separate SPEC.
- **Better freshness signals** — `origin_last_edited` as a queryable column, or a `last_verified` /
  review-by governance date. Deferred until "ingest ≠ review" is a demonstrated problem; `updated_at` is
  the honest first cut.
- **Staleness-based down-ranking** — this SPEC *warns* only; letting staleness alter retrieval order is a
  ranking change (needs recall-harness watch) and a later decision. "System decides, surfaces; does not
  silently re-rank."
- **Auto-review workflows / staleness in `search_log`** — Steward surface / signal follow-ups.

## 5. Testing

Pure (`staleness`, `annotate_staleness`; no DB/LLM):

- Fresh doc (`age < ttl`) ⇒ `stale False`; aged doc (`age > ttl`) ⇒ `stale True` with right
  `age_days`/`ttl_days`.
- Unknown `doc_type` ⇒ uses `default`; a type whose TTL is `null` (or `null` default) ⇒ never stale.
- `updated_at None` ⇒ `age_days None`, `stale False` (unknown ≠ stale).
- Future `updated_at` (clock skew) ⇒ `age_days 0`, not stale.
- Case-insensitive: `doc_type` `"adr"` resolves the `ADR` TTL.
- `annotate_staleness`: mixed fresh/stale list ⇒ correct per-snippet `staleness` + `n_stale`; empty ⇒
  `([], 0)`.

Wiring — driving the real `generate_answer` path with a fake backend and a packet whose snippets carry
`updated_at` (as #139/#140 did): a snippet older than its type's TTL yields `staleness.stale True` in
`evidence_snippets` and increments `AnswerResult.n_stale`; a recent one does not.

**Integration (`pytest.mark.integration`, DB 5433, I-005):** insert a document with a controlled
`updated_at` + one active embedded chunk, run `_enrich_hits` (or `hybrid_search`) and assert the returned
`SearchHit.updated_at` equals the stored value — covering the SQL SELECT thread that the pure tests
cannot.

## 6. Acceptance

Each answer's evidence snippets carry a deterministic `staleness` verdict (age vs the doc_type's config
TTL; `updated_at`-based, with the documented ingest-time caveat), and `AnswerResult.n_stale` (+ the
`/search/answer` and stream responses) reports how many cited sources are past their freshness TTL.
Unknown ages and untyped/`null`-TTL docs are never flagged stale. Nothing is re-ranked or excluded;
staleness is orthogonal to supersession. No LLM judgment; deterministic and pure where it counts.
