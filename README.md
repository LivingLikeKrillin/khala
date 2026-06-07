<p align="center">
  <img src="assets/logo.svg" alt="Khala" width="120" />
</p>

<h1 align="center">Khala</h1>

<p align="center">
  <strong>An alliance of tools that calibrates the AI era.</strong>
</p>

---

Khala answers the **two failure modes of the AI era — the machine lies, and the
human stops judging** — with deterministic grounding, not advice. Khala is not a
tool you run; it is the link the tools share. The ecosystem is **Khala**; one of
its components is **Nexus**.

- **The machine lies** — stale or wrong, asserted with confidence. Defended by
  grounding answers in verifiable sources, never asserting soft answers.
- **The human stops judging** — AI output rubber-stamped without reading.
  Defended by making accountable review a gate before code is written.

## The tools

| Tool | One-liner | Directory |
|---|---|---|
| **Nexus** | Enterprise RAG + GraphRAG — grounds answers in your docs and OTel telemetry. | [`./nexus`](./nexus) |
| **Probe** | Platform-aware PR analyzer — PR scope, API spec lint/diff, review checklists; consumes Nexus. | [`./probe`](./probe) |
| **specledger** | ADR/SDD governance MCP — reviewable, traceable decision records; publishes to Nexus. | [`./specledger`](./specledger) |
| **mutqa** | Mutation-driven test-quality harness — catches what advisory review misses. | [`./mutqa`](./mutqa) |
| **docs** | Astro Starlight bilingual ecosystem documentation site. | [`./docs`](./docs) |

## Documentation

Full ecosystem reference, philosophy, and per-tool guides live at the docs site:
**https://khala-docs.pages.dev** (source in [`./docs`](./docs)).

## Conventions & license

- Contribution flow, naming, versioning, and terminology rules: [CONVENTIONS.md](./CONVENTIONS.md).
- Licensed under the [MIT License](./LICENSE).
