---
id: SPEC-arbiter-status-is-read-only
type: spec
title: status() must not edit what it reports — flag a stale SPEC stamp the way an
  ADR already is
status: in_review
linked_adrs:
- ADR-0003
tags:
- arbiter
- governance
- integrity
date: '2026-09-05T09:52:52Z'
---

## 1. Goal

`Ledger.status()` reads like a query and is wired like one — the CLI `status` command, the MCP
`status` tool, `index()`, and the pre-tool-use gate all call it. For SPECs it also **writes**:
an approved SPEC whose stamped `content_hash` no longer matches its body is reset to `in_review`
and saved (`ledger.py:73-77`).

Two changes ship together, and the second is a behaviour change in its own right rather than a
consequence of the first (I-014):

1. **`status()` never writes.** SPECs are flagged, the way ADRs already are.
2. **`index()` groups on the report instead of on disk**, and no artifact the report marks
   `needs_review` or `tampered` is grouped under 승인 — for either artifact type (§3.2).

**It is not a tidying change**, which is why it is a SPEC and not a PR. Two tests pin the current
behaviour deliberately (§5), and an approved SPEC's prose is written around it (§2.4). The claim
here is that the write costs more than it buys, and the evidence is that the codebase already
pays to work around it twice.

**Counts used below, with their denominators** (I-012), all measured 2026-09-05:

| number | what it counts |
|---|---|
| **64** | artifacts carrying a frontmatter `id` — 54 SPECs + 10 ADRs; what `_all_paths()` yields |
| **60** | of those, the ones stamped `approved`/`accepted`; what `ledger_integrity.py` selects |
| **4 of 53** | rows in the hand-maintained table in `specs/README.md` against SPEC files before this one |

## 2. What exists

### 2.1 The write, and who triggers it

```
ledger.py:68-79   approved/accepted artifact whose stamp is missing or mismatched
                    SPEC -> meta["status"] = in_review; a.save(); needs_review=True
                    ADR  -> tampered=True                      (no write)
```

Four callers reach it:

| caller | when it runs |
|---|---|
| `cli.py:77` — `arbiter status` | a person types it |
| `server.py:40` — MCP `status` tool | an agent calls it |
| `ledger.py:105` — `index()` | index generation (`# repair first`) |
| `gate.py:48` — `check_gate` | **every `Write`/`Edit`**, via `hooks/pretooluse_gate.py:55` |

The fourth is the one worth stating plainly. `check_gate` calls `ledger.status()` with **no id**,
so every guarded file edit walks all 64 artifacts, and a SPEC whose stamp has gone stale is
rewritten from inside an unrelated edit to an unrelated file.

**How often, exactly — corrected at critique (I-001).** An earlier draft claimed that once an
artifact drifts, *every subsequent edit anywhere in the repo* rewrites that file. That is wrong,
and the harm is smaller than it claimed. The write demotes the artifact to `in_review`, which no
longer satisfies the `status in (APPROVED, ACCEPTED)` guard at `ledger.py:68`, so the branch is
not re-entered. Measured over a scratch ledger holding one drifted SPEC — file digest `de4bf6f0`
before, `886660f9` after the first `status()`, identical across two further calls. **The write
fires once per drift event.**

What survives the correction is the shape, not the volume: the rewrite is unannounced, it is
attributed to whoever happened to be editing something else, and it lands in their working tree.
The argument of this SPEC does not rest on frequency — it rests on §2.3 and §2.4.

### 2.2 ADRs already do the read-only thing

The same method, five lines apart, handles ADRs by flagging `tampered: True` and leaving the file
alone. One comparison, two dispositions.

**The obvious justification, taken seriously (I-006).** An earlier draft called the asymmetry
"incidental" on the grounds that no document explains it — treating silence as evidence, which it
is not. The justification a reviewer would reach for is that **an accepted ADR is immutable while
a SPEC is a working document**, so resetting a SPEC is cheap and resetting an ADR would destroy
the record. That is a real difference and it does explain why the ADR branch must not write. It
does not explain why the SPEC branch must:

- The demotion is not an edit to the document. Both branches leave the body untouched; what
  differs is only whether the tool **persists its own finding** into the artifact's frontmatter.
