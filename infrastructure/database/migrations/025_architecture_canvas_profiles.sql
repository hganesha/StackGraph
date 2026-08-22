-- Versioned tenant architecture profiles overlay the shipped canonical reference model.
-- Observed canvases remain projections; only tenant-authored policy and extensions persist.

CREATE TABLE tenant_architecture_profile (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  profile_key text NOT NULL CHECK(profile_key ~ '^[a-z][a-z0-9_.-]{2,127}$'),
  name text NOT NULL CHECK(name<>''),
  reference_model_key text NOT NULL CHECK(reference_model_key<>''),
  reference_model_version text NOT NULL CHECK(reference_model_version<>''),
  version integer NOT NULL DEFAULT 1 CHECK(version>0),
  status text NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','ACTIVE','ARCHIVED')),
  state jsonb NOT NULL CHECK(jsonb_typeof(state)='object'),
  fingerprint text NOT NULL CHECK(fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  created_by text NOT NULL,
  updated_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,profile_key)
);

CREATE TABLE tenant_architecture_profile_revision (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  profile_id uuid NOT NULL REFERENCES tenant_architecture_profile(id) ON DELETE CASCADE,
  version integer NOT NULL CHECK(version>0),
  status text NOT NULL CHECK(status IN ('DRAFT','ACTIVE','ARCHIVED')),
  state jsonb NOT NULL CHECK(jsonb_typeof(state)='object'),
  fingerprint text NOT NULL CHECK(fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  actor_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(profile_id,version)
);

CREATE UNIQUE INDEX uq_tenant_architecture_profile_active
  ON tenant_architecture_profile(tenant_id,reference_model_key,reference_model_version)
  WHERE status='ACTIVE';
CREATE INDEX idx_tenant_architecture_profile_list
  ON tenant_architecture_profile(tenant_id,status,updated_at DESC,id DESC);
CREATE INDEX idx_tenant_architecture_profile_revision
  ON tenant_architecture_profile_revision(tenant_id,profile_id,version DESC);

ALTER TABLE tenant_architecture_profile ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant_architecture_profile_revision ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tenant_architecture_profile
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

CREATE POLICY tenant_isolation ON tenant_architecture_profile_revision
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
