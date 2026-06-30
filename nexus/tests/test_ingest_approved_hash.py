"""Governed-doc ingest persists the accountable-review stamp as documents.approved_hash.

Unit-level: captures the `db.execute` parameters from `_save_document` (no DB) to prove the
stamp is written to the new column and is distinct from `content_hash` (nexus's own
change-detection hash). The real round-trip (write → retrieval read-back) is the DB-backed
test `tests/test_a2a_provenance_db.py` (run with NEXUS_TEST_DB_URL).
"""

from __future__ import annotations

from nexus.ingest import pipeline
from nexus.ingest.classifier import ClassificationResult
from nexus.ingest.collector import CollectedFile


def _collected() -> CollectedFile:
    return CollectedFile(
        path=__import__("pathlib").Path("SPEC-x.md"),
        relative_path="SPEC-x.md",
        content="# X\n본문",
        content_hash="nexus-file-hash",
        frontmatter={"title": "X"},
        canonical_uri="git://SPEC-x.md",
    )


async def test_save_document_writes_approved_hash(monkeypatch):
    captured = {}

    async def fake_execute(query, *args):
        captured["query"] = query
        captured["args"] = args
        return "INSERT 0 1"

    monkeypatch.setattr(pipeline.db, "execute", fake_execute)

    await pipeline._save_document(
        _collected(), ClassificationResult(), tenant="acme", approved_hash="sha256:stamp",
    )

    assert "approved_hash" in captured["query"]
    # the stamp is passed as a bind param, distinct from the nexus change-detection hash
    assert "sha256:stamp" in captured["args"]
    assert "nexus-file-hash" in captured["args"]


async def test_save_document_defaults_approved_hash_empty(monkeypatch):
    captured = {}

    async def fake_execute(query, *args):
        captured["args"] = args
        return "INSERT 0 1"

    monkeypatch.setattr(pipeline.db, "execute", fake_execute)
    await pipeline._save_document(_collected(), ClassificationResult(), tenant="acme")

    # last bind param is approved_hash, defaulting to '' for non-governed ingests
    assert captured["args"][-1] == ""
