---
title: Nexus
description: Grounded knowledge retrieval — RAG + GraphRAG that answers only from citable sources, with confidence and provenance.
---

Nexus is the ecosystem's knowledge base. It answers questions about your organization's knowledge (documents, policies, configs) and its operational reality (OpenTelemetry traces) **only from evidence it can cite**. Every answer carries a confidence score and a link back to the source chunk or trace it came from.

Ordinary RAG retrieves text and lets the model improvise, so it returns a plausible answer whether or not it has grounds. Nexus works the other way around: the system decides what can be retrieved and whether an answer is supported, and the model only writes over evidence that already exists. If nothing can be cited, Nexus returns no answer.

In short: **enterprise RAG + GraphRAG for grounded retrieval.** It's the context layer for code-review and troubleshooting agents, so they work from real documents and observed telemetry rather than guesses.

<svg class="kh-fig" viewBox="0 0 580 384" role="img" aria-label="A retrieval trace and its answer. For the query 'payment-service dependencies', three retrievers — BM25/mecab-ko, vector/768-d, graph/2-hop — each score candidate sources; RRF fuses them into one ranked list, producing a grounded answer: payment-service depends on ledger and fx-rate, cited to PIPELINE_SPEC.md at confidence 0.92.">
<defs><marker id="nx-a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="kh-fig-ah" d="M0 0 L10 5 L0 10 z"/></marker></defs>
<text class="kh-fig-q" x="24" y="22">› payment-service dependencies?</text>
<text class="kh-fig-h" x="24" y="52">BM25 · MECAB-KO</text>
<text class="kh-fig-d" x="30" y="72">PIPELINE_SPEC</text>
<rect class="kh-fig-track" x="150" y="67" width="100" height="6" rx="3"/>
<rect class="kh-fig-bar" x="150" y="67" width="86" height="6" rx="3"/>
<text class="kh-fig-d" x="30" y="92">API_CONTRACT</text>
<rect class="kh-fig-track" x="150" y="87" width="100" height="6" rx="3"/>
<rect class="kh-fig-bar" x="150" y="87" width="44" height="6" rx="3"/>
<text class="kh-fig-h" x="24" y="122">VECTOR · 768-D</text>
<text class="kh-fig-d" x="30" y="142">PIPELINE_SPEC</text>
<rect class="kh-fig-track" x="150" y="137" width="100" height="6" rx="3"/>
<rect class="kh-fig-bar" x="150" y="137" width="74" height="6" rx="3"/>
<text class="kh-fig-d" x="30" y="162">ledger.svc</text>
<rect class="kh-fig-track" x="150" y="157" width="100" height="6" rx="3"/>
<rect class="kh-fig-bar" x="150" y="157" width="58" height="6" rx="3"/>
<text class="kh-fig-h" x="24" y="192">GRAPH · 2-HOP</text>
<text class="kh-fig-d" x="30" y="212">payment→fx</text>
<rect class="kh-fig-track" x="150" y="207" width="100" height="6" rx="3"/>
<rect class="kh-fig-bar" x="150" y="207" width="66" height="6" rx="3"/>
<path class="kh-fig-line-acc" d="M250 72 C 296 72, 292 132, 320 132"/>
<path class="kh-fig-line-acc" d="M250 150 C 296 150, 302 132, 320 132"/>
<path class="kh-fig-line-acc" d="M250 210 C 296 210, 292 132, 320 132"/>
<path class="kh-fig-line-acc" d="M320 132 L336 132" marker-end="url(#nx-a)"/>
<rect class="kh-fig-panel" x="336" y="44" width="212" height="176" rx="8"/>
<text class="kh-fig-h" x="354" y="66">RRF · FUSED</text>
<line class="kh-fig-rule" x1="354" y1="80" x2="530" y2="80"/>
<text class="kh-fig-rk" x="354" y="102">1</text>
<text class="kh-fig-d" x="376" y="102">PIPELINE_SPEC.md</text>
<text class="kh-fig-rk" x="354" y="126">2</text>
<text class="kh-fig-d" x="376" y="126">ledger.svc</text>
<text class="kh-fig-rk" x="354" y="150">3</text>
<text class="kh-fig-d" x="376" y="150">payment→fx</text>
<path class="kh-fig-line-acc" d="M442 220 L442 252" marker-end="url(#nx-a)"/>
<rect class="kh-fig-panel" x="24" y="252" width="532" height="116" rx="8"/>
<text class="kh-fig-h" x="42" y="276">GROUNDED ANSWER</text>
<text class="kh-fig-verified" x="538" y="276" text-anchor="end">✓ CITED</text>
<line class="kh-fig-rule" x1="42" y1="290" x2="538" y2="290"/>
<text class="kh-fig-ans" x="42" y="313">payment-service → ledger, fx-rate</text>
<text class="kh-fig-s" x="42" y="333">documented + observed · no drift</text>
<text class="kh-fig-s" x="42" y="356">SOURCE</text>
<text class="kh-fig-d" x="96" y="356">PIPELINE_SPEC.md</text>
<text class="kh-fig-s" x="538" y="356" text-anchor="end">CONFIDENCE 0.92</text>
</svg>

