"""API tests — FastAPI TestClient over the FakeLLM seam, isolated tmp data dir.

No live API key: every test monkeypatches `deps.make_llm` to a scripted `FakeLLM`.
FakeLLM `responses` must budget for the `GET /due` generate call BEFORE any
attempt's grade (+remediation) calls, since /due regenerates on missing/stale.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from ken.llm import FakeLLM
from ken_web_api import deps
from ken_web_api.app import app


def _client(tmp_path, monkeypatch, responses):
    monkeypatch.setenv("KEN_DATA_DIR", str(tmp_path))
    # A single shared FakeLLM so scripted responses pop in cumulative call order
    # across requests (e.g. /due consumes the generate response before /attempts
    # consumes the grade [+remediation] responses).
    fake = FakeLLM(responses=list(responses))
    monkeypatch.setattr(deps, "make_llm", lambda: fake)
    return TestClient(app)


def test_register_due_attempt_coverage_flow(tmp_path, monkeypatch):
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    c = _client(
        tmp_path,
        monkeypatch,
        responses=[
            "Q1?\nQ2?",  # /due -> generate
            '{"passed": true, "score": 0.9, "rationale":"ok"}',  # attempt grade
        ],
    )
    aid = c.post("/api/artifacts", json={"path": str(art)}).json()["artifact_id"]
    due = c.get(f"/api/artifacts/{aid}/due").json()
    assert len(due["questions"]) == 2
    qid = due["questions"][0]["question_id"]
    res = c.post(
        "/api/attempts",
        json={"artifact_id": aid, "question_id": qid, "person": "kr", "answer": "good"},
    ).json()
    assert res["passed"] is True and res["remediation"] is None
    cov = c.get("/api/coverage").json()
    assert cov["total"] == 1


def test_attempt_fail_returns_remediation(tmp_path, monkeypatch):
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    c = _client(
        tmp_path,
        monkeypatch,
        responses=[
            "Q1?",  # /due -> generate
            '{"passed": false, "score": 0.1, "rationale":"no"}',  # attempt grade (fail)
            "Because it publishes orders.",  # remediation
        ],
    )
    aid = c.post("/api/artifacts", json={"path": str(art)}).json()["artifact_id"]
    qid = c.get(f"/api/artifacts/{aid}/due").json()["questions"][0]["question_id"]
    res = c.post(
        "/api/attempts",
        json={"artifact_id": aid, "question_id": qid, "person": "kr", "answer": "wrong"},
    ).json()
    assert res["passed"] is False and "publishes" in res["remediation"]


def test_get_artifacts_shape(tmp_path, monkeypatch):
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    c = _client(tmp_path, monkeypatch, responses=[])
    aid = c.post("/api/artifacts", json={"path": str(art)}).json()["artifact_id"]
    rows = c.get("/api/artifacts").json()
    assert isinstance(rows, list) and len(rows) == 1
    row = rows[0]
    assert row["artifact_id"] == aid
    assert row["path"] == str(art)
    assert row["status"] == "orphan"  # no questions yet -> orphan
    assert row["weak_count"] == 0


def test_unknown_artifact_id_returns_404(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, responses=["Q1?"])
    resp = c.get("/api/artifacts/does-not-exist/due")
    assert resp.status_code == 404


def test_storage_write_failure_returns_500(tmp_path, monkeypatch):
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    c = _client(
        tmp_path,
        monkeypatch,
        responses=[
            "Q1?",  # /due -> generate
            '{"passed": true, "score": 0.9, "rationale":"ok"}',  # attempt grade
        ],
    )
    aid = c.post("/api/artifacts", json={"path": str(art)}).json()["artifact_id"]
    qid = c.get(f"/api/artifacts/{aid}/due").json()["questions"][0]["question_id"]

    # Storage write fails: the store's append_attempt raises OSError. The service
    # lets it propagate (fail-loud) and the handler maps it to HTTP 500.
    from ken.stores.file_store import FileStore

    def _boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(FileStore, "append_attempt", _boom)
    # Don't let TestClient re-raise the server exception; assert the HTTP 500.
    c2 = TestClient(app, raise_server_exceptions=False)
    resp = c2.post(
        "/api/attempts",
        json={"artifact_id": aid, "question_id": qid, "person": "kr", "answer": "x"},
    )
    assert resp.status_code == 500
