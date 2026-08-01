---
id: ADR-0008
type: adr
title: Keep Nexus's own substrate; defer the Onyx adoption question with named resume
  conditions
status: accepted
date: '2026-08-01T09:24:00Z'
tags:
- ecosystem
- strategy
- retrieval
- licensing
- governance
linked_adrs:
- ADR-0002
- ADR-0004
- ADR-0006
- ADR-0007
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-01T14:09:35Z'
content_hash: sha256:1697106d24ba0d813f4ed48fd57d104bf2e860b22132a22fe2d9612196f2614f
---
# ADR-0008: Keep Nexus's own substrate; defer the Onyx adoption question with named resume conditions

## Status

**In review.** Binding on acceptance.

This ADR decides one thing: **Nexus keeps its own retrieval substrate for now, and the question of
adopting [Onyx](https://github.com/onyx-dot-app/onyx) is deferred — not settled — under the resume
conditions in §5.** It authorises no migration and no new feature work.

Its second purpose is to record what a 2026-08-01 investigation established **and what it failed to
establish**, so the question is not re-opened from zero. Several findings were expensive to obtain
and are not discoverable from Onyx's documentation.

## 1. Why the question was asked

Nexus's chat surface has no multi-turn retrieval: `nexus/nexus/web/js/api.js` (`streamAnswer`) sends
only `query`, `top_k`, `route`, `classification_max`, and `tenant`, so the conversation history the
user sees on screen never reaches the server. **What is established is the payload, not a failure
rate** — no test or log measures how often follow-ups actually degrade, and a self-contained
follow-up would still work. Quantifying it is part of what the evaluation set in §5(b) would enable.
Onyx has this
(`backend/onyx/secondary_llm_flows/query_expansion.py::semantic_query_rephrase` rewrites the last
turn into a standalone query using chat history;
`backend/onyx/tools/tool_implementations/search/search_tool.py` fuses it with the original query by
weighted RRF). Before building it, we asked whether Nexus should own a retrieval stack at all.

The investigation ran twice to the opposite conclusion before landing here. That history is kept in
§4, because knowing which arguments were tested and failed is most of this document's value.

## 2. Findings

All against `onyx-dot-app/onyx` commit
[`27e26de`](https://github.com/onyx-dot-app/onyx/commit/27e26de8aafaa2f7e482c171b4290386af6f381b),
read 2026-08-01. Onyx is open-core: MIT except `ee/` directories, which its LICENSE places under the
Onyx Enterprise License.

### 2.1 Onyx's hook framework is Enterprise-only — all three hook points

Onyx has a hook framework (`HookPoint`: `DOCUMENT_INGESTION`, `DOCUMENT_PUSH`, `QUERY_PROCESSING`;
`HookFailStrategy.HARD|SOFT`; durable execution logs). The hook-point definitions are MIT
(`backend/onyx/hooks/points/*.py`), but execution is not. `backend/onyx/hooks/executor.py`:

```python
def _execute_hook_impl(...):
    """CE no-op — hooks are not available without EE."""
    return HookSkipped()
```

Its module docstring states the dispatch: *"CE: … no-op, returns HookSkipped() / EE:
ee.onyx.hooks.executor._execute_hook_impl → real HTTP call."* The working executor is
`backend/ee/onyx/hooks/executor.py`.

**This applies to `QUERY_PROCESSING` as much as to `DOCUMENT_INGESTION`.** There is a single public
entry point, `onyx/hooks/executor.py::execute_hook`, and both call sites import it: the
query-processing path in `backend/onyx/chat/process_message.py` and the ingestion path in
`backend/onyx/indexing/indexing_pipeline.py`. No separate dispatch exists for either.

**What this does and does not establish.** It rules out the hook framework *as shipped* under the MIT
edition. It does **not** establish that governance cannot be attached at all. Two routes were left
unexamined:

- **In-process patching of MIT retrieval code**, the technique §2.4 finds viable for verification.
- **Replacing the CE stub itself.** `_execute_hook_impl` is MIT Python; patching it to dispatch to
  Khala's own executor is technically the same move as §2.4. Whether reimplementing the gate that
  reserves EE functionality is permissible — a different question from patching `ee/`, since no
  Enterprise-licensed text is copied — was not examined and would need counsel.

See §2.5.

### 2.2 The Enterprise licence is incompatible with Khala's distribution model

Not a pricing question. `backend/ee/LICENSE`, verbatim:

> you are free to modify this Software and publish patches to the Software. **You agree that
> DanswerAI and/or its licensors retain all right, title and interest in and to all such
> modifications and/or patches**, and all such modifications and/or patches may only be used,
> copied, modified, displayed, distributed, or otherwise exploited **with a valid Onyx Enterprise
> License** […] it is **forbidden to copy, merge, publish, distribute, sublicense, and/or sell** the
> Software.

And the carve-out that makes investigation permissible, also verbatim:

> Notwithstanding the foregoing, you may copy and modify the Software for **development and testing
> purposes, without requiring a subscription**.

Khala is a public repository under MIT (`LICENSE`, covering every tool in the monorepo per
`CONVENTIONS.md`). **If** the governance layer were implemented as patches to `ee/`, then:

1. That code would vest in DanswerAI.
2. Khala could not distribute it, so there would be nothing to release.
3. Every adopting organisation would need its own Enterprise licence.

**This chain holds only for the `ee/`-patch branch.** Separately-authored MIT code that merely calls
an extension point is not obviously "a patch to the Software", and §2.5 records that in-process
attachment to MIT code was never evaluated. What §2.2 establishes is that *one* route is closed, not
that all are.

*This is a reading of the licence text, not legal advice; a real engagement would need counsel.*

### 2.3 An ingestion hook could not have carried Khala's supersession

`nexus/nexus/supersede.py` requires **both** documents to already exist and be indexed —
`SELECT status FROM documents WHERE rid = $1 AND tenant = $2` — then flips the old one's status and
appends to the lifecycle ledger. Its first line: *"문서 supersession 선언 프리미티브(명시적·멱등,
자동감지 없음)"* — an explicit, idempotent, tenant-scoped declaration with no auto-detection.

Supersession is a **post-ingest human declaration about already-indexed documents**, so
`DOCUMENT_INGESTION` was never the right home for it.

**This section refutes only that one candidate.** [[ADR-0006]]'s actual containment mechanism is a
*retrieval-time* filter (`AND EXISTS (SELECT 1 FROM documents d WHERE d.rid=c.doc_rid AND
d.status='active')`), whose natural counterpart is `QUERY_PROCESSING` — which §2.1 rules out on
licence grounds, not on design grounds. A design-level evaluation of retrieval-time attachment was
**not performed**.

### 2.4 Verification, unlike governance, appears attachable to the MIT region

The three shipped answer checks need only (answer text, evidence snippets, document metadata) and do
not need to control retrieval:

- **Citation verification (#134)** — the title the LLM cites must be among the snippets shown.
- **Answer-number verification (#139)** — significant numbers in the answer must appear in what the
  LLM was shown.
- **Staleness (#143)** — evidence older than its `doc_type` TTL is flagged.

The inputs for the **first two** exist in Onyx's MIT region: `chat/citation_processor.py` maintains
the citation number → `SearchDoc` mapping and already detects dangling citations (logs a warning and
drops them, `:487`); the evidence text and the answer are both in hand at generation time.

**The third is not shown to exist.** Staleness needs a per-`doc_type` freshness TTL, and
[[ADR-0006]] places `doc_type` tier derivation in Arbiter with Nexus holding no tier registry.
`SearchDoc.metadata` carries connector-supplied source metadata, not an Arbiter-derived tier, so
staleness would additionally require getting Khala's tier data into the substrate — unexamined here.
`SearchDoc.updated_at` supplies only the timestamp half.

**Qualification.** Attachment would have to be in-process: the API-facing `SearchDoc` carries
`blurb`, a snippet, not the full section text given to the LLM (built in-process by
`convert_inference_sections_to_llm_string`), so an out-of-process checker would compare against
truncated text.

### 2.5 What the investigation did not measure

Recorded because these gaps, not the findings, are what make the decision a deferral rather than a
conclusion.

| Not measured | Why it matters |
|---|---|
| **In-process attachment of governance to MIT retrieval code** | The technique §2.4 validates for verification was never tried for filtering. It is plausibly harder — filters are constructed at many call sites, and a federated-search path bypasses them entirely — but "harder" was never quantified |
| **Interface stability of the patch surface** | Commit counts (below) measure upstream *cadence*, not the cost of a breaking refactor. §2.4's attachment binds to private internals with no stability contract, and that instability is the form of the merge-tax objection that would actually bear on the finding |
| **Korean retrieval quality** | §2.6 |

Commits in the trailing 90 days, via `gh api repos/onyx-dot-app/onyx/commits?path=…&since=2026-05-03`:

| Path | Commits |
|---|---|
| `backend/onyx/chat/citation_processor.py` | 3 |
| `backend/onyx/tools/tool_implementations/search/` | 12 |
| `backend/onyx/chat/` | 44 |
| `web/src` | 438 |

No baseline is offered for these — Nexus's own churn was not measured, and no threshold defines
"high" or "low". They are recorded as raw counts, and the only comparison they support is between
Onyx's own paths (the UI moves far more than the file a verification patch would touch).

### 2.6 No Korean comparison was obtained, and the attempt shows why one is hard

Onyx selects its analyzer by environment variable —
`OPENSEARCH_TEXT_ANALYZER = os.environ.get("OPENSEARCH_TEXT_ANALYZER") or "english"`
(`backend/onyx/configs/app_configs.py`) — so Korean is configuration, and `analysis-nori` is the
Korean analyzer. Whether it is *good enough* is a separate question, and the attempt to answer it
failed.

nori was run against Khala's committed recall fixture (`nexus/tests/test_search_recall.py`) on
OpenSearch 2.17.1. **The run is recorded as an exploration, not a measurement, and its numbers are
not cited here as evidence** — reproduction and the full list of confounds are in
[`nexus/scripts/adr0008_nori_recall.py`](../nexus/scripts/adr0008_nori_recall.py). The confounds:

1. **Engine and scorer differ.** Nexus's keyword leg is Postgres `to_tsquery('simple', …)` +
   `ts_rank_cd` (`nexus/nexus/search/hybrid.py`); the run used OpenSearch `match` + BM25. Any
   difference measures tokenizer *plus* engine *plus* scorer.
2. **mecab was not run alongside.** It is built from source inside the Nexus image
   (`nexus/Dockerfile:13-23`) and was unavailable in that environment, so there was no comparison
   arm — only the fixture's committed *floors*, which are a 2026-07-10 baseline rather than mecab's
   score.
3. **The corpus (5 documents) is smaller than the retrieval window (20).** A "miss" is therefore
   near-impossible by arithmetic, so miss count carries no signal at that size.
4. **The instrument cannot detect tokenizer regression by construction.** Each query pins an expected
   lexeme chosen from mecab's own segmentation. nori splits `엔티티` into `엔`/`티티` — a real
   difference — but that query's assertion is pinned to `식별`, which nori also produces, so the split
   cannot lower the score.
5. **The fixture's own negative control was not replicated.**
   `test_search_recall.py::test_and_semantics_would_break_this_suite` deliberately degrades query
   assembly and asserts recall collapses — the check that proves the instrument has teeth. The
   exploration had no equivalent, so nothing established that it could have failed.

**What the fixture is and is not good for.** It is a regression guard for Nexus's own keyword leg —
that is what its negative control (confound 5) proves, and it does that job. It is **not** a
tokenizer comparator, because confounds 3 and 4 are properties of its design, not defects. Both
statements are true of the same file; the error was using it as the second thing.

So the honest statement is **not** "nori is adequate" and not "nori is inadequate" — it is that **no
instrument exists that could compare them**. The gap is Khala's own and independent of Onyx: the same
absence means mecab-ko's retention is also unevidenced, and an embedding-model change is equally
unevaluable.

## 3. Decision

1. **Nexus keeps its own retrieval substrate.** Not a refusal on merit, and **not a claim that the
   incumbent is good** — §2.6 records that its Korean quality is as unmeasured as the alternative's.
   The argument is asymmetry of reversibility: §2.1 and §2.2 close the route we evaluated, §2.5
   records that two routes were never evaluated, and §2.6 leaves quality unknown on both sides.
   Under that much uncertainty, not migrating is the option that can be undone later; migrating is
   not.
2. **The adoption question is deferred, not closed.** §5 names what would reopen it and when it is
   next looked at.
3. **Nothing is authorised here.** Multi-turn retrieval and a Korean evaluation set are unblocked to
   be *proposed*, each through its own SPEC and gate, with [[ADR-0002]]'s demand-pull discipline
   applying to both. Note the procedure ADR-0002 fixes: a gate is **declared fired by the director
   and recorded in that direction's first SPEC** — it is not argued into existence by the SPEC. This
   ADR takes no position on whether [[ADR-0006]]'s entropy/ingestion-trust override extends to a
   retrieval-quality instrument; that override was granted for index trustworthiness, and stretching
   it is a call for the director to make, not a reading to assume.

**Scope.** This is about Onyx and Nexus. It is deliberately **not** a general policy about external
OSS — one investigation is no basis for one. Reusing external design judgment, as distinct from code,
remains ordinary practice and needs no ADR.

## 4. Arguments that were tested and failed

Recorded so they are not re-run. The investigation first concluded "keep and transplant" on four
grounds, then reversed to "adopt", then landed here.

| Ground originally given for keeping our own stack | Outcome |
|---|---|
| Onyx's `ee/` region covers Khala's identity area | **Partly wrong, then partly right.** False for verification (§2.4 — that path is MIT). True for the hook framework (§2.1), which is not the reason first given |
| A fork carries a permanent merge tax | **Undecided.** §2.5 measures cadence, which is low, but explicitly does not measure the interface instability that is the objection's real form |
| Korean-first requires our own mecab-ko pipeline | **Not established.** §2.6. "Korean-first" is a principle (`nexus/CLAUDE.md` §4); mecab-ko is one implementation of it, and defending the tool as though it were the principle was an error |
| `base_filter` enforcement requires owning the retrieval path | **Undecided.** The remedy proposed during the reversal — ingestion hooks — is dead (§2.1, §2.3), but retrieval-time in-process attachment was never evaluated (§2.5) |

An intermediate conclusion — adopt Onyx and layer governance on top — was also reached and
abandoned; §2.1 and §2.2 are why.

## 5. Resume conditions

Owner: **LivingLikeKrillin**.

**Backstop.** No periodic ADR review process exists in this repository, so this ADR does not lean on
one. Instead it attaches to an event that will actually occur: **this ADR is re-read at the start of
any work that would materially expand Nexus's retrieval stack** — a new retrieval channel, a second
index backend, a tokenizer or embedding-model change, or connector work beyond the existing two
sources. Each of those is exactly the moment the incumbent's cost is being paid again.

If none of those occurs, the deferral simply persists, and that is an accepted outcome rather than a
hidden closure: nothing is being built that the deferral would distort.

| # | Condition | How it would be noticed |
|---|---|---|
| a | An extension point — Onyx's hook framework under MIT, or a measured in-process alternative per §2.5 — is available for the governance layer | Re-read `backend/onyx/hooks/executor.py` and the `ee/` tree at a backstop event |
| b | A Korean evaluation set exists that can compare tokenizers on Khala's real corpus, and its result does not favour mecab-ko | Output of that set. **It does not exist**; building it is what makes this condition checkable at all |
| c | Maintaining our retrieval stack visibly crowds out governance work | Judged at a backstop event from the merged-PR record |

**Sufficiency.** (a) is **necessary and, on its own, sufficient to reopen the question** — not to
settle it. Without an attachment point the governance layer has nowhere to live whatever the
retrieval quality, so (b) and (c) cannot reopen adoption alone; they raise the priority of
re-examining (a), and (b) is a prerequisite for any subsequent decision being evidence-based.

Conditions (b) and (c) are judgments, not thresholds. (b) deliberately says "does not favour
mecab-ko" rather than naming a metric or margin: the evaluation set does not exist yet, and
specifying a threshold for an instrument nobody has designed would fix the answer before the
question. The set's own SPEC is where the comparison criterion belongs.

## 6. Consequences

- **Nexus continues to carry retrieval, ingestion, and connector work.** The connector gap is real:
  Onyx has 55 connector packages under `backend/onyx/connectors/`; Nexus has two source paths
  (filesystem collector and Notion, `nexus/nexus/ingest/sources/`). This is the decision's principal
  recurring cost. It is **not** left unowned: owner **LivingLikeKrillin**, reviewed at each backstop
  event (§5), and it is the same record that condition (c) is judged from — so the cost and the
  trigger that would surface it are deliberately tied to one artifact. No connector work is
  authorised here; the obligation is to keep the cost visible, not to pay it.
- **The Korean measurement gap (§2.6) is now explicit** and blocks three separate decisions: mecab-ko
  retention, an embedding-model change, and resume condition (b).
- **Verification's portability (§2.4) is recorded but unused.** If condition (a) fires, that finding
  is what makes re-evaluation quick — for two of the three checks; staleness needs more (§2.4).

## 7. Relationship to prior ADRs

- **[[ADR-0006]]** is unaffected by this decision: supersession, containment, and residual
  measurement stay where they are, and §2.3 records why one candidate relocation would not have
  worked.

  **One inconsistency surfaced during review and is recorded rather than resolved here.** ADR-0006
  §"out of scope" defers *"Freshness TTL / re-verification thresholds and downweighting"* to a later
  slice behind a demand-pull gate. The staleness check (#143, merged 2026-07-14) ships a
  per-`doc_type` freshness TTL, and its SPEC carries `linked_adrs: []` — it neither cites ADR-0006
  nor records that the gate fired. The SPEC passed its own review gate, so this is a reconciliation
  gap, not an ungated merge. **It is out of scope for this ADR** and needs its own disposition:
  either ADR-0006's deferral is amended, or #143's SPEC is linked and the gate recorded.
- **[[ADR-0004]]**'s component division is untouched, but "out of scope" was too broad a claim. Two
  components sit on the boundary and **must be treated as in scope by any future reopening**:
  - **Archon** — ADR-0004 places it *inside* Nexus (`nexus/nexus/claims/value_query.py`), so a
    substrate change implicates it directly, including where its user-visible grounding signal would
    render.
  - **Arbiter** — it *writes into* Nexus (its publish path and `approved_hash` provenance, plus
    `ingest_external_spec` on the Nexus side), and [[ADR-0006]] records that Nexus deliberately
    holds no `doc_type` tier registry because that derivation lives in Arbiter. Replacing the ingest
    path and index would break both that write path and that boundary — which is also why §2.4's
    staleness check does not port cleanly.

  Adept, Probe, and Observer are separate tools that read Nexus's public surface and were genuinely
  not in scope.
- **[[ADR-0002]]**'s demand-pull discipline is not waived; see §3 item 3 for how it applies to each
  unblocked item.

> **Citations.** Onyx-side references are pinned to commit `27e26de` and are stable. **Khala-side
> references (paths, symbols, line ranges) are point-in-time as of 2026-08-01 and will drift** — the
> convention [[ADR-0002]] and [[ADR-0004]] adopted. A future reader should treat them as pointers to
> find the current code, not as guaranteed locations.
>
> **Component names.** Current names are used (Arbiter, Adept, Probe, Observer, Archon); linked ADRs
> 0002/0004 predate the rename, and [[ADR-0007]] records the mapping.
