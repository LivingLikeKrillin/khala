# Nexus minimal identity layer — design

**Date:** 2026-06-18
**Status:** approved (brainstorming) → implementation. **Rev 2** — incorporates independent spec review (3 high, 3 medium, 2 low).
**Scope:** C3 minimal slice. Related: [ADR-0001](../../../../adr/ADR-0001-adopt-a2a-inter-agent-interop.md),
[SPEC Phase 0 A2A](../../../../specs/SPEC-nexus-a2a-server-phase0-spike.md) (this is its Phase 2 prerequisite).

## Problem

Nexus has **no authentication**. `tenant` and `classification_max` (clearance) arrive as
request body/query fields with defaults (`tenant="default"`, `classification_max="INTERNAL"`).
`base_filter` (tenant + `classification <= clearance` + `is_quarantined=false` +
`status='active'`) filters correctly, but the clearance value is **self-asserted by the
caller** — anyone can send `classification_max="RESTRICTED"`, `tenant="<any>"` and retrieve
privileged content. The same hole exists on HTTP, the MCP server, and Slack.

This contradicts Nexus's own principle (CLAUDE.md #3: "Default-deny") and blocks A2A Phase 2,
whose SPEC requires "one token ⇒ exactly one (tenant, clearance)".

## Goal

Bind **identity → (tenant, clearance) server-side** so callers can never widen their own
scope. Minimal slice: a bearer token resolves to a fixed `(tenant, clearance)`; requested
tenant/clearance may only *narrow*; **fail closed by default**.

## Non-goals (YAGNI — deferred to roadmap Phase 3)

JWT / OAuth, token issuance/rotation tooling, per-user identity, tenant-management UI, audit
trail. Single static tokens defined in config (stored hashed, high-entropy).

**Write/ingest paths are IN scope for tenant-binding** (see §4) — a review finding: leaving
`/ingest`, `/upload`, `/otel/aggregate` unauthenticated allows cross-tenant corpus poisoning
that feeds everyone's grounded answers. They get the same dependency (auth required in
enforced mode; tenant forced to the principal's). Per-write fine-grained roles remain Phase 3.

## Approach

**FastAPI dependency that resolves a `Principal` and clamps scope** (over global middleware:
explicit, per-endpoint testable, and the resolver is exactly what A2A `policy.py` reuses).

## Security posture (review-driven)

- **Fail closed by default.** Absence of `auth.principals` ⇒ **enforced mode with no valid
  principals ⇒ every request 401**. Open/anonymous access is *never* the silent default.
- **Permissive is an explicit, loud opt-out only:** `NEXUS_ALLOW_ANONYMOUS=1` (env) OR
  `auth.mode: permissive` (config). Then unauthenticated requests resolve to
  `Principal("anonymous", "default", "PUBLIC")` — **least privilege, PUBLIC not INTERNAL** —
  and a warning is logged **on every request** and surfaced in `/status`.
- **CORS prerequisite:** the current `allow_origins=["*"]` + `allow_credentials=True` is an
  invalid/insecure combo once an `Authorization` header is used. Replace `*` with a
  configurable origin allowlist (`auth.allowed_origins`, default the local UI origin).
- **Anti-footgun (the happy path is "use a token", not "disable auth"):** the `401` response
  body says *"authentication required; configure a bearer token — do NOT enable anonymous
  access on shared/production deployments."* The shipped `config.yaml` example ships a
  **non-resolving placeholder hash** (`REPLACE_ME`), **not** a working token — so the obvious
  next step is to run `nexus auth gen-token` / `hash-token` and paste a real hash. **Startup
  guard:** the server **refuses to boot in `enforced` mode** if any principal still carries the
  placeholder hash (prevents shipping a known credential). The Web UI reads `/status`; when it
  reports permissive, it shows a visible **"PUBLIC-only (anonymous)"** banner so a down-scoped
  (empty/partial) result set reads as a security boundary, not a bug.

### Key invariants
1. **`effective_scope` is the *sole* producer of the `(tenant, clearance)` that reaches
   `hybrid_search`/`base_filter`.** Raw `req.classification_max` / `req.tenant` must NEVER flow
   downstream. (Postgres `$N::classification_level` throws on any non-enum string → generic 500
   that leaks nothing useful and breaks the request; `floor_public` upstream prevents it.)
2. One credential ⇒ exactly one `(tenant, clearance)`. Caller input only narrows.
3. `/status` is **unauthenticated** (stays out of the privileged dependency set) and exposes
   only `{ auth_mode, anonymous }` booleans — never `allowed_origins`, principal names, or hashes.

## Components

Each unit has one purpose, a clear interface, and is unit-testable without a database.

