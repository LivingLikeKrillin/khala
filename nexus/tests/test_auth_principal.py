"""Principal resolution from bearer tokens."""

from __future__ import annotations

from nexus.auth import principal as P


def _entry(token: str, **kw):
    e = {"token_sha256": P.hash_token(token), "name": "x", "tenant": "acme", "clearance": "INTERNAL"}
    e.update(kw)
    return e


def test_hash_token_is_sha256_hex():
    h = P.hash_token("hello")
    assert h == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_gen_token_is_high_entropy_and_unique():
    a, b = P.gen_token(), P.gen_token()
    assert a != b
    assert len(a) >= 32


def test_resolve_match():
    principals = [_entry("s3cret-token", name="analyst", tenant="acme", clearance="RESTRICTED")]
    p = P.resolve_principal("s3cret-token", principals)
    assert p == P.Principal(name="analyst", tenant="acme", clearance="RESTRICTED")


def test_resolve_unknown_token_returns_none():
    principals = [_entry("right")]
    assert P.resolve_principal("wrong", principals) is None


def test_resolve_empty_or_none_token_returns_none():
    principals = [_entry("right")]
    assert P.resolve_principal("", principals) is None
    assert P.resolve_principal(None, principals) is None


def test_resolve_no_principals_returns_none():
    assert P.resolve_principal("anything", []) is None
    assert P.resolve_principal("anything", None) is None


def test_malformed_config_entries_are_tolerated():
    principals = [{}, {"token_sha256": ""}, {"name": "no-hash"}, _entry("good", name="ok")]
    p = P.resolve_principal("good", principals)
    assert p is not None and p.name == "ok"


def test_principal_clearance_floored_to_valid_level():
    # a misconfigured clearance must not silently grant anything above PUBLIC
    principals = [_entry("t", clearance="OOPS")]
    p = P.resolve_principal("t", principals)
    assert p.clearance == "PUBLIC"
