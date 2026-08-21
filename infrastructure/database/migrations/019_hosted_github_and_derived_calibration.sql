-- One-time GitHub App setup state and reproducible, server-derived calibration evidence.

CREATE TABLE github_installation_setup (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  actor_key text NOT NULL CHECK(actor_key<>''),
  state_hash text NOT NULL UNIQUE CHECK(state_hash ~ '^sha256:[a-f0-9]{64}$'),
  return_to text NOT NULL CHECK(return_to ~ '^/[^/].*|^/$'),
  expires_at timestamptz NOT NULL,
  consumed_at timestamptz,
  installation_id text CHECK(installation_id IS NULL OR installation_id ~ '^[1-9][0-9]{0,19}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(expires_at>created_at)
);

CREATE INDEX idx_github_installation_setup_expiry
  ON github_installation_setup(tenant_id,expires_at)
  WHERE consumed_at IS NULL;

ALTER TABLE github_installation_setup ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON github_installation_setup
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

ALTER TABLE modernization_calibration_corpus
  ADD COLUMN case_manifest jsonb NOT NULL DEFAULT '[]'
    CHECK(jsonb_typeof(case_manifest)='array'),
  ADD COLUMN metrics_source_version text NOT NULL DEFAULT 'client-supplied/v1'
    CHECK(metrics_source_version<>'');
