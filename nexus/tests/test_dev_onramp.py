"""로컬 dev 웹 온램프: NEXUS_DEV_TOKEN 가 있을 때만 local-dev principal 자동 주입 + 토큰 노출.

목적: 신규 `task up`(override 가 NEXUS_DEV_TOKEN 주입) 시 웹 검색이 401 없이 동작.
prod(override 미사용 → env 없음)는 enforced + principals 그대로 — 보안 기본값 불변.
"""

from __future__ import annotations

from nexus.auth.config import AuthConfig
from nexus.auth.principal import resolve_principal


def test_dev_token_env_injects_local_dev_principal(monkeypatch):
    monkeypatch.setenv("NEXUS_DEV_TOKEN", "local-secret")
    cfg = AuthConfig.from_dict({})  # repo 기본: principals 없음
    p = resolve_principal("local-secret", cfg.principals)
    assert p is not None
    assert p.name == "local-dev"
    assert p.tenant == "default"
    assert p.clearance == "INTERNAL"  # INTERNAL 코퍼스(노션 적재) 읽기 가능


def test_no_dev_principal_without_env(monkeypatch):
    monkeypatch.delenv("NEXUS_DEV_TOKEN", raising=False)
    cfg = AuthConfig.from_dict({})
    assert cfg.principals == []
    assert resolve_principal("anything", cfg.principals) is None


def test_empty_dev_token_env_is_ignored(monkeypatch):
    monkeypatch.setenv("NEXUS_DEV_TOKEN", "")
    cfg = AuthConfig.from_dict({})
    assert cfg.principals == []


def test_dev_principal_is_additive_to_configured(monkeypatch):
    monkeypatch.setenv("NEXUS_DEV_TOKEN", "local-secret")
    cfg = AuthConfig.from_dict(
        {"auth": {"principals": [{"name": "ops", "token_sha256": "deadbeef",
                                  "tenant": "default", "clearance": "INTERNAL"}]}}
    )
    names = {p.get("name") for p in cfg.principals}
    assert names == {"ops", "local-dev"}  # 기존 principal 보존 + dev 추가


def test_dev_token_payload_reflects_env(monkeypatch):
    from nexus.api import _dev_token
    monkeypatch.setenv("NEXUS_DEV_TOKEN", "local-secret")
    assert _dev_token() == "local-secret"
    monkeypatch.delenv("NEXUS_DEV_TOKEN", raising=False)
    assert _dev_token() is None
    monkeypatch.setenv("NEXUS_DEV_TOKEN", "")
    assert _dev_token() is None
