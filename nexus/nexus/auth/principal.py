"""Principal resolution: opaque bearer token -> fixed (tenant, clearance)."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from .clearance import floor_public


@dataclass(frozen=True)
class Principal:
    """An authenticated identity bound to exactly one tenant and clearance ceiling.

    ``capabilities`` is an optional, additive set of write/action grants (default: none →
    read-only). Phase 3 (SPEC-specledger-a2a-publish-phase3 §5.5) introduces the minimal
    ``ingest_governed`` capability so a read token can never write.
    """

    name: str
    tenant: str
    clearance: str  # always a valid clearance level
    capabilities: tuple[str, ...] = ()

    def has(self, capability: str) -> bool:
        """True if this principal carries ``capability`` (default-deny: empty ⇒ read-only)."""
        return capability in self.capabilities


def gen_token() -> str:
    """A fresh high-entropy bearer token. The scheme's security rests on this entropy."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """sha256 hex of a token, as stored in ``auth.principals[].token_sha256``."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def resolve_principal(token: str | None, principals: list[dict]) -> Principal | None:
    """Return the matching principal, or ``None`` if the token is missing/unknown.

    Compares ``sha256(token)`` against each configured ``token_sha256`` with a constant-time
    per-entry comparison. A principal's configured clearance is floored to a valid level so a
    misconfigured entry can never grant more than ``PUBLIC`` by accident.
    """
    if not token:
        return None
    digest = hash_token(token)
    for p in principals or []:
        stored = str(p.get("token_sha256", ""))
        if stored and hmac.compare_digest(digest, stored):
            return Principal(
                name=str(p.get("name", "unknown")),
                tenant=str(p.get("tenant", "default")),
                clearance=floor_public(p.get("clearance")),
                capabilities=tuple(str(c) for c in (p.get("capabilities") or [])),
            )
    return None
