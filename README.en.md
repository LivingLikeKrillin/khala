<p align="center">
  <img src="assets/logo.svg" alt="Khala" width="120" />
</p>

<h1 align="center">Khala</h1>

<p align="center">
  <strong>An alliance of tools that calibrates the AI era.</strong>
</p>

<p align="center">
  <em>AI builds it. You understand it.</em>
</p>

<p align="center">
  <a href="README.md"><strong>한국어 정본 문서 (Korean)</strong></a>
</p>

---

Khala answers the **two failure modes of the AI era — the machine lies, and the
human stops judging** — with deterministic grounding, not advice. Khala is not a
tool you run; it is the link the tools share. The ecosystem is **Khala**; one of
its components is **Nexus**.

- **The machine lies** — stale or wrong, asserted with confidence. Defended by
  grounding answers in verifiable sources — and by mechanical checks, not trust:
  every citation is verified against the retrieved evidence, answer numbers must
  appear in that evidence, and answers built on stale sources are flagged.
- **The human stops judging** — AI output rubber-stamped without reading.
  Defended by making accountable review a gate before code is written.

## One substrate, four kinds of information

Khala exists so that everyone who builds and runs the service — humans *and* agents —
thinks from the **same information**. Documents alone don't cover that. Four kinds of
information drift apart in an AI-era org, and each one is a Khala surface:

<p align="center">
  <img src="assets/same-information.svg" alt="Four kinds of information — documented knowledge, design decisions, operational facts, comprehension — flow into one governed substrate (approved, current, cited), which a human and an agent read through dual access interfaces: the same view." width="660" />
</p>

| Information | How it stays *the same* for everyone | Tool |
|---|---|---|
| **What the org knows** — docs, specs, know-how | Single governed substrate, dual access interfaces: humans (web) and agents (MCP/A2A) read the same governed corpus — same approvals, same current version, same citations. | [Nexus](./nexus) |
| **Why it was built** — design decisions | Architecture decision recorder: choices coding agents make by the hundred are recorded at zero marginal cost, and approval stays a named human's accountable act. | [Arbiter](./arbiter) |
| **What the system is doing** — traces, metrics, logs | Judgment context, not another dashboard: telemetry joined with approved knowledge (specs, runbooks, decisions) into evidence for review and troubleshooting. | [Observer](./observer) over Nexus + OTel |
| **Who still understands it** — comprehension | Cognitive-debt ledger: total deployment artifacts are the denominator (what must be known), vouches are the numerator (what a named human can still explain) — the gap becomes a number you can repay. | [Adept](./adept) |

The first row is where a team starts — everyday value. The last row is why it matters
more every year: as agent output grows, an org that doesn't measure comprehension
doesn't even know what it no longer knows.

## The three debts of the AI era

As AI becomes the producer, three debts accumulate:

- **Technical debt** — artifacts pile up faster than they are maintained → **Probe** + **Observer**.
- **Intent debt** — *why* a decision was made is lost → **Arbiter**.
- **Cognitive debt** — *nobody fully understands the system* → **Adept** measures it as vouch
  coverage against the shared substrate, and drives its repayment.

The reframe is recorded in [ADR-0002](adr/ADR-0002-reframe-system-command-debt.md).

## The tools

| Tool | One-liner | Directory |
|---|---|---|
| **Nexus** | Hybrid retrieval over your docs and OTel telemetry — every answer carries citations that are verified in code. | [`./nexus`](./nexus) |
| **Archon** | Authority window over domain invariants — reads values from code constants at query time. Ships inside Nexus. | [`./nexus/nexus/claims`](./nexus/nexus/claims) |
| **Observer** | Platform-aware PR analyzer — PR scope, API spec lint/diff, review checklists; consumes Nexus. | [`./observer`](./observer) |
| **Arbiter** | ADR/SDD governance MCP — intercepts Write/Edit/MultiEdit when the PreToolUse hook is registered (Bash shell execution not gated); publishes approved specs to Nexus. | [`./arbiter`](./arbiter) |
| **Probe** | Mutation-driven test-quality harness — catches what advisory review misses. | [`./probe`](./probe) |
| **Adept** | Cognitive-debt meter — graded, grounded comprehension vouches; coverage + orphan hotlist. | [`./adept`](./adept) |
| **Adept web** | Team surface for the same meter — browser UI + server-backed (file or Postgres). | [`./adept-web`](./adept-web) |
| **docs** | Astro Starlight ecosystem documentation site. | [`./docs`](./docs) |

