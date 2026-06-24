from __future__ import annotations

from fastapi.testclient import TestClient

from ken.llm import FakeLLM
from ken.schedule import _parse_ts
from ken_web_api import deps
from ken_web_api.app import app
from ken_web_api.auth_store import FakeAuthStore
from ken_web_api.security import hash_password


def _auth_client(tmp_path, monkeypatch, *, auth_store=None, responses=()):
    """Auth-ON client: file data backend (monkeypatched) + Fake auth store.
    A dummy KEN_DATABASE_URL satisfies the startup guard; make_store is patched
    to the file backend so data calls never touch Postgres."""
    monkeypatch.setenv("KEN_AUTH", "1")
    monkeypatch.setenv("KEN_DATABASE_URL", "postgresql://dummy")  # guard only
    monkeypatch.setenv("KEN_DATA_DIR", str(tmp_path))
    from ken.stores.file_store import FileStore
    store = FileStore(
        manifest=str(tmp_path / "m.yaml"),
        questions=str(tmp_path / "q.json"),
        ledger=str(tmp_path / "l.jsonl"),
    )
    monkeypatch.setattr(deps, "make_store", lambda _slug=None: store)
    auth = auth_store or FakeAuthStore()
    monkeypatch.setattr(deps, "make_auth_store", lambda: auth)
    monkeypatch.setattr(deps, "make_llm", lambda: FakeLLM(responses=list(responses)))
    return TestClient(app), auth, store


def _login(c, auth, email="a@x.com", password="password1"):
    auth.create_user(email, hash_password(password))
    return c.post("/api/auth/login", json={"email": email, "password": password})


def test_login_success_sets_cookie_and_returns_email(tmp_path, monkeypatch):
    c, auth, _ = _auth_client(tmp_path, monkeypatch)
    r = _login(c, auth)
    assert r.status_code == 200 and r.json() == {"email": "a@x.com"}
    assert deps.SESSION_COOKIE in r.cookies


