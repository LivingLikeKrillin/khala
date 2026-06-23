-- ken Postgres schema (S2) — 3 tables, no view.
--
-- The DB is an INDEX, not the artifact archive: artifacts live in the
-- filesystem/git and `content_hash` is computed LIVE from the file on read
-- (never stored here). Derivations (schedule/vouch/coverage) are recomputed in
-- Python from these rows, so no view or derived table is needed.
--
-- Apply with:  psql "$KEN_DATABASE_URL" -f db/init.sql

CREATE TABLE artifacts (
    artifact_id TEXT PRIMARY KEY,
    path        TEXT NOT NULL UNIQUE
);

CREATE TABLE questions (
    artifact_id  TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    question_id  TEXT NOT NULL,
    idx          INTEGER NOT NULL,
    text         TEXT NOT NULL,
    PRIMARY KEY (artifact_id, question_id)
);
CREATE INDEX idx_questions_artifact ON questions (artifact_id);

CREATE TABLE attempts (
    id           BIGSERIAL PRIMARY KEY,
    person       TEXT NOT NULL,
    artifact_id  TEXT NOT NULL,
    question_id  TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    passed       BOOLEAN NOT NULL,
    score        DOUBLE PRECISION NOT NULL,
    ts           TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_attempts_question ON attempts (question_id);
