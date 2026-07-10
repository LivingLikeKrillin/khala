---
id: SPEC-nexus-search-recall
type: spec
title: BM25 recall — the keyword leg answers nothing, and `route` answers nobody
status: approved
date: 2026-07-10
linked_adrs:
- ADR-0004
tags:
- nexus
- search
- correctness
- measurement
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-10T09:18:13Z'
content_hash: sha256:f2125ba577b6a69cce88e651fd7c1652538533497abe0d5debb8791329ec7c08
---

## 1. Goal

Nexus advertises "BM25 + Vector + Graph hybrid search". Measured against a 14-query set on the
live corpus, the BM25 leg returns **nothing at all for 11 of 14 queries**. What ships today is
vector search with a keyword leg that is usually silent.

Fix the recall. Make `route` mean what the API says it means. And leave behind the measurement
that would have caught this years earlier.

## 2. Non-goals

- Reranking, query expansion, synonyms, LLM-assisted retrieval. Those are answers to a question
  we have not earned the right to ask yet.
- Changing the embedding model, the chunker, or `get_search_text()`.
- Fixing Notion document titles (`SPEC` pending, separate).
- A large benchmark. Fourteen queries on twenty documents is small, and this SPEC says so.
- **Grounding correctness.** ADR-0004 §1 draws the line: Nexus grounds in a derived document index
  — a snapshot that can drift — while decision-grade fact-check, freshness and authority belong to
  Archon (`nexus/claims/`). This SPEC moves *recall*: whether the index returns the document that
  contains the words. Whether that document is true, current, or authoritative is not asked here,
  and a better keyword leg does not make it so (I-009).

## 3. What exists

### 3.1 The keyword leg requires every token

```python
def tokens_to_tsquery(tokens: list[str]) -> str:
    return " & ".join(f"'{t}'" for t in safe)      # nexus/index/bm25.py
```

mecab-ko splits `엔티티` into `엔` + `티티`. A document that says `Entity 식별` contains neither.
So `"엔티티를 어떻게 식별하나"` becomes `'엔' & '티티' & '식별'` and matches **zero rows**, even
though `식별` is right there. A five-token question demands all five lexemes inside one chunk.

Measured per leg — 14 queries, `default` corpus of 2026-07-10 (20 documents, 163 chunks), calling
`_bm25_search` / `_vector_search` directly, because §3.2 explains why `route` cannot be trusted to
isolate them:

| leg | misses | top-1 | MRR |
|---|---|---|---|
| BM25 `AND` (today) | **11/14** | 3/14 | 0.214 |
| BM25 `OR` | 0/14 | 10/14 | 0.845 |
| vector alone | 4/14 | 6/14 | 0.538 |

The hybrid only works because the vector leg carries it.

*(An earlier draft of this section reported 10/13 and 0.231. That run used thirteen queries and an
eight-character gold prefix that matched two documents. Both numbers were wrong. §4.3 exists
because of it.)*

### 3.2 `route` is not honoured

```python
bm25_task = asyncio.create_task(_bm25_search(...))          # always
if embedding_svc: vector_task = ...                          # always
if graph_repo and entity_rids and route in ("hybrid_then_graph", "graph_then_hybrid"):
```

`route` gates graph enrichment and nothing else. `keyword_only` and `vector_only` run the exact
same search as `hybrid_only` — and `SearchResult.route_used` reports back the value it was given,
so the caller is told its choice was honoured. The API contract, the MCP tool's docstring, and
the CLI all offer a knob attached to nothing.

This is worse than a missing feature: it silently invalidates any diagnosis made through it. It
invalidated one during this investigation.

### 3.3 There is no retrieval regression test

`tests/` has no query→expected-document assertion anywhere. Nothing would have failed when the
keyword leg went quiet.

## 4. Design

### 4.1 `OR`, and nothing cleverer

`tokens_to_tsquery` joins with `|`.

**Where the ordering comes from, precisely.** Inside the keyword leg, `ts_rank` orders chunks by
how many query lexemes matched and how densely, so a chunk matching four terms outranks one
matching one. That ordering is then *thrown away*: `_rrf_fusion` reads only the rank position, and
credits `1/(k + rank + 1)`. A chunk that matched one lexeme out of five and a chunk that matched
all five are separated by their positions, not by the gap between their scores. RRF is
score-agnostic by construction, and this SPEC does not change it (I-004).

So the claim is narrow: `OR` orders *within* the leg well enough that the right chunk reaches a
high rank position, and that is all RRF needs. Measured, not argued.

**Bounded output** (I-005). The leg already returns at most `search.bm25_top_k` rows (default 20,
`config.yaml`), ordered by `ts_rank DESC`. `OR` widens what *matches*, not what is *returned*. It
cannot flood the fusion; it can only change which 20 arrive.

Measured on the same 14 queries, end to end through `hybrid_search`:

| | top-1 | top-3 | MRR | misses |
|---|---|---|---|---|
| `AND` (today) | 6/14 | 9/14 | 0.524 | 5 |
| `OR` | 7/14 | 11/14 | **0.681** | **0** |

**Improved 6 · unchanged 8 · regressed 0.**

Alternatives were measured on the same corrected set and rejected:

- **Dropping one-character tokens** (`엔`, `있`) before `OR`: *worse.* Fused MRR 0.611 vs 0.681,
  top-1 6/14 vs 7/14, and one query falls out of the top ten entirely. In the keyword leg alone,
  MRR 0.774 vs 0.845. mecab's fragments carry signal we cannot predict by length.
