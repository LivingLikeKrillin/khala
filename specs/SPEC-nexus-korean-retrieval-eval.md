---
id: SPEC-nexus-korean-retrieval-eval
type: spec
title: Korean retrieval evaluation set — a tokenizer-neutral ruler on a pinned public
  corpus
status: approved
date: '2026-08-02T09:52:01Z'
linked_adrs:
- ADR-0008
tags:
- nexus
- search
- korean
- measurement
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-02T10:27:36Z'
content_hash: sha256:b72e0008720c27a52c1e3bd0749247751480142bf8d5d1c9475f1c2508373f92
---

## 1. Goal

Khala cannot measure Korean retrieval quality. `tests/test_search_recall.py` is a working
regression guard for our own keyword leg, but it is **unusable as a tokenizer comparator by
construction**: every query pins the lexeme it expects (`"엔티티를 어떻게 식별하나"` → `식별`),
and those lexemes were read off mecab's output. A different tokenizer that shreds the query
differently still scores full marks — nori splits `엔티티` into `엔`/`티티` and passes, because the
verdict hangs on `식별`. Five documents against a retrieval window of twenty makes a miss
arithmetically almost impossible on top of that.

This SPEC builds the missing instrument: **a Korean evaluation set whose verdict is "did the run
return the right document", never "does token X exist"**, on a corpus large enough for words to
collide, with the tokenizer as a swappable part under a *fixed* engine.

It unblocks three decisions that are currently made without evidence:

1. **mecab-ko retention** — today an inheritance, not a finding.
2. **KURE-v1 embedding swap** — no before/after ruler exists.
3. **ADR-0008 §5 resume condition (b)** — "a Korean evaluation set exists that can compare
   tokenizers on Khala's real corpus". §4.1 states precisely how much of that this SPEC delivers,
   and what it does not.

### 1.1 Gate record (I-004)

ADR-0008 §3 requires that the demand-pull gate for this direction be **declared fired by the
director and recorded in the direction's first SPEC** — not argued into existence by the SPEC. This
is that first SPEC, and this is that record:

> **Gate: fired. Declared by LivingLikeKrillin (director) on 2026-08-02**, instructing that the
> Korean evaluation set be built as the next unit of work.

No override is claimed. In particular this SPEC does **not** stretch ADR-0006's entropy/ingestion-
trust override to cover a retrieval-quality instrument — ADR-0008 §3 left that question open and it
stays open. The authority here is the director's declaration above, and nothing else. §1's argument
explains *what* to build; it is not the gate.

## 2. Non-goals

- **No change to retrieval behaviour.** No tokenizer swap, no embedding swap, no ranking change
  ships here: for every input, production returns what it returns today. Unit 4 does add a
  *dependency-injection seam* inside two production files (§4.4, I-010) — a change to the code, not
  to the results. That carve-out is deliberate and named, because "changes nothing" would have been
  false. ADR-0008 §5's backstop lists "a tokenizer change" as a re-read trigger; the seam is not
  such a change, but the run it enables is what would produce one.
- **Reranking, query expansion, synonyms.** Same reason as SPEC-nexus-search-recall §2.
- **Answer quality, faithfulness, citation correctness.** This measures *retrieval*: whether the
  document that contains the answer is returned. Whether the answer is right, current, or
  well-cited is measured elsewhere (#134, #139, #143).
- **LLM-as-judge, in any role, including relevance labelling.** Permanently out — "System decides,
  LLM narrates" (ADR-0002 identity invariant). Labels are written by a person (or an agent under
  human review), reviewable line by line, and committed.
- **Multi-turn evaluation.** The label schema reserves the fields so today's labels survive that
  work (§4.6); the conversational labels themselves belong to `SPEC-nexus-multi-turn-retrieval`.

## 3. What exists, and why none of it answers the question

| artifact | what it is | why it cannot compare tokenizers |
|---|---|---|
| `nexus/tests/test_search_recall.py` | 6 queries, 5 documents, one chunk each | expected lexeme pinned from mecab's output; corpus (5) smaller than the window (20) |
| `nexus/scripts/adr0008_nori_recall.py` | one-off nori run on that same fixture | its own docstring names four confounders; engine and scorer differ (OpenSearch `match`+BM25 vs Postgres `to_tsquery`+`ts_rank_cd`) |
| the live `default` tenant | ~20 documents mirrored from Notion | changes whenever someone syncs; no relevance judgments; not publishable (§4.1) |

