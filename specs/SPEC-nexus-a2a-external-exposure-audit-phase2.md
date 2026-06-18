---
id: SPEC-nexus-a2a-external-exposure-audit-phase2
type: spec
title: "Phase 2 — Nexus A2A external exposure + audit trail"
status: draft
date: 2026-06-18
linked_adrs: [ADR-0001]
linked_specs: [SPEC-nexus-a2a-server-phase0-spike, SPEC-probe-a2a-client-phase1]
tags: [a2a, nexus, auth, audit, security, interop, exposure]
---

# Phase 2 — Nexus A2A external exposure + audit trail

> Implements **Phase 2** of [ADR-0001](../adr/ADR-0001-adopt-a2a-inter-agent-interop.md):
> safely expose the Nexus A2A surface to **external** (non-localhost) A2A agents and
> **audit every cross-agent task**. The identity core this phase depends on — token auth,
> default-deny, server-side classification/clearance, narrow-only scope — **already shipped
> in Phase 0** ([SPEC-nexus-a2a-server-phase0-spike](./SPEC-nexus-a2a-server-phase0-spike.md)
> §5.5/§6, `nexus/auth/` + `nexus/a2a/policy.py`). Phase 2 therefore adds **only** the two
> things Phase 0 deliberately deferred: an **exposure posture** for untrusted callers and a
> **persistent audit trail**. Nothing in the policy core is rebuilt.

## 1. Goal

> An external A2A agent can consume Nexus's `retrieve_grounded` skill over a network
> boundary **without weakening any classification/clearance/quarantine guarantee**, and
> **every** task it triggers — granted **or denied** — leaves a durable, queryable audit
> record that names the principal, tenant, clearance, outcome, and evidence count, **without
> logging sensitive query text verbatim**.

If that holds, Phase 3 (governance flows: specledger `publish`/approval as A2A tasks) is
justified. If exposure can't be made safe or audit is too costly, the surface stays
localhost-only behind its flag at near-zero cost.

## 2. Scope

### In scope
- **Exposure posture** for the A2A routes (`/.well-known/agent-card.json` + `/a2a`): an
  explicit, A2A-specific **allowed-origins / CORS** decision; the public-card vs.
  gated-skill boundary restated for untrusted callers; deployment guidance for binding the
  surface (reverse proxy / network).
- An **audit trail**: exactly one structured, append-only audit record per A2A task —
  **success and denial** — with a stable schema and event name (`a2a.audit`).
- **Denial auditing**: the currently-silent default-deny path (missing/invalid token,
  unknown method, empty query) must emit an audit record.
- **Query-text minimization**: audit records carry a **hash** (or length + prefix), never
  the raw query, so audit logs don't become a PII sink.
- **Tests** for audit emission (grant + deny), query non-disclosure, and CORS application.

### Explicit non-goals (deferred)
- **Token auth / default-deny / clearance / narrow-only** — **already done (Phase 0)**; this
  phase reuses them unchanged.
- **OAuth/OIDC/identity federation**, token-management UI, token rotation tooling (Phase 3 /
  roadmap Governance).
- A **DB-backed** audit store and an audit query API — Phase 2 emits structured audit
  **events** (structlog); persistence/sink selection is an open question (§10), a durable
  file/collector sink is acceptable, a Postgres audit table is a Phase-2.x/3 extension.
- **Rate limiting / quota** per token (tracked in §10; not required for the gate).
- App-level **OpenTelemetry tracing** — not wired in Nexus today (the Phase 0 spec's "OTel
  span" was aspirational; reality is a `structlog` line). Phase 2 standardizes on structlog
  audit events; an OTel exporter is a separate concern.
- Multi-skill catalog, streaming, push notifications (Phase 0 non-goals, still out).

## 3. Exit criteria (the phase is "done")

1. **Every** A2A task emits exactly one `a2a.audit` record. A **granted** task records
   `{principal, tenant, clearance, skill, route, evidence_count, task_state, denied:false}`;
   a **denied** task records `{denied:true, reason, ...}` with no privileged content.
2. The default-deny paths (no/invalid token, unknown method, empty query) each produce a
   **denial** audit record — no silent denials.
3. Audit records **never** contain the raw query text; they carry a stable `query_sha256`
   (and may carry length) instead. A test asserts the raw query string is absent.
4. The A2A routes honour an **explicit allowed-origins** policy (no `*` when credentials are
   possible); a request from a disallowed origin is rejected by CORS, parity with the rest
   of the app. The **card stays public**, the **skill stays token-gated** (Phase 0 §5.5).
5. No regression: with `NEXUS_A2A_ENABLED` off the surface is absent and no audit code runs;
   with it on, existing Phase 0/1 behaviour and tests are unchanged.
6. A short **threat-model note** (untrusted caller can't widen clearance, can't read denied
   content, can't poison the audit log, can't exfiltrate via the card) is recorded in §11.

## 4. Background & constraints

- **Reuse, don't rebuild (ADR Phase 2).** `resolve_principal` (1 token ⇒ fixed
  `(tenant, clearance)`), `effective_scope` (narrow-only), and `base_filter`
  (tenant + clearance + `is_quarantined=false` + `status='active'`) are the policy. Phase 2
  wraps the A2A handler with audit + exposure config; it does not touch retrieval, ranking,
  classification, or the identity core.
