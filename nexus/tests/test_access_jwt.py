"""Cloudflare Access JWT 검증기 — SPEC-nexus-access-jwt-auth §4.1~§4.2, §6.

자체 RSA 키쌍을 만들고, 자체 JWKS 를 세우고, 자체 토큰에 서명한다. Cloudflare 를 픽스처로
대체한다 — 도메인도 네트워크도 없다. 이 하네스는 SPEC 을 탐색할 때 쓴 바로 그 구성이다.

여기서 고정하는 불변식(전부 SPEC §4.2·§6):
  · 키 재료는 오직 JWKS 에서. alg 는 RS256 고정 — alg:none / alg:HS256 우회를 막는다.
  · iss 는 설정값과 대조(토큰에서 안 읽음). aud 필수. exp 필수. email 필수.
  · 실패는 전부 AccessJwtError. 절대 '익명'으로 강등되지 않는다.
"""

from __future__ import annotations

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from nexus.auth.access_jwt import (
    AccessJwtError,
    VerifiedIdentity,
    verify_access_jwt,
)

_ISS = "https://pfplay.cloudflareaccess.com"
_AUD = "nexus-app-tag-7f3c9e2b"


def _b64(d: bytes) -> str:
    return base64.urlsafe_b64encode(d).rstrip(b"=").decode()


def _int_b64(x: int) -> str:
    return _b64(x.to_bytes((x.bit_length() + 7) // 8, "big"))


class FakeEdge:
    """Cloudflare 대역. 키쌍을 쥐고, JWKS 를 내놓고, 토큰에 서명한다."""

    def __init__(self, kid: str = "cf-key-1"):
        self.kid = kid
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def jwks(self) -> dict:
        n = self.key.public_key().public_numbers()
        return {"keys": [{"kty": "RSA", "kid": self.kid, "alg": "RS256", "use": "sig",
                          "n": _int_b64(n.n), "e": _int_b64(n.e)}]}

    def mint(self, *, alg="RS256", kid=None, iss=_ISS, aud=_AUD, email="eisen@pfplay.com",
             exp=None, extra_header=None, sign_key=None) -> str:
        header = {"alg": alg, "kid": kid or self.kid, "typ": "JWT", **(extra_header or {})}
        payload = {"iss": iss, "aud": aud, "exp": exp if exp is not None else int(time.time()) + 600}
        if email is not None:
            payload["email"] = email
        si = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(payload).encode())}"
        signer = sign_key or self.key
        if alg == "none":
            return f"{si}."
        if alg == "HS256":
            import hmac
            # 공격: 공개키를 HMAC 비밀로 써서 위조 (alg-confusion)
            pub = self.key.public_key().public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
            mac = hmac.new(pub, si.encode(), __import__("hashlib").sha256).digest()
            return f"{si}.{_b64(mac)}"
        sig = signer.sign(si.encode(), padding.PKCS1v15(), hashes.SHA256())
        return f"{si}.{_b64(sig)}"


@pytest.fixture
def edge():
    return FakeEdge()


def _verify(token, edge, **over):
    kw = {"issuer": _ISS, "audience": _AUD, "jwks": edge.jwks()}
    kw.update(over)
    return verify_access_jwt(token, **kw)


# ── 정상 ──────────────────────────────────────────────────────────────────────

def test_a_valid_token_yields_the_identity(edge):
    ident = _verify(edge.mint(), edge)
    assert isinstance(ident, VerifiedIdentity)
    assert ident.email == "eisen@pfplay.com"


# ── 위조: 이 설계가 막으려는 바로 그 공격. 첫 테스트. ─────────────────────────

def test_a_token_signed_by_a_different_key_is_rejected(edge):
    """kid 는 진짜와 같게 베끼되, 공격자 키로 서명한다."""
    attacker = FakeEdge(kid=edge.kid)          # 같은 kid
    forged = attacker.mint()                    # 공격자 키로 서명
    with pytest.raises(AccessJwtError):
        _verify(forged, edge)                   # 검증은 edge(진짜)의 JWKS 로


def test_header_supplied_key_material_and_alg_are_ignored(edge):
    """토큰이 alg:none / alg:HS256 / 내장 jwk 를 실어도 우회 못 한다 (alg-confusion)."""
    with pytest.raises(AccessJwtError):
        _verify(edge.mint(alg="none"), edge)
    with pytest.raises(AccessJwtError):
        _verify(edge.mint(alg="HS256"), edge)
    with pytest.raises(AccessJwtError):
        _verify(edge.mint(extra_header={"jwk": edge.jwks()["keys"][0]}, alg="none"), edge)


# ── 클레임 ────────────────────────────────────────────────────────────────────

def test_wrong_audience_is_rejected_even_with_a_real_signature(edge):
    """같은 팀의 다른 앱 토큰 — 서명은 진짜다. aud 만이 이걸 막는다."""
    with pytest.raises(AccessJwtError):
        _verify(edge.mint(aud="some-other-app"), edge)


def test_an_expired_token_is_rejected(edge):
    # leeway(60s)를 넘겨 만료 — 시계 오차 허용치 안이면 통과하는 게 정상이므로 그 바깥을 쓴다.
    with pytest.raises(AccessJwtError):
        _verify(edge.mint(exp=int(time.time()) - 3600), edge)


def test_a_token_within_the_clock_skew_leeway_still_passes(edge):
    """방금 만료된 토큰은 시계 오차일 수 있다 — leeway 안이면 받는다."""
    ident = _verify(edge.mint(exp=int(time.time()) - 5), edge)
    assert ident.email == "eisen@pfplay.com"


def test_wrong_issuer_is_rejected(edge):
    with pytest.raises(AccessJwtError):
        _verify(edge.mint(iss="https://evil.example.com"), edge)


def test_the_configured_issuer_wins_not_the_token_claim(edge):
    """토큰이 자기 iss 를 뭐라 적든, 검증은 설정된 issuer 로만 판정한다."""
    # 설정 issuer 를 다른 값으로 주면, 토큰의 iss(_ISS)가 맞아도 거부되어야 한다
    with pytest.raises(AccessJwtError):
        _verify(edge.mint(), edge, issuer="https://different.cloudflareaccess.com")


def test_a_token_without_an_email_claim_is_rejected_not_defaulted(edge):
    """서명은 유효하지만 email 이 없다 → 401. 기본 principal 로 흘리지 않는다."""
    with pytest.raises(AccessJwtError):
        _verify(edge.mint(email=None), edge)
    with pytest.raises(AccessJwtError):
        _verify(edge.mint(email=""), edge)


def test_an_unknown_kid_is_rejected(edge):
    with pytest.raises(AccessJwtError):
        _verify(edge.mint(kid="no-such-key"), edge)


# ── 형식 오류 ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", ["", "not-a-jwt", "only.two", "a.b.c.d", "...."])
def test_malformed_tokens_are_rejected(edge, bad):
    with pytest.raises(AccessJwtError):
        _verify(bad, edge)


def test_a_tampered_payload_breaks_verification(edge):
    tok = edge.mint()
    h, p, s = tok.split(".")
    bad_payload = _b64(json.dumps({"iss": _ISS, "aud": _AUD, "email": "attacker@pfplay.com",
                                   "exp": int(time.time()) + 600}).encode())
    with pytest.raises(AccessJwtError):
        _verify(f"{h}.{bad_payload}.{s}", edge)
