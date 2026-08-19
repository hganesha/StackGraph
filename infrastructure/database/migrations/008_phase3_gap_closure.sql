CREATE TABLE code_implementation_summary (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  source_snapshot_id uuid NOT NULL REFERENCES source_snapshot(id) ON DELETE CASCADE,
  repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  fact_assertion_id uuid NOT NULL UNIQUE REFERENCES fact_assertion(id) ON DELETE CASCADE,
  source_revision text NOT NULL,
  language text NOT NULL CHECK(language IN ('python','javascript')),
  symbol_kind text NOT NULL CHECK(symbol_kind IN ('FUNCTION','CLASS')),
  qualified_name text NOT NULL,
  path text NOT NULL,
  line_start integer NOT NULL CHECK(line_start > 0),
  line_end integer NOT NULL CHECK(line_end >= line_start),
  structural_fingerprint text NOT NULL CHECK(structural_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  semantic_tokens text[] NOT NULL DEFAULT '{}',
  dependency_keys text[] NOT NULL DEFAULT '{}',
  covering_tests text[] NOT NULL DEFAULT '{}',
  dynamic_signals text[] NOT NULL DEFAULT '{}',
  touchpoints jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(touchpoints)='array'),
  vendored boolean NOT NULL DEFAULT false,
  completeness text NOT NULL CHECK(completeness IN ('COMPLETE','PARTIAL')),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,repository_entity_id,source_revision,path,qualified_name,line_start,structural_fingerprint)
);
CREATE INDEX idx_code_implementation_repository
  ON code_implementation_summary(tenant_id,repository_entity_id,source_revision,path);
CREATE INDEX idx_code_implementation_structure
  ON code_implementation_summary(tenant_id,structural_fingerprint,source_revision);
CREATE INDEX idx_code_implementation_tokens
  ON code_implementation_summary USING gin(semantic_tokens);

CREATE TABLE modernization_policy (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  policy_key text NOT NULL CHECK(policy_key ~ '^[a-z][a-z0-9_.-]{2,127}$'),
  version text NOT NULL,
  status text NOT NULL CHECK(status IN ('DRAFT','ACTIVE','RETIRED')),
  runtime_versions jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(runtime_versions)='object'),
  allowed_licenses text[] NOT NULL DEFAULT '{}',
  denied_option_keys text[] NOT NULL DEFAULT '{}',
  allowed_security_statuses text[] NOT NULL DEFAULT ARRAY['CLEAR','UNKNOWN']::text[],
  required_policy_tags text[] NOT NULL DEFAULT '{}',
  metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),
  content_hash text NOT NULL CHECK(content_hash ~ '^sha256:[a-f0-9]{64}$'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,policy_key,version)
);
CREATE UNIQUE INDEX uq_modernization_policy_active
  ON modernization_policy(tenant_id,policy_key) WHERE status='ACTIVE';

CREATE TABLE modernization_internal_component (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  component_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  capability_definition_id uuid NOT NULL REFERENCES capability_definition(id),
  component_key text NOT NULL,
  version text NOT NULL,
  status text NOT NULL CHECK(status IN ('APPROVED','DEPRECATED','BLOCKED')),
  api_symbols text[] NOT NULL DEFAULT '{}',
  runtime_constraints jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(runtime_constraints)='object'),
  behavior_claims jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(behavior_claims)='array'),
  license text,
  security_status text NOT NULL DEFAULT 'UNKNOWN'
    CHECK(security_status IN ('CLEAR','WARN','BLOCKED','UNKNOWN')),
  policy_tags text[] NOT NULL DEFAULT '{}',
  supporting_fact_ids uuid[] NOT NULL DEFAULT '{}',
  metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,component_key,version)
);
CREATE INDEX idx_modernization_internal_capability
  ON modernization_internal_component(tenant_id,capability_definition_id,status);

ALTER TABLE modernization_candidate
  ADD COLUMN source_code_unit_ids uuid[] NOT NULL DEFAULT '{}';

