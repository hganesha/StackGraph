-- Phase 2A/2B: bounded action ontology, immutable Mutation IR, and durable simulation queue.

CREATE TABLE phase2_feature_flag (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenant(id),
  flag_key text NOT NULL CHECK(flag_key IN (
    'SCANNER_PROFILES','CHANGE_COMPILER','CHANGE_SIMULATION','AI_INTERPRETATION','CHANGE_EXECUTION'
  )),
  enabled boolean NOT NULL DEFAULT false,
  updated_by text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT(tenant_id,flag_key)
);

CREATE TABLE action_capability (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenant(id),
  predicate text NOT NULL CHECK(predicate IN ('UPGRADE','REPLACE','REMOVE','DEPRECATE','MIGRATE','MOVE')),
  subject_type text NOT NULL CHECK(subject_type IN ('Package','Runtime','Framework','API','Database','Service')),
  ontology_version text NOT NULL,
  target_schema jsonb NOT NULL CHECK(jsonb_typeof(target_schema)='object'),
  validation_rules jsonb NOT NULL CHECK(jsonb_typeof(validation_rules)='object'),
  scope_rules jsonb NOT NULL CHECK(jsonb_typeof(scope_rules)='object'),
  semantic_provider text NOT NULL,
  provider_version text NOT NULL,
  lifecycle text NOT NULL CHECK(lifecycle IN ('ACTIVE','DISABLED','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT(tenant_id,predicate,subject_type,ontology_version)
);

CREATE TABLE impact_policy (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenant(id),
  policy_key text NOT NULL CHECK(policy_key ~ '^[a-z][a-z0-9.-]{2,127}$'),
  predicate text NOT NULL CHECK(predicate IN ('UPGRADE','REPLACE','REMOVE','DEPRECATE','MIGRATE','MOVE')),
  subject_type text NOT NULL,
  version integer NOT NULL CHECK(version>0),
  status text NOT NULL CHECK(status IN ('DRAFT','ACTIVE','RETIRED')),
  configuration jsonb NOT NULL CHECK(jsonb_typeof(configuration)='object'),
  content_hash text NOT NULL CHECK(content_hash ~ '^sha256:[a-f0-9]{64}$'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  activated_at timestamptz,
  UNIQUE NULLS NOT DISTINCT(tenant_id,policy_key,version)
);

CREATE UNIQUE INDEX uq_impact_policy_active
  ON impact_policy(tenant_id,policy_key) WHERE status='ACTIVE';

CREATE TABLE change_set (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  schema_version text NOT NULL DEFAULT 'changeset/1.0.0' CHECK(schema_version='changeset/1.0.0'),
  atomic boolean NOT NULL DEFAULT true,
  lifecycle text NOT NULL CHECK(lifecycle IN (
    'DRAFT','VALIDATED','REJECTED','SUPERSEDED','SUBMITTED','EXECUTED','CANCELLED'
  )),
  input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  idempotency_key text NOT NULL CHECK(idempotency_key<>''),
  provenance jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(provenance)='object'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  superseded_by uuid REFERENCES change_set(id),
  UNIQUE(tenant_id,idempotency_key),
  UNIQUE(tenant_id,input_fingerprint)
);

CREATE TABLE mutation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  change_set_id uuid NOT NULL REFERENCES change_set(id) ON DELETE RESTRICT,
  ordinal integer NOT NULL CHECK(ordinal>=0),
  schema_version text NOT NULL DEFAULT 'mutation/1.0.0' CHECK(schema_version='mutation/1.0.0'),
  predicate text NOT NULL CHECK(predicate IN ('UPGRADE','REPLACE','REMOVE','DEPRECATE','MIGRATE','MOVE')),
  subject_entity_id uuid NOT NULL REFERENCES entity(id),
  subject_resolution text NOT NULL CHECK(subject_resolution='RESOLVED'),
  before_state jsonb NOT NULL CHECK(jsonb_typeof(before_state)='object'),
  after_state jsonb NOT NULL CHECK(jsonb_typeof(after_state)='object'),
  scope jsonb NOT NULL CHECK(jsonb_typeof(scope)='object'),
  constraints jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(constraints)='object'),
  provenance jsonb NOT NULL CHECK(jsonb_typeof(provenance)='object'),
  input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  lifecycle text NOT NULL CHECK(lifecycle IN (
    'DRAFT','VALIDATED','REJECTED','SUPERSEDED','SUBMITTED','EXECUTED','CANCELLED'
  )),
  validation_errors jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(validation_errors)='array'),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(change_set_id,ordinal),
  UNIQUE(tenant_id,input_fingerprint)
);

