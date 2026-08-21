---
title: Engineering log
description: A dated record of what this system got wrong, how each defect surfaced, and what changed because of it.
---

*Most project histories list what was shipped. This one lists what was **wrong** — because in a system whose whole promise is calibration, the interesting events are the ones where the system, or its measurements, turned out to be lying.*

This page is safe to hand-write, which most of the documentation here is not. Everything else in this repository describes the code as it is now, so it rots the moment the code moves — which is why those pages are [anchored to the sources they describe](https://github.com/LivingLikeKrillin/khala/blob/master/doc-anchors.yml) and checked on every push. A dated record is different. It says what was true on a day, and days do not change.

## Who caught what

Thirteen entries below, sorted by what actually surfaced the defect. The shape matters more than the count: automated checks caught the infrastructure problems, measurement caught the data problems, and the single most consequential defect — the one that had passed every automated check for weeks — was caught by one sentence from a person.

<svg class="kh-fig" viewBox="0 0 580 214" role="img" aria-label="A timeline from July to August 2026 with three lanes. The 'CI and guards' lane holds four defects, the 'measurement' lane holds six, and the 'a person' lane holds three. Density increases sharply through August. The final entry in the person lane, in August, is the evidence-fit defect that every automated check had passed.">
  <text class="kh-fig-h" x="0" y="14">WHAT SURFACED IT</text>

  <line class="kh-fig-rule" x1="112" y1="34" x2="560" y2="34"/>

  <text class="kh-fig-s" x="0" y="60">CI &amp; guards</text>
  <line class="kh-fig-line" x1="112" y1="60" x2="560" y2="60"/>
  <circle class="kh-fig-verified" cx="189" cy="60" r="3.5"/>
  <circle class="kh-fig-verified" cx="428" cy="60" r="3.5"/>
  <circle class="kh-fig-verified" cx="445" cy="60" r="3.5"/>
  <circle class="kh-fig-verified" cx="548" cy="60" r="3.5"/>
  <text class="kh-fig-rk" x="568" y="60" text-anchor="end">4</text>

  <text class="kh-fig-s" x="0" y="108">measurement</text>
  <line class="kh-fig-line" x1="112" y1="108" x2="560" y2="108"/>
  <circle class="kh-fig-verified" cx="403" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="420" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="462" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="471" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="480" cy="108" r="3.5"/>
  <circle class="kh-fig-verified" cx="522" cy="108" r="3.5"/>
  <text class="kh-fig-rk" x="568" y="108" text-anchor="end">6</text>

  <text class="kh-fig-s" x="0" y="156">a person</text>
  <line class="kh-fig-line" x1="112" y1="156" x2="560" y2="156"/>
  <circle class="kh-fig-verified" cx="197" cy="156" r="3.5"/>
  <circle class="kh-fig-verified" cx="466" cy="156" r="3.5"/>
  <circle class="kh-fig-ah" cx="524" cy="156" r="5"/>
  <path class="kh-fig-line-acc" d="M524 163 L524 178 L470 178"/>
  <text class="kh-fig-d" x="464" y="178" text-anchor="end">passed every automated check</text>
  <text class="kh-fig-rk" x="568" y="156" text-anchor="end">3</text>

  <line class="kh-fig-rule" x1="112" y1="196" x2="560" y2="196"/>
  <text class="kh-fig-s" x="112" y="207">JUL</text>
  <text class="kh-fig-s" x="378" y="207">AUG</text>
  <text class="kh-fig-s" x="560" y="207" text-anchor="end">2026</text>
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

Index coverage — how many chunks each retrieval leg can actually see — had been computed correctly all along. It was written to the API start-up log, where no human looks. The command people actually type showed nothing, and a gap of 51 chunks sat open for a day.

This is the most frequently repeated shape in this log, and it has now appeared four separate times: **the detector exists, the delivery does not**. The rule that came out of it is that a signal is worth zero until something a person or an agent actually reads is showing it, and that a check on the detector alone stays green when the delivery is deleted — so the test has to run the surface.

### Half the failures were mine
**2026-08-12** · `feat(nexus): measure a second corpus, and find out half the failures are mine`

Running the evaluation against a second corpus split the failures cleanly: some were the system's, and the rest were defects in the ruler itself — a label pointing at a document that did not contain the answer, an abstention detector that a fourth phrasing walked straight through, a citation format the verifier could not resolve.

The abstention detector is the instructive one. It had been a list of known refusal phrasings, and the next run produced a phrasing that was not on the list, so an honest refusal was scored as a hallucination. A list of observed strings is not a detector. It was replaced with a **structural** rule: a refusal names the evidence and negates it, which does not depend on having seen the sentence before.

### The ruler ran out of scale
**2026-08-13**

Both evaluation packs reached their ceiling. The scores had gone up over the preceding week — and every point of that gain traced back to fixing the instrument. Retrieval and generation had not been touched.

The two packs were reclassified as **regression nets**, not quality evidence, and the repository stopped citing their totals as a measure of how good the system is. A measure that cannot separate two systems is not measuring them.

### The ruler passed a defect it was structurally unable to see
**2026-08-18** · `feat(nexus): tell the user when the evidence does not fit the question`

The automated score said 7.7 out of 8. The team it was deployed to was not using it. Asked why, one person said the answers felt *off* — and that sentence opened a defect that every automated check had passed for weeks.

Reproduced: asked where a tool's name came from, the system filled all ten evidence slots and answered at length with a technology table and an API response shape. Not a hallucination. The citations resolved, the grounding check passed, the fact check passed. **No available measurement could see it.**

The cause was in the fusion step. Reciprocal rank fusion scores a result by `1/(k + rank)`, so it carries *rank* and discards *magnitude* — and both retrieval legs had already computed magnitude to sort by, then thrown it away on return. Restored, the two populations separate cleanly:

| | vector distance | keyword score |
|---|---|---|
| answerable | 0.191 – 0.455 | 2.0 – 4.5 |
| topic present, answer absent | 0.377 – 0.470 | 0.8 – 1.2 |
| outside the corpus | 0.544 – 0.575 | 0.1 – 0.6 |

Weak evidence does not block an answer — it changes the narration contract, so a wrong threshold costs a short answer rather than a wrongly withheld one. The thresholds are recorded as **a hypothesis from seventeen authored questions**, and every request now stores the two magnitudes so that real usage, not invention, can eventually set them.

A correction belongs with this entry: two of the six questions written to represent *topic present, answer absent* turned out to be answerable, and the system answered them correctly with citations. The absence check had been run with the author's vocabulary rather than the corpus's. Re-split, the reading is stronger — but the lesson is that **an absence proved with your own words is not an absence**.

### A document that no retrieval leg could read
**2026-08-18** · `fix(nexus): keep a chunk's generation key with the document it belongs to`

Reviving a soft-deleted document restores "only the current generation" of its chunks, decided by comparing a key on the chunk against the document's content hash. Re-ingestion updated the document's hash and never moved the chunk's. So any document that had been edited once carried chunks stuck in the past, and a later delete-then-revive stood the document back up with **zero readable chunks** — listed, counted, and reported healthy while no retrieval leg could read a word of it.

The live corpus the team queries had one, with eight more waiting on the same trigger, which is not a human command but a scheduled reconciliation job. The blind spot that hid it is worth naming: coverage is computed over *chunks*, so a document with none is outside the population entirely and reports as fully covered.

### The front page had been describing a retrieval path that changed
**2026-08-21**

The illustration at the top of this site said a query fans out to **three** retrievers which fuse via reciprocal rank fusion. Two legs fuse. The graph lookup runs separately and attaches *after* the diversity cut, contributing nothing to the ranking.

That exact error had already been found and corrected six days earlier — in the agent instruction file, which is anchored to `search/hybrid.py` and therefore watched. The correction never reached the public page for one reason: **the home page was not in the anchor list.** The most-read description of the retrieval architecture was the one thing the drift net was not watching, so it drifted the longest — thirty-four commits to the code it describes.

Both language versions were corrected and both are now anchored. The generalisation is uncomfortable and worth keeping: a net protects exactly what is registered with it, and the pages most likely to be omitted are the ones that feel like marketing rather than documentation — which are also the ones most people read.

---

## What the log adds up to

**Improvements came from removing defects, not adding technique.** Seven retrieval techniques were tried and measured — multi-hop retrieval, model-driven query rewriting, frequency-based expansion, corpus merging, and others. All seven were rejected on measurement. Every real gain in this period came from removing something broken: a diversity cap that was truncating the correct passage, extraction markers polluting the search index, magnitude discarded at fusion.

**The same shape kept recurring: the detector existed, the delivery did not.** Coverage was computed and never shown. Document-to-code anchors were written for weeks with nothing reading them. Refusal reasons were recorded where only one view could see them. The current rule is that a check on the detector alone is not enough — the test has to run the surface a person actually looks at, and it has to be deliberately broken once to prove it goes red.

**The instrument was wrong more often than the system.** That is not a complaint about the instrument; it is the reason the instrument is treated as a first-class artifact here, with signed labels, pre-registered verdict rules, and a standing prohibition on editing a ruler after seeing the score it produced.

*This page is a record, not a status board. For what is currently open, see [OPEN.md](https://github.com/LivingLikeKrillin/khala/blob/master/OPEN.md), which counts unresolved items so that it is possible to tell whether they are going up or down.*
