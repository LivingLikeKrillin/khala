"""PostgresStore — KenStore over Postgres (psycopg3, sync, fail-loud).

A per-request connection backend with parameterized SQL only. `psycopg` is
imported LAZILY (inside `_conn`) so the default file-backend install does not
need the optional `ken[postgres]` extra.

Contract parity with FileStore is deliberate:
  - `register` is idempotent on `path` (INSERT ... ON CONFLICT DO NOTHING then
    SELECT), reusing `registry._artifact_id` for the id.
  - `save_questions` replaces the artifact's whole set (delete-then-insert),
    reusing `questions.make_question_id` for ids when `q.id` is falsy and storing
    `idx` so `load_questions` returns rows ORDER BY idx — same ids and order as
    FileStore.
  - `current_hash(path)` is read LIVE from disk (the DB is an index, not the
    artifact archive).
  - `append_attempt` is append-only; `load_attempts` returns ORDER BY id with the
    timestamp rendered back to an ISO string to match the file backend's string ts.

All writes are FAIL-LOUD: exceptions propagate (the `with conn` block rolls back).
"""

from __future__ import annotations

from ken.models import ArtifactRef, Attempt, Question
from ken.questions import make_question_id
from ken.registry import _artifact_id, current_hash


class PostgresStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    def _conn(self):
        import psycopg  # lazy: only needed for the Postgres backend

        return psycopg.connect(self._dsn)

    def load_manifest(self) -> list[ArtifactRef]:
        with self._conn() as c, c.cursor() as cur:
            cur.execute("SELECT artifact_id, path FROM artifacts ORDER BY path")
            return [ArtifactRef(aid, path, current_hash(path)) for aid, path in cur.fetchall()]

    def register(self, path: str) -> ArtifactRef:
        aid = _artifact_id(path)
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO artifacts (artifact_id, path) VALUES (%s, %s) "
                "ON CONFLICT (path) DO NOTHING",
                (aid, path),
            )
            cur.execute("SELECT artifact_id FROM artifacts WHERE path = %s", (path,))
            aid = cur.fetchone()[0]
        return ArtifactRef(aid, path, current_hash(path))

    def load_questions(self, artifact_id: str) -> tuple[str | None, list[Question]]:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT content_hash, question_id, text FROM questions "
                "WHERE artifact_id = %s ORDER BY idx",
                (artifact_id,),
            )
            rows = cur.fetchall()
        if not rows:
            return None, []
        return rows[0][0], [Question(id=qid, text=text) for _, qid, text in rows]

    def save_questions(
        self, artifact_id: str, content_hash: str, questions: list[Question]
    ) -> None:
        # Transaction: delete-then-insert replaces the artifact's whole set.
        # Fail-loud — any DB error propagates and the `with` block rolls back.
        with self._conn() as c, c.cursor() as cur:
            cur.execute("DELETE FROM questions WHERE artifact_id = %s", (artifact_id,))
            for i, q in enumerate(questions):
                qid = q.id or make_question_id(artifact_id, content_hash, i)
                cur.execute(
                    "INSERT INTO questions (artifact_id, content_hash, question_id, idx, text) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (artifact_id, content_hash, qid, i, q.text),
                )

    def append_attempt(self, attempt: Attempt) -> None:
        # Append-only INSERT; fail-loud.
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO attempts "
                "(person, artifact_id, question_id, content_hash, passed, score, ts) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    attempt.person,
                    attempt.artifact_id,
                    attempt.question_id,
                    attempt.content_hash,
                    attempt.passed,
                    attempt.score,
                    attempt.ts,
                ),
            )

    def load_attempts(self) -> list[Attempt]:
        with self._conn() as c, c.cursor() as cur:
            cur.execute(
                "SELECT person, artifact_id, question_id, content_hash, passed, score, ts "
                "FROM attempts ORDER BY id"
            )
            return [
                Attempt(
                    person,
                    artifact_id,
                    question_id,
                    content_hash,
                    passed,
                    score,
                    # Render TIMESTAMPTZ back to an ISO string so it matches the
                    # file backend's string ts (schedule._parse_ts expects a string).
                    ts.isoformat() if hasattr(ts, "isoformat") else ts,
                )
                for person, artifact_id, question_id, content_hash, passed, score, ts in cur.fetchall()
            ]