- The reason a detector should not write is not the document's mutability. It is that the
  detector edits the evidence it reports on — `SPEC-nexus-retrieval-backstop-detector` §3 states
  exactly this, and it applies identically to a mutable document.
- If cheapness of correction were the reason, the natural design is to demote **and announce it**,
  not to demote silently from inside a gate check that the author did not invoke.

**The history does not settle it.** `git log -S 'accepted ADR is immutable: flag, never reset' --
arbiter/src/khala/arbiter/ledger.py` returns one commit, `f94632e` — the initial public snapshot.
The pre-public history was rewritten at the 2026-07-01 public transition, so the original
rationale is not recoverable from this repository. This review is where it gets decided, which is
stated rather than hidden.

### 2.3 The demoted status says something that did not happen

`adr/README.md:68` and `specs/README.md` both define the value being written:

> **in_review** — critique opened, dispositions pending

A SPEC demoted by a stale stamp has no open critique and no pending dispositions.

**Why the same word is tolerable in the report but not in the file (I-005).** The critique is
right that the objection, stated as "the value is untrue", applies to the report too — §3.1 keeps
emitting `in_review` there and §3.3 has the gate depend on it. The distinction being claimed is
narrower than "true/false":

- The **report** is a computed view that lives for the duration of a call. Its `status` answers
  "what does this artifact effectively count as right now", and `check_gate` consumes it
  immediately and discards it. The artifact asserts nothing.
- The **file** is a durable record that every other reader — a person opening it,
  `ledger_integrity.py`, the index — treats as the artifact's own claim about itself. Writing
  `in_review` there makes the artifact assert a lifecycle event that never occurred.

The report's reuse of the word is still imprecise, and §4 keeps the vocabulary out of scope, so
that imprecision is **knowingly retained, not defended**. If a reviewer wants it fixed, that is
the successor record §4 names.

### 2.4 The cost is already being paid, twice

**Once in a duplicate implementation.** `SPEC-nexus-retrieval-backstop-detector` §3 states:

> Read-only, and that is a requirement, not a description. `ledger.status()` performs the same
> comparison but, for SPECs, **rewrites the file** … Detection there edits the evidence. The job
> therefore recomputes the hash itself and never calls `status()`

`scripts/ledger_integrity.py` exists in its current shape because of this write, and that SPEC's
§5 pins a test specifically to stop a later refactor routing the check back through `status()`.
So the repository maintains two implementations of "does this body still match its stamp".