## Core concepts

- **Hybrid search.** Three retrievers run in parallel and fuse with RRF (Reciprocal Rank Fusion, `k=60`): BM25 over Korean morphology (mecab-ko, so particles and endings are stripped correctly), Vector (768-dimension embeddings via Ollama), and Graph (2-hop entity traversal).
- **Evidence-driven edges.** No relationship (edge) exists without evidence. Every edge is bound to a source chunk or a trace query reference.
- **Dual knowledge layer — Designed vs. Observed.** Relationships extracted from design documents (`CALLS`, `PUBLISHES`) live alongside relationships observed in real traces (`CALLS_OBSERVED`, with call counts, error rates, latency).
- **Design-Observation diff.** Nexus flags `doc_only` (documented but never observed — dead docs), `observed_only` (observed but undocumented — shadow dependencies), and `conflict` (both present but mismatched).
- **Default-deny security.** PII/secrets (Korean SSN, card numbers, AWS keys, JWTs) are quarantined on detection and never indexed; every query is filtered by classification (`PUBLIC < INTERNAL < RESTRICTED`).
- **Index, not storage.** Originals stay in Git and in Tempo. Nexus stores only derived data — chunks, embeddings, graph edges.

## Quickstart

Nexus runs as a Docker Compose stack. By default only the **core** containers start (PostgreSQL + Ollama + the FastAPI app); the OTel observability pipeline is opt-in. The `task` one-liners below wrap the underlying `docker compose` commands — each step shows the raw equivalent too.

### Prerequisites

- Docker Desktop
- (Optional) [go-task](https://taskfile.dev) for the `task` shortcuts
- (Optional) an Anthropic API key, for LLM grounded-answer generation

### 1. Clone & configure

```bash
git clone https://github.com/LivingLikeKrillin/khala.git
cd khala
cp nexus/.env.example nexus/.env
# (optional) set ANTHROPIC_API_KEY in nexus/.env for LLM answer generation
```

### 2. Start (core containers only)

```bash
task up        # or: cd nexus && docker compose up -d
```

Starts PostgreSQL 16 + pgvector (5432), Ollama (11434), and the FastAPI app on **8000**. The OTel collector + Tempo are **opt-in** — add them only for trace aggregation: `docker compose --profile observability up -d`.

### 3. Pull the embedding model (first time only)

```bash
task models    # or: docker compose exec nexus-ollama ollama pull nomic-embed-text
```

### 4. Index documents & search

Open `http://localhost:8000/` and ask in the chat — or use the CLI:

```bash
docker compose exec nexus-app nexus ingest ./docs
docker compose exec nexus-app nexus query "payment service dependencies"
```

The Web UI is served directly from FastAPI at `http://localhost:8000/` — no build step. New to it? See **[Using the Nexus web app](/tools/nexus-web/)**.

### Update / stop

```bash
git pull && task update    # rebuild image, restart, apply DB migrations
task down                  # stop (or: docker compose down)
```

## How-to

### Get a grounded answer (with evidence)

```bash
curl -X POST http://localhost:8000/search/answer \
  -H "Content-Type: application/json" \
  -d '{"query": "which services does the payment service call?", "clearance": "INTERNAL"}'
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
