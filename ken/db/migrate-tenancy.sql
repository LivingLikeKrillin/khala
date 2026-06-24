-- Run ONCE on an existing S6 database to add tenant isolation. NOT idempotent
-- (re-running fails on the existing tenants table / columns).
-- Verify the constraint names against the live DB (\d artifacts / \d questions) first;
-- artifacts_pkey / artifacts_path_key / questions_pkey are the Postgres defaults.
BEGIN;

CREATE TABLE tenants (slug TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now());
INSERT INTO tenants (slug, name) VALUES ('default', 'Default');

ALTER TABLE users     ADD COLUMN tenant_slug TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(slug);
ALTER TABLE artifacts ADD COLUMN tenant_slug TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(slug);
ALTER TABLE questions ADD COLUMN tenant_slug TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(slug);
ALTER TABLE attempts  ADD COLUMN tenant_slug TEXT NOT NULL DEFAULT 'default' REFERENCES tenants(slug);

ALTER TABLE artifacts DROP CONSTRAINT artifacts_pkey,     ADD PRIMARY KEY (tenant_slug, artifact_id);
ALTER TABLE artifacts DROP CONSTRAINT artifacts_path_key, ADD UNIQUE (tenant_slug, path);
ALTER TABLE questions DROP CONSTRAINT questions_pkey,     ADD PRIMARY KEY (tenant_slug, artifact_id, question_id);

CREATE INDEX idx_questions_tenant_artifact ON questions (tenant_slug, artifact_id);
CREATE INDEX idx_attempts_tenant_question  ON attempts  (tenant_slug, question_id);

COMMIT;
