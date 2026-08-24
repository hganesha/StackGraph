-- Governed, tenant-safe graph analysis control plane.
-- PostgreSQL owns scheduling and immutable results; Neo4j/GDS is disposable compute.

CREATE TABLE graph_analysis_policy (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid REFERENCES tenant(id) ON DELETE CASCADE,
  policy_key text NOT NULL CHECK(policy_key ~ '^[a-z][a-z0-9-]{2,63}$'),
  version integer NOT NULL CHECK(version>0),
  name text NOT NULL CHECK(name<>''),
  status text NOT NULL DEFAULT 'DRAFT'
    CHECK(status IN ('DRAFT','ACTIVE','RETIRED')),
  configuration jsonb NOT NULL CHECK(jsonb_typeof(configuration)='object'),
  content_hash text NOT NULL CHECK(content_hash ~ '^sha256:[a-f0-9]{64}$'),
  created_by text NOT NULL CHECK(created_by<>''),
  created_at timestamptz NOT NULL DEFAULT now(),
  activated_at timestamptz,
  retired_at timestamptz,
  UNIQUE NULLS NOT DISTINCT(tenant_id,policy_key,version),
  UNIQUE(id,policy_key),
  CHECK((status='ACTIVE')=(activated_at IS NOT NULL)),
  CHECK((status='RETIRED')=(retired_at IS NOT NULL))
);

CREATE UNIQUE INDEX uq_graph_analysis_policy_active
  ON graph_analysis_policy(tenant_id,policy_key) NULLS NOT DISTINCT
  WHERE status='ACTIVE';

CREATE TABLE graph_analysis_request (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  policy_id uuid NOT NULL REFERENCES graph_analysis_policy(id) ON DELETE RESTRICT,
  policy_key text NOT NULL,
  requested_change_watermark bigint NOT NULL CHECK(requested_change_watermark>=0),
  reason text NOT NULL CHECK(reason<>''),
  status text NOT NULL DEFAULT 'PENDING'
    CHECK(status IN ('PENDING','WAITING_FOR_PROJECTION','RUNNING','SUCCEEDED','FAILED','CANCELLED')),
  available_at timestamptz NOT NULL DEFAULT now(),
  leased_by text,
  leased_until timestamptz,
  attempt integer NOT NULL DEFAULT 0 CHECK(attempt>=0),
  last_error jsonb,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY(policy_id,policy_key)
    REFERENCES graph_analysis_policy(id,policy_key) ON DELETE RESTRICT,
  CHECK((status='RUNNING')=(started_at IS NOT NULL AND completed_at IS NULL)),
  CHECK((status IN ('SUCCEEDED','FAILED','CANCELLED'))=(completed_at IS NOT NULL))
);

CREATE UNIQUE INDEX uq_graph_analysis_request_coalescing
  ON graph_analysis_request(tenant_id,policy_id)
  WHERE status IN ('PENDING','WAITING_FOR_PROJECTION');
CREATE INDEX idx_graph_analysis_request_claim
  ON graph_analysis_request(status,available_at,tenant_id,created_at)
  WHERE status IN ('PENDING','WAITING_FOR_PROJECTION');

CREATE TABLE graph_analysis_run (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  policy_id uuid NOT NULL REFERENCES graph_analysis_policy(id) ON DELETE RESTRICT,
  policy_key text NOT NULL,
  request_id uuid NOT NULL UNIQUE REFERENCES graph_analysis_request(id) ON DELETE RESTRICT,
  requested_change_watermark bigint NOT NULL CHECK(requested_change_watermark>=0),
  neo4j_projection_watermark bigint NOT NULL CHECK(neo4j_projection_watermark>=0),
  graph_source text NOT NULL DEFAULT 'NEO4J' CHECK(graph_source='NEO4J'),
  gds_graph_name text CHECK(gds_graph_name IS NULL OR gds_graph_name<>''),
  input_fingerprint text NOT NULL CHECK(input_fingerprint ~ '^sha256:[a-f0-9]{64}$'),
  algorithm_versions jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(algorithm_versions)='object'),
  status text NOT NULL DEFAULT 'RUNNING'
    CHECK(status IN ('RUNNING','SUCCEEDED','SUCCEEDED_WITH_LIMITATIONS','FAILED','CANCELLED')),
  stage text NOT NULL DEFAULT 'PREPARING'
    CHECK(stage IN ('PREPARING','LIGHTWEIGHT','HEAVYWEIGHT','PERSISTING','COMPLETE')),
  node_count bigint CHECK(node_count IS NULL OR node_count>=0),
  edge_count bigint CHECK(edge_count IS NULL OR edge_count>=0),
  coverage jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(coverage)='object'),
  resource_usage jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(resource_usage)='object'),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'),
  error_detail jsonb,
  worker_id text NOT NULL CHECK(worker_id<>''),
  lease_expires_at timestamptz NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(id,tenant_id,policy_key),
  FOREIGN KEY(policy_id,policy_key)
    REFERENCES graph_analysis_policy(id,policy_key) ON DELETE RESTRICT,
  CHECK((status='RUNNING')=(completed_at IS NULL)),
  CHECK((status='RUNNING')=(stage<>'COMPLETE'))
);

