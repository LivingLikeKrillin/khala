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
  <img src="assets/same-information.svg" alt="Four kinds of information — documented knowledge, design decisions, operational facts, comprehension — flow into one governed substrate (approved, current, cited), which a human and an agent read through two doors: the same view." width="660" />
</p>

| Information | How it stays *the same* for everyone | Tool |
|---|---|---|
| **What the org knows** — docs, specs, know-how | One warehouse, two doors: humans (web) and agents (MCP/A2A) read the same governed corpus — same approvals, same current version, same citations. | [Nexus](./nexus) |
| **Why it was built** — design decisions | A flight recorder for decisions: the choices coding agents make by the hundred are recorded at zero marginal cost, and approval stays a named human's accountable act. | [Arbiter](./arbiter) |
| **What the system is doing** — traces, metrics, logs | Judgment context, not another dashboard: telemetry joined with approved knowledge (specs, runbooks, decisions) into evidence for review and troubleshooting. | [Observer](./observer) over Nexus + OTel |
| **Who still understands it** — comprehension | A cognitive-debt ledger: the warehouse is the denominator (what must be known), vouches are the numerator (what a named human can still explain) — the gap becomes a number you can repay. | [Adept](./adept) |

The first row is where a team starts — everyday value. The last row is why it matters
more every year: as agent output grows, an org that doesn't measure comprehension
doesn't even know what it no longer knows.

## The three debts of the AI era

As AI becomes the producer, three debts accumulate (Martin Fowler, "the three debts of the
AI era", 2026-04-02). Khala is the window where you pay them down cheaply — so you stay in
command of your own system:

- **Technical debt** — artifacts pile up faster than they're maintained → **Probe** + **Observer**.
- **Intent debt** — *why* a thing was built is lost → **Arbiter**.
- **Cognitive debt** — *nobody understands the system* → **Adept** measures it as vouch
  coverage against the shared warehouse, and drives its repayment.

The reframe is recorded in [ADR-0002](adr/ADR-0002-reframe-system-command-debt.md).

## The tools

| Tool | One-liner | Directory |
|---|---|---|
| **Nexus** | Hybrid retrieval over your docs and OTel telemetry — every answer carries citations that are verified in code. | [`./nexus`](./nexus) |
| **Archon** | Authority window over domain invariants — reads values from code constants at query time. Ships inside Nexus. | [`./nexus/nexus/claims`](./nexus/nexus/claims) |
| **Observer** | Platform-aware PR analyzer — PR scope, API spec lint/diff, review checklists; consumes Nexus. | [`./observer`](./observer) |
| **Arbiter** | ADR/SDD governance MCP — reviewable, traceable decision records; publishes to Nexus. | [`./arbiter`](./arbiter) |
| **Probe** | Mutation-driven test-quality harness — catches what advisory review misses. | [`./probe`](./probe) |
| **Adept** | Cognitive-debt meter — graded, grounded comprehension vouches; coverage + orphan hotlist. | [`./adept`](./adept) |
| **Adept web** | Team surface for the same meter — browser UI + server-backed (file or Postgres). | [`./adept-web`](./adept-web) |
| **docs** | Astro Starlight bilingual ecosystem documentation site. | [`./docs`](./docs) |

## 빠른 시작 가이드 (Nexus Quickstart)

실행 환경 요구사항: Docker 및 Docker Compose ([go-task](https://taskfile.dev) 설치 권장, 미설치 시 Compose 명령어 직접 실행).

```bash
# (선택 사항) LLM 답변 생성용 API 키 설정 — 미설정 시에도 근거 패킷 검색 파이프라인은 정상 동작
export ANTHROPIC_API_KEY=sk-ant-...

task up        # 또는: cd nexus && docker compose up -d
task models    # 최초 1회 임베딩 모델 로드 (docker compose exec nexus-ollama ollama pull nomic-embed-text)
```

> **개발 환경 무키(Keyless) 실행 옵션:** 외부 유료 API 키 없이도 답변 생성이 가능합니다. `NEXUS_LLM_PROVIDER=claude-code` 환경변수를 지정하고 `task llm-bridge`를 실행하면 호스트의 Claude Code 프로세스를 LLM 백엔드로 연동합니다.

브라우저에서 **http://localhost:8000** 접속 후 웹 인터페이스에서 질의를 수행하면 검증된 근거 및 출처 링크와 함께 답변이 생성됩니다.

- **문서 수집(Ingestion):** 웹 UI 내 업로드 기능 사용 또는 CLI 명령 실행: `docker compose exec nexus-app nexus ingest ./docs`
- **서비스 갱신 및 마이그레이션:** 소스 동기화 후 `task update` 실행 — 컨테이너 재빌드 및 DB 스키마 마이그레이션 적용 ([nexus/migrations](nexus/migrations/README.md))
- **서비스 중지:** `task down` (또는 `docker compose down`)

## How this repository is kept honest

A system whose promise is calibration has to hold itself to the same standard, so the
guards below are not process decoration — each one exists because something went wrong
first, and each is enforced on every push rather than remembered.

| Guard | What it refuses | Why it exists |
|---|---|---|
| **Doc-to-code anchors** — [`doc-anchors.yml`](./doc-anchors.yml) | A document whose anchored source paths no longer exist | "Is this page stale?" was being judged by counting commits by hand. Anchors turn it into one join. |
| **Disposable-database marker** | A test run against a database that has not declared itself scratch | The suite truncates tables. Pointed at the development database once, it took the corpus with it. |
| **Fingerprint scanner** | A push carrying identifying details — files, commit messages, and PR bodies alike | Details scrubbed before the repo went public came back through ordinary work a month later. |
| **Declared index generations** | Ingestion whose resolved embedding generation differs from the corpus's declared one | A documented command, run from the host, wrote vectors into a column no query reads. Nothing failed. |
| **Pre-registered verdict rules** | An evaluation harness edited after seeing the score it produced | Evaluation labels are signed, and the rule that decides the verdict is written down before the run. |
| **Declared evaluation corpus** | A label run where nobody said which corpus to ask, or where no label can reach the one being asked | A harness defaulting quietly to one tenant measured a corpus the labels were not written against. The same mistake happened three times; twice it was recorded only in a comment. |

2,988 test functions and 17 CI jobs, including a job that runs the database-backed
suite against a real Postgres with migrations applied — added after the discovery that
those tests had never executed at all. Governance artifacts (10 ADRs, 54 SPECs) are
stamped and checked for integrity in CI. Those four numbers are verified on every push
by `scripts/check_readme_counts.py`; they drifted once, and a hand-mirrored count in
this repository has never stayed true on its own.

**[→ Engineering log](https://livinglikekrillin.github.io/khala/engineering-log/)** — a dated
record of what was wrong, how each defect surfaced, and what changed. It is the most useful
page here for judging the project, because it is the one that reports what was wrong.

Open items are counted rather than described, in [OPEN.md](./OPEN.md), so that it is
possible to tell whether they are going up or down.

## Documentation

Full ecosystem reference, philosophy, and per-tool guides live at the docs site:
**https://livinglikekrillin.github.io/khala/** (source in [`./docs`](./docs)).

## Conventions & license
 
- Contribution flow, naming, versioning, and terminology rules: [CONVENTIONS.md](./CONVENTIONS.md).
- Standard technical glossary: [docs/glossary.md](docs/glossary.md).
- Terminology governance & retired terms record: [GLOSSARY.md](./GLOSSARY.md) (enforced by `scripts/check_terms.py`).
- Licensed under the [MIT License](./LICENSE).
