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


def _principal_from_access(assertion: str, cfg: AuthConfig) -> Principal:
    """Cf-Access-Jwt-Assertion → Principal, 또는 401. SPEC-nexus-access-jwt-auth §4.1·§4.4.

    검증 실패는 401 이고, 절대 익명으로 강등하지 않는다 — Access 헤더를 내민 요청은 그 신원으로
    판정해 달라는 것이고, 깨진 assertion 은 거부된 신원이지 익명이 아니다.
    """
    from .access_jwt import AccessJwtError, verify_access_jwt

    access = cfg.access
    header = _decode_kid(assertion)      # kid 를 먼저 뽑아 JWKS 에서 키를 고른다
    try:
        cache = access.cache()
        jwk = cache.get(header) if header else None
        if jwk is None:
            raise AccessJwtError(f"no key for kid={header!r}")
        ident = verify_access_jwt(
            assertion, issuer=access.issuer, audience=access.aud, jwks={"keys": [jwk]})
    except AccessJwtError as e:
        # 토큰 값·서명은 메시지에 담지 않는다(payload 는 읽히므로 자격증명이다).
        raise HTTPException(status_code=401, detail=f"access_jwt_invalid: {e}") from e
    except Exception as e:  # JWKS 불통 등 — 열어주지 않는다(fail closed).
        raise HTTPException(status_code=503, detail="access_jwks_unavailable") from e

    spec = access.identities.get(ident.email)
    if spec is not None:
        return Principal(
            name=ident.email, tenant="default",
            clearance=str(spec.get("clearance", "INTERNAL")),
            capabilities=tuple(spec.get("capabilities") or ()))
    # 매핑에 없지만 Access 는 통과 — 기본 신원: capabilities 는 항상 비운다(파괴적 행위 불가).
    return Principal(
        name=ident.email, tenant="default",
        clearance=access.default_clearance, capabilities=())


def _decode_kid(assertion: str) -> str | None:
    import base64
    import json

    parts = assertion.split(".")
    if len(parts) != 3:
        return None
    try:
        seg = parts[0]
        header = json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))
        return header.get("kid")
    except Exception:  # noqa: BLE001
        return None


def resolve_request_principal(
    authorization: str | None,
    cfg: AuthConfig,
    *,
    access_assertion: str | None = None,
) -> Principal:
    """Resolve a Principal, or raise 401 in enforced mode / fall back to anonymous in permissive.

    Access 헤더가 있고 Access 가 설정돼 있으면 그것으로 판정한다(가산적: 헤더가 없으면 기존 경로).
    """
    if access_assertion and cfg.access is not None:
        return _principal_from_access(access_assertion, cfg)

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
        access_assertion: str | None = Header(default=None, alias="Cf-Access-Jwt-Assertion"),
    ) -> Principal:
        return resolve_request_principal(
            authorization, cfg_provider(), access_assertion=access_assertion)

    return get_principal
