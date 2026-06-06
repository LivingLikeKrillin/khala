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

    def _matches(self, path: str, globs: list[str]) -> bool:
        from fnmatch import fnmatch
        return any(fnmatch(path, g) for g in globs)

    def _log_exempt(self, path: str, tool: str = "") -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        with (self._dir / "exempt.log").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": self._now(), "path": path, "tool": tool}) + "\n")

    def check_gate(self, paths, ledger, config) -> dict:
        active = self.active_spec()
        spec_status = None
        open_count = 0
        if active is not None:
            rep = {r["id"]: r for r in ledger.status()}
            entry = rep.get(active, {})
            spec_status = entry.get("status")
            sc_path = ledger.reviews / f"{active}.md"
            if sc_path.exists():
                from .sidecar import Sidecar
                open_count = Sidecar.read(sc_path).open_issue_count()

        for path in paths:
            if self._matches(path, config.exempt_paths):
                self._log_exempt(path)
                continue
            if self._matches(path, config.allow_globs):
                continue
            if active is None:
                return {"allowed": False, "spec_id": None, "status": None,
                        "open_issue_count": 0,
                        "reason": "활성 spec 없음 — begin_implementation 필요"}
            if spec_status not in ("approved", "accepted"):
                return {"allowed": False, "spec_id": active, "status": spec_status,
                        "open_issue_count": open_count,
                        "reason": f"spec {active} 미승인 (status={spec_status}, "
                                  f"open={open_count})"}
        return {"allowed": True, "spec_id": active, "status": spec_status,
                "open_issue_count": open_count, "reason": "ok"}
