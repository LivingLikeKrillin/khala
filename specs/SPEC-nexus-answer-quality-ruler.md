---
id: SPEC-nexus-answer-quality-ruler
type: spec
title: The answer-quality ruler — what it may call an abstention, a wrong document,
  and a signed label
status: approved
date: '2026-08-11T16:58:24Z'
linked_adrs:
- ADR-0002
- ADR-0008
- ADR-0010
tags:
- nexus
- eval
- answer-quality
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-12T14:47:44Z'
content_hash: sha256:f97b028ae2673b159b0fcd44bd60d8ce6f453faa50992c70b1f7678e0cb2f147
---

## 1. What prompted it

The answer ruler (`scripts/ko_eval_answer_quality.py` + `ko_eval_answer_run.py`) reported
`grounded 39/40` three runs in a row on 2026-08-11. Reading the four distinct failures behind those
runs, **three of them were the ruler being wrong, not the answerer**. A fourth defect surfaced while
measuring the three.

None of this is specified anywhere. The ruler was built ad hoc over four days; the only SPEC that
touches it, [[SPEC-nexus-korean-retrieval-eval]], specifies the *labels* and the *retrieval* metric
and says nothing about answers. This SPEC is that missing document, scoped to the three defects and
the one invariant they share: **the ruler must not report a verdict it cannot support.**

### 1.1 A disclaimer about one sub-question was read as a refusal of the whole question

`pb-space-01` ("낙관적락 충돌 시 재시도정책") was scored `abstained` while answering: it opened with

> 제공된 문서에 재시도 **횟수·간격·백오프 공식** 등 구체적인 정책 수치는 명시되어 있지 않습니다.

and then delivered four sections, a code sample, a four-row table of design principles, and five
citations. The detector reads the **first sentence** and asks whether it denies while naming
evidence. It does — about the numbers, not about the question.

The first-sentence rule was itself the fix for an earlier defect (a phrase list that a fourth
phrasing walked through), and the run before that had the opposite failure: a refusal that echoed
the question's vocabulary passed `must_contain` and was counted **correct** (`pb-part-07`, whose
refusal contained both `태스크` and `다른`). The two failures pull in opposite directions, which is
the signature of a rule looking at the wrong unit.

### 1.2 A correct answer that cited another document saying the same thing was scored wrong

`pb-part-02` ("플레이리스트에는 노래를 몇 곡까지 담을 수 있나") failed 3 runs of 3 with `grounded ✓`,
`must_contain ✓`, `cites_gold ✗`. Its label names one gold document, `플레이리스트 정책`
(4,632 chars active). The answer cited `플레이리스트 / 1 playlist = 100곡` — an 89-character Notion
property card whose body states `**wht**: 1 playlist = 100곡`. Both documents are in the corpus,
both state the fact, the label names one.

