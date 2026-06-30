"""Auth configuration: mode, allowed origins, principals, and the startup guard."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

PLACEHOLDER = "REPLACE_ME"
_DEFAULT_ORIGINS = ["http://localhost:8000"]


@dataclass
class AuthConfig:
    mode: str = "enforced"  # "enforced" (default, fail-closed) | "permissive"
    allowed_origins: list[str] = field(default_factory=lambda: list(_DEFAULT_ORIGINS))
    principals: list[dict] = field(default_factory=list)

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
        if dev_token:
            from .principal import hash_token
            principals.append({
                "name": "local-dev",
                "token_sha256": hash_token(dev_token),
                "tenant": "default",
                "clearance": "INTERNAL",
            })
        return cls(mode=mode, allowed_origins=list(origins), principals=principals)

    @property
    def permissive(self) -> bool:
        return self.mode == "permissive"

    def validate_startup(self) -> None:
        """Refuse to boot in enforced mode while any principal still carries the placeholder.

        Prevents shipping a known credential: an operator must mint a real token before the
        server will serve in enforced mode.
        """
        if self.permissive:
            return
        for p in self.principals:
            if str(p.get("token_sha256", "")) == PLACEHOLDER:
                raise RuntimeError(
                    f"auth: principal {p.get('name', '?')!r} still uses the {PLACEHOLDER} "
                    "placeholder hash. Run `nexus auth gen-token | nexus auth hash-token` and "
                    "paste a real hash, or set auth.mode: permissive for local dev."
                )
