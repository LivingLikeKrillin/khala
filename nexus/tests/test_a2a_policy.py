"""A2A policy: server-side, default-deny identity (SPEC §5.5, invariants §6.2/§6.5).

One token ⇒ exactly one ``(tenant, clearance)``; an unknown/rotated token resolves to
nothing (default-deny); caller-asserted wider clearance is ignored (narrow-only). Built by
reusing the identity layer (``resolve_principal`` / ``effective_scope``).
"""

from __future__ import annotations

from nexus.a2a.config import A2AConfig
from nexus.a2a.policy import effective_scope, resolve_a2a_principal
from nexus.auth.principal import hash_token

_ANALYST = {
    "name": "ext-agent",
    "token_sha256": hash_token("a2a-good-token"),
    "tenant": "acme",
    "clearance": "INTERNAL",
}


def _cfg() -> A2AConfig:
    return A2AConfig(enabled=True, principals=[_ANALYST])


def test_valid_token_resolves_to_fixed_tenant_and_clearance():
    p = resolve_a2a_principal("a2a-good-token", _cfg())
    assert p is not None
    assert (p.tenant, p.clearance) == ("acme", "INTERNAL")


def test_unknown_token_is_default_denied():
    assert resolve_a2a_principal("not-a-real-token", _cfg()) is None


def test_missing_token_is_default_denied():
    assert resolve_a2a_principal(None, _cfg()) is None


def test_rotated_token_no_longer_resolves():
    # Token removed from config (rotation) ⇒ nothing resolves.
    empty = A2AConfig(enabled=True, principals=[])
    assert resolve_a2a_principal("a2a-good-token", empty) is None


def test_caller_cannot_widen_clearance_or_cross_tenant():
    p = resolve_a2a_principal("a2a-good-token", _cfg())
    # caller asks for a higher clearance + a foreign tenant -> clamped to its own
    tenant, clearance = effective_scope(p, requested_tenant="other", requested_clearance="RESTRICTED")
    assert (tenant, clearance) == ("acme", "INTERNAL")


def test_caller_may_narrow_clearance():
    p = resolve_a2a_principal("a2a-good-token", _cfg())
    tenant, clearance = effective_scope(p, requested_clearance="PUBLIC")
    assert (tenant, clearance) == ("acme", "PUBLIC")


def test_one_token_one_identity_no_set():
    # The same token always resolves to the same single identity, never a set.
    cfg = _cfg()
    a = resolve_a2a_principal("a2a-good-token", cfg)
    b = resolve_a2a_principal("a2a-good-token", cfg)
    assert (a.name, a.tenant, a.clearance) == (b.name, b.tenant, b.clearance)
