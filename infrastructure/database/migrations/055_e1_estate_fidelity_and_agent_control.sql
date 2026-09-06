-- E1 / R16: durable estate fidelity, disagreement governance, and agent control plane.

INSERT INTO ontology_entity_type(namespace,entity_type,contract_version) VALUES
  ('INTELLIGENCE','Agent','1.1.0'),
  ('INTELLIGENCE','AgentHarness','1.1.0'),
  ('INTELLIGENCE','AIModel','1.1.0'),
  ('INTELLIGENCE','Prompt','1.1.0'),
  ('INTELLIGENCE','InstructionSet','1.1.0'),
  ('INTELLIGENCE','ContextSource','1.1.0'),
  ('INTELLIGENCE','Tool','1.1.0'),
  ('INTELLIGENCE','Dataset','1.1.0')
ON CONFLICT(namespace,entity_type) DO UPDATE
SET contract_version=EXCLUDED.contract_version;

INSERT INTO predicate_definition(predicate,object_kind,projects_as_edge,contract_version) VALUES
  ('ORCHESTRATES','ENTITY',true,'1.1.0'),
  ('INVOKES','ENTITY',true,'1.1.0'),
  ('GROUNDED_BY','ENTITY',true,'1.1.0'),
  ('ACCESSES','ENTITY',true,'1.1.0'),
  ('FEEDS','ENTITY',true,'1.1.0'),
  ('TRIGGERS','ENTITY',true,'1.1.0'),
  ('PRODUCES','ENTITY',true,'1.1.0')
ON CONFLICT(predicate) DO UPDATE SET
  object_kind=EXCLUDED.object_kind,
  projects_as_edge=EXCLUDED.projects_as_edge,
  contract_version=EXCLUDED.contract_version;

CREATE TABLE estate_component_profile (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  component_entity_id uuid NOT NULL,
  repository_entity_id uuid,
  component_path text NOT NULL CHECK(component_path<>''),
  classifications text[] NOT NULL DEFAULT '{}',
  independently_deployable boolean,
  runtime_entity_id uuid,
  attributes jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(attributes)='object'),
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  method_version text NOT NULL CHECK(method_version<>''),
  source_revision text NOT NULL CHECK(source_revision<>''),
  observed_at timestamptz NOT NULL,
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_to timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(component_entity_id,tenant_id) REFERENCES entity(id,tenant_id),
  FOREIGN KEY(repository_entity_id,tenant_id) REFERENCES entity(id,tenant_id),
  FOREIGN KEY(runtime_entity_id,tenant_id) REFERENCES entity(id,tenant_id),
  UNIQUE(id,tenant_id),
  UNIQUE NULLS NOT DISTINCT(tenant_id,component_entity_id,source_revision,component_path),
  CHECK(valid_to IS NULL OR valid_to>valid_from)
);

CREATE TABLE estate_deployment_profile (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  deployment_entity_id uuid NOT NULL,
  repository_entity_id uuid,
  provider text NOT NULL CHECK(provider<>''),
  workload_kind text NOT NULL CHECK(workload_kind<>''),
  environment text,
  region text,
  resources jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(resources)='array'),
  actions jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(actions)='array'),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'),
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  method_version text NOT NULL CHECK(method_version<>''),
  source_revision text NOT NULL CHECK(source_revision<>''),
  observed_at timestamptz NOT NULL,
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_to timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(deployment_entity_id,tenant_id) REFERENCES entity(id,tenant_id),
  FOREIGN KEY(repository_entity_id,tenant_id) REFERENCES entity(id,tenant_id),
  UNIQUE(id,tenant_id),
  UNIQUE NULLS NOT DISTINCT(tenant_id,deployment_entity_id,source_revision),
  CHECK(valid_to IS NULL OR valid_to>valid_from)
);

