from __future__ import annotations

import enum
from dataclasses import dataclass
from pathlib import Path

from . import frontmatter
from .hashing import content_hash


class ArtifactType(enum.StrEnum):
    ADR = "adr"
    SPEC = "spec"


class Status(enum.StrEnum):
    DRAFT = "draft"
    PROPOSED = "proposed"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    ACCEPTED = "accepted"
    SUPERSEDED = "superseded"
    DEPRECATED = "deprecated"
    STALE = "stale"


@dataclass
class Artifact:
    path: Path
    meta: dict
    body: str

    @classmethod
    def load(cls, path: Path) -> "Artifact":
        meta, body = frontmatter.split(Path(path).read_text(encoding="utf-8"))
        return cls(path=Path(path), meta=meta, body=body)

    @property
    def id(self) -> str:
        return self.meta["id"]

    @property
    def type(self) -> ArtifactType:
        return ArtifactType(self.meta["type"])

    @property
    def status(self) -> Status:
        return Status(self.meta["status"])

    def recompute_hash(self) -> str:
        return content_hash(self.body)

    def save(self) -> None:
        # newline="\n" is not cosmetic: left at None, write_text translates every "\n" to
        # the platform's separator, so on Windows one save rewrites the whole file in line
        # endings only. .gitattributes hides that from git and not from the working tree.
        self.path.write_text(
            frontmatter.render(self.meta, self.body), encoding="utf-8", newline="\n"
        )
