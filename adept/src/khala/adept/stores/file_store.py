"""FileStore — KenStore over the existing file-backed registry/questions/attempt.

A thin wrapper: paths are injected at construction; each method delegates to the
existing module function with the held path. Behavior is identical to ken today —
fail-loud writes, append-only attempts, live content hashes.
"""

from __future__ import annotations

from pathlib import Path

from ken.attempt import append_attempt as _append_attempt
from ken.attempt import load_attempts as _load_attempts
from ken.models import ArtifactRef, Attempt, Question
from ken.questions import load_questions as _load_questions
from ken.questions import save_questions as _save_questions
from ken.registry import load_manifest as _load_manifest
from ken.registry import register as _register


class FileStore:
    def __init__(
        self,
        *,
        manifest: str,
        questions: str,
        ledger: str,
        make_parents: bool = True,
        relative_to_root: bool = False,
    ):
        self._manifest = manifest
        self._questions = questions
        self._ledger = ledger
        self._mp = make_parents
        self._relative_to_root = relative_to_root

    def _root(self):
        # Lazily derived ONLY in root mode. Computed here (not __init__) so a
        # degenerate FileStore(manifest="x", ...) that never reaches the registry
        # (e.g. the fail-loud attempt test) is unaffected.
        return Path(self._manifest).resolve().parent if self._relative_to_root else None

    def load_manifest(self) -> list[ArtifactRef]:
        return _load_manifest(self._manifest, root=self._root())

    def register(self, path: str) -> ArtifactRef:
        return _register(path, manifest_path=self._manifest, root=self._root())

    def load_questions(self, artifact_id: str) -> tuple[str | None, list[Question]]:
        return _load_questions(artifact_id, store_path=self._questions)

    def save_questions(
        self, artifact_id: str, content_hash: str, questions: list[Question]
    ) -> None:
        _save_questions(
            artifact_id,
            content_hash,
            questions,
            store_path=self._questions,
            make_parents=self._mp,
        )

    def append_attempt(self, attempt: Attempt) -> None:
        _append_attempt(attempt, ledger_path=self._ledger, make_parents=self._mp)

    def load_attempts(self) -> list[Attempt]:
        return _load_attempts(self._ledger)
