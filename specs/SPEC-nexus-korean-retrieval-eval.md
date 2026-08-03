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
reviewed_at: '2026-08-02T11:04:10Z'
content_hash: sha256:0623ab1f06c7355200d4f9a726371b421fb1c686167e8486b16c2303fba2c200
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

### 1.1 Gate record

The demand-pull discipline is **ADR-0002's**, and ADR-0008 §3 item 3 restates the procedure it
fixes: a gate is *declared fired by the director* and *recorded in that direction's first SPEC* —
it is not argued into existence by the SPEC. This is that first SPEC, and this is that record:

> **Gate: fired. Declared by LivingLikeKrillin (director) on 2026-08-02**, instructing that the
> Korean evaluation set be built as the next unit of work.

No override is claimed. In particular this SPEC does **not** stretch ADR-0006's entropy/ingestion-
trust override to cover a retrieval-quality instrument — ADR-0008 §3 left that open and it stays
open. The authority is the director's declaration above and nothing else; §1's argument explains
*what* to build, and is not the gate.

**On ADR-0008's own status.** Its frontmatter is `status: accepted`, `approved_by:
LivingLikeKrillin`, content-hash stamped 2026-08-01; its body's Status section still reads "In
review. Binding on acceptance." — the prose was not updated when it was accepted. This SPEC relies
on the ledger's frontmatter, which is the stamped record. The stale prose is ADR-0008's to fix and
is noted here rather than repaired in passing.

## 2. Non-goals

- **No change to retrieval behaviour.** No tokenizer swap, no embedding swap, no ranking change
  ships here: for every input, production returns what it returns today. Unit 4 does add a
  *dependency-injection seam* inside two production files (§4.4) — a change to the code, not to the
  results. That carve-out is deliberate and named, because "changes nothing" would have been false.
  **ADR-0008 §5's backstop was re-read for this SPEC** (2026-08-02): it fires on work that
  *materially expands* the retrieval stack — a new retrieval channel, a second index backend, a
  tokenizer or embedding-model change. The seam ships no second tokenizer into production (the
  `NoriTokenizer` lives in the harness) and changes no result, so the backstop's re-read is
  discharged here, in writing, rather than assumed. **The run this SPEC enables is exactly what
  would produce such a change**, and the SPEC that proposes it inherits the backstop obligation.
- **Reranking, query expansion, synonyms.** Same reason as SPEC-nexus-search-recall §2.
- **Answer quality, faithfulness, citation correctness.** This measures *retrieval*: whether the
  document that contains the answer is returned. Whether the answer is right, current, or
  well-cited is measured elsewhere (#134, #139, #143).
- **LLM-as-judge.** No model scores relevance, ranks a run, or decides the verdict — ever (ADR-0002:
  "System decides, LLM narrates"). What the ban forbids is a *model's judgment being the standard*.
  Drafting labels with an agent is permitted **only** under a recorded human review: every label
  carries `authored_by: human | agent` and `reviewed_by: <person>`, an agent-authored label with no
  reviewer fails the label gate (§6), and the report prints the counts. Calling that "human review"
  without a field to check would have been an unenforced ban (§5 lists it accordingly).
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

**`test_search_recall.py` is retained unchanged.** It guards the keyword leg against the `AND`
regression on its own five-document fixture, and its negative control
(`test_and_semantics_would_break_this_suite`) is the property ADR-0008 §2.6 credits — §6 builds the
new suite's own control rather than inheriting it. The two suites are independent: different
corpora, different floors, no precedence between them. The old one answers "did the keyword leg go
silent again"; the new one answers "which tokenizer retrieves better".

Two facts about the code that the design leans on (point-in-time, 2026-08-02 — §6 makes the first
enforced rather than assumed):

- `tokenize_korean()` has exactly **two** call sites — `index/bm25.py:110` (index time) and
  `search/hybrid.py:63` (query time). That is the entire tokenizer seam.
- The mecab arm keeps only POS tags `{NNG, NNP, VV, VA, SL, SN, XR}` (`_INCLUDE_POS`), lowercased.
  §4.4 exists because the nori arm must be held to the same policy.
- `config.yaml` `search`: `bm25_top_k: 20`, `vector_top_k: 20`, `final_top_k: 10`.

## 4. Design

### 4.1 The corpus: a pinned public pack, and why not the Notion mirror

**Decision: the primary corpus (Pack A) is a pinned snapshot of the Kubernetes Korean
documentation** (`kubernetes/website`, `content/ko/docs/**`, CC BY 4.0), committed to this
repository with attribution.

Selection rule — deterministic, and applied to the **raw upstream bytes before any transform**:

```
repo    kubernetes/website @ b035ea80a2f666e0a60923560984458806788104   (2026-08-01)
paths   content/ko/docs/{concepts,tasks,tutorials,setup}/**/*.md
skip    basename == _index.md
size    raw upstream blob size in [2048, 40960] bytes   (GitHub tree API `size`)
=>      265 documents — 2.69 MiB upstream, 2.55 MiB after normalisation
```

**The count is derived, not certified by the first run.** The builder re-selects from the upstream
tree API at the pinned SHA and fails if the selection does not yield exactly the documents in the
manifest — so a selection-rule bug shows up as a disagreement between the rule and the pack, not as
a new standard silently adopted. `265` is written here because the rule was executed against the
pinned tree while writing this section; if a reader re-derives a different number from that SHA, the
rule and this text disagree and the rule wins.

The pack's text is then normalised, and the normalisation is part of the rule because the manifest
hashes the *packed* files:

- **Unicode NFC** first, on the raw text. Hangul round-trips through platforms as NFC or NFD; the
  two forms hash differently *and tokenize differently*, so leaving this unstated would have let
  the platform perturb the very quantity being measured.
- strip the YAML front-matter block (leading `---` … `---`); keep `title:` as a `# ` heading.
- **Hugo shortcodes.** Both delimiter forms — `{{< … >}}` and `{{% … %}}` — are treated
  identically; of the 2,872 tags surveyed across the 265 files (2026-08-02), **2,317 are the angle
  form and 555 the percent form**. Three rules, applied innermost-first so nesting resolves
  bottom-up:
  1. a tag carrying a **`text="…"` attribute becomes that attribute's value** — 464 tags, 387 of
     them containing Korean. `{{< glossary_tooltip text="파드" term_id="pod" >}}` → `파드`. This rule
     wins over rule 3 for the same tag, and applies wherever the tag sits, including inside a
     paired block. Deleting these would delete precisely the loanword vocabulary the `loanword`
     and `compound` strata are built to measure; the first draft of this rule did exactly that.
  2. **paired** open/close tags (`note` 385 pairs, `caution`, `warning`, `tabs`, `tab`, `mermaid`)
     — both tags removed, inner content kept.
  3. **every other tag** (`codenew`, `code_sample`, `include`, `feature-state`, `skew`, `param`,
     `version-check`, `heading`, …) removed entirely, leaving no marker.