## Quickstart (Nexus Local Stack)

Prerequisites: Docker and Docker Compose ([go-task](https://taskfile.dev) recommended, or execute docker compose commands directly).

```bash
# (Optional) Anthropic API key for LLM answer synthesis (hybrid retrieval works without it)
export ANTHROPIC_API_KEY=sk-ant-...

task up        # Or: cd nexus && docker compose up -d
task models    # Pull embedding model (docker compose exec nexus-ollama ollama pull nomic-embed-text)
```

> **Keyless dev mode:** You can run LLM answers without paid API keys. Set `NEXUS_LLM_PROVIDER=claude-code` and run `task llm-bridge` to route requests to the host Claude Code process.

Open **http://localhost:8000** in your browser to query documentation with cited evidence.

- **Ingest docs:** Use the Web UI upload feature or CLI: `docker compose exec nexus-app nexus ingest ./docs`
- **Update & migrations:** Run `task update` after `git pull` to apply database schema migrations ([nexus/migrations](nexus/migrations/README.md)).
- **Stop services:** `task down` (or `docker compose down`)

## How this repository is kept honest

A system whose promise is calibration must hold itself to the same standard. The guards below are enforced on every push and pull request:

| Guard | When enforced | What it refuses | Why it exists |
|---|---|---|---|
| **Doc-to-code anchors** — [`doc-anchors.yml`](./doc-anchors.yml) | Push · PR | A document whose anchored source paths no longer exist | Prevents documentation drift deterministically by joining docs with code symbols. |
| **Disposable-database marker** | Push · PR | A test run against a database that has not declared itself scratch | Prevents catastrophic data loss in development/production databases. |
| **Fingerprint scanner** | Push (tracked files)<br/>PR (messages, title, body) | Identifying details (partner org names, real emails, SSO tenant hosts, Notion page IDs) | Prevents identifying information leaks across files and PR metadata. |
| **Declared index generations** | Push · PR | Ingestion whose resolved embedding generation differs from the corpus's declared one | Prevents silent index corruption across mismatched embedding models. |
| **Pre-registered verdict rules** | Push · PR | An evaluation harness edited after seeing the score it produced | Enforces objective evaluation rules before benchmark execution. |
| **Declared evaluation corpus** | Push · PR | A label run where nobody said which corpus to ask, or where no label can reach the one being asked | Prevents benchmark evaluation against invalid tenants or corpora. |

Across the repository, 3,295 test functions are declared and 17 CI jobs run in CI, including real Postgres integration with schema migrations. Among governance artifacts (10 ADRs, 54 SPECs), 61 approved or accepted artifacts are stamped and cryptographically verified for integrity in CI via `scripts/ledger_integrity.py`.

- **[→ Engineering log](https://livinglikekrillin.github.io/khala/engineering-log/)** — A dated record of what went wrong, how defects were discovered, and what was remediated.
- Open items are tracked deterministically in [OPEN.md](./OPEN.md).

## Documentation

Full ecosystem reference, philosophy, and per-tool guides are available at:
**https://livinglikekrillin.github.io/khala/** (source in [`./docs`](./docs)).

## Conventions & License

- Contribution flow, naming, versioning, and terminology rules: [CONVENTIONS.md](./CONVENTIONS.md).
- Standard technical glossary: [docs/glossary.md](docs/glossary.md).
- Terminology governance & retired terms: [GLOSSARY.md](./GLOSSARY.md).
- Licensed under the [MIT License](./LICENSE).
