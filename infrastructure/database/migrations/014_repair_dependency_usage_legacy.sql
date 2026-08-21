-- Reconcile the pre-canonical migration 005 package-surface uniqueness rule.
--
-- The legacy local-development migration made analysis_fingerprint globally
-- unique. Canonical migration 005 correctly scopes that identity by tenant.
-- Fresh databases already have the desired constraint, so this migration is
-- intentionally idempotent.

DO $$
DECLARE
  legacy_definition text;
BEGIN
  SELECT pg_get_constraintdef(oid)
  INTO legacy_definition
  FROM pg_constraint
  WHERE conrelid='package_api_surface'::regclass
    AND conname='package_api_surface_analysis_fingerprint_key';

  IF legacy_definition IS NOT NULL THEN
    IF legacy_definition <> 'UNIQUE (analysis_fingerprint)' THEN
      RAISE EXCEPTION
        'unexpected package_api_surface_analysis_fingerprint_key definition: %',
        legacy_definition;
    END IF;
    ALTER TABLE package_api_surface
      DROP CONSTRAINT package_api_surface_analysis_fingerprint_key;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conrelid='package_api_surface'::regclass
      AND pg_get_constraintdef(oid) =
        'UNIQUE NULLS NOT DISTINCT (tenant_id, analysis_fingerprint)'
  ) THEN
    ALTER TABLE package_api_surface
      ADD CONSTRAINT package_api_surface_tenant_analysis_fingerprint_key
      UNIQUE NULLS NOT DISTINCT (tenant_id,analysis_fingerprint);
  END IF;
END $$;
