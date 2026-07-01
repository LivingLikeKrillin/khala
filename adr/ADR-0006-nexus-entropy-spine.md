---
id: ADR-0006
type: adr
title: Nexus entropy spine
status: accepted
date: '2026-07-01T05:12:39Z'
tags:
- nexus
- ingestion-trust
- versioning
- supersession
- entropy
linked_adrs:
- ADR-0002
- ADR-0004
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-01T05:20:19Z'
content_hash: sha256:3c06b41eaec4cf9b966aea404412655b0f6b91a912c21fee8d3b1e123873cd78
---
# ADR-0006: Nexus entropy spine — version-aware supersession, retrieval containment, residual measurement

## Status

**Accepted** (2026-07-01, approved_by LivingLikeKrillin). Records the Slice-1 architecture for controlling document-index entropy in
Nexus. Extends [[ADR-0002]] (Khala as a debt-management convergence point — an entropy tool
is built proactively under the demand-pull override) and follows [[ADR-0004]] (which placed
Nexus as the *index*, not the store). Slice 2 is deliberately deferred behind a demand-pull
gate (see out-of-scope).

## Date

2026-07-01

## Context — unversioned re-upload raises entropy until the index is untrustworthy

A document index that lets **coexisting versions of the same document** accumulate loses
trust over time; deep-research (2026-07-01) confirms coexistence is the #1 entropy failure
mode. If the index cannot be trusted, the index itself is worthless — so ingestion trust
must be built **proactively, first**. This decision gates the solution's survival.

Two hard constraints bound the fix:

1. **Index-only.** Nexus stores the derived index, not the originals (Git/Notion/etc. remain
   source-of-truth). See [[ADR-0004]].
2. **Never force a workflow change.** Users must not be told to change how they author docs;
   meet them at the source. (This rules out mandatory in-document `supersedes:` frontmatter —
   editing the user's original is out.)

**Ground truth in the current code** (verified): document identity is
`rid = doc_rid(canonical_uri)` with `canonical_uri = "{tenant}:{filename}"` (basename only).
The `documents.status` enum already has `'superseded'`, but **no code path ever supersedes a
document row**; chunk-level supersession exists on re-ingest, and search filters
`chunks.status='active'` but **not** the parent document's status. There is no
`superseded_by`, no cross-URI dedup, and re-embedding is emergent (NULL-column driven), with
a latent bug: a chunk whose text changes under a stable `chunk_rid` keeps its **stale
embedding**.

## Decision — prevention (deterministic) + containment (retrieval) + measurement

Ingestion-time prevention has an **information-theoretic ceiling**: the link "v2 supersedes
v1" often does not exist at ingest (the user renamed the file, content changed so hashes
differ, the source gives no stable id). **You cannot prevent what you cannot detect.** So the
posture is *not* "prevent everything" but:

1. **Prevent what is deterministically preventable** — independent of heuristics or human
   adoption. These are the real survival spine:
   - **Document-level supersession filter in search.** Candidate queries
     (`_bm25_search`, `_vector_search`) gain
     `AND EXISTS (SELECT 1 FROM documents d WHERE d.rid=c.doc_rid AND d.status='active')`.
     Once a document is superseded, it and its chunks vanish from retrieval — the containment
     backstop.
   - **Correct "re-embed only changed."** On chunk upsert, invalidate `embedding`/`tsvector_ko`
     **only when `chunk_text` actually changed** (`IS DISTINCT FROM`), fixing the stale-vector
     bug while preserving unchanged vectors.

2. **A minimal, explicit supersession primitive** (bounded by adoption, so kept thin):
   `supersede(old_rid, new_rid, tenant)` — sets the old document `status='superseded'`,
   `superseded_by=new_rid`, cascades chunks to superseded, in one transaction. Decision rules
   are fixed-order and explicit (self-reference → new must be active → old must exist → old
   already-superseded is an idempotent no-op → apply). Exposed via CLI `nexus supersede`, a
   `POST /supersede` API endpoint, and a `nexus_supersede` MCP tool. **No auto-detection**;
   near-dup body-merge is refused (it can collapse meaningfully-different edits).

