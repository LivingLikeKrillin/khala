-- ken Postgres schema. Tenant-isolated (one tenant per user); tenant key = slug.
-- The DB is an INDEX, not the artifact archive (content_hash is read live from disk).
-- Apply with:  psql "$KEN_DATABASE_URL" -f db/init.sql

CREATE TABLE tenants (
    slug       TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO tenants (slug, name) VALUES ('default', 'Default');

CREATE TABLE artifacts (
    tenant_slug TEXT NOT NULL REFERENCES tenants(slug),
    artifact_id TEXT NOT NULL,
    path        TEXT NOT NULL,
    PRIMARY KEY (tenant_slug, artifact_id),
    UNIQUE (tenant_slug, path)
);

CREATE TABLE questions (
    tenant_slug  TEXT NOT NULL REFERENCES tenants(slug),
    artifact_id  TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    question_id  TEXT NOT NULL,
    idx          INTEGER NOT NULL,
    text         TEXT NOT NULL,
    PRIMARY KEY (tenant_slug, artifact_id, question_id)
);
CREATE INDEX idx_questions_tenant_artifact ON questions (tenant_slug, artifact_id);

CREATE TABLE attempts (
    id           BIGSERIAL PRIMARY KEY,
    tenant_slug  TEXT NOT NULL REFERENCES tenants(slug),
    person       TEXT NOT NULL,
    artifact_id  TEXT NOT NULL,
    question_id  TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    passed       BOOLEAN NOT NULL,
    score        DOUBLE PRECISION NOT NULL,
    ts           TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_attempts_tenant_question ON attempts (tenant_slug, question_id);

-- S6 auth (Postgres-only gating).
CREATE TABLE users (
    id            BIGSERIAL PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    tenant_slug   TEXT NOT NULL REFERENCES tenants(slug),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    token      TEXT PRIMARY KEY,
    user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX idx_sessions_user ON sessions (user_id);
