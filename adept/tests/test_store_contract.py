"""Shared KenStore contract — one parametrized suite both backends must satisfy.

FileStore runs ALWAYS. PostgresStore runs only when `KEN_TEST_DATABASE_URL` is set
(mirrors nexus's integration gate); otherwise its param is skipped. Proving both
backends pass the SAME contract makes parity enforced, not assumed.
"""

import os

import pytest

from ken.models import Attempt, Question

_PG_DSN = os.getenv("KEN_TEST_DATABASE_URL")


def _file_store(tmp_path):
    from ken.stores.file_store import FileStore

    return FileStore(
        manifest=str(tmp_path / "m.yaml"),
        questions=str(tmp_path / "q.json"),
        ledger=str(tmp_path / "l.jsonl"),
    )


def _postgres_store(tmp_path):
    # Start from a clean store: the contract tests assume an empty backend, and
    # re-applying init.sql would error on the existing tables. TRUNCATE resets.
    # tenants is the FK parent so TRUNCATE needs CASCADE.
    import psycopg

    from ken.stores.postgres_store import PostgresStore

    with psycopg.connect(_PG_DSN) as c, c.cursor() as cur:
        cur.execute("TRUNCATE artifacts, questions, attempts, users, sessions, tenants CASCADE")
        cur.execute("INSERT INTO tenants (slug, name) VALUES ('default', 'Default'), ('contract', 'Contract')")
    return PostgresStore(_PG_DSN, "contract")  # 'contract' (not 'default') keeps the contract tenant isolated from the seeded 'default' row


# FileStore always; PostgresStore gated on KEN_TEST_DATABASE_URL (skipped when unset).
STORE_FACTORIES = [
    pytest.param(_file_store, id="file"),
    pytest.param(
        _postgres_store,
        id="postgres",
        marks=pytest.mark.skipif(_PG_DSN is None, reason="KEN_TEST_DATABASE_URL unset"),
    ),
]


@pytest.fixture(params=STORE_FACTORIES)
def store(request, tmp_path):
    return request.param(tmp_path)


def test_register_roundtrip_and_idempotent(store, tmp_path):
    art = tmp_path / "a.md"
    art.write_text("hello\n", encoding="utf-8")
    r1 = store.register(str(art))
    r2 = store.register(str(art))  # idempotent on path
    assert r1.artifact_id == r2.artifact_id
    man = store.load_manifest()
    assert len(man) == 1 and man[0].path == str(art) and man[0].content_hash  # hash live


def test_save_questions_replace_hash_ids_order(store):
    store.save_questions("a1", "sha256:h1", [Question(id="", text="Q1"), Question(id="", text="Q2")])
    h, qs = store.load_questions("a1")
    assert h == "sha256:h1" and [q.text for q in qs] == ["Q1", "Q2"]  # order preserved
    from ken.questions import make_question_id

    assert qs[0].id == make_question_id("a1", "sha256:h1", 0)  # stable id scheme
    store.save_questions("a1", "sha256:h2", [Question(id="", text="NEW")])  # replace
    h2, qs2 = store.load_questions("a1")
    assert h2 == "sha256:h2" and [q.text for q in qs2] == ["NEW"]


def test_attempts_append_only_in_order(store):
    def a(p, ts):
        return Attempt("kr", "a1", "q1", "sha256:h", p, 1.0, ts)

    store.append_attempt(a(True, "2026-06-20T00:00:00Z"))
    store.append_attempt(a(False, "2026-06-20T01:00:00Z"))
    got = store.load_attempts()
    assert [x.passed for x in got] == [True, False]


def test_load_absent_is_empty(store):
    assert (
        store.load_manifest() == []
        and store.load_questions("nope") == (None, [])
        and store.load_attempts() == []
    )


def test_filestore_default_is_verbatim_outside_any_root(tmp_path):
    # Guards the opt-in default: ken-web registers arbitrary paths verbatim.
    from ken.stores.file_store import FileStore

    art = tmp_path / "artifacts" / "a.md"
    art.parent.mkdir(parents=True)
    art.write_text("x\n", encoding="utf-8")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    s = FileStore(
        manifest=str(data_dir / "m.yaml"),
        questions=str(data_dir / "q.json"),
        ledger=str(data_dir / "l.jsonl"),
    )  # default relative_to_root=False
    ref = s.register(str(art))  # art is NOT under data_dir -> must NOT raise
    assert ref.path == str(art) and s.load_manifest()[0].path == str(art)


def test_append_attempt_fail_loud(tmp_path):
    from ken.stores.file_store import FileStore

    s = FileStore(
        manifest="x",
        questions="x",
        ledger=str(tmp_path / "nope" / "x.jsonl"),
        make_parents=False,
    )
    with pytest.raises(OSError):  # missing parent dir -> FileNotFoundError (subclass of OSError)
        s.append_attempt(Attempt("k", "a", "q", "h", True, 1.0, "2026-06-20T00:00:00Z"))


@pytest.mark.skipif(_PG_DSN is None, reason="KEN_TEST_DATABASE_URL unset")
def test_postgres_two_tenant_isolation(tmp_path):
    import psycopg
    from ken.stores.postgres_store import PostgresStore
    art = tmp_path / "a.md"
    art.write_text("Payment service publishes orders.\n", encoding="utf-8")
    with psycopg.connect(_PG_DSN) as c, c.cursor() as cur:
        cur.execute("TRUNCATE artifacts, questions, attempts, users, sessions, tenants CASCADE")
        cur.execute("INSERT INTO tenants (slug, name) VALUES ('a', 'A'), ('b', 'B')")
    a, b = PostgresStore(_PG_DSN, "a"), PostgresStore(_PG_DSN, "b")
    ra = a.register(str(art))                     # same path under both tenants
    rb = b.register(str(art))
    assert ra.artifact_id == rb.artifact_id       # path-only id; tenant is the discriminator
    assert [r.path for r in a.load_manifest()] == [str(art)]
    assert [r.path for r in b.load_manifest()] == [str(art)]
    # an attempt under A is invisible to B
    a.append_attempt(Attempt("u", ra.artifact_id, "q1", "h", True, 1.0, "2026-06-24T00:00:00+00:00"))
    assert len(a.load_attempts()) == 1 and b.load_attempts() == []
    # B's questions don't leak into A
    b.save_questions(rb.artifact_id, "h", [Question(text="Q?")])
    assert a.load_questions(ra.artifact_id) == (None, [])
