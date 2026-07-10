---
id: SPEC-nexus-notion-connection-health
type: spec
title: Notion connection health — is the token real, and can we actually reach that
  root?
status: approved
date: 2026-07-10
linked_adrs:
- ADR-0004
tags:
- nexus
- surface
- usability
- notion
- diagnostics
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-10T07:15:25Z'
content_hash: sha256:e23a537454929afc70cc9b538712c10cd9f2686efd122614785903346b2fb526
---

## 1. Goal

Answer, at the surface, three questions a person or an agent has to answer before a sync is
worth starting:

1. Is the configured Notion token real, and whose is it?
2. Can the integration actually reach each registered root?
3. If not, what do I do about it?

Today all three are answerable only by opening a shell in the container and calling Notion's
API by hand. That is not a surface; it is an archaeology dig.

## 2. Non-goals

- **Writing or rotating the token.** Nexus has no login of its own; behind a tunnel, whoever
  Cloudflare Access admits reaches the web UI. Making that UI a place where a credential can
  be *set* turns every Access misconfiguration into a credential compromise. Rotation stays a
  `.env` edit plus a restart, and the runbook says so.
- **Returning the token value.** No endpoint returns it, not even masked beyond a prefix.
- **Multiple Notion credentials per instance.** One instance, one Notion identity.
- **Repairing anything automatically.** We report. The human shares the page in Notion.
- **Blocking a sync.** Health is a diagnosis, not a gate. A user who wants to run a sync
  against a half-broken connection may.

## 3. What exists

`nexus/sources/api.py`:

```python
def _notion_configured() -> bool:
    return bool(os.getenv("NOTION_TOKEN"))
```

Presence, not validity. A revoked token, a typo'd token, a token from a different workspace —
all report `token_configured: true`, and the web shows no warning.

`roots_store.add_root` parses a page id out of whatever the user pasted and inserts it. It
never asks Notion whether that page exists or whether this integration was invited to it. The
endpoint answers `201 Created`.

So both failures are deferred to sync time, where they surface as
`finish_run(status="failed", reason=str(e)[:500])` — a `notion_client` exception string, in
English, after an unbounded walk.

**Two facts about Notion that shape the design:**

- Notion answers `404 object_not_found` for a page the integration was not invited to, *not*
  `403`. It is indistinguishable from a page that does not exist. Notion's own message says so:
  "Make sure the relevant pages and databases are shared with your integration." We must not
  claim to know which of the two it is. *(Observed, 2026-07-10, against the live API.)*
- A root may be a page **or** a database, and the two live at different endpoints.

## 4. Design

### 4.1 One capability: ask Notion, don't guess

`probe_connection(token, roots) -> ConnectionHealth` calls Notion:

- `GET /v1/users/me` → token validity, integration name, workspace name.
- per root: `GET /v1/pages/{id}`; **whenever that is not `200`, retry `GET /v1/databases/{id}`**
  before concluding anything. Not only on `404` — we have not established what a database id
  returns at the pages endpoint, and guessing `404` would misfile a real database as
  `invalid_id` on a `400` (I-006). The retry is cheap; the wrong verdict sends a user to
  re-share a page that was never unshared.

Nothing is cached in the DB. The answer is about *now*; a stored answer would be a lie the
moment someone revokes access in Notion.

**Snapshot semantics** (I-011): the root list is read from `notion_sources` once, at the start
of the call. `checked_at` is the time of that read. A root added or removed while probes are in
flight is simply absent from, or stale in, this response; the next call sees it. Health makes no
consistency promise beyond "these were the roots when I looked", and says so by returning
`checked_at`.

Roots are probed concurrently, at most 8 at a time (I-007), each with its own timeout.

### 4.2 The states of a token

| Notion says | We report | What the surface says |
|---|---|---|
| (no token set) | `not_configured` | "Notion 토큰이 설정되지 않았습니다." |
| `401` | `invalid` | "토큰이 거부되었습니다(401). 폐기되었거나 잘못된 값입니다." |
| `200` | `ok` + integration, workspace | "실증 테스트 · Joo Young Jung의 Notion" |
| anything else, or no answer | `unknown` | "Notion 에 연결할 수 없어 확인하지 못했습니다." |

