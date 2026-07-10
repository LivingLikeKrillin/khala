"""Cloudflare Access 설정 — SPEC-nexus-access-jwt-auth §4.4·§4.5.

`auth.access` 가 있으면 Nexus 는 자신이 Access 뒤에 있다고 선언한 것이다(설정이 진실의 출처;
Nexus 는 자기 앞에 터널이 있는지 스스로 감지할 수 없다). 그러면:
  · Cf-Access-Jwt-Assertion 을 검증하고 email 로 principal 을 고른다.
  · 공유 dev-token 경로는 꺼진다(config.py 가 issuer 설정 시 local-dev 를 안 넣는다).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from .access_jwks import JwksCache


@dataclass
class AccessConfig:
    issuer: str
    aud: str
    #: email → {capabilities, clearance}
    identities: dict[str, dict] = field(default_factory=dict)
    #: 매핑에 없는(하지만 Access 는 통과한) email 의 기본 신원. capabilities 는 항상 비운다.
    default_clearance: str = "PUBLIC"
    jwks_ttl_seconds: int = 3600
    min_refresh_seconds: int = 60

    _cache: JwksCache | None = field(default=None, repr=False, compare=False)

    @classmethod
    def from_auth(cls, auth: dict) -> "AccessConfig | None":
        acc = auth.get("access")
        if not acc:
            return None
        issuer = acc.get("issuer")
        aud = acc.get("aud")
        if not issuer or not aud:
            # access 섹션이 있는데 issuer/aud 가 없으면 설정 오류 — 조용히 넘어가지 않는다.
            raise ValueError("auth.access requires both 'issuer' and 'aud'")
        default = (acc.get("default_identity") or {})
        return cls(
            issuer=issuer.rstrip("/"),
            aud=aud,
            identities=dict(acc.get("identities") or {}),
            default_clearance=str(default.get("clearance", "PUBLIC")),
            jwks_ttl_seconds=int(acc.get("jwks_ttl_seconds", 3600)),
            min_refresh_seconds=int(acc.get("min_refresh_seconds", 60)),
        )

    @property
    def jwks_url(self) -> str:
        # 토큰의 iss 가 아니라 **설정된** issuer 로부터 유도한다.
        return f"{self.issuer}/cdn-cgi/access/certs"

    def set_jwks_source(self, fetch: Callable[[], dict]) -> None:
        """JWKS fetch 함수를 주입해 캐시를 만든다(테스트는 네트워크 대신 픽스처를 준다)."""
        self._cache = JwksCache(
            fetch, ttl_seconds=self.jwks_ttl_seconds,
            min_refresh_seconds=self.min_refresh_seconds)

    def cache(self) -> JwksCache:
        if self._cache is None:
            import httpx

            def _http_fetch() -> dict:
                return httpx.get(self.jwks_url, timeout=5.0).raise_for_status().json()

            self.set_jwks_source(_http_fetch)
        return self._cache
