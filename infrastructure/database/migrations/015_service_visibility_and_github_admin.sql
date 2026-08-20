-- Runtime service visibility and Admin parity for existing GitHub App installations.

CREATE TABLE IF NOT EXISTS service_heartbeat (
  service_key text PRIMARY KEY CHECK(service_key ~ '^[a-z][a-z0-9-]{1,63}$'),
  instance_id text NOT NULL CHECK(instance_id <> ''),
  status text NOT NULL DEFAULT 'RUNNING' CHECK(status IN ('RUNNING','DEGRADED','STOPPING')),
  metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),
  started_at timestamptz NOT NULL DEFAULT now(),
  last_heartbeat_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_service_heartbeat_freshness
  ON service_heartbeat(last_heartbeat_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS uq_github_installation_tenant
  ON connector_account(external_account_key)
  WHERE external_account_key LIKE 'github:installation:%';

INSERT INTO connector(
  tenant_id,provider,display_name,external_account_key,credential_reference,
  scopes,status,metadata,created_by,created_at,updated_at
)
SELECT account.tenant_id,'GITHUB_APP',
       'GitHub installation ' || replace(account.external_account_key,'github:installation:',''),
       account.external_account_key,account.credential_reference,
       ARRAY(SELECT jsonb_array_elements_text(account.permissions)),
       CASE account.status WHEN 'ACTIVE' THEN 'CONNECTED'
            WHEN 'DISABLED' THEN 'DISABLED' ELSE 'REVOKED' END,
       jsonb_build_object(
         'connection_mode','GITHUB_APP_INSTALLATION',
         'installation_id',replace(account.external_account_key,'github:installation:',''),
         'ingest_target_id',target.id::text
       ),
       'system:migration-015',account.created_at,account.updated_at
FROM connector_account account
JOIN source_system source ON source.id=account.source_system_id AND source.source_key='github-app'
JOIN LATERAL (
  SELECT id FROM ingest_target
  WHERE connector_account_id=account.id AND target_kind='GITHUB_INSTALLATION'
  ORDER BY created_at,id LIMIT 1
) target ON true
WHERE account.tenant_id IS NOT NULL
  AND account.external_account_key LIKE 'github:installation:%'
ON CONFLICT(tenant_id,provider,external_account_key) DO UPDATE
  SET credential_reference=EXCLUDED.credential_reference,
      scopes=EXCLUDED.scopes,status=EXCLUDED.status,
      metadata=connector.metadata || EXCLUDED.metadata,updated_at=now();
