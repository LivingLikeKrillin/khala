"""JWKS 캐시 — SPEC-nexus-access-jwt-auth §4.3.

Cloudflare 는 서명키를 회전하고, 새 키와 옛 키를 서로 다른 kid 로 함께 게시한다. 그래서:
  · 캐시하되 TTL 로 신선도를 잃으면 갱신.
  · unknown kid 는 회전 직후일 수 있으니 **한 번** 갱신하고, 그래도 없으면 거부.
  · single-flight: min_refresh 창 안에서는, 동시든 순차든, 최대 1회만 fetch.
    없으면 무작위 kid 를 퍼붓는 공격자가 Nexus 를 JWKS 엔드포인트 증폭기로 쓴다.
  · fetch 가 실패하고 캐시가 비어 있으면 열어주지 않는다(fail closed) — 예외를 그대로 올린다.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class JwksCache:
    def __init__(
        self,
        fetch: Callable[[], dict],
        *,
        ttl_seconds: int = 3600,
        min_refresh_seconds: int = 60,
        now: Callable[[], float] | None = None,
    ):
        self._fetch = fetch
        self._ttl = ttl_seconds
        self._min_refresh = min_refresh_seconds
        self._now = now or time.time
        self._keys: dict[str, dict] = {}
        self._fetched_at: float | None = None
        # unknown-kid 때문에 갱신한 마지막 시각. TTL 갱신과 별개로 이 창이 증폭을 막는다.
        self._unknown_refresh_at: float | None = None
        self._lock = threading.Lock()

    def _fresh(self) -> bool:
        return self._fetched_at is not None and (self._now() - self._fetched_at) < self._ttl

    def _refresh(self) -> None:
        # fetch 실패 + 캐시 비어 있음 → 예외를 삼키지 않는다(fail closed).
        data = self._fetch()
        self._keys = {k["kid"]: k for k in data.get("keys", []) if k.get("kid")}
        self._fetched_at = self._now()

    def get(self, kid: str) -> dict | None:
        """kid 로 JWK 를 돌려준다. 없으면 (조건부) 한 번 갱신. 그래도 없으면 None.

        · 초기이거나 TTL 로 신선도를 잃었으면 무조건 갱신.
        · kid 만 없으면, unknown 때문에 마지막으로 갱신한 이후 min_refresh 를 지났을 때만 갱신.
          이게 무작위 kid 증폭을 막는 바닥이다.

        동기다: FastAPI 의존성(resolve_request_principal)이 동기이고, fetch 는 짧은 HTTP 호출.
        """
        if kid in self._keys and self._fresh():
            return self._keys[kid]

        with self._lock:
            # 락 대기 중 다른 요청이 이미 채웠을 수 있다 — 다시 본다(single-flight).
            if kid in self._keys and self._fresh():
                return self._keys[kid]

            now = self._now()
            if self._fetched_at is None or not self._fresh():
                self._refresh()                          # 초기/만료: 무조건
            elif kid not in self._keys and (
                self._unknown_refresh_at is None
                or (now - self._unknown_refresh_at) >= self._min_refresh
            ):
                self._refresh()                          # unknown: 창을 지났을 때만 한 번
                self._unknown_refresh_at = now

            return self._keys.get(kid)