There is no query→gold-document label set anywhere in the repository that is independent of the
tokenizer that produced it. That is the whole gap.

One thing the old suite got right and this one must keep: it carries a **negative control**
(`test_and_semantics_would_break_this_suite`) that proves it can fail. ADR-0008 §2.6 named the
absence of exactly that as the reason the nori exploration proved nothing. §6 carries it forward.

Two facts about the code that the design leans on (both point-in-time, 2026-08-02 — §6 makes the
first one enforced rather than assumed, I-014):

- `tokenize_korean()` has exactly **two** call sites — `index/bm25.py:110` (index time) and
  `search/hybrid.py:63` (query time). That is the entire tokenizer seam.
- `config.yaml` `search`: `bm25_top_k: 20`, `vector_top_k: 20`, `final_top_k: 10`.

## 4. Design

### 4.1 The corpus: a pinned public pack, and why not the Notion mirror

**Decision: the primary corpus (Pack A) is a pinned snapshot of the Kubernetes Korean
documentation** (`kubernetes/website`, `content/ko/docs/**`, CC BY 4.0), committed to this
repository with attribution.

Selection rule — deterministic, and applied to the **raw upstream bytes before any transform**
(I-015):

```
repo    kubernetes/website @ b035ea80a2f666e0a60923560984458806788104   (2026-08-01)
paths   content/ko/docs/{concepts,tasks,tutorials,setup}/**/*.md
skip    basename == _index.md
size    raw upstream blob size in [2048, 40960] bytes   (GitHub tree API `size`)
=>      265 documents, ~2.75 MiB   (asserted by the builder, not trusted from this text)
```

The pack's text is then normalised, and the normalisation is part of the rule because the manifest
hashes the *packed* files:

- strip the YAML front-matter block (leading `---` … `---`); keep `title:` as a `# ` heading
- Hugo shortcodes: `{{< … >}}` and `{{% … %}}` open/close tags are removed and their inner content
  kept; a self-closing shortcode is removed entirely
- HTML comments removed; CRLF → LF; trailing whitespace stripped; file ends with one `\n`

The builder writes `manifest.json` (upstream SHA, per-file upstream blob SHA-1 and packed
SHA-256, document count, byte total) and **fails if the count or any hash disagrees with the
committed manifest**. Two people running the builder get byte-identical packs or an error.

Why this corpus:

- **It has the failure modes we are trying to see.** Loanword transcription (`파드`/`Pod`,
  `디플로이먼트`), compound nouns (`스테이트풀셋`, `퍼시스턴트볼륨클레임`), Korean-English mixing in
  one sentence, and spacing variants are not decorations here — they are the whole vocabulary.
  Those are precisely the five strata in §4.2.
- **Words collide.** 265 documents about one system, all reusing the same terms, is exactly the
  condition under which a retrieval miss is possible and therefore informative. Five toy documents
  are not.
- **It is redistributable.** CC BY 4.0, attribution recorded in the pack.
- **It is pinned.** A ruler that moves is not a ruler (SPEC-nexus-search-recall §4.3 learned this
  the expensive way).

**Why not the live Notion mirror, which the earlier note assumed.** *This repository is public.*
The mirror is an organisation's internal documents; committing a corpus — or labels that quote
document titles — would republish them. That is disqualifying regardless of the corpus's technical
merit, and it is the reason the obvious candidate is not the primary one.

**Pack B — a frozen export, not the live tenant (I-003).** §3 disqualifies the live tenant because
it moves, and that disqualification applies to Pack B too. So Pack B is defined the same way Pack A
is: a **local, git-ignored export** (`nexus/tests/eval/local/`) of a *named tenant at a named
moment* — document rid, title, text and content hash written to disk, with its own manifest and
document count. Labels reference the export, never the live table. Only its location and licence
differ from Pack A. A Pack B run whose manifest does not verify is not a result.

**What that means for ADR-0008 §5(b), stated without stretching:**

- Pack A alone yields a **reproducible, auditable verdict on a representative corpus**. Anyone can
  re-run it. That is what makes the tokenizer decision reviewable at all.
