---
id: SPEC-nexus-access-jwt-auth
type: spec
title: Browser identity from Cloudflare Access — verify the JWT, stop handing out
  a shared bearer
status: approved
date: 2026-07-10
linked_adrs:
- ADR-0004
tags:
- nexus
- auth
- security
- surface
approved_by: LivingLikeKrillin
reviewed_at: '2026-07-10T11:29:58Z'
content_hash: sha256:dca73bfb2147a6091b9e43d14e0ee5bce2d36a6476293228a7e919993c0e3ec4
---

## 1. Goal

Give the web UI a real, per-person identity behind Cloudflare Access, and close the hole that
`/auth/dev-token` opens in a tunnelled deployment.

Today Nexus behind a tunnel gives every visitor the same INTERNAL bearer. Cloudflare Access
already proves *who* each visitor is — it just isn't wired to *what* they can do. This SPEC reads
the identity Access already established, verifies it in Nexus (not on trust of the edge), and maps
it to a principal. Access guards the perimeter; the JWT signature is the authorization.

## 2. Non-goals

- **A login screen in Nexus.** Nexus has no password store and gains none. Authentication happens
  at Cloudflare's hosted screen; Nexus only *verifies the result*.
- **Choosing or coding an identity provider.** Email OTP today, Google or GitHub later, is a
  Cloudflare dashboard change. The claims Nexus depends on — `iss`, `aud`, `exp`, `email` — are set
  by Cloudflare Access, not by the upstream IdP, so they are present whichever IdP the operator
  wires (I-001). Switching IdP changes *where Cloudflare learned the email*, not the token Nexus
  verifies. The verifier is written against Access's token, and this SPEC claims decoupling only
  for those four claims, not for anything IdP-specific (which Nexus never reads).
- **Multi-tenant identity.** One instance, one tenant (`default`). The `email` selects a principal
  within it, not a tenant.
- **Replacing the token model wholesale.** ADR-0004 §3 names the tunnel deployment mechanism as
  "tokens". This SPEC does not delete that — the bearer path stays for localhost and for any
  non-Access deployment (I-010). It *adds* a per-identity path that takes precedence when Access is
  configured, and turns the shared token off in that one case. It is an evolution of the ADR's
  model, not a contradiction of it; the ADR entry reads "tokens" and now also means "or Access
  identity when Access is the door".
- **Session management, refresh, logout.** Cloudflare owns the cookie and the session. Nexus sees
  one already-authenticated request at a time and verifies it fresh each time.

## 3. What exists

`/auth/dev-token` returns `NEXUS_DEV_TOKEN` to *anyone who reaches it*, unauthenticated by design
(`api.py`; the route is in `UNGATED`). The web UI fetches it and uses it as a Bearer. The token's
principal is `local-dev`, tenant `default`, clearance `INTERNAL`, capabilities
`[manage_sources, manage_documents]` (`auth/config.py`) — so it can hide documents and supersede.

On localhost that is a frictionless on-ramp. Behind a tunnel it is a wall with a key taped to it:

- The route is ungated, so whoever reaches the origin gets an INTERNAL bearer.
- `docker-compose.prod.yml` *requires* a strong `NEXUS_DEV_TOKEN` (`${NEXUS_DEV_TOKEN:?…}`), so the
  prod overlay's own hardening hands out a stronger key through the same open door. The dev-token
  docstring claims prod sets nothing and so exposes nothing; the prod overlay contradicts it.
- Every team member is the same principal. Nobody's actions are attributable; per-person capability
  is impossible.

Cloudflare Access, when configured (runbook §4), sits in front and adds a header to every request
it proxies:

    Cf-Access-Jwt-Assertion: <header>.<payload>.<signature>

The payload is base64, not encrypted — `email`, `aud`, `iss`, `exp` are readable by anyone. Its
value is the signature: Cloudflare signed `header.payload` with a private key only Cloudflare
holds. The matching public keys live at `<iss>/cdn-cgi/access/certs` (a JWKS).

**The claim shapes here are from Cloudflare's published documentation, not from the live edge**
(I-008). The fixture in §6 mints RS256 tokens with these claims, which is enough to test the
verifier's logic — but if the real edge diverges (a claim named differently, an unexpected `alg`),
that surfaces only at §8, against the live tunnel. §8 is therefore not ceremony; it is the check
that the fixture matched reality. Until it passes, "verified" means "verified against our model of
Access", and this SPEC says so.

## 4. Design

