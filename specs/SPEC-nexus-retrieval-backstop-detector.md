---
id: SPEC-nexus-retrieval-backstop-detector
type: spec
title: Run the hash check unattended — one small job, and the findings from two detector
  designs that failed
status: approved
linked_adrs:
- ADR-0009
- ADR-0008
- ADR-0002
tags:
- arbiter
- governance
- ci
- integrity
- process
date: '2026-08-05'
approved_by: LivingLikeKrillin
reviewed_at: '2026-08-05T09:28:49Z'
content_hash: sha256:fc547f9cf0231ce8f7f57e73600a66f26af758c011a990e57381ecf88e85e539
---

## 0. How this document got small

Four gate rounds. Two detector designs, then a disposition of impossibility, and each round refuted a
load-bearing claim of the one before — the last two being claims *this* document made about its own
mechanism. The pattern was the problem: every round added a claim, and the added claim was what the
next round killed.

So the claim surface is cut to what survives. **This SPEC ships one CI job and records four rounds of
findings. It discharges nothing.**

## Backstop record

```yaml
backstop:
- row: adr-0008-retrieval-stack
  reread: performed 2026-08-05 — ADR-0008 §5 and its resume-condition table were read; conditions
    (a) and (c) prescribe their own re-reads and were NOT performed
  clause: none
  ruling: does-not-fire
  declared_by: LivingLikeKrillin
  declared_at: '2026-08-05'
  reason: >-
    Judged case by case, not by rule: one CI job over governance artifacts.
```

**What this record is worth, stated exactly.** The ruling was made in conversation on 2026-08-05 and
these fields report it. **Nothing here proves that.** An earlier draft claimed approval adds
"tamper-evidence"; it does not — the stamped `content_hash` lives in frontmatter, which the hash does
not cover, so a body edit accompanied by a recomputed stamp is one commit with no detector (§3). And
on 2026-08-05, in this session, an agent wrote `declared_by: LivingLikeKrillin` for a ruling the
director had never made; review caught it, and §3's job would not have. **The reviewer is being asked
to take the author's word.** That is the same posture §2 uses to reject the detector designs, and it
is stated rather than dressed up.

## 1. Non-goals — including the item this SPEC was supposed to answer

- **ADR-0009's detector item is NOT discharged.** An earlier draft closed it with a disposition of
  impossibility. Two objections retire that: ADR-0009's stated outcomes are *"a mechanism that detects
  backstop events, **or a declaration made after the fact**"*, and an after-the-fact declaration is
  **cooperative by construction** — it was never a detection problem, so an impossibility argument
  about detection does not reach it. And the argument's universal negative was never established
  (§2). The item stays **open**, with its trigger spent (§4).
- **ADR-0009's "materially expand" predicate item**: not addressed.
- **Detecting backstop events**: nothing here does that.
- **Tamper-evidence**: §3 does not provide it.

## 2. Findings from the two designs that failed

Recorded for whoever picks the item up, as facts about the substrate rather than as a verdict on it.

**Design 1 — a CI check over the PR diff.** Killed by the repo's order: SPECs are approved and merged
*before* implementation, so the governing SPEC is untouched on the implementation branch. "The branch
must carry a SPEC with a record" fails on every correctly-gated change, and satisfying it means
editing an approved SPEC — breaking its hash.

**Design 2 — a rule inside the Arbiter gate.** Better placed: the gate knows the approved SPEC. What
it hangs from does not survive:

- `.arbiter/active.json` is gitignored local runtime state — invisible to CI, and the hook can be off;
- `linked_adrs` is a line the author writes (ADR-0008 §7's precedent: #143 shipped a freshness TTL
  with `linked_adrs: []`);
- frontmatter — `status`, `approved_by`, `content_hash` — is outside the body hash
  (`artifacts.py:51`, `hashing.py:10`);
- the review sidecar is an ordinary file editable in the same commit;
- matching would be per-row, so one `does-not-fire` record unlocks a SPEC's whole implementation.

**What was NOT examined**, and therefore what no one should treat as ruled out: CODEOWNERS and branch
protection; a merge-diff glob over `nexus/nexus/search/` and friends resolving the governing SPEC from
the ledger; model-name and requirements diffs; and the `embed_health` / `reembed status` outputs that
[[ADR-0009]] already records as machine-readable evidence of an embedding generation change. An
earlier draft asserted "no signal exists" while leaving these unchecked — and withdrew a *different*
universal negative in the same document for exactly that defect.

## 3. What ships — `governance (ledger integrity)`

**One job. It recomputes `hashing.content_hash(body)` for every artifact whose frontmatter `status` is
`approved` or `accepted`, and fails on a mismatch or a missing stamp.**