CREATE TABLE modernization_option_evaluation (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  modernization_option_id uuid NOT NULL UNIQUE
    REFERENCES modernization_option(id) ON DELETE CASCADE,
  policy_id uuid REFERENCES modernization_policy(id),
  capability_fit text NOT NULL CHECK(capability_fit IN ('PASS','FAIL','UNKNOWN')),
  api_fit text NOT NULL CHECK(api_fit IN ('PASS','FAIL','UNKNOWN')),
  behavior_fit text NOT NULL CHECK(behavior_fit IN ('PASS','FAIL','UNKNOWN')),
  runtime_fit text NOT NULL CHECK(runtime_fit IN ('PASS','FAIL','UNKNOWN')),
  license_fit text NOT NULL CHECK(license_fit IN ('PASS','FAIL','UNKNOWN')),
  security_fit text NOT NULL CHECK(security_fit IN ('PASS','FAIL','UNKNOWN')),
  policy_fit text NOT NULL CHECK(policy_fit IN ('PASS','FAIL','UNKNOWN')),
  eligible boolean NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(evidence)='object'),
  disqualifiers jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(disqualifiers)='array'),
  unknowns jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(unknowns)='array'),
  evaluated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE modernization_impact (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  modernization_candidate_id uuid NOT NULL UNIQUE
    REFERENCES modernization_candidate(id) ON DELETE CASCADE,
  affected_call_sites integer NOT NULL CHECK(affected_call_sites >= 0),
  affected_files integer NOT NULL CHECK(affected_files >= 0),
  covered_call_sites integer NOT NULL CHECK(covered_call_sites >= 0),
  uncovered_call_sites integer NOT NULL CHECK(uncovered_call_sites >= 0),
  affected_test_files text[] NOT NULL DEFAULT '{}',
  dynamic_signals text[] NOT NULL DEFAULT '{}',
  configuration_touchpoints jsonb NOT NULL DEFAULT '[]'
    CHECK(jsonb_typeof(configuration_touchpoints)='array'),
  build_touchpoints jsonb NOT NULL DEFAULT '[]'
    CHECK(jsonb_typeof(build_touchpoints)='array'),
  deployment_touchpoints jsonb NOT NULL DEFAULT '[]'
    CHECK(jsonb_typeof(deployment_touchpoints)='array'),
  evidence_locations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(evidence_locations)='array'),
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  effort_points integer NOT NULL CHECK(effort_points >= 0),
  effort_model_version text NOT NULL,
  limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE modernization_validation_outcome (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  modernization_recommendation_id uuid NOT NULL
    REFERENCES modernization_recommendation(id) ON DELETE CASCADE,
  validation_status text NOT NULL CHECK(validation_status IN ('SUCCEEDED','PARTIAL','FAILED')),
  actual_call_sites integer CHECK(actual_call_sites IS NULL OR actual_call_sites >= 0),
  actual_files integer CHECK(actual_files IS NULL OR actual_files >= 0),
  actual_effort text CHECK(actual_effort IS NULL OR actual_effort IN ('LOW','MEDIUM','HIGH','UNKNOWN')),
  successful_checks text[] NOT NULL DEFAULT '{}',
  failed_checks text[] NOT NULL DEFAULT '{}',
  notes text NOT NULL,
  reporter_actor_key text NOT NULL,
  reported_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_modernization_validation_recommendation
  ON modernization_validation_outcome(tenant_id,modernization_recommendation_id,reported_at DESC);

CREATE TABLE modernization_candidate_review (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  modernization_candidate_id uuid NOT NULL
    REFERENCES modernization_candidate(id) ON DELETE CASCADE,
  decision text NOT NULL CHECK(decision IN ('CONFIRM','REJECT')),
  rationale text NOT NULL,
  reviewer_actor_key text NOT NULL,
  prior_version integer NOT NULL CHECK(prior_version > 0),
  resulting_version integer NOT NULL CHECK(resulting_version=prior_version+1),
  reviewed_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE intelligence_job
  ADD COLUMN configuration_fingerprint text NOT NULL DEFAULT 'snapshot-v1';
DO $$
DECLARE
  existing_constraint text;
BEGIN
  SELECT constraint_record.conname INTO existing_constraint
  FROM pg_constraint constraint_record
  WHERE constraint_record.conrelid='intelligence_job'::regclass
    AND constraint_record.contype='u'
    AND (
      SELECT array_agg(attribute.attname ORDER BY key_column.ordinality)
      FROM unnest(constraint_record.conkey) WITH ORDINALITY
        AS key_column(attnum,ordinality)
      JOIN pg_attribute attribute
        ON attribute.attrelid=constraint_record.conrelid
       AND attribute.attnum=key_column.attnum
    )=ARRAY['tenant_id','repository_entity_id','source_revision','job_kind']::name[];
  IF existing_constraint IS NOT NULL THEN
    EXECUTE format(
      'ALTER TABLE intelligence_job DROP CONSTRAINT %I',
      existing_constraint
    );
  END IF;
END $$;
ALTER TABLE intelligence_job
  ADD CONSTRAINT intelligence_job_configuration_unique UNIQUE(
    tenant_id,repository_entity_id,source_revision,job_kind,configuration_fingerprint
  );

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
           'REPOSITORY_MODERNIZATION','snapshot-v1'
    FROM ingest_target target
    JOIN entity repository
      ON repository.tenant_id=NEW.tenant_id
     AND repository.namespace='ENTERPRISE'
     AND repository.entity_type='Repository'
     AND repository.canonical_key=target.target_key
    WHERE target.id=NEW.ingest_target_id
    ON CONFLICT DO NOTHING;
  END IF;
  RETURN NEW;
END $$;

ALTER TABLE code_implementation_summary ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON code_implementation_summary
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE modernization_policy ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON modernization_policy
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE modernization_internal_component ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON modernization_internal_component
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE modernization_option_evaluation ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON modernization_option_evaluation
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE modernization_impact ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON modernization_impact
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE modernization_validation_outcome ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON modernization_validation_outcome
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE modernization_candidate_review ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON modernization_candidate_review
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
