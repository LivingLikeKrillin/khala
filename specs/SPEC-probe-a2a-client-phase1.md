---
id: SPEC-probe-a2a-client-phase1
type: spec
title: Phase 1 — Probe as an A2A client of Nexus
status: approved
date: 2026-06-18
linked_adrs:
- ADR-0001
linked_specs:
- SPEC-nexus-a2a-server-phase0-spike
tags:
- a2a
- probe
- nexus
- interop
- client
- grounding
approved_by: LivingLikeKrillin
reviewed_at: '2026-06-18T10:30:00Z'
content_hash: sha256:b0fd2d2366f677bd4324c1a18f71eca569015ce553ce8d08f03d641563c45707
---

# Phase 1 — Probe as an A2A client of Nexus

> Implements **Phase 1** of [ADR-0001](../adr/ADR-0001-adopt-a2a-inter-agent-interop.md):
> make **Probe** an **A2A client** of Nexus, replacing **one** bespoke HTTP call
> (`POST /search/answer`) with an A2A `retrieve_grounded` task — behind a flag, drop-in,
> reversible — and compare maintainability/observability against the direct path.
>
> Phase 0 ([SPEC-nexus-a2a-server-phase0-spike](./SPEC-nexus-a2a-server-phase0-spike.md))
> stood up the Nexus A2A **server** and proved an off-the-shelf client can discover Nexus,
> delegate a query, and receive the full grounded answer (verdict **GO**, §15). Phase 1 is
> the mirror: Khala's own consumer (Probe) becomes the **client**, so we learn the
> client-side ergonomics before committing the ecosystem to A2A.

## 1. Goal

Prove the second load-bearing claim behind ADR-0001 at low cost:

> Probe can consume Nexus's grounded answer over **A2A** instead of the bespoke
> `/search/answer` call — with **identical results** (answer + evidence + provenance +
> route), **identical graceful-degradation** (Nexus stays optional), and **no regression**
> — while being at least as maintainable/observable as the direct path.

If that holds, Phase 2 (external exposure + auth) and Phase 3 (governance flows) are
justified. If the client path is materially worse (more glue, worse failure semantics,
heavier deps), Phase 1 is deleted behind its flag at near-zero cost and the bespoke call
stays.

## 2. Scope

### In scope
- A new **A2A transport** for exactly one Probe→Nexus call: `NexusClient.searchAnswer`.
- **Discovery** via Nexus's Agent Card (`/.well-known/agent-card.json`) → the
  `retrieve_grounded` skill.
- A **`A2A task artifact → NexusAnswerResult`** mapping (the client-side inverse of the
  Phase 0 server mapping), lossless for the fields Probe consumes.
- **Flag-gated transport selection** (`http` default | `a2a`), reversible, with HTTP as the
  fallback path that stays the default until A2A is proven.
- **Graceful degradation parity**: any A2A failure (transport, denied, failed task) returns
  `null` exactly like today, so callers' fallbacks are unchanged.
- **Contract + parity tests** (vitest) and a short maintainability/observability writeup.

### Explicit non-goals (deferred)
- Migrating Probe's **other** Nexus calls (`/search`, `/graph`, `/diff`, `/status`). One
  call only.
- Nexus as a Probe-facing **A2A server change** beyond what Phase 0 already ships. (One
  exception is flagged in §5.4 / §10 — the optional `graph_findings` mapping gap.)
- Full **auth/identity federation** (Phase 2). Phase 1 reuses the Phase 0 static bearer
  token from config/env.
- Adopting the heavyweight `@a2a-js/sdk` (see §5.3 + §9 — Phase 1 recommends a thin client;
  the SDK is a tracked alternative, not a Phase 1 commitment).
- specledger / mutqa as A2A clients (Phase 3+).

## 3. Exit criteria (the phase is "done")

0. **(Feasibility gate — already discharged.)** A reachable Nexus A2A server exists and a
   reference client can drive it. → **✅** Phase 0 §14/§15 proved the server + an
   off-the-shelf client round-trip (card discovery + `message/send` + grounded artifact),
   p50 transport overhead ≈ 2.64 ms. Phase 1 only adds the *Probe-side* client.