### 1. `nexus/auth/clearance.py` — single source of truth for ordering
```python
ORDER = {"PUBLIC": 0, "INTERNAL": 1, "RESTRICTED": 2}
def parse(level: str | None) -> str | None:   # returns a valid level or None
def floor_public(level: str | None) -> str:   # invalid/None -> "PUBLIC" (fail-safe)
```
The same `PUBLIC<INTERNAL<RESTRICTED` order backs both `scope.py` and the SQL
`::classification_level` cast; a test asserts parity.

### 2. `nexus/auth/principal.py`
```python
@dataclass(frozen=True)
class Principal:
    name: str
    tenant: str
    clearance: str   # a valid clearance level

def resolve_principal(token: str | None, principals: list[dict]) -> Principal | None:
    """sha256(token) compared (hmac.compare_digest per entry) against configured
       token_sha256 values. None if no token or no match."""
```
- Config carries `token_sha256` only — **never plaintext**.
- **Tokens MUST be high-entropy** (`secrets.token_urlsafe(32)`); the unsalted-sha256 scheme's
  security rests on this. CLI helper `nexus auth hash-token`: **reads the token from stdin**
  (never argv — argv leaks to shell history / `ps`), and **outputs only the sha256 hex** for
  pasting into `auth.principals[].token_sha256`. A sibling `nexus auth gen-token` prints a fresh
  `secrets.token_urlsafe(32)`. (Low-entropy tokens are out of spec.)

### 3. `effective_scope` (`nexus/auth/scope.py`)
```python
def effective_scope(principal, requested_tenant, requested_clearance) -> tuple[str, str]:
    """tenant = principal.tenant (requested tenant IGNORED → tenant isolation).
       clearance = min(principal.clearance, floor_public(requested_clearance)).
       Invalid/typo'd requested clearance floors to PUBLIC (fail-safe), never widens."""
```
Pure function; the single source of truth for "narrow-only". Floors unknown input to PUBLIC
rather than to the principal's level (review fix: a typo must not clamp *up*).

### 4. `get_principal` dependency (`nexus/auth/deps.py`) + full route coverage
- Reads `Authorization: Bearer <token>`.
- **Enforced mode (default):** invalid/missing token → `HTTPException(401)`.
- **Permissive mode (explicit opt-out only):** anonymous `PUBLIC` principal + per-request warning.
- **Every privileged route gets `principal = Depends(get_principal)`** and replaces
  `req.tenant`/`req.classification_max` with `effective_scope(...)`. Enumerated by auditing
  routes that touch `base_filter` / `hybrid_search` / `tenant`, **not** a hand-list:
  - reads: `/search`, `/search/answer`, **`/search/answer/stream` (SSE)**, **`/graph/{entity}`**,
    `/diff`, `/documents`, **`/entities/suggest`**, `/claims/value`, `/claims/grade-authority`
  - writes (tenant-bound): `/ingest`, `/upload`, `/otel/aggregate`
- **Coverage guard test:** introspect `app.routes`; assert every route in the privileged set
  declares the `get_principal` dependency. The test flattens `route.dependant` recursively
  (dependencies can be declared either in the signature `= Depends(...)` or via
  `dependencies=[...]`), not just top-level `.dependencies`.
- **Dead inputs:** the body/query `tenant` and `classification_max` fields (`SearchRequest`,
  `AnswerRequest`, the `/graph` & `/documents` query params, the `/upload` `tenant` query) are
  now **ignored** for scope. Mark them `deprecated=True` with an OpenAPI description
  ("ignored — scope is derived from your credential") so API clients don't believe they control
  access. (Removing them outright is a breaking API change → defer; deprecate now.)
- **SSE note:** `get_principal` is a *route-signature* dependency on `/search/answer/stream`, so
  it runs and can 401 **before** the `StreamingResponse` generator is constructed — never put
  auth inside the event-stream closure.

### 5. MCP server (`mcp/server.py`) — token **forwarding**, not resolution
The MCP server is a pure HTTP client (`_api_call` builds an `httpx.AsyncClient` with no DB or
`auth.principals` access) — it **cannot resolve principals**. Correct design:
- `_api_call` attaches `Authorization: Bearer ${NEXUS_MCP_TOKEN}` to **every** request; the
  **API** resolves it and clamps scope. The MCP holds *one* credential = *one* `(tenant,clearance)`.
- **Startup guard:** if `NEXUS_MCP_TOKEN` is unset, the MCP server fails fast with a clear error
  (rather than emitting 401s on every tool call once the API enforces).
- This is shipped **in the same change** as API enforcement (see Migration) so MCP tools don't
  break on upgrade.
