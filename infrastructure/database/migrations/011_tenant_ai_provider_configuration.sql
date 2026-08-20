-- Tenant-scoped AI provider configuration and encrypted credential storage.
-- Raw provider keys are accepted write-only by the Admin API, encrypted with pgcrypto,
-- and never returned to clients. The configuration references the encrypted secret row.

CREATE TABLE tenant_secret (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  secret_kind text NOT NULL CHECK(secret_kind IN ('AI_PROVIDER_KEY')),
  ciphertext bytea NOT NULL,
  fingerprint text NOT NULL CHECK(length(fingerprint) = 4),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tenant_ai_configuration (
  tenant_id uuid PRIMARY KEY REFERENCES tenant(id),
  provider text NOT NULL CHECK(provider IN ('openrouter','openai','anthropic')),
  model text NOT NULL DEFAULT '',
  credential_secret_id uuid REFERENCES tenant_secret(id) ON DELETE SET NULL,
  enabled boolean NOT NULL DEFAULT true,
  test_status text NOT NULL DEFAULT 'NOT_TESTED'
    CHECK(test_status IN ('NOT_TESTED','SUCCEEDED','FAILED')),
  tested_at timestamptz,
  last_error text,
  updated_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE tenant_secret ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenant_secret
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE tenant_ai_configuration ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenant_ai_configuration
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