**Once in detection quality.** `ledger_integrity.py` only inspects the 60 stamped artifacts. A
demotion moves the artifact out of that set, so the precise finding — `MISMATCH: body no longer
matches its stamp` — is replaced by the manifest's indirect one, `listed in the manifest but not
selected`. Before the manifest covered every stamped artifact (2026-09-05, 42 of the 60 listed)
an unlisted demoted SPEC produced **no finding at all**.

## 3. Design

### 3.1 `status()` never writes

`ledger.py:73-79` collapses to the ADR branch for both types: set the report entry and move on.

- SPEC with a missing or mismatched stamp → `needs_review: True`, `status` in the report is the
  computed `in_review`, the file is untouched.
- ADR → `tampered: True`, unchanged from today.

The report's shape does not change, so no caller's reading of it changes.

**`needs_review` gets a consumer (I-004).** The critique is right that today it is unread data:
`grep -rn needs_review` over the repository returns the two lines in `ledger.py` that initialise
and set it, and four lines in tests (three assertions and one test name) — **no production reader
at all**. Under this SPEC it acquires two:

- `index()` groups on it (§3.2), so it decides which heading a SPEC appears under;
- `cli.py:77` prints it, so `arbiter status` distinguishes "in review because someone opened a
  critique" from "in review because the stamp went stale" instead of showing one word for both.

Without those two, §2.3's claim that `needs_review` is "the honest name for the same fact" would
name a field nothing reads.

### 3.2 `index()` groups on the report, and 승인 means stamped

This is the part that breaks quietly if it is forgotten. `index()` today calls `status()` to
repair, then **re-reads every artifact from disk** and groups by `a.status` (`ledger.py:105-109`).
With the write gone, a SPEC with a broken stamp still says `approved` on disk and would be listed
under 🟢 승인 — a silent regression in exactly the surface a reviewer looks at.

**The invariant, stated for both types (I-002).** Grouping on report `status` alone is not
sufficient, and the critique caught this: a tampered ADR keeps report `status: accepted` — its
status is deliberately never recomputed, because the record is immutable — and only carries
`tampered: True`. Grouping on status alone would file it under 승인.

> **No artifact the report marks `needs_review` or `tampered` is grouped under 🟢 승인.**

The 승인 group means "stamped and the stamp still matches". Everything else goes to 검토중, with
the reason distinguishable from the report.

**This part is a fix, not a repair of something this SPEC breaks.** Today the index already files
a tampered ADR under 승인, because it reads `accepted` from disk. The change lands in the same
lines and is included deliberately rather than left as a known-wrong neighbour.

### 3.3 Nothing changes for the gate

`check_gate` reads `entry.get("status")` out of the report (`gate.py:49-51`), which is the
computed value. A SPEC with a stale stamp still resolves to `in_review`, still fails the
`in ("approved", "accepted")` test, and still blocks implementation. The gate never needed the
file to be rewritten; it needed the comparison.

### 3.4 What is deliberately given up

An artifact whose stamp is stale keeps displaying `status: approved` to anyone who opens the file
without running Arbiter. That is a real loss, accepted for three reasons.

**The stamp, not the word, is the claim.** `status: approved` alongside `content_hash: sha256:…`
is one assertion: *this body was approved at this digest*. It is a record of something that
happened, and it remains true of the digest it names. A body that has since diverged makes the
pair self-invalidating and machine-detectable. `status` alone was never the claim.

**Reconciliation with ADR-0003's canonical tier (I-010).** ADR-0003 binds canonical standing to
an approval gate, a `content_hash`, and a vouch that goes stale when the artifact changes. §3.4
does not weaken that — it relies on it: divergence is exactly the staleness ADR-0003 designs for,
and the pair above is the mechanism that makes it visible. What this SPEC does **not** provide is
a vouch-side staleness signal on the Adept side; nothing here emits one, and none is claimed.
That gap exists today and is unchanged by this SPEC.

**CI checks it, on these triggers, and not on others (I-007).** `.github/workflows/ci.yml:44-45`
defines job `governance` / `name: governance (ledger integrity)`, running
`scripts/ledger_integrity.py`. The workflow's `on:` block is `push: branches: [master, main]` and
`pull_request: branches: [master, main]`. So the honest statement is **every push to `master`/`main`
and every pull request targeting them** — not "every push". A commit on a feature branch with no
open PR is not checked until one exists. §2.4 additionally notes the selection dependence of that
job, now closed by the manifest covering all 60 stamped artifacts.

**Accepted ADRs have always behaved this way**, which is the strongest evidence the loss is
survivable: the in-place amendment of ADR-0008 was caught on 2026-08-05 by exactly this read-only
path.

### 3.5 Artifacts already demoted on disk (I-003)

Removing the write does not un-demote anything. A SPEC previously reset by `status()` keeps
`status: in_review` in its frontmatter with no path back to `approved` and, in the file alone, no
way to tell it from a genuinely critiqued SPEC.

**The discriminator is the sidecar.** A critique writes `.reviews/<id>.md` (`critique.py:47`); a
`status()` demotion writes nothing there. So an artifact that is `in_review` **with no sidecar**
was demoted, not critiqued.

**Measured 2026-09-05, before the change lands:** 3 artifacts are `in_review` — this SPEC, plus
`SPEC-nexus-code-semantic-cards` and `SPEC-nexus-doc-code-anchors`, **both of which carry a
sidecar**. Nothing in the tree is stranded, so **no migration code ships**. The rule and the
measurement are recorded here so the claim is re-runnable rather than remembered, and §5 pins the
discriminator so a future stranded artifact is nameable.

## 4. Non-goals

- **The status vocabulary is not touched.** Adding a distinct value for "approved but the stamp
  went stale" is a change to the lifecycle vocabulary, which is defined in `adr/README.md:68` and
  `specs/README.md`, and it would need its own record. **Corrected at critique (I-008):** an
  earlier draft attributed that vocabulary to ADR-0003. ADR-0003 defines the bimodal
  stream/canonical lifecycle and the debt-repayment loop; it does not define
  `in_review`/`approved`/`accepted`, and citing it as the blocking authority claimed more than it
  holds. (The related claim that ADR-0003 is merely *proposed* was **rejected** — its frontmatter
  reads `accepted`, and `adr/README.md` states that frontmatter is authoritative and that frozen
  bodies still read "Proposed".)
- **`ledger_integrity.py` is not merged back into `status()`.** With `status()` read-only the
  duplication becomes removable in principle, but `SPEC-nexus-retrieval-backstop-detector` §5
  pins the separation on purpose and unpinning it is a separate argument. This SPEC only removes
  the reason the workaround was needed.
- **`check_gate` scanning all 64 artifacts on every edit is not addressed.** Removing the write
  removes the harm; the full scan remains a performance question for another record.

## 5. Test plan

Two existing tests assert the file is rewritten and must be inverted — they are the behaviour
being changed, so they are named here rather than quietly edited:

| test | today | after |
|---|---|---|
| `test_ledger.py:53` `test_status_repairs_tampered_approved_spec` | `Artifact.load(a.path).status == IN_REVIEW` | file byte-identical; report says `in_review` + `needs_review` |
| `test_ledger.py:142` `test_status_flags_approved_spec_missing_hash_as_needs_review` | same | same |

Renaming the first (`repairs` → `flags`) is part of the change.

New coverage:

1. **`status()` leaves every file byte-identical.** Hash the whole ledger before and after a
   `status()` call over a tree containing one mismatched SPEC, one unstamped approved SPEC and
   one tampered accepted ADR. This is the assertion that would have failed before the change.
2. **`index()` puts a stale-stamped SPEC under 검토중, not 승인.** The §3.2 regression, pinned
   directly.
3. **`index()` puts a tampered ADR under 검토중, not 승인.** The I-002 half. Written as its own
   test rather than a second assertion, because the two travel through different report fields
   (`needs_review` vs `tampered`) and a single test would let one carry the other.
4. **`check_gate` still refuses** on a SPEC whose stamp is stale, with the file left unmodified —
   the gate's behaviour and the read-only property asserted in one test, because the risk is
   that fixing one silently drops the other.
5. **`arbiter status` output distinguishes the two reasons** for `in_review`, per §3.1 — the
   `needs_review` consumer, pinned so it cannot regress to unread data.
6. **The §3.5 discriminator holds on the real tree**: every `in_review` artifact has a sidecar in
   `.reviews/`. This is a check over the repository rather than a fixture, so it fails the day an
   artifact is stranded.
7. **A negative control**: a tree with no mismatches produces an unchanged report and unchanged
   files, so test 1 cannot pass by the ledger being empty.

## 6. Risks

- **Something outside the arbiter package reads `status:` from frontmatter and assumes it
  self-corrects.** *Search method, recorded (I-011):* `grep -rn` for `meta.get("status")`,
  `meta["status"]` and `"status"` across `scripts/`, `nexus/`, `probe/`, `adept/` and `observer/`,
  filtered to artifact/frontmatter contexts. Result: the only reader of a real artifact's
  frontmatter status outside `khala.arbiter` is `scripts/ledger_integrity.py`, whose selection
  improves under this change (§2.4). Two hits in `nexus/tests/` are fixture dictionaries, not
  readers. **What is not shipped:** a guard preventing a *future* external reader from assuming
  self-correction. Test 1 pins the property those readers would depend on, which is weaker than
  the precedent this SPEC cites approvingly (`SPEC-nexus-retrieval-backstop-detector` §5 pins a
  behaviour rather than an absence), and the weakness is stated rather than papered over.
- **The demotion is load-bearing for a workflow not represented in the tests.** The critique path
  (`critique.py:48`) sets `in_review` itself when a critique is opened, which is the documented
  meaning; that path is untouched. Whether a human workflow relies on `arbiter status` demoting
  files cannot be answered from this repository — there is no usage record for the command
  (**deferred at critique, I-013**: the check would need `arbiter status` invocations to be
  logged, which nothing does today; deferring is recorded rather than resolved by assertion).
- **Reviewer disagreement on §3.4.** If keeping the file's status truthful is judged to outweigh
  the two costs in §2.4, the alternative is to keep the write but move it behind an explicit
  `arbiter repair` and default `status(repair=False)` — smaller, and it leaves two code paths.
  That option is recorded here so a disposition can choose it rather than re-derive it.
