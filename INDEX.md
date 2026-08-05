# Arbiter Index

## 🔴 미검토 (1)

| id | title | approved_by | date | linked_adrs |
|---|---|---|---|---|
| SPEC-specledger-a2a-publish-phase3 | Phase 3 — specledger publish to Nexus as an A2A task |  | 2026-06-18 | ADR-0001 |

## 🟡 검토중 (0)


## 🟢 승인 (39)

| id | title | approved_by | date | linked_adrs |
|---|---|---|---|---|
| SPEC-arbiter-claude-code-critic | A keyless Arbiter critic — run the gate through claude -p, no paid key | LivingLikeKrillin |  | ADR-0004, ADR-0005, ADR-0007 |
| SPEC-nexus-a2a-external-exposure-audit-phase2 | Phase 2 — Nexus A2A external exposure + audit trail | LivingLikeKrillin | 2026-06-18 | ADR-0001 |
| SPEC-nexus-a2a-server-phase0-spike | Phase 0 spike — Nexus A2A grounded-retrieval server | LivingLikeKrillin | 2026-06-18 | ADR-0001 |
| SPEC-nexus-access-jwt-auth | Browser identity from Cloudflare Access — verify the JWT, stop handing out a shared bearer | LivingLikeKrillin | 2026-07-10 | ADR-0004 |
| SPEC-nexus-answer-number-verification | Deterministic verification that answer numbers appear in the evidence | LivingLikeKrillin |  |  |
| SPEC-nexus-answer-staleness-warning | Deterministic staleness warning on answer evidence (Unit 1, backend) | LivingLikeKrillin |  |  |
| SPEC-nexus-citation-validation | Verify the LLM's citations against the evidence — the code checks, it doesn't trust | LivingLikeKrillin |  | ADR-0004, ADR-0006 |
| SPEC-nexus-claude-code-llm-dev-backend | A dev LLM backend that routes narration through the running Claude Code — no paid key | LivingLikeKrillin |  | ADR-0004 |
| SPEC-nexus-deterministic-retrieval-order | Deterministic ordering in the retrieval legs — the same query must not depend on physical row order | LivingLikeKrillin | 2026-08-03T10:08:58Z | ADR-0006 |
| SPEC-nexus-document-lifecycle | Document lifecycle — origin, search, hide, and the inverse of every destructive act | LivingLikeKrillin | 2026-07-10 | ADR-0006 |
| SPEC-nexus-embed-generation-drift | Detect mixed embedding generations (partial re-embed guardrail) | LivingLikeKrillin |  |  |
| SPEC-nexus-embed-tokenizer-race | The over-length guard races the encoder - give it its own tokenizer | LivingLikeKrillin | 2026-08-05T01:28:06Z | ADR-0008 |
| SPEC-nexus-embedding-cutover-seam | The embedding cutover seam is half-built - the query path, the write path, and the wiring still hardcode the old generation | LivingLikeKrillin | 2026-08-04T13:28:28Z | ADR-0008 |
| SPEC-nexus-graph-scope-filter | The graph channel must obey base_filter — stop cross-tenant / over-clearance / quarantined leakage | LivingLikeKrillin |  | ADR-0004, ADR-0006 |
| SPEC-nexus-korean-embedding-comparison | Korean embedding comparison — nomic-embed-text vs KURE-v1 on the pinned pack | LivingLikeKrillin | 2026-08-03T12:27:40Z | ADR-0008 |
| SPEC-nexus-korean-retrieval-eval | Korean retrieval evaluation set — a tokenizer-neutral ruler on a pinned public corpus | LivingLikeKrillin | 2026-08-02T09:52:01Z | ADR-0008 |
| SPEC-nexus-kure-embedding-swap | Swap the embedding model to KURE-v1 — dimension change, re-embed, and the ANN measurement the comparison could not make | LivingLikeKrillin | 2026-08-04T05:38:24Z | ADR-0008 |
| SPEC-nexus-llm-usage-capture | Capture per-call LLM token usage and cost (Unit A of cost tracking) | LivingLikeKrillin |  |  |
| SPEC-nexus-llm-usage-persistence | Persist LLM token usage + cost to search_log and v_search_health (Unit B) | LivingLikeKrillin |  |  |
| SPEC-nexus-notion-connection-health | Notion connection health — is the token real, and can we actually reach that root? | LivingLikeKrillin | 2026-07-10 | ADR-0004 |
| SPEC-nexus-notion-reconciliation | Notion deletion reconciliation — soft_delete/revive primitives + root-scoped prune | LivingLikeKrillin | 2026-07-09 | ADR-0006 |
| SPEC-nexus-notion-source-console | Notion source console — endpoint-first source management, background sync, previewed deletion | LivingLikeKrillin | 2026-07-10 | ADR-0006 |
| SPEC-nexus-ranking-precision | Ranking precision — cover-density lexical scoring and per-document diversity | LivingLikeKrillin |  | ADR-0004 |
| SPEC-nexus-search-recall | BM25 recall — the keyword leg answers nothing, and `route` answers nobody | LivingLikeKrillin | 2026-07-10 | ADR-0004 |
| SPEC-nexus-search-signal-completeness | Search signals — record the streaming path, and measure citation fabrication | LivingLikeKrillin |  | ADR-0004, ADR-0006 |
| SPEC-nexus-slack-bot | The Slack bot, revived — the lowest-friction on-ramp for a team that lives in Slack | LivingLikeKrillin | 2026-07-10 | ADR-0004 |
| SPEC-nexus-snippet-boundary-truncation | Evidence snippets truncate at a sentence boundary, not mid-sentence | LivingLikeKrillin |  | ADR-0004 |
| SPEC-nexus-web-citation-verification | Web chat renders citation verification (verified / unverified) | LivingLikeKrillin |  |  |
| SPEC-probe-a2a-client-phase1 | Phase 1 — Probe as an A2A client of Nexus | LivingLikeKrillin | 2026-06-18 | ADR-0001 |
| SPEC-probe-cli | Probe gets a CLI — the deterministic spine as one command, the judgment left where it belongs | LivingLikeKrillin |  | ADR-0004, ADR-0005 |
| ADR-0001 | Adopt A2A (Agent2Agent) as Khala's agent-to-agent interoperability layer | LivingLikeKrillin | 2026-06-18 |  |
| ADR-0002 | Reframe Khala around staying in command of your own system in the AI era | LivingLikeKrillin | 2026-06-23 | ADR-0001 |
| ADR-0003 | The AI-era artifact lifecycle and the debt-repayment loop | LivingLikeKrillin | 2026-06-26 | ADR-0002 |
| ADR-0004 | Component architecture — grounding division, dual-mode, and dual deployment | LivingLikeKrillin | 2026-06-26 | ADR-0002, ADR-0003 |
| ADR-0005 | Component naming — Protoss-unit rename and forward-mapping layer | LivingLikeKrillin | 2026-06-30 | ADR-0002, ADR-0004 |
| ADR-0006 | Nexus entropy spine | LivingLikeKrillin | 2026-07-01T05:12:39Z | ADR-0002, ADR-0004 |
| ADR-0007 | Component rename migration landed — ADR-0005's deferred code/directory rename is complete | LivingLikeKrillin | 2026-07-11 | ADR-0004, ADR-0005 |
| ADR-0008 | Keep Nexus's own substrate; defer the Onyx adoption question with named resume conditions | LivingLikeKrillin | 2026-08-01T09:24:00Z | ADR-0002, ADR-0004, ADR-0006, ADR-0007 |
| ADR-0009 | The embedding-model block of ADR-0008 is lifted - what the director declared, and what stays open | LivingLikeKrillin | 2026-08-05T04:26:52Z | ADR-0008, ADR-0007 |
