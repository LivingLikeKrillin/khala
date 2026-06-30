"""A2A surface configuration (SPEC §8) — flag + Phase-0 single-token identity.

Off by default: ``NEXUS_A2A_ENABLED`` unset/false ⇒ the surface is never mounted. The
Phase-0 identity model is a single static bearer token mapped to exactly one
``(tenant, clearance)`` (invariant §6.5), reusing the identity layer's principal shape so
``resolve_principal`` / ``effective_scope`` apply unchanged.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from nexus.auth.clearance import floor_public
from nexus.auth.principal import hash_token

_DEFAULT_BASE_URL = "http://localhost:8000"
_TRUTHY = {"1", "true", "yes", "on"}


@dataclass
class A2AConfig:
    enabled: bool = False
    base_url: str = _DEFAULT_BASE_URL
    # Identity layer principal shape: {name, token_sha256, tenant, clearance}.
    principals: list[dict] = field(default_factory=list)
    # Extra CORS origins for external A2A callers (Phase 2). None ⇒ inherit the app's origins.
    allowed_origins: list[str] | None = None
    # Per-principal request budget per 60s window (SPEC §21). 0 ⇒ disabled (default).
    rate_limit_per_min: int = 0

    @classmethod
    def from_dict(cls, cfg: dict | None) -> "A2AConfig":
        """Build from config.yaml's ``a2a`` block, overlaid by env (SPEC §8).

        Enable precedence: ``NEXUS_A2A_ENABLED`` env (loud opt-in) OR ``a2a.enabled``.
        A ``NEXUS_A2A_TOKEN`` env (with ``NEXUS_A2A_TENANT`` / ``NEXUS_A2A_CLEARANCE``)
        contributes a single static principal; otherwise ``a2a.principals`` is used.
        """
        a2a = (cfg or {}).get("a2a") or {}

        enabled = bool(a2a.get("enabled", False))
        env_enabled = os.getenv("NEXUS_A2A_ENABLED")
        if env_enabled is not None:
            enabled = env_enabled.strip().lower() in _TRUTHY

        base_url = os.getenv("NEXUS_A2A_BASE_URL") or a2a.get("base_url") or _DEFAULT_BASE_URL

        principals = list(a2a.get("principals") or [])
        env_token = os.getenv("NEXUS_A2A_TOKEN")
        if env_token:
            principals = principals + [{
                "name": "a2a-static",
                "token_sha256": hash_token(env_token),
                "tenant": os.getenv("NEXUS_A2A_TENANT", "default"),
                "clearance": floor_public(os.getenv("NEXUS_A2A_CLEARANCE")),
            }]

        origins = a2a.get("allowed_origins")
        allowed_origins = list(origins) if origins else None

        rate_limit = int(a2a.get("rate_limit_per_min", 0) or 0)
        env_rate = os.getenv("NEXUS_A2A_RATE_LIMIT_PER_MIN")
        if env_rate is not None and env_rate.strip():
            rate_limit = int(env_rate)

        return cls(
            enabled=enabled,
            base_url=str(base_url).rstrip("/"),
            principals=principals,
            allowed_origins=allowed_origins,
            rate_limit_per_min=rate_limit,
        )


def resolve_a2a_cors_origins(auth_origins: list[str], cfg: A2AConfig) -> list[str]:
    """Effective CORS origins for the surface: the app's origins, plus any A2A-specific
    origins when A2A is enabled. Order-preserving, de-duplicated, never ``*`` (the surface
    can carry an Authorization header, so a wildcard origin is refused — parity with the app).
    """
    origins = list(auth_origins)
    if cfg.enabled and cfg.allowed_origins:
        for origin in cfg.allowed_origins:
            if origin and origin != "*" and origin not in origins:
                origins.append(origin)
    return origins
