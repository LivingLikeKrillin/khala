---
id: SPEC-nexus-code-semantic-cards
type: spec
title: Generate a natural-language card from code and prove the generator repeats
  itself — matching is a later SPEC
status: in_review
linked_adrs:
- ADR-0008
tags:
- nexus
- code
- drift
- retrieval
---

## 0. Gate declaration

[[ADR-0008]] §3.3, quoting [[ADR-0002]]: *"a gate is **declared fired by the director and recorded
in that direction's first SPEC** — it is not argued into existence by the SPEC."*

**Declared fired by:** LivingLikeKrillin, 2026-08-16, in session, after the measurement below.
**Puller:** the policy corpus the deployment already answers from, which the lexical anchor unit
([[SPEC-nexus-doc-code-anchors]]) demonstrably cannot reach.

The evidence in §1 is supporting material for **how** to build it, not the authorisation.

### ADR-0008 §5 backstop — deferred with the work that would trip it

An earlier draft recorded the backstop as firing **and then specified the gated work anyway**. That
is not paying it; ADR-0008 §5 names "a second index backend" as precisely the moment the incumbent's
cost is being repaid, so a SPEC cannot both record the moment and proceed through it.

This SPEC is therefore cut to the part that does **not** trip it: generate cards, store them, measure
whether the generator repeats itself. **No embedding, no matching, no edges.** Nothing here is
indexed or queried, so no retrieval channel is added.

Embedding the cards and matching documents against them is a **separate SPEC**, and §5's backstop is
its opening obligation, not a footnote in this one.

The narrowing is not a technicality. The expensive assumption in this whole direction is that a model
can describe code faithfully and repeatably. If that fails, nothing downstream is worth designing —
so it is worth a SPEC on its own, ahead of the decision it would otherwise force.

### Whose direction is this

ADR-0002's rule places the gate record in *the direction's first SPEC*. [[SPEC-nexus-doc-code-anchors]]
was first in the doc↔code binding direction, and this SPEC is its continuation rather than a new
direction. The declaration above records a **scope extension the director called for after that unit
was measured** — the lexical path reaching ~0 on the target corpus — not a fresh gate. If the director
reads this as a new direction, the record belongs here; if as a continuation, it belongs as an
amendment to the earlier SPEC. Stated rather than assumed.

## 1. What prompted it

[[SPEC-nexus-doc-code-anchors]] shipped and was measured. It works, and it cannot reach the corpus it
was built for.

**Measured on this repository (2026-08-16):** 4,601 symbols indexed; 403 chunks; 128 candidates;
**24 anchors, of which 19 were true** on a full census. Every true anchor was CamelCase
(`NexusResponse`, `GraphRepository`) or a distinctively prefixed name (`nexus_*`, `archon_*`). Every
false one was a short generic lowercase name the document used as a parameter, column or event label.

**Measured on the target policy corpus:** 281 chunks produced **9 candidates**. One
(`OptimisticLockException`) had the shape of a Java type and resolved to **0** symbols in the index;
the remaining 8 were SQL keywords, language keywords, or common words (`Key`, `version`). So: **9
candidates, 0 bound.**

The lexical anchor works in the **engineering register** and has no purchase outside it. A policy
document says *"결제 실패 시 3회까지 재시도한다"*; the code says `RetryPolicy.MAX_ATTEMPTS`. There is
no shared token to match on. **Whether a looser extractor could find one has not been run** — the
79% figure above is the unloosened rule on engineering documents, and transferring it to a loosened
rule on policy prose would be an assumption, not a measurement. What is measured is that the rule as
built binds nothing here.

### What the field does instead

**Generate the natural-language side from the code, and match on meaning.**

- **Toss** (toss.tech, 2026-07-30), same corpus shape (documents + code + messenger): after a
  parser produces symbols with no LLM, an agent walks the implementation and emits a card carrying
  `subject`, `behavior`, **`domain_terms` (업무에서 사용하는 표현)**, `code_terms`, `spans`,
  `commit_sha`. Document↔code relations are then made by **embedding search to a limited candidate
  set, then batch semantic verification** — explicitly to avoid all-pairs cost. Ambiguous internal
  aliases are not auto-merged; they become proposals for human approval, and rejections are recorded
  so they do not recur. The article states the principle directly: *"이름만 보고 하나로 합치지
  않아요."* No precision figures are published.