CREATE TABLE simulation_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  change_set_id uuid NOT NULL REFERENCES change_set(id) ON DELETE RESTRICT,
  idempotency_key text NOT NULL CHECK(idempotency_key<>''),
  status text NOT NULL CHECK(status IN (
    'QUEUED','RUNNING','SUCCEEDED','LIMITED','NOT_SIMULATABLE','FAILED','CANCELLED'
  )),
  estate_watermark text NOT NULL,
  policy_id uuid REFERENCES impact_policy(id),
  policy_version text NOT NULL,
  provider_version text NOT NULL,
  scanner_versions text[] NOT NULL DEFAULT '{}',
  input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  result_hash text CHECK(result_hash IS NULL OR result_hash ~ '^sha256:[a-f0-9]{64}$'),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'),
  failure_detail jsonb,
  attempt integer NOT NULL DEFAULT 0 CHECK(attempt>=0),
  max_attempts integer NOT NULL DEFAULT 5 CHECK(max_attempts>0),
  available_at timestamptz NOT NULL DEFAULT now(),
  leased_by text,
  leased_until timestamptz,
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,idempotency_key),
  UNIQUE(tenant_id,input_fingerprint)
);

CREATE TABLE simulation_finding (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  simulation_run_id uuid NOT NULL REFERENCES simulation_run(id) ON DELETE RESTRICT,
  rule_key text NOT NULL,
  rule_version text NOT NULL,
  classification text NOT NULL CHECK(classification IN (
    'DIRECT','TRANSITIVE','CONTEXT','STOP','INFORMATIONAL'
  )),
  severity text NOT NULL CHECK(severity IN ('INFO','LOW','MEDIUM','HIGH','CRITICAL')),
  title text NOT NULL,
  detail text NOT NULL,
  affected_entity_id uuid REFERENCES entity(id),
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  evidence_fact_ids uuid[] NOT NULL DEFAULT '{}',
  path_entity_ids uuid[] NOT NULL DEFAULT '{}',
  fact_payload jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(fact_payload)='object'),
  deterministic_key text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(simulation_run_id,deterministic_key)
);

CREATE TABLE simulation_interpretation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  simulation_run_id uuid NOT NULL UNIQUE REFERENCES simulation_run(id) ON DELETE RESTRICT,
  status text NOT NULL CHECK(status IN ('AVAILABLE','UNAVAILABLE','QUARANTINED')),
  provider text,
  model text,
  prompt_version text,
  risk text,
  explanation text,
  rollout jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(rollout)='array'),
  verification jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(verification)='array'),
  cited_finding_ids uuid[] NOT NULL DEFAULT '{}',
  limitation text,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE modernization_recommendation
  ADD COLUMN proposed_change_set_id uuid REFERENCES change_set(id),
  ADD COLUMN not_simulatable_reason jsonb;

CREATE FUNCTION stackgraph_prevent_terminal_change_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.lifecycle IN ('VALIDATED','REJECTED','SUPERSEDED','SUBMITTED','EXECUTED','CANCELLED') THEN
    RAISE EXCEPTION 'terminal Mutation IR is immutable';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_mutation_immutable
  BEFORE UPDATE OR DELETE ON mutation
  FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_terminal_change_mutation();

CREATE FUNCTION stackgraph_prevent_terminal_simulation_mutation()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status IN ('SUCCEEDED','LIMITED','NOT_SIMULATABLE','FAILED','CANCELLED') THEN
    RAISE EXCEPTION 'terminal SimulationRun is immutable';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER trg_simulation_immutable
  BEFORE UPDATE OR DELETE ON simulation_run
  FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_terminal_simulation_mutation();

CREATE INDEX idx_action_capability_lookup
  ON action_capability(predicate,subject_type,lifecycle);