CREATE TABLE estate_container_profile (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  image_entity_id uuid NOT NULL,
  repository_entity_id uuid,
  digest text NOT NULL CHECK(digest ~ '^sha256:[a-f0-9]{64}$'),
  tags text[] NOT NULL DEFAULT '{}',
  registry text,
  architecture text,
  operating_system text,
  runtime text,
  build_metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(build_metadata)='object'),
  deployment_metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(deployment_metadata)='object'),
  coverage jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(coverage)='object'),
  source_revision text NOT NULL CHECK(source_revision<>''),
  observed_at timestamptz NOT NULL,
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_to timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(image_entity_id,tenant_id) REFERENCES entity(id,tenant_id),
  FOREIGN KEY(repository_entity_id,tenant_id) REFERENCES entity(id,tenant_id),
  UNIQUE(id,tenant_id),
  UNIQUE(tenant_id,digest,source_revision),
  CHECK(valid_to IS NULL OR valid_to>valid_from)
);

CREATE TABLE estate_container_layer (
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  container_profile_id uuid NOT NULL,
  ordinal integer NOT NULL CHECK(ordinal>=0),
  digest text CHECK(digest IS NULL OR digest ~ '^sha256:[a-f0-9]{64}$'),
  command text,
  size_bytes bigint CHECK(size_bytes IS NULL OR size_bytes>=0),
  PRIMARY KEY(container_profile_id,ordinal),
  FOREIGN KEY(container_profile_id,tenant_id)
    REFERENCES estate_container_profile(id,tenant_id) ON DELETE RESTRICT
);

CREATE TABLE estate_container_package (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  container_profile_id uuid NOT NULL,
  name text NOT NULL CHECK(name<>''),
  version text,
  ecosystem text,
  purl text,
  UNIQUE NULLS NOT DISTINCT(container_profile_id,name,version,ecosystem),
  FOREIGN KEY(container_profile_id,tenant_id)
    REFERENCES estate_container_profile(id,tenant_id) ON DELETE RESTRICT
);

CREATE TABLE estate_profile_evidence (
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  profile_kind text NOT NULL CHECK(profile_kind IN ('COMPONENT','DEPLOYMENT','CONTAINER')),
  profile_id uuid NOT NULL,
  fact_assertion_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(profile_kind,profile_id,fact_assertion_id),
  FOREIGN KEY(fact_assertion_id,tenant_id) REFERENCES fact_assertion(id,tenant_id) ON DELETE RESTRICT
);

CREATE TABLE estate_lineage_edge (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  upstream_entity_id uuid NOT NULL,
  downstream_entity_id uuid NOT NULL,
  lineage_kind text NOT NULL CHECK(lineage_kind IN (
    'COLUMN_TO_TABLE','TABLE_TO_PIPELINE','PIPELINE_TO_FEATURE','FEATURE_TO_MODEL',
    'MODEL_TO_AGENT','AGENT_TO_API','API_TO_PROCESS','DATASET_TO_CAPABILITY','OTHER'
  )),
  fact_assertion_id uuid NOT NULL,
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  observed_at timestamptz NOT NULL,
  valid_to timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(upstream_entity_id,tenant_id) REFERENCES entity(id,tenant_id),
  FOREIGN KEY(downstream_entity_id,tenant_id) REFERENCES entity(id,tenant_id),
  FOREIGN KEY(fact_assertion_id,tenant_id) REFERENCES fact_assertion(id,tenant_id),
  UNIQUE(tenant_id,upstream_entity_id,downstream_entity_id,lineage_kind,fact_assertion_id),
  CHECK(upstream_entity_id<>downstream_entity_id)
);

CREATE TABLE estate_assumption (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  subject_entity_id uuid NOT NULL,
  dimension text NOT NULL CHECK(dimension<>''),
  statement text NOT NULL CHECK(statement<>''),
  status text NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','ACCEPTED','REJECTED','SUPERSEDED')),
  authority text NOT NULL CHECK(authority<>''),
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  last_verified_at timestamptz NOT NULL,
  version integer NOT NULL DEFAULT 1 CHECK(version>0),
  created_by text NOT NULL CHECK(created_by<>''),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(subject_entity_id,tenant_id) REFERENCES entity(id,tenant_id),
  UNIQUE(tenant_id,id),
  UNIQUE(tenant_id,subject_entity_id,dimension,statement)
);

