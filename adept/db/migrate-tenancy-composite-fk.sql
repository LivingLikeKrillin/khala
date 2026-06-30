-- Run ONCE on a DB already migrated to tenant isolation (migrate-tenancy.sql applied).
-- NOT idempotent. Verify the single-column FK constraint names against the live DB first
-- (\d questions / \d attempts) — questions_tenant_slug_fkey / attempts_tenant_slug_fkey are
-- the Postgres defaults. The ADD FK fails loudly if any questions/attempts row references a
-- (tenant_slug, artifact_id) absent from artifacts (a real integrity error to surface).
BEGIN;
ALTER TABLE questions DROP CONSTRAINT questions_tenant_slug_fkey;
ALTER TABLE attempts  DROP CONSTRAINT attempts_tenant_slug_fkey;
-- Name the new composite FKs explicitly so future migrations can DROP by a known name.
ALTER TABLE questions ADD CONSTRAINT questions_artifact_fk FOREIGN KEY (tenant_slug, artifact_id) REFERENCES artifacts (tenant_slug, artifact_id);
ALTER TABLE attempts  ADD CONSTRAINT attempts_artifact_fk  FOREIGN KEY (tenant_slug, artifact_id) REFERENCES artifacts (tenant_slug, artifact_id);
COMMIT;