- (b) says "on Khala's real corpus". Pack A is not that corpus — it is a public stand-in of the
  same *kind* (Korean technical documentation, loanword-dense). (b) is **fully** satisfied only when
  a Pack B export is labelled and run. This SPEC ships the seam, the export format and the
  protocol; **not** Pack B's labels, which need corpus access.
- A verdict reported from Pack A alone **must say so in the report header** and must not be cited
  as closing (b). Under-claiming is cheap; this question has already reversed itself twice.
- If Pack A and Pack B disagree, that disagreement is the finding. They are not averaged.

### 4.2 The labels

**45 labelled queries**: 40 answerable across five failure-mode strata (8 each), plus 5
unanswerable. Forty is a **pragmatic starting size, not a powered sample** (I-012): it is what the
verdict rule in §4.3 is built to be honest about — that rule can return "no measurable difference"
and often will. A hundred labels would delay the instrument's existence by the length of the
labelling; growing the set later is cheap and the schema makes added labels non-invalidating.

Strata, one per known Korean failure mode:

| stratum | what it stresses | example shape |
|---|---|---|
| `loanword` | transcription variants | query says `파드`, document says `Pod` (or the reverse) |
| `compound` | compound-noun segmentation | `퍼시스턴트볼륨클레임을 어떻게 만드나` |
| `particle` | particle attachment (`을/를/으로/에서`) | the same noun in four case forms |
| `mixed` | Korean-English in one query | `노드에 taint 를 어떻게 거나` |
| `spacing` | spacing variants | `스테이트풀 셋` vs `스테이트풀셋` |

Label file (`nexus/tests/eval/ko/labels.yaml`) carries a **revision** and a list of records:

```yaml
revision: 1                      # bumped whenever any record changes; floors cite it (§4.5)
pack: ko-k8s-2026-08-01
queries:
  - id: q014
    query: "파드가 계속 Pending 상태면 어디부터 보나"
    stratum: loanword
    answerable: true
    gold: [tasks/debug-application-cluster/debug-pods.md]   # pack-relative paths
    rationale: "파드 Pending 원인 진단 절차가 이 문서의 본문 전체다"
    provenance: authored_from_doc                            # | adjudicated
    # reserved for SPEC-nexus-multi-turn-retrieval, absent today:
    # context: [...]   prior turns
```

Rules that make it a ruler rather than a wish:

- **No token, lexeme, or morpheme field exists in the schema, at any level.** A test fails if such a
  key appears (§6). This makes the *recorded* defect — a pinned expected lexeme — unrepresentable.
  It does **not** stop a labeller from choosing gold by looking at what mecab retrieves; §5 says so
  plainly instead of crediting the ban with more than it buys (I-013).
- **Gold is a set of pack-relative paths**, never a prefix. Each must resolve to exactly one
  document in the pack — zero or two fails the run *before* any metric is computed (an
  eight-character prefix matching two pages once turned a correct top-1 into a "regression").
- **Queries are authored from the document side, then de-lexicalised.** Pick a document, write the
  question a person would actually type — and it may **not** reuse the gold document's title or any
  of its headings verbatim. That last rule is machine-checked (§6): no gold document's title or
  heading may appear as a substring of the query, after whitespace normalisation. The rest of the
  authoring discipline is process, not mechanism, and §5 records it as such.
- **Pooled adjudication, before the floors exist.** Author-side gold under-counts: a run returning a
  different but equally relevant document would be scored wrong. So during Unit 3, the union of the
  **top-5 of every leg of every configuration in the pool** is collected per query, each pooled
  document is judged by reading it, and relevant ones join `gold` with `provenance: adjudicated`.
  Adjudication is part of *building* the set: it completes, the label revision is stamped, and only
  then are floors recorded (I-006).
- **Pool membership is a property of the report, and later configurations must re-pool** (I-005).
  TREC pooling favours the systems in the pool. mecab and nori are pooled together, so neither is
  favoured over the other — but a configuration that was **not** in the pool (the KURE-v1 run of
  §4.6, most obviously) is systematically penalised, because documents only it finds are unjudged
  and therefore counted non-relevant. Rule: **a new configuration's numbers are comparable only
  after a re-pooling round that adjudicates its own top-5 and bumps the label revision.** Every
  report names its pool members and its unjudged count.
