"""effective_scope — the narrow-only clamp."""

from __future__ import annotations

from nexus.auth import Principal, effective_scope


def test_clearance_never_widens():
    internal = Principal("a", "acme", "INTERNAL")
    # asking for RESTRICTED with an INTERNAL ceiling -> INTERNAL
    assert effective_scope(internal, None, "RESTRICTED") == ("acme", "INTERNAL")


def test_clearance_narrows_when_requested_lower():
    restricted = Principal("a", "acme", "RESTRICTED")
    assert effective_scope(restricted, None, "PUBLIC") == ("acme", "PUBLIC")


def test_none_request_keeps_principal_ceiling():
    p = Principal("a", "acme", "INTERNAL")
    assert effective_scope(p, None, None) == ("acme", "INTERNAL")


def test_typo_clearance_floors_to_public_not_up():
    restricted = Principal("a", "acme", "RESTRICTED")
    # a typo must NOT clamp up to the principal's RESTRICTED
    assert effective_scope(restricted, None, "INTERNL") == ("acme", "PUBLIC")


def test_requested_tenant_is_ignored():
    p = Principal("a", "acme", "INTERNAL")
    # confused-deputy: asking for another tenant yields the principal's tenant
    assert effective_scope(p, "other-corp", "RESTRICTED") == ("acme", "INTERNAL")


def test_public_principal_stays_public():
    anon = Principal("anonymous", "default", "PUBLIC")
    assert effective_scope(anon, "x", "RESTRICTED") == ("default", "PUBLIC")