`invalid` is a *distinct state from unset*, and that distinction is the whole point: today they
look identical from every surface. `unknown` is a distinct state from both, and is what we say
when we do not know (I-007).

### 4.3 The states of a root

| Notion says | We report | What the surface says |
|---|---|---|
| `200` (page or database) | `reachable` + title | the page title, so the user knows they registered the right page |
| `404` **or `403`** on both endpoints | `unreachable` | "이 페이지를 볼 수 없습니다 — 존재하지 않거나, integration 이 초대되지 않았습니다." |
| `400` on both endpoints | `invalid_id` | "페이지 id 형식이 잘못되었습니다." |
| `401` | *(not probed)* | the token is `invalid`; probing roots is pointless |
| `429`, `5xx`, timeout, transport error | `unknown` | "확인하지 못했습니다." |

`403` is in the `unreachable` row on purpose. Notion answers `404` for an uninvited page today
— one observation, 2026-07-10, against the live API — and the honest reading of a single
observation is that it may change. `403` means the same thing to the user and carries the same
remedy, so both map to the same state and the same sentence. Nothing downstream depends on
which one Notion chose (I-005).

We report the root's **title** when reachable. A `root_id` is a hex string; a title is what the
user recognises. The document lifecycle SPEC (`SPEC-nexus-document-lifecycle` §4.5) applies the
same rule to `superseded_by`, for the same reason (I-009).

**Every status that is not an explicit row above maps to `unknown`, never to `unreachable`**
(I-005). Reporting Notion's outage as "your page is gone" would be a lie, and a user who trusts
it will go re-share a page that was never unshared.

### 4.4 Registration reports; it does not refuse

`POST /sources/notion/roots` probes the page and **still writes the row**, returning what it
learned:

```json
{ "root_id": "fc054c8f…", "state": "unreachable", "title": null,
  "remedy": "Notion 에서 이 페이지의 연결(Connections)에 integration 을 추가하세요." }
```

The first draft rejected an unreachable root with `422`. That was wrong (I-004, I-011).
**Registering a root before sharing it in Notion is a legitimate order of operations** — you
paste the URL, then go add the connection — and Notion cannot tell us apart a page that is not
shared *yet* from one that does not exist. Refusing would break a working flow to defend against
a typo we cannot actually detect.

So registration keeps its `201` and its old semantics. What changes is that it now *tells you*,
at that moment, instead of leaving you to discover it after an unbounded walk. That is the whole
goal of this SPEC, applied to the write path rather than bolted onto it.

### 4.5 Endpoints, then clients

`GET /sources/notion/health` requires the **`manage_sources`** capability.

The first draft left it ungated on the grounds that it "returns no secret." That reasoning was
inconsistent with this SPEC's own threat model (I-001, I-002): the response names the workspace,
the integration, and the title of every registered root. Behind a tunnel, whoever Access admits
would read the shape of the org's document tree. The token is not the only thing worth guarding.
Sources management already sits behind `manage_sources`; health belongs there too.

```json
{ "token": { "state": "ok", "integration": "실증 테스트",
             "workspace": "Joo Young Jung의 Notion", "prefix": "ntn_" },
  "roots": [ { "root_id": "fc054c8f…", "state": "reachable",
               "title": "System Architecture" } ],
  "checked_at": "2026-07-10T…Z" }
```

`prefix` is the first four characters — enough to tell `ntn_` from `secret_` from paste-garbage,
not enough to be a credential.

**The gate applies to every client, not just the web** (I-008). MCP and CLI are not a side door:
the MCP server is an HTTP client that forwards `NEXUS_MCP_TOKEN`, and the API resolves the
principal. So an explicitly configured MCP principal without `manage_sources` gets `403` from
`nexus_sources_health()` — exactly as it already does from `nexus_sources_add`. The dev-token
principal has `manage_sources` by default (`auth.local_dev_capabilities`), so the local web and
the dev-token MCP path keep working. Cloudflare Access guards the network edge; capabilities
guard the endpoint. Neither substitutes for the other.

**The response body carries no exception text** (I-003). `unknown` is a state, not a message
slot: a probe that fails carries its HTTP status or a fixed reason code, never the stringified
exception. Underlying error text stays in the process — that is the same invariant as §4.6, and
it is what keeps a transport error from smuggling a URL, a header, or a credential into a
response.