- HTML comments removed; CRLF → LF; trailing whitespace stripped; file ends with one `\n`.

The builder writes `manifest.json` (upstream SHA, per-file upstream blob SHA-1 and packed SHA-256,
document count, byte total) and **fails if the count or any hash disagrees with the committed
manifest**. Two people running the builder get byte-identical packs or an error.

Why this corpus:

- **It has the failure modes we are trying to see.** Loanword transcription (`파드`/`Pod`,
  `디플로이먼트`), compound nouns (`스테이트풀셋`, `퍼시스턴트볼륨클레임`), Korean-English mixing in
  one sentence, and spacing variants are not decorations here — they are the whole vocabulary.
  Those are precisely the five strata in §4.2.
- **Words collide.** 265 documents about one system, all reusing the same terms, is exactly the
  condition under which a retrieval miss is possible and therefore informative. Five toy documents
  are not.
- **It is redistributable.** CC BY 4.0, attribution and a statement of modifications in the pack.
- **It is pinned.** A ruler that moves is not a ruler (SPEC-nexus-search-recall §4.3 learned this
  the expensive way).

**Why not the live Notion mirror, which the earlier note assumed.** *This repository is public.*
The mirror is an organisation's internal documents; committing a corpus — or labels that quote
document titles — would republish them. That is disqualifying regardless of the corpus's technical
merit, and it is the reason the obvious candidate is not the primary one.

**Pack B — a frozen export, not the live tenant.** §3 disqualifies the live tenant because it
moves, and that applies to Pack B too. So Pack B is defined the way Pack A is: a **local,
git-ignored export** (`nexus/tests/eval/local/`) of a *named tenant at a named moment* — document
rid, title, text and content hash on disk, with its own manifest and count. Labels reference the
export, never the live table. A Pack B run whose manifest does not verify is not a result.

