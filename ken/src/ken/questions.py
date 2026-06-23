"""Questions store — per-artifact, bound to a content_hash. FAIL-LOUD.

The store is the join target for all derivations, so a dropped write corrupts
coverage as badly as a dropped attempt — hence writes are fail-loud (raise).
`save_questions` REPLACES the artifact's prior set (keyed by artifact_id).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ken.models import Question


def make_question_id(artifact_id: str, content_hash: str, index: int) -> str:
    """A stable question id: sha(artifact_id + content_hash + index)[:12].

    Changes when the artifact's content changes (the intended staleness reset).
    """
    raw = f"{artifact_id}:{content_hash}:{index}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


def _load_store(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_questions(
    artifact_id: str,
    content_hash: str,
    questions: list[Question],
    *,
    store_path: str | Path,
    make_parents: bool = True,
) -> None:
    """Replace the artifact's question set, binding it to `content_hash`.

    Ids are assigned via `make_question_id` when missing. FAIL-LOUD: IO errors
    propagate (OSError).
    """
    path = Path(store_path)
    if make_parents:
        path.parent.mkdir(parents=True, exist_ok=True)

    store = _load_store(path)
    entries = []
    for i, q in enumerate(questions):
        qid = q.id or make_question_id(artifact_id, content_hash, i)
        entries.append({"id": qid, "text": q.text})
    store[artifact_id] = {"content_hash": content_hash, "questions": entries}

    path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def load_questions(
    artifact_id: str, *, store_path: str | Path
) -> tuple[str | None, list[Question]]:
    """Return (content_hash, [Question]) for the artifact, or (None, []) if absent."""
    path = Path(store_path)
    if not path.exists():
        return None, []
    store = json.loads(path.read_text(encoding="utf-8"))
    entry = store.get(artifact_id)
    if entry is None:
        return None, []
    questions = [Question(id=q["id"], text=q["text"]) for q in entry["questions"]]
    return entry["content_hash"], questions