- **Unanswerable queries** (`answerable: false`, `gold: []`) are questions this corpus genuinely
  cannot answer. They are **excluded from every aggregate** (§4.3) — they exist because they cost
  minutes now and are a prerequisite for the abstention/multi-turn work (§4.6). Today the only
  assertion on them is that they resolve to no gold document.

### 4.3 The metrics, and the criterion that decides (I-002, I-007, I-016)

**Denominators.** Every aggregate below is over the **40 answerable queries**. Unanswerable queries
contribute to nothing — no recall, no MRR, no miss count — and the report prints both counts so a
reader can see which denominator was used.

**How a ranked list becomes a score**, stated so two implementers get the same number:

1. A leg produces its own ranked chunk list — `keyword` and `vector` at their configured depth
   (`bm25_top_k` / `vector_top_k` = 20), `fused` the RRF output *before* `final_top_k` truncation.
2. Chunks collapse to documents, keeping each document's best rank; the collapsed list preserves
   that order.
3. Metrics are computed over the **first 10 documents** of the collapsed list — ten documents, not
   the documents surviving inside a ten-*chunk* window. If fewer than 10 distinct documents exist,
   the shorter list is used as-is.

Then, per query with gold set `G`:

- **Recall@10** — `|top-10 documents ∩ G| / |G|`
- **MRR@10** — reciprocal rank of the first gold document, 0 if none
- **miss** — no gold document in the top 10

Reported per leg (`keyword`, `vector`, `fused`) and per stratum.

**The keyword leg is the comparison surface.** The tokenizer touches nothing else: the vector leg
embeds raw text and never sees a morpheme. A tokenizer verdict read off fused numbers is diluted by
a leg that cannot have changed. Fused is reported because it is what a user experiences, and a
keyword-leg win that RRF erases is a real — and reportable — non-result.

**The verdict rule, fixed here before any number exists.** ADR-0008 §5 assigned this SPEC the job of
naming the criterion, so:

- **Decisive metric:** keyword-leg **Recall@10**, per query, over the 40 answerable queries.
- **Paired comparison:** for each query, the two configurations produce a win, a loss, or a tie.
- **Decision:** a two-sided exact binomial (sign) test on wins vs losses, ties excluded, **α = 0.05**.
  - `p ≥ 0.05` → **"no measurable difference at this sample size."** mecab-ko is retained — not
    because it won, but because a change with no measured benefit is not paid for. The report must
    print the wins/losses/ties and say the result is inconclusive rather than dress it as a win.
  - `p < 0.05` and nori ahead → ADR-0008 §5(b) **fires**, and the SPEC that proposes acting on it
    inherits this report as its evidence.
  - `p < 0.05` and mecab ahead → mecab retention becomes a finding rather than an inheritance.
- **MRR@10** is reported and may inform commentary; it never overturns the recall verdict.
- **Per-stratum numbers are descriptive only.** Eight queries move 12.5 recall points per query;
  no stratum result decides anything, and the report says so next to the table.
- If the result is inconclusive and the question still matters, the remedy is named in advance:
  **add labelled queries and re-run** (which bumps the label revision and re-records floors).

Corpus 265 ≫ window 10, so a miss is now a measurement rather than an arithmetic impossibility.

### 4.4 Swapping the tokenizer without swapping the engine

The nori exploration was uninterpretable mainly because the engine changed with the tokenizer
(OpenSearch `match` + BM25 vs Postgres `to_tsquery` + `ts_rank_cd`). This design removes that
confounder instead of documenting it again:

**nori is used only as a tokenizer.** Text goes to an OpenSearch container's `_analyze` API, the
returned tokens are fed into the *same* `tokens_to_tsquery`, the *same* Postgres tsvector column and
the *same* `ts_rank_cd`.

**Pinned analyzer configuration** (I-008) — the parameters that decide compound segmentation are
part of the result, so they are fixed here and echoed in every report:

```
opensearch      2.17.1            analysis-nori plugin of the same build
analyzer        {"type":"nori", "decompound_mode":"mixed"}
user_dictionary none
```

`decompound_mode: mixed` keeps both the compound and its parts, which is the configuration that
most resembles what our mecab allow-list yields; a run under any other mode is a *different
configuration* and must be labelled as such in the report.

**One tokenizer per run, bound to the index (I-009).** The seam is a `Tokenizer` protocol
(`id: str`, `tokenize(text) -> list[str]`) with `MecabTokenizer` (today's `tokenize_korean`,
the default) and `NoriTokenizer` (HTTP `_analyze`, harness-only), injected at the two call sites of
§3. Prose is not enough to keep index-time and query-time in agreement, so:

- the harness resolves **one** tokenizer instance per run and passes it to both paths;
- the loader stamps `tokenizer_id` on the tenant it builds (a row in the harness's run manifest);
- the scorer **refuses to score** when the query-time `tokenizer_id` differs from the one stamped on
  the index, and refuses when the index was built by a different label/pack revision than the run
  claims. A mismatch is an error, never a number.

This is the invariant most worth asserting: the whole SPEC exists because a previous instrument
could not detect its own invalidity.

What remains confounded, stated rather than hidden: nori's POS filtering differs from our
`tokenize_korean` tag allow-list, so "nori" here means *nori's segmentation under our filter
policy*, not "nori as Onyx would run it". The comparison is about **segmentation** — the property
that made `엔티티` → `엔`/`티티` a problem in the first place.

### 4.5 What runs in CI, and what does not

- **CI (existing `nexus (search recall, mecab)` job):** keyword-leg metrics over Pack A with mecab,
  asserted against floors. Keyword-only keeps CI free of an embedding service; indexing 265
  documents for BM25 is seconds.
- **Floors are pinned to a triple** — `(pack revision, label revision, date)` (I-006). A label
  revision bump requires re-recording the floors **in the same commit**; the harness fails if the
  floors' cited label revision does not match the label file's. Raising a floor is progress and the
  diff says so; lowering one requires a reason in the same commit.
- **Floors are not self-certifying** (I-011). Two things stop "whatever the first run produced"
  from being the standard:
  - an **absolute sanity bound** — keyword-leg Recall@10 **≥ 0.50** and misses ≤ 25% of the 40
    answerable queries. A first run below that is treated as a broken instrument (bad index, bad
    pack, bad labels) and investigated; it is *not* recorded as a floor.
  - the **negative control** (§6) — a deliberately degraded run must fall below the floors. A floor
    that survives sabotage is not measuring anything.
- **Not in CI:** the vector and fused legs (need ollama) and the nori configuration (needs an
  OpenSearch container). These are **exploratory runs**, invoked by hand, each writing a dated
  report to `nexus/tests/eval/reports/` recording pack revision, label revision, tokenizer id and
  analyzer config, embedding model, pool members, unjudged count, the numbers, and the §4.3 verdict
  with its p-value. The report is the artifact a future reader cites — ADR-0008 §5(b) is answered by
  a committed report, not by a memory of a run.

### 4.6 Built to be reused, not rebuilt

- **Embedding comparison (KURE-v1, sequence ③)** needs no new *queries*: hold the tokenizer fixed,
  vary the embedding model, read the vector and fused legs. It does need a **re-pooling round**
  before its numbers are comparable (§4.2) — that is the reuse discount honestly priced.
- **Multi-turn (`SPEC-nexus-multi-turn-retrieval` Unit 1)** adds `context` (prior turns) to the same
  records and reuses the same corpus, strata and scorer. Labelling both axes on one corpus is the
  halving of labour both notes anticipated. The 5 unanswerable labels are its first material.
- The harness takes `(corpus pack, label file)` as parameters, which is what makes Pack B possible
  at all.

## 5. How this instrument can lie, and what stops it

| failure | consequence | guard | mechanical? |
|---|---|---|---|
| a gold path matches 0 or 2 documents | a correct answer scored a miss | integrity gate fails the run before metrics | yes |
| pack changes underfoot | floors pinned to nothing | commit SHA + per-file hashes; count asserted | yes |
| labels change and floors don't | CI breaks with no code change, or hides a regression | floors cite the label revision; mismatch fails | yes |
| index built with one tokenizer, queried with another | plausible, meaningless numbers | `tokenizer_id` stamped on the index; scorer refuses on mismatch | yes |
| a lexeme expectation creeps back in | the recorded defect returns | schema key ban, asserted | yes |
| a query just restates its gold document's title | measures string matching | title/heading substring check | yes |
| the instrument cannot fail | a green suite that proves nothing | negative control must fall below floors | yes |
| a third `tokenize_korean` call site appears | future runs partly mecab-tokenised | import-boundary test | yes |
| **labeller picks gold by seeing what mecab returns** | the ruler bends toward the incumbent | authoring protocol (document-side, de-lexicalised) + adjudication pooling both configurations. **Process, not mechanism — a determined labeller can still do this** | **no** |
| verdict read off fused or per-stratum numbers | tokenizer effect diluted, or noise read as signal | §4.3 fixes the decisive metric and marks strata descriptive | partly |
| Pack A verdict cited as closing ADR-0008 (b) | a deferred decision falsely closed | report header names the pack; §4.1 states the limit | no |

The last three rows are conventions this document imposes on its readers. Listing them next to the
mechanical guards, rather than among them, is the point.

## 6. Testing

Unit, no DB:

- Label file parses; `revision` and `pack` present; every record has `id`, `query`, `stratum`,
  `answerable`, `gold`, `rationale`, `provenance`; ids unique.
- **No key anywhere in the file matches `token|lexeme|morpheme|term|expected_word`** — the
  structural ban, naming the regression it prevents.
- `answerable: false` ⇔ `gold == []`.
- Each stratum has ≥ 5 queries; every gold entry is a full pack-relative path.
- **No query contains a gold document's title or any of its headings** as a substring, after
  whitespace normalisation.
- Metric functions: known ranked lists → known Recall@10 / MRR@10 / miss, including `|gold| > 1`,
  empty results, fewer than 10 distinct documents, and **unanswerable queries excluded from
  aggregates** (denominator 40, not 45).
- Manifest verification: a mutated corpus file, a missing file, or a wrong document count fails.
- Verdict rule: given synthetic per-query outcomes, the sign test returns the expected decision —
  including a case that must come back **inconclusive**.
- **Import boundary**: no module outside the tokenizer seam imports `tokenize_korean` directly.

Against Postgres (the mecab CI job):

- **Integrity gate fires** — a deliberately ambiguous gold path fails the run *on the label*, not on
  the recall.
- Keyword-leg metrics over Pack A meet the recorded floors, and the floors' cited label revision
  matches the label file.
- **Negative control** — with query assembly deliberately degraded (`tokens_to_tsquery` reverted to
  `AND`, the documented historical failure), the run falls **below** the floors. If it does not, the
  suite fails with a message saying the instrument has no teeth.
- **Tokenizer binding** — scoring a mecab-built index with a nori query tokenizer raises rather than
  scores.
- **Default is still mecab** — with nothing injected, index and query paths call `tokenize_korean`;
  asserted at the seam, not by reading a config value.

Exploratory (documented, not in CI):

- mecab vs nori under the fixed Postgres engine, both in the pool, report written with the §4.3
  verdict and p-value.

## 7. Acceptance

- A pinned 265-document Korean corpus pack with a manifest and CC BY 4.0 attribution is in the
  repository; a mutated file or a wrong count fails the run.
- 45 labels exist — 40 answerable across five strata, 5 unanswerable — carrying a revision, with no
  lexeme expectation representable in the schema and no query restating its gold document's title.
- The harness reports Recall@10, MRR@10 and misses per leg and per stratum over the 40 answerable
  queries, refuses to score a tokenizer/index mismatch, and CI holds mecab keyword-leg floors that
  are **above the §4.5 sanity bound** and that the negative control breaks.
- The same harness runs mecab and nori **on the same engine, index and scorer**, with the analyzer
  configuration of §4.4 pinned, and a committed dated report applies the §4.3 verdict rule —
  including the possibility that it returns "no measurable difference" — with its pool membership,
  unjudged count, and an explicit statement that Pack A is not Khala's own corpus.
- Production retrieval returns, for every input, what it returned before this SPEC; the only
  production change is the injection seam of §4.4.

## 8. Units

1. **Corpus pack** — builder (fetch at pinned SHA, normalise per §4.1, write manifest), the
   committed pack, attribution.
2. **Labels + gates** — schema, the 45 labels, the structural, integrity and title-reuse tests.
3. **Harness + CI floors** — loader into a disposable tenant, leg-wise scorer, verdict rule, report
   writer, negative control, the mecab floors (recorded after adjudication, above the sanity bound).
4. **Tokenizer seam + verdict** — `Tokenizer` protocol, injection at the two call sites, index
   stamping and mismatch refusal, `NoriTokenizer`, the mecab-vs-nori run, the committed report.

Units 1–3 are independent of 4; 4 is where the ADR-0008 question is actually answered.