- **Web**: the 소스 view's existing `src-token-warn` grows into a connection panel — token state,
  integration · workspace, and per-root state beside each row, with the remedy on unreachable rows.
- **MCP**: `nexus_sources_health()`.
- **CLI**: `nexus sources health`.

Same endpoint, three clients. An agent about to call `nexus_sources_sync` can ask first and stop
wasting a walk.

**Scope of "roots".** Health probes the roots registered in `notion_sources` — the ones the
console manages. `nexus ingest-notion --roots "…"` takes page ids on the command line and does
not consult that table; health says nothing about those, and does not claim to (I-010,
ADR-0004).

### 4.6 The token never leaves the process (invariant)

Beyond "no endpoint returns it" (I-003):

- The token is read from the environment at call time. It is **never** written to the database,
  a cache, a file, or a log.
- `finish_run(reason=…)` and every other place that records an exception string **redacts** any
  occurrence of the token value before persisting.

  Today's `notion_client` does not leak it: with a bogus token, `str(e)` and `repr(e)` on an
  `APIResponseError` are `"API token is invalid."` and contain no credential *(observed
  2026-07-10)*. So this is a guard against regression, not a fix for a live leak — a version
  that attaches request headers to the exception would otherwise write the credential into
  `notion_sync_runs.reason`, where it would sit forever, readable by any surface that shows a
  run. The guard costs one function and is tested by injecting the token into an exception.

- Redaction is by value, not by pattern: we know the exact string, so we replace it. A pattern
  would have to guess what a credential looks like, and would miss the next format.

This is an invariant, not an intention. §6 tests it.

## 5. Error handling

- The health endpoint never fails because Notion failed. Notion unreachable → `token.state` and
  every root `unknown`, HTTP `200`. A diagnostic that goes down with the thing it diagnoses is
  useless exactly when it is needed.
- Per-root probe timeout: 5s. There is no aggregate deadline; with bounded concurrency and a
  per-probe timeout the endpoint is already bounded, and a second knob would be a number nothing
  tests (I-008).
- No token → `token.state = not_configured`, roots are not probed (`unknown`), HTTP `200`.
- `token.state = invalid` → roots are not probed. Every root probe would answer `401`, and
  reporting them as `unreachable` would blame the pages for the token.

## 6. Testing

Against a fake transport, so every branch is reachable:

- Token: `401` → `invalid`; `200` → `ok` with integration and workspace names; `429`/`500`/
  timeout/transport error → `unknown`.
- Root: `200` on `/pages` → `reachable`; **any non-200 on `/pages` then `200` on `/databases`**
  → `reachable` (a database is not a missing page); `404` on both → `unreachable`; `403` on both
  → `unreachable` (same state, same sentence); `400` on both → `invalid_id`; `429`/`500`/timeout
  → `unknown`, **never** `unreachable`.
- A probe that fails carries no exception text into the response — assert the body against an
  allow-list of fields, so a future `str(e)` cannot be added without failing the test.
- `token.state in (invalid, not_configured)` → zero root probes are issued (assert on the
  transport, not on the output).
- `POST /roots` with an unreachable page → `201`, **the row is written**, and the response
  carries `state: unreachable` with a remedy.
- `GET /health` returns `200` when every Notion call raises.
- `GET /health` without `manage_sources` → `403`, and the MCP tool surfaces that `403` rather
  than pretending the connection is fine.
- A root list read once: removing a root mid-call does not raise; `checked_at` is present.
- **Redaction**: a `finish_run` whose exception string contains the token value persists a
  `reason` that does not. Seed a run, raise an exception carrying the token, read the row back.
  (Today's `notion_client` does not put it there; the test injects it, so the guard is exercised
  rather than assumed.)
- No response body or persisted row emitted by *our* code contains more than the token's first
  four characters. This is a claim about the code paths in this SPEC, asserted by inspecting the
  values those paths produce — not a claim about every log line the process will ever emit,
  which nothing could test.

## 7. Acceptance

A user who pastes a page they never shared with the integration is told **at that moment**, not
after a sync — and the row is still registered, so they can go share it and sync. A user whose
token was revoked sees `invalid` on the 소스 page instead of a green "connected". An agent can
ask `nexus_sources_health()` before syncing. The token value never leaves the process that reads
it, not even into an error string. And nothing named here is visible to a caller without
`manage_sources`.
