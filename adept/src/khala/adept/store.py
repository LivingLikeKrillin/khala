"""AdeptStore — the storage abstraction the service layer persists through.

A single Protocol covering exactly the persistence operations `service.*` needs.
Two implementations (`FileStore`, `PostgresStore`) satisfy one shared contract test
so the same orchestration runs over either backend.

`current_hash(path)` is intentionally NOT on the store — it reads the artifact file
from disk via `registry.current_hash`; both backends and `service` call it directly
(the DB/manifest is an index, not the artifact archive).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from khala.adept.models import ArtifactRef, Attempt, Question


@runtime_checkable
class AdeptStore(Protocol):
    def load_manifest(self) -> list[ArtifactRef]: ...
    def register(self, path: str) -> ArtifactRef: ...
    def load_questions(self, artifact_id: str) -> tuple[str | None, list[Question]]: ...
    def save_questions(
        self, artifact_id: str, content_hash: str, questions: list[Question]
    ) -> None: ...
    def append_attempt(self, attempt: Attempt) -> None: ...
    def load_attempts(self) -> list[Attempt]: ...
