from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path


class Gate:
    def __init__(self, project_root: Path, now: Callable[[], str]):
        self.root = Path(project_root)
        self._dir = self.root / ".specledger"
        self._marker = self._dir / "active.json"
        self._now = now

    def begin_implementation(self, spec_id: str, set_by: str = "agent") -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._marker.write_text(
            json.dumps({"spec_id": spec_id, "set_at": self._now(), "set_by": set_by}),
            encoding="utf-8",
        )

    def end_implementation(self) -> None:
        self._marker.unlink(missing_ok=True)

    def active_spec(self) -> str | None:
        if not self._marker.exists():
            return None
        return json.loads(self._marker.read_text(encoding="utf-8"))["spec_id"]
