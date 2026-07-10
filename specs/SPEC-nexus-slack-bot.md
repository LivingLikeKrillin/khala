---
id: SPEC-nexus-slack-bot
type: spec
title: The Slack bot, revived — the lowest-friction on-ramp for a team that lives
  in Slack
status: approved
date: 2026-07-10
linked_adrs:
- ADR-0004
tags:
- nexus
- slack
- surface
- adoption
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-10T15:04:16Z'
content_hash: sha256:292266aaa9c87856c1e18c1a694ea3a584c8602e9e369f23ddc6a2424a60e2cb
---

## 1. Goal

Make the Slack bot actually run, so a teammate can ask Nexus a question without leaving Slack.

The adoption argument is the whole point. Getting a team to use Nexus by sending them to a new
URL and a new UI is friction; letting them `@nexus <question>` in a channel they already have open
all day is not. For a team that lives in Slack, the bot is not a nice-to-have side surface — it is
the *cheapest* on-ramp, the one that meets people where they already are.

## 2. Non-goals

- **Per-person Slack identity in Nexus.** The bot authenticates as one service principal (§4.2).
  Mapping each Slack user to a Nexus principal is a larger auth design (Slack `users.info`,
  unmapped-user handling) and buys little while every surface is read-only. Deferred, not designed.
- **Writes from Slack.** The bot asks questions. It does not ingest, hide, or supersede. Its
  principal is read-only, and there is no command that changes the corpus.
- **A public HTTP endpoint.** The bot runs in Socket Mode (`app.py` already), so it needs no
  tunnel, no domain, no inbound port — two Slack tokens and an outbound connection. This is why it
  can ship before the Cloudflare tunnel work does.
- **Rebuilding the handlers or the answer formatter.** `bot.py`, `app.py`, and `format_answer` are
  written and stay. This SPEC wires them to run and authenticate, and it *does* add the error
  mapping that turns out not to exist (§4.3, I-004) — that is a small addition, not a rewrite.
- **Surfacing Archon grounding distinctly (I-001).** ADR-0004 says a live-code-constant answer must
  show as a distinct fact-check. That is a property of `/search/answer`'s *response*, owed on every
  surface (web, MCP, A2A) equally — not something the Slack bot invents or omits on its own. The bot
  renders what the endpoint returns; making the endpoint mark Archon grounding is a separate,
  cross-surface concern, and giving Slack a bespoke version would be the fragmentation to avoid. Out
  of scope here, tracked against the answer endpoint.

## 3. What exists

Three files under `nexus/slack/`, none reachable:

- `app.py` — Socket Mode entry point (`python -m nexus.slack.app`), registers `app_mention` and DM
  handlers, needs `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN`.
- `bot.py` — `handle_mention` / `handle_dm` strip the mention, call Nexus `/search/answer`, format
  the reply into a thread.
- `formatter.py` — builds Slack Block Kit blocks (answer, evidence, sources).

Two defects make it dead, exactly as the audit found:

1. **No entry point anyone can find.** The `slack` dependency group exists in `pyproject.toml`,
   but there is no `[project.scripts]` console script and no compose service. `python -m
   nexus.slack.app` works if you know to type it; nothing documents or runs it.
2. **No auth header.** `_call_nexus_api` POSTs to `/search/answer` with no `Authorization` header
   (`bot.py`). Auth defaults to `enforced`, so every question the bot asks returns `401`. The same
   class of bug the Notion and Access work kept surfacing: a client that forgets it must
   authenticate.

There are zero tests for any of it.

## 4. Design

### 4.1 An entry point that exists

