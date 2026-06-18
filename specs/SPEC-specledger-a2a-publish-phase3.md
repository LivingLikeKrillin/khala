---
id: SPEC-specledger-a2a-publish-phase3
type: spec
title: "Phase 3 — specledger publish to Nexus as an A2A task"
status: draft
date: 2026-06-18
linked_adrs: [ADR-0001]
linked_specs: [SPEC-nexus-a2a-server-phase0-spike, SPEC-probe-a2a-client-phase1, SPEC-nexus-a2a-external-exposure-audit-phase2]
tags: [a2a, specledger, nexus, governance, interop, publish, write]
---

# Phase 3 — specledger publish to Nexus as an A2A task

> Implements **Phase 3** of [ADR-0001](../adr/ADR-0001-adopt-a2a-inter-agent-interop.md):
> migrate the last bespoke ecosystem integration — **specledger → Nexus `publish`** — to an
> A2A task, so an **approved** governance doc (ADR/SPEC) is delivered to Nexus over A2A and
> becomes grounded, retrievable context **with its content-hash provenance intact**. This
> closes the loop: specledger **approves** → Nexus **indexes** → Probe **retrieves** grounded
> specs (the `SpecRef.approvedHash` Probe v0.6 already reads).

Phases 0–2 are all **GO** and stamped: Nexus is an A2A *server* (read-only
`retrieve_grounded`), Probe is an A2A *client* (Phase 1), and external exposure + audit are
in place (Phase 2). Phase 3 introduces the ecosystem's **first write-side A2A skill** and
**specledger as an A2A client** — a materially new surface, hence its own spec and gate.

## 1. Goal

> When specledger `approve`s an ADR/SPEC, it can `publish` that doc to Nexus **over A2A**
> instead of the bespoke `NexusHttpSink` HTTP POST — Nexus ingests it as a governed,
> classified, provenance-stamped resource (carrying specledger's `content_hash`), the write
> is **token-gated, server-classified, audited, and idempotent**, and the bespoke path keeps
> working until A2A is proven.

If it holds, the ecosystem is fully A2A-interoperable end to end (retrieve + publish) and the
bespoke point-to-point HTTP glue can be retired. If the write surface proves too risky or
costly, Phase 3 is deleted behind its flag and `NexusHttpSink` stays.

## 2. Scope

### In scope
- **One Nexus A2A write skill** — `ingest_governed_doc` — wrapping Nexus's *existing* ingest
  path; accepts an approved governance doc (`id`, `title`, `status`, `approved_by`,
  `content_hash`, `body`, `source`) and indexes it with provenance.
- **specledger as an A2A client** — a thin `A2ANexusSink` (alongside `NexusHttpSink`),
  flag-gated; `publish()` selects the transport.
- **Write policy** — the ingest skill is token-gated with a **write capability** (not a mere
  read clearance — see §5.5), server-side classification of the ingested doc, default-deny,
  and a Phase-2 `a2a.audit` record for every publish (grant/deny).
- **Idempotency** — re-publishing the same `(id, content_hash)` is a no-op upsert, not a
  duplicate.
- **Provenance loop** — Nexus stores `content_hash` as the resource's `approved_hash`, so
  Probe's `SpecRef.approvedHash` resolves to specledger's stamp.

### Explicit non-goals (deferred)
- **Approval-notification fan-out** to a fleet of agents (broadcast "X approved") — a separate
  event skill; noted as an extension (§10), not built here.
- Migrating any **other** specledger or Nexus flow; `publish` only (one call, like Phase 1).
- Changes to Nexus **retrieval/ranking/classification rules** or the chunker.
- A general write/ingest A2A API beyond this single governed-doc skill.
- A full **capability/role model** overhaul — Phase 3 adds the *minimal* write capability it
  needs (§5.5); a richer RBAC is future work.

## 3. Exit criteria (the phase is "done")

1. With the flag **off** (default), `publish` uses the existing `NexusHttpSink` HTTP POST
   unchanged; no A2A path, no new dependency.
2. With the flag **on**, `publish` delegates an A2A `ingest_governed_doc` task; Nexus ingests
   the doc and it becomes **retrievable** via the Phase 0 `retrieve_grounded` skill, with the
   doc's `content_hash` queryable as `approved_hash` provenance.
3. The ingest skill is **token-gated with a write capability**: a read-only token (the Phase
   0/1 retrieval token) is **denied**; only a token carrying the write capability succeeds.
   Denials and grants both produce a Phase-2 `a2a.audit` record.
4. **Idempotent**: publishing the same `(id, content_hash)` twice yields one resource
   (upsert), not duplicates; a *changed* body (new `content_hash`) supersedes the prior.
5. **Server classifies**: the ingested doc's classification is decided server-side (Nexus
   classifier), never taken from the caller; quarantine rules apply unchanged.
