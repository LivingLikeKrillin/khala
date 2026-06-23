"""Artifact registry — a checked-in YAML manifest mapping artifact_id -> path.

The manifest stores only (artifact_id, path); the content hash is computed LIVE
from the file on disk (never stored stale) so freshness checks always compare
against the artifact's current content.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from ken.hashing import content_hash
from ken.models import ArtifactRef


def _artifact_id(path: str) -> str:
    """A stable id derived from the path (no git, no content)."""
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]


def current_hash(path: str) -> str:
    """Read the file and compute its current content_hash."""
    text = Path(path).read_text(encoding="utf-8")
    return content_hash(text)


def load_manifest(manifest_path) -> list[ArtifactRef]:
    """Load manifest entries; hash is computed live, never read from the manifest.

    Returns [] if the manifest does not exist.
    """
    path = Path(manifest_path)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    refs: list[ArtifactRef] = []
    for entry in data:
        refs.append(
            ArtifactRef(
                artifact_id=entry["artifact_id"],
                path=entry["path"],
                content_hash=current_hash(entry["path"]),
            )
        )
    return refs


def _load_raw(manifest_path: Path) -> list[dict]:
    if not manifest_path.exists():
        return []
    return yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or []


def register(path: str, *, manifest_path) -> ArtifactRef:
    """Register an artifact (idempotent on path). Returns its ArtifactRef.

    The manifest persists only (artifact_id, path); the returned ref carries the
    live content_hash.
    """
    man = Path(manifest_path)
    raw = _load_raw(man)
    aid = _artifact_id(path)
    if not any(entry["path"] == path for entry in raw):
        raw.append({"artifact_id": aid, "path": path})
        man.parent.mkdir(parents=True, exist_ok=True)
        man.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    else:
        # reuse the existing id for this path
        aid = next(entry["artifact_id"] for entry in raw if entry["path"] == path)
    return ArtifactRef(artifact_id=aid, path=path, content_hash=current_hash(path))