- **Greptile** publishes the one number: query↔**description** similarity **0.8152** versus
  query↔**code** **0.7280** for the same retrieval task. Embedding a generated docstring beats
  embedding the source by ~12%.
- **CodeRAG-Bench** shows the direction is a property of the task, not of a vendor: dense retrieval
  wins where lexical overlap is low (Voyage-code **33.1** vs BM25 **5.2** nDCG@10 on DS-1000) and
  loses where identifiers are shared. This corpus is the low-overlap case by construction.

### The distinction this SPEC depends on

An earlier draft of the follow-up plan rejected this direction on the grounds that "an LLM in the
loop brings back the precision problem". That conflated two different jobs.

| job | evidence | used here |
|---|---|---|
| **Judging** whether a document and code disagree | DocPrism: naive judge flags **98%** of functions at **14%** accuracy | no — §2 |
| **Describing** code in natural language at index time | Greptile's 0.8152/0.7280; Toss ships it | yes — §3.2 |

Generation with a rule-based re-check is not adjudication. Conflating them is what nearly cost this
direction.

## 2. Non-goals

- **No embedding and no matching.** Cards are generated and stored. Nothing is indexed, nothing is
  queried, no document is compared to anything. That work is a separate SPEC whose opening obligation
  is ADR-0008 §5 (§0).
- **No edges, no relation types, no verification.** This SPEC produces cards, not links. An earlier
  draft specified batch verification here while also declaring it out of scope; the design section
  and the non-goals described different SPECs.
- **The lexical anchor path is untouched.** It is deterministic, costs no model calls, and measured
  19/24 on engineering documents. The two paths are meant to coexist — shared vocabulary binds by
  lookup, absent vocabulary later by meaning. Nothing here removes or changes it.
- **No new language support.** Java and Python, the two grammars that exist.

## 3. Design

### 3.1 Card unit

One card per **symbol that carries business behaviour** — not per symbol. Cards for getters,
constructors and one-line delegators cost model calls and describe nothing, and they dilute the
embedding population with near-identical text.

Selection is deterministic and per-language, because "class/interface/record" is Java vocabulary and
Python has none of the last two:

| language | card candidate |
|---|---|
| Java | `class`, `interface`, `record`, `enum`; any `method` whose body exceeds the line threshold |
| Python | module-level `class`; any `function` (module-level or method) whose body exceeds the threshold |

Plus, in both: any symbol already referenced by a lexical anchor, whatever its size — a document has
already named it, so it is worth describing regardless of length.

**Line threshold default: 8** body lines, recorded per run. Nested definitions are candidates on their
own terms; the enclosing symbol's card does not stand in for them.

### 3.2 Card generation

An agent reads the implementation and emits the card below. **Traversal is bounded**, because §4
names cost as a principal risk and an unbounded walk is where it goes: at most **2 call hops** from
the subject symbol, **within the scanned repository only** (third-party and stdlib are never opened),
cycles visited once, and a hard cap on source bytes read per card. All four are recorded per run.

```
subject       무엇에 관한 카드인가
behavior      실제로 어떤 동작을 하는가
domain_terms  업무 표현 (문서가 실제로 쓰는 어휘)
code_terms    코드 식별자
spans[]       repo, file, start_line, end_line, symbol, span_hash
commit_sha    어느 시점의 코드인가
generator     model · prompt_version · traversal settings
```

`span_hash` is carried so staleness is detected by content rather than by line range, which shifts on
any unrelated edit above the symbol.

`generator` is carried because **the declared embedding generation does not cover it**. Two cards
written by different prompts or different models are indistinguishable inside one declared generation
— the same silent heterogeneity [[SPEC-nexus-generation-of-record]] exists to prevent, one layer up.
A card whose generator does not match the run's declared generator is not read.