CREATE TABLE estate_assumption_claim (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  assumption_id uuid NOT NULL,
  claim_key text NOT NULL CHECK(claim_key<>''),
  display_value text NOT NULL CHECK(display_value<>''),
  source_key text NOT NULL CHECK(source_key<>''),
  assertion_class text NOT NULL CHECK(assertion_class IN (
    'DECLARED','OBSERVED','INFERRED','CURATED','EXTERNAL_MEASURED'
  )),
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  observed_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(assumption_id,tenant_id) REFERENCES estate_assumption(id,tenant_id) ON DELETE RESTRICT,
  UNIQUE(tenant_id,id),
  UNIQUE(assumption_id,claim_key,source_key)
);

CREATE TABLE estate_assumption_claim_evidence (
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  claim_id uuid NOT NULL,
  fact_assertion_id uuid NOT NULL,
  polarity text NOT NULL CHECK(polarity IN ('SUPPORTING','OPPOSING')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(claim_id,fact_assertion_id,polarity),
  FOREIGN KEY(claim_id,tenant_id) REFERENCES estate_assumption_claim(id,tenant_id) ON DELETE RESTRICT,
  FOREIGN KEY(fact_assertion_id,tenant_id) REFERENCES fact_assertion(id,tenant_id) ON DELETE RESTRICT
);

CREATE TABLE estate_assumption_dependent (
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  assumption_id uuid NOT NULL,
  entity_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(assumption_id,entity_id),
  FOREIGN KEY(assumption_id,tenant_id) REFERENCES estate_assumption(id,tenant_id) ON DELETE RESTRICT,
  FOREIGN KEY(entity_id,tenant_id) REFERENCES entity(id,tenant_id) ON DELETE RESTRICT
);

CREATE TABLE estate_contradiction (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  assumption_id uuid,
  subject_entity_id uuid NOT NULL,
  dimension text NOT NULL CHECK(dimension<>''),
  status text NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','RESOLVED','DISMISSED')),
  severity text NOT NULL DEFAULT 'MEDIUM' CHECK(severity IN ('LOW','MEDIUM','HIGH','CRITICAL')),
  resolution text,
  resolved_by text,
  resolved_at timestamptz,
  version integer NOT NULL DEFAULT 1 CHECK(version>0),
  created_by text NOT NULL CHECK(created_by<>''),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(assumption_id,tenant_id) REFERENCES estate_assumption(id,tenant_id) ON DELETE RESTRICT,
  FOREIGN KEY(subject_entity_id,tenant_id) REFERENCES entity(id,tenant_id),
  UNIQUE(tenant_id,id),
  CHECK((status='OPEN' AND resolved_at IS NULL) OR (status<>'OPEN' AND resolved_at IS NOT NULL))
);

CREATE TABLE estate_contradiction_claim (
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  contradiction_id uuid NOT NULL,
  claim_id uuid NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(contradiction_id,claim_id),
  FOREIGN KEY(contradiction_id,tenant_id) REFERENCES estate_contradiction(id,tenant_id) ON DELETE RESTRICT,
  FOREIGN KEY(claim_id,tenant_id) REFERENCES estate_assumption_claim(id,tenant_id) ON DELETE RESTRICT
);

CREATE TABLE estate_contradiction_resolution (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  contradiction_id uuid NOT NULL,
  from_status text NOT NULL,
  to_status text NOT NULL CHECK(to_status IN ('RESOLVED','DISMISSED')),
  rationale text NOT NULL CHECK(rationale<>''),
  actor_key text NOT NULL CHECK(actor_key<>''),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(contradiction_id,tenant_id) REFERENCES estate_contradiction(id,tenant_id) ON DELETE RESTRICT
);

CREATE TABLE agent_capability_policy (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenant(id),
  policy_key text NOT NULL CHECK(policy_key ~ '^[a-z][a-z0-9._-]{2,127}$'),
  version integer NOT NULL CHECK(version>0),
  status text NOT NULL CHECK(status IN ('DRAFT','ACTIVE','RETIRED')),
  configuration jsonb NOT NULL CHECK(jsonb_typeof(configuration)='object'),
  content_hash text NOT NULL CHECK(content_hash ~ '^sha256:[a-f0-9]{64}$'),
  created_by text NOT NULL CHECK(created_by<>''),
  created_at timestamptz NOT NULL DEFAULT now(),
  activated_at timestamptz,
  UNIQUE NULLS NOT DISTINCT(tenant_id,policy_key,version)
);
CREATE UNIQUE INDEX uq_agent_capability_policy_active
  ON agent_capability_policy(tenant_id,policy_key) WHERE status='ACTIVE';

CREATE TABLE agent_capability_envelope (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  policy_id uuid NOT NULL REFERENCES agent_capability_policy(id),
  actor_key text NOT NULL CHECK(actor_key<>''),
  objective text NOT NULL CHECK(objective<>''),
  environment text NOT NULL CHECK(environment<>''),
  estate_watermark text NOT NULL CHECK(estate_watermark<>''),
  risk_tier text NOT NULL CHECK(risk_tier IN ('TIER_0','TIER_1','TIER_2','TIER_3')),
  context_confidence numeric(5,4) NOT NULL CHECK(context_confidence BETWEEN 0 AND 1),
  decision text NOT NULL CHECK(decision IN ('ALLOW','CONSTRAIN','ESCALATE','DENY')),
  decision_reasons jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(decision_reasons)='array'),
  constraints jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(constraints)='object'),
  evidence_fact_ids uuid[] NOT NULL DEFAULT '{}',
  contradiction_ids uuid[] NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','EXPIRED','REVOKED','CONSUMED')),
  valid_until timestamptz NOT NULL,
  compiled_hash text NOT NULL CHECK(compiled_hash ~ '^sha256:[a-f0-9]{64}$'),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,id),
  UNIQUE(tenant_id,compiled_hash),
  CHECK(valid_until>created_at)
);

