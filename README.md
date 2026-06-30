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

---

Khala answers the **two failure modes of the AI era — the machine lies, and the
human stops judging** — with deterministic grounding, not advice. Khala is not a
tool you run; it is the link the tools share. The ecosystem is **Khala**; one of
its components is **Nexus**.

- **The machine lies** — stale or wrong, asserted with confidence. Defended by
  grounding answers in verifiable sources, never asserting soft answers.
- **The human stops judging** — AI output rubber-stamped without reading.
  Defended by making accountable review a gate before code is written.

## The three debts of the AI era

As AI becomes the producer, three debts accumulate (Martin Fowler, "the three debts of the
AI era", 2026-04-02). Khala is the window where you pay them down cheaply — so you stay in
command of your own system:

- **Technical debt** — artifacts pile up faster than they're maintained → **Probe** (formerly mutqa) + **Observer** (formerly Probe).
- **Intent debt** — *why* a thing was built is lost → **Arbiter** (formerly specledger).
- **Cognitive debt** — *nobody understands the system* → the open leg Khala is built to close.

The reframe is recorded in [ADR-0002](adr/ADR-0002-reframe-system-command-debt.md).

## The tools

| Tool | One-liner | Directory |
|---|---|---|
| **Nexus** | Enterprise RAG + GraphRAG — grounds answers in your docs and OTel telemetry. | [`./nexus`](./nexus) |
| **Observer** | Platform-aware PR analyzer — PR scope, API spec lint/diff, review checklists; consumes Nexus. | [`./probe`](./probe) |
| **Arbiter** | ADR/SDD governance MCP — reviewable, traceable decision records; publishes to Nexus. | [`./arbiter`](./arbiter) |
| **Probe** | Mutation-driven test-quality harness — catches what advisory review misses. | [`./mutqa`](./mutqa) |
| **docs** | Astro Starlight bilingual ecosystem documentation site. | [`./docs`](./docs) |

## Quickstart (Nexus · ~5분)

전제: Docker + Docker Compose. ([go-task](https://taskfile.dev) 있으면 `task`, 없으면 우측 명령 그대로)

```bash
# (선택) LLM 답변 생성용 — 없어도 근거 검색은 동작
export ANTHROPIC_API_KEY=sk-ant-...

task up        # 또는: cd nexus && docker compose up -d
task models    # 최초 1회 임베딩 모델 — 또는: docker compose exec nexus-ollama ollama pull nomic-embed-text
```

→ 브라우저에서 **http://localhost:8000** 열기 → **채팅**에 질문하면 *근거와 함께* 답합니다.

- **문서 넣기:** 좌측 **업로드**, 또는 `docker compose exec nexus-app nexus ingest ./docs`
- **업데이트:** `git pull` 후 `task update` — 이미지 재빌드·재기동 + DB 마이그레이션 적용([nexus/migrations](nexus/migrations/README.md))
- **정지:** `task down` (또는 `docker compose down`)

## Documentation

Full ecosystem reference, philosophy, and per-tool guides live at the docs site:
**https://khala-docs.pages.dev** (source in [`./docs`](./docs)).

## Conventions & license

- Contribution flow, naming, versioning, and terminology rules: [CONVENTIONS.md](./CONVENTIONS.md).
- Licensed under the [MIT License](./LICENSE).
