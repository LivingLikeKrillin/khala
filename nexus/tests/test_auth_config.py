"""AuthConfig parsing + the enforced-mode startup guard."""

from __future__ import annotations

import pytest

from nexus.auth import AuthConfig, PLACEHOLDER


def test_default_mode_is_enforced():
    cfg = AuthConfig.from_dict({})
    assert cfg.mode == "enforced"
    assert cfg.permissive is False
    assert cfg.principals == []


def test_permissive_via_config():
    cfg = AuthConfig.from_dict({"auth": {"mode": "permissive"}})
    assert cfg.permissive is True


def test_unknown_mode_fails_closed():
    cfg = AuthConfig.from_dict({"auth": {"mode": "wat"}})
    assert cfg.mode == "enforced"


def test_env_opt_out_forces_permissive(monkeypatch):
    monkeypatch.setenv("NEXUS_ALLOW_ANONYMOUS", "1")
    cfg = AuthConfig.from_dict({"auth": {"mode": "enforced"}})
    assert cfg.permissive is True


def test_default_allowed_origins():
    cfg = AuthConfig.from_dict({})
    assert cfg.allowed_origins == ["http://localhost:8000"]


def test_startup_refuses_placeholder_in_enforced():
    cfg = AuthConfig.from_dict(
        {"auth": {"principals": [{"name": "dev", "token_sha256": PLACEHOLDER}]}}
    )
    with pytest.raises(RuntimeError, match="placeholder"):
        cfg.validate_startup()


def test_startup_allows_placeholder_in_permissive():
    cfg = AuthConfig.from_dict(
        {"auth": {"mode": "permissive", "principals": [{"name": "dev", "token_sha256": PLACEHOLDER}]}}
    )
    cfg.validate_startup()  # no raise


def test_startup_ok_with_real_hash():
    cfg = AuthConfig.from_dict(
        {"auth": {"principals": [{"name": "p", "token_sha256": "abc123"}]}}
    )
    cfg.validate_startup()  # no raise


# ── SPEC-nexus-notion-source-console §4.7 ─────────────────────────────────────

def test_local_dev_principal_gets_manage_sources_by_default(monkeypatch):
    """웹 콘솔이 자기 화면에서 403 으로 막히면 안 된다."""
    monkeypatch.setenv("NEXUS_DEV_TOKEN", "x" * 40)
    from nexus.auth.config import AuthConfig
    cfg = AuthConfig.from_dict({"auth": {"mode": "enforced"}})
    dev = next(p for p in cfg.principals if p["name"] == "local-dev")
    assert dev["capabilities"] == ["manage_sources"]


def test_local_dev_capabilities_can_be_emptied_to_keep_the_ui_read_only(monkeypatch):
    """터널 뒤에서는 Access 통과자 누구나 소스를 지울 수 있다 — 끄는 스위치가 있어야 한다."""
    monkeypatch.setenv("NEXUS_DEV_TOKEN", "x" * 40)
    from nexus.auth.config import AuthConfig
    cfg = AuthConfig.from_dict({"auth": {"mode": "enforced", "local_dev_capabilities": []}})
    dev = next(p for p in cfg.principals if p["name"] == "local-dev")
    assert dev["capabilities"] == []


def test_configured_principals_keep_default_deny(monkeypatch):
    monkeypatch.delenv("NEXUS_DEV_TOKEN", raising=False)
    from nexus.auth.config import AuthConfig
    cfg = AuthConfig.from_dict({"auth": {"mode": "enforced", "principals": [
        {"name": "reader", "token_sha256": "a" * 64, "tenant": "default", "clearance": "INTERNAL"},
    ]}})
    assert cfg.principals[0].get("capabilities", []) == []