- **Grounding & default-deny are non-negotiable** and already server-side. A caller can never
  widen its own clearance; a denied call returns no privileged content (Phase 0 invariants).
- **Air-gap / self-host.** Audit must work with no external dependency — structured events to
  the existing `structlog` pipeline (stdout/file/collector), not a hosted service.
- **PII discipline (Nexus principle #3).** Audit logs must not become a quarantine bypass:
  never store raw query text or evidence snippets in the audit record.
- **Adapter isolation.** Audit + exposure live alongside `nexus/a2a/`, behind the same flag,
  so they're inert when A2A is off and deletable with the surface.

## 5. Design

### 5.1 Placement

```
nexus/nexus/a2a/
├── server.py        # wrap message/send + every denial path with an audit emit
├── audit.py         # NEW — build & emit the a2a.audit record (structlog), query hashing
└── config.py        # A2AConfig gains explicit allowed_origins for the A2A surface
```

No new top-level modules; audit is one small file behind the existing flag.

### 5.2 Audit record (schema)

A stable, flat, PII-safe event emitted via `structlog` under event name `a2a.audit`:

| field | type | notes |
|---|---|---|
| `event` | str | constant `"a2a.audit"` |
| `skill` | str | `"retrieve_grounded"` (or the attempted method on a method-not-found denial) |
| `principal` | str\|null | principal name, or `null` when unauthenticated |
| `tenant` | str\|null | effective tenant (null on pre-auth denial) |
| `clearance` | str\|null | effective clearance applied |
| `query_sha256` | str | sha256 of the raw query; **never the query itself** |
| `query_len` | int | length only (coarse signal) |
| `route` | str\|null | route used (granted only) |
| `evidence_count` | int | 0 on denial / no-evidence |
| `task_state` | str\|null | `"completed"` / `"failed"` (granted) |
| `denied` | bool | true for every default-deny path |
| `reason` | str\|null | denial reason code (`unauthorized` / `method_not_found` / `empty_query`) |
| `latency_ms` | int | handler wall time |

The record is emitted **once per request** in a `finally`-style path so a granted task and
every denial branch are covered. (Structlog already carries timestamps + context.)

### 5.3 Exposure posture

- **Card public, skill token-gated** (unchanged from Phase 0 §5.5). External discovery is
  intentional; execution requires a token resolving to a fixed `(tenant, clearance)`.
- **A2A allowed origins.** `A2AConfig` gains `allowed_origins` (default: the app's existing
  `auth.allowed_origins`). For external exposure the operator sets the real caller origins;
  `*` is refused when credentials/headers are in play, consistent with the app CORS policy.
- **Deployment guidance (doc, not code).** Terminate TLS and apply network ACLs at a reverse
  proxy; the A2A surface assumes the same trust boundary as the rest of the Nexus API. No new
  inbound port — it shares the FastAPI app.

### 5.4 Denial auditing

The Phase 0 handler returns early via `_rpc_error` on unknown method / unauthorized / empty
query **without** an audit line. Phase 2 routes all four outcomes (granted, unauthorized,
method-not-found, empty-query) through a single audit emit so **no denial is silent**
(exit #2). Denials carry `denied:true` + a `reason` code and **no** privileged fields.

### 5.5 What is explicitly NOT changing

`nexus/auth/**`, `nexus/a2a/policy.py`, `mapping.py`, `card.py`, retrieval/ranking, and the
MCP server are byte-for-byte unchanged. Phase 2 is additive (audit) + config (origins).

## 6. Invariants

1. **One task ⇒ one audit record**, whether granted or denied. No silent denial.
2. **Audit is PII-safe.** No raw query, no evidence text, no answer text in the record —
   `query_sha256` + `query_len` only.
3. **Denied ⇒ no privileged content** anywhere (response or audit).
4. **Server decides policy.** Reused Phase 0 core; a caller can only narrow scope.
5. **Off by default.** `NEXUS_A2A_ENABLED` unset ⇒ no routes, no audit, no exposure config.
6. **Card public, skill gated.** External callers can read the card; execution needs a valid
   token.

## 7. Test plan (TDD)

- `test_a2a_audit.py` — a granted task emits one `a2a.audit` record with
  `denied=false` + tenant/clearance/route/evidence_count/task_state; capture via a structlog
  test sink.
- `test_a2a_audit_denials.py` — unauthorized / method-not-found / empty-query each emit one
  `denied=true` record with the right `reason` and no privileged fields.
- `test_a2a_audit_no_query_leak.py` — the raw query string never appears in any audit record;
  `query_sha256` equals `sha256(query)`.
- `test_a2a_cors.py` — a disallowed origin is rejected on the A2A routes; an allowed origin
  passes; the card remains publicly fetchable.
- Regression: the Phase 0/1 suites stay green; flag-off path emits nothing.

## 8. Rollout & reversibility

- Audit is on whenever the A2A surface is on (no separate flag) — auditing cross-agent tasks
  is the point of exposing them. `A2AConfig.allowed_origins` defaults to the app's origins;
  operators widen it deliberately for external callers.
- Reversal = delete `audit.py` + the audit calls + the origins field. Phase 0/1 unaffected.

## 9. Risks specific to Phase 2

| Risk | Mitigation |
|---|---|
| Audit log becomes a PII sink (raw queries) | Hash-only (`query_sha256`); test asserts non-disclosure (§7) |
| Silent denials hide abuse | Every deny path audited with a reason (exit #2) |
| Over-permissive CORS exposes credentials | Explicit allowed-origins; refuse `*` with credentials (parity with app) |
| Audit volume / cost | Structured events to the existing pipeline; DB sink deferred (§10) |
| Exposure widens attack surface | Card public / skill gated; policy reused; threat-model note (§11); no new port |
| "OTel span" expectation from Phase 0 | Corrected: structlog audit events; OTel exporter is out of scope (§2) |

## 10. Open questions

- **Audit sink** — structlog→stdout/file (default) vs. a Postgres `a2a_audit` table + a query
  API (Phase 2.x/3). Which does the first external deployment need?
- **Query minimization** — hash-only vs. hash + redacted prefix vs. opt-in full-query audit
  for trusted tenants.
- **Rate limiting** — per-token quota; needed before real external exposure, or Phase 3?
- **Card gating for external** — keep the card fully public, or gate it behind a coarse token
  for untrusted networks?
- **Multi-principal audit correlation** — add a per-task `task_id`/`context_id` to the record
  for cross-system correlation (cheap; likely yes).

## 11. Definition of done

All §3 exit criteria met, §7 tests green, the §6 threat-model note appended here, and a
one-paragraph **go/no-go recommendation for Phase 3**. On `approved`, this spec is stamped
and `begin_implementation` arms the specledger gate for `nexus/a2a/audit.py` + the
`server.py`/`config.py` deltas.

## 12. Review log (dry-run, 2026-06-18)

Pre-registration accountable-review pass against the specledger rubric. Issues dispositioned
**accepted**:

| Issue | Category | Disposition | Change |
|---|---|---|---|
| I-001 | scope-creep | accepted | Hard-scoped Phase 2 to exposure + audit; auth/clearance explicitly reused from Phase 0, not rebuilt (§1/§2/§4). |
| I-002 | risky-assumption | accepted | Audit made PII-safe by construction (`query_sha256`, never raw query) + a non-disclosure test (§5.2/§6.2/§7). |
| I-003 | missing-invariant | accepted | "One task ⇒ one audit record, no silent denial" (§6.1) + denial-audit exit (#2). |
| I-004 | unverifiable-claim | accepted | Corrected the Phase 0 "OTel span" claim — Phase 2 standardizes on structlog audit events (§2/§9). |
| I-005 | untestable-requirement | accepted | Exposure made testable via explicit allowed-origins + a CORS test, not a vague "secure" goal (§5.3/§7). |

> Dry-run record. When specledger is registered, run `critique` → `approve` to produce the
> canonical sidecar and stamp the content hash.
