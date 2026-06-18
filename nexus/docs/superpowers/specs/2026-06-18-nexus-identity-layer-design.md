# Nexus minimal identity layer — design

**Date:** 2026-06-18
**Status:** approved (brainstorming) → implementation
**Scope:** C3 minimal slice. Related: [ADR-0001](../../../../adr/ADR-0001-adopt-a2a-inter-agent-interop.md),
[SPEC Phase 0 A2A](../../../../specs/SPEC-nexus-a2a-server-phase0-spike.md) (this is its Phase 2 prerequisite).

## Problem

Nexus has **no authentication**. `tenant` and `classification_max` (clearance) arrive as
request body/query fields with defaults (`tenant="default"`, `classification_max="INTERNAL"`).
`base_filter` (tenant + `classification <= clearance` + `is_quarantined=false` +
`status='active'`) filters correctly, but the clearance value is **self-asserted by the
caller** — anyone can send `classification_max="RESTRICTED"`, `tenant="<any>"` and retrieve
privileged content. The same hole exists on HTTP, the MCP server, and Slack.

This contradicts Nexus's own principle ("System decides … default-deny") and blocks A2A
Phase 2 (external exposure), whose SPEC requires "one token ⇒ exactly one (tenant, clearance)".

## Goal

Bind **identity → (tenant, clearance) server-side** so callers can never widen their own
scope. Minimal slice only: a bearer token resolves to a fixed `(tenant, clearance)`;
requested tenant/clearance may only *narrow*. No JWT, no token issuance tooling, no
per-user management, no admin UI, no audit log (all deferred to roadmap Phase 3).

## Non-goals (YAGNI)

JWT / OAuth, token rotation tooling, multi-reviewer or per-user identity, tenant-management
UI, audit trail. Single static tokens defined in config (stored hashed).

## Approach

**FastAPI dependency that resolves a `Principal` and clamps scope** (chosen over global
middleware for explicitness, per-endpoint testability, and because the resolver is exactly
what the A2A `policy.py` will reuse).

## Components

Each unit has one purpose, a clear interface, and is unit-testable without a database.

### 1. `nexus/auth/principal.py`
```python
@dataclass(frozen=True)
class Principal:
    name: str
    tenant: str
    clearance: str   # PUBLIC | INTERNAL | RESTRICTED

def resolve_principal(token: str | None, principals: list[dict]) -> Principal | None:
    """sha256(token) matched (constant-time) against configured principals. None if no match."""
```
- Config carries `token_sha256`, never the plaintext token.
- Comparison is constant-time (`hmac.compare_digest`).

### 2. `nexus/auth/scope.py`
```python
_ORDER = {"PUBLIC": 0, "INTERNAL": 1, "RESTRICTED": 2}

def effective_scope(principal: Principal,
                    requested_tenant: str | None,
                    requested_clearance: str | None) -> tuple[str, str]:
    """tenant = principal.tenant (requested tenant ignored → tenant isolation).
       clearance = min(principal.clearance, requested_clearance or principal.clearance).
       Never widens. Unknown clearance strings clamp to the principal's."""
```
- Pure function; the single source of truth for "narrow-only".

### 3. `get_principal` dependency (in `nexus/auth/deps.py`, used by `api.py`)
- Reads `Authorization: Bearer <token>`.
- **Permissive mode** (config has no `auth.principals`): returns a default
  `Principal("anonymous", "default", "INTERNAL")` and logs a one-time warning. Preserves
  today's local Web UI / CLI behavior with zero config.
- **Enforced mode** (principals configured): missing/invalid token → `HTTPException(401)`
  (default-deny).

### 4. Endpoint wiring (`api.py`)
Every search/answer/documents/diff/claims endpoint takes `principal = Depends(get_principal)`
and computes `tenant, clearance = effective_scope(principal, req.tenant, req.classification_max)`,
then passes the clamped values into the existing `hybrid_search` / `base_filter` paths.
**No change to retrieval/ranking logic.**

### 5. MCP server (`mcp/server.py`)
Same resolver applied: the MCP process holds its token via env (`NEXUS_MCP_TOKEN`); tool
`classification_max` params are clamped through `effective_scope`. (If unset and no
principals configured → permissive default, mirroring HTTP.)

### 6. Config schema (`config.yaml`)
```yaml
auth:
  principals:
    - name: "analyst"
      token_sha256: "<sha256 hex of the bearer token>"
      tenant: "acme"
      clearance: "INTERNAL"
```
Absent/empty `auth.principals` ⇒ permissive mode.

## Data flow

```
request ─► get_principal (Authorization: Bearer)
                 │  permissive: default principal + warn
                 │  enforced:   401 if unknown
                 ▼
        effective_scope(principal, req.tenant, req.classification_max)
                 │  tenant ← principal.tenant ; clearance ← min(...)
                 ▼
        hybrid_search / list / diff / claims  (base_filter unchanged)
```

## Error handling

| Situation | Behavior |
|---|---|
| No `auth.principals` configured | Permissive: default principal `(default, INTERNAL)` + one-time warning log |
| Principals configured, no/invalid token | `401 Unauthorized` (default-deny) |
| Requested clearance > granted | Silently clamped down to granted |
| Requested tenant ≠ granted | Ignored; principal's tenant used (no tenant-existence leak) |
| Unknown clearance string | Clamped to principal's clearance |

## Testing (TDD, DB-free for the security core)

- `tests/test_auth_principal.py` — sha256 match; unknown token → None; constant-time compare; malformed config tolerated.
- `tests/test_auth_scope.py` — clearance never widens (INTERNAL principal + RESTRICTED request → INTERNAL); RESTRICTED principal + PUBLIC request → PUBLIC; tenant forced to principal's; None requests → principal defaults; unknown strings clamp.
- `tests/test_auth_deps.py` — FastAPI `TestClient` with a stub endpoint: permissive mode (no token → default principal); enforced mode (no token → 401, valid token → principal, low-clearance token cannot widen).
- Parity: existing endpoint tests pass unchanged in permissive mode.

## Reuse for A2A

`resolve_principal` + `effective_scope` are precisely the A2A SPEC's `policy.py` contract
("one token ⇒ one (tenant, clearance)", caller may only narrow). C3 directly unblocks A2A
Phase 2 (external exposure) with no rework.

## Rollout & reversibility

- Backward compatible by default (permissive when unconfigured).
- Secure-by-config: add `auth.principals` to enforce.
- Reversal: remove `nexus/auth/` + the `Depends(get_principal)` wiring; behavior returns to today's.
