"""JWKS 캐시 — SPEC-nexus-access-jwt-auth §4.3.

키 회전 대응: 캐시하되 TTL 로 갱신하고, unknown kid 는 한 번 갱신 후 거부한다.
single-flight: 동시 unknown-kid 요청이 와도 JWKS 엔드포인트는 **최대 1회** 친다 — 안 그러면
공격자가 무작위 kid 로 Nexus 를 JWKS 엔드포인트에 대한 증폭기로 쓴다.
"""

from __future__ import annotations

import pytest

from nexus.auth.access_jwks import JwksCache


class Counter:
    """fetch 횟수를 세는 스파이. 회전 후 새 kid 를 노출할 수 있다."""

    def __init__(self, keys):
        self.calls = 0
        self._keys = keys

    def fetch(self):
        self.calls += 1
        return {"keys": list(self._keys)}


def _jwk(kid):
    return {"kty": "RSA", "kid": kid, "n": "x", "e": "AQAB"}


def test_first_lookup_fetches_and_caches():
    src = Counter([_jwk("k1")])
    cache = JwksCache(src.fetch, ttl_seconds=3600, min_refresh_seconds=60, now=lambda: 1000.0)

    assert (cache.get("k1"))["kid"] == "k1"
    assert (cache.get("k1"))["kid"] == "k1"
    assert src.calls == 1, "캐시 히트는 다시 fetch 하지 않는다"


def test_unknown_kid_triggers_one_refresh_then_rejects():
    src = Counter([_jwk("k1")])
    cache = JwksCache(src.fetch, ttl_seconds=3600, min_refresh_seconds=60, now=lambda: 1000.0)
    cache.get("k1")                       # 초기 로드 (fetch 1)

    assert cache.get("nope") is None       # unknown → 갱신 시도(fetch 2) 후 없음
    assert src.calls == 2


def test_rotation_is_picked_up_by_the_unknown_kid_refresh():
    """회전 직후: 새 kid 가 캐시에 없다 → 한 번 갱신하면 새 키가 보인다."""
    src = Counter([_jwk("k1")])
    t = [1000.0]
    cache = JwksCache(src.fetch, ttl_seconds=3600, min_refresh_seconds=60, now=lambda: t[0])
    cache.get("k1")

    src._keys.append(_jwk("k2"))                 # Cloudflare 가 새 키를 발행
    t[0] = 1100.0                                # min_refresh 지남
    assert (cache.get("k2"))["kid"] == "k2"


def test_repeated_unknown_kids_do_not_amplify():
    """무작위 unknown kid 를 퍼부어도, min_refresh 창 안에서는 최대 1회만 fetch."""
    src = Counter([_jwk("k1")])
    cache = JwksCache(src.fetch, ttl_seconds=3600, min_refresh_seconds=60, now=lambda: 1000.0)
    cache.get("k1")                        # fetch 1
    before = src.calls

    for i in range(50):
        assert cache.get(f"attack-{i}") is None
    assert src.calls - before == 1, "50개의 unknown kid 가 1회 갱신으로 흡수돼야 한다"


def test_concurrent_unknown_kids_are_single_flighted():
    """동시 요청도 최대 1회. 락 없는 구현이면 여기서 여러 번 친다."""
    import threading

    src = Counter([_jwk("k1")])
    cache = JwksCache(src.fetch, ttl_seconds=3600, min_refresh_seconds=60, now=lambda: 1000.0)
    cache.get("k1")
    before = src.calls

    threads = [threading.Thread(target=lambda i=i: cache.get(f"x-{i}")) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert src.calls - before == 1


def test_ttl_expiry_forces_a_refresh_even_for_a_known_kid():
    src = Counter([_jwk("k1")])
    t = [1000.0]
    cache = JwksCache(src.fetch, ttl_seconds=100, min_refresh_seconds=10, now=lambda: t[0])
    cache.get("k1")                        # fetch 1
    t[0] = 1200.0                                # TTL(100s) 초과
    cache.get("k1")                        # 신선도 잃음 → fetch 2
    assert src.calls == 2


def test_an_empty_cache_that_cannot_fetch_raises():
    """JWKS 불통 + 캐시 비어 있음 → 열어주지 않는다. fail closed."""
    def boom():
        raise ConnectionError("jwks unreachable")

    cache = JwksCache(boom, ttl_seconds=3600, min_refresh_seconds=60, now=lambda: 1000.0)
    with pytest.raises(ConnectionError):
        cache.get("k1")
