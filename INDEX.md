# Arbiter Index

## 🔴 미검토 (2)

| id | title | approved_by | date | linked_adrs |
|---|---|---|---|---|
| SPEC-nexus-bug-report-diagnosis-program | Bug reports become ranked hypotheses with evidence — khala grounds, a code-reading agent reads, the owner rules |  | 2026-09-23T11:24:45Z | ADR-0002, ADR-0004, ADR-0006, ADR-0010 |
| SPEC-specledger-a2a-publish-phase3 | Phase 3 — specledger publish to Nexus as an A2A task |  | 2026-06-18 | ADR-0001 |

## 🟡 검토중 (2)

| id | title | approved_by | date | linked_adrs |
|---|---|---|---|---|
| SPEC-nexus-code-semantic-cards | Generate a natural-language card from code and prove the generator repeats itself — matching is a later SPEC |  |  | ADR-0008 |
| SPEC-nexus-doc-code-anchors | A document that describes code should hold a typed reference into it, so "is this doc stale" is a join and not a judgement |  |  | ADR-0008 |

## 🟢 승인 (61)

| id | title | approved_by | date | linked_adrs |
|---|---|---|---|---|
| SPEC-arbiter-claude-code-critic | A keyless Arbiter critic — run the gate through claude -p, no paid key | LivingLikeKrillin |  | ADR-0004, ADR-0005, ADR-0007 |
| SPEC-arbiter-status-is-read-only | status() must not edit what it reports — flag a stale SPEC stamp the way an ADR already is | LivingLikeKrillin | 2026-09-05T09:52:52Z | ADR-0003 |
| SPEC-nexus-a2a-external-exposure-audit-phase2 | Phase 2 — Nexus A2A external exposure + audit trail | LivingLikeKrillin | 2026-06-18 | ADR-0001 |
| SPEC-nexus-a2a-server-phase0-spike | Phase 0 spike — Nexus A2A grounded-retrieval server | LivingLikeKrillin | 2026-06-18 | ADR-0001 |
| SPEC-nexus-access-jwt-auth | Browser identity from Cloudflare Access — verify the JWT, stop handing out a shared bearer | LivingLikeKrillin | 2026-07-10 | ADR-0004 |
| SPEC-nexus-answer-feedback | Answer feedback: a 👎 is a lead, not a rate | LivingLikeKrillin | 2026-08-14T06:00:00Z | ADR-0002, ADR-0008 |
| SPEC-nexus-answer-number-verification | Deterministic verification that answer numbers appear in the evidence | LivingLikeKrillin |  |  |
| SPEC-nexus-answer-quality-ruler | The answer-quality ruler — what it may call an abstention, a wrong document, and a signed label | LivingLikeKrillin | 2026-08-11T16:58:24Z | ADR-0002, ADR-0008, ADR-0010 |
| SPEC-nexus-answer-staleness-warning | Deterministic staleness warning on answer evidence (Unit 1, backend) | LivingLikeKrillin |  |  |
| SPEC-nexus-audit-query-hash | The audit hash re-identifies retained questions, and salt does not fix it | LivingLikeKrillin | 2026-08-14T08:00:00Z | ADR-0002, ADR-0008 |
| SPEC-nexus-bm25-length-normalization | Length normalisation for the keyword leg — an amendment to the cover-density choice | LivingLikeKrillin | 2026-09-03T18:40:00Z | ADR-0004, ADR-0006 |
| SPEC-nexus-citation-validation | Verify the LLM's citations against the evidence — the code checks, it doesn't trust | LivingLikeKrillin |  | ADR-0004, ADR-0006 |
| SPEC-nexus-claude-code-llm-dev-backend | A dev LLM backend that routes narration through the running Claude Code — no paid key | LivingLikeKrillin |  | ADR-0004 |
| SPEC-nexus-design-corpus-cutover | Retire the copy and read the source — a gap is safer than an overlap | LivingLikeKrillin |  | ADR-0002, ADR-0006, ADR-0008 |
| SPEC-nexus-deterministic-retrieval-order | Deterministic ordering in the retrieval legs — the same query must not depend on physical row order | LivingLikeKrillin | 2026-08-03T10:08:58Z | ADR-0006 |
| SPEC-nexus-document-lifecycle | Document lifecycle — origin, search, hide, and the inverse of every destructive act | LivingLikeKrillin | 2026-07-10 | ADR-0006 |
| SPEC-nexus-embed-generation-drift | Detect mixed embedding generations (partial re-embed guardrail) | LivingLikeKrillin |  |  |
| SPEC-nexus-embed-tokenizer-race | The over-length guard races the encoder - give it its own tokenizer | LivingLikeKrillin | 2026-08-05T01:28:06Z | ADR-0008 |
| SPEC-nexus-embedding-cutover-seam | The embedding cutover seam is half-built - the query path, the write path, and the wiring still hardcode the old generation | LivingLikeKrillin | 2026-08-04T13:28:28Z | ADR-0008 |
| SPEC-nexus-embedding-provenance-grain | The generation label is on the wrong grain: one row, two vectors, one lie | LivingLikeKrillin | 2026-08-14T13:00:00Z | ADR-0008, ADR-0009 |
| SPEC-nexus-generation-of-record | Which generation is this corpus on — declare it in the database, because two processes reading the same config disagreed and nothing noticed | LivingLikeKrillin |  | ADR-0006, ADR-0008, ADR-0009 |
| SPEC-nexus-graph-scope-filter | The graph channel must obey base_filter — stop cross-tenant / over-clearance / quarantined leakage | LivingLikeKrillin |  | ADR-0004, ADR-0006 |
| SPEC-nexus-index-completeness | Surface the coverage signal where someone reads it — the gap was measured, logged, and buried under an alarm that is always on | LivingLikeKrillin |  | ADR-0006, ADR-0008, ADR-0009 |
| SPEC-nexus-ko-eval-pool-sensitivity | A record of measurements already taken — how far the deferred pool adjudication could move the KURE verdict | LivingLikeKrillin | 2026-08-05 | ADR-0009, ADR-0008 |
| SPEC-nexus-korean-embedding-comparison | Korean embedding comparison — nomic-embed-text vs KURE-v1 on the pinned pack | LivingLikeKrillin | 2026-08-03T12:27:40Z | ADR-0008 |
| SPEC-nexus-korean-retrieval-eval | Korean retrieval evaluation set — a tokenizer-neutral ruler on a pinned public corpus | LivingLikeKrillin | 2026-08-02T09:52:01Z | ADR-0008 |
| SPEC-nexus-kure-embedding-swap | Swap the embedding model to KURE-v1 — dimension change, re-embed, and the ANN measurement the comparison could not make | LivingLikeKrillin | 2026-08-04T05:38:24Z | ADR-0008 |
| SPEC-nexus-llm-usage-capture | Capture per-call LLM token usage and cost (Unit A of cost tracking) | LivingLikeKrillin |  |  |
| SPEC-nexus-llm-usage-persistence | Persist LLM token usage + cost to search_log and v_search_health (Unit B) | LivingLikeKrillin |  |  |
| SPEC-nexus-multi-turn-narration | Multi-turn narration: answer the question that was asked about the conversation | LivingLikeKrillin | 2026-08-13T11:20:00Z | ADR-0002, ADR-0008 |
| SPEC-nexus-multi-turn-retrieval | Multi-turn retrieval: keep the question the user actually asked | LivingLikeKrillin | 2026-08-13T02:43:04Z | ADR-0002, ADR-0006, ADR-0008 |
| SPEC-nexus-notion-connection-health | Notion connection health — is the token real, and can we actually reach that root? | LivingLikeKrillin | 2026-07-10 | ADR-0004 |
| SPEC-nexus-notion-reconciliation | Notion deletion reconciliation — soft_delete/revive primitives + root-scoped prune | LivingLikeKrillin | 2026-07-09 | ADR-0006 |
| SPEC-nexus-notion-source-console | Notion source console — endpoint-first source management, background sync, previewed deletion | LivingLikeKrillin | 2026-07-10 | ADR-0006 |
| SPEC-nexus-query-text-retention | Keep the question, so the eval set can stop being written by the documents it grades | LivingLikeKrillin | 2026-08-12T00:00:00Z | ADR-0002, ADR-0009 |
| SPEC-nexus-ranking-precision | Ranking precision — cover-density lexical scoring and per-document diversity | LivingLikeKrillin |  | ADR-0004 |
| SPEC-nexus-retrieval-backstop-detector | Run the hash check unattended — one small job, and the findings from two detector designs that failed | LivingLikeKrillin | 2026-08-05 | ADR-0009, ADR-0008, ADR-0002 |
| SPEC-nexus-screenshot-text-extraction | Read the policy that lives inside screenshots — khala absorbs the friction, the organisation does not retype its documents | LivingLikeKrillin |  | ADR-0002, ADR-0004, ADR-0006, ADR-0010 |
| SPEC-nexus-search-recall | BM25 recall — the keyword leg answers nothing, and `route` answers nobody | LivingLikeKrillin | 2026-07-10 | ADR-0004 |
| SPEC-nexus-search-signal-completeness | Search signals — record the streaming path, and measure citation fabrication | LivingLikeKrillin |  | ADR-0004, ADR-0006 |
| SPEC-nexus-slack-bot | The Slack bot, revived — the lowest-friction on-ramp for a team that lives in Slack | LivingLikeKrillin | 2026-07-10 | ADR-0004 |
| SPEC-nexus-snippet-boundary-truncation | Evidence snippets truncate at a sentence boundary, not mid-sentence | LivingLikeKrillin |  | ADR-0004 |
| SPEC-nexus-stage-spans | Stage spans (Unit 1) — capture what each retrieval stage received and produced | LivingLikeKrillin | 2026-09-04 | ADR-0006 |
| SPEC-nexus-sufficiency-signal | Record whether the evidence answered the question — a per-search verdict, off by default | LivingLikeKrillin |  | ADR-0002, ADR-0006 |
| SPEC-nexus-tenant-read-scope | One token, more than one corpus to read — the mechanism only | LivingLikeKrillin |  | ADR-0002, ADR-0006, ADR-0008 |
| SPEC-nexus-vision-reader-of-record | Replace the reader that cannot repeat itself — qualify candidates on both axes, after fixing the one defect adjudication found | LivingLikeKrillin |  | ADR-0006, ADR-0010 |
| SPEC-nexus-vision-reproducibility | The reader must be able to repeat itself — ADR-0010's central invariant is false in production, and nothing was checking | LivingLikeKrillin |  | ADR-0006, ADR-0010 |
| SPEC-nexus-vision-source-ref | Give the citation a way back to the image — the recourse ADR-0010 admits the tier for has never been stored | LivingLikeKrillin |  | ADR-0004, ADR-0006, ADR-0010 |
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
| ADR-0010 | Machine-read text from images is evidence, of a lower tier — and the tier must travel with it | LivingLikeKrillin | 2026-08-09 | ADR-0002, ADR-0004, ADR-0006 |
