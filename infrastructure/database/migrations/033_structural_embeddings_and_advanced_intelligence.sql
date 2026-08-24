CREATE TABLE structural_embedding_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  analysis_run_id uuid NOT NULL,
  embedding_space_id uuid NOT NULL,
  algorithm_key text NOT NULL CHECK (algorithm_key<>''),
  algorithm_version text NOT NULL CHECK (algorithm_version<>''),
  configuration jsonb NOT NULL CHECK (jsonb_typeof(configuration)='object'),
  input_fingerprint text NOT NULL CHECK (input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  status text NOT NULL CHECK (status IN ('SUCCEEDED','SUCCEEDED_WITH_LIMITATIONS','FAILED')),
  node_count integer NOT NULL DEFAULT 0 CHECK (node_count>=0),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(limitations)='array'),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(analysis_run_id,tenant_id) REFERENCES graph_analysis_run(id,tenant_id) ON DELETE CASCADE,
  FOREIGN KEY(embedding_space_id,tenant_id) REFERENCES embedding_space(id,tenant_id) ON DELETE CASCADE,
  UNIQUE(analysis_run_id,algorithm_key)
);

CREATE TABLE graph_community_alignment (
  run_id uuid NOT NULL,
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  entity_id uuid NOT NULL,
  algorithm_key text NOT NULL CHECK (algorithm_key<>''),
  community_key text NOT NULL CHECK (community_key<>''),
  governed_domain_key text,
  mismatch_score double precision NOT NULL CHECK (mismatch_score BETWEEN 0 AND 1),
  cohort jsonb NOT NULL CHECK (jsonb_typeof(cohort)='object'),
  reasons jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(reasons)='array'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(run_id,entity_id,algorithm_key),
  FOREIGN KEY(run_id,tenant_id) REFERENCES graph_analysis_run(id,tenant_id) ON DELETE CASCADE,
  FOREIGN KEY(entity_id,tenant_id) REFERENCES entity(id,tenant_id) ON DELETE CASCADE
);

CREATE TABLE graph_anomaly (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL,
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  entity_id uuid NOT NULL,
  anomaly_key text NOT NULL CHECK (anomaly_key<>''),
  score double precision NOT NULL CHECK (score BETWEEN 0 AND 1),
  cohort_key text NOT NULL CHECK (cohort_key<>''),
  cohort_definition jsonb NOT NULL CHECK (jsonb_typeof(cohort_definition)='object'),
  observed_components jsonb NOT NULL CHECK (jsonb_typeof(observed_components)='object'),
  reasons jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(reasons)='array'),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(limitations)='array'),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(run_id,tenant_id) REFERENCES graph_analysis_run(id,tenant_id) ON DELETE CASCADE,
  FOREIGN KEY(entity_id,tenant_id) REFERENCES entity(id,tenant_id) ON DELETE CASCADE,
  UNIQUE(run_id,entity_id,anomaly_key,cohort_key)
);

CREATE TABLE graph_motif (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL,
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  motif_key text NOT NULL CHECK (motif_key IN (
    'CIRCULAR_DEPENDENCY','SHARED_DATABASE','DIRECT_DATABASE_BYPASS',
    'LEGACY_MIDDLEWARE_CHAIN','CROSS_DOMAIN_BRIDGE','DISTRIBUTED_MONOLITH'
  )),
  entity_ids uuid[] NOT NULL CHECK (cardinality(entity_ids)>=2),
  supporting_fact_ids uuid[] NOT NULL CHECK (cardinality(supporting_fact_ids)>=1),
  confidence double precision NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  components jsonb NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(components)='object'),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(limitations)='array'),
  created_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(run_id,tenant_id) REFERENCES graph_analysis_run(id,tenant_id) ON DELETE CASCADE,
  UNIQUE(run_id,motif_key,entity_ids,supporting_fact_ids)
);

CREATE TABLE application_description_proposal (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  application_id uuid NOT NULL,
  proposed_text text NOT NULL CHECK (proposed_text<>''),
  sentence_provenance jsonb NOT NULL CHECK (jsonb_typeof(sentence_provenance)='array'),
  source_revision_fingerprint text NOT NULL CHECK (source_revision_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  model_configuration jsonb NOT NULL CHECK (jsonb_typeof(model_configuration)='object'),
  sensitivity text NOT NULL CHECK (sensitivity IN ('PUBLIC','INTERNAL','CONFIDENTIAL','RESTRICTED')),
  confidence double precision NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK (jsonb_typeof(limitations)='array'),
  review_state text NOT NULL DEFAULT 'UNREVIEWED'
    CHECK (review_state IN ('UNREVIEWED','APPROVED','REJECTED','SUPERSEDED')),
  created_by text NOT NULL CHECK (created_by<>''),
  reviewed_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  reviewed_at timestamptz,
  FOREIGN KEY(application_id,tenant_id) REFERENCES entity(id,tenant_id) ON DELETE CASCADE
);

ALTER TABLE structural_embedding_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_community_alignment ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_anomaly ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_motif ENABLE ROW LEVEL SECURITY;
ALTER TABLE application_description_proposal ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'structural_embedding_run','graph_community_alignment','graph_anomaly',
    'graph_motif','application_description_proposal'
  ] LOOP
    EXECUTE format(
      'CREATE POLICY tenant_isolation ON %I USING (tenant_id=stackgraph_current_tenant_id()) WITH CHECK (tenant_id=stackgraph_current_tenant_id())',
      table_name
    );
  END LOOP;
END $$;

UPDATE graph_analysis_policy
SET status='RETIRED',retired_at=now()
WHERE tenant_id IS NULL AND policy_key='runtime-dependency' AND status='ACTIVE';

WITH prepared AS (
  SELECT '{
    "assertion_classes":["CURATED","DECLARED","OBSERVED"],
    "confidence_minimum":0.5,
    "directions":{"BUILT_ON":"OUT","CALLS":"OUT","CONNECTS_TO":"BOTH","DEPENDS_ON":"OUT","ENABLED_BY":"OUT","IMPLEMENTED_BY":"OUT","IMPLEMENTS":"OUT","RUNS_ON":"OUT","USES":"OUT"},
    "entity_types":["API","Application","BusinessCapability","BusinessProcess","Component","Database","Deployment","InfrastructureResource","Package","Repository","Runtime","Service","Technology"],
    "global_nodes":"REFERENCED",
    "identity_states":["CANONICAL","CONFIRMED"],
    "predicates":["BUILT_ON","CALLS","CONNECTS_TO","DEPENDS_ON","ENABLED_BY","IMPLEMENTED_BY","IMPLEMENTS","RUNS_ON","USES"],
    "projection_budget":{"max_edges":2000000,"max_nodes":500000,"timeout_seconds":900},
    "resource_class":"STANDARD",
    "structural_embedding":{"enabled":true,"algorithm":"gds.node2vec","dimensions":128,"walk_length":80,"walks_per_node":10,"random_seed":42,"max_nodes":200000}
  }'::jsonb AS configuration
)
INSERT INTO graph_analysis_policy(
  tenant_id,policy_key,version,name,status,configuration,content_hash,created_by,activated_at
)
SELECT NULL,'runtime-dependency',3,'Runtime dependency','ACTIVE',configuration,
       'sha256:'||encode(digest(configuration::text,'sha256'),'hex'),'migration:033',now()
FROM prepared;
