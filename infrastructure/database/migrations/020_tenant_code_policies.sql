-- Tenant-specific technology policy overlays and evidence-backed repository evaluation.
-- The curated StackGraph function catalog remains primary. Custom functions extend it for
-- tenant-specific or otherwise unclassified technology usage.

CREATE TABLE tenant_code_function (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  function_key text NOT NULL CHECK(function_key ~ '^[a-z][a-z0-9.-]{1,127}$'),
  name text NOT NULL CHECK(name <> ''),
  description text NOT NULL DEFAULT '',
  domain_key text NOT NULL CHECK(domain_key ~ '^[a-z][a-z0-9.-]{1,127}$'),
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','RETIRED')),
  created_by text NOT NULL,
  updated_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,function_key)
);

CREATE TABLE tenant_code_policy (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  function_key text NOT NULL CHECK(function_key ~ '^[a-z][a-z0-9.-]{1,127}$'),
  function_source text NOT NULL CHECK(function_source IN ('PRIMARY','CUSTOM')),
  allowed_technology_ids uuid[] NOT NULL DEFAULT '{}',
  prohibited_technology_ids uuid[] NOT NULL DEFAULT '{}',
  policy_fingerprint text NOT NULL CHECK(policy_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  updated_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,function_key),
  CHECK(NOT allowed_technology_ids && prohibited_technology_ids)
);

CREATE TABLE repository_code_policy_evaluation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  policy_set_fingerprint text NOT NULL CHECK(policy_set_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  evidence_fingerprint text NOT NULL CHECK(evidence_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  status text NOT NULL CHECK(status IN ('COMPLIANT','MISALIGNED','UNASSESSED')),
  violation_count integer NOT NULL DEFAULT 0 CHECK(violation_count >= 0),
  unclassified_count integer NOT NULL DEFAULT 0 CHECK(unclassified_count >= 0),
  details jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(details)='object'),
  evaluated_by text NOT NULL,
  evaluated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,repository_entity_id,policy_set_fingerprint,evidence_fingerprint)
);

CREATE INDEX idx_tenant_code_function_active
  ON tenant_code_function(tenant_id,status,function_key);
CREATE INDEX idx_tenant_code_policy_function
  ON tenant_code_policy(tenant_id,function_key);
CREATE INDEX idx_repository_code_policy_latest
  ON repository_code_policy_evaluation(tenant_id,repository_entity_id,evaluated_at DESC,id DESC);

ALTER TABLE tenant_code_function ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenant_code_function
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE tenant_code_policy ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenant_code_policy
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE repository_code_policy_evaluation ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON repository_code_policy_evaluation
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
