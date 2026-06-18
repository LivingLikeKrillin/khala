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

        return cls(enabled=enabled, base_url=str(base_url).rstrip("/"), principals=principals)
