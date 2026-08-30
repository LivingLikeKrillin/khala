---
title: Engineering log
description: A dated record of what this system got wrong, how each defect surfaced, and what changed because of it.
---

*Most project histories list what was shipped. This one lists what was **wrong** — because in a system whose whole promise is calibration, the interesting events are the ones where the system, or its measurements, turned out to be lying.*

This page is safe to hand-write, which most of the documentation here is not. Everything else in this repository describes the code as it is now, so it rots the moment the code moves — which is why those pages are [anchored to the sources they describe](https://github.com/LivingLikeKrillin/khala/blob/master/doc-anchors.yml) and checked on every push. A dated record is different. It says what was true on a day, and days do not change.

## Who caught what

Twenty entries below, sorted by what actually surfaced the defect. The shape matters more than the count: automated checks caught the infrastructure problems, measurement caught the data problems, and the single most consequential defect — the one that had passed every automated check for weeks — was caught by one sentence from a person. The most recent ones were found the same way: by checking a claim against the thing it describes — including the newest, where a person's question exposed a capability that had been built and then never wired to anything that reads it.

<svg class="kh-fig" viewBox="0 0 600 214" role="img" aria-label="A timeline from July to August 2026 with three lanes. The 'CI and guards' lane holds four defects, the 'measurement' lane holds twelve, and the 'a person' lane holds four. Density increases sharply through August, with entries clustered at the end of the month. The person lane ends with a question that exposed a capability built but never wired to anything that reads it.">
  <text class="kh-fig-h" x="0" y="14">WHAT SURFACED IT</text>
  <line class="kh-fig-rule" x1="112" y1="34" x2="575" y2="34"/>
  <text class="kh-fig-s" x="0" y="60">CI &amp; guards</text>
  <line class="kh-fig-line" x1="112" y1="60" x2="575" y2="60"/>
  <circle class="kh-fig-verified" cx="189" cy="60" r="3.5"/>
  <circle class="kh-fig-verified" cx="428" cy="60" r="3.5"/>
  <circle class="kh-fig-verified" cx="445" cy="60" r="3.5"/>
  <circle class="kh-fig-verified" cx="548" cy="60" r="3.5"/>
  <text class="kh-fig-rk" x="583" y="60" text-anchor="end">4</text>
  <text class="kh-fig-s" x="0" y="108">measurement</text>
  <line class="kh-fig-line" x1="112" y1="108" x2="575" y2="108"/>
  <circle class="kh-fig-verified" cx="403" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="420" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="462" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="471" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="480" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="522" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="538" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="547" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="556" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="563" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="569" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="575" cy="108" r="3.5"/>
  <text class="kh-fig-rk" x="583" y="108" text-anchor="end">12</text>
  <text class="kh-fig-s" x="0" y="156">a person</text>
  <line class="kh-fig-line" x1="112" y1="156" x2="575" y2="156"/>
  <circle class="kh-fig-verified" cx="197" cy="156" r="3.5"/>
  <circle class="kh-fig-verified" cx="466" cy="156" r="3.5"/>
  <circle class="kh-fig-ah" cx="524" cy="156" r="5"/>
  <circle class="kh-fig-verified" cx="575" cy="156" r="3.5"/>
  <path class="kh-fig-line-acc" d="M524 163 L524 178 L470 178"/>
  <text class="kh-fig-d" x="464" y="178" text-anchor="end">passed every automated check</text>
  <text class="kh-fig-rk" x="583" y="156" text-anchor="end">4</text>
  <line class="kh-fig-rule" x1="112" y1="196" x2="575" y2="196"/>
  <text class="kh-fig-s" x="112" y="207">JUL</text>
  <text class="kh-fig-s" x="378" y="207">AUG</text>
  <text class="kh-fig-s" x="575" y="207" text-anchor="end">2026</text>
</svg>

---

## July — the checks that were not running

### The tests that had never run
**2026-07-10** · `ci(nexus): run the DB-backed tests — and repair the fixtures that never ran`

The database-backed integration tests looked healthy in the sense that nothing was red. They had never executed: a fixture scope mismatch made them fail during setup, which the runner reported as an error the suite tolerated. Months of "passing" told us nothing about the paths that touch a real database.

The repair added a Postgres CI job that runs the full suite against a real server with migrations applied. The rule it left behind: **a skipped test is not a test**, and a net you have never seen catch anything has not been shown to work. Since then, when a guard is added, it gets deliberately broken once to confirm it goes red.

### A test run destroyed a real corpus
**2026-07-10** · `feat(nexus): document lifecycle across web, MCP and CLI + a guard against wiping a real DB`

The suite truncates tables between tests, which is correct for a scratch database. It was pointed at the development database, and the corpus in it was gone.

The fix was not "be careful with the connection string". A database now has to **declare itself disposable** — the suite looks for a marker table and exits with a hard failure if it is absent. Care is not a mechanism; a refusal is.

---

## August — the measurements that were wrong

### The figure in the document was not the figure the run produced
**2026-08-04** · `docs: correct the coverage figure — 232 chunks was wrong, the run says 10`

A coverage number had been written into a document from memory rather than from output. Re-reading the run showed it was off by more than an order of magnitude. Small on its own, and the reason it is here is that it was the first of a pattern: over the following two weeks, **the instrument was wrong more often than the system was**.

### A control that had been specified and skipped overturned a verdict
**2026-08-06** · `fix(ko-eval): run the calibration control that was specified and skipped - it overturned a judgement`

An evaluation design called for a negative control — an input that *should* produce the same result if the effect being claimed were not real. It had been written into the plan and then not run, because the primary result looked convincing. Running it reversed the conclusion.

Standing rule since: **a result without its control is not a result**, and the control is run before the verdict is written down, not after it is doubted.

### A partner's fingerprint came back a month after it was scrubbed
**2026-08-07** · `chore(scrub): remove a partner organisation's fingerprint, and count it on every push`

The repository was scrubbed of identifying details before it went public. A month later they had returned through ordinary work — an address here, a real page identifier there, and, in the blind spot nobody was watching, inside commit messages and pull-request bodies.

A scanner now runs on every push. It reads the API for the current title and body rather than the frozen webhook payload, so an edit cannot slip past it, and it carries negative controls so that a scanner which has stopped detecting anything fails loudly instead of passing quietly. The allowlist takes reasons, not exceptions: when a test later tripped it, the fix was to use synthetic identifiers, **not to add a line to the allowlist** — a list that grows one exception per incident is a hole with a schedule.

### The repository had two schemas
**2026-08-09** · `fix(ci): the recall job never ran migrations, so the repo had two schemas`

One CI job created its database from the baseline file and never applied the migrations on top. It had therefore been testing a schema that no deployment has ever run, and passing.

### Ingestion wrote into a column that nothing searches
**2026-08-11** · `fix(nexus): the corpus never said which generation serves it, so two processes disagreed`

The embedding model, its dimension, and the vector column it writes to are one unit — a *generation*. The documented command, run on the host, resolved that unit from configuration defaults; the container resolved it from environment variables. They disagreed, so a perfectly successful ingestion wrote vectors into a column no query reads. Nothing failed. The documents were simply not findable.

A corpus now **declares its generation in the database, append-only**, and ingestion is refused before a single document is collected if the running process resolves a different one. The same change also established that when chunk text changes, *every* vector column is invalidated — a bug an earlier decision record had declared dead came back the moment a second column was added.

### The number existed, and nobody was ever shown it
**2026-08-11** · `fix(nexus): the coverage number existed, and no one was ever shown it`

Index coverage — how many chunks each retrieval path can actually see — had been computed correctly all along. It was written to the API start-up log, where no human looks. The command people actually type showed nothing, and a gap of 51 chunks sat open for a day.

This is the most frequently repeated shape in this log, and it has now appeared four separate times: **the detector exists, the delivery does not**. The rule that came out of it is that a signal is worth zero until something a person or an agent actually reads is showing it, and that a check on the detector alone stays green when the delivery is deleted — so the test has to run the surface.

### Half the failures were mine
**2026-08-12** · `feat(nexus): measure a second corpus, and find out half the failures are mine`

Running the evaluation against a second corpus split the failures cleanly: some were the system's, and the rest were defects in the grader itself — a label pointing at a document that did not contain the answer, an abstention detector that a fourth phrasing walked straight through, a citation format the verifier could not resolve.

The abstention detector is the instructive one. It had been a list of known refusal phrasings, and the next run produced a phrasing that was not on the list, so an honest refusal was scored as a hallucination. A list of observed strings is not a detector. It was replaced with a **structural** rule: a refusal names the evidence and negates it, which does not depend on having seen the sentence before.

### The grader could no longer tell systems apart
**2026-08-13**

Both evaluation packs reached their ceiling. The scores had gone up over the preceding week — and every point of that gain traced back to fixing the instrument. Retrieval and generation had not been touched.

The two packs were reclassified as **regression nets**, not quality evidence, and the repository stopped citing their totals as a measure of how good the system is. A measure that cannot separate two systems is not measuring them.

### The grader passed a defect it was structurally unable to see
**2026-08-18** · `feat(nexus): tell the user when the evidence does not fit the question`

The automated score said 7.7 out of 8. The team it was deployed to was not using it. Asked why, one person said the answers felt *off* — and that sentence opened a defect that every automated check had passed for weeks.

Reproduced: asked where a tool's name came from, the system filled all ten evidence slots and answered at length with a technology table and an API response shape. Not a hallucination. The citations resolved, the grounding check passed, the fact check passed. **No available measurement could see it.**

The cause was in the fusion step. Reciprocal rank fusion scores a result by `1/(k + rank)`, so it carries *rank* and discards *magnitude* — and both retrieval paths had already computed magnitude to sort by, then thrown it away on return. Restored, the two populations separate cleanly:

| | vector distance | keyword score |
|---|---|---|
| answerable | 0.191 – 0.455 | 2.0 – 4.5 |
| topic present, answer absent | 0.377 – 0.470 | 0.8 – 1.2 |
| outside the corpus | 0.544 – 0.575 | 0.1 – 0.6 |

Weak evidence does not block an answer — it changes the narration contract, so a wrong threshold costs a short answer rather than a wrongly withheld one. The thresholds are recorded as **a hypothesis from seventeen authored questions**, and every request now stores the two magnitudes so that real usage, not invention, can eventually set them.

A correction belongs with this entry: two of the six questions written to represent *topic present, answer absent* turned out to be answerable, and the system answered them correctly with citations. The absence check had been run with the author's vocabulary rather than the corpus's. Re-split, the reading is stronger — but the lesson is that **an absence proved with your own words is not an absence**.

### A document that no retrieval path could read
**2026-08-18** · `fix(nexus): keep a chunk's generation key with the document it belongs to`

Reviving a soft-deleted document restores "only the current generation" of its chunks, decided by comparing a key on the chunk against the document's content hash. Re-ingestion updated the document's hash and never moved the chunk's. So any document that had been edited once carried chunks stuck in the past, and a later delete-then-revive stood the document back up with **zero readable chunks** — listed, counted, and reported healthy while no retrieval path could read a word of it.

The live corpus the team queries had one, with eight more waiting on the same trigger, which is not a human command but a scheduled reconciliation job. The blind spot that hid it is worth naming: coverage is computed over *chunks*, so a document with none is outside the population entirely and reports as fully covered.

### The front page had been describing a retrieval path that changed
**2026-08-21**

The illustration at the top of this site said a query fans out to **three** retrievers which fuse via reciprocal rank fusion. Two legs fuse. The graph lookup runs separately and attaches *after* the diversity cut, contributing nothing to the ranking.

That exact error had already been found and corrected six days earlier — in the agent instruction file, which is anchored to `search/hybrid.py` and therefore watched. The correction never reached the public page for one reason: **the home page was not in the anchor list.** The most-read description of the retrieval architecture was the one thing the drift net was not watching, so it drifted the longest — thirty-four commits to the code it describes.

Both language versions were corrected and both are now anchored. The generalisation is uncomfortable and worth keeping: a net protects exactly what is registered with it, and the pages most likely to be omitted are the ones that feel like marketing rather than documentation — which are also the ones most people read.

### Fifteen out of fifteen, with the change switched off
**2026-08-26** · `feat(nexus): the answer-fact ruler measured mention, not assertion — split them`

A new grader was written to measure something retrieval metrics cannot see: whether the answer actually contains the value the question asks for. It read 15 out of 15. Then the retrieval change it had been built to evaluate was switched off, and it still read 15 out of 15.

Both facts had one cause. A substring test cannot distinguish a value that is claimed from a value that is merely listed. The failing answer wrote `4,000` into a table of what each source says, then closed with "until this is confirmed, no figure can be asserted." The grader counted that as correct.

The replacement asks where the value stands. Either in the lead, meaning the prose before the first table, quote or heading, which is the place the system's own prompt reserves for the answer. Or in a verdict segment, one opened by a conclusive connective. Everything else is laying evidence out.

Three rounds per arm, majority per question, noise band read before any test:

| | with the change | without it | band | gap |
|---|---|---|---|---|
| substring | 15 · 15 · 15 | 15 · 15 · 15 | 0 | **0** |
| assertion | 14 · 13 · 14 | 9 · 9 · 10 | 1 | **5** |

The gap clears the noise. The sign test still does not run: five discordant pairs against a pre-registered minimum of six. All five point one way and none the other, and the claim stops there. More rounds cannot fix it, because discordant pairs are a property of the question set rather than of the sampling.

The rule it left behind is now applied before measuring anything: **ask whether the grader can see the treatment before reading its score.** A grader pinned at 1.000 is not a strong result. It is an absent one. The same pass turned up a second defect in the substring version, which accepts a value that appears only inside a quotation of a superseded policy while the answer concludes something else entirely.

### The instrument was counting our own re-runs
**2026-08-26** · `fix(nexus): the re-ingest signal counted our own re-runs — give it a denominator`

One of the entropy signals counts re-ingest overwrites: documents whose content changed under an existing identity. An accepted architecture decision designates it a demand-pull trigger, and several deferred items are gated on it, so this number decides what gets built.

The day before, that view had been repaired. It aggregated globally, so throwaway evaluation tenants were drowning the live signal: 61,425 duplicate pairs globally against 0 in the live corpus. Splitting it per tenant was the repair.

It was half the repair. The live number reads 53 events, spread across **18 documents**, 38 of them inside three days, in a corpus of 126. Those three days are days the ingestion pipeline was being changed and re-run. The signal was measuring how often we re-ingested the same eighteen documents, not how much the corpus was churning.

The correction adds a denominator instead of redefining the metric. The accepted decision record defines the signal as events, and quietly changing what that column means would put an approved document and the code out of step. Whoever read 53 alone now reads 53 across 18.

What it does not fix is stated in the migration itself. Our re-ingest and a genuine edit both change the content hash, so the two cannot be separated from stored data. Separating them means recording the cause at write time, which is a specification, not a migration.

The uncomfortable part is the sequence. The person who split that view per tenant and the person who missed the second layer are the same, one day apart. **Cleaning half of an instrument makes the other half look clean.**

### The only path that spends money had no ledger
**2026-08-26** · `feat(nexus): book what the screenshot reader spends — the only path that costs money had no ledger`

An ingestion run was reported as costing nothing. It had sent 39 images to a vision provider.

The report was not a lie. It was an **absence**. A spend module existed and was wired into two evaluation scripts, the paths that had once burned a day of paid API calls, and into nothing on the ingestion path. So the figure came from counting by hand, and the hand count missed the pages the loop had died on, which were exactly the pages that generated the calls.

The reads are now booked the way the answer path already books its own: token usage returned from each backend, priced once from the same rate table, accumulated per run, printed when the run ends. Three distinctions are kept apart on purpose, because collapsing any of them produces a number that reads as reassurance:

- a cache hit is not a call, and counting it inflates the spend
- a failure is a call, and not counting it breaks "how many did we send", which is the exact figure that was wrong
- an unknown price is not a free one, so the run names the model that has no rate rather than inventing one

Wiring it surfaced a latent failure worth recording. Passing the new argument unconditionally makes any reader that does not accept it raise a type error, and the extraction path catches every exception per image, so that error would have been swallowed as a read failure. Images would have silently stopped being read while every counter reported a clean run. With no ledger attached the call is now byte-identical to before, and a test pins that property.

**A number produced by hand is not a measurement.** It has no failure mode that anyone can see.

---

## What the log adds up to

**Improvements came from removing defects, not adding technique.** Seven retrieval techniques were tried and measured — multi-hop retrieval, model-driven query rewriting, frequency-based expansion, corpus merging, and others. All seven were rejected on measurement. Every real gain in this period came from removing something broken: a diversity cap that was truncating the correct passage, extraction markers polluting the search index, magnitude discarded at fusion.

**The same shape kept recurring: the detector existed, the delivery did not.** Coverage was computed and never shown. Document-to-code anchors were written for weeks with nothing reading them. Refusal reasons were recorded where only one view could see them. The current rule is that a check on the detector alone is not enough — the test has to run the surface a person actually looks at, and it has to be deliberately broken once to prove it goes red.

**The instrument was wrong more often than the system.** That is not a complaint about the instrument; it is the reason the instrument is treated as a first-class artifact here, with signed labels, pre-registered verdict rules, and a standing prohibition on editing a grader after seeing the score it produced. The sharpest case is the most recent: a grader that read a perfect score and could not see the change it had been written to evaluate, and an entropy signal that was counting our own re-ingests one day after being repaired for a different contamination. Both were found by checking a claim against the thing it describes, which is cheap and is now done on a schedule rather than when something feels wrong.

*This page is a record, not a status board. For what is currently open, see [OPEN.md](https://github.com/LivingLikeKrillin/khala/blob/master/OPEN.md), which counts unresolved items so that it is possible to tell whether they are going up or down.*

### The harness was measuring a path no user takes

**2026-08-29** · `fix(nexus): the harness was measuring a path no user takes`

Two labels passed 5/5 and 4/5 in experiment scripts. Run through the evaluation harness, the same labels failed outright.

Same corpus, same questions, same scoring rules. One thing differed: how the evidence was assembled. The experiments called the function the answer paths use; the harness assembled its own. So the harness was missing both enrichments added that week. **Every number it produced described a system nobody uses.**

Pointing it at the shared function flipped both labels back to passing. That is the proof.

This repo has recorded the shape before — registration behind an execution guard, a copy outside the regression checks, wiring attached to one of three paths. What is new is that the list now includes **the measuring instrument itself**. When measurement takes a different road than production, it stays green while guarding nothing.


### The instrument invented a defect, and I went to fix it

**2026-08-29** · `fix(nexus): a value has surface forms, and one missing form invented a defect`

A label listed its expected value in one spelling. The system answered **correctly** in another. The grader scored three correct answers as misses.

That much is an ordinary label defect. The cost came next. I read the failure as a system defect — *"it holds the evidence and picks the stale side"* — designed a remedy for that defect, wrote a prompt clause, and measured it over five runs per arm. The pre-registered adoption rule rejected it. **Of course it did: there was nothing to fix.**

Reading one failing answer ended it in three minutes. Until then I had been reading only scores.

So a rule was added: **read the failing answer before diagnosing the failure.** A score says which value is missing; it does not say whether that value is really missing. Re-measured with the spellings the system actually writes, the enrichment reads **0/5 → 5/5**, not the 3/5 first reported.


### A change meant to make the harness honest buried a real contradiction

**2026-08-29** · `eval: labels say what they are measured against, and a "fix" that hid a conflict`

The corpus is documents, yet the questions were phrased as *"how does the product behave"*. Under that mismatch, **a correctly cited answer that is wrong about reality scores full marks.** So every label was made to declare its authority, and the questions were rewritten to say *"according to the document"*.

Putting that change under measurement produced this:

| | conflicting document in evidence | answer |
|---|---|---|
| natural phrasing | present | both values, disagreement flagged (2/2) |
| authority prefix | **absent** | one value, stated confidently (2/2) |

The prefix narrowed retrieval and dropped the document holding the contradiction out of the candidate set entirely. The answer was faithful to what it received. Evidence arrival does not vary between runs, so this is not noise.

Reverted. Authority stays metadata. **A label's wording is not a free variable** — change it and retrieval changes. A phrasing meant to make the harness honest had come close to hiding exactly what this tool is built to surface.

### Built, then never read

Asking *"how many characters can a nickname be"* returned two documents with two different numbers. Opening the code settled less than expected: the server does not validate that length at all, and only the column caps it at 20. It was not a question of which document to believe.

What the owner asked for was not a verdict but a juxtaposition — *an implementation may have broken the document, or the document may not have caught up, so tell me both.* Checking whether that capability existed found **three of four layers disconnected**:

| layer | state |
|---|---|
| code value resolver | present |
| code tree mount | present |
| registered concepts | **zero rows** — the seed file targeted a sample app |
| wired into answers | **absent** — reachable only from one dedicated CLI command |

Fixing it surfaced three more. **The resolver read the wrong shape**: `static final` constants only, while in real Java the "how many characters" limits live in `@Size(max = 100)` and `@Column(length = 20)` — so it could reach none of the values we wanted to compare. **I looked for the cost in the wrong place**: the first lookup took 55.9s and I assumed the new parsing was to blame, added a pre-filter, and measured no improvement at all. Split out, it was listing files 50.70s, reading them 5.28s, parsing 0.18s — the cost of walking a bind mount. **Seeding made dead claims look alive**: it printed only `11 loaded`, and a claim that fails to bind is still stored, just without a value.

What comes out now:

```
50 characters — but the code disagrees, so both are given.
⚠ The server's request validation caps this at 500, ten times the document's 50.
Which one is correct cannot be settled from this evidence.
```

Three values diverge: party name 30 vs 100, party introduction 50 vs 500, nickname 12 vs 20. **The system picks neither.** They may both be right at different layers — a product rule of 30, a server guard of 100 and a column of 255 is a real shape in this codebase, not a contradiction.

**Correction (2026-08-31).** Above, I wrote that the nickname had *no server validation at all*. **That was false.** The owner asked *"no limit? not even in the test code?"*, and checking properly found it in four places: the user-facing `UpdateMyBioRequest @Size(max = 20)`, a domain value object `Nickname` that throws above 20, the column `varchar(20)`, and a test asserting that 21 characters fail. **The code is consistently 20.**

What I had looked at were the admin and bot-creation paths only. And missing the user-facing one had a mechanical cause: the regex that finds field declarations required them to begin with `private|protected|public`, and that class uses Lombok, so its fields carry no modifier.

```java
@Getter
public class UpdateMyBioRequest {
    @Size(max = 20, message = "닉네임은 20자를 초과할 수 없습니다")
    String nickname;          // no modifier
```

So I did not read an absence — **I read a failure to read as an absence.** A tool that cannot tell those two apart, wired to something that speaks with confidence, produces exactly this. It now requires a type token and no modifier, with the real-world shape pinned in a test. Seeded claims went from 4 of 7 bound to 6 of 7.

⛔ One limitation belongs next to it: the value object's `if (value.length() > 20) throw …` is neither a constant nor an annotation, so it is **still unreadable**. That the 20 holds in three layers is something a person confirmed, not something the tool produced.

**Sweep (2026-08-31).** Having corrected it, I checked all eleven documented values against the code. **Four agree, six diverge, one has no code site I could find** — the "three" I had written was not a sweep. The history then supplies a clue the values alone cannot: four of the divergences (party name 100, party introduction 500, DJ minimum 1 minute, playlist name 100) arrived in **one commit** that added validation to eighteen DTOs at once. That reads as blanket defaults rather than per-field product decisions. ⛔ The one I could not place is recorded as **"not found", not "absent"** — having just been wrong by confusing exactly those two.
