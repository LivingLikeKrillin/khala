---
id: SPEC-arbiter-status-is-read-only
type: spec
title: status() must not edit what it reports — flag a stale SPEC stamp the way an
  ADR already is
status: draft
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

This SPEC removes the write. `status()` reports; nothing else.

**It is not a tidying change**, which is why it is a SPEC and not a PR. Two tests pin the current
behaviour deliberately (§2), and an approved SPEC's prose is written around it (§2). The claim
here is that the write costs more than it buys, and the evidence is that the codebase already
pays to work around it twice.

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
so every guarded file edit walks the whole ledger — 64 artifacts as this is written — and rewrites
any SPEC whose stamp has gone stale. Today the tree has 0 mismatches, so the write does not fire;
the moment one artifact drifts, every subsequent edit anywhere in the repo rewrites that file.

### 2.2 ADRs already do the read-only thing

The same method, five lines apart, handles ADRs by flagging `tampered: True` and leaving the file
alone. One comparison, two dispositions. Nothing in `adr/README.md` or ADR-0003 explains why the
two artifact types should differ here; the asymmetry appears to be incidental.

### 2.3 The demoted status says something that is not true

`adr/README.md:68` and `specs/README.md` both define the value being written:

> **in_review** — critique opened, dispositions pending

A SPEC demoted by a stale stamp has no open critique and no pending dispositions. `status()`
writes a lifecycle claim into the artifact to represent a hash result. The report already carries
`needs_review: True`, which is the honest name for the same fact.

### 2.4 The cost is already being paid, twice

**Once in a duplicate implementation.** `SPEC-nexus-retrieval-backstop-detector` §3 states:

> Read-only, and that is a requirement, not a description. `ledger.status()` performs the same
> comparison but, for SPECs, **rewrites the file** … Detection there edits the evidence. The job
> therefore recomputes the hash itself and never calls `status()`

`scripts/ledger_integrity.py` exists in its current shape because of this write, and that SPEC's
§5 pins a test specifically to stop a later refactor routing the check back through `status()`.
So the repository maintains two implementations of "does this body still match its stamp".

**Once in detection quality.** `ledger_integrity.py` only inspects artifacts whose status is
`approved`/`accepted`. A demotion moves the artifact out of that set, so the precise finding —
`MISMATCH: body no longer matches its stamp` — is replaced by the manifest's indirect one,
`listed in the manifest but not selected`. Before the manifest covered every stamped artifact
(2026-09-05, 42 of 60 listed) an unlisted demoted SPEC produced **no finding at all**.

## 3. Design

### 3.1 `status()` never writes

`ledger.py:73-79` collapses to the ADR branch for both types: set the report entry and move on.

- SPEC with a missing or mismatched stamp → `needs_review: True`, `status` in the report is the
  computed `in_review`, the file is untouched.
- ADR → `tampered: True`, unchanged from today.

The report's shape does not change, so no caller's reading of it changes.

### 3.2 `index()` must group on the report, not on the disk

This is the part that breaks quietly if it is forgotten. `index()` today calls `status()` to
repair, then **re-reads every artifact from disk** and groups by `a.status` (`ledger.py:105-109`).
With the write gone, a SPEC with a broken stamp still says `approved` on disk and would be listed
under 🟢 승인 — a silent regression in exactly the surface a reviewer looks at.

`index()` therefore groups by the status in the report, not the status on disk. The `# repair
first` comment goes with the repair.

### 3.3 Nothing changes for the gate

`check_gate` reads `entry.get("status")` out of the report (`gate.py:49-51`), which is the
computed value. A SPEC with a stale stamp still resolves to `in_review`, still fails the
`in ("approved", "accepted")` test, and still blocks implementation. The gate never needed the
file to be rewritten; it needed the comparison.

### 3.4 What is deliberately given up

An artifact whose stamp is stale keeps displaying `status: approved` to anyone who opens the file
without running Arbiter. That is a real loss and it is accepted for three reasons: the stamp is
the mechanism that makes the claim checkable, `governance (ledger integrity)` checks it on every
push, and **accepted ADRs have always behaved this way** — an in-place amendment of ADR-0008 was
caught on 2026-08-05 by exactly that read-only path.

## 4. Non-goals

- **The status vocabulary is not touched.** Adding a distinct value for "approved but the stamp
  went stale" is a lifecycle change under ADR-0003 and would need its own record. `needs_review`
  in the report is sufficient for everything that reads it today.
- **`ledger_integrity.py` is not merged back into `status()`.** With `status()` read-only the
  duplication becomes removable in principle, but `SPEC-nexus-retrieval-backstop-detector` §5
  pins the separation on purpose and unpinning it is a separate argument. This SPEC only removes
  the reason the workaround was needed.
- **`check_gate` scanning all artifacts on every edit is not addressed.** Removing the write
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
2. **`index()` groups a stale-stamped SPEC under 검토중, not 승인.** The §3.2 regression, pinned
   directly.
3. **`check_gate` still refuses** on a SPEC whose stamp is stale, with the file left unmodified —
   the gate's behaviour and the read-only property asserted in one test, because the risk is
   that fixing one silently drops the other.
4. **A negative control**: a tree with no mismatches produces an unchanged report and unchanged
   files, so test 1 cannot pass by the ledger being empty.

## 6. Risks

- **Something outside the arbiter package reads `status:` from frontmatter and assumes it self-
  corrects.** Searched: the only frontmatter-status reader outside the package is
  `scripts/ledger_integrity.py`, whose selection improves under this change (§2.4). `specs/README.md`
  carries a hand-maintained index table listing 4 of 53 SPECs; it is already stale and is not
  affected.
- **The demotion is load-bearing for a workflow not represented in the tests.** The critique
  path (`critique.py`) sets `in_review` itself when a critique is opened, which is the documented
  meaning; that path is untouched. If a human workflow relies on `arbiter status` demoting files,
  it is undocumented and this SPEC's review is where it should surface.
- **Reviewer disagreement on §3.4.** If keeping the file's status truthful is judged to outweigh
  the two costs in §2.4, the alternative is to keep the write but move it behind an explicit
  `arbiter repair` and default `status(repair=False)` — smaller, and it leaves two code paths.
  That option is recorded here so a disposition can choose it rather than re-derive it.