**Pack B is designed here and built by no unit in §8.** It needs corpus access this SPEC's author
does not exercise, and inventing a schedule for it would be fiction. What §8 delivers is the
parameterisation that makes it a data-entry task rather than a redesign. Concretely:

- **owner:** LivingLikeKrillin · **trigger:** the first time ADR-0008 §5(b) is cited in a decision.
- Until then, (b) stands **partially** satisfied: a reproducible verdict exists on a representative
  public corpus, and no verdict exists on Khala's own.

**What that means for ADR-0008 §5(b), stated without stretching:**

- Pack A alone yields a **reproducible, auditable verdict on a representative corpus**. Anyone can
  re-run it. That is what makes the tokenizer decision reviewable at all.
- (b) says "on Khala's real corpus". Pack A is not that corpus — it is a public stand-in of the
  same *kind* (Korean technical documentation, loanword-dense).
- A verdict from Pack A alone **must say so in the report header** and must not be cited as closing
  (b). Under-claiming is cheap; this question has already reversed itself twice.
- If Pack A and Pack B disagree, that disagreement is the finding. They are not averaged.

### 4.2 The labels

**45 labelled queries**: 40 answerable across five failure-mode strata (**exactly 8 each**, asserted
in §6), plus 5 unanswerable. Forty is a **pragmatic starting size, not a powered sample**: §4.3's
verdict rule is built to say so out loud, including a precondition that can declare the instrument
underpowered. A hundred labels would delay the instrument's existence by the length of the
labelling; growing the set is cheap and non-invalidating.

Strata, one per known Korean failure mode:

| stratum | what it stresses | example shape |
|---|---|---|
| `loanword` | transcription variants | query says `파드`, document says `Pod` (or the reverse) |
| `compound` | compound-noun segmentation | `퍼시스턴트볼륨클레임을 어떻게 만드나` |
| `particle` | particle attachment (`을/를/으로/에서`) | the same noun in four case forms |
| `mixed` | Korean-English in one query | `노드에 taint 를 어떻게 거나` |
| `spacing` | spacing variants | `스테이트풀 셋` vs `스테이트풀셋` |

Unanswerable records carry `stratum: unanswerable`, which is **not** one of the five and never
counts toward their balance.

Label file (`nexus/tests/eval/ko/labels.yaml`) carries a **revision** and the records:

```yaml
revision: 1                      # bumped whenever any record changes; floors cite it (§4.5)
pack: ko-k8s-2026-08-01
queries:
  - id: q014
    query: "파드가 계속 Pending 상태면 어디부터 보나"
    stratum: loanword            # loanword|compound|particle|mixed|spacing|unanswerable
    answerable: true
    gold: [tasks/debug-application-cluster/debug-pods.md]   # pack-relative paths
    rationale: "파드 Pending 원인 진단 절차가 이 문서의 본문 전체다"
    provenance: authored_from_doc                            # | adjudicated
    authored_by: agent                                       # | human
    reviewed_by: LivingLikeKrillin                           # required when authored_by: agent
    # reserved for SPEC-nexus-multi-turn-retrieval, absent today:
    # context: [...]   prior turns
```

Rules that make it a ruler rather than a wish:

- **No token, lexeme, or morpheme field exists in the schema, at any level.** A test fails if such a
  key appears (§6). This makes the *recorded* defect — a pinned expected lexeme — unrepresentable.
  It does **not** stop a labeller from choosing gold by looking at what mecab retrieves; §5 says so
  plainly instead of crediting the ban with more than it buys.
- **Gold is a set of pack-relative paths**, never a prefix. Each must resolve to exactly one
  document in the pack — zero or two fails the run *before* any metric is computed (an
  eight-character prefix matching two pages once turned a correct top-1 into a "regression").
- **Queries are authored from the document side, then de-lexicalised.** Pick a document, write the
  question a person would actually type. The machine-checked part is narrow **and deliberately so**:
  a query may not contain its gold document's **full title** as a substring (after whitespace and
  NFC normalisation) when that title is ≥ 6 characters. It says nothing about headings or short
  titles — Korean k8s docs carry headings like `파드`, `노드`, `볼륨`, and banning those would force
  labellers away from the exact vocabulary the `loanword` and `compound` strata exist to stress.
  The rest of the authoring discipline is process, and §5 records it as process.
