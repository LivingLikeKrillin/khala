"""NEXUS_DEV_TOKEN 약함 가드: 약한 토큰이면 경고, strict 모드(NEXUS_REQUIRE_STRONG_DEV_TOKEN=1)면 부트 거부."""
import pytest

from nexus.auth.config import AuthConfig


def _cfg(monkeypatch, dev_token=None, strict=False):
    monkeypatch.delenv("NEXUS_DEV_TOKEN", raising=False)
    monkeypatch.delenv("NEXUS_REQUIRE_STRONG_DEV_TOKEN", raising=False)
    if dev_token is not None:
        monkeypatch.setenv("NEXUS_DEV_TOKEN", dev_token)
    if strict:
        monkeypatch.setenv("NEXUS_REQUIRE_STRONG_DEV_TOKEN", "1")
    return AuthConfig.from_dict({"auth": {"mode": "enforced", "principals": []}})


def test_no_dev_token_not_weak(monkeypatch):
    cfg = _cfg(monkeypatch, dev_token=None)
    assert cfg.dev_token_weak is False
    cfg.validate_startup()  # no raise


def test_default_weak_token_flagged(monkeypatch):
    cfg = _cfg(monkeypatch, dev_token="nexus-local-dev")
    assert cfg.dev_token_weak is True


def test_short_token_flagged(monkeypatch):
    cfg = _cfg(monkeypatch, dev_token="short")
    assert cfg.dev_token_weak is True


def test_strong_token_not_weak(monkeypatch):
    from nexus.auth import gen_token
    cfg = _cfg(monkeypatch, dev_token=gen_token())  # token_urlsafe(32) ≈ 43 chars
    assert cfg.dev_token_weak is False
    cfg.validate_startup()  # no raise


def test_weak_token_warns_but_boots_by_default(monkeypatch):
    cfg = _cfg(monkeypatch, dev_token="nexus-local-dev", strict=False)
    cfg.validate_startup()  # must NOT raise (frictionless local preserved)


def test_weak_token_refused_in_strict_mode(monkeypatch):
    cfg = _cfg(monkeypatch, dev_token="nexus-local-dev", strict=True)
    with pytest.raises(RuntimeError, match="NEXUS_DEV_TOKEN"):
        cfg.validate_startup()


def test_strong_token_ok_even_in_strict_mode(monkeypatch):
    from nexus.auth import gen_token
    cfg = _cfg(monkeypatch, dev_token=gen_token(), strict=True)
    cfg.validate_startup()  # no raise


def test_weak_token_refused_in_strict_mode_even_when_permissive(monkeypatch):
    monkeypatch.delenv("NEXUS_DEV_TOKEN", raising=False)
    monkeypatch.setenv("NEXUS_DEV_TOKEN", "nexus-local-dev")
    monkeypatch.setenv("NEXUS_REQUIRE_STRONG_DEV_TOKEN", "1")
    cfg = AuthConfig.from_dict({"auth": {"mode": "permissive", "principals": []}})
    assert cfg.permissive is True
    with pytest.raises(RuntimeError, match="NEXUS_DEV_TOKEN"):
        cfg.validate_startup()


def test_weak_token_emits_warning_event(monkeypatch):
    import structlog
    monkeypatch.delenv("NEXUS_DEV_TOKEN", raising=False)
    monkeypatch.delenv("NEXUS_REQUIRE_STRONG_DEV_TOKEN", raising=False)
    monkeypatch.setenv("NEXUS_DEV_TOKEN", "nexus-local-dev")
    cfg = AuthConfig.from_dict({"auth": {"mode": "enforced", "principals": []}})
    with structlog.testing.capture_logs() as logs:
        cfg.validate_startup()
    assert any(e.get("event") == "weak_dev_token" for e in logs)
