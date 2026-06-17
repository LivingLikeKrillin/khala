---
id: SPEC-nexus-a2a-server-phase0-spike
type: spec
title: "Phase 0 spike — Nexus A2A grounded-retrieval server"
status: draft
date: 2026-06-18
linked_adrs: [ADR-0001]
tags: [a2a, nexus, spike, interop, grounding]
---

# Phase 0 spike — Nexus A2A grounded-retrieval server

> Implements **Phase 0** of [ADR-0001](../adr/ADR-0001-adopt-a2a-inter-agent-interop.md):
> stand up a minimal, flag-gated **Nexus A2A server** so a third-party A2A agent can
> discover Nexus, delegate a query, and receive a grounded answer **with evidence,
> provenance, and confidence intact** — then decide whether A2A is worth carrying
> forward.

## 1. Goal

Prove the single load-bearing claim behind ADR-0001 at the lowest possible cost:

> An external A2A-speaking agent can discover Nexus via an Agent Card, delegate a
> retrieval task, and receive Nexus's **full grounded answer** (answer + evidence +
> provenance + confidence) over A2A — without weakening any determinism,
> classification, or quarantine guarantee.

If that holds with acceptable overhead, Phase 1 (Probe as A2A client) is justified. If
it does not, the spike is deleted behind its flag at near-zero cost.

## 2. Scope

### In scope
- One A2A **Agent Card** for Nexus, served from the existing FastAPI app.
- One A2A **skill**: `retrieve_grounded` — wraps the existing grounded-answer path.
- A **`NexusResponse` → A2A artifact** mapping that preserves the evidence packet.
- Server-side **policy enforcement** (tenant, classification/clearance, default-deny,
  quarantine exclusion) on the A2A path — identical guarantees to the HTTP/MCP paths.
- A **feature flag** to enable/disable the entire A2A surface.
- **Contract + integration tests** and OTel spans for A2A tasks.

### Explicit non-goals (deferred)
- Nexus as an A2A **client** (calling other agents). Server only.
- Migrating Probe/specledger off bespoke calls (Phase 1+).
- Multi-skill catalog, streaming/long-running tasks, push notifications.
- Production auth/identity federation (Phase 2). Phase 0 uses a single static token.
- Any change to Nexus core retrieval, ranking, or the MCP server.

## 3. Exit criteria (the spike is "done")

0. **(Feasibility gate — check first.)** The pinned A2A SDK/spec version supports a
   **first-class structured data part** (JSON) on a task artifact. The entire grounding
   bridge (§5.4) depends on this. If structured data parts are unsupported, the mapping
   is not expressible over A2A → **stop and report**; the remaining criteria are moot.
   → **✅ PASSED (2026-06-18, desk check vs. A2A v1.0):** A2A defines `DataPart`, a
   "structured data segment (e.g., JSON)" that is a valid `Part` of an **artifact** — so
   the §5.4 mapping (`[TextPart(answer), DataPart(evidence packet)]`) is expressible. The
   implementation must still re-verify against the actual pinned SDK build.
1. A reference A2A client (off-the-shelf SDK) fetches Nexus's Agent Card and lists the
   `retrieve_grounded` skill.
2. The client sends a query task; the returned artifact contains **(a)** a narrated
   answer **and (b)** a structured evidence packet: ≥1 `evidence_snippet` with
   `source_uri`/`section_path`, a `provenance` list, a `confidence` value, and the
   `route_used`.
3. A **contract test** fails the build if any A2A answer is returned **without** an
   evidence packet (grounding-preservation guard).
4. A request with insufficient clearance / a quarantined target returns **no**
   privileged content over A2A (parity with `base_filter` on the existing paths).
5. Measured latency overhead of the A2A path vs. the direct `/search/answer` path is
   recorded and judged acceptable (target: p50 transport overhead < 50 ms).
   **Measurement method:** run the same query N=100 times through both the A2A task and a
   direct in-process call to the same grounded-answer service; overhead = `p50(a2a_total)
   − p50(direct_total)`. Both share identical retrieval/LLM work, so the difference
   isolates A2A serialization + JSON-RPC transport. Record p50/p95 and the raw retrieval
   share for context.
6. The whole surface is off when `NEXUS_A2A_ENABLED` is unset/false, with zero impact
   on existing endpoints.

## 4. Background & constraints (from ADR-0001)