- **Pooled adjudication at the metric depth, before the floors exist.** The pool is the union of the
  **top-10** — not top-5 — of every leg of every configuration in the pool, because §4.3 scores at
  10 and a pool shallower than the metric would leave ranks 6–10 unjudged and silently counted
  non-relevant. Each pooled document is judged by reading it; relevant ones join `gold` with
  `provenance: adjudicated`. Adjudication is part of *building* the set: it completes, the label
  revision is stamped, and only then are floors recorded.
- **Pool membership is a property of the report, and later configurations must re-pool.** TREC
  pooling favours the systems in the pool. mecab and nori are pooled together, so neither is
  favoured — but a configuration that was **not** in the pool (the KURE-v1 run of §4.6, most
  obviously) is systematically penalised, because documents only it finds are unjudged and counted
  non-relevant. Rule: **a new configuration's numbers are comparable only after a re-pooling round
  that adjudicates its own top-10 and bumps the label revision.** Every report names its pool
  members and its unjudged count.
- **Unanswerable queries** (`answerable: false`, `gold: []`) are questions this corpus genuinely
  cannot answer. They are **excluded from every aggregate** (§4.3). They are labelled here — and
  this is a deliberate, small piece of scope this SPEC does not use — because
  `SPEC-nexus-multi-turn-retrieval` Unit 1 needs exactly this material on exactly this corpus, and
  authoring them alongside the other 40 costs minutes now versus a separate pass later. §7 states
  the 40/5 split wherever the count appears, so "45" never stands in for the working set.

### 4.3 The metrics, and the criterion that decides

**Denominators.** Every aggregate is over the **40 answerable queries**, macro-averaged (mean of
per-query values, each query weighted equally). Unanswerable queries contribute to nothing, and the
report prints both counts so a reader can see which denominator was used.

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
naming the criterion.

- **Per-query outcome** — configuration A beats B on a query if its keyword-leg **Recall@10** is
  higher; **if recall ties, MRR@10 breaks the tie**. Only an exact tie on both is a tie. Recall@10
  alone ties on most queries of a 265-document corpus (both configurations find the gold document,
  at different ranks); scoring those as ties would throw away the rank information that a
  segmentation change moves most.
- **Decision** — two-sided exact binomial (sign) test on wins vs losses, ties excluded, **α = 0.05**.
- **Power precondition, checked and printed before the p-value.** A two-sided exact binomial cannot
  reach p < 0.05 with fewer than **6 discordant pairs** (6–0 gives p ≈ 0.031). If the run yields
  fewer than 6, the report states **"underpowered — the test could not have concluded"** and does
  not print a verdict at all. That is a different statement from "no difference", and conflating
  them is how an instrument launders its own insensitivity.
- **Outcomes:**
  - `p ≥ 0.05`, ≥ 6 discordant → **"no measurable difference at this sample size."**
  - `p < 0.05`, nori ahead → ADR-0008 §5(b)'s condition is met on Pack A.
  - `p < 0.05`, mecab ahead → mecab retention becomes a finding rather than an inheritance.
- **What an inconclusive result means for (b), stated because the ADR's wording admits two
  readings.** ADR-0008 §5(b) says "its result does not favour mecab-ko". Read literally,
  *inconclusive* does not favour mecab-ko and would satisfy (b). This SPEC reads it as requiring an
  **affirmative** result — an inconclusive run leaves the incumbent in place, since a change with
  no measured benefit is not paid for. That is a narrowing of the ADR's text, it is recorded here
  rather than performed silently, and **the director can overturn it**; if they do, ADR-0008 §5
  should be amended rather than reinterpreted.
- **MRR@10** is reported and informs commentary; it never overturns the recall-with-MRR-tiebreak
  verdict.
- **Per-stratum numbers are descriptive only.** Eight queries move 12.5 recall points per query; no
  stratum result decides anything, and the report says so next to the table.
- If the result is inconclusive or underpowered and the question still matters, the remedy is named
  in advance: **add labelled queries and re-run** (which bumps the label revision and re-records
  floors).

Corpus 265 ≫ window 10, so a miss is now a measurement rather than an arithmetic impossibility.

