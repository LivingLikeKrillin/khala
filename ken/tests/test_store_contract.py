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
    import psycopg

    from ken.stores.postgres_store import PostgresStore

    with psycopg.connect(_PG_DSN) as c, c.cursor() as cur:
        cur.execute("TRUNCATE artifacts, questions, attempts")
    return PostgresStore(_PG_DSN)


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