CREATE INDEX idx_change_set_tenant_created
  ON change_set(tenant_id,created_at DESC);
CREATE INDEX idx_mutation_change_set
  ON mutation(tenant_id,change_set_id,ordinal);
CREATE INDEX idx_simulation_claim
  ON simulation_run(status,available_at,leased_until,created_at);
CREATE INDEX idx_simulation_change_set
  ON simulation_run(tenant_id,change_set_id,created_at DESC);
CREATE INDEX idx_simulation_finding_run
  ON simulation_finding(tenant_id,simulation_run_id,classification);

ALTER TABLE phase2_feature_flag ENABLE ROW LEVEL SECURITY;
ALTER TABLE action_capability ENABLE ROW LEVEL SECURITY;
ALTER TABLE impact_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE change_set ENABLE ROW LEVEL SECURITY;
ALTER TABLE mutation ENABLE ROW LEVEL SECURITY;
ALTER TABLE simulation_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE simulation_finding ENABLE ROW LEVEL SECURITY;
ALTER TABLE simulation_interpretation ENABLE ROW LEVEL SECURITY;

CREATE POLICY phase2_feature_flag_visibility ON phase2_feature_flag
  USING(tenant_id IS NULL OR tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
CREATE POLICY action_capability_visibility ON action_capability
  USING(tenant_id IS NULL OR tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
CREATE POLICY impact_policy_visibility ON impact_policy
  USING(tenant_id IS NULL OR tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

DO $$ DECLARE table_name text; BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'change_set','mutation','simulation_run','simulation_finding','simulation_interpretation'
  ] LOOP
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id=stackgraph_current_tenant_id()) WITH CHECK (tenant_id=stackgraph_current_tenant_id())',
      table_name
    );
  END LOOP;
END $$;

INSERT INTO phase2_feature_flag(tenant_id,flag_key,enabled,updated_by) VALUES
  (NULL,'SCANNER_PROFILES',false,'migration:047'),
  (NULL,'CHANGE_COMPILER',true,'migration:047'),
  (NULL,'CHANGE_SIMULATION',true,'migration:047'),
  (NULL,'AI_INTERPRETATION',false,'migration:047'),
  (NULL,'CHANGE_EXECUTION',false,'migration:047');

INSERT INTO action_capability(
  tenant_id,predicate,subject_type,ontology_version,target_schema,validation_rules,
  scope_rules,semantic_provider,provider_version,lifecycle
) VALUES (
  NULL,'UPGRADE','Package','actions/1.0.0',
  '{"type":"object","required":["version"],"properties":{"version":{"type":"string","minLength":1}}}',
  '{"exact_subject":true,"exact_target":true,"require_observed_scope":true,"max_mutations":20}',
  '{"kinds":["ESTATE","REPOSITORY","COMPONENT"],"requires_evidence":true}',
  'package-registry','package-registry/1.0.0','ACTIVE'
);

WITH configuration AS (
  SELECT '{
    "max_depth":4,
    "max_nodes":100000,
    "max_edges":500000,
    "minimum_confidence":0.80,
    "edges":[
      {"predicate":"DEPENDS_ON","direction":"INBOUND","classification":"DIRECT","max_depth":1},
      {"predicate":"CONTAINS","direction":"INBOUND","classification":"CONTEXT","max_depth":2},
      {"predicate":"SUPPORTS","direction":"OUTBOUND","classification":"CONTEXT","max_depth":3},
      {"predicate":"BELONGS_TO","direction":"OUTBOUND","classification":"CONTEXT","max_depth":3}
    ],
    "stop_conditions":["LOW_CONFIDENCE","UNRESOLVED_IDENTITY","PARTIAL_SOURCE","TRAVERSAL_BUDGET"]
  }'::jsonb AS value
)
INSERT INTO impact_policy(
  tenant_id,policy_key,predicate,subject_type,version,status,configuration,content_hash,
  created_by,activated_at
)
SELECT NULL,'upgrade-package','UPGRADE','Package',1,'ACTIVE',value,
       'sha256:'||encode(digest(value::text,'sha256'),'hex'),'migration:047',now()
FROM configuration;