### 4.1 One verifier, at the one door

`resolve_request_principal` (`auth/deps.py`) is the single place every gated route resolves its
principal. Access verification goes there, before the existing bearer path:

1. Read `Cf-Access-Jwt-Assertion`. Absent → fall through to the existing bearer/permissive logic
   (so localhost without Access is unchanged).
2. Decode the header segment; take `kid`.
3. Select the public key with that `kid` from the cached JWKS (§4.3).
4. Verify the signature over `header.payload` with that key (RS256).
5. Check `iss`, `aud`, `exp` (§4.2).
6. Require a non-empty `email` claim (§4.4). A signed token without one is a `401`, not the
   unmapped default — an identity mapping keyed on `email` cannot run on a token that has none.
7. Map `email` → principal (§4.4).

Any failure in 2–6 is a `401`, never a fallback to a shared bearer. A request that presents an
Access header is asking to be judged as that identity; a broken or identity-less assertion is a
rejected identity, not an anonymous one.

### 4.2 What must hold, and why each is load-bearing

- **Key material comes only from the trusted JWKS, never from the token.** This is the invariant the
  whole design rests on (2nd-round I-007). The token's `kid` *selects* which cached public key to
  use; it never *supplies* key material. A token may carry any header fields it likes — an embedded
  key (`jwk`), a key URL (`jku`), a chosen `alg` — and the verifier ignores all of them except `kid`
  and the RS256 signature bytes. `alg` is pinned to RS256 by the verifier, not read from the header
  (an attacker who could set `alg: none` or `alg: HS256` with the public key as the HMAC secret
  would bypass everything). The public key is fetched from the configured issuer's JWKS and from
  nowhere else.
- **`iss` is compared against a configured value, never trusted from the token.** The token says
  who issued it; if we believed that and fetched *its* JWKS URL, an attacker would set `iss` to
  their own server, serve their own keys, and self-sign. `auth.access.issuer` in config is the only
  issuer Nexus trusts, and the JWKS URL is derived from *it*, not from the token.
- **`aud` is required and checked.** A JWT minted by the same Cloudflare team for a *different*
  application is correctly signed — it would pass every check except this one. Without `aud`, any
  app behind the same team's Access is a valid credential for Nexus. `auth.access.aud` is the
  application tag Nexus requires.
- **`exp` is required and checked.** No expiry check means a captured token works forever. The
  payload is readable, so a leaked token is a leaked credential until it expires; expiry is the only
  thing that bounds the damage.
- **The header is verified, not trusted for existing.** Access proves "came through the tunnel";
  it cannot prove "came *only* through the tunnel". A request hitting `localhost:8000` directly can
  forge the header string. The signature is what a forger cannot produce. So presence of the header
  is not evidence — the signature is. This is why Nexus verifies even though Access already did.

