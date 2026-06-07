---
title: Nexus
description: Grounded knowledge retrieval — RAG + GraphRAG that answers only from citable sources, with confidence and provenance.
---

Nexus is the grounded knowledge base of the ecosystem. It answers questions about your organization's knowledge — documents, policies, configs — and your operational reality — OpenTelemetry traces — **only from evidence it can cite**. Every answer carries a confidence and a pointer back to the source chunk or trace that grounds it.

The problem it calibrates: ordinary RAG retrieves text and lets the model improvise; it will produce a plausible answer whether or not it has grounds. Nexus inverts that. The system decides what is retrievable and whether the answer is supportable; the LLM only narrates over evidence that already exists. If there is no citable source, the answer does not get made.

One-line identity: **enterprise RAG + GraphRAG for grounded knowledge retrieval** — the context provider that AI agents (code review, troubleshooting) lean on so they reason from real documents and observed telemetry rather than guesses.

## Core concepts

- **Hybrid search.** Three retrievers run in parallel and fuse with RRF (Reciprocal Rank Fusion, `k=60`): BM25 over Korean morphology (mecab-ko, so 조사/어미 are stripped correctly), Vector (768-dimension embeddings via Ollama), and Graph (2-hop entity traversal).
- **Evidence-driven edges.** No relationship (edge) exists without evidence. Every edge is bound to a source chunk or a trace query reference.
- **Dual knowledge layer — Designed vs. Observed.** Relationships extracted from design documents (`CALLS`, `PUBLISHES`) live alongside relationships observed in real traces (`CALLS_OBSERVED`, with call counts, error rates, latency).
- **Design-Observation diff.** Nexus flags `doc_only` (documented but never observed — dead docs), `observed_only` (observed but undocumented — shadow dependencies), and `conflict` (both present but mismatched).
- **Default-deny security.** PII/secrets (Korean SSN, card numbers, AWS keys, JWTs) are quarantined on detection and never indexed; every query is filtered by classification (`PUBLIC < INTERNAL < RESTRICTED`).
- **Index, not storage.** Originals stay in Git and in Tempo. Nexus stores only derived data — chunks, embeddings, graph edges.

## Quickstart

Nexus runs as a Docker Compose stack (PostgreSQL + Ollama + OTel Collector + Tempo + the FastAPI app). Commands transcribed from the source repo README.

### Prerequisites

- Docker Desktop
- (Optional) an Anthropic API key, for LLM grounded-answer generation

### 1. Clone & configure

```bash
git clone https://github.com/LivingLikeKrillin/khala.git nexus
cd nexus

cp .env.example .env
# set ANTHROPIC_API_KEY in .env if you want LLM answer generation
```

### 2. Start infrastructure

```bash
docker compose up -d
```

This starts the containers (PostgreSQL 16 + pgvector on 5432, Ollama on 11434, Tempo on 3200, OTel Collector on 4317/4318, and the FastAPI app on **8000**).

### 3. Pull the embedding model (first time only)

```bash
docker exec nexus-ollama ollama pull nomic-embed-text
```

### 4. Index documents

```bash
docker exec nexus-app nexus ingest ./docs
```

### 5. Search

```bash
docker exec nexus-app nexus query "결제 서비스 의존성"
```

The Web UI is served directly from FastAPI at `http://localhost:8000/` — no build step.

## How-to

### Get a grounded answer (with evidence)

```bash
curl -X POST http://localhost:8000/search/answer \
  -H "Content-Type: application/json" \
  -d '{"query": "결제 서비스가 어떤 서비스를 호출하나요?", "clearance": "INTERNAL"}'
```

The response includes evidence snippets with source URIs and provenance. Use `/search/answer/stream` for SSE streaming in the chat UI.

### Explore the knowledge graph

```bash
docker exec nexus-app nexus graph payment-service        # 1-hop
docker exec nexus-app nexus graph payment-service -h 2   # 2-hop
```

Or via the API: `GET /graph/{entity}` resolves by name or rid.

### Find design-vs-observation drift

```bash
docker exec nexus-app nexus otel-aggregate   # roll traces up into CALLS_OBSERVED
docker exec nexus-app nexus diff             # report doc_only / observed_only / conflict
```

The same report is available at `GET /diff`.

## Reference

- Source repo README: [github.com/LivingLikeKrillin/khala](https://github.com/LivingLikeKrillin/khala) (`README.md`)
- API contract, pipeline, MCP server, Slack bot, and UI integration docs live under that repo's `docs/` (`API_CONTRACT.md`, `PIPELINE_SPEC.md`, `MCP_SERVER.md`, `SLACK_BOT.md`, `UI_INTEGRATION.md`).
- MCP server exposes six tools — `nexus_search`, `nexus_answer`, `nexus_graph`, `nexus_suggest`, `nexus_diff`, `nexus_status` — via `python -m nexus.mcp`.

:::note[Last verified]
Source repo README (site re-run verification pending).
:::
