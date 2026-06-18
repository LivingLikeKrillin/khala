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
        principals = auth.get("principals") or []
        return cls(mode=mode, allowed_origins=list(origins), principals=list(principals))

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
