---
title: Nexus
description: Retrieval that answers only from citable sources, with verified citations and provenance.
---

Nexus is the ecosystem's knowledge base. It answers questions about your organization's knowledge (documents, policies, configs) and its operational reality (OpenTelemetry traces) **only from evidence it can cite**. Every answer carries a confidence score and a link back to the source chunk or trace it came from.

Ordinary RAG retrieves text and lets the model improvise, so it returns a plausible answer whether or not it has grounds. Nexus works the other way around: the system decides what can be retrieved and whether an answer is supported, and the model only writes over evidence that already exists. If nothing can be cited, Nexus returns no answer.

In short: **enterprise retrieval for grounded answers.** It's the context layer for code-review and troubleshooting agents, so they work from real documents and observed telemetry rather than guesses.

<svg class="kh-fig" viewBox="0 0 580 384" role="img" aria-label="A retrieval trace and its answer. For the query 'payment-service dependencies', two retrievers — BM25 over Korean morphology and vector search over pgvector — score candidate chunks, and RRF fuses them into one ranked list. A 2-hop graph lookup runs separately: it is not scored and does not affect the ranking, but its edges are attached to the answer. The grounded answer states that payment-service depends on ledger and fx-rate, with a citation verified against the evidence packet.">
<defs><marker id="nx-a" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path class="kh-fig-ah" d="M0 0 L10 5 L0 10 z"/></marker></defs>
<text class="kh-fig-q" x="24" y="22">› payment-service dependencies?</text>
<text class="kh-fig-h" x="24" y="52">BM25 · MECAB-KO</text>
<text class="kh-fig-d" x="30" y="72">PIPELINE_SPEC</text>
<rect class="kh-fig-track" x="150" y="67" width="100" height="6" rx="3"/>
<rect class="kh-fig-bar" x="150" y="67" width="86" height="6" rx="3"/>
<text class="kh-fig-d" x="30" y="92">API_CONTRACT</text>
<rect class="kh-fig-track" x="150" y="87" width="100" height="6" rx="3"/>
<rect class="kh-fig-bar" x="150" y="87" width="44" height="6" rx="3"/>
<text class="kh-fig-h" x="24" y="122">VECTOR · PGVECTOR</text>
<text class="kh-fig-d" x="30" y="142">PIPELINE_SPEC</text>
<rect class="kh-fig-track" x="150" y="137" width="100" height="6" rx="3"/>
<rect class="kh-fig-bar" x="150" y="137" width="74" height="6" rx="3"/>
<text class="kh-fig-d" x="30" y="162">ledger.svc</text>
<rect class="kh-fig-track" x="150" y="157" width="100" height="6" rx="3"/>
<rect class="kh-fig-bar" x="150" y="157" width="58" height="6" rx="3"/>
<path class="kh-fig-line-acc" d="M250 72 C 296 72, 292 132, 320 132"/>
<path class="kh-fig-line-acc" d="M250 150 C 296 150, 302 132, 320 132"/>
<path class="kh-fig-line-acc" d="M320 132 L336 132" marker-end="url(#nx-a)"/>
<line class="kh-fig-rule" x1="24" y1="186" x2="250" y2="186"/>
<text class="kh-fig-h" x="24" y="208">GRAPH · 2-HOP</text>
<text class="kh-fig-d" x="30" y="228">payment→fx · payment→ledger</text>
<text class="kh-fig-s" x="30" y="246">not scored — attached after fusion</text>
<path class="kh-fig-line-acc" d="M250 228 C 300 228, 330 236, 330 252" marker-end="url(#nx-a)"/>
<rect class="kh-fig-panel" x="336" y="44" width="212" height="176" rx="8"/>
<text class="kh-fig-h" x="354" y="66">RRF · BM25 + VECTOR</text>
<line class="kh-fig-rule" x1="354" y1="80" x2="530" y2="80"/>
<text class="kh-fig-rk" x="354" y="102">1</text>
<text class="kh-fig-d" x="376" y="102">PIPELINE_SPEC.md</text>
<text class="kh-fig-rk" x="354" y="126">2</text>
<text class="kh-fig-d" x="376" y="126">ledger.svc</text>
<text class="kh-fig-rk" x="354" y="150">3</text>
<text class="kh-fig-d" x="376" y="150">API_CONTRACT.md</text>
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