- **Single-principal by construction:** one shared `NEXUS_MCP_TOKEN` ⇒ all MCP traffic resolves
  to one `(tenant, clearance)` = the MCP service ceiling, regardless of the human behind the
  tool. Intentional and documented; per-user MCP scoping (forwarding the *caller's* token) is
  a Phase 3 concern, not this slice.

### 6. CORS (`api.py`)
Replace `allow_origins=["*"]` with `auth.allowed_origins` (list; default `["http://localhost:8000"]`
or the configured UI origin), keep `allow_credentials=True`. Documented as an enforcement prerequisite.

### 7. Config schema (`config.yaml`)
```yaml
auth:
  mode: enforced            # or "permissive" (explicit opt-out)
  allowed_origins: ["http://localhost:8000"]
  principals:
    - name: "analyst"
      token_sha256: "REPLACE_ME"     # run: nexus auth gen-token | nexus auth hash-token
      tenant: "acme"
      clearance: "INTERNAL"
```
The committed example carries the **non-resolving placeholder** `REPLACE_ME` (never a real
token/hash). **Startup refuses to boot in `enforced` mode while any principal's hash is
`REPLACE_ME`** — forcing operators to mint a real token, and preventing a known credential from
shipping. No `principals` + `mode: enforced` (default) ⇒ all requests 401 (fail closed).
Permissive requires `mode: permissive` or `NEXUS_ALLOW_ANONYMOUS=1`.

## Data flow

```
request ─► get_principal (Authorization: Bearer)
                 │  enforced (default): 401 if missing/invalid
                 │  permissive (opt-out): anonymous PUBLIC + warn-every-request
                 ▼
        effective_scope(principal, req.tenant, req.classification_max)
                 │  tenant ← principal.tenant ; clearance ← min(principal, floor_public(req))
                 ▼
        hybrid_search / list / diff / claims / ingest  (base_filter unchanged)
```

## Error handling

| Situation | Behavior |
|---|---|
| No principals, default `mode: enforced` | **All requests 401** (fail closed) |
| `mode: permissive` / `NEXUS_ALLOW_ANONYMOUS=1` | Anonymous `PUBLIC` principal + per-request warning + `/status` flag |
| Principals set, no/invalid token | `401 Unauthorized` |
| Requested clearance > granted | Clamped down |
| Requested clearance invalid/typo | Floored to `PUBLIC` (fail-safe) |
| Requested tenant ≠ granted | Ignored; principal's tenant used (no tenant-existence leak) |

## Testing (TDD; security core is DB-free)

- `test_auth_clearance.py` — ordering parity with the SQL enum; `floor_public` on junk → PUBLIC.
- `test_auth_principal.py` — sha256 match via `compare_digest`; unknown/empty token → None; malformed config tolerated. *(No flaky wall-clock timing test; assert behavior, not nanoseconds.)*
- `test_auth_scope.py` — never widens (INTERNAL principal + RESTRICTED req → INTERNAL); RESTRICTED principal + PUBLIC req → PUBLIC; typo'd clearance → PUBLIC; tenant forced; None → principal default.
- `test_auth_deps.py` — `TestClient` stub route: enforced no-token → 401; valid token → principal; low-clearance token cannot widen; permissive opt-out → anonymous PUBLIC; **a typo'd `classification_max` returns 200 with PUBLIC scope, never a 500** (proves invalid clearance is floored before the SQL enum cast).
- `test_mcp_auth_forwarding.py` — `_api_call` attaches `Authorization: Bearer ${NEXUS_MCP_TOKEN}`; MCP startup raises if the token is unset.
- `test_auth_route_coverage.py` — **guard:** every privileged `app.route` declares `get_principal`.
- `test_auth_enforced.py` — **enforced-mode runtime behaviour (the core security property), parametrized over the privileged route list:** no token → 401; malformed/unknown token → 401; valid token → exactly the granted `(tenant, clearance)`; **confused-deputy:** body/query `tenant=other` + `classification_max=RESTRICTED` with a PUBLIC token → PUBLIC + principal's tenant (the deprecated params are truly unread); placeholder-hash principal in enforced mode → boot refused.
- Parity: existing endpoint tests run in `mode: permissive` (assertions updated where they encoded the old self-asserted-`INTERNAL` bug — anonymous is now `PUBLIC`). Permissive parity does **not** substitute for `test_auth_enforced.py`; both run.

## Reuse for A2A

`resolve_principal` + `effective_scope` are precisely the A2A SPEC's `policy.py` contract
("one token ⇒ one (tenant, clearance)", narrow-only, fail-closed). C3 directly unblocks A2A
Phase 2 with no rework.

## Migration (breaking — enforced is the new default)

Once this ships, any caller without a valid Bearer gets **401**. To avoid breaking everything
on upgrade, the following land **together in one change**:
- **MCP**: `_api_call` forwards `Authorization: Bearer ${NEXUS_MCP_TOKEN}`; MCP startup fails
  fast if the token is unset. `NEXUS_MCP_TOKEN` becomes a documented requirement.
- **Web UI / CLI**: `config.yaml` example carries the `REPLACE_ME` placeholder; docs show
  "`gen-token` → `hash-token` → paste". The happy path is *mint and use a token* (enforced boot
  is refused while the placeholder remains).
- **Local dev / CI**: set `auth.mode: permissive` (or `NEXUS_ALLOW_ANONYMOUS=1`) explicitly;
  the existing endpoint test-suite runs in permissive mode, with assertions updated where they
  encoded the old self-asserted-`INTERNAL` bug (they now expect `PUBLIC` for anonymous).
- **Slack** path (same self-assert hole) is out of this slice → tracked as follow-up.

## Reversibility

Remove `nexus/auth/`, the `Depends(get_principal)` wiring, the MCP header forwarding, and
restore CORS `*`. Behavior returns to today's (insecure) baseline.

## Review log (independent spec review, 2026-06-18)

| Sev | Issue | Resolution |
|---|---|---|
| high | SSE/`/graph`/`/entities/suggest` omitted from wiring → headline bug stays open on UI main endpoint | §4 enumerates all privileged routes + a `app.routes` coverage-guard test |
| high | Permissive default fails *open* on misconfig (violates default-deny) | §"Security posture": **enforced is default, fail closed**; permissive is explicit loud opt-out |
| high | Anonymous default INTERNAL too privileged | Anonymous principal = **PUBLIC** (least privilege) |
| medium | CORS `*` + credentials breaks/insecure with Authorization header | §6: configurable origin allowlist, enforcement prerequisite |
| medium | Unsalted sha256 weak for low-entropy tokens | §2: tokens MUST be high-entropy (`secrets.token_urlsafe(32)`); helper documented |
| medium | "constant-time" oversold; timing test flaky | Per-entry `compare_digest`; dropped wall-clock test; behavioral assert |
| low | `effective_scope` unknown clearance clamps *up* to principal's | Floors to **PUBLIC** (fail-safe); single ordering enum |
| low | Write/ingest paths leave cross-tenant poisoning open | Brought **in scope** for tenant-binding (§Non-goals + §4) |

### Rev 3 — second-pass review (2026-06-18)

| Sev | Issue | Resolution |
|---|---|---|
| high | MCP "same resolver" is wrong — it's an httpx client with no `auth.principals` access | §5 rewritten: MCP **forwards** `Authorization: Bearer ${NEXUS_MCP_TOKEN}`; API resolves; startup guard |
| high | Migration trap: enforced default → all MCP/HTTP callers 401 on upgrade | §Migration: MCP forwarding + dev token + permissive-for-CI land together |
| medium | Permissive-PUBLIC footgun (operator flips on anonymous to "fix" empty UI) | §Security posture anti-footgun: explicit 401 body, ship dev token, UI "PUBLIC-only" banner from `/status` |
| medium | Invalid clearance reaching `::classification_level` → 500 leak | Invariant #1 (effective_scope is sole producer) + deps-test: typo → 200/PUBLIC not 500 |
| low | `/upload` tenant is a Query param; body/query scope fields become misleading | Mark `deprecated` in OpenAPI ("ignored — scope from credential") |
| low | `hash-token` underspecified | §2: reads stdin (not argv), outputs only sha256 hex; `gen-token` sibling |
| low | `/status` exposure | Invariant #3: `/status` unauthenticated, exposes only `{auth_mode, anonymous}` |
| — | Confirmed non-issues (no churn) | route-coverage test feasible (flatten `route.dependant`); SSE Depends runs before stream; writes-in-scope is consistent minimal posture |

### Rev 4 — third-pass review (2026-06-18)

Round 3 confirmed all prior highs (1–5) resolved; these new items are now incorporated:

| Sev | Issue | Resolution |
|---|---|---|
| high | "Tests move to permissive" leaves **enforced-mode fail-closed untested** | New `test_auth_enforced.py`: per-route 401 (no/bad token), valid → exact scope, confused-deputy, placeholder-boot-refusal. Permissive parity does not substitute. |
| medium | One shared `NEXUS_MCP_TOKEN` collapses MCP to a single principal | §5: documented as single-principal-by-construction (= MCP service ceiling); per-user forwarding is Phase 3 |
| medium | Shipping a working dev token in the example invites copy-to-prod of a known credential | Example uses non-resolving `REPLACE_ME`; **enforced boot refused while placeholder present** |
| low | Deprecated scope params safe only if truly unread | Confused-deputy test asserts body/query `tenant`/`classification_max` are ignored |

Verdict trajectory: round 1 (3 high) → round 2 (2 high) → round 3 (1 high) → Rev 4 addresses all; remaining items are bounded and verified by the enforced-mode test suite during TDD implementation.