CREATE TABLE agent_envelope_operation (
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  envelope_id uuid NOT NULL,
  operation_key text NOT NULL CHECK(operation_key ~ '^[a-z][a-z0-9._:-]{2,127}$'),
  band text NOT NULL CHECK(band IN ('READ','EXECUTE','CONDITIONAL','PROHIBITED','ESCALATE')),
  constraints jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(constraints)='object'),
  PRIMARY KEY(envelope_id,operation_key),
  FOREIGN KEY(envelope_id,tenant_id) REFERENCES agent_capability_envelope(id,tenant_id) ON DELETE RESTRICT
);

CREATE TABLE agent_approval (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  envelope_id uuid NOT NULL,
  operation_key text NOT NULL,
  reason_code text NOT NULL CHECK(reason_code ~ '^[A-Z][A-Z0-9_]{2,63}$'),
  status text NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','APPROVED','REJECTED','EXPIRED')),
  requested_by text NOT NULL CHECK(requested_by<>''),
  decided_by text,
  rationale text,
  version integer NOT NULL DEFAULT 1 CHECK(version>0),
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  decided_at timestamptz,
  FOREIGN KEY(envelope_id,tenant_id) REFERENCES agent_capability_envelope(id,tenant_id) ON DELETE RESTRICT,
  UNIQUE(tenant_id,id),
  CHECK((status='PENDING' AND decided_at IS NULL) OR (status<>'PENDING' AND decided_at IS NOT NULL))
);

