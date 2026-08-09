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


async def _no_prior_doc(query, *args):
    """Stub for db.fetch_one: no previously-stored document (prev-hash lookup → None).

    _save_document queries the prior content_hash before upserting (re-ingest event
    detection). These unit tests run without a DB, so that lookup is stubbed to None
    to preserve no-DB isolation (a real prior-row round-trip is covered by the
    DB-backed tests/test_reingest_event_db.py).
    """
    return None


async def test_save_document_writes_approved_hash(monkeypatch):
    captured = {}

    async def fake_execute(query, *args):
        captured["query"] = query
        captured["args"] = args
        return "INSERT 0 1"

    monkeypatch.setattr(pipeline.db, "fetch_one", _no_prior_doc)
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
        # **위치가 아니라 이름으로 잡는다.** 예전엔 `args[-1]` 이 approved_hash 라고 단언했는데,
        # 바인드 파라미터를 하나 늘리는 것만으로 깨졌다(2026-08-09, n_images 추가). 그건 이 검사가
        # 지키려던 것과 무관한 실패다 — SQL 의 열 순서에서 위치를 읽어 온다.
        import re as _re
        head = query.split("INSERT INTO documents (", 1)[1]
        cols = [c.strip() for c in head.split(")", 1)[0].split(",")]
        vals = [v.strip() for v in
                head.split("VALUES (", 1)[1].split(")", 1)[0].split(",")]
        # VALUES 에는 리터럴('document', 'git', 'active')이 섞여 있어 열↔인자가 1:1 이 아니다.
        # `$N` 인 자리만 골라 이름에 붙인다.
        captured["by_name"] = {
            c: args[int(_re.fullmatch(r"\$(\d+)(?:::\w+)?", v).group(1)) - 1]
            for c, v in zip(cols, vals, strict=False)
            if _re.fullmatch(r"\$(\d+)(?:::\w+)?", v)}
        captured["args"] = args
        return "INSERT 0 1"

    monkeypatch.setattr(pipeline.db, "fetch_one", _no_prior_doc)
    monkeypatch.setattr(pipeline.db, "execute", fake_execute)
    await pipeline._save_document(_collected(), ClassificationResult(), tenant="acme")

    # approved_hash defaults to '' for non-governed ingests
    assert captured["by_name"]["approved_hash"] == ""