`domain_terms` is the field this whole SPEC exists for. It is what a policy document can match
against.

**The model's output is not stored as given.** Rule-based re-checks run first, and a card failing any
of them is discarded rather than downgraded:

- every `span` resolves to a real file and line range in the scanned index
- `code_terms` appear in the referenced spans
- the card is not a near-duplicate of another card for the same file beyond a density cap
- **no verbatim source escapes into prose** — see below

Toss states the same discipline: *"LLM이 만든 결과는 그대로 저장하지 않아요."*

#### The source-text boundary, stated rather than inherited

The lexical unit's invariant was "the index stores no source text", and an earlier draft claimed it
"extends unchanged". **It does not.** That unit stored only names, paths, lines and hashes. This one
stores generated prose written by a model that has just read the source, and it stores `code_terms`,
which are identifiers lifted from it. The boundary has to be drawn here, not assumed:

- **`code_terms` are identifiers only** — a bare symbol name, no qualifiers, no expressions, no
  literals. Capped in count. An identifier is a name, which the symbol index already stores.
- **`subject` and `behavior` are prose about behaviour, never quotation.** A re-check rejects a card
  if any normalised line of its spans appears as a substring of either field, or if either field
  contains a run of source-shaped punctuation beyond a threshold.
- **No literals.** Numeric and string constants from the source are not reproduced in any field;
  "재시도 횟수 상한이 있다" is a description, "MAX_ATTEMPTS = 2" is source.

This is the constraint that matters most in this repository: the corpus being described is not
public, and a generated field is a far easier leak path than a schema column. §6.3 tests it rather
than trusting the prompt.

### 3.3 Reproducibility, measured before anything else

Card generation is a non-deterministic reader over bytes. This project has been here: the deployment
screenshot reader produced **84.7% different text** on the same image twice, falsifying the invariant
an entire tier rested on — and four SPECs had been written on top of it before anyone measured the
noise floor ([[SPEC-nexus-vision-reproducibility]]).

So the generator is measured against itself first. **Not twice — five runs** over the same symbols at
the same commit, reporting a distribution rather than a point: two runs give one number with no
interval, which is exactly what §5 says every figure here needs. The vision precedent established a
floor from repeated trials, not a pair.

**The generator measured must be the generator that ships.** Model, prompt version and traversal
settings are recorded with every run and must match; measuring reproducibility on the keyless
development bridge and then generating production cards with a different model certifies an
instrument that will not be the one running. If both backends are to be used, both are measured and
reported separately.

### 3.4 The card is never the authority

Added after the critique round, from comparing this design against Toss's published one. Their
article ends on the rule this SPEC had left out:

> Topic이 답을 만들거나 최신성을 검사할 때는 **카드의 설명만 믿지 않고 현재 코드의 실제 span을
> 다시 읽어 검증**해요.

The card is a **pointer with a description attached**, not a record of fact. It was written by a
model at one commit, and the code has been free to move ever since. Two consequences:

**For every consumer, now and later.** Anything that acts on a card — matching, answering, drift
reporting — re-reads the referenced spans from the checkout before relying on the description. A
card that cannot be re-read is not evidence. This is a rule the matching SPEC inherits; it is
written here because this is where cards come into existence and where the temptation to treat
them as durable begins.

**In this SPEC's scope**, that means a card must remain *re-verifiable* and must announce when it
has stopped being current. The card carries `span_hash` for exactly this: comparing the stored hash
against the current one is a lookup, and a card whose spans have changed is **stale** — reported as
such and not served to any consumer until regenerated. Detecting this needs no model.

Stale is not wrong. It means the description was true of code that has since moved, which is
precisely the signal this whole direction exists to surface — but it is a signal about the card,
and it must not be quietly presented as a fact about the code.

## 4. How this can lie, and what it costs if it does

- **The card describes what the code appears to do.** A generator that misreads an early return or a
  swallowed exception writes a confident wrong `behavior`. Span re-check proves the lines exist; it
  does not prove the reading is right. §6.2 samples it, and it is the failure that would poison
  everything built later.
