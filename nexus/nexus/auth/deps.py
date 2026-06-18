"""FastAPI dependency: resolve the request's Principal (or 401 / anonymous)."""

from __future__ import annotations

from collections.abc import Callable

import structlog
from fastapi import Header, HTTPException

from .config import AuthConfig
from .principal import Principal, resolve_principal

log = structlog.get_logger(__name__)

# Permissive-mode identity: least privilege (PUBLIC), never INTERNAL.
ANONYMOUS = Principal(name="anonymous", tenant="default", clearance="PUBLIC")

_UNAUTH_DETAIL = (
    "authentication required; configure a bearer token "
    "(do NOT enable anonymous access on shared/production deployments)."
)


def extract_bearer(authorization: str | None) -> str | None:
    """Pull the token out of an ``Authorization: Bearer <token>`` header."""
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip() or None
    return None


def resolve_request_principal(authorization: str | None, cfg: AuthConfig) -> Principal:
    """Resolve a Principal, or raise 401 in enforced mode / fall back to anonymous in permissive."""
    token = extract_bearer(authorization)
    principal = resolve_principal(token, cfg.principals)
    if principal is not None:
        return principal
    if cfg.permissive:
        log.warning("auth_permissive_anonymous", reason="no valid token; serving PUBLIC scope")
        return ANONYMOUS
    raise HTTPException(status_code=401, detail=_UNAUTH_DETAIL)


def make_get_principal(cfg_provider: Callable[[], AuthConfig]):
    """Build a FastAPI dependency bound to a config provider (so tests/app can inject config)."""

    def get_principal(
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> Principal:
        return resolve_request_principal(authorization, cfg_provider())

    return get_principal