A `[project.scripts]` console script `nexus-slack = "nexus.slack.app:main"`, and a compose service
(opt-in, like the observability profile) so a team can run the bot with `docker compose --profile
slack up -d`. The service passes `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, and the bot's Nexus token
(§4.2) from the environment, the same way `NOTION_TOKEN` reaches the app. The runbook gains the
five-minute "create a Slack app, enable Socket Mode, set two tokens" section.

Socket Mode is load-bearing here: no inbound port means the bot ships independently of the tunnel
and Access work. A team can have the bot before it has a domain.

### 4.2 One service principal, read-only

The bot authenticates as a single Nexus principal via a service token, exactly as the MCP server
does (`NEXUS_MCP_TOKEN` → one (tenant, clearance) ceiling). `_call_nexus_api` sends
`Authorization: Bearer <token>` on every call. The token is read from the environment
(`NEXUS_SLACK_TOKEN`), never logged, never in a Slack message.

**Read-only is enforced server-side, not merely assumed from the token (I-003).** Nexus's write
paths already gate on `manage_documents` / `manage_sources` capability
(`documents/api.py`, `sources/api.py`), default-deny. A principal with zero capabilities is
*refused* by those endpoints with a 403 — the ceiling is not a convention the bot politely honours,
it is what the server enforces on every write route. The bot also never calls a write route; but
even if a bug did, the capability check stands. This SPEC pins that with a test: the bot's
principal hitting `/documents/{rid}/hide` gets 403.

**The clearance a workspace member inherits is a real decision, not a hand-wave (I-002).** A single
service principal means *every* Slack workspace member — including single-channel guests and
external shared-channel participants — reads whatever that principal can read. At **INTERNAL** that
is the whole INTERNAL corpus. So the clearance is `auth.slack.clearance`, an operator setting, and
the runbook states plainly: **the bot's clearance is the floor of trust you extend to everyone in
the Slack workspace, guests included.** A workspace with external guests should set it to `PUBLIC`;
an all-employee workspace may set `INTERNAL`. The default is `PUBLIC` — the safe floor — not
`INTERNAL`. Entry is decided upstream (workspace membership); what that entry can *read* is the
operator's explicit choice, the same shape as the Access unmapped-default (SPEC-nexus-access-jwt-auth
§4.4).

If the token is missing, the bot refuses to start with a clear message — it does not start
unauthenticated and 401 on every question, which is today's silent failure.

### 4.3 The bot says when it cannot answer

**Correction to §3's scope (I-004):** `format_error` exists, but it is *one generic message* —
`⚠️ 오류: {error_msg}`. The distinct 401/503/empty-corpus mapping this section needs does **not**
exist yet. So this SPEC builds it — a small function that maps an outcome to a message — rather
than claiming the formatter already does. This is exactly the kind of unverified "it's already
there" the gate is meant to catch before code, and it did.

`_call_nexus_api` classifies each outcome and the bot renders a distinct message:

| outcome | who it's for | message |
|---|---|---|
| `401` from Nexus | the operator (the bot's token is wrong, not the user's question) | "봇 인증 설정이 잘못되었습니다 — 운영자에게 알리세요." |
| `503` / unreachable | the user, honestly | "지금 답변할 수 없습니다. 잠시 후 다시 시도하세요." |
| empty grounding (0 evidence) | the user | "인덱싱된 문서에서 답을 찾지 못했습니다." |
| empty corpus (0 documents) | the user | "아직 인덱싱된 문서가 없습니다." |
| anything else (429, 500, timeout, malformed) | the user, with the operator logged | "답변 중 오류가 발생했습니다." — never a stack trace (I-007) |

**How the bot tells "no evidence" from "no corpus" (I-006):** the answer response carries
`evidence_snippets`; if it is empty the grounding was empty. Whether the *corpus* is empty is a
different fact, and the bot reads it from `/status`'s `documents_count` — the same field the web
chat uses for its empty-corpus hint. So: zero snippets **and** zero documents → "아직 인덱싱된
문서가 없습니다"; zero snippets but documents exist → "찾지 못했습니다". The bot does not infer one
from the other; it asks the two questions separately.

The mapping is a pure function (outcome → message key), unit-tested per row. The generic
`format_error` stays as the last-resort branch, not the whole error story.

## 5. Error handling

- Missing `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` → refuse to start (already the behaviour).
- Missing `NEXUS_SLACK_TOKEN` → refuse to start (new; the auth defect made this a runtime 401
  instead of a startup refusal).
- Nexus `401` → a Slack message telling the operator the bot's token is wrong, not the user's
  question. This is a configuration error surfaced to whoever can fix it.
- Nexus `503` / unreachable → "지금 답변할 수 없습니다", logged for the operator.
- The bot's token never appears in a log line or a Slack message. Same rule as every other
  credential in this codebase.

## 6. Testing

The handlers and the API client are unit-testable without a live Slack (`bot.py` takes the event
dict and a `say` callable) and without a live Nexus (the HTTP client is injectable / mockable).

- `_call_nexus_api` sends `Authorization: Bearer <token>` — the assertion that would have failed
  for as long as the bot has existed.
- `handle_mention` strips the `<@U…>` mention and passes the bare query.
- A Nexus `401` produces the operator-facing error message, not the user-facing one.
- A Nexus `503` produces "지금 답변할 수 없습니다".
- An empty grounding produces the "찾지 못했습니다" message; an empty corpus, the "아직 인덱싱된
  문서가 없습니다" message (the two are distinct — no evidence vs no documents).
- **Any other status** (429, 500, timeout, malformed body) produces the generic user message and a
  logged operator detail — never a stack trace (I-007).
- **Read-only is server-enforced (I-003):** the bot's principal (zero capabilities) calling
  `/documents/{rid}/hide` gets `403`. Asserted through the real auth path, not assumed from the
  token — this is the mechanism the ceiling rests on.
- The outcome→message mapping is a pure function, one assertion per row of the §4.3 table.
- The bot token appears in no formatted block and no log call, asserted against captured output on
  the error branches too (I-005) — the mapping is written so the token is never interpolated into a
  message, which is a property of the code, not of one captured path.
- `main()` refuses to start when `NEXUS_SLACK_TOKEN` is unset (exit non-zero, clear message).

Slack Bolt's own wiring (Socket Mode connection) is not unit-tested — that is the framework's job;
the go-live check in §7 exercises it against a real workspace.

## 7. Acceptance

The bot needs three tokens: `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` (from the Slack app,
Socket Mode), and `NEXUS_SLACK_TOKEN` — a Nexus bearer the operator mints with
`nexus auth gen-token`, registered as a principal at the `auth.slack.clearance` ceiling with zero
capabilities (I-008). Rotation is the same as any Nexus token: mint a new one, update the env,
restart the bot.

`docker compose --profile slack up -d` with those three set, and `@nexus <question>` in a channel
returns a grounded answer in-thread. A wrong bot token produces a message a human can act on, not a
401 loop. And the bot reads — the capability model refuses it a write even if asked.

The live-workspace check (create the Slack app, connect Socket Mode, ask a real question) is the
go-live gate, the same shape as the Access tunnel check: everything above is built and unit-tested
without a workspace; the one thing a real Slack app is needed for is the end-to-end confirmation.