6. No regression: A2A flag off ⇒ Nexus/specledger behave exactly as today; Phases 0–2 suites
   stay green.

## 4. Background & constraints

- **Direction flips.** Phases 0–2: Nexus is the *server*, callers *read*. Phase 3: specledger
  is the *client* and **writes**. Writing is higher-risk than reading — it can introduce
  ungrounded or misclassified content — so policy/classification/audit must be at least as
  strict (default-deny, server-classified, audited, idempotent).
- **Grounding stays Nexus's job.** specledger ships the approved doc + its hash; Nexus decides
  classification, chunking, and quarantine. specledger cannot assert classification or bypass
  the scanner (PII/secret) — an approved doc with a secret still quarantines (Nexus principle
  #3). "System decides" applies to ingest too.
- **Provenance is the point.** The doc's specledger `content_hash` rides as `approved_hash`,
  making Nexus-indexed governance docs verifiably tied to an accountable-review stamp; Probe's
  `SpecRef` already expects this.
- **Reuse.** Identity/audit/exposure from Phases 0/2; the existing ingest pipeline (collect →
  classify → chunk → index). Phase 3 adds an A2A *adapter* over ingest, not new ingest logic.
- **Lean deps / air-gap.** specledger uses `urllib` today; the A2A sink is a thin JSON-RPC
  client (no SDK), consistent with the Probe Phase-1 thin-client decision.

## 5. Design

### 5.1 Placement

```
nexus/nexus/a2a/
├── card.py        # advertise a 2nd skill: ingest_governed_doc (write)
├── server.py      # route the new method to an ingest handler (token+capability gated, audited)
└── ingest_skill.py  # NEW — map A2A governed-doc payload -> existing ingest pipeline

specledger/src/specledger/
└── publish.py     # A2ANexusSink (thin A2A client) alongside NexusHttpSink; flag-selected
```

### 5.2 The write skill — `ingest_governed_doc`

- **Input** (A2A task message, a `DataPart`): `{id, title, status, approved_by,
  content_hash, body, source}` — the same payload `publish()` builds today.
- **Execution**: persist `body` to a transient location and run the *existing* ingest pipeline
  (collect → scan → classify → chunk → index) with `tenant` from the caller's principal;
  attach `approved_hash = content_hash`, `source_kind = "specledger"`, and the artifact `id`
  as stable provenance.
- **Output**: an A2A task artifact summarizing the ingest — `{resource_rid, classification,
  chunks_indexed, quarantined, approved_hash, idempotent_hit}` — **no document body echoed**.
- A `failed` task when the scanner quarantines or ingest errors, carrying the reason (mirrors
  Nexus's ingest error contract).

### 5.3 specledger client — `A2ANexusSink`

A thin sink implementing the existing `NexusSink` Protocol:
1. Discover Nexus's card (`/.well-known/agent-card.json`), confirm the `ingest_governed_doc`
   skill and the grounding/write extension.
2. `message/send` the governed-doc `DataPart` with `Authorization: Bearer <write token>`.
3. Map the result to `publish()`'s `{published: bool, reason}` return (a `failed`/denied task
   ⇒ `{published: False, reason}` — same graceful contract as today's `try/except`).

`publish()` selects `A2ANexusSink` vs `NexusHttpSink` by config/flag
(`config.nexus["transport"] == "a2a"` or `SPECLEDGER_NEXUS_TRANSPORT=a2a`), default HTTP.

### 5.4 Idempotency & provenance

- Nexus upserts by `(tenant, artifact_id)`; if the incoming `content_hash` equals the stored
  `approved_hash`, it's a no-op (`idempotent_hit: true`). A new hash supersedes (re-index).
- `approved_hash` is queryable and surfaces in `retrieve_grounded` provenance, so a consumer
  (Probe) can show "grounded in SPEC-X @ approved hash abc…".

### 5.5 Policy — the new bit: a **write capability**

Phases 0–2 model one token ⇒ one `(tenant, clearance)` for **reads**. Ingest is a **write**,
and a read token must not be able to write. Phase 3 adds the **minimal** capability:

- A principal gains an optional `capabilities: ["ingest_governed"]` (default: none → read-only).
- `ingest_governed_doc` requires `ingest_governed` in the caller's capabilities; absent ⇒
  default-deny (audited). Clearance/tenant still apply; classification is still server-decided.
- This is deliberately narrow (one capability, one skill) — not a general RBAC. A richer model
  is future work (§10).

### 5.6 Observability

Every publish is a Phase-2 `a2a.audit` record (`skill: ingest_governed_doc`, `denied`,
`reason`, plus `resource_rid`/`classification`/`idempotent_hit` on success) — query text
isn't relevant here, but the artifact `id` + `content_hash` are recorded for provenance.

## 6. Invariants

1. **Flag off ⇒ zero change** — bespoke `NexusHttpSink` path, no A2A, no new dep.
2. **Write needs a capability** — a read-only token can never ingest; default-deny + audit.
3. **Server classifies** — the caller never sets classification; PII/secret ⇒ quarantine,
   never indexed (Nexus principle #3 holds across A2A).
4. **Idempotent** — same `(id, content_hash)` ⇒ one resource; changed hash supersedes.
5. **Provenance preserved** — `content_hash` ⇒ `approved_hash`, retrievable.
6. **One call only** — only `publish` migrates; everything else unchanged.

## 7. Test plan (TDD)

- Nexus `test_a2a_ingest_skill.py` — governed-doc payload ⇒ ingest pipeline invoked, artifact
  with `approved_hash`/classification; quarantined input ⇒ `failed` task, nothing indexed.
- Nexus `test_a2a_ingest_policy.py` — read-only token denied; write-capability token allowed;
  both audited; caller-supplied classification ignored.
- Nexus `test_a2a_ingest_idempotent.py` — same `(id, hash)` twice ⇒ one resource,
  `idempotent_hit`; new hash ⇒ supersede.
- specledger `test_publish_a2a.py` — flag off ⇒ `NexusHttpSink`; flag on ⇒ card discovery +
  `ingest_governed_doc`; denied/failed ⇒ `{published: False, reason}` (graceful parity).
- Card test — the card now lists **two** skills (`retrieve_grounded`, `ingest_governed_doc`)
  and validates against the pinned schema.
- Regression: Phase 0/1/2 suites green; flag-off paths untouched.

## 8. Rollout & reversibility

- Ship behind `config.nexus["transport"]` / `SPECLEDGER_NEXUS_TRANSPORT=a2a` (default HTTP) +
  a write-capability token in Nexus's `a2a.principals`.
- Reversal = remove `ingest_governed_doc` from the card + skill handler + `ingest_skill.py`,
  and the `A2ANexusSink`. `retrieve_grounded` and `NexusHttpSink` untouched.

## 9. Risks specific to Phase 3

| Risk | Mitigation |
|---|---|
| Write surface lets ungrounded/misclassified content in | Server-side classify + scanner/quarantine unchanged; caller can't set classification (§6.3) |
| Read token escalates to write | Explicit write capability required; default-deny + audit (§5.5) |
| Nexus ingest is path/file-based, not inline-body | Bridge: persist `body` to a transient file then run the existing pipeline (§5.2); confirm at impl |
| Duplicate/looping publishes | Idempotency by `(id, content_hash)` (§5.4) |
| Capability model creep | One capability, one skill; no general RBAC (§2/§5.5) |
| Provenance mismatch with Probe's `SpecRef.approvedHash` | Contract test ties `content_hash` → `approved_hash` → retrieval provenance |

## 10. Open questions

- **Inline-body ingest** — does Nexus need a first-class "ingest from body" entry, or is the
  temp-file bridge (§5.2) acceptable for Phase 3? (Confirm against `run_ingest`.)
- **Classification of governance docs** — default `INTERNAL`? Are approved ADRs org-`PUBLIC`?
  Server rule, but which default.
- **Capability model** — is a single `ingest_governed` capability enough, or does Phase 3
  force the broader role/capability design now? (Prefer minimal.)
- **Approval notifications** — fold a fire-and-forget "approved" event into this skill, or a
  separate `notify_approval` skill / A2A message (deferred)?
- **Idempotency key** — `(tenant, id)` upsert vs content-addressed by `content_hash`; how to
  represent supersession of an old approved hash in the index.

## 11. Definition of done

All §3 exit criteria met, §7 tests green, and a one-paragraph **recommendation**: retire the
bespoke `NexusHttpSink` (and the Probe/specledger bespoke glue generally) or keep A2A
opt-in. On `approved`, this spec is stamped and `begin_implementation` arms the gate for
`nexus/a2a/ingest_skill.py` + `specledger/.../publish.py`.

## 12. Review log (dry-run, 2026-06-18)

Pre-registration accountable-review pass against the specledger rubric. Issues dispositioned
**accepted**:

| Issue | Category | Disposition | Change |
|---|---|---|---|
| I-001 | risky-assumption | accepted | §5.5 introduces an explicit **write capability** so a read token can't write — the core new-surface risk named and gated. |
| I-002 | scope-creep | accepted | Hard-scoped to one skill + one migrated call; approval fan-out and general RBAC explicitly deferred (§2/§10). |
| I-003 | missing-invariant | accepted | Added §6.3 "server classifies / scanner unchanged" and §6.4 idempotency — write can't bypass grounding/quarantine. |
| I-004 | undefined | accepted | §5.2 defines the inline-body→ingest bridge and flags the path-based-ingest gap as a tracked risk/open question. |
| I-005 | untestable-requirement | accepted | Provenance loop made testable: `content_hash → approved_hash → retrieval provenance` contract test (§7). |

> Dry-run record. The specledger gate is now active (ADR-0001 accepted; Phases 0–2 SPECs
> approved). When `ANTHROPIC_API_KEY` is set, run `critique` → `approve` to supersede this
> dry-run import with a live LLM sidecar and stamp the content hash.

## 13. Implementation note (2026-06-18) — part 1: Nexus write skill landed

Phase 3 split into two units. **Part 1 (this) — the Nexus `ingest_governed_doc` write skill —
is implemented**, TDD, 16 new tests; full Nexus suite **280 passed / 14 skipped**, ruff clean.

- **Write capability (§5.5) ✅** — `Principal` gained an additive `capabilities: tuple[...]`
  (default empty ⇒ read-only) + `Principal.has(...)`; `resolve_principal` reads
  `capabilities` from config. Backward compatible (existing read tokens unaffected).
- **Card ✅** — now advertises two skills; `ingest_governed_doc` is tagged `write`/`governed`.
- **Skill routing + gate ✅** — `server.py` routes by `message.metadata.skill_id`. The ingest
  branch requires the `ingest_governed` capability: a read-only token ⇒ **403 + audited
  denial** (`reason: forbidden_no_capability`), never reaching the pipeline; a write token ⇒
  ingest. Incomplete payload ⇒ invalid-params + audit. Every outcome is a Phase-2 `a2a.audit`
  record.
- **Mapping ✅** — `ingest_skill.py` maps an `IngestOutcome` to an artifact (resource_rid,
  classification, approved_hash, idempotent_hit) — **the document body is never echoed back**;
  quarantine/error ⇒ `failed` task. Server classifies; the caller never sets classification.
- **Idempotency** — surfaced through the injected `ingest_fn` (`idempotent_hit`); the
  production default (`_default_ingest_fn`) bridges the inline body to the file-based
  `run_ingest` (SPEC §5.2) and reports `idempotent_hit=False` — real dedup by
  `(tenant, id, content_hash)` is deferred (§10), to be done with the durable store.

**Part 2 (next) — specledger `A2ANexusSink`** (the thin A2A client in `publish.py`, flag-gated
alongside `NexusHttpSink`) — completes the end-to-end exit criteria (§3.1/§3.2/§3.4 client
side). Tracked as the follow-up.

## 14. Implementation note (2026-06-18) — part 2: specledger A2A client landed

Phase 3 pt.2 — the specledger **`A2ANexusSink`** — is implemented, TDD, 11 new tests; full
specledger suite **86 passed**, ruff clean.

- **Transport selection (§5.3, §6.1) ✅** — `publish()` now routes through `_select_sink`:
  `config.nexus["transport"] == "a2a"` or `SPECLEDGER_NEXUS_TRANSPORT=a2a` opts into A2A;
  **default is HTTP** (flag off ⇒ the bespoke `NexusHttpSink` POST, zero change, no new dep —
  the A2A client is pure-`urllib`/no-SDK, matching Probe's Phase-1 thin-client decision).
- **Thin A2A client ✅** — `A2ANexusSink` discovers the agent card (`/.well-known/agent-card.json`,
  cached per instance), confirms the `ingest_governed_doc` skill, then `message/send`s the
  governed-doc as a single **DataPart** with `metadata.skill_id` and `Authorization: Bearer
  <write token>`. The urllib transport is injected (`transport=`) so the client is unit-testable
  without a live Nexus.
- **Graceful parity (§3.4) ✅** — a JSON-RPC error (capability **denial** ⇒ 403 `forbidden`),
  a `failed`/quarantined task, or a card-discovery failure each raise `A2APublishError`, which
  `publish()`'s existing `try/except` maps to `{published: False, reason}` — same contract as
  the HTTP path; **no document body is ever read back**.
- **Provenance (§5.4) ✅** — `publish()` now adds `content_hash` to the payload (the approval
  stamp's `meta["content_hash"]`, falling back to `recompute_hash()`), so Nexus stores it as
  `approved_hash` and Probe's `SpecRef.approvedHash` resolves to specledger's stamp.
- **Minor deviation** — the client confirms the skill **id** (the concrete gate; the write
  capability is server-enforced) but does not additionally inspect the grounding/write
  *extension*; noted, not load-bearing.

**Recommendation (§11):** keep A2A **opt-in** for now. Both transports are green and the flag
defaults to HTTP, so the bespoke `NexusHttpSink` is the safe default until the A2A write path is
exercised against a live, capability-gated Nexus (idempotency dedup is still deferred — §10).
Retire `NexusHttpSink` only once an end-to-end live run confirms §3.2/§3.4 with a real write
token. The ecosystem is now A2A-interoperable end to end (retrieve **and** publish) behind flags.

## 15. End-to-end run (2026-06-18) — in-process cross-tool verification

The §11 "live end-to-end run" landed as a deterministic, CI-reproducible cross-tool test:
`tests/test_a2a_e2e_specledger_to_nexus.py` (repo root; `pytest.importorskip`-guarded so neither
tool's isolated CI is affected). It wires the **real** Nexus A2A server (`mount_a2a` → card +
JSON-RPC + capability gate + audit + ingest mapping) to the **real** specledger `A2ANexusSink` +
`publish()` over an in-process ASGI transport — no SDK faked between them. **5 tests, all green**
(nexus a2a suite 63 + specledger 86 unaffected). Confirmed over the wire:

- **§3.2/§5.4** — a write-capable `publish()` ingests the governed doc under the principal's
  tenant, and specledger's `content_hash` round-trips as the ingest artifact's `approved_hash`.
- **§3.3/§5.5** — a read-only token is denied (403, audited `a2a.audit` denial); the ingest
  pipeline is never reached (`store.ingests == 0`).
- **§3.4** — quarantine and denial both map to the graceful `{published: False, reason}`;
  idempotent re-publish yields **one** resource (`idempotent_hit` recognised).
- **§3.5** — specledger never sends a classification; the server decides it (`INTERNAL`).

**What this run does *not* cover (the remaining gate before retiring `NexusHttpSink`):** the
DB-backed RAG pipeline + real classifier/scanner (stubbed here by an in-memory store — covered
by nexus's own suite), and a true Docker-stack bring-up. **Discovered gap (follow-up):** §5.4
also promises `approved_hash` *surfaces in `retrieve_grounded` provenance*, but the current
retrieval mapping (`nexus/a2a/mapping.py::build_grounded_artifact`) carries only
`source_uri`/`source_version`/`doc_rid` — it does **not** yet emit `approved_hash`. So the
provenance loop is proven on the **ingest** side end-to-end, but the **read-back** side
(Probe reading `SpecRef.approvedHash` *via retrieval*) needs a small mapping addition. Tracked
as the next concrete unit; the recommendation (keep A2A opt-in) stands until both that mapping
and a DB-backed live run are done.