### 4.4 Swapping the tokenizer without swapping the engine — or the filter policy

The nori exploration was uninterpretable mainly because the engine changed with the tokenizer
(OpenSearch `match` + BM25 vs Postgres `to_tsquery` + `ts_rank_cd`). This design removes that
confounder instead of documenting it again:

**nori is used only as a tokenizer.** Text goes to an OpenSearch container's `_analyze` API, the
returned tokens are fed into the *same* `tokens_to_tsquery`, the *same* Postgres tsvector column and
the *same* `ts_rank_cd`.

**Pinned analyzer configuration** — the parameters that decide compound segmentation are part of the
result, so they are fixed here and echoed in every report:

```
opensearch      2.17.1            analysis-nori plugin of the same build
analyzer        {"type":"nori", "decompound_mode":"mixed"}
user_dictionary none
_analyze call   explain: true     (POS tags required — see below)
```

`decompound_mode: mixed` keeps both the compound and its parts, closest to what our mecab allow-list
yields; a run under any other mode is a *different configuration* and must be labelled as such.

**The POS filter must be the same on both arms.** mecab's arm keeps only `{NNG, NNP, VV, VA, SL, SN,
XR}` (§3). A `tokenize(text) -> list[str]` seam would have compared *filtered* mecab against
*unfiltered* nori and called the difference "segmentation" — reintroducing a confound at the exact
point this SPEC exists to remove one. So:

- nori is called with `explain: true`, which returns each token's POS tag from the **same mecab-ko-dic
  tagset**, and **our allow-list is applied to nori's output in our code** — not approximated with
  `nori_part_of_speech` stoptags.
- The seam is `Tokenizer` with `id: str`, `policy: str` (a human-readable statement of the filter
  actually applied) and `tokenize(text) -> list[str]`. Every report prints both arms' `policy`
  strings adjacent, so a reader sees whether they matched.
- §6 asserts the two arms' allow-lists are the same set, from the code, not from prose.

Residual, stated: nori's tagset overlaps mecab-ko-dic's but is not guaranteed identical across
versions, so a tag nori emits that mecab never does is dropped by our allow-list. The report prints
any such tag and its count instead of hiding it.

**One tokenizer per run, bound to the index.** Prose is not enough to keep index-time and query-time
in agreement:

- the harness resolves **one** tokenizer instance per run and passes it to both call sites of §3;
- the loader stamps `tokenizer_id` on the tenant it builds (in the run manifest);
- the scorer **refuses to score** when the query-time `tokenizer_id` differs from the one stamped on
  the index, or when the index was built from a different pack or label revision than the run
  claims. A mismatch is an error, never a number.

This is the invariant most worth asserting: the whole SPEC exists because a previous instrument
could not detect its own invalidity.

### 4.5 What runs in CI, and what does not

- **CI (existing `nexus (search recall, mecab)` job):** keyword-leg metrics over Pack A with mecab.
  Keyword-only keeps CI free of an embedding service; indexing 265 documents for BM25 is seconds.
- **The floors, enumerated** (three, no more):
  - `KEYWORD_RECALL10_MIN` — macro-mean Recall@10 over the 40 answerable queries
  - `KEYWORD_MRR10_MIN` — macro-mean MRR@10 over the same 40
  - `KEYWORD_MISSES_MAX` — count of queries with no gold document in the top 10

  No per-stratum floors (8 queries cannot carry one) and no vector/fused floors in CI (those legs do
  not run there).
- **Floors are pinned to a triple** — `(pack revision, label revision, date)`. A label revision bump
  requires re-recording the floors **in the same commit**; the harness fails if the floors' cited
  label revision does not match the label file. Raising a floor is progress and the diff says so;
  lowering one requires a reason in the same commit.
- **Floors are not self-certifying.** Two things stop "whatever the first run produced" from
  becoming the standard:
  - an **absolute sanity bound** — macro-mean keyword Recall@10 **≥ 0.50** and misses **≤ 10** of 40.
    A first run below that is treated as a broken instrument (bad index, bad pack, bad labels) and
    investigated; it is *not* recorded as a floor.
  - the **negative control** (§6) — a deliberately degraded run must fall below the floors. A floor
    that survives sabotage is not measuring anything.
- **Not in CI:** the vector and fused legs (need ollama) and the nori configuration (needs an
  OpenSearch container). These are **exploratory runs**, invoked by hand, each writing a dated
  report to `nexus/tests/eval/reports/` recording pack revision, label revision, tokenizer id,
  analyzer config, both arms' filter policy, embedding model, pool members, unjudged count, the
  numbers, the discordant-pair count, and the §4.3 verdict with its p-value. The report is the
  artifact a future reader cites — ADR-0008 §5(b) is answered by a committed report, not by a memory
  of a run.

### 4.6 Built to be reused, not rebuilt

- **Embedding comparison (KURE-v1, sequence ③)** needs no new *queries*: hold the tokenizer fixed,
  vary the embedding model, read the vector and fused legs. It does need a **re-pooling round**
  before its numbers are comparable (§4.2) — the reuse discount, honestly priced.
- **Multi-turn (`SPEC-nexus-multi-turn-retrieval` Unit 1)** adds `context` (prior turns) to the same
  records and reuses the same corpus, strata and scorer. The 5 unanswerable labels are its first
  material.
- The harness takes `(corpus pack, label file)` as parameters, which is what makes Pack B possible
  at all.

## 5. How this instrument can lie, and what stops it

| failure | consequence | guard | mechanical? |
|---|---|---|---|
| a gold path matches 0 or 2 documents | a correct answer scored a miss | integrity gate fails the run before metrics | yes |
| pack changes underfoot | floors pinned to nothing | commit SHA + per-file hashes; selection re-derived from the pinned tree | yes |
| NFC/NFD drift between machines | different hashes *and* different tokens | NFC applied in the builder; hashes catch the rest | yes |
| labels change and floors don't | CI breaks with no code change, or hides a regression | floors cite the label revision; mismatch fails | yes |
| index built with one tokenizer, queried with another | plausible, meaningless numbers | `tokenizer_id` stamped on the index; scorer refuses on mismatch | yes |
| one arm POS-filtered, the other not | "segmentation" difference that is a filter difference | same allow-list applied to both, asserted from code; policies printed side by side | yes |
| a lexeme expectation creeps back in | the recorded defect returns | schema key ban, asserted | yes |
| a query restates its gold document's title | measures string matching | full-title substring check (titles ≥ 6 chars) | partly |
| an agent's judgment becomes the standard | the ADR-0002 ban breached quietly | `authored_by` + `reviewed_by`, unreviewed agent labels fail the gate | yes |
| the instrument cannot fail | a green suite that proves nothing | negative control must fall below floors | yes |
| a test declared "no difference" that could never have found one | insensitivity read as equivalence | discordant-pair precondition printed before any p-value | yes |
| a third `tokenize_korean` call site appears | future runs partly mecab-tokenised | import-boundary test **plus** an AST check that the two seam files call it exactly once each | yes |
| **labeller picks gold by seeing what mecab returns** | the ruler bends toward the incumbent | authoring protocol + adjudication pooling both configurations. **Process, not mechanism — a determined labeller can still do this** | **no** |
| verdict read off fused or per-stratum numbers | tokenizer effect diluted, or noise read as signal | §4.3 fixes the decisive metric and marks strata descriptive | partly |
| Pack A verdict cited as closing ADR-0008 (b) | a deferred decision falsely closed | report header names the pack; §4.1 states the limit | no |

The last rows are conventions this document imposes on its readers. Listing them next to the
mechanical guards, rather than among them, is the point.

## 6. Testing

Unit, no DB:

- Label file parses; `revision` and `pack` present; every record has `id`, `query`, `stratum`,
  `answerable`, `gold`, `rationale`, `provenance`, `authored_by`; ids unique.
- **No key anywhere in the file matches `token|lexeme|morpheme|term|expected_word`** — the
  structural ban, naming the regression it prevents.
- `answerable: false` ⇔ `gold == []` ⇔ `stratum == unanswerable`.
- **Exactly 8 answerable queries in each of the five strata**; unanswerable records count toward
  none of them.
- `authored_by: agent` ⇒ non-empty `reviewed_by`.
- Every gold entry is a full pack-relative path that exists in the pack.
- **No query contains its gold document's full title** (≥ 6 chars) as a substring after NFC and
  whitespace normalisation.
- Normalisation: front-matter stripped with `title:` preserved as a heading; a `text=`-bearing
  shortcode inside a paired `note` block yields the text (nesting, innermost-first); a percent-form
  tag behaves as the angle form; NFD input and NFC input produce the identical packed bytes.
- Metric functions: known ranked lists → known Recall@10 / MRR@10 / miss, including `|gold| > 1`,
  empty results, fewer than 10 distinct documents, and **unanswerable queries excluded from
  aggregates** (denominator 40, not 45).
- Verdict rule: synthetic per-query outcomes → expected decision, including (a) a case that must be
  **inconclusive**, (b) a case with < 6 discordant pairs that must be reported **underpowered and
  without a verdict**, and (c) a recall tie broken by MRR.
- Manifest verification: a mutated corpus file, a missing file, or a wrong document count fails.
- **Filter-policy parity**: the allow-list applied to the nori arm is the same set as
  `_INCLUDE_POS`, asserted from the code objects, not from a copied literal.
- **Seam integrity**: no module outside the tokenizer seam imports `tokenize_korean`, and an AST
  check finds exactly one call to the injected tokenizer in each of `index/bm25.py` and
  `search/hybrid.py` — an import check alone would not catch a second call added inside those files.

Against Postgres (the mecab CI job):

- **Integrity gate fires** — a deliberately ambiguous gold path fails the run *on the label*, not on
  the recall.
- Keyword-leg metrics over Pack A meet the three recorded floors, and the floors' cited label
  revision matches the label file.
- **Negative control** — with query assembly deliberately degraded (`tokens_to_tsquery` reverted to
  `AND`, the documented historical failure), the run falls **below** the floors. If it does not, the
  suite fails with a message saying the instrument has no teeth.
- **Tokenizer binding** — scoring a mecab-built index with a nori query tokenizer raises rather than
  scores.
- **Default is still mecab** — with nothing injected, index and query paths call `tokenize_korean`;
  asserted at the seam, not by reading a config value.

Exploratory (documented, not in CI):

- mecab vs nori under the fixed Postgres engine and the same filter policy, both in the pool, report
  written with the §4.3 verdict, discordant count and p-value.

## 7. Acceptance

- A pinned Korean corpus pack — the 265 documents the §4.1 rule selects from the pinned tree — with
  a manifest, CC BY 4.0 attribution and a statement of modifications; a mutated file, a missing
  file, or a selection that disagrees with the rule fails the run.
- **40 answerable labels (8 per stratum) + 5 unanswerable**, carrying a revision, with no lexeme
  expectation representable in the schema, no query restating its gold document's title, and no
  agent-authored label lacking a reviewer.
- The harness reports Recall@10, MRR@10 and misses per leg and per stratum over the **40** answerable
  queries, refuses to score a tokenizer/index mismatch, and CI holds the three keyword-leg floors —
  above the §4.5 sanity bound, and broken by the negative control.
- The same harness runs mecab and nori **on the same engine, index, scorer and POS filter policy**,
  with the analyzer configuration of §4.4 pinned, and a committed dated report applies the §4.3
  verdict rule — including its underpowered and inconclusive outcomes — with pool membership,
  unjudged count, discordant-pair count, and an explicit statement that Pack A is not Khala's own
  corpus.
- Production retrieval returns, for every input, what it returned before this SPEC; the only
  production change is the injection seam of §4.4.
- **Pack B is not delivered** (§4.1) — its owner and trigger are recorded, and ADR-0008 §5(b) stands
  partially satisfied until it is.

## 8. Units

1. **Corpus pack** — builder (fetch at pinned SHA, NFC, normalise per §4.1, write manifest,
   re-derive the selection), the committed pack, attribution.
2. **Labels + gates** — schema, the 45 records, the structural, integrity, balance, authorship and
   title-reuse tests.
3. **Harness + CI floors** — loader into a disposable tenant, leg-wise scorer, verdict rule with its
   power precondition, report writer, negative control, the three mecab floors (recorded after
   adjudication, above the sanity bound).
4. **Tokenizer seam + verdict** — `Tokenizer` protocol with `policy`, injection at the two call
   sites, index stamping and mismatch refusal, `NoriTokenizer` with allow-list parity, the
   mecab-vs-nori run, the committed report.

Units 1–3 are independent of 4; 4 is where the ADR-0008 question is actually answered. Pack B is
deliberately not a unit (§4.1).
