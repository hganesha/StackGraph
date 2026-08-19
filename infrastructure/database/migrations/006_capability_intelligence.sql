CREATE TABLE capability_taxonomy_version (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenant(id),
  taxonomy_key text NOT NULL CHECK(taxonomy_key ~ '^[a-z][a-z0-9_.-]{2,127}$'),
  version text NOT NULL CHECK(version ~ '^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$'),
  status text NOT NULL CHECK(status IN ('DRAFT','ACTIVE','RETIRED')),
  name text NOT NULL,
  description text NOT NULL,
  content_hash text NOT NULL CHECK(content_hash ~ '^sha256:[a-f0-9]{64}$'),
  metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),
  created_by text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE NULLS NOT DISTINCT(tenant_id,taxonomy_key,version)
);
CREATE UNIQUE INDEX uq_capability_taxonomy_active_global
  ON capability_taxonomy_version(taxonomy_key)
  WHERE tenant_id IS NULL AND status='ACTIVE';
CREATE UNIQUE INDEX uq_capability_taxonomy_active_tenant
  ON capability_taxonomy_version(tenant_id,taxonomy_key)
  WHERE tenant_id IS NOT NULL AND status='ACTIVE';

CREATE TABLE capability_definition (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  taxonomy_version_id uuid NOT NULL REFERENCES capability_taxonomy_version(id) ON DELETE CASCADE,
  capability_key text NOT NULL CHECK(capability_key ~ '^[a-z][a-z0-9.-]{1,127}$'),
  name text NOT NULL,
  description text NOT NULL,
  parent_capability_key text,
  aliases jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(aliases)='array'),
  metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),
  UNIQUE(taxonomy_version_id,capability_key)
);

CREATE TABLE capability_mapping (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  taxonomy_version_id uuid NOT NULL REFERENCES capability_taxonomy_version(id) ON DELETE CASCADE,
  capability_definition_id uuid NOT NULL REFERENCES capability_definition(id) ON DELETE CASCADE,
  ecosystem text NOT NULL CHECK(ecosystem IN ('npm','pypi')),
  package_name text NOT NULL,
  symbol_pattern text,
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  rationale text NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(evidence)='object'),
  UNIQUE NULLS NOT DISTINCT(
    taxonomy_version_id,ecosystem,package_name,symbol_pattern,capability_definition_id
  )
);
CREATE INDEX idx_capability_mapping_lookup
  ON capability_mapping(taxonomy_version_id,ecosystem,package_name);

CREATE TABLE capability_inference (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  subject_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  capability_definition_id uuid NOT NULL REFERENCES capability_definition(id),
  source_revision text NOT NULL,
  assertion_class text NOT NULL CHECK(assertion_class IN ('CURATED','INFERRED')),
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  confidence_band text NOT NULL CHECK(confidence_band IN ('LOW','MEDIUM','HIGH')),
  supporting_fact_ids uuid[] NOT NULL CHECK(cardinality(supporting_fact_ids)>0),
  counter_evidence_fact_ids uuid[] NOT NULL DEFAULT '{}',
  taxonomy_version_id uuid NOT NULL REFERENCES capability_taxonomy_version(id),
  analyzer_key text NOT NULL,
  analyzer_version text NOT NULL,
  model_invocation_id uuid REFERENCES ai_model_invocation(id),
  model_provider text,
  model_name text,
  policy_version text,
  input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  analysis_fingerprint text NOT NULL CHECK(analysis_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  rationale text NOT NULL,
  review_state text NOT NULL DEFAULT 'UNREVIEWED'
    CHECK(review_state IN ('UNREVIEWED','CONFIRMED','REJECTED')),
  version integer NOT NULL DEFAULT 1 CHECK(version>0),
  stale_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,analysis_fingerprint)
);
CREATE INDEX idx_capability_inference_repository
  ON capability_inference(tenant_id,repository_entity_id,source_revision,review_state);
CREATE INDEX idx_capability_inference_subject
  ON capability_inference(subject_entity_id,capability_definition_id);

CREATE TABLE capability_inference_review (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  capability_inference_id uuid NOT NULL REFERENCES capability_inference(id) ON DELETE CASCADE,
  decision text NOT NULL CHECK(decision IN ('CONFIRM','REJECT')),
  rationale text NOT NULL,
  reviewer_actor_key text NOT NULL,
  prior_version integer NOT NULL CHECK(prior_version>0),
  resulting_version integer NOT NULL CHECK(resulting_version=prior_version+1),
  reviewed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE duplicate_capability_candidate (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id),
  repository_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  capability_definition_id uuid NOT NULL REFERENCES capability_definition(id),
  source_revision text NOT NULL,
  dependency_entity_ids uuid[] NOT NULL CHECK(cardinality(dependency_entity_ids)>=2),
  capability_inference_ids uuid[] NOT NULL CHECK(cardinality(capability_inference_ids)>=2),
  supporting_fact_ids uuid[] NOT NULL CHECK(cardinality(supporting_fact_ids)>=2),
  confidence numeric(5,4) NOT NULL CHECK(confidence BETWEEN 0 AND 1),
  analysis_fingerprint text NOT NULL CHECK(analysis_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  summary text NOT NULL,
  limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'),
  review_state text NOT NULL DEFAULT 'UNREVIEWED'
    CHECK(review_state IN ('UNREVIEWED','CONFIRMED','REJECTED')),
  stale_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,analysis_fingerprint)
);
CREATE INDEX idx_duplicate_capability_repository
  ON duplicate_capability_candidate(tenant_id,repository_entity_id,source_revision,review_state);

ALTER TABLE capability_taxonomy_version ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON capability_taxonomy_version
  USING(tenant_id IS NULL OR tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE capability_definition ENABLE ROW LEVEL SECURITY;
CREATE POLICY capability_definition_visibility ON capability_definition USING(EXISTS(
  SELECT 1 FROM capability_taxonomy_version taxonomy
  WHERE taxonomy.id=taxonomy_version_id
    AND (taxonomy.tenant_id IS NULL OR taxonomy.tenant_id=stackgraph_current_tenant_id())
));
ALTER TABLE capability_mapping ENABLE ROW LEVEL SECURITY;
CREATE POLICY capability_mapping_visibility ON capability_mapping USING(EXISTS(
  SELECT 1 FROM capability_taxonomy_version taxonomy
  WHERE taxonomy.id=taxonomy_version_id
    AND (taxonomy.tenant_id IS NULL OR taxonomy.tenant_id=stackgraph_current_tenant_id())
));
ALTER TABLE capability_inference ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON capability_inference
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE capability_inference_review ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON capability_inference_review
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
ALTER TABLE duplicate_capability_candidate ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON duplicate_capability_candidate
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