- **Layering:** A2A is the *agent ↔ agent* layer; MCP stays the *agent ↔ tool* layer.
  This spike adds A2A **alongside** MCP; it does not replace or re-expose it.
- **Grounding is non-negotiable.** "System decides, LLM narrates." Classification,
  clearance, route selection, and quarantine remain deterministic and **server-side**;
  a calling agent can never widen its own clearance.
- **Air-gap.** A2A is plain HTTP + JSON-RPC 2.0; the spike adds no external dependency
  beyond a pinned A2A SDK, consistent with Nexus's self-host posture.
- **Adapter isolation.** Per Nexus's existing discipline (`EmbeddingService`,
  `LLMService`, `GraphRepository`), the A2A surface lives behind an adapter so protocol
  churn cannot leak into Nexus core.

## 5. Design

### 5.1 Placement

New, self-contained module — no edits to retrieval/ranking core:

```
nexus/nexus/a2a/
├── __init__.py
├── card.py        # builds the Agent Card from config (name, url, version, skills)
├── server.py      # JSON-RPC 2.0 handler; mounts onto the existing FastAPI app
├── mapping.py     # NexusResponse  <->  A2A task artifact (the grounding bridge)
└── policy.py      # resolves caller -> tenant + clearance; applies default-deny
```

Wiring point: `api.py` conditionally mounts the A2A routes when `NEXUS_A2A_ENABLED`
is true. Everything is import-light and inert when the flag is off.

### 5.2 Agent Card (discovery)

**Pinned protocol: A2A v1.0.** Served at the spec-mandated path
**`https://<base>/.well-known/agent-card.json`**. Grounding is declared via the
**official `AgentExtension` mechanism** (an entry in `capabilities.extensions`), not an
ad-hoc top-level key. Shape:

```jsonc
{
  "name": "Nexus",
  "description": "Grounded knowledge retrieval over org docs + OTel telemetry. Returns evidence-bound answers only.",
  "url": "https://<nexus-host>/a2a",
  "version": "0.1.0-spike",
  "provider": { "organization": "Khala" },
  "capabilities": {
    "streaming": false,
    "pushNotifications": false,
    "extensions": [
      {
        "uri": "https://khala.dev/a2a/ext/grounding/v1",
        "description": "Answers are evidence-bound; classification/clearance is enforced server-side.",
        "required": false,
        "params": {
          "grounded": true,
          "evidenceBound": true,
          "clearanceModel": "server-enforced",
          "evidenceSchemaRef": "https://<nexus-host>/a2a/schemas/evidence-packet.json"
        }
      }
    ]
  },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain", "application/json"],
  "skills": [
    {
      "id": "retrieve_grounded",
      "name": "Grounded knowledge retrieval",
      "description": "Answer a question from indexed org knowledge; returns answer + evidence + provenance + confidence. Never asserts ungrounded claims.",
      "tags": ["rag", "graphrag", "grounded", "evidence-bound", "server-enforced-clearance", "korean"],
      "examples": ["결제 서비스가 발행하는 토픽이 뭐야?"],
      "inputModes": ["text/plain"],
      "outputModes": ["text/plain", "application/json"]
    }
  ]
}
```

The card declares grounding **structurally** — a consuming agent detects "evidence-bound,
server-enforced clearance" by reading the `grounding/v1` extension in
`capabilities.extensions` (+ a machine-readable `evidenceSchemaRef`) and the skill `tags`,
not by parsing prose. The extension `uri` is the Khala-owned identifier; field placement
follows the A2A v1.0 `AgentExtension` schema.

### 5.3 Skill contract — `retrieve_grounded`

- **Input:** an A2A task whose message carries the user query (text). Optional metadata:
  `tenant`, `classification_max`, `route` — but these are **requests, not grants**
  (see policy).
- **Execution:** the A2A handler calls the *existing* grounded-answer path (the same
  service behind `POST /search/answer`) — no new retrieval logic.
- **Output:** one A2A artifact with two parts:
  1. **text part** — the narrated answer (markdown), identical to the HTTP answer.
  2. **data part** (`application/json`) — the evidence packet (see mapping).

Non-streaming for Phase 0 (single request/response task).

### 5.4 `NexusResponse` → A2A artifact mapping (the grounding bridge)

This is the heart of the spike. The mapping is **total** and **lossless** for the
grounding fields:

| `NexusResponse` field | A2A artifact location | Required |
|---|---|---|
| narrated answer (markdown) | text part | yes |
| `evidence_snippets[]` (`doc_title`, `section_path`, `text`, `score`, `source_uri`) | data part `.evidence[]` | **yes (≥1)** |
| `provenance[]` (`source_uri`, `source_version`, `doc_rid`) | data part `.provenance[]` | **yes** |
| `confidence` | data part `.confidence` | yes |
| `route_used` | data part `.route` | yes |
| `tenant`, `clearance_applied` | data part `.policy` | yes |

If the underlying response has **no** evidence (e.g., LLM failure path), the A2A task is
completed with the **`failed` task state** defined by the pinned A2A spec (not an
invented "uncertain" state), and its message/artifact carries **(a)** a plain-text
reason ("답변을 생성할 수 없습니다 — 근거 부족") and **(b)** any evidence snippets that
**were** retrieved, in the same data-part shape. A confident answer is **never** emitted
without ≥1 evidence snippet. (Mirrors Nexus's "answer cannot be generated, but evidence
is still returned" rule.) *Confirmed against A2A v1.0:* the `TaskState` enum includes a
`Failed` member (wire form **`TASK_STATE_FAILED`** in v1.0's SCREAMING_SNAKE naming) — a
valid, non-invented state.

### 5.5 Policy (server-side, default-deny)

- The caller's identity (Phase 0: a static bearer token mapped to one tenant +
  clearance in config) determines `tenant` and `classification_max`. Caller-supplied
  `tenant`/`classification_max` may only **narrow**, never widen.
- The existing `base_filter` (tenant + clearance + `is_quarantined = false` +
  `status = 'active'`) applies unchanged on the retrieval the A2A path triggers.
- Missing/invalid token → default-deny (no card-privileged calls; the Agent Card itself
  may be public, but skill execution requires the token).

### 5.6 Observability

Wrap each A2A task in an OTel span (`a2a.retrieve_grounded`) with attributes:
`tenant`, `route`, `evidence_count`, `confidence`, `latency_ms`, `denied` — so the
overhead measurement (exit criterion 5) and audit (Phase 2 groundwork) come for free.

## 6. Invariants

1. **No answer without evidence.** Every successful A2A artifact contains ≥1 evidence
   snippet and a provenance list. Enforced by contract test, not convention.
2. **Server decides policy.** Clearance/tenant/quarantine are resolved server-side from
   the token; caller input can only narrow scope.
3. **No core changes.** Retrieval, ranking, classification, and the MCP server are
   byte-for-byte unchanged; A2A is purely additive behind a flag.
4. **Off by default.** `NEXUS_A2A_ENABLED` unset ⇒ no routes, no overhead, no surface.
5. **One token ⇒ exactly one `(tenant, clearance)`.** A bearer token resolves to a
   single, fixed `(tenant, clearance)` pair from config — never a set, never
   caller-overridable. An unknown/rotated/removed token resolves to nothing → default-deny.
   This is the Phase 0 identity model and is asserted by `test_a2a_policy.py`.

## 7. Test plan (TDD)

Red → green, contract tests first:

- `test_a2a_card.py` — Agent Card is served, lists `retrieve_grounded`, validates
  against the pinned A2A card schema.
- `test_a2a_grounding_contract.py` — **the guard:** for a known query, the artifact
  MUST contain answer + ≥1 evidence + provenance + confidence + route. A stubbed
  no-evidence response MUST yield a `Failed` task (`TASK_STATE_FAILED`), never a
  confident answer.
- `test_a2a_policy.py` — low-clearance token cannot retrieve `CONFIDENTIAL` content;
  quarantined docs never appear; caller-asserted wider clearance is ignored;
  **one token resolves to exactly one `(tenant, clearance)`** and an unknown/rotated
  token is default-denied (invariant §6.5).
- `test_a2a_disabled.py` — with the flag off, A2A routes 404 and existing endpoints are
  unaffected.
- `test_a2a_parity.py` — same query via A2A vs. `/search/answer` yields the same answer
  text and the same evidence set (mapping is lossless).
- Integration: drive the flow end-to-end with a reference A2A client SDK (exit
  criteria 1–2) and record transport overhead (exit criterion 5).

## 8. Rollout & reversibility

- Ship behind `NEXUS_A2A_ENABLED` (default false) + `NEXUS_A2A_TOKEN` (single static
  token) + `NEXUS_A2A_TENANT` / `NEXUS_A2A_CLEARANCE` mapping in config.
- Pin the A2A SDK/protocol version; isolate it in `nexus/a2a/` behind the adapter.
- Reversal = delete `nexus/a2a/` + the conditional mount. Nothing else touched.

## 9. Risks specific to the spike

| Risk | Mitigation |
|---|---|
| A2A SDK field/method names differ from assumptions here | Treat §5.2/§5.3 shapes as intent; bind exact names to the pinned SDK at impl time; the contract tests, not the field names, are the spec |
| Evidence packet silently dropped in mapping | `test_a2a_grounding_contract.py` is a build-blocking guard |
| Spike code rots into a half-product | Hard non-goals (§2); flag-gated; explicit "delete to reverse" exit |
| Overhead unacceptable | Exit criterion 5 measures it; a failed budget is a valid "stop" outcome |

## 10. Open questions

Resolved by the Exit-0 desk check (2026-06-18):
- ~~Pinned A2A spec/SDK version and the exact well-known Agent Card path.~~ →
  **A2A v1.0**, card at `/.well-known/agent-card.json`. Note v1.0 `TaskState` enum is
  SCREAMING_SNAKE (`TASK_STATE_FAILED`, etc.).
- ~~How to structurally declare grounding on the card.~~ → official `AgentExtension` in
  `capabilities.extensions` (§5.2).

Still open (resolve during implementation):
- Whether the Agent Card is public or token-gated (default: card public, skill gated).
- Confidence semantics over A2A — surface raw `confidence` or a coarse band?
- Korean-first examples in the card vs. bilingual.
- Exact pinned **SDK build** (language + version) and re-verification of `DataPart` /
  `AgentExtension` shapes against that build.

## 11. Definition of done

All §3 exit criteria met, §7 tests green, overhead recorded, and a one-paragraph
**go/no-go recommendation for Phase 1** appended here. On `approved`, this spec is
stamped and `begin_implementation` arms the specledger gate for `nexus/a2a/**`.

## 12. Review log (dry-run, 2026-06-18)

Pre-registration accountable-review pass against the specledger rubric. All issues
dispositioned **accepted** (body revised accordingly):

| Issue | Category | Disposition | Change |
|---|---|---|---|
| I-001 | risky-assumption | accepted | Added Exit criterion **0** — verify SDK supports structured data parts *first* (the grounding bridge depends on it). |
| I-002 | untestable-requirement | accepted | Defined the overhead measurement method in Exit #5 (A2A vs. direct in-process, N=100, p50 diff). |
| I-003 | undefined | accepted | §5.4 no-evidence path now maps to the A2A `failed` state + attached evidence (no invented "uncertain" state). |
| I-004 | missing-invariant | accepted | Added invariant §6.5 "one token ⇒ exactly one (tenant, clearance)" + `test_a2a_policy` case. |
| I-005 | unverifiable-claim | accepted | Agent Card now declares grounding structurally via the official `AgentExtension` (`capabilities.extensions`) + skill tags, not prose. |

> Dry-run record. When specledger is registered, run `critique` → `approve` to produce
> the canonical sidecar and stamp the content hash.

## 13. Exit-0 feasibility finding (2026-06-18)

Desk check of Exit criterion 0 against the **A2A v1.0** specification. **Verdict: GO** —
every load-bearing assumption is satisfied by the spec:

| Dependency | A2A v1.0 fact | Result |
|---|---|---|
| Structured JSON part on an artifact | `DataPart` — a structured data `Part` of a message **or artifact** | ✅ grounding bridge expressible |
| No-evidence → failure state | `TaskState.Failed` (`TASK_STATE_FAILED`) | ✅ valid state |
| Structural grounding declaration on the card | `AgentExtension` in `capabilities.extensions` | ✅ (replaced ad-hoc `x-khala`) |
| Discovery path | `/.well-known/agent-card.json` | ✅ path fixed |

Caveat: this is a documentation desk check; the implementation must re-verify the
`DataPart` / `AgentExtension` shapes against the actual pinned SDK build (§10).

Sources: [A2A spec](https://a2a-protocol.org/latest/specification/) ·
[Part / DataPart](https://a2acn.com/en/docs/concepts/part/) ·
[Extensions](https://a2a-protocol.org/latest/topics/extensions/) ·
[AgentCard](https://agent2agent.info/docs/concepts/agentcard/) ·
[What's new in v1.0](https://a2a-protocol.org/latest/whats-new-v1/)