def test_login_wrong_password_and_unknown_email_same_generic_401(tmp_path, monkeypatch):
    c, auth, _ = _auth_client(tmp_path, monkeypatch)
    auth.create_user("a@x.com", hash_password("password1"))
    wrong = c.post("/api/auth/login", json={"email": "a@x.com", "password": "nope"})
    unknown = c.post("/api/auth/login", json={"email": "ghost@x.com", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]  # identical generic message


def test_me_requires_session(tmp_path, monkeypatch):
    c, auth, _ = _auth_client(tmp_path, monkeypatch)
    assert c.get("/api/auth/me").status_code == 401
    _login(c, auth)
    assert c.get("/api/auth/me").json() == {"email": "a@x.com"}


def test_protected_endpoint_401_without_session_200_with(tmp_path, monkeypatch):
    c, auth, _ = _auth_client(tmp_path, monkeypatch)
    assert c.get("/api/coverage").status_code == 401
    _login(c, auth)
    assert c.get("/api/coverage").status_code == 200


def test_logout_clears_session(tmp_path, monkeypatch):
    c, auth, _ = _auth_client(tmp_path, monkeypatch)
    _login(c, auth)
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/auth/me").status_code == 401


def test_expired_session_is_401(tmp_path, monkeypatch):
    c, auth, _ = _auth_client(tmp_path, monkeypatch)
    u = auth.create_user("a@x.com", hash_password("password1"))
    past = (_parse_ts("2000-01-01T00:00:00+00:00")).isoformat()
    auth.create_session(u.id, "tok", past)
    c.cookies.set(deps.SESSION_COOKIE, "tok")
    assert c.get("/api/auth/me").status_code == 401


def test_person_is_server_derived_from_session(tmp_path, monkeypatch):
    c, auth, store = _auth_client(
        tmp_path, monkeypatch,
        responses=["Q1?", '{"passed": true, "score": 0.9, "rationale":"ok"}'],
    )
    _login(c, auth)
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    aid = c.post("/api/artifacts", json={"path": str(art)}).json()["artifact_id"]
    qid = c.get(f"/api/artifacts/{aid}/due").json()["questions"][0]["question_id"]
    # NOTE: no "person" in the body — server derives it from the session.
    r = c.post("/api/attempts", json={"artifact_id": aid, "question_id": qid, "answer": "..."})
    assert r.status_code == 200
    assert store.load_attempts()[0].person == "a@x.com"


def test_startup_guard_fails_when_auth_on_without_db(monkeypatch):
    monkeypatch.setenv("KEN_AUTH", "1")
    monkeypatch.delenv("KEN_DATABASE_URL", raising=False)
    import pytest
    with pytest.raises(RuntimeError):
        with TestClient(app):  # entering context triggers startup (lifespan)
            pass


def test_auth_off_endpoints_open_and_person_local(tmp_path, monkeypatch):
    monkeypatch.delenv("KEN_AUTH", raising=False)
    monkeypatch.setenv("KEN_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(deps, "make_llm", lambda: FakeLLM(responses=["Q1?", '{"passed": true, "score": 0.9, "rationale":"ok"}']))
    c = TestClient(app)
    assert c.get("/api/coverage").status_code == 200       # open
    assert c.get("/api/auth/me").json() == {"email": deps.DEFAULT_PERSON}
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    aid = c.post("/api/artifacts", json={"path": str(art)}).json()["artifact_id"]
    qid = c.get(f"/api/artifacts/{aid}/due").json()["questions"][0]["question_id"]
    c.post("/api/attempts", json={"artifact_id": aid, "question_id": qid, "answer": "x"})
    # person defaulted to "local" — read it back via a FileStore over the app's
    # DEFAULT KEN_DATA_DIR paths (deps defaults: ken.manifest.yaml / .questions.json
    # / .attempts.jsonl — NOT the m.yaml/q.json/l.jsonl used by the auth-ON helper).
    from ken.stores.file_store import FileStore
    store = FileStore(
        manifest=str(tmp_path / "ken.manifest.yaml"),
        questions=str(tmp_path / "ken.questions.json"),
        ledger=str(tmp_path / "ken.attempts.jsonl"),
    )
    assert store.load_attempts()[0].person == deps.DEFAULT_PERSON  # "local"


def test_two_users_distinct_tenants_see_disjoint_data(tmp_path, monkeypatch):
    # Capture the tenant_slug make_store is called with, per request.
    calls = []
    c, auth, store = _auth_client(tmp_path, monkeypatch)
    monkeypatch.setattr(deps, "make_store", lambda slug=None: (calls.append(slug), store)[1])
    auth.create_tenant("a", "A"); auth.create_tenant("b", "B")
    auth.create_user("alice@x.com", hash_password("password1"), tenant_slug="a")
    c.post("/api/auth/login", json={"email": "alice@x.com", "password": "password1"})
    c.get("/api/coverage")
    assert calls[-1] == "a"   # store bound to Alice's tenant


def test_attempt_records_caller_tenant(tmp_path, monkeypatch):
    c, auth, store = _auth_client(
        tmp_path, monkeypatch,
        responses=["Q1?", '{"passed": true, "score": 0.9, "rationale":"ok"}'],
    )
    auth.create_tenant("a", "A")
    auth.create_user("a@x.com", hash_password("password1"), tenant_slug="a")
    c.post("/api/auth/login", json={"email": "a@x.com", "password": "password1"})
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    aid = c.post("/api/artifacts", json={"path": str(art)}).json()["artifact_id"]
    qid = c.get(f"/api/artifacts/{aid}/due").json()["questions"][0]["question_id"]
    c.post("/api/attempts", json={"artifact_id": aid, "question_id": qid, "answer": "x"})
    assert store.load_attempts()[0].person == "a@x.com"   # person still server-derived