- **Hybrid search.** Two retrievers run in parallel and fuse with RRF (Reciprocal Rank Fusion, `k=60`): BM25 over Korean morphology (mecab-ko, so particles and endings are stripped correctly) and vector search over pgvector. Fused results are then capped per document so one file cannot flood the answer.
- **Graph is context, not ranking.** A 2-hop entity traversal runs on graph-enabled routes, but it happens *after* fusion and never contributes to a hit's score. Its edges are returned alongside the answer, not blended into the ranking.
- **Citations are verified, not trusted.** The model is asked to cite, and then the citations are checked in code against the evidence packet it was actually given. Anything that does not resolve is reported separately as unverified rather than being passed off as a source. Numbers in the answer are checked the same way.
- **Evidence-driven edges.** No relationship (edge) exists without evidence. Every edge is bound to a source chunk or a trace query reference.
- **Dual knowledge layer — Designed vs. Observed.** Relationships extracted from design documents (`CALLS`, `PUBLISHES`) live alongside relationships observed in real traces (`CALLS_OBSERVED`, with call counts, error rates, latency).
- **Design-Observation diff.** Nexus flags `doc_only` (documented but never observed — dead docs), `observed_only` (observed but undocumented — shadow dependencies), and `conflict` (both present but mismatched).
- **Default-deny security.** PII/secrets (Korean SSN, card numbers, AWS keys, JWTs) are quarantined on detection and never indexed; every query is filtered by classification (`PUBLIC < INTERNAL < RESTRICTED`).
- **Provenance tier.** A chunk written by a person and a chunk a model read out of a screenshot are not the same kind of evidence. Machine-read text is labelled as such, and the label travels all the way into the prompt, the API response, and the web UI — so an answer never quietly launders an extraction into an authored policy.
- **Declared index generations.** The embedding model, its dimension, and the vector column move together as one generation, declared append-only in the database. Ingestion is refused before a single document is collected if the running configuration does not match a declared generation — the failure mode this closes is a documented command silently writing into a column nothing searches. The repository default is `nomic-embed-text` (768-d); a KURE-v1 (1024-d) generation is available and selected per deployment.
- **Section fill — retrieval picks the document, then fills in the rest of it.** Retrieval decides two things: *which document*, and *which passage inside it*. Measurement showed the first is reliable and the second is not — a question and the passage that answers it can share no vocabulary at all, in which case no ranking reaches that passage. So when one document saturates the per-document cap, the remaining sections of that same document are added **to the evidence, not to the ranking**: recall and top-1 are byte-identical, only the packet grows. On by default in the shipped configuration, off in the code default so that a caller without configuration does not touch the database.
- **Evidence fit — the system knows when it found nothing good.** Rank fusion scores by `1/(k + rank)`, which carries rank and discards magnitude, so a well-matched query and an off-corpus one came out indistinguishable. Both retrieval legs already compute magnitude to sort by; it is now kept. When *both* are weak the narration contract changes — the answer says up front that the question is outside what the evidence covers, and stays short. It does not block: a wrong threshold costs brevity, not a withheld answer.
- **Document debt travels with the evidence.** If a cited document has been superseded, or shares its title with another active document — which makes a `[source: title]` citation ambiguous — the answer is told. Only what is deterministically recorded qualifies. Semantic contradiction between documents is deliberately **not** judged here: doing it needs a judge model, and the evidence for that path is poor enough that the system describes conflicts without vouching for them.
- **Code anchors — the names a document calls, checked against the code as it is now.** Ingestion binds back-ticked symbols in each chunk to the code index. At answer time the packet reports how many of the names a cited paragraph uses still exist, and which do not, resolved in a single set query rather than one lookup per anchor. A document that says `FooService` after `FooService` was deleted stops being quietly authoritative.
- **Follow-up questions are rewritten conservatively, or not at all.** "So when does that start?" has no content words. With conversation history present, the query is rewritten — but only four edits are permitted (fill in a pronoun, drop a formatting request, carry a fact the user supplied, drop a source restriction), and the original query is always kept as its own retrieval channel so a bad rewrite has a floor under it. With no history the model is not called at all.
- **Staleness is shown, not enforced.** Answers carry a per-snippet age warning against a per-type TTL. It is a label for the reader; it deliberately does not re-rank or exclude anything.
- **Honest absence.** If nothing can be cited, Nexus does not call the model at all — it returns a fixed statement that it has no evidence, and says so in the response payload.
- **Index, not storage.** Originals stay in Git and in Tempo. Nexus stores only derived data — chunks, embeddings, graph edges.

### What happens between the ranked list and the answer you read

Ranking is the visible half. The half that decides whether an answer is trustworthy happens after it: one assembly point attaches everything the reader needs to judge the evidence, and one verification pass checks the model's output against the evidence it was actually handed.