- **`domain_terms` can be paraphrase, not knowledge.** `processPayment` → "결제 처리" is free and adds
  nothing; the value is only in terms the identifier does not already contain. §6.2 records the share
  derivable from the identifier alone, without gating on it — nobody knows the right value.
- **The evidence for this direction is English and same-language.** Greptile's 0.8152/0.7280 is an
  English query against an English docstring; CodeRAG-Bench's DS-1000 is English. The task here is
  **Korean policy prose against Java and Python identifiers**, and this repository's own record shows
  embedding choice dominating outcome on Korean (the KURE comparison). The ~12% uplift is a reason to
  try, not a prediction. **This SPEC cannot detect that failure**, because it does no matching — the
  cross-register question belongs to the matching SPEC, and it should be that SPEC's first gate.
- **Generated text drifts between runs**, which §3.3 measures rather than assumes.
- **Cost scales with the corpus, not with the question.** Cards are generated for thousands of symbols
  whether or not any document ever names them. §6.4 gates on total spend, and the per-edge figure that
  would decide whether it was worth it cannot exist until the matching SPEC does.
- **Source can leak through generated prose.** The boundary is drawn in §3.2 and tested in §6.3
  because a prose field is an easier leak path than a schema column.

## 5. Limits

- This unit produces descriptions, not links. It cannot say whether the direction works — only whether
  the generator is steady and faithful enough to be worth pointing at documents. That is deliberately a
  smaller claim than the one that motivated it.
- Every figure here is a sample with an interval. None is a join, and none should be quoted without one.

## 6. Acceptance

Gates in order. **6.1 blocks the rest.** All are measured with the generator that will ship (§3.3).

1. **Reproducibility.** Five runs over the same 100 symbols at one commit.
   - `domain_terms`: mean pairwise Jaccard across the ten run-pairs, reported **with its range**.
     **Below 0.70 mean, this unit does not ship.** The threshold is provisional and stated as such:
     it is chosen so that a later matching layer sees more signal than generator noise, and it has
     not been derived from a retrieval outcome because no matching exists yet to derive it from. It
     is a floor to be revisited by the matching SPEC, not a validated number.
   - `behavior`: on a 20-card subsample, two people independently mark each pair **same claim /
     different claim** — same claim meaning a reader acting on either would do the same thing.
     Inter-rater agreement is reported. **Below 0.70 same-claim, this unit does not ship.**
2. **Faithfulness.** 30 cards hand-checked against their spans. **More than 6 of 30 with a false
   `behavior` rejects the generator prompt.** Separately reported, not gated: the share of
   `domain_terms` derivable from the identifier alone.
3. **The source boundary holds.** Over every card produced in a full run, **zero** may contain a
   verbatim normalised source line, a source literal, or a `code_terms` entry that is not a bare
   identifier. This is a lookup, not a sample, and a single violation fails the gate.
4. **Cost.** Total spend for a full run over the scanned repository, with the backend declared before
   it starts. Development runs use the keyless path unless a paid run is authorised in advance. Spend
   per produced edge is **not** a gate here — there are no edges until the matching SPEC.
5. **Card staleness is detected without a model.** Change one line inside a carded symbol,
   re-run the staleness check, and confirm the card reports `stale` — with the LLM provider unset
   and no API key present, so the check cannot be passing by way of a model call.
6. **The lexical path is unharmed.** Re-run its census **pinned to the commit it was measured at**
   (2026-08-16, 24 anchors / 19 true) against the stored expected set, so ordinary repository churn
   cannot make this pass or fail spuriously.

## 7. Units

1. Card candidate selection + bounded traversal + generation + rule re-checks, including the source
   boundary (§3.1–3.2), and span-hash staleness detection (§3.4).
2. Reproducibility harness and the five-run measurement (§3.3, §6.1).
3. Faithfulness sample and the boundary lookup (§6.2, §6.3).

Not this SPEC: embedding, matching, verification, edges, regeneration policy. Those follow, and
ADR-0008 §5 is the opening obligation of the SPEC that takes them on.