1. With the flag **off** (default), Probe behaves **byte-for-byte** as today: `searchAnswer`
   issues the same `POST /search/answer`; no A2A code path, no new runtime dependency loaded.
2. With the flag **on**, `searchAnswer` performs an A2A `retrieve_grounded` task against
   Nexus's Agent Card and returns a `NexusAnswerResult` whose `answer`, `evidence_snippets`,
   `provenance`, and `route_used` are **equal** to the HTTP path's result for the same query
   (parity; see §7 method).
3. A **contract test** asserts the client maps a grounded A2A artifact to a populated
   `NexusAnswerResult` (≥1 evidence snippet + provenance + route), and maps a **failed**
   task (no-evidence, `TASK_STATE_FAILED`/`"failed"`) to **`null`** — never a fabricated
   answer. (Mirrors the server-side grounding guard from Phase 0 §6.1, viewed from the
   consumer.)
4. **Graceful degradation parity:** Nexus unreachable / denied / timeout over A2A returns
   `null` and the caller's existing fallback runs — identical to the HTTP path. No thrown
   error escapes `NexusClient`.
5. A one-paragraph **maintainability/observability comparison** (A2A vs. direct) is recorded
   in §11, with the measured glue-size and failure-surface delta.
6. The A2A surface is **off when unset**; the bespoke `/search/answer` path is untouched and
   remains the reversal target (delete the transport + flag).

## 4. Background & constraints (from ADR-0001 + Probe conventions)

- **Layering.** A2A is agent↔agent; MCP stays agent↔tool. Probe keeps its MCP server; this
  only changes how Probe *consumes* Nexus, not how Claude Code consumes Probe.
- **Grounding rides the protocol — at the emission boundary (ADR Key Point 3).** Nexus emits
  and enforces evidence/clearance server-side; Probe (the consumer) must **read and carry**
  the evidence packet through unchanged. Probe never asserts its own clearance; the server
  decides.
