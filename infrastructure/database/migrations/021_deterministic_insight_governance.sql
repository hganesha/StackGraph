-- Tenant-governed deterministic insight rules. Findings are derived from current facts at
-- read time so counts and impact paths cannot drift from the bitemporal graph.

CREATE TABLE deterministic_insight_rule_policy (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  rule_key text NOT NULL CHECK(rule_key ~ '^[a-z][a-z0-9_.-]{2,127}$'),
  enabled boolean NOT NULL DEFAULT true,
  severity text NOT NULL CHECK(severity IN ('CRITICAL','HIGH','MEDIUM','LOW','INFO')),
  minimum_repositories integer NOT NULL DEFAULT 1 CHECK(minimum_repositories>0),
  configuration jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(configuration)='object'),
  version integer NOT NULL DEFAULT 1 CHECK(version>0),
  updated_by text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,rule_key)
);

CREATE TABLE deterministic_insight_rule_policy_revision (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  rule_policy_id uuid NOT NULL REFERENCES deterministic_insight_rule_policy(id) ON DELETE CASCADE,
  prior_version integer NOT NULL CHECK(prior_version>=0),
  resulting_version integer NOT NULL CHECK(resulting_version=prior_version+1),
  enabled boolean NOT NULL,
  severity text NOT NULL CHECK(severity IN ('CRITICAL','HIGH','MEDIUM','LOW','INFO')),
  minimum_repositories integer NOT NULL CHECK(minimum_repositories>0),
  configuration jsonb NOT NULL CHECK(jsonb_typeof(configuration)='object'),
  actor_key text NOT NULL,
  changed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(rule_policy_id,resulting_version)
);

CREATE INDEX idx_deterministic_rule_policy_tenant
  ON deterministic_insight_rule_policy(tenant_id,enabled,rule_key);

ALTER TABLE deterministic_insight_rule_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE deterministic_insight_rule_policy_revision ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON deterministic_insight_rule_policy
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

CREATE POLICY tenant_isolation ON deterministic_insight_rule_policy_revision
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
