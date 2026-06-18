"""A2A policy (SPEC §5.5) — server-side, default-deny, narrow-only.

Phase 0 reuses the identity layer wholesale: ``resolve_principal`` maps one bearer token
to one fixed ``(tenant, clearance)`` (invariant §6.5), and ``effective_scope`` is the only
producer of the ``(tenant, clearance)`` that may reach ``hybrid_search`` / ``base_filter`` —
caller-supplied ``tenant`` / ``classification_max`` can only narrow, never widen. The A2A
path adds no new policy logic; it routes through the exact same clamp as HTTP/MCP.
"""

from __future__ import annotations

from nexus.auth.principal import Principal, resolve_principal
from nexus.auth.scope import effective_scope  # re-exported: the single narrow-only clamp

from nexus.a2a.config import A2AConfig

__all__ = ["resolve_a2a_principal", "effective_scope"]


def resolve_a2a_principal(token: str | None, cfg: A2AConfig) -> Principal | None:
    """Resolve a bearer token to its fixed principal, or ``None`` (default-deny).

    A missing/unknown/rotated token resolves to nothing — skill execution is then denied.
    """
    return resolve_principal(token, cfg.principals)
