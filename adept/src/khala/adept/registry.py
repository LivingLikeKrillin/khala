"""Artifact registry — a checked-in YAML manifest mapping artifact_id -> path.

The manifest stores only (artifact_id, path); the content hash is computed LIVE
from the file on disk (never stored stale) so freshness checks always compare
against the artifact's current content.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml

from khala.adept.hashing import content_hash
from khala.adept.models import ArtifactRef


def _artifact_id(path: str) -> str:
    """A stable id derived from the path (no git, no content)."""
    return hashlib.sha256(path.encode("utf-8")).hexdigest()[:12]


def current_hash(path: str) -> str:
    """Read the file and compute its current content_hash."""
    text = Path(path).read_text(encoding="utf-8")
    return content_hash(text)


def load_manifest(manifest_path, *, root=None) -> list[ArtifactRef]:
    """Load manifest entries; hash is computed live, never read from the manifest.

    root=None: entry paths are used verbatim (cwd-relative, today's behavior).
    root set: each stored relative path is resolved to absolute against root, so
    the live hash works from any cwd. Returns [] if the manifest does not exist.
    """
    path = Path(manifest_path)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    refs: list[ArtifactRef] = []
    for entry in data:
        read_path = entry["path"] if root is None else str(Path(root).resolve() / entry["path"])
        refs.append(
            ArtifactRef(
                artifact_id=entry["artifact_id"],
                path=read_path,
                content_hash=current_hash(read_path),
            )
        )
    return refs


def _load_raw(manifest_path: Path) -> list[dict]:
    if not manifest_path.exists():
        return []
    return yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or []


def register(path: str, *, manifest_path, root=None) -> ArtifactRef:
    """Register an artifact (idempotent on its stored key). Returns its ArtifactRef.

    root=None (default): store `path` verbatim, id from it, read it as given
    (today's behavior). root set: store the root-relative POSIX path, id from
    that, and return/read the resolved absolute path. A path outside root raises
    ValueError (fail-loud). The manifest persists only (artifact_id, path); the
    returned ref carries the live content_hash.
    """
    if root is None:
        stored = path
        read_path = path
    else:
        abs_path = Path(path).resolve()
        try:
            stored = abs_path.relative_to(Path(root).resolve()).as_posix()
        except ValueError:
            raise ValueError(f"artifact {path} is outside the adept root {root}") from None
        read_path = str(abs_path)

    man = Path(manifest_path)
    raw = _load_raw(man)
    aid = _artifact_id(stored)
    if not any(entry["path"] == stored for entry in raw):
        raw.append({"artifact_id": aid, "path": stored})
        man.parent.mkdir(parents=True, exist_ok=True)
        man.write_text(yaml.safe_dump(raw, sort_keys=False, allow_unicode=True), encoding="utf-8")
    else:
        # reuse the existing id for this stored key
        aid = next(entry["artifact_id"] for entry in raw if entry["path"] == stored)
    return ArtifactRef(artifact_id=aid, path=read_path, content_hash=current_hash(read_path))