<svg class="kh-fig" viewBox="0 0 580 358" role="img" aria-label="The pipeline from ranked hits to a verified answer. Ranked hits feed a single evidence packet assembly point, which attaches the snippet, provenance tier, staleness, code anchors, document debt and filled sections. An evidence-fit check follows: when both retrieval legs are weak, the narration contract changes to a shorter, scoped answer rather than blocking it. The model then narrates, and a verification pass in code checks that every citation resolves against the packet and every number appears in it. Unresolved citations are reported rather than hidden.">
  <rect class="kh-fig-box" x="195" y="14" width="190" height="26" rx="3"/>
  <text class="kh-fig-d" x="290" y="27" text-anchor="middle">ranked hits · per-doc cap</text>
  <path class="kh-fig-line" d="M290 40 L290 62"/>

  <text class="kh-fig-h" x="110" y="52">EVIDENCE PACKET</text>
  <text class="kh-fig-s" x="470" y="52" text-anchor="end">one packet, four surfaces</text>
  <rect class="kh-fig-surface" x="110" y="62" width="360" height="72" rx="3"/>
  <text class="kh-fig-d" x="126" y="82">snippet</text>
  <text class="kh-fig-d" x="126" y="101">provenance tier</text>
  <text class="kh-fig-d" x="126" y="120">staleness</text>
  <text class="kh-fig-d" x="306" y="82">code anchors</text>
  <text class="kh-fig-d" x="306" y="101">document debt</text>
  <text class="kh-fig-d" x="306" y="120">filled sections</text>
  <path class="kh-fig-line" d="M290 134 L290 154"/>

  <rect class="kh-fig-box-acc" x="210" y="154" width="160" height="26" rx="3"/>
  <text class="kh-fig-rk" x="290" y="167" text-anchor="middle">evidence fit?</text>
  <path class="kh-fig-line-acc" d="M370 167 L392 167"/>
  <text class="kh-fig-s" x="398" y="161">both legs weak:</text>
  <text class="kh-fig-s" x="398" y="174">say so, answer short</text>
  <path class="kh-fig-line" d="M290 180 L290 200"/>

  <rect class="kh-fig-box" x="225" y="200" width="130" height="26" rx="3"/>
  <text class="kh-fig-d" x="290" y="213" text-anchor="middle">model narrates</text>
  <path class="kh-fig-line" d="M290 226 L290 248"/>

  <text class="kh-fig-h" x="140" y="238">VERIFY IN CODE</text>
  <text class="kh-fig-s" x="440" y="238" text-anchor="end">not in the prompt</text>
  <rect class="kh-fig-surface" x="140" y="248" width="300" height="52" rx="3"/>
  <text class="kh-fig-d" x="156" y="267">every citation resolves against the packet</text>
  <text class="kh-fig-d" x="156" y="286">every number appears in the evidence</text>
  <path class="kh-fig-line-acc" d="M290 300 L290 318"/>

  <rect class="kh-fig-box-acc" x="205" y="318" width="170" height="26" rx="3"/>
  <text class="kh-fig-rk" x="290" y="331" text-anchor="middle">answer + citations</text>
  <text class="kh-fig-s" x="290" y="352" text-anchor="middle">unresolved citations are reported, never hidden</text>
</svg>

Two properties of this stage are worth stating plainly, because both were bought with defects:

- **Everything attaches at one point.** Four surfaces consume the packet — two HTTP endpoints, the agent protocol, and the CLI. When something was attached per-surface instead, one of them silently missed it and a person and an agent got different answers to the same question.
- **Weak evidence changes the narration, it does not block it.** The fit check fires only when *both* retrieval legs are weak, and its effect is a shorter answer that states its own scope. A blocking design would make a wrong threshold cost a withheld answer; this way it costs brevity. See the [engineering log](/engineering-log/) for the measurement behind the thresholds and their known limits.

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

### 2. Start — one line

```bash
task up
```

`task up` starts the containers (waiting for health), **applies DB migrations**, and pulls the embedding model automatically. No Task? Run those three yourself from `nexus/`:

```bash
docker compose up -d --wait                                  # containers + model auto-pull
docker compose exec -T nexus-app python -m scripts.migrate   # ← skip this and the source console / document management break
```

Starts PostgreSQL 16 + pgvector (5432), Ollama (11434), and the FastAPI app on **8000**. The OTel collector + Tempo are **opt-in** — add them only for trace aggregation: `docker compose --profile observability up -d`.

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
docker compose exec nexus-app nexus graph payment-service        # 1-hop
docker compose exec nexus-app nexus graph payment-service -h 2   # 2-hop
```

Or via the API: `GET /graph/{entity}` resolves by name or rid.

### Find design-vs-observation drift

```bash
docker compose exec nexus-app nexus otel-aggregate   # roll traces up into CALLS_OBSERVED
docker compose exec nexus-app nexus diff             # report doc_only / observed_only / conflict
```

The same report is available at `GET /diff`.

## Reference

- Source repo README: [github.com/LivingLikeKrillin/khala](https://github.com/LivingLikeKrillin/khala) (`README.md`)
- API contract, pipeline, MCP server, Slack bot, and UI integration docs live under that repo's `docs/` (`API_CONTRACT.md`, `PIPELINE_SPEC.md`, `MCP_SERVER.md`, `SLACK_BOT.md`, `UI_INTEGRATION.md`).
- MCP server exposes nine tools — `nexus_search`, `nexus_answer`, `nexus_graph`, `nexus_suggest`, `nexus_diff`, `nexus_status`, `nexus_supersede`, `archon_claim_value`, `archon_grade_authority` — via `python -m nexus.mcp`. Set `NEXUS_MCP_TOKEN`, or every call returns 401 (auth defaults to `enforced`).

:::note[Last verified]
Source repo README (site re-run verification pending).
:::
