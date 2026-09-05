from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import frontmatter


@dataclass
class Issue:
    issue_id: str
    category: str
    severity: str
    description: str
    status: str  # open | accepted | rejected | deferred
    disposition_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "issue_id": self.issue_id,
            "category": self.category,
            "severity": self.severity,
            "description": self.description,
            "status": self.status,
            "disposition_reason": self.disposition_reason,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Issue":
        return cls(
            issue_id=d["issue_id"],
            category=d["category"],
            severity=d["severity"],
            description=d["description"],
            status=d["status"],
            disposition_reason=d.get("disposition_reason"),
        )


@dataclass
class Sidecar:
    target: str
    critiqued_hash: str
    critiqued_at: str
    issues: list[Issue] = field(default_factory=list)
    approved_by: str | None = None
    approved_at: str | None = None
    narrative: str = ""

    def open_issue_count(self) -> int:
        return sum(1 for i in self.issues if i.status == "open")

    def write(self, path: Path) -> None:
        meta = {
            "target": self.target,
            "critiqued_hash": self.critiqued_hash,
            "critiqued_at": self.critiqued_at,
            "issues": [i.to_dict() for i in self.issues],
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
        }
        Path(path).write_text(
            frontmatter.render(meta, self.narrative), encoding="utf-8", newline="\n"
        )

    @classmethod
    def read(cls, path: Path) -> "Sidecar":
        meta, body = frontmatter.split(Path(path).read_text(encoding="utf-8"))
        return cls(
            target=meta["target"],
            critiqued_hash=meta["critiqued_hash"],
            critiqued_at=meta["critiqued_at"],
            issues=[Issue.from_dict(d) for d in (meta.get("issues") or [])],
            approved_by=meta.get("approved_by"),
            approved_at=meta.get("approved_at"),
            narrative=body,
        )
