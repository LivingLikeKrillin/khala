# Surface & usability audit — 2026-07-10

> A point-in-time record. Every claim below was checked against code or against a running
> system; `file:line` references are to the tree at commit `23c6af8` (master, 2026-07-10).
> Nothing here is an impression.

**Verdict: the engine is real; the product is not.** Roughly a quarter of Nexus's capabilities
are reachable from a browser. The rest require typing an incantation inside a container, an MCP
client, or — in three cases — reading the source and calling a Python function by hand.

---

## 1. Method

Seven parallel read-only investigations, one per surface (nexus CLI · nexus web+HTTP ·
install/first-run/deploy · adept+adept-web · arbiter/probe/observer · MCP/Slack/A2A ·
docs-vs-code), plus direct observation of the running stack and manual driving of the web UI
in a browser.

Each capability was scored on six axes:

| Axis | Question |
|---|---|
| Entry path | browser / CLI on host / CLI inside container / hand-edit a file / MCP-only / none |
| Prerequisites | how many env vars, tokens, external installs |
| Reversibility | can a mistake be undone from the surface that made it |
| Failure feedback | clear error / silence that looks like success / stack trace |
| Documentation | present and correct / present and stale / absent |
| Friction | distinct human acts required to reach the goal |

---

## 2. Nexus — where each capability lives

| Capability | Browser | HTTP API | CLI | Note |
|---|:--:|:--:|:--:|---|
| Search / grounded answer | ✅ | ✅ | ✅ | works well |
| Graph exploration | ✅ | ✅ | ✅ | chat has entity autocomplete, graph does not |
| Document list | ✅ | ✅ | — | read-only dead end (§4) |
| Single `.md` upload | ✅ | ✅ | — | multi-file drop silently keeps the first |
| Diff dashboard | 🚫 | ✅ | ✅ | built, then hidden **on purpose**: "Diff는 운영자 도구 — Reader 표면에서 기본 숨김" (`nexus/nexus/web/index.html:107`). There is no operator surface to move it to, so it went nowhere. |
| Folder ingest | ❌ | ✅ | ✅ | no UI affordance |
| **Notion ingest + reconcile** | ❌ | ❌ | ✅ | **no endpoint at all** — invisible to web *and* agents |
| Hide a document (`supersede`) | ❌ | ✅ | ✅ | no UI; no dry-run, no confirm, no inverse |
| **Delete a document** | ❌ | ❌ | ❌ | does not exist anywhere |
| Entropy signals | ❌ | ❌ | ✅ | undocumented; stack-traces without migration 001 |
| OTel aggregation | 🚫 | ✅ | ✅ | `otelAggregate()` exists in `nexus/nexus/web/js/api.js`, no view calls it |
| Archon claim lookup | ❌ | ✅ | ✅ | no UI |
| Mint a bearer token | ❌ | ❌ | ✅ | **the browser has no way to authenticate at all** |
| Last-ingest time | ❌ | ✅ | ✅ | `/status` returns it; `nexus/nexus/web/js/components/status-bar.js:38-51` discards it |
| Source management / user management | ❌ | ❌ | ❌ | does not exist |

🚫 = implemented but unreachable from that surface.

**Surface coverage: 4 of the 15 capabilities above are usable from a browser** — search, graph,
the document list, and single-file upload. That is the 27 % this document keeps referring to; the
denominator is this table.

**`/ingest` and `/otel/aggregate` are reachable by neither the web UI nor the MCP server.**
`ingest-notion`, `entropy-signals`, `claim-seed` and `auth gen-token` have no HTTP endpoint,
so they are unavailable to *both* humans and agents.

---

## 3. The other components

| Component | Verdict | Evidence |
|---|---|---|
| **Slack bot** | Dead | No entrypoint — absent from `[project.scripts]` (`nexus/pyproject.toml:60-61`) and from compose. `_call_nexus_api` sends no `Authorization` header (`nexus/nexus/slack/bot.py:86-96`) while auth defaults to `enforced` → every query 401s. |
| **Probe** | Not a tool | No CLI (`[project.scripts]` absent), no MCP server, and `probe/SKILL.md` is not installed under any `.claude/skills/`. Usage = paste six Python blocks and dispatch a critic subagent yourself. |
| **Arbiter** | Unrunnable by a human | All 12 tools are MCP-only; there is no CLI. The repo ships no `.mcp.json` (gitignored), so a fresh clone has Arbiter wired to nothing. Running its own approval gate on 2026-07-09 required hand-writing Python against `khala.arbiter.ledger`. |
| **Observer** | Documented install does not work | `pnpm add -D @khala/observer` — registry returns 404, and `dist/` is gitignored, so a clone can run nothing until `pnpm install && pnpm build`. Every skill and agent in the repo invokes the bare `observer` binary. |
| **Adept** | Documented loop is unrunnable | `save-questions` requires `--hash`, but no command prints the content hash (`adept/src/khala/adept/cli.py:92,113`). The only in-tool way to learn it is to pass a wrong hash and read the value out of the error (`adept/src/khala/adept/cli.py:133-135`). adept-web has `POST /api/artifacts` and a client function, but **no page calls it** — an empty web instance is a dead end. |
| **A2A** | Well built, undiscoverable | Fully mounted, token-gated, extensively tested. **Zero human-facing documentation.** |

---

