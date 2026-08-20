-- Attribute repository intelligence jobs to the tenant provider configuration
-- that will execute them. This keeps publish-triggered jobs and Admin-triggered
-- reanalysis on the same idempotency and status fingerprint.

CREATE OR REPLACE FUNCTION tenant_ai_configuration_fingerprint(
  p_provider text,
  p_model text,
  p_secret_id uuid
) RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
  SELECT 'sha256:' || encode(
    digest(
      convert_to(
        'tenant-ai-v1' || chr(31) || p_provider || chr(31) || p_model
          || chr(31) || p_secret_id::text,
        'UTF8'
      ),
      'sha256'
    ),
    'hex'
  )
$$;

CREATE OR REPLACE FUNCTION enqueue_repository_intelligence_on_publish() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status='PUBLISHED'
     AND OLD.status IS DISTINCT FROM NEW.status
     AND NEW.completeness='COMPLETE'
     AND NEW.extractor_key='repository-dependency-usage' THEN
    INSERT INTO intelligence_job(
      tenant_id,repository_entity_id,source_snapshot_id,source_revision,
      job_kind,configuration_fingerprint
    )
    SELECT NEW.tenant_id,repository.id,NEW.id,NEW.source_revision,
           'REPOSITORY_MODERNIZATION',
           coalesce(
             tenant_ai_configuration_fingerprint(
               configuration.provider,
               configuration.model,
               configuration.credential_secret_id
             ),
             'snapshot-v1'
           )
    FROM ingest_target target
    JOIN entity repository
      ON repository.tenant_id=NEW.tenant_id
     AND repository.namespace='ENTERPRISE'
     AND repository.entity_type='Repository'
     AND repository.canonical_key=target.target_key
    LEFT JOIN tenant_ai_configuration configuration
      ON configuration.tenant_id=NEW.tenant_id
     AND configuration.enabled
     AND configuration.model<>''
     AND configuration.credential_secret_id IS NOT NULL
    WHERE target.id=NEW.ingest_target_id
    ON CONFLICT DO NOTHING;
  END IF;
  RETURN NEW;
END $$;
