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
