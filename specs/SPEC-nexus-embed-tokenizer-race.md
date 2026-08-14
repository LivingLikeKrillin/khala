---
id: SPEC-nexus-embed-tokenizer-race
type: spec
title: The over-length guard races the encoder - give it its own tokenizer
status: approved
linked_adrs:
- ADR-0008
tags:
- nexus
- embedding
- sidecar
- defect
date: '2026-08-05T01:28:06Z'
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-14T14:22:59Z'
content_hash: sha256:2635a67caa5d03e0557dde5f6eccfacc0dd058679828a523dc2b5807c0e3705b
---

# The over-length guard races the encoder — give it its own tokenizer

## Backstop record

```yaml
backstop:
- row: adr-0008-retrieval-stack
  reread: performed 2026-08-05 — §5 의 예시 중 "a tokenizer or embedding-model change" 에
    닿는지가 쟁점이었다. 이 SPEC 이 하는 일은 스택이 **이미 적재한** 토크나이저를 깊은 복사해
    길이검사가 인코더와 한 객체를 공유하지 않게 하는 것이다.
  clause: none
  ruling: does-not-fire
  declared_by: LivingLikeKrillin
  declared_at: '2026-08-05'
  reason: >-
    스택이 이미 적재한 토크나이저의 두 번째 인스턴스는 검색 스택에 아무것도 더하지 않는다.
    모델도 검색 경로도 그대로이고, 이미 선언된 방향 안의 결함 수리이며 프로덕션 500(부하 시
    ~0.5%)이 살아 있었다. **이 항목은 2026-08-14 에 옮겨 적은 것이고, 판정 자체는
    2026-08-05 산문 선언(§1 말미)이다** — 해석을 더하지 않았다.
```


## 1. Goal

The embedding sidecar **returns 500 under concurrent load**, on the deployment now serving
production queries. Measured 2026-08-05, right after the KURE cutover:

| load | result |
|---|---|
| C=4 × 400 requests | 200 × 398, **500 × 2** |
| C=8 × 200 requests | 200 × 199, **500 × 1** |
| C=16 × 200 requests | 200 × 199, **500 × 1** |

Root cause, from the sidecar's own traceback: **`RuntimeError: Already borrowed`** at
`embed_service/app.py:99` — the over-length guard

```python
too_long = [t for t in req.texts if len(model.tokenizer(t)["input_ids"]) > model.max_seq_length]
```

HuggingFace's fast tokenizer is a Rust object behind a borrow check. The guard calls it **on the
event loop** while another request's `model.encode(...)` — in `asyncio.to_thread` — calls the *same*
object from a worker thread.

**Which pairs collide was measured, in one harness, with a positive control:**

| pair | calls per round | errors per round |
|---|---|---|
| **shared tokenizer × `encode`** (the defect) | 600 + 60 | **21 · 23 · 23** |
| deep-copied tokenizer × `encode` (the fix) | 600 + 60 | 0 · 0 · 0 |
| `encode` × `encode` | 600 + 600 | 0 · 0 · 0 |
| `encode` × `encode` × `encode` | 400 × 3 | 0 · 0 · 0 |
| `tokenizer` × `tokenizer` | 3000 + 3000 | 0 · 0 · 0 |

The first two rows are **the same harness, same call counts, same call pattern** — one collides, one
does not. That is the control the null rows need: it shows the instrument has teeth in exactly the
configuration where the fix is claimed to work, rather than in a neighbouring one.

Two honesty notes about the nulls. A first pass ran 25 iterations and found zero everywhere — a
race's absence at low iteration counts is not evidence, and the guard race only appeared at ten
times that. And the `encode × encode` nulls ran 1,200 calls against the positive row's 660: **twice
the total exposure, not the "ten to twenty times" an earlier draft of this SPEC claimed** by
comparing against only the 60-call side. They are supported by the positive control above, not by
that arithmetic.

**Blast radius is a worse answer, not an error page.** `SPEC-nexus-embedding-cutover-seam` §4.4
already degrades the vector leg on an embedding-backend failure, so `/search` answers from the
keyword leg and reports `degraded: ["vector"]`. That is why this is a defect and not an outage — and
not why it is acceptable. At the loads measured, on the order of one query in two hundred loses its
vector leg; **"on the order of" is the precision available**, since the rate rests on four events in
800 requests at C=4–16 (at or past saturation), with a Poisson interval spanning roughly 0.15 %–1.3 %.
The failure is *marked*, not silent; what is silent is whether anyone reads the mark, since
persisting that signal was deferred.

**This defect was introduced by this line of work.** The guard exists because
`SPEC-nexus-kure-embedding-swap` §4.3 refused silent truncation — a truncated vector does not record
that it was truncated — and that refusal is right. Its implementation reached into an object it does
not own.

### 1.1 Gate record

