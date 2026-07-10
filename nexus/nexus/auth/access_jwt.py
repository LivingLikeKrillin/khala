"""Cloudflare Access JWT 검증 — SPEC-nexus-access-jwt-auth §4.1~§4.2.

순수 함수. DB 도 네트워크도 없다(JWKS 는 인자로 받는다). PyJWT 없이 `cryptography` 만 쓴다 —
의존성을 늘리지 않고, 무엇을 검증하는지 한눈에 보이게.

이 파일의 전부는 두 문장이다:
  · 키 재료는 **오직 JWKS 에서**. 토큰이 실어 보내는 jwk/jku/alg 는 무시한다.
  · alg 는 **RS256 고정**. alg:none / alg:HS256(공개키를 HMAC 비밀로) 우회를 원천 차단.
"""

from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa


class AccessJwtError(Exception):
    """Access JWT 가 유효하지 않다. 호출자는 이걸 401 로 바꾼다 — 절대 익명으로 강등하지 않는다."""


@dataclass(frozen=True)
class VerifiedIdentity:
    email: str
    subject: str = ""


def _b64url_decode(seg: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4))
    except Exception as e:  # noqa: BLE001
        raise AccessJwtError("malformed base64url segment") from e


def _key_from_jwks(jwks: dict, kid: str) -> rsa.RSAPublicKey:
    """JWKS 에서 kid 로 공개키를 고른다. **키 재료는 여기서만 온다** — 토큰에서 절대 아님."""
    for k in jwks.get("keys", []):
        if k.get("kid") == kid:
            if k.get("kty") != "RSA":
                raise AccessJwtError(f"unsupported key type: {k.get('kty')}")
            n = int.from_bytes(_b64url_decode(k["n"]), "big")
            e = int.from_bytes(_b64url_decode(k["e"]), "big")
            return rsa.RSAPublicNumbers(e, n).public_key()
    raise AccessJwtError(f"no key for kid={kid!r}")


def verify_access_jwt(
    token: str,
    *,
    issuer: str,
    audience: str,
    jwks: dict,
    leeway_seconds: int = 60,
    now: float | None = None,
) -> VerifiedIdentity:
    """검증하고 신원을 돌려준다. 어떤 실패도 AccessJwtError. 시간은 주입 가능(테스트).

    절차(SPEC §4.1):
      1. 세 조각으로 나눈다.
      2. header 에서 kid 만 읽는다. alg 는 읽지 않는다 — 우리가 RS256 으로 고정한다.
      3. JWKS 에서 kid 로 공개키를 고른다.
      4. RS256 으로 `header.payload` 서명을 검증한다.
      5. iss(설정값) · aud · exp · email 을 확인한다.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise AccessJwtError("token must have three segments")
    h_seg, p_seg, s_seg = parts
    if not s_seg:
        raise AccessJwtError("empty signature")  # alg:none 은 여기서 죽는다

    try:
        header = json.loads(_b64url_decode(h_seg))
        payload = json.loads(_b64url_decode(p_seg))
    except (json.JSONDecodeError, AccessJwtError) as e:
        raise AccessJwtError("undecodable header/payload") from e
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise AccessJwtError("header/payload not objects")

    kid = header.get("kid")
    if not kid:
        raise AccessJwtError("no kid in header")

    # alg 는 토큰에서 읽지 않는다. 우리가 RS256 을 강제한다 — alg-confusion 차단.
    # 공개키를 JWKS 에서만 가져와 RS256 으로 검증하므로, 토큰이 alg:HS256 이나 내장 jwk 를
    # 실어 보내도 그 값들은 애초에 쳐다보지 않는다.
    public_key = _key_from_jwks(jwks, kid)

    signature = _b64url_decode(s_seg)
    signing_input = f"{h_seg}.{p_seg}".encode()
    try:
        public_key.verify(signature, signing_input, padding.PKCS1v15(), hashes.SHA256())
    except InvalidSignature as e:
        raise AccessJwtError("signature verification failed") from e

    # ── 클레임 (서명이 진짜여도, 아래 중 하나만 틀리면 거부) ──
    if payload.get("iss") != issuer:
        # 설정된 issuer 로만 판정한다. 토큰의 iss 를 믿고 그 JWKS 를 받으러 가지 않는다.
        raise AccessJwtError("issuer mismatch")

    aud = payload.get("aud")
    aud_ok = (aud == audience) or (isinstance(aud, list) and audience in aud)
    if not aud_ok:
        # 같은 팀의 다른 앱 토큰은 서명이 진짜다. 이 검사만이 그걸 막는다.
        raise AccessJwtError("audience mismatch")

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        raise AccessJwtError("no exp claim")
    if (now if now is not None else time.time()) > exp + leeway_seconds:
        raise AccessJwtError("token expired")

    email = payload.get("email")
    if not email or not isinstance(email, str):
        # email 로 principal 을 고르는데 email 이 없으면 고를 수 없다 → 401, 기본값 아님.
        raise AccessJwtError("no email claim")

    return VerifiedIdentity(email=email, subject=str(payload.get("sub", "")))
