---
title: Getting Started
description: Pick your goal; it routes you to the right tool.
---

New here? Start from what you're trying to do — each goal points to the tool that calibrates it.

## Run Nexus in five minutes

Docker is the only thing you need installed. Everything else runs inside the compose stack.

```bash
git clone https://github.com/LivingLikeKrillin/khala.git
cd khala
cp nexus/.env.example nexus/.env     # then set ANTHROPIC_API_KEY for narrated answers
task up
```

No Task? `task up` is three commands — run them from `nexus/`:

```bash
cd nexus
docker compose up -d --wait                                  # containers + model auto-pull
docker compose exec -T nexus-app python -m scripts.migrate   # ← skip this and the source console / document management break
```

The **first** boot builds the image, which compiles mecab-ko from source — budget **10–20 minutes**. Later runs start in seconds. The embedding model (`nomic-embed-text`, ~274 MB) is pulled automatically on first boot.

Now **index something**. An empty corpus answers every question with "not found", so this step is not optional:

```bash
cd nexus
docker compose exec nexus-app nexus ingest ./docs   # index the shipped design docs
```

Open `http://localhost:8000/` and ask a question. Answers cite the chunks they came from; if the corpus doesn't contain the answer, Nexus says so instead of guessing.

Without `ANTHROPIC_API_KEY` you still get the retrieved evidence — just not a narrated answer.

To stop: `task down`. To update after `git pull`: `task update` (rebuilds **and** runs DB migrations).

## Pick your goal
| I want to… | → Tool |
|---|---|
| get grounded answers about my codebase/domain | [Nexus](/tools/nexus/) / [Archon](/tools/archon/) |
| ground my PRs & troubleshooting in org context | [Observer](/tools/observer/) |
| stop rubber-stamping specs | [Arbiter](/tools/arbiter/) |
| make AI-generated tests actually verify behavior | [Probe](/tools/probe/) |
| know whether a human can still vouch for what the AI wrote | [Adept](/tools/adept/) |

## 5-minute tour
[What is Khala?](/) → [Philosophy](/philosophy/) → [Ecosystem](/ecosystem/)

## Prerequisites
- Common: git, a recent runtime.
- Nexus: Docker (Postgres etc. run inside the compose stack — no separate install). Observer: Node ≥20. Arbiter / Probe / Adept: Python (Probe needs `cosmic-ray`).