This SPEC repairs a defect in code merged under `SPEC-nexus-embedding-cutover-seam` (approved
2026-08-05, LivingLikeKrillin), found by that SPEC's own follow-up measurement
(`nexus/tests/eval/reports/2026-08-05-sidecar-concurrency.md`).

**ADR-0008 §6 records that the Korean measurement gap blocks "an embedding-model change"** — and the
embedding-model change has already shipped. That is not left implicit here: on **2026-08-05 the
director declared that block lifted** for this swap, on stand-in-corpus evidence and with resume
condition (b) explicitly still open; the declaration and its limits are recorded in
`SPEC-nexus-embedding-cutover-seam` §1.1. This SPEC repairs code inside that already-declared
direction and reopens nothing.

**On §5's backstop** ("re-read at the start of any work that would materially expand Nexus's
retrieval stack — … a tokenizer or embedding-model change"): this SPEC did not argue the trigger
away. It stated what it does — deep-copy the tokenizer the stack already loaded, so a length check
stops sharing one object with the encoder — and put the judgement where ADR-0008 §5 puts it, with
the owner.

**Directorial declaration, 2026-08-05:** asked whether the backstop fires for this repair,
**LivingLikeKrillin declared that it does not** — a second instance of the tokenizer the stack has
already loaded adds nothing to the retrieval stack, the model and the search path are unchanged, and
this is a defect repair inside an already-declared direction where a production 500 (~0.5 % under
load) is live. Implementation proceeds on that record, not on this document's reading.

## 2. Non-goals

- **Not a throughput improvement.** The concurrency report measured the ceiling (~7.6 rps
  end-to-end, saturating at C=2–4) and found torch thread count does not move it. Raising it —
  workers, batching, GPU — is a separate question with its own trigger. **A throughput
  *regression*, however, is in scope**: the reason this design refuses a lock is that it costs
  nothing, and a claim like that has to be checked (§5).
- **Not a change to the guard's contract.** Over-length input still gets a 413 and is still a
  counted failure that blocks a cutover. Silent truncation stays refused.
- **Not a lock around encoding.** Serializing `encode` would pay concurrency to fix a collision
  `encode` does not have with itself (measured, with a control). Fixing the wrong pair is how a
  defect becomes a permanent tax.
- **Not a general thread-safety audit of the sidecar.** One object, one call site, one measured
  collision — plus a check (§5) that would catch the next caller of the same shape, whose limits are
  stated rather than oversold.
- **Not an alerting or metrics system.** §3 adds one counter to `/health` because a defect found
  only by a follow-up measurement should leave *something* behind; wiring it to anything is not here.

## 3. Design

**The guard gets its own copy of the model's tokenizer**, made at load time:

```python
guard_tokenizer = copy.deepcopy(model.tokenizer)
```

An earlier draft of this SPEC loaded a second tokenizer with
`AutoTokenizer.from_pretrained(model.tokenizer.name_or_path)`. **That was wrong, and the review
caught it**: `name_or_path` is the repo id (`'nlpai-lab/KURE-v1'`, verified on the running service),
not a resolved snapshot, so the second load would re-resolve the branch independently — the silent
divergence the design claimed to avoid. A deep copy removes the question instead of answering it:

- **No second resolution, no download, no revision argument.** The copy comes from the object the
  model already loaded, so "same checkpoint, same revision" is true by construction rather than by
  configuration. No new startup precondition, and in particular no new fail-to-boot condition for a
  deployment that leaves `EMBED_REVISION` unset (the sidecar's checkpoint pin, introduced by
  `SPEC-nexus-embedding-cutover-seam` §4.5 and defaulted in compose to a commit) — which the
  second-load design would have introduced.
- **The copy is backed by a distinct Rust object, which is the mechanism, not an inference.**
  Verified on the running service: `guard._tokenizer is not model.tokenizer._tokenizer` is true.
  "Already borrowed" is a borrow conflict *on one object*; two distinct objects cannot produce it.
  A probe that enabled truncation on the copy's backend showed **no** behavioural divergence — not
  because the objects are shared, but because `PreTrainedTokenizerFast.__call__` re-applies
  truncation/padding per call from its own arguments. That is worth recording twice over: it is why
  the mutation probe was inconclusive, and it is why a cached-state difference between the two
  instances cannot silently change what the guard counts.
- **The versions this rests on are recorded, and two of them are not pinned.** Measured with
  `tokenizers 0.22.2`, `transformers 4.57.6`, `sentence-transformers 3.3.1`. The sidecar image pins
  only the last of those, so a rebuild can move deepcopy semantics underneath this fix. **Unit 1
  pins `transformers` and `tokenizers` in `embed_service/Dockerfile`**; without that the fix's
  premise is a floating dependency.