- **Signature verification stops a *forged* token; it does not stop a *replayed* one, and the
  origin must not be directly reachable** (I-002). A valid, unexpired token captured off the wire
  and sent straight to `localhost:8000`, bypassing the edge, would verify — the signature is real.
  Nexus cannot distinguish it from a legitimate proxied request, and `exp` is the only bound (the
  doc says so). Closing this is a *deployment* invariant, not a code one: the origin binds to
  `127.0.0.1:8000` and is reachable only through `cloudflared`, never a public port. The prod
  overlay already binds `127.0.0.1:8000` (PR #108); this SPEC states it as a required condition of
  turning Access on, and §8 verifies it. Naming what code cannot enforce is the point — an
  unstated assumption here is a silent hole.
- **Nexus reads the header, never the cookie.** `CF_Authorization` is the browser↔Cloudflare
  session channel and is `HttpOnly`. Parsing it in the origin reaches into a channel that is not
  ours; the header is the edge's deliberate hand-off to the origin, and the only thing we read.

### 4.3 JWKS: cached, and refreshed for rotation

The JWKS is fetched from `<issuer>/cdn-cgi/access/certs` and cached. Cloudflare rotates signing
keys, publishing new and old together under distinct `kid`s so tokens signed by either verify
during the overlap. So:

- Cache with a TTL (config `auth.access.jwks_ttl_seconds`, default 3600).
- On a token whose `kid` is not in the cache, refresh once before rejecting — a rotation may have
  just happened. Without a floor, an attacker sending random `kid`s turns Nexus into an amplifier
  against the JWKS endpoint. The bound is *at most one refresh per `min_refresh_interval`* (default
  60s), enforced by a **single-flight guard**: a refresh-in-progress flag plus a last-refresh
  timestamp, both under one lock (I-007). Concurrent unknown-`kid` requests await the one refresh or
  are rejected against the timestamp; they do not each hit the endpoint. This is a concrete
  mechanism, not an assertion — §6 asserts N concurrent unknown-`kid` requests cause ≤1 fetch.
- If the JWKS endpoint is unreachable and the cache is empty, Access verification fails closed —
  `503`, not "skip verification". A verifier that waves tokens through when it cannot check them is
  worse than no verifier.

### 4.4 email → principal, and the unmapped case

`auth.access.identities` maps an email to a principal spec (capabilities, clearance). The token's
`email` selects one. This is the same shape as `auth.principals`, keyed by email instead of token
hash.

**Email is the unique key** (2nd-round I-005): a duplicate email across identities is a config
error caught at startup validation, not a runtime precedence puzzle. A mapped email uses its
identity; only an unmapped email falls to `default_identity`, so the two never both apply to one
request. What a mapping grants is independent of what Access admits — Access is the "who may enter",
the mapping is the "what they may do"; a mapping may grant less than, but the clearance it grants is
still bounded by the tenant's classification ceiling, exactly as `auth.principals` already is.

An email that Access admitted but Nexus has no mapping for gets the **configured default identity**,
`auth.access.default_identity` — capabilities `[]` (no destructive action) and a clearance the
operator sets. It is **not** hard-coded to `INTERNAL`.

The reason is I-011: "read-only" is not "harmless". Clearance gates *reads* —
`classification <= clearance` in every search (`hybrid.py`). An `INTERNAL` default lets an admitted-
but-unmapped email read the entire INTERNAL corpus; it only blocks `RESTRICTED` and blocks writes.
Whether that is safe depends on what the deployment classifies as INTERNAL, which this SPEC cannot
know. So the clearance of the default is the operator's decision, defaulting to `PUBLIC` (the
floor), and the SPEC's invariant is the narrow one it can guarantee: **the default identity has
zero capabilities** — admitted-but-unmapped can never take a destructive action, whatever it can
read.

This keeps the two layers from lockstep: tightening who enters is an Access policy edit, granting
what they can do (or read) is a Nexus config edit, and neither silently implies the other. For a
one-person deployment the mapping is one entry; the default is the safety net, not the plan.

### 4.5 The dev-token on-ramp inverts

`NEXUS_DEV_TOKEN` stays for localhost. What changes is prod:

- The base compose keeps it for local dev (it already lives in the dev overlay, per
  `test_compose_credentials`).
- When `auth.access.issuer` is configured, `/auth/dev-token` returns `null` and the `local-dev`
  principal is not registered. The two identity paths do not run at once: if Access is configured,
  the shared key is off.

  **`auth.access.issuer` set is Nexus's declaration that it is behind Access — the config, not a
  probe, is the source of truth** (I-005). Nexus cannot detect from inside whether a tunnel is
  actually in front; the operator asserts it by configuring the issuer. The two dangerous
  mismatches are handled explicitly, not left as a gap:
  - *Issuer set, Access not actually in front:* every request lacks the Access header, so every
    request is a `401` (no dev-token to fall back to). The deployment is locked, not open — visibly
    broken, which is the safe direction. Fail closed.
  - *Access in front, issuer unset:* the prod overlay refuses to boot (below), so this state cannot
    reach production. On localhost it just means the dev-token path runs, which is the intended
    local behaviour.
- The prod overlay stops *requiring* `NEXUS_DEV_TOKEN` and requires `auth.access.issuer` and
  `auth.access.aud` instead. Requiring a shared INTERNAL key in the deployment whose whole point is
  per-person identity is the contradiction §3 named. Booting the prod overlay without Access
  configured is refused — the same fail-closed posture the strong-dev-token check has today, pointed
  at the right thing.

  There is **no shared-bearer escape hatch in prod** (2nd-round I-009). An earlier draft offered a
  `NEXUS_ALLOW_SHARED_BEARER=1` override; it is removed. An override that reopens the exact
  shared-INTERNAL-key hole this SPEC exists to close, bounded by nothing, is worse than the problem.
  A deployment that genuinely wants a shared bearer is not using the prod overlay — it is choosing a
  different, documented posture, not toggling an env var past a guard.

## 5. Error handling