CREATE TABLE agent_kill_switch (
  tenant_id uuid PRIMARY KEY REFERENCES tenant(id) ON DELETE RESTRICT,
  engaged boolean NOT NULL DEFAULT true,
  reason text NOT NULL DEFAULT 'Agent execution is disabled until explicitly enabled.',
  version integer NOT NULL DEFAULT 1 CHECK(version>0),
  updated_by text NOT NULL CHECK(updated_by<>''),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE agent_authorization_decision (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  envelope_id uuid NOT NULL,
  operation_key text NOT NULL,
  decision text NOT NULL CHECK(decision IN ('ALLOW','CONSTRAIN','ESCALATE','DENY')),
  reason_codes text[] NOT NULL DEFAULT '{}',
  approval_id uuid,
  request_fingerprint text NOT NULL CHECK(request_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  actor_key text NOT NULL CHECK(actor_key<>''),
  decided_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(envelope_id,tenant_id) REFERENCES agent_capability_envelope(id,tenant_id) ON DELETE RESTRICT,
  FOREIGN KEY(approval_id,tenant_id) REFERENCES agent_approval(id,tenant_id) ON DELETE RESTRICT,
  UNIQUE(tenant_id,id)
);

CREATE TABLE agent_flight_record (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  envelope_id uuid NOT NULL,
  objective text NOT NULL CHECK(objective<>''),
  status text NOT NULL DEFAULT 'ACTIVE' CHECK(status IN ('ACTIVE','SUCCEEDED','FAILED','ABORTED')),
  event_count integer NOT NULL DEFAULT 0 CHECK(event_count>=0),
  chain_head text CHECK(chain_head IS NULL OR chain_head ~ '^sha256:[a-f0-9]{64}$'),
  outcome jsonb CHECK(outcome IS NULL OR jsonb_typeof(outcome)='object'),
  started_by text NOT NULL CHECK(started_by<>''),
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  FOREIGN KEY(envelope_id,tenant_id) REFERENCES agent_capability_envelope(id,tenant_id) ON DELETE RESTRICT,
  UNIQUE(tenant_id,id),
  CHECK((status='ACTIVE' AND completed_at IS NULL) OR (status<>'ACTIVE' AND completed_at IS NOT NULL))
);

CREATE TABLE agent_flight_event (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  flight_record_id uuid NOT NULL,
  sequence integer NOT NULL CHECK(sequence>=1),
  event_type text NOT NULL CHECK(event_type IN (
    'OBJECTIVE','CONTEXT','TOOL','CALL','DECISION','ACTION','ASSET','VERIFICATION','OUTCOME'
  )),
  system_boundary text NOT NULL CHECK(system_boundary<>''),
  payload jsonb NOT NULL CHECK(jsonb_typeof(payload)='object'),
  previous_hash text CHECK(previous_hash IS NULL OR previous_hash ~ '^sha256:[a-f0-9]{64}$'),
  event_hash text NOT NULL CHECK(event_hash ~ '^sha256:[a-f0-9]{64}$'),
  occurred_at timestamptz NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(flight_record_id,tenant_id) REFERENCES agent_flight_record(id,tenant_id) ON DELETE RESTRICT,
  UNIQUE(flight_record_id,sequence),
  UNIQUE(flight_record_id,event_hash)
);

CREATE TABLE agent_control_drill (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  drill_kind text NOT NULL CHECK(drill_kind IN ('KILL_SWITCH','ROLLBACK','AUDIT_RECONSTRUCTION')),
  status text NOT NULL CHECK(status IN ('PASSED','FAILED')),
  checks jsonb NOT NULL CHECK(jsonb_typeof(checks)='array'),
  performed_by text NOT NULL CHECK(performed_by<>''),
  performed_at timestamptz NOT NULL DEFAULT now()
);

CREATE FUNCTION stackgraph_prevent_agent_audit_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'agent authorization and flight history is immutable';
END $$;
CREATE TRIGGER trg_agent_authorization_immutable
  BEFORE UPDATE OR DELETE ON agent_authorization_decision
  FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_agent_audit_change();
CREATE TRIGGER trg_agent_flight_event_immutable
  BEFORE UPDATE OR DELETE ON agent_flight_event
  FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_agent_audit_change();
CREATE TRIGGER trg_agent_control_drill_immutable
  BEFORE UPDATE OR DELETE ON agent_control_drill
  FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_agent_audit_change();

CREATE INDEX idx_component_profile_current ON estate_component_profile(tenant_id,component_entity_id) WHERE valid_to IS NULL;
CREATE INDEX idx_deployment_profile_current ON estate_deployment_profile(tenant_id,repository_entity_id) WHERE valid_to IS NULL;
CREATE INDEX idx_container_profile_current ON estate_container_profile(tenant_id,repository_entity_id) WHERE valid_to IS NULL;
CREATE INDEX idx_lineage_upstream_current ON estate_lineage_edge(tenant_id,upstream_entity_id) WHERE valid_to IS NULL;
CREATE INDEX idx_lineage_downstream_current ON estate_lineage_edge(tenant_id,downstream_entity_id) WHERE valid_to IS NULL;
CREATE INDEX idx_assumption_subject_open ON estate_assumption(tenant_id,subject_entity_id,dimension) WHERE status='OPEN';
CREATE INDEX idx_contradiction_subject_open ON estate_contradiction(tenant_id,subject_entity_id,dimension) WHERE status='OPEN';
CREATE INDEX idx_agent_envelope_active ON agent_capability_envelope(tenant_id,actor_key,valid_until) WHERE status='ACTIVE';
CREATE INDEX idx_agent_approval_pending ON agent_approval(tenant_id,envelope_id,operation_key,expires_at) WHERE status='PENDING';
CREATE INDEX idx_agent_authorization_timeline ON agent_authorization_decision(tenant_id,envelope_id,decided_at DESC);
CREATE INDEX idx_agent_flight_timeline ON agent_flight_record(tenant_id,started_at DESC);
CREATE INDEX idx_agent_flight_event_sequence ON agent_flight_event(tenant_id,flight_record_id,sequence);

ALTER TABLE agent_capability_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_capability_policy FORCE ROW LEVEL SECURITY;
CREATE POLICY agent_capability_policy_visibility ON agent_capability_policy
  USING(tenant_id IS NULL OR tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

DO $$ DECLARE table_name text; BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'estate_component_profile','estate_deployment_profile','estate_container_profile',
    'estate_container_layer','estate_container_package','estate_profile_evidence','estate_lineage_edge',
    'estate_assumption','estate_assumption_claim','estate_assumption_claim_evidence',
    'estate_assumption_dependent','estate_contradiction','estate_contradiction_claim',
    'estate_contradiction_resolution','agent_capability_envelope','agent_envelope_operation',
    'agent_approval','agent_kill_switch','agent_authorization_decision','agent_flight_record',
    'agent_flight_event','agent_control_drill'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',table_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',table_name);
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id=stackgraph_current_tenant_id()) WITH CHECK (tenant_id=stackgraph_current_tenant_id())',
      table_name
    );
  END LOOP;
END $$;

WITH configuration AS (
  SELECT '{
    "default_ttl_seconds":900,
    "minimum_context_confidence":0.80,
    "approval_risk_tiers":["TIER_0"],
    "destructive_operations":["delete","destroy","drop","purge","rollback","force_push"],
    "prohibited_operations":["disable_audit","bypass_policy","export_credentials"],
    "maximum_operations":100
  }'::jsonb AS value
)
INSERT INTO agent_capability_policy(
  tenant_id,policy_key,version,status,configuration,content_hash,created_by,activated_at
)
SELECT NULL,'default-agent-control',1,'ACTIVE',value,
       'sha256:'||encode(digest(value::text,'sha256'),'hex'),'migration:055',now()
FROM configuration;