- **Configuration parity is structural, and was measured anyway.** Copy and original report the same
  `model_max_length` (8192) and return identical token counts, including at the boundary the guard
  turns on: 8188 / 8193 / 8198 tokens, identical in both, so the 413 fires on exactly the same
  inputs as before. Startup asserts the parity too (below), because "structural" is an argument.
- **It works, and the harness could have said otherwise.** Copied-tokenizer × encode: 0 · 0 · 0
  errors where the shared tokenizer gave 21 · 23 · 23 in the same harness (§1).

**The guard stays on the loop, and that is pinned.** The copy is safe because the event loop is
single-threaded, so it has exactly one user. As a sync `def`, FastAPI would run the handler in the
threadpool and the copy would be shared across threads again — the same defect, the same traceback,
one keyword away. §5 asserts the handler remains a coroutine function.

**The invariant has two directions, and the second was missing from the first draft:**

1. *No event-loop code path calls the tokenizer object owned by the model.* (The defect.)
2. *No worker thread calls the guard's copy.* (Its mirror — a future caller that tokenizes inside
   the `to_thread` block would reproduce the identical defect against the new object while every
   check aimed at direction 1 passes.)

Direction 2 is enforced **at runtime, not by review**: the copy is created on the loop thread, its
thread id is recorded, and the guard raises if it is ever called from another thread. A mistake then
fails loudly and deterministically on the first request instead of rarely and mysteriously under
load — which is the difference between this defect and a caught one.