3. **Containment for the unknowable residual.** Where the v2→v1 link is genuinely
   undetectable, do not pretend to prevent — make coexistence *visible* and let retrieval-time
   governance (freshness/label, already Nexus's calibration philosophy) handle it.

4. **Measure the residual.** A `v_entropy_signals` read-only view surfaces four signals —
   (①) re-ingest overwrite events (from a new append-only `doc_reingest_events` log, since
   `documents` upserts in place and keeps no history), (②) cross-URI `content_hash` collisions
   (exact-dup candidates), (③) normalized title-stem collisions (coexistence candidates),
   (④) supersession count. This **observes** the residual instead of assuming prevention, and
   the signals are the demand-pull trigger for Slice 2.

### Schema (migration `001_supersession.sql`, idempotent DDL)

- `documents.superseded_by TEXT NOT NULL DEFAULT ''`.
- `doc_reingest_events` append-only table + index.
- `norm_title_stem()` IMMUTABLE function (word-boundary-anchored version-token stripping).
- `v_entropy_signals` view (the four signals above).

No `valid_from`/`valid_to` temporal columns — `status` + `superseded_by` cover active/cold;
temporal ranges are YAGNI until a real query needs them.

## Consequences

**Positive**
- The #1 entropy failure mode (coexisting versions) becomes *containable* deterministically:
  once declared, an old version cannot be served.
- "Re-embed only changed" becomes correct, killing stale-vector retrieval drift.
- Entropy is **measured**, not assumed — the operator can see the residual and trigger Slice 2
  on evidence rather than speculation.

**Costs / honest limits**
- The explicit `supersede` primitive has an **adoption ceiling**: it only helps when a human
  declares the link. Undisciplined re-upload under a new filename with undetectable relation
  still creates coexistence — surfaced by measurement, not prevented.
- The identity key `tenant:filename` is simultaneously **too coarse** (different docs sharing a
  basename collide → silent overwrite) and **too fine** (a renamed doc coexists). Slice 1
  **measures** the coarse-collision (overwrite events) rather than preventing it.
- Exact-hash dedup is jitter-sensitive (raw-file hash incl. frontmatter); measurement will show
  whether jitter-driven false-uniqueness is a real problem before the hash basis is touched.

## What this ADR does NOT decide (out of scope — Slice 2, demand-pull gated)

- Ingest-time `--supersedes` ergonomics and **candidate-surfacing / nudge** (title/path
  heuristics + human confirm).
- **Strong prevention of the coarse basename collision** (provenance enrichment + quarantine).
- **Connector-driven stable ids** (Confluence/Notion page-id) — pilot C remains deferred.
- **Freshness TTL / re-verification** thresholds and downweighting.
- **Hash-basis normalization** (normalize body before hashing) — refused now (false-merge risk);
  reconsidered only if `v_entropy_signals` proves jitter is a real problem.

Each is gated on `v_entropy_signals` producing a concrete pull signal.

## Relationship to other ADRs

- **Extends [[ADR-0002]]** (entropy/debt tool → demand-pull override applies: build proactively).
- **Follows [[ADR-0004]]** (Nexus = index not store; supersession governs the index, doc_type
  tier derivation stays in Arbiter — Nexus holds no tier registry).

## Review log (self-critique, 2026-07-01)

Dry-run self-critique before human sign-off (the design also passed two independent
spec-reviewer passes upstream).

| id | sev | category | finding | disposition |
|----|-----|----------|---------|-------------|
| I-001 | high | risky-assumption | Explicit `supersede` has an adoption ceiling: an undetectable renamed re-upload with changed content still creates coexistence | **accepted** — this is the stated posture, not a defect: Consequences names the ceiling explicitly, and the residual is caught by *measurement* (`v_entropy_signals`) + retrieval *containment*, not a false claim of prevention |
| I-002 | medium | scope-creep | Coarse basename collision (`tenant:filename` → silent overwrite of a different doc) is measured, not prevented, in Slice 1 | **accepted** — deliberately scoped: Slice 1 *measures* overwrite events (signal ①); strong prevention (provenance + quarantine) is out-of-scope Slice 2, gated on that signal |
| I-003 | low | unverifiable-claim | Exact-hash dedup is jitter-sensitive; real-world effectiveness unproven | **deferred** — reason: hash-basis normalization is a Slice-2 item explicitly gated on `v_entropy_signals` showing jitter-driven false-uniqueness is a real problem; pre-normalizing now risks false merges |