The label file's own header records this class of error being fixed once before by hand
(revision 3, `pb-comp-04`: *"성능 플레이북에도 같은 처방이 있어, 그쪽을 인용한 정확한 답변이 오답
처리됐다"*). It came back because nothing in the ruler distinguishes **"cited a wrong document"**
from **"cited a document nobody has judged yet."** It calls both `incorrect`.

### 1.3 The labels were signed against text that no longer exists

`pb-part-01` ("로그인하지 않고 들어오면 어느 화면으로 가는가") has failed **6 runs of 6** — the only
systematic failure in the set. Its label requires the answer to contain `파티 목록`, quoting the
document's prose:

> - […도메인] 을 통해 비로그인 입장 시, [파티 목록]으로 이동

(Quotes from the corpus are redacted where they carry the other organisation's identifiers; this
repo is public and `tests/eval/local/` is not committed for the same reason.)

The system consistently answers `파티룸 입장(Main)`, quoting the **screen-spec table in the same
document** — text that entered the corpus on 2026-08-10 when 44 screenshots were read
([[ADR-0010]], machine-read tier):

> \| 3 \| 팝업 \| popup \| 기능 제한 관련 안내 팝업<br>- [비로그인 입장하기] : 비로그인 상태에서
> [파티룸 입장(Main)]화면으로 이동

The label was authored before that text existed. Measuring how general the problem is:

| | count |
|---|---|
| documents in the signed pack | 116 |
| whose active body hash differs from the pack today | **8** |
| answerable queries whose gold is one of those 8 | **22 of 40** |

`로그인 정책` went 3 → 9 active chunks, 11,138 → 4,578 chars. `[파티룸] 디제잉 정책` went 4 → 15
chunks. Both directions moved: extraction added machine-read text, and the expired-S3-URL repair
removed thousands of characters of link garbage. **Nothing in the harness noticed.** The label gate
checks that a gold key *exists in the manifest*; the run then measures the **live tenant**, which is
a different corpus. Two days of "no regression" readings sat on top of that.

### 1.4 What the control arm said — and what it killed

The label set has 5 `answerable: false` queries, authored in revision 1 for *"the unbuilt abstention
work"* ([[SPEC-nexus-korean-retrieval-eval]] §4.2). **They had never been run.** Running them is the
positive control the abstention detector never had: on a query the corpus genuinely cannot answer, a
grounded answerer must refuse.

Measured (2026-08-11, claude-code bridge, tenant `default`): **5 of 5 refused**, and the current
detector caught 5 of 5. But their shape refutes the obvious fix. Two of the five are long, sectioned
answers with tables, code blocks and citations — the same shape as the hedged answer in §1.1:

| control | chars | citations | shape |
|---|---|---|---|
| `pb-un-02` | 190 | 0 | one sentence |
| `pb-un-04` | 176 | 0 | one sentence |
| `pb-un-03` | 284 | 1 | two sentences |
| `pb-un-01` | 733 | 2 | headings + quoted evidence + a 한계 section |
| `pb-un-05` | 780 | 2 | headings + a table + a code block + a 결론 section |

So **length, structure, and citation count cannot separate a true abstention from a hedged
answer.** The rule I would have written without running the controls ("an abstention is short and
delivers nothing") would have re-broken 2 of the 5. This is the [[suspect-the-instrument-first]]
control discipline applied before the rule, not after.

## 2. Non-goals

- **No model judges an answer.** Nothing in this ruler asks a model whether an answer is good; the
  verdict is computed from citations, the label's `must_contain`, and the text. The reason is not an
  ADR — [[ADR-0002]] governs how *answers* are produced ("grounded answers only", "system decides,
  LLM narrates"), not what an instrument may use, and this SPEC does not claim otherwise. The reason
  is that an LLM judge would score the judge's taste, which is less reviewed than these labels and
  cannot be re-run identically. Nexus **does** ship one model judgment used beside this ruler — the
  sufficiency judge of [[SPEC-nexus-sufficiency-signal]], measured at 43/45 — and this SPEC keeps it
  where it already is: an opt-in second axis (`--sufficiency`), reported as a model judgment, never
  part of `correct`/`incorrect`.
- **Not a re-authoring of the eval set.** No new queries, no strata changes, no re-pooling of the
  whole corpus. Where a judgment is missing this SPEC makes the ruler *say so*; it does not invent
  the judgment.
- **Not the retrieval ruler.** `cites_gold` and Recall@10 both read `gold`, so widening `gold`
  moves both — that is intended and stated, but no metric definition changes here.
- **Not an answer-quality improvement.** Nothing here makes an answer better. One real generation
  defect found in the same runs — an answer citing `[출처: 동일]`, which no verifier can resolve, so
  `grounded` collapses — is **out of scope and stays open**.

## 3. Design

### 3.1 A refusal has a scope: the sentence it is in, and where it stands

Two conditions, both structural, both measured:

1. Split the answer into **segments** on line breaks and Korean sentence terminators
   (`다.` `습니다.` `?` `!`).
2. A segment is a **refusal segment** when it denies while naming evidence — the existing pattern
   (`(제공된|검색된|주어진)? (근거|문서|자료) … {0,80} (없|않|어렵|불가|못 찾|못 하|아닙니다)`),
   unchanged, and still a vocabulary rule (§4).
3. `refuses(answer)` = any refusal segment. `leads_with_refusal(answer)` = the first segment that is
   not a markdown heading or rule is a refusal segment.
4. `must_contain` is evaluated on the **non-refusal segments only** — the *delivered* text.
5. `abstained` = `leads_with_refusal` **and** the required facts were not delivered.
   With an empty `must_contain` (the `answerable: false` controls) "the facts were not delivered" is
   **true by definition** — there is nothing to deliver — so a control that opens by refusing scores
   `abstained`. This is pinned by test, not left to `all([])`.

Condition 4 keeps what the old position rule protected: a refusal that echoes the question's
vocabulary can no longer buy a fact-check pass, because the echo lives *inside* a stripped segment.
Condition 3 keeps a **trailing** caveat from turning an answer into an abstention.

**Condition 3 exists because the first version of this rule was refuted by measurement.** The rule
written for the first sample was steps 1–2 + 4 only (`abstained = refuses ∧ ¬delivered`). On a fresh
45-answer run it created a *new* false abstention: `pb-part-01` answered with three sections and a
table and closed with a provenance caveat —

> 근거 1·2는 그림에서 기계가 읽은 내용(vision 추출)입니다. 설계 문서 기반 정보이며, 실제 구현
> 관측 데이터는 제공된 근거에 없습니다.

— which is a refusal segment about a different aspect than the one asked. Adding the leading
condition removes it.

Measured over **85 answers** (40 from run `post-source-ref-bridge-r3`, 45 from a fresh run of the
whole label set including controls):

| | old rule | this rule |
|---|---|---|
| controls scored `abstained` | 5/5 | 5/5 |
| hedged answers scored `abstained` (false positives) | 2 | **0** |
| any other verdict moved | — | none |

The two corrected are `pb-space-01` (§1.1) and `pb-mix-08`, which opened by narrowing scope
("근거에서 k6와 Locust에 대한 언급은 한 곳뿐이며…") and then delivered the answer.

`refuses` is reported separately from `abstained`: on the control arm the meaningful number is
*did the answerer refuse*, and the ruler should not need a label to say that.

### 3.2 `unadjudicated` — a document nobody judged is not a wrong document

New outcome, entered when **all** of:

- `grounded` (at least one citation, every citation verified), and
- the facts were delivered (§3.1), and
- `cites_gold` is false, and
- at least one cited title resolves to **a document in the tenant being measured**.

That combination means: the answer said the right thing, its sources resolve, and it pointed at a
document the labels have never ruled on. The ruler does not know whether that document answers the
question — **so it says `unadjudicated`, never `incorrect`.**

The last condition is deliberately about the **tenant**, not the pack. The pack is 116 documents
frozen on 2026-08-07; the tenant grows with every ingest, and scoring a correct answer as wrong
because it cited a document added last week would re-create §1.2 for new documents. A citation whose
title resolves to **nothing in the tenant** stays `incorrect` — that is indistinguishable from a
fabricated source, and [[SPEC-nexus-citation-validation]] already treats it that way.

Resolution is a human reading the cited document, and it must be able to end in **either** verdict,
or the gate never converges:

```yaml
  - id: pb-part-02
    gold: [ext-notion-525206d0-….md, ext-notion-fbbeb6fd-….md]   # joined by adjudication
    not_gold: [ext-notion-8898e29f-….md]                          # judged, and it does not answer
```

`not_gold` is the negative half of the same judgment. Without it every run re-raises the same
resolved case forever. Both halves obey the signature rules already in force (`reviewed_by` +
`reviewed_revision` = the file's revision) and both are bound to their document's text (§3.3) —
a `not_gold` verdict signed against text that has since changed is as expired as a `gold` one, which
is exactly what happened to the `pb-part-01` judgment when machine-read text arrived.

**Cited-but-unjudged documents are always reported, even when the verdict is `correct`.** An answer
that cites one gold document and one unjudged document produces a correct verdict *and* an
adjudication candidate; only the first gates the run. Otherwise the unjudged pool grows silently and
the §4 defence — "the gate is what keeps the softened score honest" — quietly stops being true.

### 3.3 A label is bound to the text it was signed against

The label file gains one block, written when the labels are signed:

```yaml
corpus:
  tenant: default             # the run refuses to start against any other tenant
  signed_at: '2026-08-12'
  bodies:                     # every gold and not_gold document
    ext-notion-b3531625-….md: sha256:…
```

The hash is the **same function the pack manifest uses** (`ko_eval_packb._body_hash`: sha256 over
active chunk texts in `chunk_index` order, NUL-separated), computed over the tenant the run
measures. Tenant mismatch is refusal, not expiry: hashes from another tenant carry no information
about these labels.

At run start each scored query's gold and not_gold bodies are compared with the signed hashes. A
mismatch **expires that query's label**:

- the expired queries are **named, with what changed** — chunk count, character delta, and how many
  of the document's active chunks are `machine_read` ([[ADR-0010]] tier), so the person re-signing
  can see they are about to sign off on text a model read out of a screenshot;
- the run **scores the remaining queries and writes the per-query report**, marked
  `partial: true` with the expired ids, and **exits non-zero without printing an aggregate grade**.

Partial scoring rather than a whole-run halt, because drift is routine — 8 documents in two days
from ordinary ingest and repair — and a ruler that goes dark whenever the corpus moves is a ruler
nobody runs. Withholding the *aggregate* is what has teeth: 19 of 40 is not a grade and must never
be quoted as one, and the report says so in the file rather than in a person's memory.

Re-signing is the human act of re-reading the changed document and confirming (or fixing) the
`rationale`, `must_contain`, `gold` and `not_gold` of every query that points at it, then bumping
the revision — which, under the existing signature rule, re-signs the whole file.

**Only the judged documents are bound, not the corpus.** A label is a claim about a document —
"this document answers this query, and an answer must contain this" — and a new unrelated document
elsewhere does not falsify it. It *can* change retrieval, and that is what the retrieval metric is
for. Binding the whole corpus would expire all 45 labels on every ingest and train everyone to
re-sign without reading, which is the failure this gate exists to prevent (§4).

### 3.4 The control arm is part of the run, and it can expire too

The 5 `answerable: false` labels run as a **control arm** (`--controls`), scored on one question:
did the answerer refuse. They stay out of every answerable aggregate
([[SPEC-nexus-korean-retrieval-eval]] §4.3 excludes them; that does not change).

A control has no gold, so §3.3 cannot bind it — its claim is about the *absence* of an answer in the
whole corpus, and nothing hashes an absence. What binds it instead is the arm itself: **a control
that does not refuse is reported as a control needing re-adjudication, not as a hallucination.**
Either the corpus gained an answer — 44 screenshots did exactly that on 2026-08-10, and one of the
five (`pb-un-05`, embedding-swap deployment order) is about a subject this repo keeps writing down —
or the answerer invented one. The ruler cannot tell those apart, so it names the case and stops
there; a human reads the cited evidence and either flips the label to `answerable: true` with gold,
or records a hallucination. Reporting it as a hallucination without that read is the same
unsupported verdict this SPEC exists to remove.

### 3.5 A gold document the run cannot read is not a retrieval failure

*Added 2026-08-12, after Pack A.* `q002` failed four runs in a row and the cause was not ranking.
Its gold — `tutorials/security/apparmor.md` — is `RESTRICTED` under the `**/security/**` path rule,
while the harness searched at a hardcoded `INTERNAL`. Search obeys
`classification <= clearance`, so that document was excluded before ranking ever happened. Neither
leg could return it under any phrasing, native or transliterated, and the ruler wrote it down as a
retrieval failure. **The system was keeping a policy and the instrument scored it as a defect.**

Clearance is a *condition of the measurement*, not a constant. It is a run argument now, recorded
with the run, and the gate checks the labels against it before scoring:

- a query whose gold is **entirely** unreadable at this clearance **blocks the run**. It cannot pass
  under any phrasing, and a grade that includes impossible queries measures the classification
  settings rather than the system;
- a query with one unreadable gold among several is **named and the run continues** — it can still
  pass on the readable one. Half its label is dead, and saying so is the point; blocking is reserved
  for what makes the number false.

The blast radius when this was found: 3 of 64 judged documents, and 1 of 40 queries impossible.
Correcting it moved Pack A from 34–35 to 38 of 40 with **nothing in retrieval or generation
changed** — which is the exact shape of an instrument defect, and the reason the number has to be
reported with its cause rather than as an improvement.

## 4. How this instrument can lie

- **Refusal detection is still a vocabulary rule.** It catches denial *that names evidence* in
  Korean. A refusal that names nothing ("잘 모르겠습니다") is missed, and an English or mixed-script
  refusal is missed. Nine real phrasings are pinned by test; that is a floor, not coverage.
- **Both rules are fitted to 85 answers from one answerer.** §3.1 was written against 40, refuted by
  the next 45, and rewritten — the honest reading is that the rule tracks the shapes seen so far, not
  that it is right. There is no held-out set left: **the three runs of §6 are the held-out set**, and
  the falsifier is stated — any verdict a reader contests is added to the fixtures with its real
  text, and the rule that produced it is re-derived, not patched.
- **A sentence that denies and delivers at once is scored as an abstention.** "문서에 수치는 없지만
  상한은 100곡입니다" puts the fact inside a refusal segment, where step 4 strips it. Not observed in
  85 answers (0 occurrences), so no machinery is added for it; if it appears, it appears as a
  *false abstention on a leading refusal*, the same shape as §1.1, and it will be visible in the same
  place.
- **The segment splitter is a Korean-sentence heuristic.** A refusal glued to delivered content in
  one unpunctuated line (a table row, a bullet with no terminator) is stripped whole, taking the
  content with it — biasing toward `abstained`.
- **`unadjudicated` softens the score by construction.** An answer that cited a genuinely wrong
  document parks in a bucket instead of counting against the grade. The only thing keeping that
  honest is the gate: **a grade reported with a non-empty bucket is inflated**, and any run that
  prints one is a bug in this design, not a reading of it.
- **Hash binding is byte-level, and meaning is not.** A whitespace repair expires 22 labels; a
  rewrite that inverts a policy expires them the same way, so the signal carries no severity. And 22
  labels re-signed in one sitting is exactly the shape that produces rubber-stamping — the gate can
  force a read, it cannot force attention.
- **The drift gate cannot tell what changed the text**, only that it changed. It reports the
  machine-read chunk count so a re-signer can see the [[ADR-0010]] tier of what they are signing, but
  a human edit and a re-chunking present identically.
- **Adjudication follows what the system retrieves.** Documents promoted to `gold` come from what
  answers cited, which is what the pooled configuration surfaced. TREC pooling bias, named in
  [[SPEC-nexus-korean-retrieval-eval]] §4.2 and inherited here: a document no configuration ever
  surfaces is never judged, and counts against every configuration equally.

## 5. Testing

Every fixture is **committed inline in the test file as the sentence it came from** — not read from
`tests/eval/local/`, which is gitignored, because a test that silently skips on a clean checkout is
an absent test. Whole answers stay local (another organisation's policy text); the pinned sentences
are the refusal and delivery lines, which carry none.

Unit (`nexus/tests/test_answer_outcome_taxonomy.py`, extended):

- the §1.1 hedge (verbatim opening + one delivered fact) scores `correct`, not `abstained`;
- the §3.1 trailing provenance caveat (verbatim) does not make an answer an abstention;
- the vocabulary-echo refusal (`pb-part-07`, already pinned) still scores `abstained`;
- each of the 5 control openings (verbatim first sentences) scores `refuses` and, with an empty
  `must_contain`, `abstained` — the `all([])` semantics pinned explicitly;
- `grounded ∧ facts ∧ ¬cites_gold` with a citation resolving in-tenant → `unadjudicated`; the same
  case with the cited key in `not_gold` → `incorrect`; with a title resolving to nothing →
  `incorrect`;
- an unverified citation with the same shape stays `incorrect`;
- `aggregate()` reports `unadjudicated` separately and `all_three` keeps its formula.

Gate (`nexus/tests/test_ko_eval_labels.py`, extended):

- a label whose gold body hash differs from `corpus.bodies` is reported expired, naming the qid;
- the same for a `not_gold` document;
- a label file with no `corpus` block fails (a ruler that cannot say what it was signed against);
- a run whose tenant differs from `corpus.tenant` fails before scoring;
- `not_gold` keys must exist in the pack, must not intersect `gold`, and obey the signature rules.

Run-level (`test_ko_eval_run_db.py`): with an expired label or a non-empty unadjudicated bucket, the
run writes the per-query report **with `partial: true`**, prints no aggregate grade, and exits
non-zero.

## 6. Acceptance

1. The three §1 defects are gone on the same inputs: `pb-space-01` scores `correct`,
   `pb-part-02` reaches a human judgment through `unadjudicated` rather than being scored wrong,
   and `pb-part-01`'s label is re-signed against the text actually in the corpus.
2. The 22 expired labels are re-signed (or corrected) by the human whose name is on them, and the
   run passes its own gate afterwards.
3. Three answer runs on the re-signed labels, recorded in `packb-answer-runs.jsonl` with the
   per-query `ok` map. **Criterion:** the report names the failure count of each run (the noise
   band) and every query that failed in *all three* carries a written disposition — ruler defect,
   label defect, or answerer defect. Three runs agreeing is not by itself evidence of health; §1
   was three runs agreeing.
4. Numbers this SPEC's *tests* assert are reproducible on a clean checkout with no local state.
   Numbers from the label set are reproducible **by anyone holding the corpus** — the label file and
   the answers stay in `tests/eval/local/`, and the PR body carries the run output. This is a real
   limit, not a checkbox: an outside reviewer can re-derive the rule's behaviour from the committed
   fixtures, and nothing else.

## 7. Units

| # | unit | lands in |
|---|---|---|
| U1 | Refusal scope: segments, `refuses`, `leads_with_refusal`, facts on delivered text | `ko_eval_answer_quality.py`, tests |
| U2 | `unadjudicated` outcome + `not_gold` schema + in-tenant title resolution + gate | `ko_eval_answer_quality.py`, `ko_eval_answer_run.py`, `ko_eval_labels.py`, tests |
| U3 | `corpus` binding, per-query expiry with `partial` report, tenant refusal, control arm | `ko_eval_labels.py`, `ko_eval_answer_run.py`, tests |
| U4 | Re-sign the 22 expired labels; adjudicate the open citations; 3 runs | `tests/eval/local/` (not committed), report in the PR body |

U4 is the only unit whose product is not code, and the only one that requires the human signature.