- No Access header → existing behaviour, unchanged: `resolve_request_principal` runs the bearer
  path, and on a config with `permissive: true` a request with no valid token resolves to the
  `ANONYMOUS` principal (PUBLIC scope) rather than `401` (I-004, `auth/deps.py` today). Enforced
  configs (prod) still `401`. Access verification is layered *before* this and does not alter it;
  its absence is not an error.
- Access header present but malformed / bad signature / wrong `iss` / wrong `aud` / expired → `401`
  with a reason code (`access_jwt_invalid`, `…_wrong_aud`, `…_expired`), never a downgrade to a
  shared or anonymous principal.
- JWKS unreachable with an empty cache → `503`. Fail closed.
- The token value never enters a log line, a DB row, or an error `detail`. The payload is readable,
  so it is a credential; same rule as the Notion token redaction (SPEC-nexus-notion-connection-health
  §4.6).

## 6. Testing

A self-contained harness mints its own RSA keypair, serves its own JWKS, and signs its own tokens —
the same construction used to explore this design. Cloudflare is replaced by a fixture; no domain,
no network.

- **Valid** token (right `iss`, `aud`, unexpired, `kid` in JWKS) → the mapped principal.
- **Forged**: signed by a *different* key whose `kid` collides with a real one → `401`. This is the
  attack the whole design defends against; it is the first test.
- **Header-supplied key material is ignored**: a token carrying an embedded `jwk`/`jku` and an
  `alg` of `none` or `HS256` → `401`. Asserts the verifier pins RS256 and sources the key only from
  the trusted JWKS (2nd-round I-007), never from the token.
- **Wrong `aud`** (correctly signed by the real key, different application tag) → `401`. Same signer,
  wrong audience — the check that a shared-team token cannot cross apps.
- **Expired** (`exp` in the past, otherwise valid) → `401`.
- **Wrong `iss`** (a token whose issuer is not the configured one) → `401`, and assert the verifier
  used the *configured* JWKS, not a URL derived from the token's `iss`.
- **Absent/empty `email`** (correctly signed, right `aud`/`iss`, unexpired, but no `email` claim)
  → `401`, **not** the default identity. Asserted explicitly (I-003) — the mapping cannot key on an
  email that is not there.
- **Unknown `kid`, concurrent** → N simultaneous unknown-`kid` requests cause **≤1** JWKS fetch
  (single-flight, I-007), asserted by counting fetches against a spy, then all reject.
- **JWKS unreachable, empty cache** → `503`, and no request is served as anonymous.
- **Unmapped email** → the default identity: capabilities empty (a destructive route → `403`), and
  clearance is whatever `auth.access.default_identity` sets, not hard-coded INTERNAL (I-011).
- **Mapped email** → its capabilities; the destructive route succeeds.
- **No Access header** → localhost bearer path unchanged (regression guard on the existing flow).
- **dev-token off under Access**: with `auth.access.issuer` set, `/auth/dev-token` returns `null`
  and `local-dev` is not among the principals.
- **Cookie ignored**: a request carrying a `CF_Authorization` cookie but no header is not
  authenticated by the cookie.
- No token value appears in any response body, log, or persisted row.

## 7. Acceptance

Behind Access, each teammate is their own principal, their `email` in the audit trail, their
capabilities their own. A tunnelled deployment no longer hands an INTERNAL bearer to whoever asks;
`/auth/dev-token` is dark in prod. A forged or expired or wrong-audience assertion is rejected, not
downgraded. And localhost, with no Access in front, works exactly as it does today.

## 8. The one thing a domain is needed for

Everything above is built and tested without a domain, against a fixture edge. Two things require
the real thing, and both are the go-live gate in the runbook — not a blocker for building or merging
the verifier:

1. **End-to-end identity.** Log in at the hosted screen; confirm the real
   `Cf-Access-Jwt-Assertion` verifies against the live JWKS and maps to the right principal. This is
   also where a fixture/edge divergence (§3, I-008) would surface.
2. **The replay invariant that code cannot enforce** (2nd-round I-003). The origin must be reachable
   *only* through `cloudflared` — bound to `127.0.0.1:8000`, no public port, no reverse proxy on a
   routable interface, no host networking. A valid captured token sent straight to a reachable
   origin verifies; the signature is real and `exp` is the only bound. Nexus cannot check its own
   reachability, so this is a runbook checklist item verified at deploy: confirm the port is
   loopback-bound and the only inbound path is the tunnel. Turning Access on without confirming this
   leaves the replay hole open, which is why it is a gate, not a footnote.
