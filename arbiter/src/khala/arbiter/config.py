from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

_DEFAULT_ALLOW = ["docs/**", "tests/**"]


@dataclass
class SpecledgerConfig:
    exempt_paths: list[str] = field(default_factory=list)
    allow_globs: list[str] = field(default_factory=lambda: list(_DEFAULT_ALLOW))
    nexus: dict | None = None

    @classmethod
    def load(cls, project_root: Path) -> "SpecledgerConfig":
        path = Path(project_root) / ".specledger" / "config.yaml"
        if not path.exists():
            return cls()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(
            exempt_paths=data.get("exempt_paths", []),
            allow_globs=data.get("allow_globs", list(_DEFAULT_ALLOW)),
            nexus=data.get("nexus"),
        )