Plain attribute reads of Python values are outside both directions — `model.max_seq_length` is an
int, not a borrow — and the handler caches it at load anyway. The broader statement ("nothing the
encoder mutates") is deliberately not the invariant: what `encode` mutates is a
sentence-transformers internal and cannot be enumerated. §5 checks the two narrow directions and
states what it cannot see.

**The copy and the model are bound together.** Both are set in the same load step, and nothing else
rebinds the model: a reload path that swapped the model without remaking the copy would leave the
guard validating against the previous checkpoint's tokenizer — the silent divergence this design
rejects the second-`from_pretrained` alternative for. §5 asserts the model is assigned in exactly
one place and that the copy is set there too.

**Serving is gated the same way it already is.** `/embed` answers 503 while the model is absent;
the guard copy is created in the same load step, so if the model is present the copy is too. The
copy cannot fail independently the way a second download could — which is also why this design does
not turn a rare per-request failure into a total outage, the risk the review raised against the
earlier one.

**One counter, so recurrence is not invisible.** `/health` reports `embed_errors`: the number of
requests that failed **inside the embedding step with an unexpected exception** since start.
Explicitly *not* counted — 413 (the guard doing its job, already counted by the re-embed run) and
503 (not ready, which `/health` already reports). It resets on restart, and it does not classify
causes: it answers "has this service failed a request since it started", which is the question
nobody could answer before. The defect was found by a follow-up measurement rather than by anything
the service said about itself; one integer is the smallest thing that changes that. It expands a
published health contract inside a defect SPEC, which is a real cost, and it is taken deliberately
rather than by accident (§2).

**Why not the alternatives**, each live until the measurements:

| alternative | why not |
|---|---|
| One lock around guard + encode | Serializes encoding to fix a collision `encode` does not have with itself (measured, with control). Pays throughput for nothing. |
| Guard inside the `to_thread` block | Sequential *within* a request; across requests, thread A's guard still meets thread B's encode. Does not fix it. |
| Second `AutoTokenizer.from_pretrained` | Re-resolves the checkpoint independently (`name_or_path` is a repo id, verified) → silent divergence, plus a new boot precondition. |
| Character-length heuristic | Removes the tokenizer from the guard but replaces an exact check with an approximation — and exactness is the point of refusing silent truncation. |
| Tokenizer per request | Correct but wasteful: a copy per request for a guard that runs on one thread. |

## 4. Error handling

- **The copy cannot be made** (deepcopy raises) → the service is **not ready**, `/embed` answers 503,
  and `/health.error` carries `guard_tokenizer_unavailable: <exception>`. A sidecar that cannot
  enforce its own length rule must not serve, because the alternative is silently truncated vectors.
  This adds one named error condition and one more reason for `ready: false` — a small contract
  extension, stated rather than smuggled.
- **Over-length input** → 413, unchanged, counted as a failure by the re-embed run.
- **A borrow error surviving anyway** → 500 as today, counted in `embed_errors`; the seam SPEC §4.4
  degrades the vector leg rather than failing search. §5's burst is what would show it.

## 5. Testing

Unit — **no network, no model**: `sentence_transformers` is patched and the fake model carries a
fake tokenizer, so nothing is downloaded and CI runs these on every push.

- **The guard never touches the encoder's tokenizer.** The fake tokenizer raises on call **and
  carries a `__deepcopy__` returning a benign twin** — without that the test is self-defeating,
  since a deep copy of a raising fake also raises (the review caught this in the previous draft).
  The assertion is then exact: the twin was called, the original never was.
- **No event-loop path calls the model's tokenizer** — asserted over the module's source by call
  node. **What this cannot see**, stated because it is the regression guard: aliasing
  (`tok = model.tokenizer`), access through a helper or another module, or `getattr`. It catches the
  shape that occurred, not the class — and §6's acceptance is worded to that, not beyond it.
- **The guard refuses to run off the loop thread** — call it from a worker thread and it raises.
  This is invariant direction 2 (§3), the one a source scan cannot cover.
- **The handler stays a coroutine** (`inspect.iscoroutinefunction`) — what keeps the guard on one
  thread in the first place.
- **The model is bound in exactly one place, and the copy is bound with it** — asserted over the
  source, so a reload path cannot appear without failing this test.
- **Startup asserts parity**, and on more than a number: the copy's `model_max_length` equals the
  model's **and both return the same token count for a fixed probe string**. Equal limits do not
  imply equal tokenization; the counting is what the 413 contract rests on. A mismatch is a
  not-ready condition rather than a silent difference.
- A model that loads while the copy fails leaves `ready` false, names the error, and makes `/embed`
  answer 503.
- `embed_errors` increments on a failed request and appears in `/health`.
- Over-length input still yields 413 (routing and plumbing; the *counting* is checked live below,
  because with a fake tokenizer this test cannot see a truncation-default change).

Against the running service (documented, executed at merge; the model is 2–3 GB and CI does not
download it):

- **The burst that found it, sized so a pass means something.** The original 800 requests produced 4
  failures; a clean 800-request run would happen by luck about 2 % of the time even unfixed. So:
  **2,000 requests at C=4, plus 400 each at C=8 and C=16**, acceptance **zero 500s**, with 2 / 1 / 1
  as the control. At the pooled point estimate (~0.5 %) an unfixed service passes with probability
  ~10⁻⁶; at the low end of the Poisson interval (~0.15 %) it is ~1.5 %. **Both figures pool four
  events across three concurrencies**, and a borrow collision is concurrency-dependent by
  construction — so they are order-of-magnitude, not a computed guarantee. This is why the
  correctness argument rests on the microbenchmark and its positive control (§1) and the burst
  *confirms* it on the real path, rather than the other way round.
- **A live 413**: an input over 8,192 tokens still returns 413 from the running service, and one just
  under does not. This is the check that would catch a truncation-default difference, which the unit
  test structurally cannot.
- **The concurrency sweep re-run at C=1…16.** Peak throughput within **15 %** of the recorded peaks
  (8.82 rps `/embed`, 7.62 rps `/search`). The band is wide because those peaks are single runs
  without a variance estimate. **A breach blocks the merge** until either the cause is identified or
  the baseline is re-measured three times and the new band recorded — "we do not know" is not an
  explanation, it is the trigger for the re-measurement. Judgement sits with the director, as
  everywhere else in this repository.

## 6. Acceptance

- **Zero 500s** across 2,000 requests at C=4 and 400 each at C=8 / C=16, with 2 / 1 / 1 as the
  control and the false-pass bound stated (§5).
- The guard uses a copy of the model's tokenizer. Tests fail if `embed_service/app.py` contains a
  direct call node on `model.tokenizer`, if the guard is invoked off the loop thread, if the handler
  stops being a coroutine, or if the model is bound anywhere but the one load step. **That is the
  exact reach of the checks** — aliased or cross-module access is not covered (§5).
- Startup parity passes on both the limit and a probe token count; an unmakeable copy leaves the
  service not ready with `/embed` at 503. **That is a total-outage failure mode and it is chosen:**
  a deep copy of an already-loaded object either works at every start or fails at every start, so it
  surfaces at deploy rather than drifting into production — unlike a second download, which can fail
  on one restart, and unlike silent truncation, which never surfaces at all.
- `transformers` and `tokenizers` are pinned in the sidecar image, since the fix's premise is a
  property of their deepcopy behaviour.
- A live over-length request still returns 413 and a just-under one does not.
- The concurrency sweep is re-run and recorded next to the previous numbers, within the stated band
  or explained.
- The 413 contract is unchanged. The health contract gains one error condition and one counter (§4).

## 7. Units

1. **The guard's own tokenizer** — deep copy at load with the loop-thread assertion, cached
   `max_seq_length`, startup parity check, readiness and 503 gating, the `embed_errors` counter,
   `transformers`/`tokenizers` pinned in the image, tests as in §5; then the burst, the live 413,
   and the sweep re-run, all recorded in
   `nexus/tests/eval/reports/2026-08-05-sidecar-concurrency.md` alongside the parity and mechanism
   measurements this SPEC cites, so a reviewer can reproduce them.
