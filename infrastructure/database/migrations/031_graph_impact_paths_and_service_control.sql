-- Evidence-backed blast-radius paths and an independently pausable graph worker.

ALTER TABLE tenant_service_control
  DROP CONSTRAINT tenant_service_control_service_key_check;
ALTER TABLE tenant_service_control
  ADD CONSTRAINT tenant_service_control_service_key_check
  CHECK(service_key IN (
    'github-webhook','github-control-loop','projection','intelligence','graph-intelligence'
  ));

CREATE TABLE graph_impact_path (
  run_id uuid NOT NULL REFERENCES graph_analysis_run(id) ON DELETE CASCADE,
  tenant_id uuid NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
  source_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  target_entity_id uuid NOT NULL REFERENCES entity(id) ON DELETE CASCADE,
  impact_kind text NOT NULL CHECK(impact_kind<>''),
  distance integer NOT NULL CHECK(distance>0),
  path_entity_ids uuid[] NOT NULL,
  path_fact_ids uuid[] NOT NULL,
  minimum_confidence double precision NOT NULL CHECK(minimum_confidence BETWEEN 0 AND 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(run_id,source_entity_id,target_entity_id,impact_kind),
  FOREIGN KEY(run_id,tenant_id)
    REFERENCES graph_analysis_run(id,tenant_id) ON DELETE CASCADE,
  CHECK(source_entity_id<>target_entity_id),
  CHECK(cardinality(path_entity_ids)=distance+1),
  CHECK(cardinality(path_fact_ids)=distance),
  CHECK(path_entity_ids[1]=source_entity_id),
  CHECK(path_entity_ids[cardinality(path_entity_ids)]=target_entity_id)
);

CREATE INDEX idx_graph_impact_path_source
  ON graph_impact_path(tenant_id,run_id,source_entity_id,distance,target_entity_id);
CREATE INDEX idx_graph_impact_path_target
  ON graph_impact_path(tenant_id,run_id,target_entity_id,distance,source_entity_id);

ALTER TABLE graph_impact_path ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON graph_impact_path
  USING(tenant_id=stackgraph_current_tenant_id())
  WITH CHECK(tenant_id=stackgraph_current_tenant_id());

UPDATE graph_analysis_policy
SET status='RETIRED',retired_at=now()
WHERE tenant_id IS NULL AND policy_key='runtime-dependency' AND status='ACTIVE';

WITH prepared AS (
  SELECT
    '{"assertion_classes":["CURATED","DECLARED","OBSERVED"],"confidence_minimum":0.5,"directions":{"BUILT_ON":"OUT","CALLS":"OUT","CONNECTS_TO":"BOTH","DEPENDS_ON":"OUT","ENABLED_BY":"OUT","IMPLEMENTED_BY":"OUT","IMPLEMENTS":"OUT","RUNS_ON":"OUT","USES":"OUT"},"entity_types":["API","Application","BusinessCapability","BusinessProcess","Component","Database","Deployment","InfrastructureResource","Package","Repository","Runtime","Service","Technology"],"global_nodes":"REFERENCED","identity_states":["CANONICAL","CONFIRMED"],"predicates":["BUILT_ON","CALLS","CONNECTS_TO","DEPENDS_ON","ENABLED_BY","IMPLEMENTED_BY","IMPLEMENTS","RUNS_ON","USES"],"projection_budget":{"max_edges":2000000,"max_nodes":500000,"timeout_seconds":900},"resource_class":"STANDARD"}'::jsonb AS configuration
)
INSERT INTO graph_analysis_policy(
  tenant_id,policy_key,version,name,status,configuration,content_hash,
  created_by,activated_at
)
SELECT NULL,'runtime-dependency',2,'Runtime dependency','ACTIVE',configuration,
       'sha256:'||encode(digest(configuration::text,'sha256'),'hex'),
       'migration:031',now()
FROM prepared;
