"""Access JWT → principal 매핑, 그리고 검증기와 auth 파이프라인의 결합 — SPEC §4.1·§4.4·§4.5.

resolve_request_principal 이 Cf-Access-Jwt-Assertion 헤더를 검증하고 email 로 principal 을
고른다. 실패는 401, 절대 익명 강등 아님. Access 가 설정되면 공유 dev-token 은 꺼진다.
"""

from __future__ import annotations

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import HTTPException

from nexus.auth.config import AuthConfig
from nexus.auth.deps import resolve_request_principal

_ISS = "https://example-team.cloudflareaccess.com"
_AUD = "nexus-app-tag"


def _b64(d):
    return base64.urlsafe_b64encode(d).rstrip(b"=").decode()


def _int_b64(x):
    return _b64(x.to_bytes((x.bit_length() + 7) // 8, "big"))


class FakeEdge:
    def __init__(self, kid="cf-key-1"):
        self.kid = kid
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def jwks(self):
        n = self.key.public_key().public_numbers()
        return {"keys": [{"kty": "RSA", "kid": self.kid, "alg": "RS256",
                          "n": _int_b64(n.n), "e": _int_b64(n.e)}]}

    def mint(self, email="alice@example.com", aud=_AUD, iss=_ISS):
        h = {"alg": "RS256", "kid": self.kid, "typ": "JWT"}
        p = {"iss": iss, "aud": aud, "email": email, "exp": int(time.time()) + 600}
        si = f"{_b64(json.dumps(h).encode())}.{_b64(json.dumps(p).encode())}"
        sig = self.key.sign(si.encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{si}.{_b64(sig)}"


@pytest.fixture
def edge():
    return FakeEdge()


def _cfg(edge, identities=None, default_clearance="PUBLIC", monkeypatch=None):
    """Access 를 설정한 AuthConfig. JWKS 는 fetch 를 edge 로 스텁."""
    raw = {"auth": {"mode": "enforced", "access": {
        "issuer": _ISS, "aud": _AUD, "default_identity": {"clearance": default_clearance},
        "identities": identities or {},
    }}}
    cfg = AuthConfig.from_dict(raw)
    # 네트워크 대신 edge.jwks() 를 준다.
    cfg.access.set_jwks_source(edge.jwks)
    return cfg


def _resolve(edge, cfg, token=None, bearer=None):
    return resolve_request_principal(bearer, cfg, access_assertion=token)


# ── 매핑 ──────────────────────────────────────────────────────────────────────

def test_a_mapped_email_becomes_its_principal(edge):
    cfg = _cfg(edge, identities={
        "alice@example.com": {"capabilities": ["manage_sources", "manage_documents"],
                             "clearance": "INTERNAL"}})
    p = _resolve(edge, cfg, token=edge.mint())
    assert p.name == "alice@example.com"
    assert p.has("manage_documents")


def test_an_unmapped_email_gets_the_default_identity_with_zero_capabilities(edge):
    cfg = _cfg(edge, identities={}, default_clearance="PUBLIC")
    p = _resolve(edge, cfg, token=edge.mint(email="stranger@example.com"))
    assert p.name == "stranger@example.com"
    assert p.capabilities == ()               # 파괴적 행위 불가
    assert p.clearance == "PUBLIC"            # INTERNAL 하드코딩 아님


def test_the_default_clearance_is_the_operators_choice(edge):
    cfg = _cfg(edge, default_clearance="INTERNAL")
    p = _resolve(edge, cfg, token=edge.mint(email="stranger@example.com"))
    assert p.clearance == "INTERNAL" and p.capabilities == ()


# ── 검증 실패는 401, 익명 아님 ────────────────────────────────────────────────

def test_a_forged_assertion_is_401_not_anonymous(edge):
    attacker = FakeEdge(kid=edge.kid)
    cfg = _cfg(edge)
    with pytest.raises(HTTPException) as e:
        _resolve(edge, cfg, token=attacker.mint())
    assert e.value.status_code == 401


def test_wrong_audience_is_401(edge):
    cfg = _cfg(edge)
    with pytest.raises(HTTPException) as e:
        _resolve(edge, cfg, token=edge.mint(aud="other-app"))
    assert e.value.status_code == 401


def test_no_email_claim_is_401_not_the_default_identity(edge):
    cfg = _cfg(edge, default_clearance="PUBLIC")
    with pytest.raises(HTTPException) as e:
        _resolve(edge, cfg, token=edge.mint(email=""))
    assert e.value.status_code == 401


# ── 헤더 없으면 기존 경로 ─────────────────────────────────────────────────────

def test_no_access_header_falls_through_to_bearer(edge, monkeypatch):
    """Access 헤더가 없으면 기존 bearer 경로. Access 는 가산적이다."""
    monkeypatch.setenv("NEXUS_DEV_TOKEN", "x" * 40)
    raw = {"auth": {"mode": "enforced"}}          # access 미설정
    cfg = AuthConfig.from_dict(raw)
    p = resolve_request_principal("Bearer " + "x" * 40, cfg, access_assertion=None)
    assert p.name == "local-dev"


# ── §4.5 Access 가 설정되면 dev-token 은 꺼진다 ────────────────────────────────

def test_dev_token_principal_is_off_when_access_is_configured(edge, monkeypatch):
    """공유 dev-token 과 Access 신원이 동시에 돌지 않는다. Access 가 문이면 공유 열쇠는 끈다."""
    monkeypatch.setenv("NEXUS_DEV_TOKEN", "x" * 40)
    raw = {"auth": {"mode": "enforced", "access": {"issuer": _ISS, "aud": _AUD}}}
    cfg = AuthConfig.from_dict(raw)
    names = [p["name"] for p in cfg.principals]
    assert "local-dev" not in names


def test_dev_token_principal_stays_without_access(monkeypatch):
    monkeypatch.setenv("NEXUS_DEV_TOKEN", "x" * 40)
    cfg = AuthConfig.from_dict({"auth": {"mode": "enforced"}})
    assert "local-dev" in [p["name"] for p in cfg.principals]


def test_access_section_without_issuer_or_aud_is_a_config_error():
    with pytest.raises(ValueError, match="issuer"):
        AuthConfig.from_dict({"auth": {"access": {"aud": "x"}}})
