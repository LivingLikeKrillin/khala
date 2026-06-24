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

-- S6 auth (Postgres-only gating). Separate from the 3 core tables.
CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    token      TEXT PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_sessions_user ON sessions (user_id);