CREATE UNIQUE INDEX uq_graph_analysis_run_active_execution
  ON graph_analysis_run(tenant_id,policy_key)
  WHERE status='RUNNING';
CREATE INDEX idx_graph_analysis_run_history
  ON graph_analysis_run(tenant_id,policy_key,started_at DESC);

CREATE TABLE active_graph_analysis_run (
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  policy_key text NOT NULL,
  run_id uuid NOT NULL,
  activated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(tenant_id,policy_key),
  FOREIGN KEY(run_id,tenant_id,policy_key)
    REFERENCES graph_analysis_run(id,tenant_id,policy_key) ON DELETE RESTRICT
);

CREATE TABLE graph_entity_metric (
  run_id uuid NOT NULL REFERENCES graph_analysis_run(id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  metric_key text NOT NULL CHECK(metric_key ~ '^[a-z][a-z0-9_.-]{1,63}$'),
  numeric_value double precision,
  percentile double precision CHECK(percentile IS NULL OR percentile BETWEEN 0 AND 1),
  rank bigint CHECK(rank IS NULL OR rank>0),
  components jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(components)='object'),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(run_id,entity_id,metric_key)
);

CREATE INDEX idx_graph_entity_metric_lookup
  ON graph_entity_metric(tenant_id,entity_id,metric_key,run_id);
CREATE INDEX idx_graph_entity_metric_ranking
  ON graph_entity_metric(tenant_id,run_id,metric_key,numeric_value DESC NULLS LAST);