## 4. Irreversibility

The sharpest axis. Destructive operations are designed inconsistently.

- `supersede` removes a document and all its chunks from every search
  (`nexus/nexus/supersede.py:32-35`). No dry-run, no confirmation, **no inverse** — `unsupersede`
  does not exist.
- `adept save-questions` replaces an artifact's question set, orphaning every prior attempt
  (`adept/src/khala/adept/questions.py:54`, `adept/src/khala/adept/schedule.py:76-79`). Silent.
- An uploaded document **cannot be removed from the browser.** No delete endpoint exists.
- By contrast `ingest-notion --reconcile`, which performs the same class of hide-data operation,
  ships `--dry-run`, a 50 % prune threshold, and `--force`.

The safety of a destructive action currently depends on which week it was written.

---

## 5. Silent failure

- A dead database produces a **raw traceback** from the CLI — `get_pool()` in `nexus/nexus/db.py`
  wraps `asyncpg.create_pool` in nothing — while the HTTP layer maps the same condition to a clean
  503. The CLI is strictly worse than the API for the most common failure.
- The service-health dots carry the `hidden` class (`nexus/nexus/web/index.html:57`), so a DB/Ollama
  outage is nearly invisible in the UI.
- A failing `/entities/suggest` silently hides the dropdown (`nexus/nexus/web/js/views/chat.js:174-176`) —
  indistinguishable from "no matches".
- **In production the web UI is a 401 wall.** The frictionless local experience exists only because
  `docker-compose.override.yml` injects `NEXUS_DEV_TOKEN`, which the client fetches from
  `/auth/dev-token` (`nexus/nexus/web/js/api.js:14-29`). There is no token input anywhere in the UI.

---

## 6. Documentation

Fidelity is unusually high — dozens of concrete claims (ports, task names, CLI verbs, flags, MCP
tool names, API routes, the embedding model, the classification model) check out. The failures are
concentrated and lethal:

| Claim | Reality |
|---|---|
| README docs link `khala-docs.pages.dev` | does not resolve (`curl` → 000); the site is on GitHub Pages |
| Archon page: `git checkout spec/domain-invariant-governance` | branch does not exist; the code is on `master` |
| Observer: `pnpm add -D @khala/observer` | package is not published (404) |
| MCP guide | omits `NEXUS_MCP_TOKEN`; every tool call 401s. Documents 6 tools; there are 9 |
| `config.yaml: llm.model` | nothing reads that section, and the value hit EOL 2026-06-15 |
| "Getting Started" | contained **zero commands** |
| Quickstart order | invites a question before `nexus ingest`, so the first experience is "not found" |
| `nexus/README` CLI list | 6 of 13 commands |

There is not a single screenshot or GIF anywhere. The first build compiles mecab-ko from source —
budget 10–20 minutes — and no quickstart says so.

*(All of the above were corrected in PR #111. They are recorded here because the pattern matters
more than the individual defects.)*

---

## 7. What is good, and must not be thrown away

Measured, not assumed. A live query against the 13-document corpus returned a grounded answer with
ten cited chunks, relevance bars, trust badges, and — where the corpus was silent — an explicit
"this is not in the provided documents" notice rather than a guess.

The retrieval pipeline, the graph, PII quarantine, classification, the supersession machinery, the
Notion reconciliation and its safety rails, the governance ledger, and the A2A surface are real,
tested assets. Exactly one external install (Docker) is required for the core journey.

Scrapping the project would discard the hard half in order to rebuild the easy half.

---

## 8. Root cause

Not a shortage of features. **Every surface was designed for an agent.** CLI and MCP are convenient
for a program to call and hostile for a person to use. `nexus/CLAUDE.md` states *System decides, LLM
narrates*; there is no corresponding *human operates*. So the acts that belong to a person —
connecting a source, checking freshness, undoing a mistake, signing in — were never given a home.

The structural expression of this is that **the HTTP API is the common substrate and it has holes.**
`ingest-notion` has no endpoint, so neither the browser nor an MCP agent can reach it. A capability
that skips the API is lost to *both* audiences, not just to humans.

---

## 9. Remediation order

**Principle: capability → HTTP endpoint → (web view · MCP tool · CLI).** The endpoint is canonical;
the three surfaces are thin clients over it. Build once, serve both audiences.

0. **Stop lying.** Fix false instructions before anything else. *(done — PR #111)*
1. **Turn the Nexus web app into an operating console.** Source (Notion root) registration and sync
   with a deletion preview; a Documents view with origin, a link back to the source, search, hide and
   undo; last-sync and freshness; visible progress.
2. **Make reversibility universal.** Preview + confirm + inverse for every destructive action,
   starting with `unsupersede`.
3. **Authenticate from the browser.** Production is a 401 wall today.
4. **Make failure visible.** Expose the health dots; replace CLI tracebacks with messages.
5. **Fix first-run.** Ingest inside the quickstart; `task up` runs migrations; publish a prebuilt image.
6. **Wire the rest.** Register Arbiter in the repo and give it a CLI. Fix Observer's install path.
   Give Probe a CLI or stop calling it a tool. Decide whether Slack lives or dies.

### Measure

**Surface coverage = capabilities reachable from a browser ÷ total capabilities** (§2 is the
current census: 4 / 15). Raising that ratio — without stripping the agent path — is the definition
of the work.