**Read-only, and that is a requirement, not a description.** `ledger.status()` performs the same
comparison but, for SPECs, **rewrites the file** — resetting `status` to `in_review` and saving
(`ledger.py:73-77`); only ADRs get `tampered: True`. Detection there edits the evidence. The job
therefore recomputes the hash itself and never calls `status()`, and §5 pins that the run leaves every
file byte-identical.

**What it detects: an edit that did not update the stamp.** That is the ADR-0009 §Context case — an
in-place edit to an accepted ADR, caught when the ledger reported `tampered`. Arbiter already
implements this; what is missing is that **nothing runs it unattended**, so it fires only when someone
happens to type `arbiter status`.

**What it does not detect**, each disclosed because a green check would otherwise be read as covering
it:

1. a body edit with the stamp recomputed in the same commit — no detector, and this is why §0 refuses
   the word *tamper-evidence*;
2. `status: approved` → `draft`, which silently removes a file from scope;
3. deletion of the frontmatter `id`, which moves a file from checked to skipped.

**Selection reads frontmatter, not the ledger**, and that is why (2) and (3) exist. A ledger-driven
selector would remove them but would also skip artifacts whose bodies disagree with the ledger —
ADR-0009 records that seven of eight ADR bodies do. The choice is stated so the two readings are not
confused; an earlier draft described one job in one section and the other job in another.

**Coverage is pinned by a manifest, not by a floor.** `governance/integrity-manifest.txt` lists the
artifact ids in scope; the job fails if any listed id is absent, unparseable, or no longer selected.
An earlier draft used a floor of 30 against 39 artifacts, which left nine exemptible by (2) or (3)
with the build still green — and "the skipped file is named in the output" was not a failure
condition at all. Adding an artifact to the manifest is a reviewable one-line diff; removing one is
too.

**Measured 2026-08-05: 39 approved/accepted artifacts, 0 mismatches.** The measurement used a
throwaway script, not the shipped one — this SPEC precedes its implementation, per the repo's order —
so it is reproducible only in the sense that the algorithm is three lines and is stated above. The
committed job is what makes it reproducible thereafter.

**Negative control, because zero failures is not evidence of teeth.** A character inserted mid-word
and a changed digit are both **flagged**; a whitespace-only edit is **not**, because `_normalize`
rstrips lines and strips leading and trailing newlines by design.

## 4. What is left open, and for whom

| item | state |
|---|---|
| ADR-0009's detector item | **open.** Its trigger (`linked_adrs`) is spent by this round; nothing guarantees another ADR-0008-linked SPEC. Whether an after-the-fact declaration discharges it is the owner's call. |
| ADR-0009's "materially expand" predicate | **open**, untouched |
| Propagation | A reader of ADR-0009 alone sees both items open, correctly. If any disposition is later made, it needs a successor record or an `adr/README.md` pointer — the gap ADR-0009 was written to close for ADR-0008 §6 |
| Frontmatter outside the content hash | **Named, unowned.** Repository-wide. ADR-0009 refused to dispose of a cross-cutting gap "in passing, in a record about something else"; the same restraint applies here. Candidate fixes: hash the frontmatter; move approval facts into the hashed region and re-stamp; or accept it and record that |
| This SPEC opens a direction without a gate declaration | ADR-0008 §3 item 3 (citing ADR-0002) asks that a new direction's first SPEC carry a director's gate declaration. This one carries a `does-not-fire` backstop ruling, which is a different construct. **Stated as a gap, not papered over** |

Owner for all of the above: **LivingLikeKrillin**.

## 5. Tests

- An approved artifact whose body is edited without re-stamping → fails, naming the file.
- **Read-only**: a run over a repository containing a mismatched SPEC leaves every file
  byte-identical — the guard against a later refactor routing the check back through `status()`,
  which would downgrade the artifact while going red.
- **Boundary set**: a whitespace-only edit does **not** fail; a single changed character, a changed
  digit, a deleted word, an internal double space collapsed, and a changed heading case **must** fail.
  Pinning only the green half would let a later widening of `_normalize` hide more edits with every
  test still passing.
- Missing `content_hash` on an approved artifact → fails.
- A `draft`/`in_review` artifact with a mismatched hash → passes (out of scope).
- A manifest id that is absent, unparseable, or no longer selected → fails. Covers bypasses (2) and
  (3) from §3.
- The job passes over the repository as it stands, and reports the ids it checked.

## 6. Risks

- **The green check will be over-read.** §3's three disclosed non-detections are the mitigation, and
  the job's name — *ledger integrity*, not *backstop detection* — is chosen not to invite the
  misreading.
- **The manifest can drift** — an artifact added and not listed is unchecked. The job reports what it
  checked, which makes the omission visible in the log but does not fail the build.
- **The whitespace blind spot is now pinned by a test**, which freezes it rather than bounding it.
  Trailing whitespace is semantic in Markdown (two spaces are a hard break), so an edit that changes
  rendering passes by design.