- **`AND`-then-`OR` fallback**: unnecessary. `OR` regressed nothing, so the fallback would exist
  only to defend against a regression that does not occur, at the cost of two query paths forever.

**The honest risk.** Twenty documents, 163 chunks. That is a small corpus, and a corpus ten times
larger may behave differently: with `OR` the keyword leg now answers questions it used to decline,
and RRF cannot tell a one-lexeme match from a five-lexeme one. This SPEC does not pre-emptively
defend against that. It ships the measurement (§4.3) so the day it happens is a failing test, not
a user's complaint.

### 4.2 `route` does what it says

| `route` | BM25 | vector | graph |
|---|:--:|:--:|:--:|
| `keyword_only` | ✓ | — | — |
| `vector_only` | — | ✓ | — |
| `hybrid_only` | ✓ | ✓ | — |
| `hybrid_then_graph` (default) | ✓ | ✓ | ✓ |
| `graph_then_hybrid` | ✓ | ✓ | ✓ |

An unknown value is a `400`, not a silent `hybrid`. Being told "your route was ignored" is worth
more than being told nothing.

`vector_only` with no `embedding_svc` returns no hits and says so in `route_used`; it does not
quietly fall back to BM25 and report `vector_only`.

### 4.3 The measurement stays

`tests/test_search_recall.py` runs against a **fixture corpus committed to the repo**, not the
live `default` tenant. The numbers in §3.1 and §4.1 were measured on a corpus that changes every
time someone syncs Notion; a floor pinned to it would be a floor pinned to nothing (I-011). The
fixture is a small set of documents whose text is in the test file, seeded into a disposable
tenant.

Its assertions, in order:

- **Label integrity first.** Each gold reference must resolve to exactly one document in the
  fixture. Zero or two → the test fails *before* measuring anything.

  This is not defensive decoration. During this investigation a gold id was given as an
  eight-character prefix, `2740c71b` matched two different Notion pages, and the scorer marked a
  correct top-1 answer as a regression. A whole design was nearly built to fix it. A measurement
  whose ruler is wrong is not a weak measurement; it is a fiction.

- **Per-query keyword recall.** For each query, the test names the gold document *and* the lexeme
  it expects to carry the match (e.g. `"엔티티를 어떻게 식별하나"` → `식별`). The assertion is
  that the keyword leg returns that document. There is no appeal to a "content word" — the SPEC
  cannot define one, and mecab is the only thing that decides what a lexeme is (I-002, I-003).

- **Floors.** `MISSES_MAX`, `TOP3_MIN`, `MRR_MIN`, per leg and fused, as constants carrying the
  date and the fixture revision they were measured on. Raising them is progress and the diff says
  so. Lowering them requires saying why in the same commit.

- **`route` is honoured.** Asserted by counting the SQL and embedding calls each route issues — not
  by reading `route_used`, which is exactly the field that lied.

The floors will be recorded when the fixture is built, and this SPEC does not pretend to know them
in advance. What it fixes is that they exist and that a change to them is visible.

## 5. Error handling

- Empty token list → empty tsquery → no BM25 hits (unchanged).

- **`OR` does not widen the injection surface** (I-008), and the reason is the tokenizer, not the
  escaping. `to_tsquery` never sees user text: mecab yields lexemes, and it discards everything
  that is not a word. Observed 2026-07-10:

  | input | tokens |
  |---|---|
  | `'; DROP TABLE chunks; --` | `['drop', 'table', 'chunks']` |
  | `a' \| 'b` | `['a', 'b']` |
  | `foo & bar` | `['foo', 'bar']` |

  A `'` cannot reach the query string because no token ever contains one. The `''` doubling in
  `tokens_to_tsquery` is belt on top of braces, and changing `&` to `\|` touches neither. §6 pins
  this with a test, because the argument rests on mecab's behaviour and mecab could change.

- Unknown `route` → `400 unknown_route`, listing the accepted values.

## 6. Testing

Unit, no DB:

- `tokens_to_tsquery(["엔", "티티", "식별"]) == "'엔' | '티티' | '식별'"`, and a test that fails
  if the joiner returns to `&`, naming the recall it costs.
- mecab discards `'`, `&`, `|` and `;` from a hostile query (§5's table, asserted).
- `route="nope"` → `400 unknown_route`, and the message lists the accepted values.

Against the fixture corpus:

- **The label-integrity gate fires.** Feed it the eight-character prefix that matched two pages;
  the test must fail on the label, not on the recall.
- **Per-query keyword recall**, each with its expected lexeme (§4.3). `"엔티티를 어떻게 식별하나"`
  → the document containing `식별`, from the keyword leg alone.
- **Floors** for misses / top-3 / MRR, per leg and fused.
- **`route` matrix**: `keyword_only` issues one SQL query and zero embedding calls; `vector_only`
  the reverse; `hybrid_only` both; `hybrid_then_graph` both plus graph. Counted at the seams.
- `vector_only` with `embedding_svc=None` returns zero hits (I-010 — this is one assertion, not a
  fallback mechanism; the point is only that it does not silently become a BM25 search).

## 7. Acceptance

The keyword leg finds `Entity 식별` when asked `"엔티티를 어떻게 식별하나"`, and finds the
Cloudflare runbook when asked how to deploy through a tunnel — two of the eleven queries it
answers with silence today. `keyword_only` issues no embedding call. And each of those is a test
that fails before a user does.