CREATE TABLE graph_edge_metric (
  run_id uuid NOT NULL REFERENCES graph_analysis_run(id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  fact_assertion_id uuid NOT NULL REFERENCES fact_assertion(id) ON DELETE CASCADE,
  subject_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  object_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  metric_key text NOT NULL CHECK(metric_key ~ '^[a-z][a-z0-9_.-]{1,63}$'),
  numeric_value double precision,
  components jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(components)='object'),
  limitations jsonb NOT NULL DEFAULT '[]' CHECK(jsonb_typeof(limitations)='array'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(run_id,fact_assertion_id,metric_key)
);

CREATE INDEX idx_graph_edge_metric_lookup
  ON graph_edge_metric(tenant_id,fact_assertion_id,metric_key,run_id);

CREATE TABLE graph_community_membership (
  run_id uuid NOT NULL REFERENCES graph_analysis_run(id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  algorithm_key text NOT NULL CHECK(algorithm_key ~ '^[a-z][a-z0-9_.-]{1,63}$'),
  community_key text NOT NULL CHECK(community_key<>''),
  score double precision,
  metadata jsonb NOT NULL DEFAULT '{}' CHECK(jsonb_typeof(metadata)='object'),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(run_id,entity_id,algorithm_key)
);

CREATE INDEX idx_graph_community_membership_lookup
  ON graph_community_membership(tenant_id,run_id,algorithm_key,community_key);

CREATE FUNCTION stackgraph_prevent_terminal_graph_run_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF OLD.status<>'RUNNING' THEN
    RAISE EXCEPTION 'terminal graph analysis run % is immutable',OLD.id
      USING ERRCODE='55000';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER graph_analysis_run_immutable
BEFORE UPDATE OR DELETE ON graph_analysis_run
FOR EACH ROW EXECUTE FUNCTION stackgraph_prevent_terminal_graph_run_mutation();

CREATE FUNCTION stackgraph_request_graph_analysis(
  requested_tenant_id uuid,
  requested_watermark bigint,
  requested_reason text DEFAULT 'PROJECTION_ADVANCED'
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
  affected integer;
BEGIN
  IF requested_tenant_id IS NULL OR requested_watermark<0 OR requested_reason='' THEN
    RAISE EXCEPTION 'tenant, non-negative watermark, and reason are required';
  END IF;

  WITH effective_policy AS (
    SELECT DISTINCT ON (policy.policy_key)
      policy.id,policy.policy_key
    FROM graph_analysis_policy policy
    WHERE policy.status='ACTIVE'
      AND (policy.tenant_id IS NULL OR policy.tenant_id=requested_tenant_id)
    ORDER BY policy.policy_key,(policy.tenant_id IS NOT NULL) DESC,policy.version DESC
  )
  INSERT INTO graph_analysis_request(
    tenant_id,policy_id,policy_key,requested_change_watermark,reason,status
  )
  SELECT requested_tenant_id,policy.id,policy.policy_key,requested_watermark,
         requested_reason,'PENDING'
  FROM effective_policy policy
  ON CONFLICT(tenant_id,policy_id)
    WHERE status IN ('PENDING','WAITING_FOR_PROJECTION')
  DO UPDATE SET
    requested_change_watermark=greatest(
      graph_analysis_request.requested_change_watermark,
      EXCLUDED.requested_change_watermark
    ),
    reason=EXCLUDED.reason,
    status=CASE
      WHEN greatest(
        graph_analysis_request.requested_change_watermark,
        EXCLUDED.requested_change_watermark
      )<=(
        SELECT deployment.projected_outbox_id
        FROM tenant_graph_deployment deployment
        WHERE deployment.tenant_id=requested_tenant_id
      ) THEN 'PENDING'
      ELSE 'WAITING_FOR_PROJECTION'
    END,
    available_at=now(),last_error=NULL,updated_at=now();

  GET DIAGNOSTICS affected=ROW_COUNT;
  RETURN affected;
END
$$;

WITH policy(policy_key,version,name,configuration) AS (
  VALUES
  ('runtime-dependency',1,'Runtime dependency',
    '{"assertion_classes":["CURATED","DECLARED","OBSERVED"],"confidence_minimum":0.5,"directions":{"BUILT_ON":"OUT","CALLS":"OUT","CONNECTS_TO":"BOTH","DEPENDS_ON":"OUT","RUNS_ON":"OUT","USES":"OUT"},"entity_types":["API","Application","Component","Database","Deployment","InfrastructureResource","Package","Runtime","Service","Technology"],"global_nodes":"REFERENCED","identity_states":["CANONICAL","CONFIRMED"],"predicates":["BUILT_ON","CALLS","CONNECTS_TO","DEPENDS_ON","RUNS_ON","USES"],"projection_budget":{"max_edges":2000000,"max_nodes":500000,"timeout_seconds":900},"resource_class":"STANDARD"}'::jsonb),
  ('business-alignment',1,'Business alignment',
    '{"assertion_classes":["CURATED","DECLARED","OBSERVED"],"confidence_minimum":0.5,"directions":{"CONTAINS":"OUT","ENABLED_BY":"OUT","IMPLEMENTS":"OUT","OPERATES":"OUT","OWNS":"OUT","PROVIDES":"OUT"},"entity_types":["Application","BusinessCapability","BusinessFunction","BusinessProcess","BusinessUnit","Organization","Service"],"global_nodes":"REFERENCED","identity_states":["CANONICAL","CONFIRMED"],"predicates":["CONTAINS","ENABLED_BY","IMPLEMENTS","OPERATES","OWNS","PROVIDES"],"projection_budget":{"max_edges":1000000,"max_nodes":250000,"timeout_seconds":600},"resource_class":"STANDARD"}'::jsonb),
  ('ownership',1,'Ownership',
    '{"assertion_classes":["CURATED","DECLARED","OBSERVED"],"confidence_minimum":0.5,"directions":{"CONTAINS":"OUT","OPERATES":"OUT","OWNS":"OUT"},"entity_types":["Application","BusinessUnit","Component","Organization","Repository","Service"],"global_nodes":"REFERENCED","identity_states":["CANONICAL","CONFIRMED"],"predicates":["CONTAINS","OPERATES","OWNS"],"projection_budget":{"max_edges":500000,"max_nodes":250000,"timeout_seconds":300},"resource_class":"LIGHTWEIGHT"}'::jsonb),
  ('technology-portfolio',1,'Technology portfolio',
    '{"assertion_classes":["CURATED","DECLARED","OBSERVED"],"confidence_minimum":0.5,"directions":{"BUILT_ON":"OUT","HAS_VERSION":"OUT","IMPLEMENTED_BY":"OUT","RUNS_ON":"OUT","USES":"OUT"},"entity_types":["Application","Component","Database","Framework","Language","Package","PackageVersion","Runtime","Service","Technology"],"global_nodes":"REFERENCED","identity_states":["CANONICAL","CONFIRMED"],"predicates":["BUILT_ON","HAS_VERSION","IMPLEMENTED_BY","RUNS_ON","USES"],"projection_budget":{"max_edges":1500000,"max_nodes":500000,"timeout_seconds":600},"resource_class":"STANDARD"}'::jsonb)
), prepared AS (
  SELECT policy_key,version,name,configuration,
    'sha256:'||encode(digest(configuration::text,'sha256'),'hex') AS content_hash
  FROM policy
)
INSERT INTO graph_analysis_policy(
  tenant_id,policy_key,version,name,status,configuration,content_hash,
  created_by,activated_at
)
SELECT NULL,policy_key,version,name,'ACTIVE',configuration,content_hash,
       'migration:029',now()
FROM prepared;

ALTER TABLE graph_analysis_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_analysis_request ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_analysis_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE active_graph_analysis_run ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_entity_metric ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_edge_metric ENABLE ROW LEVEL SECURITY;
ALTER TABLE graph_community_membership ENABLE ROW LEVEL SECURITY;

CREATE POLICY graph_analysis_policy_visibility ON graph_analysis_policy
  USING(tenant_id IS NULL OR tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
CREATE POLICY tenant_isolation ON graph_analysis_request
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
CREATE POLICY tenant_isolation ON graph_analysis_run
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
CREATE POLICY tenant_isolation ON active_graph_analysis_run
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
CREATE POLICY tenant_isolation ON graph_entity_metric
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
CREATE POLICY tenant_isolation ON graph_edge_metric
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
CREATE POLICY tenant_isolation ON graph_community_membership
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());
