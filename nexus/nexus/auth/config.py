"""Auth configuration: mode, allowed origins, principals, and the startup guard."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)

PLACEHOLDER = "REPLACE_ME"
_DEFAULT_ORIGINS = ["http://localhost:8000"]
_WEAK_DEV_TOKEN_DEFAULT = "nexus-local-dev"
_MIN_DEV_TOKEN_LEN = 24


@dataclass
class AuthConfig:
    mode: str = "enforced"  # "enforced" (default, fail-closed) | "permissive"
    allowed_origins: list[str] = field(default_factory=lambda: list(_DEFAULT_ORIGINS))
    principals: list[dict] = field(default_factory=list)
    dev_token_weak: bool = False

    @classmethod
    def from_dict(cls, cfg: dict | None) -> "AuthConfig":
        auth = (cfg or {}).get("auth") or {}
        mode = str(auth.get("mode", "enforced")).lower()
        # explicit, loud opt-out only
        if os.getenv("NEXUS_ALLOW_ANONYMOUS") == "1":
            mode = "permissive"
        if mode not in ("enforced", "permissive"):
            mode = "enforced"  # unknown -> fail closed
        origins = auth.get("allowed_origins") or list(_DEFAULT_ORIGINS)
        principals = list(auth.get("principals") or [])
        # 로컬 dev 온램프: NEXUS_DEV_TOKEN 이 있을 때만(=docker-compose.override.yml 의 로컬
        # 편의 레이어) INTERNAL local-dev principal 을 *추가* 주입한다. 리포 기본 config 는
        # enforced + principals:[] 그대로라 prod(override 미사용)는 영향 없음. 토큰은 env 로만
        # 들어오고 리포에 커밋되지 않는다. override 를 prod 에 쓰지 말 것.
        dev_token = os.getenv("NEXUS_DEV_TOKEN")
        dev_token_weak = False
        if dev_token:
            from .principal import hash_token
            # local-dev 는 **운영자 신원**이지 독자 신원이 아니다. 웹 콘솔(소스 관리)이
            # 자기 화면에서 403 으로 막히지 않도록 manage_sources 를 기본 부여한다.
            #
            # ⚠️ GET /auth/dev-token 은 이 토큰을 도달한 누구에게나 내준다. 터널 뒤에서는
            #    Cloudflare Access 통과자 누구나 소스를 관리하고 (미리보기를 거쳐) 문서를
            #    내릴 수 있다는 뜻이다. 그게 싫으면 config.yaml 에
            #        auth.local_dev_capabilities: []
            #    를 두어 로컬 UI 를 읽기 전용으로 만든다. 명시 설정된 principal 은
            #    여전히 default-deny 다.
            dev_caps = auth.get("local_dev_capabilities")
            if dev_caps is None:
                dev_caps = ["manage_sources"]
            principals.append({
                "name": "local-dev",
                "token_sha256": hash_token(dev_token),
                "tenant": "default",
                "clearance": "INTERNAL",
                "capabilities": list(dev_caps),
            })
            dev_token_weak = (
                dev_token == _WEAK_DEV_TOKEN_DEFAULT or len(dev_token) < _MIN_DEV_TOKEN_LEN
            )
        return cls(
            mode=mode,
            allowed_origins=list(origins),
            principals=principals,
            dev_token_weak=dev_token_weak,
        )

    @property
    def permissive(self) -> bool:
        return self.mode == "permissive"

    def validate_startup(self) -> None:
        """Refuse to boot in enforced mode while any principal still carries the placeholder.

        Prevents shipping a known credential: an operator must mint a real token before the
        server will serve in enforced mode.
        """
        # Weak-dev-token guard runs regardless of mode: the exposure risk (GET /auth/dev-token
        # handing an INTERNAL bearer to any caller) is independent of enforced/permissive.
        if self.dev_token_weak:
            msg = (
                "NEXUS_DEV_TOKEN is weak/default — GET /auth/dev-token serves an INTERNAL bearer "
                "to anyone who can reach it. Safe only on localhost. If exposing beyond localhost "
                "(tunnel/LAN), set a strong random NEXUS_DEV_TOKEN (`nexus auth gen-token`) AND gate "
                "at the edge (e.g. Cloudflare Access)."
            )
            if os.getenv("NEXUS_REQUIRE_STRONG_DEV_TOKEN") == "1":
                raise RuntimeError("auth: " + msg)
            logger.warning("weak_dev_token", detail=msg)

        if self.permissive:
            return
        for p in self.principals:
            if str(p.get("token_sha256", "")) == PLACEHOLDER:
                raise RuntimeError(
                    f"auth: principal {p.get('name', '?')!r} still uses the {PLACEHOLDER} "
                    "placeholder hash. Run `nexus auth gen-token | nexus auth hash-token` and "
                    "paste a real hash, or set auth.mode: permissive for local dev."
                )
