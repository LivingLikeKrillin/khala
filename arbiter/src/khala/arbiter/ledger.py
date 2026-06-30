from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

from . import ids
from .artifacts import Artifact, ArtifactType, Status
from .errors import ArtifactNotFoundError, ImmutableArtifactError
from .frontmatter import render


def _md_cell(value: object) -> str:
    """Escape a value for safe use in a markdown table cell."""
    return str(value).replace("|", "\\|")


class Ledger:
    def __init__(self, root: Path, now: Callable[[], str]):
        self.root = Path(root)
        self.specs = self.root / "specs"
        self.adr = self.root / "adr"
        self.reviews = self.root / ".reviews"
        for d in (self.specs, self.adr, self.reviews):
            d.mkdir(parents=True, exist_ok=True)
        self._now = now

    def record(self, type: str, title: str, slug: str | None = None) -> str:
        atype = ArtifactType(type)
        if atype is ArtifactType.ADR:
            aid = ids.next_adr_id(self.adr)
            status = Status.PROPOSED
            path = self.adr / f"{aid}-{ids.slugify(title)}.md"
        else:
            aid = ids.make_spec_id(self.specs, title, slug)
            status = Status.DRAFT
            path = self.specs / f"{aid}.md"
        meta = {
            "id": aid, "type": str(atype), "title": title,
            "status": str(status), "date": self._now(),
        }
        path.write_text(render(meta, f"# {title}\n\n"), encoding="utf-8")
        return aid

    def _resolve(self, artifact_id: str) -> Path:
        for d in (self.specs, self.adr):
            for p in d.glob(f"{artifact_id}*.md"):
                if Artifact.load(p).id == artifact_id:
                    return p
        raise ArtifactNotFoundError(artifact_id)

    def _all_paths(self) -> Iterator[Path]:
        # Only real artifacts (markdown carrying a frontmatter `id`). Non-artifact docs
        # like a README.md living in specs/ or adr/ are skipped, not crashed on.
        for p in (*self.specs.glob("*.md"), *self.adr.glob("*.md")):
            try:
                if Artifact.load(p).meta.get("id"):
                    yield p
            except Exception:  # noqa: BLE001 - unreadable/malformed file is not an artifact
                continue

    def status(self, artifact_id: str | None = None) -> list[dict]:
        paths = [self._resolve(artifact_id)] if artifact_id else list(self._all_paths())
        report = []
        for p in paths:
            a = Artifact.load(p)
            entry = {"id": a.id, "type": str(a.type), "status": str(a.status),
                     "needs_review": False, "tampered": False}
            if a.status in (Status.APPROVED, Status.ACCEPTED):
                stored = a.meta.get("content_hash")
                # an approved artifact with no stamped hash, or a hash that no
                # longer matches the body, has lost its accountable-review proof
                if not stored or a.recompute_hash() != stored:
                    if a.type is ArtifactType.SPEC:
                        a.meta["status"] = str(Status.IN_REVIEW)
                        a.save()
                        entry["status"] = str(Status.IN_REVIEW)
                        entry["needs_review"] = True
                    else:  # accepted ADR is immutable: flag, never reset
                        entry["tampered"] = True
            report.append(entry)
        return report

    def supersede(self, old_id: str, new_id: str) -> None:
        if old_id == new_id:
            raise ValueError("an ADR cannot supersede itself")
        a_old = Artifact.load(self._resolve(old_id))
        a_new = Artifact.load(self._resolve(new_id))
        if a_old.type is not ArtifactType.ADR or a_new.type is not ArtifactType.ADR:
            raise ImmutableArtifactError("supersede applies to ADRs only")
        if a_old.status is Status.SUPERSEDED:
            raise ImmutableArtifactError(f"{old_id} is already superseded")
        a_old.meta["status"] = str(Status.SUPERSEDED)
        a_old.meta["superseded_by"] = new_id
        a_old.save()
        a_new.meta["supersedes"] = old_id
        a_new.save()

    _GROUPS = [
        ("🔴 미검토", {Status.DRAFT, Status.PROPOSED}),
        ("🟡 검토중", {Status.IN_REVIEW}),
        ("🟢 승인", {Status.APPROVED, Status.ACCEPTED}),
    ]

    def index(self) -> Path:
        self.status()  # repair first
        arts = [Artifact.load(p) for p in self._all_paths()]
        lines = ["# Arbiter Index", ""]
        for label, statuses in self._GROUPS:
            members = [a for a in arts if a.status in statuses]
            lines.append(f"## {label} ({len(members)})")
            lines.append("")
            if members:
                lines.append("| id | title | approved_by | date | linked_adrs |")
                lines.append("|---|---|---|---|---|")
                for a in members:
                    linked = ", ".join(a.meta.get("linked_adrs") or [])
                    lines.append(
                        f"| {_md_cell(a.id)} | {_md_cell(a.meta.get('title', ''))} "
                        f"| {_md_cell(a.meta.get('approved_by', ''))} "
                        f"| {_md_cell(a.meta.get('date', ''))} | {_md_cell(linked)} |"
                    )
            lines.append("")
        out = self.root / "INDEX.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        return out