- **Nexus is optional (Probe principle #5).** Every feature works without Nexus and is
  *richer* with it. The A2A path must preserve this: failure ⇒ `null` ⇒ fallback.
- **Lean deps / air-gap.** Probe ships **2** runtime deps (`@modelcontextprotocol/sdk`,
  `zod`). A2A's wire is plain HTTP + JSON-RPC 2.0; Phase 1 favours a **thin in-house client**
  over a heavyweight SDK to keep the dependency surface and air-gap posture intact (§5.3).
- **TS conventions.** strict mode, no `any` (use `unknown` + guards), JSDoc on public
  functions, Korean-first error/log messages, kebab-case files, vitest. Adapter isolation:
  the A2A surface lives behind one module so protocol churn can't leak into Probe core.

## 5. Design

### 5.1 Placement

New, self-contained module — no edits to Probe core or the other Nexus calls:

```
probe/src/nexus/
├── client.ts            # NexusClient — selects transport for searchAnswer (flag)
└── a2a/
    ├── transport.ts     # discover card + message/send (thin JSON-RPC 2.0 client)
    ├── mapping.ts       # A2A task artifact -> NexusAnswerResult (client-side inverse)
    └── types.ts         # minimal A2A wire types Probe needs (Task/Artifact/Part subset)
```

`NexusClient.searchAnswer` gains a transport switch; everything else is untouched and inert
when the flag is off.

### 5.2 Transport selection (flag)

- New optional config field `NexusClientConfig.transport: 'http' | 'a2a'` (**default
  `'http'`**), overridable by env `PROBE_NEXUS_TRANSPORT=a2a` (loud opt-in), mirroring
  Nexus's `NEXUS_A2A_ENABLED` discipline.
- New optional `NexusClientConfig.nexusToken?: string` (or env `PROBE_NEXUS_TOKEN`) — the
  Phase 0 static bearer token. Required only for the A2A path (the skill is token-gated; the
  card is public). Absent token + enforced server ⇒ denied ⇒ `null` ⇒ fallback.
- `baseUrl` is reused; the A2A interface URL is read from the discovered card (`url` field),
  not hard-coded.

### 5.3 A2A client (thin, dependency-light)

Phase 1 implements a **thin client** rather than adopting `@a2a-js/sdk`:

1. **Discover** — `GET {baseUrl}/.well-known/agent-card.json`, validate it advertises
   `skills[].id == "retrieve_grounded"` and the grounding extension; read the JSON-RPC
   interface `url`. Cache per client instance.
2. **Delegate** — `POST {card.url}` a JSON-RPC 2.0 `message/send` with
   `params.message.parts = [{kind:"text", text: query}]` and
   `Authorization: Bearer <token>`. Non-streaming (Phase 0 card declares `streaming:false`).
3. **Map** — parse the `result` Task's artifact into `NexusAnswerResult` (§5.4).

Rationale: the wire is trivial, Probe already uses raw `fetch` with timeout + graceful
degradation, and a thin client keeps Probe's 2-dep / air-gap posture. The off-the-shelf SDK
is the natural Phase 2+ upgrade if richer features (streaming, push, auth schemes) are
needed; tracked in §10. The **contract tests, not the client internals, are the spec**.

### 5.4 `A2A artifact → NexusAnswerResult` mapping (client-side inverse)

The Phase 0 server emits an artifact `[TextPart(answer), DataPart(evidence packet)]` where
the data part is `{evidence[], provenance[], confidence, route, policy}`. Phase 1 inverts it:

| A2A artifact location | `NexusAnswerResult` field | Notes |
|---|---|---|
| text part | `answer` | narrated answer (markdown) |
| data part `.evidence[]` | `evidence_snippets[]` | `{doc_title, section_path, text, score, source_uri}` |
| data part `.provenance[]` | `provenance` | `{source_uri, source_version, doc_rid}` |
| data part `.route` | `route_used` | |
| data part `.confidence` | (surfaced in `timing_ms`/meta or ignored — §10) | new field, no HTTP equiv |
| — | `graph_findings` | **GAP**: Phase 0's data part omits `graph_findings` (§10) |
| task `status.timestamp` etc. | `timing_ms` | best-effort; transport time may be added |

A **`failed`** task (no evidence) ⇒ `searchAnswer` returns **`null`** (graceful
degradation), *not* an empty-but-present answer — consistent with today's null-on-failure
and with the Phase 0 "no confident answer without evidence" guard.

**Lossless requirement:** for the fields Probe's grounders consume today
(`answer`/`evidence_snippets`/`provenance`/`route_used`), the A2A result must equal the HTTP
result. `graph_findings` fidelity is an explicit open question (§10) — Phase 1 either (a)
extends the Phase 0 server `DataPart` to include `graph_findings`, or (b) documents that the
A2A `retrieve_grounded` skill returns the core grounded answer and graph enrichment stays on
its own (`/graph`) call for now. **Decision for Phase 1: (b)** — keep the skill's contract
as shipped; only extend if a Probe consumer of `searchAnswer.graph_findings` is found to
regress (verified by the parity test, which will flag a non-empty `graph_findings`).

### 5.5 Policy & grounding (unchanged, server-side)

- Clearance/tenant/quarantine remain **server-enforced** (Phase 0 §5.5). Probe sends a token
  that resolves to a fixed `(tenant, clearance)`; caller-asserted widening is ignored.
- Probe carries the returned evidence packet through to its grounders **unchanged** — it
  never re-derives or strips grounding. The "human stops judging" guarantee is the
  consumer's responsibility (ADR Key Point 3); Probe honours it by surfacing evidence as-is.

### 5.6 Observability comparison (exit criterion 5)

Record, for the same query, A2A vs. HTTP: (a) **glue size** (LOC of the transport+mapping
vs. the one-line `post()`), (b) **failure surface** (how many distinct failure modes each
collapses to `null`, and whether the reason is still logged), (c) **latency** (A2A adds the
Phase 0 ~2.6 ms transport overhead + one card-discovery round-trip, cached thereafter). The
writeup is the qualitative input to the Phase-2 go/no-go.

## 6. Invariants

1. **Flag off ⇒ zero change.** Unset/`'http'` ⇒ the exact current `POST /search/answer`
   path; no A2A import, no card fetch, no new dep loaded.
2. **Nexus stays optional.** Every A2A failure path returns `null`; no error escapes
   `NexusClient`; callers' fallbacks are untouched.
3. **Grounding preserved.** The A2A path's `answer`/`evidence`/`provenance`/`route` equal
   the HTTP path's; a no-evidence task ⇒ `null`, never a fabricated answer.
4. **Server decides policy.** Probe never asserts clearance; the token resolves it
   server-side. Caller input can only narrow.
5. **One call only.** Only `searchAnswer` is migrated; all other Nexus calls keep their
   current transport.
6. **No heavy dependency.** Phase 1 adds **no** new runtime dependency (thin client); if a
   dep is ever added it must be pinned and air-gap-audited (ADR risk row).

## 7. Test plan (TDD, vitest)

Red → green, contract tests first; all run without a live Nexus (transport `fetch` stubbed):

- `client.searchAnswer.transport.test.ts` — flag off ⇒ calls `/search/answer` (existing
  stub); flag on ⇒ calls the card well-known path then `message/send`. Asserts request
  shapes + `Authorization` header on the A2A path.
- `a2a/mapping.test.ts` — a grounded artifact ⇒ populated `NexusAnswerResult` (≥1 evidence +
  provenance + route); a `failed` task ⇒ `null`; field-for-field losslessness vs. a known
  HTTP `NexusAnswerResult`.
- `a2a/transport.failure.test.ts` — timeout / non-200 / JSON-RPC error / missing card ⇒
  `null` (graceful degradation parity), reason logged via `logger.debug`.
- `client.searchAnswer.parity.test.ts` — same canned grounded payload expressed as (a) an
  HTTP `/search/answer` body and (b) an A2A task ⇒ both transports yield an **equal**
  `NexusAnswerResult` on the consumed fields.
- (Optional, if Nexus stack is up) integration: drive the real Probe client against a live
  flagged Nexus A2A server and diff against the HTTP path.

## 8. Rollout & reversibility

- Ship behind `transport: 'a2a'` / `PROBE_NEXUS_TRANSPORT=a2a` (default `'http'`) +
  `nexusToken`/`PROBE_NEXUS_TOKEN`.
- Keep `/search/answer` as the default and the fallback.
- Reversal = delete `src/nexus/a2a/` + the transport switch in `client.ts`. Nothing else
  touched; no other Nexus call affected.

## 9. Risks specific to Phase 1

| Risk | Mitigation |
|---|---|
| A2A field/method names differ from Phase 0 assumptions | Phase 0 server is the contract; the parity test (not field names) is the spec; both live in one repo so they version together |
| `graph_findings` lost over A2A (§5.4 gap) | Parity test flags a non-empty `graph_findings`; decision (b) documented; extend the server DataPart only if a real consumer regresses |
| Thin client diverges from the A2A spec over time | Contract tests pin behaviour; `@a2a-js/sdk` is the Phase 2+ upgrade path if drift appears |
| Token provisioning friction (gated skill) | Document `PROBE_NEXUS_TOKEN`; absent token ⇒ graceful `null`, never a hard failure |
| Card-discovery round-trip adds latency | Cache the card per client instance; measure (≤ one extra round-trip on first call) |
| Spike code rots into a half-migration | Hard non-goals (§2); flag-gated; explicit "delete to reverse" |

## 10. Open questions

Resolve during implementation:
- **`graph_findings` mapping fidelity** — keep skill as-is (decision (b), §5.4) vs. extend the
  Phase 0 server `DataPart`. Gated on whether a `searchAnswer.graph_findings` consumer exists.
- **`confidence` surfacing** — `NexusAnswerResult` has no `confidence` field; surface the
  A2A coarse band in `timing_ms`/meta, add a field, or drop it for Phase 1.
- **Thin client vs. `@a2a-js/sdk`** — confirm the thin client suffices for Phase 1; record
  the threshold (streaming/push/auth-schemes) that would justify the SDK in Phase 2.
- **Auth overlap with Phase 2** — Phase 1 uses one static token; ensure the config surface
  won't need a breaking change when Phase 2 adds real identity.

## 11. Definition of done

All §3 exit criteria met, §7 tests green, the §5.6 maintainability/observability comparison
appended here, and a one-paragraph **go/no-go recommendation for Phase 2**. On `approved`,
this spec is stamped and `begin_implementation` arms the specledger gate for
`probe/src/nexus/a2a/**`.

## 12. Review log (dry-run, 2026-06-18)

Pre-registration accountable-review pass against the specledger rubric. Issues dispositioned
**accepted** (body revised accordingly):

| Issue | Category | Disposition | Change |
|---|---|---|---|
| I-001 | risky-assumption | accepted | §5.4 names the `graph_findings` mapping gap explicitly and picks a default (decision (b)) with a test-driven trigger to revisit. |
| I-002 | untestable-requirement | accepted | Exit #2 parity is defined as field equality on the consumed fields for the *same* query (§7 method), not a vague "same result". |
| I-003 | missing-invariant | accepted | Added invariant §6.2 (no error escapes `NexusClient`) and §6.6 (no heavy dependency). |
| I-004 | scope-creep | accepted | Hard "one call only" (§2 / §6.5); other Nexus calls explicitly out of scope. |
| I-005 | risky-assumption | accepted | Token provisioning made a graceful-`null` path, never a hard failure (§5.2 / §9). |

> Dry-run record. When specledger is registered, run `critique` → `approve` to produce the
> canonical sidecar and stamp the content hash.

## 13. Implementation note (2026-06-18) — `probe/src/nexus/a2a/` landed

Phase 1 implemented in `probe/src/nexus/a2a/` (`types` · `mapping` · `transport`) + a
transport switch in `nexus/client.ts`, TDD/vitest, **19 new tests** (mapping 5, transport 9,
client-switch+parity 5); full Probe suite **225 passed**, `tsc --noEmit` clean. No new runtime
dependency (thin client; Probe stays at 2 deps).

- **Exit 1 ✅** — flag off (default `'http'`): `searchAnswer` issues the same
  `POST /search/answer`; no A2A code path, no card fetch (asserted by URL).
- **Exit 2 ✅** — flag on (`transport:'a2a'` or `PROBE_NEXUS_TRANSPORT=a2a`): discovers the
  card, sends `message/send` with a bearer token, maps the task artifact to
  `NexusAnswerResult`. A **parity** test asserts `answer`/`route_used`/`provenance` equal and
  the evidence projection (`doc_title`/`section_path`/`text`/`score`/`source_uri`) equal to
  the HTTP path for the same answer.
- **Exit 3 ✅** — `failed` task or empty-evidence ⇒ `null` (no confident answer without
  evidence), mirrored on the consumer side.
- **Exit 4 ✅** — every A2A failure mode (card fetch fail, missing skill, timeout, non-200,
  JSON-RPC error, HTTP 401, malformed) returns `null` and logs a `logger.debug` reason; no
  error escapes `NexusClient` (graceful-degradation parity).
- **Exit 6 ✅** — bespoke `/search/answer` untouched; reversal = delete `src/nexus/a2a/` +
  the switch.

**§5.6 maintainability/observability comparison (Exit 5).**
- **Glue size.** Direct path = one `post()` line at the call site. A2A path = a one-time
  isolated adapter (~250 LOC across 3 files) + a ~10-line switch in `searchAnswer`. Per-call
  cost is trivial; the adapter is reusable for future migrations and reversible in one delete.
- **Failure surface.** Direct collapses 3 modes → `null`; A2A collapses ~7 → `null`, each
  with a distinct `logger.debug` reason — *more* failure modes but identical caller contract
  and **richer** diagnosability (denied vs. unreachable vs. no-evidence are separable). The
  server also emits the OTel `a2a.retrieve_grounded` span, so the A2A path is at least as
  observable end-to-end.
- **Latency.** A2A adds the Phase-0 ~2.6 ms transport overhead + one card-discovery
  round-trip on first call (cached per client instance). Negligible against the LLM-bound
  `/search/answer` (seconds).

## 14. Phase-2 go/no-go — **GO**

The client path is a clean, isolated, flag-gated **drop-in** with identical
graceful-degradation and consumed-field parity, trivial per-call cost, richer failure
diagnosability, and a one-delete reversal. No new dependency, air-gap intact. **Recommend
proceeding to Phase 2** (external exposure + token auth, reusing Nexus's server-side policy
filter) and migrating Probe's remaining bespoke Nexus calls opportunistically behind the same
flag. The `graph_findings` fidelity gap (§5.4) stayed at decision (b) — no `searchAnswer`
consumer reads it, so no server `DataPart` change was needed.
