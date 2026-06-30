"""Nexus identity layer.

Binds an opaque bearer token to a fixed ``(tenant, clearance)`` server-side so callers
can never widen their own scope. Fail-closed by default. See
docs/superpowers/specs/2026-06-18-nexus-identity-layer-design.md.

The pure pieces (`clearance`, `principal`, `scope`) are dependency-free and are the exact
contract the A2A `policy.py` reuses (ADR-0001 / SPEC Phase 0).
"""

from .clearance import ORDER, LEVELS, floor_public, min_level, parse
from .config import PLACEHOLDER, AuthConfig
from .principal import Principal, gen_token, hash_token, resolve_principal
from .scope import effective_scope

__all__ = [
    "ORDER", "LEVELS", "floor_public", "min_level", "parse",
    "PLACEHOLDER", "AuthConfig",
    "Principal", "gen_token", "hash_token", "resolve_principal",
    "effective_scope",
]
